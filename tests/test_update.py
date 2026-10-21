"""`steph update` : ce qui est lancé selon le mode d'installation, sans réseau réel."""

import subprocess

from steph import update


class FakeRun:
    """Remplace subprocess.run : enregistre les commandes, répond selon un préfixe."""

    def __init__(self, replies=None):
        self.calls = []
        self.replies = replies or {}

    def __call__(self, cmd, **kw):
        self.calls.append(cmd)
        for prefix, (code, out) in self.replies.items():
            if " ".join(cmd).startswith(prefix):
                return subprocess.CompletedProcess(cmd, code, out, "")
        return subprocess.CompletedProcess(cmd, 0, "", "")


def _clone(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "install.sh").write_text("#!/bin/sh\n")
    return tmp_path


def test_clone_update_pulls_then_runs_install_script(tmp_path):
    d = _clone(tmp_path)
    run = FakeRun()
    assert update.run_update(d, check=False, run=run, out=lambda s: None) == 0
    assert run.calls[0] == ["git", "-C", str(d), "pull", "--ff-only"]
    assert run.calls[1] == ["bash", str(d / "scripts" / "install.sh"), "--update"]


def test_clone_update_stops_when_pull_fails(tmp_path):
    d = _clone(tmp_path)
    run = FakeRun({"git -C": (1, "")})
    lines = []
    assert update.run_update(d, check=False, run=run, out=lines.append) == 1
    assert len(run.calls) == 1
    assert any("git pull" in line for line in lines)


def test_clone_check_changes_nothing(tmp_path):
    d = _clone(tmp_path)
    run = FakeRun({
        f"git -C {d} rev-parse HEAD": (0, "aaa\n"),
        f"git -C {d} rev-parse --abbrev-ref": (0, "origin/master\n"),
        f"git -C {d} ls-remote": (0, "bbb\trefs/heads/master\n"),
        f"git -C {d} merge-base": (1, ""),
    })
    lines = []
    assert update.run_update(d, check=True, run=run, out=lines.append) == 0
    flat = [" ".join(c) for c in run.calls]
    assert not any(" pull" in c or " fetch" in c for c in flat)
    assert flat[-1] == f"bash {d / 'scripts' / 'install.sh'} --check"
    assert any("nouvelle version" in line for line in lines)


def test_clone_check_up_to_date(tmp_path):
    d = _clone(tmp_path)
    run = FakeRun({
        f"git -C {d} rev-parse HEAD": (0, "aaa\n"),
        f"git -C {d} rev-parse --abbrev-ref": (0, "origin/master\n"),
        f"git -C {d} ls-remote": (0, "aaa\trefs/heads/master\n"),
    })
    lines = []
    update.run_update(d, check=True, run=run, out=lines.append)
    assert any("steph : à jour" in line for line in lines)


def test_non_clone_only_gives_the_command(tmp_path, monkeypatch):
    monkeypatch.setattr(update.sys, "prefix", "/Users/x/.local/share/uv/tools/steph")
    monkeypatch.setattr(update.shutil, "which", lambda name: None)
    run = FakeRun()
    lines = []
    assert update.run_update(None, check=False, run=run, out=lines.append) == 0
    assert run.calls == []
    assert any("uv tool upgrade steph" in line for line in lines)


def test_non_clone_homebrew(tmp_path, monkeypatch):
    monkeypatch.setattr(update.sys, "prefix", "/opt/homebrew/Cellar/steph/0.1.0/libexec")
    monkeypatch.setattr(update.shutil, "which", lambda name: None)
    lines = []
    update.run_update(None, check=True, run=FakeRun(), out=lines.append)
    assert any("brew upgrade steph" in line for line in lines)


def test_non_clone_upgrades_homebrew_llama(monkeypatch):
    monkeypatch.setattr(update.sys, "prefix", "/opt/homebrew/Cellar/steph/0.1.0/libexec")
    monkeypatch.setattr(update.shutil, "which", lambda name: "/opt/homebrew/bin/" + name)
    run = FakeRun({"brew outdated": (0, "llama.cpp\n")})
    update.run_update(None, check=False, run=run, out=lambda s: None)
    assert ["brew", "upgrade", "llama.cpp"] in run.calls
    run = FakeRun({"brew outdated": (0, "llama.cpp\n")})
    update.run_update(None, check=True, run=run, out=lambda s: None)
    assert ["brew", "upgrade", "llama.cpp"] not in run.calls


def test_cli_dispatches_update_check(monkeypatch):
    from steph import cli
    seen = []
    monkeypatch.setattr(update, "main", lambda check: seen.append(check) or 0)
    assert cli.main(["update", "--check"]) == 0
    assert cli.main(["update"]) == 0
    assert seen == [True, False]


def test_clone_check_local_commits_ahead_is_not_an_update(tmp_path):
    d = _clone(tmp_path)
    run = FakeRun({
        f"git -C {d} rev-parse HEAD": (0, "aaa\n"),
        f"git -C {d} rev-parse --abbrev-ref": (0, "origin/master\n"),
        f"git -C {d} ls-remote": (0, "bbb\trefs/heads/master\n"),
        f"git -C {d} merge-base --is-ancestor bbb HEAD": (0, ""),
    })
    lines = []
    update.run_update(d, check=True, run=run, out=lines.append)
    assert not any("nouvelle version" in line for line in lines)
    assert any("à jour" in line for line in lines)


def test_update_failure_is_bold_when_styled(tmp_path):
    from steph.term_style import Style

    d = _clone(tmp_path)
    lines = []
    assert update.run_update(d, check=False, run=FakeRun({"git -C": (1, "")}), out=lines.append,
                             style=Style("truecolor")) == 1
    assert lines[0].startswith("\x1b[1msteph : ")
    assert lines[0].endswith("\x1b[0m")


def test_update_available_is_lemon_when_styled(tmp_path):
    from steph.term_style import Style

    d = _clone(tmp_path)
    run = FakeRun({
        "git -C {} rev-parse HEAD".format(d): (0, "aaa\n"),
        "git -C {} rev-parse --abbrev-ref".format(d): (0, "origin/master\n"),
        "git -C {} ls-remote".format(d): (0, "bbb\trefs/heads/master\n"),
        "git -C {} merge-base".format(d): (1, ""),
    })
    lines = []
    update.run_update(d, check=True, run=run, out=lines.append, style=Style("truecolor"))
    assert "\x1b[38;2;11;11;11;48;2;226;255;59msteph : nouvelle version disponible.\x1b[0m" in lines
