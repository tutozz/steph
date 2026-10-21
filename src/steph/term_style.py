"""Charte graphique dans le terminal (docs/design/tokens.json).

Seule source des couleurs de steph en terminal ; `shell/style.sh` en est la copie
pour les scripts shell (parité vérifiée par tests/test_term_style.py).
Aucun style si NO_COLOR est non vide, si TERM vaut dumb ou si la sortie n'est pas
un terminal. Jamais de clignotement ; la couleur ne porte jamais seule le sens.
"""

from __future__ import annotations

import os
from typing import Mapping, TextIO

RGB = {
    "black": (11, 11, 11),
    "offwhite": (244, 244, 240),
    "lemon": (226, 255, 59),
    "gray": (138, 138, 133),
}
# index xterm le plus proche de chaque couleur
XTERM_256 = {"black": 232, "offwhite": 255, "lemon": 191, "gray": 245}
ANSI_16_FG = {"black": 30, "offwhite": 97, "lemon": 93, "gray": 90}

CHEVRON = "›"
CHEVRON_ASCII = ">"


def color_depth(env: Mapping[str, str] | None = None, isatty: bool = True) -> str | None:
    """"truecolor", "256", "16", ou None (aucun style)."""
    env = os.environ if env is None else env
    term = env.get("TERM", "")
    if not isatty or env.get("NO_COLOR") or term in ("", "dumb"):
        return None
    if env.get("COLORTERM") in ("truecolor", "24bit"):
        return "truecolor"
    return "256" if "256color" in term else "16"


def fg_params(name: str, depth: str) -> str:
    if depth == "truecolor":
        return "38;2;{};{};{}".format(*RGB[name])
    if depth == "256":
        return f"38;5;{XTERM_256[name]}"
    return str(ANSI_16_FG[name])


def bg_params(name: str, depth: str) -> str:
    if depth == "truecolor":
        return "48;2;{};{};{}".format(*RGB[name])
    if depth == "256":
        return f"48;5;{XTERM_256[name]}"
    return str(ANSI_16_FG[name] + 10)


def chevron(env: Mapping[str, str] | None = None, encoding: str | None = "utf-8") -> str:
    """› (U+203A) : guillemet que les lecteurs d'écran taisent au niveau de ponctuation
    par défaut ; > en ASCII hors UTF-8 et sur un terminal minimal."""
    env = os.environ if env is None else env
    utf8 = (encoding or "").lower().replace("-", "") == "utf8"
    return CHEVRON if utf8 and env.get("TERM", "") != "dumb" else CHEVRON_ASCII


class Style:
    """Rôles de la charte : `strong` (titres), `accent` (recommandé, succès, sélection),
    `muted` (bloqué, secondaire), `logo` (« steph » + chevron).

    Le fond du terminal est inconnu (thème clair ou sombre) : un rôle ne pose jamais
    une couleur de texte seule. `strong` garde la couleur du thème, `accent` et `logo`
    sont noir sur citron, `muted` gris sur noir."""

    def __init__(self, depth: str | None, chevron: str = CHEVRON):
        self.depth = depth
        self.chevron = chevron

    def paint(self, text: str, fg: str | None = None, bg: str | None = None, bold: bool = False) -> str:
        if not self.depth or not text:
            return text
        params = (["1"] if bold else []) + ([fg_params(fg, self.depth)] if fg else []) \
            + ([bg_params(bg, self.depth)] if bg else [])
        return f"\x1b[{';'.join(params)}m{text}\x1b[0m" if params else text

    def bg_params(self, name: str) -> str:
        return bg_params(name, self.depth) if self.depth else ""

    def strong(self, text: str) -> str:
        return self.paint(text, bold=True)

    def accent(self, text: str) -> str:
        return self.paint(text, fg="black", bg="lemon")

    def muted(self, text: str) -> str:
        return self.paint(text, fg="gray", bg="black")

    def selected(self, text: str) -> str:
        """Élément choisi : noir sur citron ; vidéo inverse sans couleur."""
        if not self.depth:
            return f"\x1b[7m{text}\x1b[27m"
        return self.paint(text, fg="black", bg="lemon", bold=True)

    def logo(self) -> str:
        """Déclinaison « sur citron » : mot et chevron noirs, comme l'indicateur de prompt."""
        if not self.depth:
            return f"steph {self.chevron}"
        return self.accent(f" steph {self.chevron} ")


def for_stream(stream: TextIO, env: Mapping[str, str] | None = None) -> Style:
    env = os.environ if env is None else env
    try:
        isatty = stream.isatty()
    except (AttributeError, ValueError):
        isatty = False
    return Style(color_depth(env, isatty), chevron(env, getattr(stream, "encoding", None)))
