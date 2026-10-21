"""B8b : erreurs de démarrage actionnables, `steph say` sans son, `steph uninstall`."""

import sys
import types

from steph import cli, setup
from steph.config import Config

# ------------------------------------------------------------ erreurs distinctes au démarrage du modèle


def _cfg(tmp_path, model=True, server=True):
    cfg = Config()
    cfg.model = str(tmp_path / "m.gguf")
    if model:
        (tmp_path / "m.gguf").write_bytes(b"x")
    cfg.llama_server = sys.executable if server else str(tmp_path / "absent" / "llama-server")
    return cfg


def test_preflight_missing_model_names_the_remedy(tmp_path):
    msg = cli.llm_preflight(_cfg(tmp_path, model=False))
    assert msg.startswith("Modèle introuvable") and "steph update" in msg


def test_preflight_missing_server_is_a_different_message(tmp_path):
    msg = cli.llm_preflight(_cfg(tmp_path, server=False))
    assert msg.startswith("llama.cpp introuvable") and "steph update" in msg


def test_preflight_bare_command_name_is_looked_up_in_path(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    cfg.llama_server = "llama-server-absent-xyz"
    assert cli.llm_preflight(cfg).startswith("llama.cpp introuvable")


def test_preflight_ok(tmp_path):
    assert cli.llm_preflight(_cfg(tmp_path)) is None


def test_preflight_in_english(tmp_path):
    cfg = _cfg(tmp_path, model=False)
    cfg.language = "en"
    assert cli.llm_preflight(cfg).startswith("Model not found")


def test_run_says_model_missing_without_starting_the_server(tmp_path, monkeypatch):
    said, started = [], []

    class FakeSpeaker:
        window = None

        def __init__(self, cfg, **kw):
            pass

        def say(self, text, **kw):
            said.append(text)

        def close(self):
            pass

    class FakeLLM:
        logfile = "/tmp/llama.log"

        def __init__(self, *a, **k):
            pass

        def ensure_server(self, *a, **k):
            started.append(1)
            return True

        def stop_server(self):
            pass

    class Dummy:
        llm_ready = None

        def __init__(self, *a, **k):
            pass

        def start(self):
            pass

        def close(self):
            pass

        def warm_system_prompts(self):
            pass

        def run(self):
            import time
            time.sleep(0.2)  # laisse le fil de démarrage du modèle parler
            return 0

    cfg = _cfg(tmp_path, model=False)
    monkeypatch.delenv("STEPH_ACTIVE", raising=False)
    monkeypatch.setattr(cli, "load_config", lambda **kw: cfg)
    monkeypatch.setattr(cli, "RUNTIME_DIR", tmp_path / "run")
    monkeypatch.setattr(setup, "first_run", lambda: None)
    monkeypatch.setattr("steph.voice_client.VoiceClient", FakeSpeaker)
    monkeypatch.setattr("steph.llm.LLM", FakeLLM)
    monkeypatch.setattr("steph.narrator.Narrator", Dummy)
    monkeypatch.setattr("steph.server.ControlServer", Dummy)
    monkeypatch.setattr("steph.proxy.PtyProxy", Dummy)
    assert cli.cmd_run(types.SimpleNamespace(no_voice=False)) == 0
    assert any(s.startswith("Modèle introuvable") for s in said)
    assert not started


# ------------------------------------------------------------ steph say : dire quand aucun son n'est possible


def test_say_without_any_audio_player_says_so_in_text(tmp_path, monkeypatch, capsys):
    from steph import audio

    monkeypatch.setattr(audio.shutil, "which", lambda name: None)
    cfg = Config()
    cfg.voice = str(tmp_path / "absent.onnx")
    monkeypatch.setattr(cli, "load_config", lambda **kw: cfg)
    assert cli.main(["say", "bonjour"]) == 1
    assert "Aucun son possible" in capsys.readouterr().err


def test_say_with_a_player_succeeds(tmp_path, monkeypatch, capsys):
    from steph import audio

    monkeypatch.setattr(audio.shutil, "which", lambda name: "/usr/bin/" + name)
    monkeypatch.setattr(audio, "popen_quiet", lambda cmd, stdin=None: types.SimpleNamespace(
        wait=lambda: 0, poll=lambda: 0))
    cfg = Config()
    cfg.voice = str(tmp_path / "absent.onnx")
    monkeypatch.setattr(cli, "load_config", lambda **kw: cfg)
    assert cli.main(["say", "bonjour"]) == 0
    assert "Aucun son" not in capsys.readouterr().err


# ------------------------------------------------------------ steph uninstall


def _home(tmp_path):
    data, conf, run = tmp_path / "data" / "steph", tmp_path / "config" / "steph", tmp_path / "run" / "steph"
    (data / "models").mkdir(parents=True)
    (data / "models" / "m.gguf").write_bytes(b"x" * 2048)
    (data / "voices").mkdir()
    (data / "src").mkdir()
    conf.mkdir(parents=True)
    (conf / "config.toml").write_text("")
    run.mkdir(parents=True)
    return data, conf, run


def _uninstall(tmp_path, answer="o", keep_models=False, yes=False, interactive=True, prefix="/x/uv/tools/steph"):
    from steph import uninstall

    data, conf, run = _home(tmp_path)
    calls, out = [], []
    ask = (lambda p: answer) if interactive else None
    code = uninstall.run_uninstall(data, conf, run, keep_models=keep_models, yes=yes, ask=ask, out=out.append,
                                   run=lambda cmd, **kw: calls.append(cmd) or types.SimpleNamespace(returncode=0),
                                   uv="/bin/uv", prefix=prefix)
    return code, (data, conf, run), calls, out


def test_uninstall_lists_then_removes_everything(tmp_path):
    code, (data, conf, run), calls, out = _uninstall(tmp_path)
    assert code == 0
    assert not data.exists() and not conf.exists() and not run.exists()
    assert ["/bin/uv", "tool", "uninstall", "steph"] in calls
    assert str(data) in "\n".join(out)


def test_uninstall_declined_removes_nothing(tmp_path):
    code, (data, conf, _run_dir), calls, _out = _uninstall(tmp_path, answer="")
    assert code == 0
    assert data.exists() and conf.exists()
    assert calls == []


def test_uninstall_keep_models(tmp_path):
    _code, (data, conf, _run_dir), _calls, _out = _uninstall(tmp_path, keep_models=True)
    assert (data / "models" / "m.gguf").exists()
    assert not (data / "voices").exists() and not (data / "src").exists() and not conf.exists()


def test_uninstall_without_terminal_needs_yes(tmp_path):
    code, (data, *_), calls, _out = _uninstall(tmp_path, interactive=False)
    assert code != 0 and data.exists() and calls == []
    code, (data, *_), calls, out = _uninstall(tmp_path / "b", interactive=False, yes=True)
    assert code == 0 and not data.exists()


def test_uninstall_under_homebrew_points_to_brew(tmp_path):
    _code, _, calls, out = _uninstall(tmp_path, prefix="/opt/homebrew/Cellar/steph/0.1.0/libexec")
    assert calls == []
    assert any("brew uninstall steph" in line for line in out)


def test_cli_dispatches_uninstall(monkeypatch):
    from steph import uninstall

    seen = []
    monkeypatch.setattr(uninstall, "main", lambda keep_models, yes: seen.append((keep_models, yes)) or 0)
    assert cli.main(["uninstall", "--keep-models", "--yes"]) == 0
    assert seen == [(True, True)]


def test_uninstall_main_never_removes_the_whole_xdg_runtime_dir(tmp_path, monkeypatch):
    from steph import config, uninstall

    xdg = tmp_path / "xdg"
    (xdg / "steph").mkdir(parents=True)
    (xdg / "pulse").mkdir()
    monkeypatch.setattr(config, "RUNTIME_DIR", xdg / "steph")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data" / "steph")
    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "cfg" / "steph" / "config.toml")
    monkeypatch.setattr(uninstall, "find_uv", lambda: None)
    assert uninstall.main(keep_models=False, yes=True) == 0
    assert not (xdg / "steph").exists()
    assert (xdg / "pulse").exists()


def test_find_uv_also_looks_in_the_installers_bin_dir(tmp_path, monkeypatch):
    """Lancé par son chemin complet, steph n'a pas ~/.local/bin dans le PATH : uv y est pourtant."""
    from steph import uninstall

    bindir = tmp_path / ".local" / "bin"
    bindir.mkdir(parents=True)
    (bindir / "uv").write_text("#!/bin/sh\n")
    (bindir / "uv").chmod(0o755)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    assert uninstall.find_uv() == str(bindir / "uv")


def test_uninstall_reports_what_could_not_be_removed(tmp_path):
    from steph import uninstall

    data, conf, run = _home(tmp_path)
    out = []
    code = uninstall.run_uninstall(data, conf, run, keep_models=False, yes=True, ask=None, out=out.append,
                                   run=lambda cmd, **kw: types.SimpleNamespace(returncode=0), uv=None,
                                   prefix="", remove=lambda p: None)
    assert code != 0
    assert any(str(data) in line and ("Non supprimé" in line) for line in out)
    assert "steph est désinstallé." not in out


def test_uninstall_styles_header_and_success_without_changing_text(tmp_path):
    from steph import uninstall
    from steph.term_style import Style
    from steph.textproc import strip_ansi

    data, conf, run = _home(tmp_path)
    out = []
    code = uninstall.run_uninstall(data, conf, run, keep_models=False, yes=True, ask=None, out=out.append,
                                   run=lambda cmd, **kw: types.SimpleNamespace(returncode=0),
                                   uv="/bin/uv", prefix="/x/uv/tools/steph", style=Style("truecolor"))
    assert code == 0
    assert out[0] == "\x1b[1msteph uninstall va supprimer :\x1b[0m"
    assert out[-1] == "\x1b[38;2;11;11;11;48;2;226;255;59msteph est désinstallé.\x1b[0m"
    assert strip_ansi(out[-1]) == "steph est désinstallé."
