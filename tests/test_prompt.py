"""Indicateur de prompt (F6) : source l'intégration shell dans un sous-shell non
interactif et vérifie l'idempotence, l'insertion sur la dernière ligne (thème
multiligne, starship...) et le style (segment citron : chevron et touche en noir, pointe)."""

import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
ZSH_INTEGRATION = REPO / "src" / "steph" / "shell" / "integration.zsh"
BASHRC = REPO / "src" / "steph" / "shell" / "bashrc"
TAG_ENV = {"STEPH_MENU_KEY": "F6", "TERM": "xterm-256color", "COLORTERM": "truecolor", "LANG": "fr_FR.UTF-8"}
TIP = "\ue0b0"
ESC = "\x1b"
LEMON_BG_BLACK_FG = ESC + "[0;48;2;226;255;59;38;2;11;11;11m"
LEMON_FG = ESC + "[0;38;2;226;255;59m"
RESET = ESC + "[0m"
# segment citron : chevron noir et touche du menu, puis pointe citron sur le fond du terminal
ZSH_TAG = "%{" + LEMON_BG_BLACK_FG + "%} \u203a F6 %{" + LEMON_FG + "%}" + TIP + "%{" + RESET + "%} "
BASH_TAG = "\\[" + LEMON_BG_BLACK_FG + "\\] \u203a F6 \\[" + LEMON_FG + "\\]" + TIP + "\\[" + RESET + "\\] "


def run_zsh(script: str, cwd, extra: dict | None = None) -> subprocess.CompletedProcess:
    import os

    env = {k: v for k, v in os.environ.items() if k not in ("NO_COLOR", "STEPH_PROMPT_TIP", "LC_ALL", "LC_CTYPE")}
    env.update(TAG_ENV, **(extra or {}))
    return subprocess.run(["zsh", "-c", script], cwd=cwd, capture_output=True, text=True, env=env, timeout=10)


def run_bash(script: str, home, cwd, extra: dict | None = None) -> subprocess.CompletedProcess:
    env = {"HOME": str(home), "PATH": "/usr/bin:/bin", **TAG_ENV, **(extra or {})}
    return subprocess.run(["bash", "-c", script], cwd=cwd, capture_output=True, text=True, env=env, timeout=10)


# ------------------------------------------------------------ zsh : statique, une ligne


@pytest.mark.skipif(shutil.which("zsh") is None, reason="zsh absent")
def test_zsh_static_single_line_prompt_is_tagged_once(tmp_path):
    script = f"""
    PROMPT="%# "
    source "{ZSH_INTEGRATION}"
    __steph_prompt_tag
    __steph_prompt_tag
    print -r -- $PROMPT
    """
    out = run_zsh(script, tmp_path)
    assert out.returncode == 0, out.stderr
    prompt = out.stdout.rstrip("\n")
    assert prompt.count("F6") == 1  # appelé deux fois : posé une seule fois
    assert prompt.startswith(ZSH_TAG)
    assert prompt.endswith("%# ")  # le prompt d'origine est conservé, à la fin


# ------------------------------------------------------------ zsh : statique, multiligne


@pytest.mark.skipif(shutil.which("zsh") is None, reason="zsh absent")
def test_zsh_static_multiline_prompt_is_tagged_on_last_line_only(tmp_path):
    script = f"""
    PROMPT=$'info line\\n%# '
    source "{ZSH_INTEGRATION}"
    __steph_prompt_tag
    __steph_prompt_tag
    print -r -- $PROMPT
    """
    out = run_zsh(script, tmp_path)
    assert out.returncode == 0, out.stderr
    prompt = out.stdout.rstrip("\n")
    lines = prompt.split("\n")
    assert lines[0] == "info line"  # jamais touchée
    assert lines[1].startswith(ZSH_TAG)
    assert lines[1].endswith("%# ")
    assert prompt.count("F6") == 1


# ------------------------------------------------------------ zsh : dynamique (thème factice)


@pytest.mark.skipif(shutil.which("zsh") is None, reason="zsh absent")
def test_zsh_dynamic_multiline_theme_is_tagged_on_last_line_only(tmp_path):
    script = f"""
    setopt PROMPT_SUBST
    __fake_theme() {{ printf '\\ninfo-line %s\\n$ ' "$PWD" }}
    PROMPT='$(__fake_theme)'
    source "{ZSH_INTEGRATION}"
    for f in $precmd_functions; do $f; done
    for f in $precmd_functions; do $f; done
    print -r -- "EXPR=[$PROMPT]"
    print -r -- "RENDERED=[${{(e)PROMPT}}]"
    """
    out = run_zsh(script, tmp_path)
    assert out.returncode == 0, out.stderr
    # __steph_precmd (marqueurs OSC 6973) est aussi dans precmd_functions : ignorer
    # ce qui précède nos propres marqueurs "EXPR="/"RENDERED=" plutôt que découper
    # ligne à ligne (le marqueur OSC n'ajoute pas de retour à la ligne).
    expr, after = out.stdout.split("EXPR=[", 1)[1].split("]\n", 1)
    assert expr == "$(__steph_prompt_wrap)"  # appelé deux fois : reste ce wrapper
    raw = after.split("RENDERED=[", 1)[1].rstrip("\n")
    rendered = raw[:-1]  # retire le "]" final
    lines = rendered.split("\n")
    assert lines[0] == ""  # ligne vide d'origine (add_newline-like), jamais touchée
    assert lines[1].startswith("info-line ")  # jamais touchée
    assert lines[2].startswith(ZSH_TAG)
    assert lines[2].endswith("$ ")
    assert rendered.count("F6") == 1


@pytest.mark.skipif(shutil.which("zsh") is None or shutil.which("starship") is None,
                    reason="zsh ou starship absent")
def test_zsh_real_starship_prompt_is_tagged_on_last_line_only(tmp_path):
    starship_toml = tmp_path / "starship.toml"
    starship_toml.write_text("add_newline = true\n")
    script = f"""
    eval "$(starship init zsh)"
    source "{ZSH_INTEGRATION}"
    for f in $precmd_functions; do $f; done
    for f in $precmd_functions; do $f; done
    print -r -- "LAST=${{precmd_functions[-1]}}"
    print -r -- "EXPR=[$PROMPT]"
    print -r -- "RENDERED=[${{(e)PROMPT}}]"
    """
    import os
    env = dict(os.environ, **TAG_ENV, STARSHIP_CONFIG=str(starship_toml))
    out = subprocess.run(["zsh", "-c", script], cwd=tmp_path, capture_output=True, text=True, env=env, timeout=10)
    assert out.returncode == 0, out.stderr
    # __steph_precmd (marqueurs OSC 6973) est aussi dans precmd_functions : ignorer
    # ce qui précède nos propres marqueurs plutôt que découper ligne à ligne.
    last, after = out.stdout.split("LAST=", 1)[1].split("\n", 1)
    expr, after = after.split("EXPR=[", 1)[1].split("]\n", 1)
    assert last == "__steph_prompt_tag"
    assert expr == "$(__steph_prompt_wrap)"
    raw = after.split("RENDERED=[", 1)[1].rstrip("\n")
    rendered = raw[:-1]  # retire le "]" final
    lines = rendered.split("\n")
    # le tag n'est jamais sur la première ligne (infos starship), toujours sur la dernière
    assert "F6" not in lines[0]
    assert lines[-1].startswith(ZSH_TAG)
    assert rendered.count("F6") == 1


# ------------------------------------------------------------ zsh : ordre d'enregistrement


@pytest.mark.skipif(shutil.which("zsh") is None, reason="zsh absent")
def test_zsh_prompt_tag_is_registered_last_in_precmd_functions(tmp_path):
    script = f"""
    PROMPT="%# "
    precmd_functions=(some_theme_hook)
    source "{ZSH_INTEGRATION}"
    print -r -- ${{precmd_functions[-1]}}
    """
    out = run_zsh(script, tmp_path)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "__steph_prompt_tag"


# ------------------------------------------------------------ bash : statique, une ligne et multiligne


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash absent")
def test_bash_single_line_ps1_is_tagged_once(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    script = f"""
    PS1="\\\\u\\\\$ "
    source "{BASHRC}"
    __steph_ready
    __steph_ready
    printf 'PS1_START%sPS1_END' "$PS1"
    """
    out = run_bash(script, home, tmp_path)
    assert out.returncode == 0, out.stderr
    ps1 = out.stdout.split("PS1_START", 1)[1].split("PS1_END", 1)[0]
    assert ps1.count("F6") == 1
    assert ps1.startswith(BASH_TAG)
    assert ps1.endswith("\\u\\$ ")  # le PS1 d'origine est conservé, à la fin


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash absent")
def test_bash_multiline_ps1_is_tagged_on_last_line_only(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    script = f"""
    PS1=$'info line\\n\\\\$ '
    source "{BASHRC}"
    __steph_ready
    __steph_ready
    printf 'PS1_START%sPS1_END' "$PS1"
    """
    out = run_bash(script, home, tmp_path)
    assert out.returncode == 0, out.stderr
    ps1 = out.stdout.split("PS1_START", 1)[1].split("PS1_END", 1)[0]
    lines = ps1.split("\n")
    assert lines[0] == "info line"  # jamais touchée
    assert lines[1].startswith(BASH_TAG)
    assert lines[1].endswith("\\$ ")
    assert ps1.count("F6") == 1


# ------------------------------------------------------------ replis : NO_COLOR, TERM=dumb, police sans pointe

ZSH_PRINT = """
    PROMPT="%# "
    source "{path}"
    __steph_prompt_tag
    print -r -- $PROMPT
    """
BASH_PRINT = """
    PS1="\\\\$ "
    source "{path}"
    __steph_ready
    printf 'PS1_START%sPS1_END' "$PS1"
    """


def _zsh_prompt(tmp_path, extra):
    out = run_zsh(ZSH_PRINT.format(path=ZSH_INTEGRATION), tmp_path, extra)
    assert out.returncode == 0, out.stderr
    return out.stdout.rstrip("\n")


def _bash_prompt(tmp_path, extra):
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    out = run_bash(BASH_PRINT.format(path=BASHRC), home, tmp_path, extra)
    assert out.returncode == 0, out.stderr
    return out.stdout.split("PS1_START", 1)[1].split("PS1_END", 1)[0]


@pytest.mark.parametrize("extra, expected", [
    ({"NO_COLOR": "1"}, "\u203a F6 "),
    ({"TERM": "dumb"}, "> F6 "),
    ({"LANG": "C"}, None),
])
@pytest.mark.parametrize("shell", ["zsh", "bash"])
def test_prompt_fallbacks_stay_readable_without_color_or_utf8(tmp_path, shell, extra, expected):
    if shutil.which(shell) is None:
        pytest.skip(f"{shell} absent")
    prompt = (_zsh_prompt if shell == "zsh" else _bash_prompt)(tmp_path, extra)
    if expected is not None:
        assert prompt.startswith(expected)
        assert ESC not in prompt  # aucune séquence : rien de plus à lire, rien à mal afficher
    else:
        # locale non UTF-8 : couleurs gardées, chevron ASCII, pas de pointe powerline
        assert " > F6 " in prompt and TIP not in prompt and "\u203a" not in prompt
    assert prompt.count("F6") == 1


@pytest.mark.parametrize("shell", ["zsh", "bash"])
def test_prompt_tip_can_be_removed_for_fonts_without_powerline_glyphs(tmp_path, shell):
    if shutil.which(shell) is None:
        pytest.skip(f"{shell} absent")
    prompt = (_zsh_prompt if shell == "zsh" else _bash_prompt)(tmp_path, {"STEPH_PROMPT_TIP": ""})
    assert TIP not in prompt
    assert " \u203a F6 " in prompt


@pytest.mark.skipif(shutil.which("zsh") is None or shutil.which("bash") is None, reason="zsh ou bash absent")
def test_zsh_and_bash_segments_are_identical_once_wrappers_are_removed(tmp_path):
    zsh = _zsh_prompt(tmp_path, {}).replace("%{", "").replace("%}", "")
    bash = _bash_prompt(tmp_path, {}).replace("\\[", "").replace("\\]", "")
    assert zsh.removesuffix("%# ") == bash.removesuffix("\\$ ")


# ------------------------------------------------------------ constantes / câblage


def test_cli_menu_key_and_no_dead_prompt_tag():
    from steph import cli

    assert cli.MENU_KEY == "F6"
    assert not hasattr(cli, "PROMPT_TAG")  # STEPH_PROMPT_TAG n'était lu par aucun script shell


def test_help_keys_still_mentions_f6_for_the_menu_help_entry():
    from steph.cli import HELP_KEYS

    assert HELP_KEYS.startswith("F6 menu, ")


def test_proxy_shell_argv_exports_menu_key_only(monkeypatch):
    from steph.config import Config
    from steph.proxy import PtyProxy

    monkeypatch.setenv("SHELL", "/bin/zsh")
    cfg = Config()
    proxy = PtyProxy(cfg, narrator=None, socket_path="/tmp/unused.sock", menu_key="F6")
    _, env = proxy._shell_argv()
    assert "STEPH_PROMPT_TAG" not in env
    assert env["STEPH_MENU_KEY"] == "F6"
