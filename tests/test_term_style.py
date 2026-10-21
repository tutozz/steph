"""Style terminal de la charte : profondeur de couleur, repli, NO_COLOR, logo, et
parité avec la copie shell (src/steph/shell/style.sh) lue par les scripts."""

import io
import shutil
import subprocess
from pathlib import Path

import pytest

from steph import term_style as ts

REPO = Path(__file__).resolve().parents[1]
STYLE_SH = REPO / "src" / "steph" / "shell" / "style.sh"

TRUECOLOR = {"TERM": "xterm-256color", "COLORTERM": "truecolor"}


# ------------------------------------------------------------ profondeur de couleur


@pytest.mark.parametrize("env, expected", [
    ({"TERM": "xterm-256color", "COLORTERM": "truecolor"}, "truecolor"),
    ({"TERM": "xterm-kitty", "COLORTERM": "24bit"}, "truecolor"),
    ({"TERM": "xterm-256color"}, "256"),
    ({"TERM": "screen-256color", "COLORTERM": ""}, "256"),
    ({"TERM": "xterm"}, "16"),
    ({"TERM": "linux"}, "16"),
    ({"TERM": "dumb", "COLORTERM": "truecolor"}, None),
    ({}, None),
    ({"TERM": "xterm-256color", "COLORTERM": "truecolor", "NO_COLOR": "1"}, None),
])
def test_color_depth_follows_colorterm_term_and_no_color(env, expected):
    assert ts.color_depth(env, isatty=True) == expected


def test_color_depth_ignores_empty_no_color():
    # no-color.org : seul un NO_COLOR non vide désactive la couleur
    assert ts.color_depth({**TRUECOLOR, "NO_COLOR": ""}, isatty=True) == "truecolor"


def test_color_depth_is_none_when_output_is_not_a_terminal():
    assert ts.color_depth(TRUECOLOR, isatty=False) is None


# ------------------------------------------------------------ séquences


def test_truecolor_sequences_use_the_exact_charter_values():
    assert ts.fg_params("lemon", "truecolor") == "38;2;226;255;59"
    assert ts.bg_params("black", "truecolor") == "48;2;11;11;11"
    assert ts.fg_params("offwhite", "truecolor") == "38;2;244;244;240"
    assert ts.fg_params("gray", "truecolor") == "38;2;138;138;133"


def test_256_color_fallback_uses_the_nearest_xterm_index():
    assert ts.fg_params("lemon", "256") == "38;5;191"   # #d7ff5f
    assert ts.bg_params("black", "256") == "48;5;232"   # #080808
    assert ts.fg_params("offwhite", "256") == "38;5;255"  # #eeeeee
    assert ts.fg_params("gray", "256") == "38;5;245"    # #8a8a8a


def test_16_color_fallback_uses_basic_ansi_codes():
    assert ts.fg_params("lemon", "16") == "93"
    assert ts.bg_params("lemon", "16") == "103"
    assert ts.fg_params("black", "16") == "30"
    assert ts.bg_params("black", "16") == "40"
    assert ts.fg_params("offwhite", "16") == "97"
    assert ts.fg_params("gray", "16") == "90"


def test_plain_style_adds_no_escape_sequence():
    style = ts.Style(None)
    assert style.paint("steph", fg="lemon", bg="black", bold=True) == "steph"
    assert style.accent("recommandé") == "recommandé"
    assert style.muted("pas encore publié") == "pas encore publié"
    assert style.strong("titre") == "titre"


def test_colored_style_wraps_text_and_resets():
    style = ts.Style("truecolor")
    out = style.paint("x", fg="lemon", bg="black", bold=True)
    assert out == "\x1b[1;38;2;226;255;59;48;2;11;11;11mx\x1b[0m"


def test_styled_text_reads_the_same_once_sequences_are_stripped():
    from steph.textproc import strip_ansi

    style = ts.Style("truecolor")
    for text in ("recommandé", "non recommandé : pas optimisé pour steph", "steph est installé."):
        assert strip_ansi(style.accent(text)) == text
        assert strip_ansi(style.muted(text)) == text
        assert strip_ansi(style.strong(text)) == text


def test_no_blinking_attribute_is_ever_emitted():
    style = ts.Style("truecolor")
    rendered = style.logo() + style.accent("a") + style.muted("b") + style.strong("c") + style.selected("d")
    assert "\x1b[5m" not in rendered and ";5m" not in rendered.replace("38;5;", "").replace("48;5;", "")


# ------------------------------------------------------------ logo


def test_chevron_is_single_guillemet_in_utf8_and_ascii_otherwise():
    assert ts.chevron({"TERM": "xterm-256color"}, "utf-8") == "›"
    assert ts.chevron({"TERM": "xterm-256color"}, "ascii") == ">"
    assert ts.chevron({"TERM": "dumb"}, "utf-8") == ">"  # terminal minimal : ASCII


def test_logo_is_black_word_and_chevron_on_lemon_on_one_line():
    logo = ts.Style("truecolor", chevron="›").logo()
    assert logo == "\x1b[38;2;11;11;11;48;2;226;255;59m steph › \x1b[0m"


def _sets_fg_and_bg(sequence: str) -> tuple[bool, bool]:
    params = [int(p) for p in sequence[2:sequence.index("m")].split(";")]
    fg = 38 in params or any(30 <= p <= 37 or 90 <= p <= 97 for p in params)
    bg = 48 in params or any(40 <= p <= 47 or 100 <= p <= 107 for p in params)
    return fg, bg


@pytest.mark.parametrize("depth", ["256", "16"])
def test_roles_never_set_a_text_color_without_a_background(depth):
    # fond du terminal inconnu : citron ou blanc cassé seuls seraient illisibles sur un thème clair
    style = ts.Style(depth)
    for text in (style.strong("a"), style.accent("a"), style.muted("a"), style.selected("a"), style.logo()):
        fg, bg = _sets_fg_and_bg(text)
        assert bg or not fg, repr(text)


def test_plain_logo_is_the_word_and_chevron():
    assert ts.Style(None, chevron=">").logo() == "steph >"


def test_for_stream_is_plain_when_stream_is_not_a_tty(monkeypatch):
    monkeypatch.setenv("TERM", "xterm-256color")
    monkeypatch.setenv("COLORTERM", "truecolor")
    monkeypatch.delenv("NO_COLOR", raising=False)
    assert ts.for_stream(io.StringIO()).depth is None


class FakeTty(io.StringIO):
    encoding = "utf-8"

    def isatty(self):
        return True


def test_cli_error_is_bold_on_a_terminal_and_plain_otherwise(monkeypatch):
    from steph import cli

    monkeypatch.setenv("TERM", "xterm-256color")
    monkeypatch.setenv("COLORTERM", "truecolor")
    monkeypatch.delenv("NO_COLOR", raising=False)
    tty = FakeTty()
    monkeypatch.setattr("sys.stderr", tty)
    cli._error("Aucune session steph active.")
    assert tty.getvalue() == "\x1b[1mAucune session steph active.\x1b[0m\n"

    monkeypatch.setenv("NO_COLOR", "1")
    tty = FakeTty()
    monkeypatch.setattr("sys.stderr", tty)
    cli._error("Aucune session steph active.")
    assert tty.getvalue() == "Aucune session steph active.\n"


# ------------------------------------------------------------ parité avec style.sh


def _sh(script: str, env: dict) -> str:
    out = subprocess.run(["sh", "-c", f'. "{STYLE_SH}"; {script}'], env={"PATH": "/usr/bin:/bin", **env},
                         capture_output=True, text=True, timeout=10)
    assert out.returncode == 0, out.stderr
    return out.stdout


@pytest.mark.parametrize("env", [
    TRUECOLOR, {"TERM": "xterm-256color"}, {"TERM": "xterm"}, {"TERM": "dumb"}, {},
    {**TRUECOLOR, "NO_COLOR": "1"}, {**TRUECOLOR, "NO_COLOR": ""},
])
def test_shell_color_depth_matches_python(env):
    expected = ts.color_depth(env, isatty=True) or "none"
    assert _sh("__steph_color_depth", env) == expected


@pytest.mark.parametrize("depth", ["truecolor", "256", "16"])
@pytest.mark.parametrize("name", ["black", "offwhite", "lemon", "gray"])
def test_shell_palette_matches_python(depth, name):
    assert _sh(f"__steph_fg {depth} {name}", {}) == ts.fg_params(name, depth)
    assert _sh(f"__steph_bg {depth} {name}", {}) == ts.bg_params(name, depth)


@pytest.mark.parametrize("env, expected", [
    ({"TERM": "xterm-256color", "LANG": "fr_FR.UTF-8"}, "›"),
    ({"TERM": "xterm-256color", "LC_ALL": "en_US.utf8"}, "›"),
    ({"TERM": "xterm-256color", "LANG": "C"}, ">"),
    ({"TERM": "dumb", "LANG": "fr_FR.UTF-8"}, ">"),
])
def test_shell_chevron_follows_locale_and_term(env, expected):
    assert _sh("__steph_chevron", env) == expected


@pytest.mark.skipif(shutil.which("zsh") is None, reason="zsh absent")
def test_style_sh_also_loads_in_zsh():
    out = subprocess.run(["zsh", "-c", f'source "{STYLE_SH}"; __steph_fg truecolor lemon'],
                         capture_output=True, text=True, timeout=10)
    assert out.stdout == "38;2;226;255;59"
