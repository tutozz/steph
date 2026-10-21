"""`steph setup` : écriture de config.toml à partir des réponses, sans rien perdre."""

import tomllib
from pathlib import Path

import pytest

from steph import setup
from steph.config import Config


# ------------------------------------------------------------ update_config_text


def test_new_file_gets_all_answers():
    text = setup.update_config_text("", {"speech_rate": 1.5, "verbosity": 2, "voice": "/v/a.onnx"})
    assert tomllib.loads(text) == {"speech_rate": 1.5, "verbosity": 2, "voice": "/v/a.onnx"}


def test_existing_keys_comments_and_tables_are_kept():
    existing = (
        "# ma config\n"
        "speech_rate = 1.1  # un peu lent\n"
        "llm_port = 9000\n"
        "\n"
        "[rules]\n"
        'vim = "mute"\n'
    )
    text = setup.update_config_text(existing, {"speech_rate": 1.4, "verbosity": 0})
    data = tomllib.loads(text)
    assert data == {"speech_rate": 1.4, "llm_port": 9000, "verbosity": 0, "rules": {"vim": "mute"}}
    assert "# ma config" in text
    # une clé ajoutée ne doit pas atterrir dans la table [rules]
    assert "verbosity" not in data["rules"]


def test_key_sequences_are_valid_toml_escapes():
    text = setup.update_config_text("", {"key_stop": "\x1b[19~", "key_ask": '\x1bO"'})
    assert tomllib.loads(text) == {"key_stop": "\x1b[19~", "key_ask": '\x1bO"'}


def test_same_prefix_key_is_not_replaced():
    text = setup.update_config_text("voice_extra = 1\n", {"voice": "x"})
    assert tomllib.loads(text) == {"voice_extra": 1, "voice": "x"}


# ------------------------------------------------------------ save_settings (menu F6)


def test_save_settings_creates_missing_file_and_parents(tmp_path):
    path = tmp_path / "sub" / "config.toml"
    setup.save_settings(path, {"speech_rate": 1.5})
    assert tomllib.loads(path.read_text()) == {"speech_rate": 1.5}


def test_save_settings_merges_into_existing_file_and_keeps_comments(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("# ma config\nverbosity = 2\n\n[rules]\nvim = \"mute\"\n")
    setup.save_settings(path, {"speech_rate": 1.75, "tts_enabled": False})
    text = path.read_text()
    data = tomllib.loads(text)
    assert data == {"verbosity": 2, "speech_rate": 1.75, "tts_enabled": False, "rules": {"vim": "mute"}}
    assert "# ma config" in text


# ------------------------------------------------------------ parsing des réponses


def test_parse_rate_bounds_and_default():
    assert setup.parse_rate("", 1.25) == 1.25
    assert setup.parse_rate("1,5", 1.25) == 1.5
    assert setup.parse_rate("9", 1.25) is None
    assert setup.parse_rate("vite", 1.25) is None


def test_parse_choice():
    assert setup.parse_choice("", 3, 2) == 2
    assert setup.parse_choice("3", 3, 1) == 3
    assert setup.parse_choice("4", 3, 1) is None
    assert setup.parse_choice("x", 3, 1) is None


# ------------------------------------------------------------ déroulé (I/O injectée)


def _run(tmp_path, answers, existing=None, voices=("fr_FR-siwis-medium", "fr_FR-tom-medium"),
         models=None, voices_catalog=None, download=None, cfg=None):
    cfg_path = tmp_path / "config.toml"
    if existing is not None:
        cfg_path.write_text(existing)
    vdir = tmp_path / "voices"
    vdir.mkdir()
    for v in voices:
        (vdir / f"{v}.onnx").write_bytes(b"")
    said = []
    it = iter(answers)
    code = setup.run_setup(cfg or Config(), cfg_path, ask=lambda prompt: next(it), say=said.append, voices_dir=vdir,
                           capture_key=lambda: "\x1bOP", models=models, voices=voices_catalog, download=download)
    return code, cfg_path, said


def test_full_run_writes_config(tmp_path):
    # voix 2, débit 1,5, verbosité 2, touches par défaut
    code, path, said = _run(tmp_path, ["2", "1,5", "2", "1"])
    assert code == 0
    data = tomllib.loads(path.read_text())
    assert data["voice"].endswith("fr_FR-tom-medium.onnx")
    assert data["speech_rate"] == 1.5
    assert data["verbosity"] == 2
    assert "key_stop" not in data  # touches par défaut : rien à écrire
    assert said  # chaque question est aussi dite


def test_invalid_answer_is_asked_again(tmp_path):
    code, path, _ = _run(tmp_path, ["", "vite", "1", "", ""])
    data = tomllib.loads(path.read_text())
    assert data["speech_rate"] == 1.0


def test_custom_keys_are_captured(tmp_path):
    code, path, _ = _run(tmp_path, ["", "", "", "2"])
    data = tomllib.loads(path.read_text())
    for k in ("key_ask", "key_stop", "key_repeat", "key_details"):
        assert data[k] == "\x1bOP"


def test_existing_config_is_not_touched_without_confirmation(tmp_path):
    code, path, _ = _run(tmp_path, [""], existing="llm_port = 9000\n")
    assert code == 0  # « non » est un choix, pas une erreur
    assert path.read_text() == "llm_port = 9000\n"


def test_existing_config_keeps_other_keys_when_confirmed(tmp_path):
    code, path, _ = _run(tmp_path, ["o", "", "", "", ""], existing="llm_port = 9000\n")
    assert code == 0
    assert tomllib.loads(path.read_text())["llm_port"] == 9000


# ------------------------------------------------------------ premier lancement


def test_first_run_offer_only_once(tmp_path):
    cfg_path, marker = tmp_path / "config.toml", tmp_path / "offered"
    asked = []
    ask = lambda p: asked.append(p) or "n"  # noqa: E731
    assert setup.should_run_first_setup(cfg_path, marker, ask=ask, interactive=True) is False
    assert marker.exists()
    assert setup.should_run_first_setup(cfg_path, marker, ask=ask, interactive=True) is False
    assert len(asked) == 1


def test_first_run_offer_accepted(tmp_path):
    assert setup.should_run_first_setup(tmp_path / "c.toml", tmp_path / "m", ask=lambda p: "o", interactive=True)


def test_no_offer_when_config_exists_or_not_interactive(tmp_path):
    cfg_path = tmp_path / "config.toml"
    boom = lambda p: (_ for _ in ()).throw(AssertionError("ne doit pas demander"))  # noqa: E731
    assert setup.should_run_first_setup(cfg_path, tmp_path / "m", ask=boom, interactive=False) is False
    cfg_path.write_text("")
    assert setup.should_run_first_setup(cfg_path, tmp_path / "m2", ask=boom, interactive=True) is False


def test_launch_greeting_is_short_and_does_not_read_the_full_key_list(monkeypatch, tmp_path):
    """`steph` ne doit plus lire toute la liste des touches à l'ouverture (HELP_KEYS
    reste utilisé pour le badge de fenêtre et l'entrée "Aide des touches" du menu)."""
    import types

    from steph import cli

    said = []

    class FakeSpeaker:
        window = None

        def __init__(self, cfg, **kw):
            pass

        def say(self, text, **kw):
            said.append(text)

        def close(self):
            pass

    class FakeLLM:
        def __init__(self, *a, **k):
            pass

        def ensure_server(self, *a, **k):
            return True

        def stop_server(self):
            pass

        def healthy(self):
            return False

    class FakeNarrator:
        def __init__(self, *a, **k):
            self.llm_ready = False

        def start(self):
            pass

        def warm_system_prompts(self):
            pass

    class FakeServer:
        def __init__(self, *a, **k):
            pass

        def close(self):
            pass

    class FakeProxy:
        def __init__(self, *a, **k):
            pass

        def run(self):
            return 0

    monkeypatch.delenv("STEPH_ACTIVE", raising=False)
    monkeypatch.setattr(cli, "load_config", lambda **kw: Config())
    monkeypatch.setattr(setup, "first_run", lambda: None)
    monkeypatch.setattr("steph.voice_client.VoiceClient", FakeSpeaker)
    monkeypatch.setattr("steph.llm.LLM", FakeLLM)
    monkeypatch.setattr("steph.narrator.Narrator", FakeNarrator)
    monkeypatch.setattr("steph.server.ControlServer", FakeServer)
    monkeypatch.setattr("steph.proxy.PtyProxy", FakeProxy)

    assert cli.cmd_run(types.SimpleNamespace(no_voice=False)) == 0
    assert said, "aucune annonce de lancement"
    greeting = said[0]
    assert greeting == f"Steph. {cli.MENU_KEY} pour les paramètres."
    assert "questions" not in greeting  # échouerait si HELP_KEYS était encore lu en entier
    assert "F10" not in greeting


def test_cli_dispatches_setup(monkeypatch):
    from steph import cli
    monkeypatch.setattr(setup, "main", lambda: 7)
    assert cli.main(["setup"]) == 7


def test_run_offers_setup_before_starting(monkeypatch):
    from steph import cli
    calls = []
    monkeypatch.delenv("STEPH_ACTIVE", raising=False)
    monkeypatch.setattr(setup, "first_run", lambda: calls.append("offer"))
    monkeypatch.setattr(cli, "load_config", lambda **kw: (_ for _ in ()).throw(SystemExit(calls.append("run"))))
    try:
        cli.main([])
    except SystemExit:
        pass
    assert calls == ["offer", "run"]


# ------------------------------------------------------------ B8b : terminal, fin de fichier


def test_end_of_input_is_never_an_answer(tmp_path):
    """Fin de fichier (stdin fermé, `curl | sh`) : rien n'est écrit, jamais les défauts."""
    cfg_path = tmp_path / "config.toml"
    said = []

    def ask(prompt):
        raise EOFError

    code = setup.run_setup(Config(), cfg_path, ask=ask, say=said.append, voices_dir=tmp_path,
                           capture_key=lambda: "")
    assert code != 0
    assert not cfg_path.exists()
    assert any("rien" in s for s in said)


def test_tty_prompter_reads_answers_and_raises_at_end_of_file():
    import io

    out = io.StringIO()
    prompter = setup.TtyPrompter(io.StringIO("2\n"), out)
    assert prompter.ask("> ") == "2"
    assert out.getvalue() == "> "
    try:
        prompter.ask("> ")
    except EOFError:
        pass
    else:
        raise AssertionError("la fin de fichier doit lever EOFError, pas valoir Entrée")


def test_main_without_terminal_writes_nothing_and_says_so(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(setup, "open_tty", lambda: None)
    monkeypatch.setattr(setup, "load_config", lambda: Config(tts_enabled=False))
    cfg_path = tmp_path / "config.toml"
    assert setup.main(cfg_path) != 0
    assert not cfg_path.exists()
    assert "steph setup" in capsys.readouterr().out


def test_real_setup_without_controlling_terminal_writes_no_config(tmp_path):
    """Critère B8a : `steph setup < /dev/null` sans terminal ne crée pas config.toml."""
    import os
    import subprocess
    import sys

    env = dict(os.environ, XDG_CONFIG_HOME=str(tmp_path / "cfg"), XDG_DATA_HOME=str(tmp_path / "data"),
               STEPH_TTS_ENABLED="0")
    r = subprocess.run([sys.executable, "-m", "steph.cli", "setup"], stdin=subprocess.DEVNULL,
                       capture_output=True, text=True, env=env, timeout=30, start_new_session=True)
    assert r.returncode != 0
    assert not (tmp_path / "cfg" / "steph" / "config.toml").exists()
    assert "terminal" in r.stdout


def test_declining_existing_config_is_not_an_error(tmp_path):
    code, path, _said = _run(tmp_path, ["non"], existing="llm_port = 9000\n")
    assert code == 0
    assert path.read_text() == "llm_port = 9000\n"


def test_invalid_answer_recalls_valid_choices(tmp_path):
    _, _, said = _run(tmp_path, ["9", "", "", "", ""])
    retry = next(s for s in said if "non comprise" in s)
    assert "1" in retry and "2" in retry


# ------------------------------------------------------------ B8b : touches F6 et relecture


def test_keys_question_names_f6_and_review_keys(tmp_path):
    _, _, said = _run(tmp_path, ["", "", "", ""])
    keys = next(s for s in said if s.startswith("Touches"))
    assert "F6" in keys and "Maj F5" in keys


def test_custom_keys_include_menu_and_review(tmp_path):
    _code, path, _ = _run(tmp_path, ["", "", "", "2"])
    data = tomllib.loads(path.read_text())
    for k in ("key_menu", "key_line_first", "key_line_prev", "key_line_next", "key_line_last"):
        assert data[k] == "\x1bOP"


# ------------------------------------------------------------ B8b : débit aligné sur le menu


def test_rate_bounds_match_menu():
    from steph import menu

    assert (setup.RATE_MIN, setup.RATE_MAX) == (menu.RATE_MIN, menu.RATE_MAX)
    assert setup.parse_rate("3", 1.25) == 3.0


def test_rate_question_states_the_real_bounds(tmp_path):
    _, _, said = _run(tmp_path, ["", "", "", ""])
    rate = next(s for s in said if s.startswith("Débit"))
    assert "0,5 à 3" in rate


# ------------------------------------------------------------ B8b : anglais (language = "en")


def test_setup_speaks_english_when_language_is_en(tmp_path):
    cfg_path = tmp_path / "config.toml"
    vdir = tmp_path / "voices"
    vdir.mkdir()
    (vdir / "en_US-amy-medium.onnx").write_bytes(b"")
    said = []
    it = iter(["", "", "", ""])
    code = setup.run_setup(Config(language="en"), cfg_path, ask=lambda p: next(it), say=said.append,
                           voices_dir=vdir, capture_key=lambda: "")
    assert code == 0
    text = " ".join(said)
    assert "Speech rate" in text and "Keys" in text and "saved" in text
    assert "Débit" not in text and "Touches" not in text


def test_first_run_question_in_english(tmp_path):
    asked = []
    setup.should_run_first_setup(tmp_path / "c.toml", tmp_path / "m", ask=lambda p: asked.append(p) or "n",
                                 interactive=True, language="en")
    assert asked[0].startswith("First")


# ------------------------------------------------------------ B8b : modèle selon le matériel (point d'accroche B4)


def _models(tmp_path):
    small, big = tmp_path / "small.gguf", tmp_path / "big.gguf"
    small.write_bytes(b"x")  # déjà présent : la sélection ne doit rien télécharger
    return [
        setup.ModelChoice(label="Petit", path=str(small), size_mb=533, profile="generic",
                          recommended=True, out_of_scope=False),
        setup.ModelChoice(label="Grand", path=str(big), size_mb=3300, profile="generic",
                          recommended=False, out_of_scope=True),
    ]


def test_model_question_defaults_to_recommended_and_marks_out_of_scope(tmp_path):
    cfg_path = tmp_path / "config.toml"
    said = []
    it = iter(["", "", "", "", ""])
    setup.run_setup(Config(), cfg_path, ask=lambda p: next(it), say=said.append, voices_dir=tmp_path / "none",
                    capture_key=lambda: "", models=_models(tmp_path))
    question = next(s for s in said if s.startswith("Modèle"))
    assert "recommandé" in question and "hors de portée" in question
    data = tomllib.loads(cfg_path.read_text())
    assert data["model"].endswith("small.gguf")
    assert data["llm_profile"] == "generic"


def test_no_model_question_without_catalog(tmp_path):
    _, _, said = _run(tmp_path, ["", "", "", ""])
    assert not any(s.startswith("Modèle") for s in said)


# ------------------------------------------------------------ B9 : Gemma non recommandé


def _b9_models(tmp_path):
    steph_speak, gemma = tmp_path / "steph-speak.gguf", tmp_path / "gemma.gguf"
    steph_speak.write_bytes(b"x")
    gemma.write_bytes(b"x")
    return [
        setup.ModelChoice(label="steph-speak", path=str(steph_speak), size_mb=223, profile="finetuned",
                          recommended=True, out_of_scope=False),
        setup.ModelChoice(label="Gemma 4 E2B", path=str(gemma), size_mb=3300, profile="generic",
                          recommended=False, out_of_scope=False, not_recommended=True),
    ]


def test_model_question_marks_gemma_as_not_recommended(tmp_path):
    cfg_path = tmp_path / "config.toml"
    said = []
    it = iter(["1", "", "", "", ""])
    setup.run_setup(Config(), cfg_path, ask=lambda p: next(it), say=said.append, voices_dir=tmp_path / "none",
                    capture_key=lambda: "", models=_b9_models(tmp_path))
    question = next(s for s in said if s.startswith("Modèle"))
    assert "non recommandé : pas optimisé pour steph" in question


def test_model_question_marks_gemma_as_not_recommended_in_english(tmp_path):
    cfg_path = tmp_path / "config.toml"
    said = []
    it = iter(["1", "", "", "", ""])
    setup.run_setup(Config(language="en"), cfg_path, ask=lambda p: next(it), say=said.append,
                    voices_dir=tmp_path / "none", capture_key=lambda: "", models=_b9_models(tmp_path))
    question = next(s for s in said if s.startswith("Language model"))
    assert "not recommended: not optimized for steph" in question


# ------------------------------------------------------------ B6 : catalogue, blocage, téléchargement


def _catalog_models(tmp_path, recommended_available=True, recommended_out_of_scope=False):
    missing = tmp_path / "recommended.gguf"
    other = tmp_path / "other.gguf"
    other.write_bytes(b"x")  # déjà présent : toujours sélectionnable
    return [
        setup.ModelChoice(label="Recommandé", path=str(missing), size_mb=223, profile="finetuned",
                          recommended=True, out_of_scope=recommended_out_of_scope,
                          available=recommended_available, source="org/recommended-GGUF"),
        setup.ModelChoice(label="Autre", path=str(other), size_mb=3300, profile="generic",
                          recommended=False, out_of_scope=False, available=True, source="org/other-GGUF"),
    ]


def test_out_of_scope_model_is_blocked_then_a_valid_choice_succeeds(tmp_path):
    models = _catalog_models(tmp_path, recommended_out_of_scope=True)
    code, path, said = _run(tmp_path, ["1", "2", "", "", "", ""], models=models, download=lambda c: True)
    assert code == 0
    blocked = next(s for s in said if s.startswith("Recommandé"))
    assert "hors de portée" in blocked
    data = tomllib.loads(path.read_text())
    assert data["model"].endswith("other.gguf")


def test_unpublished_model_is_blocked_then_a_valid_choice_succeeds(tmp_path):
    models = _catalog_models(tmp_path, recommended_available=False)
    code, path, said = _run(tmp_path, ["1", "2", "", "", "", ""], models=models, download=lambda c: True)
    assert code == 0
    blocked = next(s for s in said if s.startswith("Recommandé"))
    assert "pas encore publié" in blocked
    data = tomllib.loads(path.read_text())
    assert data["model"].endswith("other.gguf")


def test_already_present_model_is_always_selectable_even_if_out_of_scope(tmp_path):
    """Un modèle déjà sur le disque ne se bloque pas : il tourne déjà, quoi qu'en dise le catalogue."""
    models = _catalog_models(tmp_path, recommended_out_of_scope=False)
    models[1].out_of_scope = True  # "Autre" est présent sur le disque malgré tout
    calls = []
    code, path, _said = _run(tmp_path, ["2", "", "", "", ""], models=models, download=lambda c: calls.append(c) or True)
    assert code == 0
    data = tomllib.loads(path.read_text())
    assert data["model"].endswith("other.gguf")
    assert calls == []  # déjà présent : aucun téléchargement déclenché


def test_selecting_a_missing_model_triggers_download(tmp_path):
    models = _catalog_models(tmp_path)
    calls = []

    def fake_download(choice):
        calls.append(choice.label)
        return True

    code, path, _said = _run(tmp_path, ["", "", "", "", ""], models=models, download=fake_download)
    assert code == 0
    assert calls == ["Recommandé"]
    data = tomllib.loads(path.read_text())
    assert data["model"].endswith("recommended.gguf")
    assert data["llm_profile"] == "finetuned"


def test_failed_download_leaves_model_unchanged(tmp_path):
    models = _catalog_models(tmp_path)
    code, path, said = _run(tmp_path, ["", "", "", "", ""], models=models, download=lambda c: False)
    assert code == 0
    data = tomllib.loads(path.read_text())
    assert "model" not in data and "llm_profile" not in data
    assert any("impossible" in s for s in said)


def test_default_skips_a_blocked_recommendation_and_falls_back(tmp_path):
    """Le recommandé n'est pas téléchargeable : Entrée doit proposer l'autre choix, pas boucler."""
    models = _catalog_models(tmp_path, recommended_available=False)
    code, path, said = _run(tmp_path, ["", "", "", "", ""], models=models, download=lambda c: True)
    assert code == 0
    question = next(s for s in said if s.startswith("Modèle"))
    assert not any(s.startswith("Recommandé") for s in said)  # jamais proposé, donc jamais bloqué
    assert "2 Autre" in question
    data = tomllib.loads(path.read_text())
    assert data["model"].endswith("other.gguf")


def test_model_question_skipped_when_nothing_is_selectable(tmp_path):
    missing = tmp_path / "m.gguf"
    models = [setup.ModelChoice(label="Bientôt", path=str(missing), size_mb=200, profile="finetuned",
                                recommended=True, out_of_scope=False, available=False, source="org/x")]
    _, _, said = _run(tmp_path, ["", "", "", ""], models=models)
    assert not any(s.startswith("Bientôt") or s.startswith("Modèle") for s in said)


# ------------------------------------------------------------ B6 : voix du catalogue


def _catalog_voices(tmp_path):
    missing = tmp_path / "voices" / "fr_FR-new-medium.onnx"
    return [
        setup.ModelChoice(label="Voix recommandée", path=str(missing), size_mb=63, profile="generic",
                          recommended=True, out_of_scope=False, available=True, source="rhasspy/piper-voices"),
    ]


def test_voice_catalog_question_downloads_the_choice(tmp_path):
    voices_catalog = _catalog_voices(tmp_path)
    calls = []

    def fake_download(choice):
        calls.append(choice.label)
        Path(choice.path).parent.mkdir(parents=True, exist_ok=True)
        Path(choice.path).write_bytes(b"x")
        return True

    code, path, said = _run(tmp_path, ["", "", "", ""], voices_catalog=voices_catalog, download=fake_download)
    assert code == 0
    assert calls == ["Voix recommandée"]
    question = next(s for s in said if s.startswith("Voix"))
    assert "recommandé" in question
    data = tomllib.loads(path.read_text())
    assert data["voice"].endswith("fr_FR-new-medium.onnx")


def test_voice_local_fallback_still_works_when_catalog_has_no_voices(tmp_path):
    """voices_catalog=None : le comportement local (glob des .onnx déjà présents) ne doit pas changer."""
    code, path, _said = _run(tmp_path, ["2", "", "", ""])
    assert code == 0
    data = tomllib.loads(path.read_text())
    assert data["voice"].endswith("fr_FR-tom-medium.onnx")


# l'enfant fait execve aussitôt : l'avertissement forkpty en processus multi-fil ne le concerne pas
@pytest.mark.filterwarnings("ignore:This process .* is multi-threaded:DeprecationWarning")
def test_real_setup_reads_the_terminal_even_when_stdin_is_a_pipe(tmp_path):
    """Critère B8a : sous `curl | sh` (stdin = tuyau), les questions passent par le terminal."""
    import os
    import pty
    import select
    import sys
    import time

    env = dict(os.environ, XDG_CONFIG_HOME=str(tmp_path / "cfg"), XDG_DATA_HOME=str(tmp_path / "data"),
               STEPH_TTS_ENABLED="0", TERM="dumb",
               # isolé du vrai catalogue B4 : ce test porte sur le tuyau/pty (B8a), pas sur B6,
               # et un vrai catalogue proposerait un téléchargement réel (réseau, plusieurs Go)
               STEPH_CATALOG=str(tmp_path / "no-catalog.json"))
    pid, fd = pty.fork()
    if pid == 0:  # enfant : le pty est son terminal de contrôle, stdin un tuyau plein de « 9 »
        os.execve("/bin/sh", ["sh", "-c", f"yes 9 | {sys.executable} -m steph.cli setup"], env)
    out = b""

    def wait_prompts(count, seconds=15):
        nonlocal out
        end = time.time() + seconds
        while time.time() < end and out.count(b"> ") < count:
            if select.select([fd], [], [], 0.05)[0]:
                try:
                    out += os.read(fd, 4096)
                except OSError:
                    return

    for i, answer in enumerate(["2", "0", ""], 1):  # débit 2, verbosité 0, touches par défaut
        wait_prompts(i)
        if out.count(b"> ") < i:
            break
        os.write(fd, (answer + "\r").encode())
    wait_prompts(99, seconds=3)
    os.waitpid(pid, 0)
    text = (tmp_path / "cfg" / "steph" / "config.toml").read_text()
    assert "speech_rate = 2.0" in text and "verbosity = 0" in text, out.decode(errors="replace")


# ------------------------------------------------------------ M5 : charte dans le terminal


def test_model_listing_colors_recommended_lemon_and_blocked_gray_without_changing_text(tmp_path):
    from steph.term_style import Style
    from steph.textproc import strip_ansi

    models = _catalog_models(tmp_path, recommended_available=False) + _b9_models(tmp_path)
    plain = setup._model_listing(models, "fr")
    styled = setup._model_listing(models, "fr", Style("truecolor"))
    assert strip_ansi(styled) == plain
    assert "\x1b[38;2;11;11;11;48;2;226;255;59mrecommandé\x1b[0m" in styled
    assert "\x1b[38;2;138;138;133;48;2;11;11;11mpas encore publié\x1b[0m" in styled
    assert "\x1b[38;2;138;138;133;48;2;11;11;11mnon recommandé : pas optimisé pour steph\x1b[0m" in styled


def test_saved_message_is_lemon_when_styled(tmp_path):
    from steph.term_style import Style

    cfg_path = tmp_path / "config.toml"
    said = []
    it = iter(["", "", ""])
    setup.run_setup(Config(), cfg_path, ask=lambda p: next(it), say=said.append, voices_dir=tmp_path / "none",
                    capture_key=lambda: "", style=Style("truecolor"))
    assert said[-1].startswith("\x1b[38;2;11;11;11;48;2;226;255;59mConfiguration enregistrée")


def test_voice_prints_colors_but_speaks_plain_text(capsys):
    class FakeSpeaker:
        def __init__(self):
            self.spoken = []

        def say(self, text):
            self.spoken.append(text)

    voice = setup._Voice.__new__(setup._Voice)
    voice.speaker = FakeSpeaker()
    voice.say("\x1b[38;2;11;11;11;48;2;226;255;59mrecommandé\x1b[0m")
    assert voice.speaker.spoken == ["recommandé"]
    assert "\x1b[38;2;11;11;11;48;2;226;255;59m" in capsys.readouterr().out


# ------------------------------------------------------------ B10 : choix selon la vitesse mesurée


def _speed_models(tmp_path, small_present=True):
    small = tmp_path / "small.gguf"
    if small_present:
        small.write_bytes(b"x")
    return [
        setup.ModelChoice(label="steph-speak petit", path=str(small), size_mb=223, profile="finetuned",
                          recommended=True, out_of_scope=False, id="llm/small", role="small",
                          prompt_tokens_per_sec=200.0, summary_prompt_tokens_p90=270),
        setup.ModelChoice(label="steph-speak base", path=str(tmp_path / "base.gguf"), size_mb=2432,
                          profile="generic", recommended=False, out_of_scope=False, id="llm/base", role="base",
                          prompt_tokens_per_sec=28.0, summary_prompt_tokens_p90=766, source="org/base"),
    ]


def test_chosen_model_writes_its_prompt_speed(tmp_path):
    code, path, _ = _run(tmp_path, ["1", "", "", "", ""], models=_speed_models(tmp_path))
    data = tomllib.loads(path.read_text())
    assert data["model"].endswith("small.gguf")
    assert data["llm_prompt_tokens_per_sec"] == 200.0


def test_model_without_known_speed_writes_no_prompt_speed(tmp_path):
    code, path, _ = _run(tmp_path, ["", "", "", "", ""], models=_models(tmp_path))
    assert "llm_prompt_tokens_per_sec" not in tomllib.loads(path.read_text())


def test_speed_verdict_is_said_right_before_the_model_question(tmp_path):
    cfg_path = tmp_path / "config.toml"
    said = []
    it = iter(["", "", "", "", ""])
    setup.run_setup(Config(), cfg_path, ask=lambda p: next(it), say=said.append, voices_dir=tmp_path / "none",
                    capture_key=lambda: "", models=_speed_models(tmp_path), model_intro="Verdict de vitesse.")
    at = said.index("Verdict de vitesse.")
    assert said[at + 1].startswith("Modèle")


def test_model_listing_gives_the_first_summary_estimate(tmp_path):
    cfg_path = tmp_path / "config.toml"
    said = []
    it = iter(["", "", "", "", ""])
    setup.run_setup(Config(), cfg_path, ask=lambda p: next(it), say=said.append, voices_dir=tmp_path / "none",
                    capture_key=lambda: "", models=_speed_models(tmp_path))
    question = next(s for s in said if s.startswith("Modèle"))
    assert "premier résumé en 1,4 seconde environ" in question  # 270 / 200
    assert "premier résumé en 27 secondes environ" in question  # 766 / 28


def test_setup_llm_measures_with_the_model_on_disk_and_recommends_by_speed(tmp_path, monkeypatch):
    from steph import catalog, speed

    measured = []
    monkeypatch.setattr(setup, "_setup_models", lambda cfg: _speed_models(tmp_path))
    monkeypatch.setattr(setup, "detect_machine", lambda: catalog.Machine(4, 8, 0))
    monkeypatch.setattr(setup, "load_config", lambda apply_profile=False: Config())
    monkeypatch.setattr(speed, "measure_prompt_speed", lambda cfg, path: measured.append(path) or 2000.0)
    said = []
    models, note = setup._setup_llm(Config(), said.append)
    assert measured == [str(tmp_path / "small.gguf")]
    assert said == ["Mesure de la vitesse de cette machine, quelques secondes."]
    small, base = models
    assert base.recommended and not small.recommended
    assert base.prompt_tokens_per_sec == 280.0
    assert note[0].startswith("Vitesse mesurée : premier résumé estimé à 2,7 secondes")


def test_setup_llm_estimates_without_measuring_when_no_model_is_on_disk(tmp_path, monkeypatch):
    from steph import catalog, speed

    monkeypatch.setattr(setup, "_setup_models", lambda cfg: _speed_models(tmp_path, small_present=False))
    monkeypatch.setattr(setup, "detect_machine", lambda: catalog.Machine(2, 16, 0))
    monkeypatch.setattr(speed, "measure_prompt_speed", lambda *a: pytest.fail("aucun modèle à mesurer"))
    said = []
    models, note = setup._setup_llm(Config(), said.append)
    assert said == []
    assert models[0].recommended and not models[1].recommended
    assert note[:2] == ["Vitesse non mesurée, aucun modèle installé.", "Processeur seul : petit modèle recommandé."]


def test_setup_llm_without_catalog_does_nothing(monkeypatch):
    monkeypatch.setattr(setup, "_setup_models", lambda cfg: [])
    assert setup._setup_llm(Config(), lambda s: pytest.fail("rien à dire")) == ([], [])


def test_main_line_mode_passes_the_speed_verdict(tmp_path, monkeypatch):
    import io

    captured = {}
    monkeypatch.setattr(setup, "_Voice", lambda cfg: type("V", (), {"say": lambda s, x: None,
                                                                    "close": lambda s: None})())
    monkeypatch.setattr(setup, "load_config", lambda: Config(tts_enabled=False))
    monkeypatch.setattr(setup, "open_tty", lambda: (io.StringIO(""), io.StringIO()))
    monkeypatch.setattr(setup, "_tty_mode", lambda cfg, i, o: ("line", "user", None))
    monkeypatch.setattr(setup, "_setup_llm", lambda cfg, say: (["m"], ["Vitesse.", "Verdict."]))
    monkeypatch.setattr(setup, "_setup_voices", lambda cfg: [])
    monkeypatch.setattr(setup, "run_setup", lambda *a, **k: captured.update(k) or 0)
    assert setup.main(tmp_path / "config.toml") == 0
    assert captured["models"] == ["m"] and captured["model_intro"] == "Vitesse. Verdict."


def test_first_setup_defaults_to_the_speed_pick_not_the_built_in_model(tmp_path):
    """Sans config.toml, `model` n'est que la valeur par défaut (Gemma brut d'install.sh) :
    Entrée doit prendre le modèle recommandé par la vitesse, pas garder ce défaut."""
    models = _b9_models(tmp_path)  # steph-speak recommandé, Gemma non recommandé, tous deux présents
    code, path, _ = _run(tmp_path, ["", "", "", "", ""], models=models, cfg=Config(model=models[1].path))
    assert tomllib.loads(path.read_text())["model"] == models[0].path


def test_rerun_keeps_the_model_chosen_in_config_toml(tmp_path):
    models = _b9_models(tmp_path)
    existing = f'model = "{models[1].path}"\n'
    code, path, _ = _run(tmp_path, ["o", "", "", "", "", ""], existing=existing, models=models,
                         cfg=Config(model=models[1].path))
    assert tomllib.loads(path.read_text())["model"] == models[1].path
