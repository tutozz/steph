"""Tests of the pure parts of bench/matrix/finetune/capture_corpus.py (K2).

No subprocess is ever run here: only task-list generation and the locale/env
helper are exercised. Running commands for real is done by hand on each
machine (K2 step), never in this suite.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bench" / "matrix" / "finetune"))

import pytest

from capture_corpus import (
    FORBIDDEN_ON_LINUX_LOW,
    PROFILE_BUILDERS,
    build_tasks,
    locale_env,
)

REQUIRED_KEYS = {"cmd", "category", "workdir", "setup", "timeout"}


# ---------------------------------------------------------------- locale_env

def test_locale_env_fr_leaves_lang_untouched():
    base = {"LANG": "fr_FR.UTF-8", "PATH": "/usr/bin"}
    env = locale_env("fr", base)
    assert env["LANG"] == "fr_FR.UTF-8"
    assert "LC_ALL" not in env


def test_locale_env_en_sets_macos_locale(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    env = locale_env("en", {"PATH": "/usr/bin"})
    assert env["LANG"] == "en_US.UTF-8"
    assert env["LC_ALL"] == "en_US.UTF-8"


def test_locale_env_en_sets_linux_locale(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    env = locale_env("en", {"PATH": "/usr/bin"})
    assert env["LANG"] == "C.utf8"
    assert env["LC_ALL"] == "C.utf8"


def test_locale_env_rejects_unknown_lang():
    with pytest.raises(ValueError):
        locale_env("de", {})


def test_locale_env_copies_rather_than_mutates_input():
    base = {"LANG": "fr_FR.UTF-8"}
    locale_env("en", base)
    assert base == {"LANG": "fr_FR.UTF-8"}  # the caller's dict is untouched


# ---------------------------------------------------------------- build_tasks

@pytest.mark.parametrize("profile", sorted(PROFILE_BUILDERS))
def test_build_tasks_nonempty(profile, tmp_path):
    tasks = build_tasks(profile, str(tmp_path))
    assert len(tasks) > 50


@pytest.mark.parametrize("profile", sorted(PROFILE_BUILDERS))
def test_build_tasks_shape(profile, tmp_path):
    tasks = build_tasks(profile, str(tmp_path))
    for t in tasks:
        assert REQUIRED_KEYS <= t.keys()
        assert isinstance(t["cmd"], str) and t["cmd"]
        assert isinstance(t["category"], str) and t["category"]
        assert isinstance(t["workdir"], str) and t["workdir"]
        assert isinstance(t["timeout"], int) and t["timeout"] > 0
        assert t["setup"] is None or (isinstance(t["setup"], str) and t["setup"])


@pytest.mark.parametrize("profile", sorted(PROFILE_BUILDERS))
def test_build_tasks_covers_core_families(profile, tmp_path):
    tasks = build_tasks(profile, str(tmp_path))
    categories = {t["category"] for t in tasks}
    expected = {"compilation", "packages", "git", "files", "network", "system", "interactive"}
    assert expected <= categories


def test_build_tasks_unknown_profile_raises(tmp_path):
    with pytest.raises(ValueError):
        build_tasks("windows-11", str(tmp_path))


# ---------------------------------------------------------------- safety: linux-low

def test_linux_low_forbids_destructive_or_apt_install(tmp_path):
    tasks = build_tasks("linux-low", str(tmp_path))
    for t in tasks:
        blob = " ".join(filter(None, [t["cmd"], t["setup"]]))
        for snippet in FORBIDDEN_ON_LINUX_LOW:
            assert snippet not in blob, f"forbidden snippet {snippet!r} found in: {blob!r}"


def test_linux_low_rm_rf_stays_inside_the_sandbox(tmp_path):
    """Any `rm -rf X` in a setup step must target a path under the sandbox
    (base), never a real system path - this is what makes the sandbox
    reusable/rewritable without ever touching the live machine."""
    base = str(tmp_path)
    tasks = build_tasks("linux-low", base)
    for t in tasks:
        setup = t["setup"] or ""
        for line in setup.split("&&"):
            line = line.strip()
            if line.startswith("rm -rf "):
                target = line.removeprefix("rm -rf ").strip()
                assert target.startswith(base), f"rm -rf outside sandbox: {target!r}"


def test_linux_low_has_no_docker_run(tmp_path):
    tasks = build_tasks("linux-low", str(tmp_path))
    docker_cmds = [t["cmd"] for t in tasks if t["cmd"].startswith("docker")]
    assert docker_cmds  # containers family is still exercised, read-only
    assert all(c.split()[1] in {"ps", "images", "version", "info", "inspect", "logs"} for c in docker_cmds)
