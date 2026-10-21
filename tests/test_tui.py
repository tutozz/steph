"""M6 : TUI accessible (tui.py) - choix du mode, modèle d'état, rendu partiel, voix."""

import subprocess

import pyte
import pytest

from steph import tui
from steph.term_style import Style
from steph.textproc import strip_ansi

ROWS, COLS = 24, 80


# ------------------------------------------------------------ choix du mode


def no_reader():
    return None


@pytest.mark.parametrize("pref, env, isatty, reader, expected", [
    ("auto", {"TERM": "xterm-256color"}, True, no_reader, ("tui", "tui")),
    ("auto", {"TERM": "xterm-256color"}, False, no_reader, ("line", "no_tty")),
    ("tui", {"TERM": "xterm-256color"}, False, no_reader, ("line", "no_tty")),
    ("auto", {"TERM": "dumb"}, True, no_reader, ("line", "dumb")),
    ("tui", {}, True, no_reader, ("line", "dumb")),
    ("line", {"TERM": "xterm"}, True, no_reader, ("line", "user")),
    ("auto", {"TERM": "xterm"}, True, lambda: "VoiceOver", ("line", "screen_reader")),
    ("tui", {"TERM": "xterm"}, True, lambda: "VoiceOver", ("tui", "user")),
    ("n'importe", {"TERM": "xterm"}, True, no_reader, ("tui", "tui")),
])
def test_ui_mode_decision_order(pref, env, isatty, reader, expected):
    assert tui.ui_mode(pref, env, isatty, reader) == expected


def test_ui_mode_does_not_probe_the_screen_reader_when_the_user_chose():
    def reader():
        raise AssertionError("sonde inutile : l'utilisateur a choisi")

    assert tui.ui_mode("line", {"TERM": "xterm"}, True, reader) == ("line", "user")
    assert tui.ui_mode("auto", {"TERM": "dumb"}, True, reader) == ("line", "dumb")


def test_no_color_keeps_the_full_screen_mode():
    assert tui.ui_mode("auto", {"TERM": "xterm", "NO_COLOR": "1"}, True, no_reader) == ("tui", "tui")


def test_ui_is_a_config_key_overridable_by_steph_ui(monkeypatch, tmp_path):
    from steph import config

    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "absent.toml")
    assert config.load_config().ui == "auto"
    monkeypatch.setenv("STEPH_UI", "line")
    assert config.load_config().ui == "line"


class FakeRun:
    """subprocess.run simulé : réponses par premier mot de commande."""

    def __init__(self, answers):
        self.answers = answers
        self.calls = []

    def __call__(self, argv, **kwargs):
        self.calls.append(argv)
        assert kwargs.get("timeout"), "chaque sonde doit être bornée dans le temps"
        answer = self.answers.get(" ".join(argv))
        if isinstance(answer, Exception):
            raise answer
        code, out = answer if answer is not None else (1, "")
        return subprocess.CompletedProcess(argv, code, stdout=out, stderr="")


def test_voiceover_detected_by_its_process():
    run = FakeRun({"pgrep -x VoiceOver": (0, "123\n")})
    assert tui.screen_reader_active("darwin", run, lambda p: False) == "VoiceOver"


def test_voiceover_detected_by_its_defaults_key():
    run = FakeRun({"defaults read com.apple.universalaccess voiceOverOnOffKey": (0, "1\n")})
    assert tui.screen_reader_active("darwin", run, lambda p: False) == "VoiceOver"


def test_voiceover_off_on_this_mac_state():
    # état observé sur le Mac de développement : clé à 0, aucun processus
    run = FakeRun({"defaults read com.apple.universalaccess voiceOverOnOffKey": (0, "0\n")})
    assert tui.screen_reader_active("darwin", run, lambda p: False) is None


def test_orca_detected_by_process_or_gsettings():
    assert tui.screen_reader_active("linux", FakeRun({"pgrep -x orca": (0, "42\n")}), lambda p: False) == "Orca"
    gs = "gsettings get org.gnome.desktop.a11y.applications screen-reader-enabled"
    assert tui.screen_reader_active("linux", FakeRun({gs: (0, "true\n")}), lambda p: False) == "Orca"
    assert tui.screen_reader_active("linux", FakeRun({gs: (0, "false\n")}), lambda p: False) is None


def test_speakup_and_brltty_detected_on_linux():
    assert tui.screen_reader_active("linux", FakeRun({}), lambda p: p == "/sys/accessibility/speakup") == "Speakup"
    assert tui.screen_reader_active("linux", FakeRun({"pgrep -x brltty": (0, "1\n")}), lambda p: False) == "BRLTTY"


def test_failing_probes_count_as_no_screen_reader():
    boom = FakeRun({"pgrep -x VoiceOver": FileNotFoundError(),
                    "defaults read com.apple.universalaccess voiceOverOnOffKey":
                        subprocess.TimeoutExpired("defaults", 1)})
    assert tui.screen_reader_active("darwin", boom, lambda p: False) is None
    assert tui.screen_reader_active("linux", FakeRun({"pgrep -x orca": OSError()}), lambda p: False) is None


def test_other_platforms_have_no_probe():
    run = FakeRun({})
    assert tui.screen_reader_active("win32", run, lambda p: True) is None
    assert run.calls == []


# ------------------------------------------------------------ touches


@pytest.mark.parametrize("seq, name", [
    (b"\x1b[A", "up"), (b"\x1bOA", "up"), (b"\x1b[B", "down"), (b"\x1bOB", "down"),
    (b"\x1b[C", "right"), (b"\x1b[D", "left"), (b"\r", "enter"), (b"\n", "enter"),
    (b"\x1b", "escape"), (b"\t", "tab"), (b"\x1b[Z", "backtab"),
    (b"\x1b[H", "home"), (b"\x1bOH", "home"), (b"\x1b[1~", "home"),
    (b"\x1b[F", "end"), (b"\x1bOF", "end"), (b"\x1b[4~", "end"),
    (b"\x7f", "backspace"), (b"\x03", "interrupt"), (b"\x04", "interrupt"),
    (b"?", "?"), (b"3", "3"), (b"\x1b[17~", "\x1b[17~"),
])
def test_decode_key(seq, name):
    assert tui.decode_key(seq) == name


# ------------------------------------------------------------ modèle d'état


def models_options():
    return [
        tui.Option("Gemma 4 E2B", notes=("recommandé",), tag="recommended", detail="3 200 Mo."),
        tui.Option("Granite 4.2 1B", notes=("non recommandé : pas optimisé pour steph",), tag="muted",
                   detail="900 Mo."),
        tui.Option("Qwen 3 8B", blocked="hors de portée de cette machine", detail="5 000 Mo."),
    ]


def make_model(focus=0, language="fr"):
    return tui.ChoiceModel("Configuration", "Modèle de langage", models_options(), focus=focus,
                           step="étape 1 sur 5", language=language)


def test_spoken_focus_is_label_and_state():
    m = make_model()
    assert m.spoken(0) == "Gemma 4 E2B, recommandé"
    assert m.spoken(1) == "Granite 4.2 1B, non recommandé : pas optimisé pour steph"
    assert m.spoken(2) == "Qwen 3 8B, bloqué : hors de portée de cette machine"


def test_opening_says_question_focus_count_and_help_hint():
    assert make_model().opening() == \
        "Modèle de langage. Gemma 4 E2B, recommandé. 3 choix. Point d'interrogation pour l'aide."


def test_opening_in_english():
    m = tui.ChoiceModel("Setup", "Language model", [tui.Option("A"), tui.Option("B")], language="en")
    assert m.opening() == "Language model. A. 2 choices. Question mark for help."


@pytest.mark.parametrize("key, focus", [
    ("down", 1), ("tab", 1), ("up", 2), ("backtab", 2), ("end", 2), ("3", 2), ("2", 1),
])
def test_focus_moves_and_says_label_and_state(key, focus):
    m = make_model()
    out = m.handle(key)
    assert m.focus == focus
    assert out.say == m.spoken(focus)
    assert out.redraw == "focus" and out.old == 0 and out.done is None and not out.cancelled


def test_home_goes_back_to_the_first_option():
    m = make_model(focus=2)
    assert m.handle("home").say == "Gemma 4 E2B, recommandé"
    assert m.focus == 0


def test_focus_wraps_at_both_ends():
    m = make_model(focus=2)
    assert m.handle("down").say == "Gemma 4 E2B, recommandé"
    assert m.focus == 0
    m.handle("up")
    assert m.focus == 2


def test_digit_out_of_range_and_unknown_keys_do_nothing():
    m = make_model()
    for key in ("9", "0", "x", "left", "right", "backspace", "\x1b[17~"):
        out = m.handle(key)
        assert out == tui.Outcome()
        assert m.focus == 0


def test_enter_validates_the_focused_option():
    m = make_model(focus=1)
    assert m.handle("enter").done == 1


def test_enter_on_blocked_option_says_the_reason_and_stays():
    m = make_model(focus=2)
    out = m.handle("enter")
    assert out.done is None
    assert out.say == "Qwen 3 8B : hors de portée de cette machine. Choisissez une autre option."
    assert m.focus == 2


@pytest.mark.parametrize("key", ["escape", "interrupt"])
def test_escape_and_ctrl_c_cancel(key):
    assert make_model().handle(key).cancelled


def test_question_mark_says_help_and_shows_it():
    m = make_model()
    out = m.handle("?")
    assert out.say.startswith("Flèches haut et bas")
    assert out.redraw == "description"
    assert m.showing_help
    m.handle("down")
    assert not m.showing_help  # un mouvement rend la description de l'option


def test_moving_to_the_same_option_says_nothing():
    m = make_model()
    assert m.handle("1") == tui.Outcome()


# ------------------------------------------------------------ rendu


def screen(raw: str, rows=ROWS, cols=COLS) -> pyte.Screen:
    s = pyte.Screen(cols, rows)
    pyte.Stream(s).feed(raw)
    return s


def lines(s: pyte.Screen) -> list[str]:
    return [line.rstrip() for line in s.display]


def test_full_render_shows_logo_title_step_question_options_description_and_keys():
    r = tui.Renderer(Style(None), ROWS, COLS)
    s = screen(r.full(make_model()))
    text = lines(s)
    assert text[0].startswith(" steph ›  Configuration")
    assert text[0].endswith("étape 1 sur 5")
    assert text[2] == "Modèle de langage"
    assert text[4].startswith("› 1  Gemma 4 E2B") and "recommandé" in text[4]
    assert text[5].startswith("  2  Granite 4.2 1B") and "non recommandé" in text[5]
    assert text[6].startswith("  3  Qwen 3 8B") and "bloqué : hors de portée de cette machine" in text[6]
    assert "3 200 Mo." in "\n".join(text)
    assert text[-1].startswith("↑↓ choisir · Entrée valider")


def test_full_render_leaves_the_visible_cursor_on_the_focused_line():
    m = make_model(focus=1)
    raw = tui.Renderer(Style(None), ROWS, COLS).full(m)
    s = screen(raw)
    assert (s.cursor.y, s.cursor.x) == (5, 0)
    assert raw.endswith("\x1b[?25h")


def test_focus_change_rewrites_only_description_and_two_lines():
    m = make_model()
    r = tui.Renderer(Style(None), ROWS, COLS)
    s = screen(r.full(m))
    before = lines(s)
    out = m.handle("down")
    update = r.update(m, out)
    assert "\x1b[2J" not in update
    assert update.count("\x1b[2K") == tui.DESCRIPTION_LINES + 2
    pyte.Stream(s).feed(update)
    after = lines(s)
    changed = [i for i in range(ROWS) if before[i] != after[i]]
    assert set(changed) <= {4, 5, *r.description_rows(m)}
    assert after[4].startswith("  1  Gemma") and after[5].startswith("› 2  Granite")
    assert "900 Mo." in "\n".join(after)
    assert (s.cursor.y, s.cursor.x) == (5, 0)


def test_update_draws_the_new_line_last_so_the_cursor_ends_on_it():
    m = make_model()
    r = tui.Renderer(Style(None), ROWS, COLS)
    r.full(m)
    update = r.update(m, m.handle("down"))
    assert update.rindex("Granite") > update.rindex("Gemma")


def test_help_rewrites_only_the_description_block():
    m = make_model()
    r = tui.Renderer(Style(None), ROWS, COLS)
    s = screen(r.full(m))
    update = r.update(m, m.handle("?"))
    assert update.count("\x1b[2K") == tui.DESCRIPTION_LINES
    pyte.Stream(s).feed(update)
    assert "Flèches haut et bas" in "\n".join(lines(s))
    assert (s.cursor.y, s.cursor.x) == (4, 0)


def test_long_lists_scroll_and_scrolling_redraws_everything():
    options = [tui.Option(f"option {i}") for i in range(30)]
    m = tui.ChoiceModel("T", "Q", options)
    r = tui.Renderer(Style(None), 12, COLS)
    s = screen(r.full(m), rows=12)
    assert "option 0" in lines(s)[4]
    update = ""
    for _ in range(10):
        update = r.update(m, m.handle("down"))
    assert "\x1b[2J" in update
    s = screen(update, rows=12)
    assert any(line.startswith("›") and "option 10" in line for line in lines(s))
    assert s.cursor.y == next(i for i, line in enumerate(lines(s)) if line.startswith("›"))


def test_every_line_fits_the_width():
    m = make_model()
    r = tui.Renderer(Style("truecolor"), ROWS, 20)
    for line in lines(screen(r.full(m), cols=20)):
        assert len(line) <= 20


def test_plain_render_marks_focus_with_chevron_and_reverse_video_only():
    raw = tui.Renderer(Style(None), ROWS, COLS).full(make_model())
    assert "\x1b[7m" in raw
    assert "\x1b[38;" not in raw and "\x1b[48;" not in raw


def test_colored_render_follows_the_charter():
    raw = tui.Renderer(Style("truecolor"), ROWS, COLS).full(make_model())
    assert raw.startswith("\x1b[?25l\x1b[48;2;11;11;11m\x1b[2J")  # fond noir, curseur masqué pendant le dessin
    assert "\x1b[38;2;11;11;11;48;2;226;255;59m steph › \x1b[0m" in raw  # logo sur citron
    assert "\x1b[1;38;2;11;11;11;48;2;226;255;59m› 1  Gemma 4 E2B" in raw  # focus noir sur citron
    assert "\x1b[38;2;11;11;11;48;2;226;255;59mrecommandé\x1b[0m" not in raw.split("› 1")[0]
    s = screen(raw)
    blocked = s.buffer[6][5]  # « Q » de Qwen, option bloquée : gris
    assert blocked.data == "Q" and blocked.fg == "8a8a85"


def test_colored_and_plain_renders_read_the_same():
    m = make_model()
    colored = lines(screen(tui.Renderer(Style("truecolor"), ROWS, COLS).full(m)))
    plain = lines(screen(tui.Renderer(Style(None), ROWS, COLS).full(m)))
    assert colored == plain


def test_body_lines_are_drawn_between_question_and_options():
    m = tui.ChoiceModel("T", "Enregistrer ?", [tui.Option("Oui"), tui.Option("Non")],
                        body=("Débit : 1,5", "Niveau de détail : bref"))
    text = lines(screen(tui.Renderer(Style(None), ROWS, COLS).full(m)))
    assert text[4:6] == ["Débit : 1,5", "Niveau de détail : bref"]
    assert text[7].startswith("› 1  Oui")


def test_tiny_terminal_still_shows_the_focused_option():
    m = make_model(focus=2)
    s = screen(tui.Renderer(Style(None), 6, 30).full(m), rows=6, cols=30)
    assert any("Qwen" in line and line.startswith("›") for line in lines(s))


# ------------------------------------------------------------ boucle d'écran (E/S injectées)


class FakeTerm:
    def __init__(self, keys, rows=ROWS, cols=COLS):
        self.keys = list(keys)
        self.out = []
        self.said = []
        self.size = (rows, cols)

    def read(self):
        if not self.keys:
            raise EOFError
        return self.keys.pop(0)

    def screen(self, style=None, language="fr"):
        return tui.Screen(self.read, self.out.append, lambda: self.size, style or Style(None),
                          self.said.append, language)


def test_choose_speaks_opening_then_each_focus_change_and_returns_the_choice():
    term = FakeTerm([b"\x1b[B", b"\x1b[B", b"\r", b"\x1b[A", b"\r"])
    choice = term.screen().choose(make_model())
    assert choice == 1
    assert term.said == [
        make_model().opening(),
        "Granite 4.2 1B, non recommandé : pas optimisé pour steph",
        "Qwen 3 8B, bloqué : hors de portée de cette machine",
        "Qwen 3 8B : hors de portée de cette machine. Choisissez une autre option.",
        "Granite 4.2 1B, non recommandé : pas optimisé pour steph",
    ]
    assert "\x1b[2J" in term.out[0] and all("\x1b[2J" not in o for o in term.out[1:])


def test_choose_returns_none_on_escape():
    term = FakeTerm([b"\x1b"])
    assert term.screen().choose(make_model()) is None


def test_redraw_repaints_the_current_screen_at_the_new_size():
    term = FakeTerm([b"\x1b[B"])
    scr = term.screen()
    with pytest.raises(EOFError):
        scr.choose(make_model())
    term.size = (30, 100)
    scr.redraw()
    s = screen(term.out[-1], rows=30, cols=100)
    assert lines(s)[-1].startswith("↑↓ choisir")
    assert lines(s)[5].startswith("› 2  Granite")


def test_capture_returns_escape_sequences_and_keeps_on_enter_or_letter():
    term = FakeTerm([b"\x1b[17~", b"\r", b"a", b"\x1b"])
    scr = term.screen()
    assert scr.capture("Configuration", "Appuyez sur la touche pour ouvrir le menu.", "") == "\x1b[17~"
    assert scr.capture("Configuration", "Q", "") == ""
    assert scr.capture("Configuration", "Q", "") == ""
    assert scr.capture("Configuration", "Q", "") == ""
    assert term.said[0] == "Appuyez sur la touche pour ouvrir le menu."


# ------------------------------------------------------------ session : écran restauré


def test_session_enters_alt_screen_and_always_restores_it(tmp_path):
    out = []
    with pytest.raises(RuntimeError):
        with tui.session(out.append):
            out.append("dessin")
            raise RuntimeError("boum")
    assert out[0] == tui.ENTER_SCREEN
    assert out[-1] == tui.LEAVE_SCREEN
    assert tui.LEAVE_SCREEN == "\x1b[0m\x1b[?25h\x1b[?1049l"


def test_raw_terminal_restores_the_terminal_attributes():
    import os
    import pty
    import termios

    master, slave = pty.openpty()
    try:
        before = termios.tcgetattr(slave)
        with pytest.raises(KeyboardInterrupt):
            with tui.raw_terminal(slave):
                assert termios.tcgetattr(slave)[3] & termios.ICANON == 0
                raise KeyboardInterrupt
        after = termios.tcgetattr(slave)
        # PENDIN : drapeau d'état que macOS pose au retour en mode canonique, pas un réglage
        after[3] &= ~getattr(termios, "PENDIN", 0)
        assert after == before
    finally:
        os.close(master)
        os.close(slave)


def test_key_reader_splits_a_burst_into_single_keys():
    import os
    import pty

    master, slave = pty.openpty()
    try:
        os.write(master, b"\x1b[B\x1b[B\r")
        read = tui.key_reader(slave)
        # pty encore en mode canonique : \r arrive traduit en \n, les deux valent Entrée
        assert [tui.decode_key(read()) for _ in range(3)] == ["down", "down", "enter"]
    finally:
        os.close(master)
        os.close(slave)


def test_capture_returns_none_on_ctrl_c():
    assert FakeTerm([b"\x03"]).screen().capture("Configuration", "Q", "") is None


def test_choose_prefixes_the_first_opening_with_an_intro():
    term = FakeTerm([b"\r"])
    term.screen().choose(make_model(), intro="Configuration de steph, plein écran.")
    assert term.said == ["Configuration de steph, plein écran. " + make_model().opening()]


def test_description_repeats_the_state_so_a_clipped_row_loses_nothing():
    m = make_model(focus=2)
    assert m.description() == "Bloqué : hors de portée de cette machine. 5 000 Mo."
    m.handle("up")
    assert m.description() == "Non recommandé : pas optimisé pour steph. 900 Mo."
    assert tui.ChoiceModel("T", "Q", [tui.Option("A", detail="Rien.")]).description() == "Rien."
