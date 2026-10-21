"""Intégration proxy <-> menu F6 : ouverture/fermeture, tampon de sortie, écran
alternatif de l'enfant, application et persistance des réglages.

Le "vrai terminal" est simulé par une paire de pseudo-terminaux (le proxy
écrit sur `slave_fd`, le test lit ce qui en sort sur `master_fd`) : les deux
passent `os.isatty()`, contrairement à un pipe, ce qui exerce les mêmes
branches que l'exécution réelle.
"""

import os
import pty
import select
import signal

import pytest

from steph import config as config_mod
from steph import menu, setup
from steph.config import Config
from steph.narrator import Narrator
from steph.proxy import PtyProxy
from steph.session import Session

from test_rules import FakeLLM, FakeSpeaker


class SettingSpeaker(FakeSpeaker):
    """FakeSpeaker + ce que le menu attend pour appliquer un réglage à chaud."""

    def __init__(self):
        super().__init__()
        self.enabled = True
        self.reloaded_voice = None
        self.rate = None

    def reload_voice(self, path):
        self.reloaded_voice = path

    def set_rate(self, rate):
        self.rate = rate


@pytest.fixture
def pty_pair():
    master_fd, slave_fd = pty.openpty()
    yield master_fd, slave_fd
    for fd in (master_fd, slave_fd):
        try:
            os.close(fd)
        except OSError:
            pass


def drain(fd) -> bytes:
    out = b""
    while select.select([fd], [], [], 0)[0]:
        chunk = os.read(fd, 65536)
        if not chunk:
            break
        out += chunk
    return out


def press(proxy, master_fd, slave_fd, key: bytes) -> bytes:
    """Envoie une touche puis draine `master_fd`, comme le ferait un vrai terminal
    qui lit en continu (sinon le tampon du pty peut se remplir et bloquer l'écriture
    si plusieurs touches s'enchaînent sans lecture entre elles)."""
    proxy._on_input(key, slave_fd)
    return drain(master_fd)


@pytest.fixture(autouse=True)
def full_screen_terminal(monkeypatch):
    """Isole le choix du mode : terminal capable, aucun lecteur d'écran sondé pour de vrai."""
    monkeypatch.setenv("TERM", "xterm-256color")
    monkeypatch.delenv("STEPH_UI", raising=False)


def make_proxy(on_ask=None, reader=None, ui="auto"):
    cfg = Config(ui=ui)
    nar = Narrator(cfg, Session(), FakeSpeaker(), FakeLLM())
    nar.llm_ready = True
    proxy = PtyProxy(cfg, nar, "/tmp/unused.sock", on_ask=on_ask, help_keys="F7 questions.")
    proxy.screen_reader = reader or (lambda: None)
    return proxy, nar, cfg


# ------------------------------------------------------------ touche


def test_key_menu_default_does_not_clash_with_other_keys():
    cfg = Config()
    others = [cfg.key_stop, cfg.key_repeat, cfg.key_details, cfg.key_ask,
              cfg.key_line_first, cfg.key_line_prev, cfg.key_line_next, cfg.key_line_last]
    assert all(cfg.key_menu not in o and o not in cfg.key_menu for o in others)


# ------------------------------------------------------------ ouverture


def test_f6_opens_menu_and_renders_first_screen(pty_pair):
    master_fd, slave_fd = pty_pair
    proxy, nar, cfg = make_proxy()
    data = proxy._on_input(cfg.key_menu.encode(), slave_fd)
    assert data == b""
    assert proxy.menu is not None
    out = drain(master_fd)
    assert out.startswith(b"\x1b[?1049h\x1b[?25l")
    assert b"\x1b[2J\x1b[H" in out
    assert b"Menu" in out and b"Couper la parole" in out
    assert nar.sp.said and nar.sp.said[0].startswith("Menu steph. ")


def test_f6_does_nothing_when_stdin_is_not_a_tty(pty_pair):
    master_fd, slave_fd = pty_pair
    proxy, nar, cfg = make_proxy()
    proxy._is_tty = False
    data = proxy._on_input(cfg.key_menu.encode(), slave_fd)
    assert data == b""  # la touche est quand même avalée, comme les autres touches
    assert proxy.menu is None
    assert drain(master_fd) == b""


# ------------------------------------------------------------ pendant que le menu est ouvert


def test_menu_open_swallows_all_input_and_skips_typing_tracker(pty_pair):
    master_fd, slave_fd = pty_pair
    proxy, nar, cfg = make_proxy()
    proxy._on_input(cfg.key_menu.encode(), slave_fd)
    drain(master_fd)
    data = proxy._on_input(b"ls -la\r", slave_fd)
    assert data == b""
    assert proxy._typed == ""  # pas de suivi de frappe pendant que le menu est ouvert


def test_shell_output_is_buffered_while_menu_is_open(pty_pair):
    master_fd, slave_fd = pty_pair
    proxy, nar, cfg = make_proxy()
    proxy._on_input(cfg.key_menu.encode(), slave_fd)
    drain(master_fd)
    proxy._on_output(b"nouvelle ligne\n", slave_fd)
    assert bytes(proxy._menu_out_buf) == b"nouvelle ligne\n"
    assert drain(master_fd) == b""  # rien n'est écrit tant que le menu est ouvert


# ------------------------------------------------------------ fermeture


def test_close_restores_screen_and_flushes_buffered_output(pty_pair):
    master_fd, slave_fd = pty_pair
    proxy, nar, cfg = make_proxy()
    proxy._on_input(cfg.key_menu.encode(), slave_fd)
    drain(master_fd)
    proxy._on_output(b"nouvelle ligne\n", slave_fd)
    proxy._on_input(b"\x1b", slave_fd)  # Echap : ferme
    assert proxy.menu is None
    out = drain(master_fd)
    assert out.startswith(b"\x1b[?25h\x1b[?1049l")
    assert out.endswith(b"nouvelle ligne\r\n")  # le pty traduit \n en \r\n (ONLCR), comme un vrai terminal


def test_action_routes_to_narrator_on_key_after_close(pty_pair):
    master_fd, slave_fd = pty_pair
    proxy, nar, cfg = make_proxy()
    got = []
    nar.on_key = lambda w: got.append(w)
    proxy._on_input(cfg.key_menu.encode(), slave_fd)
    drain(master_fd)
    proxy._on_input(b"\r", slave_fd)  # Entrée sur "Couper la parole" (1er élément)
    assert got == ["stop"]


def test_ask_action_routes_to_on_ask_callback(pty_pair):
    master_fd, slave_fd = pty_pair
    calls = []
    proxy, nar, cfg = make_proxy(on_ask=lambda: calls.append(1))
    press(proxy, master_fd, slave_fd, cfg.key_menu.encode())
    for _ in range(3):  # -> "Poser une question" (index 3)
        press(proxy, master_fd, slave_fd, menu.DOWN[0])
    press(proxy, master_fd, slave_fd, b"\r")
    assert calls == [1]


def test_child_alt_screen_is_restored_with_sigwinch_on_close(pty_pair, monkeypatch):
    master_fd, slave_fd = pty_pair
    proxy, nar, cfg = make_proxy()
    proxy._child_pid = 424242
    kills = []
    monkeypatch.setattr(os, "kill", lambda pid, sig: kills.append((pid, sig)))
    # le shell était déjà en écran alternatif (vim, htop…) avant l'ouverture du menu
    proxy._on_output(b"\x1b[?1049h", slave_fd)
    drain(master_fd)
    assert proxy._child_alt_screen is True
    proxy._on_input(cfg.key_menu.encode(), slave_fd)
    drain(master_fd)
    proxy._on_input(b"\x1b", slave_fd)
    out = drain(master_fd)
    assert b"\x1b[?25h\x1b[?1049l\x1b[?1049h" in out
    assert kills == [(424242, signal.SIGWINCH)]


# ------------------------------------------------------------ réglages : application + persistance


def enter_settings_on_voice(proxy, master_fd, slave_fd, cfg):
    press(proxy, master_fd, slave_fd, cfg.key_menu.encode())
    for _ in range(6):  # -> "Réglages"
        press(proxy, master_fd, slave_fd, menu.DOWN[0])
    press(proxy, master_fd, slave_fd, b"\r")  # entre, sur "Voix"


def test_setting_change_applies_to_speaker_and_persists(pty_pair, monkeypatch):
    master_fd, slave_fd = pty_pair
    proxy, nar, cfg = make_proxy()
    nar.sp = SettingSpeaker()
    saved = []
    monkeypatch.setattr(setup, "save_settings", lambda path, answers: saved.append((path, dict(answers))))
    enter_settings_on_voice(proxy, master_fd, slave_fd, cfg)
    press(proxy, master_fd, slave_fd, b"\r")  # bascule tts_enabled -> False
    assert cfg.tts_enabled is False
    assert nar.sp.enabled is False
    assert saved == [(config_mod.CONFIG_PATH, {"tts_enabled": False})]


def test_rate_change_applies_via_set_rate(pty_pair, monkeypatch):
    master_fd, slave_fd = pty_pair
    proxy, nar, cfg = make_proxy()
    nar.sp = SettingSpeaker()
    monkeypatch.setattr(setup, "save_settings", lambda *a, **k: None)
    enter_settings_on_voice(proxy, master_fd, slave_fd, cfg)
    press(proxy, master_fd, slave_fd, menu.DOWN[0])  # -> "Débit de parole"
    press(proxy, master_fd, slave_fd, menu.RIGHT[0])  # augmente le débit
    assert nar.sp.rate == cfg.speech_rate


# ------------------------------------------------------------ M6 : rendu partiel et mode ligne


def test_moving_in_the_menu_writes_a_partial_update_with_the_cursor_on_the_item(pty_pair):
    master_fd, slave_fd = pty_pair
    proxy, nar, cfg = make_proxy()
    press(proxy, master_fd, slave_fd, cfg.key_menu.encode())
    out = press(proxy, master_fd, slave_fd, menu.DOWN[0])
    assert b"\x1b[2J" not in out
    assert out.count(b"\x1b[2K") == 5  # description (3 lignes) + ancienne + nouvelle ligne
    assert out.endswith(b"\x1b[6;1H\x1b[0m\x1b[?25h")


def test_unknown_key_writes_nothing(pty_pair):
    master_fd, slave_fd = pty_pair
    proxy, nar, cfg = make_proxy()
    press(proxy, master_fd, slave_fd, cfg.key_menu.encode())
    assert press(proxy, master_fd, slave_fd, b"x") == b""


def test_screen_reader_opens_the_menu_in_line_mode(pty_pair):
    master_fd, slave_fd = pty_pair
    proxy, nar, cfg = make_proxy(reader=lambda: "VoiceOver")
    out = press(proxy, master_fd, slave_fd, cfg.key_menu.encode())
    # l'écran du shell reste intact ; un seul effacement, à l'ouverture, pour partir du haut
    assert out.startswith(b"\x1b[?1049h\x1b[H\x1b[2J")
    assert out.count(b"\x1b[2J") == 1 and b"\x1b[?25l" not in out
    # le pty de test garde ONLCR : chaque \n écrit arrive en \r\n, d'où \r\r\n
    assert out.endswith("Menu steph, mode ligne. Flèches pour naviguer, Entrée pour choisir, Échap pour fermer."
                        "\r\r\nMenu steph. Couper la parole. 9 éléments.\r\r\n".encode())
    out = press(proxy, master_fd, slave_fd, menu.DOWN[0])
    assert out == "Répéter\r\r\n".encode()  # ajout seul : une ligne, aucun déplacement du curseur
    out = press(proxy, master_fd, slave_fd, b"\x1b")
    assert out.startswith("Menu fermé.\r\r\n\x1b[?25h\x1b[?1049l".encode())
    assert proxy.menu is None


def test_user_choice_opens_the_menu_in_line_mode(pty_pair):
    master_fd, slave_fd = pty_pair
    proxy, nar, cfg = make_proxy(ui="line")
    out = press(proxy, master_fd, slave_fd, cfg.key_menu.encode())
    assert out.count(b"\x1b[2J") == 1 and b"mode ligne" in out
    assert press(proxy, master_fd, slave_fd, menu.DOWN[0]) == "Répéter\r\r\n".encode()


def test_dumb_terminal_opens_the_menu_in_line_mode(pty_pair, monkeypatch):
    master_fd, slave_fd = pty_pair
    monkeypatch.setenv("TERM", "dumb")
    proxy, nar, cfg = make_proxy()
    out = press(proxy, master_fd, slave_fd, cfg.key_menu.encode())
    assert b"\x1b" not in out and b"mode ligne" in out  # terminal sans séquences : texte seul
    assert out.startswith(b"\r\r\n")  # sur une ligne neuve, pas à la suite de l'invite
    press(proxy, master_fd, slave_fd, menu.DOWN[0])
    out = press(proxy, master_fd, slave_fd, b"\x1b")
    assert out == "Menu fermé.\r\r\n".encode()  # le retour au shell se lit aussi


def test_line_mode_setting_change_is_one_line(pty_pair, monkeypatch):
    master_fd, slave_fd = pty_pair
    monkeypatch.setattr(setup, "save_settings", lambda *a, **k: None)
    proxy, nar, cfg = make_proxy(reader=lambda: "Orca")
    nar.sp = SettingSpeaker()
    enter_settings_on_voice(proxy, master_fd, slave_fd, cfg)
    out = press(proxy, master_fd, slave_fd, menu.RIGHT[0])
    assert out == "Voix coupée.\r\r\n".encode()


def test_full_screen_render_resets_colors_at_the_end(pty_pair):
    master_fd, slave_fd = pty_pair
    proxy, nar, cfg = make_proxy()
    out = press(proxy, master_fd, slave_fd, cfg.key_menu.encode())
    # aucune couleur de fond ne doit fuir vers l'écran du shell à la fermeture
    assert out.endswith(b"\x1b[0m\x1b[?25h")
