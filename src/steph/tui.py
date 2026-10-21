"""Interface plein écran accessible (M6, docs/tui-a11y.md).

Trois couches séparées : le modèle d'état (`ChoiceModel`, pur), le rendu (`Renderer`,
chaînes ANSI pures) et la boucle d'E/S (`Screen`, lecture et écriture injectées).
Règles d'accessibilité : curseur visible posé sur la ligne focalisée, un mouvement ne
réécrit que la description et deux lignes, le focus porte un signe en plus de la couleur,
chaque changement de focus est dit. Repli en mode ligne décidé par `ui_mode`.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Callable, Iterator, Mapping

from .strings import t
from .term_style import Style

ENTER_SCREEN = "\x1b[?1049h"
LEAVE_SCREEN = "\x1b[0m\x1b[?25h\x1b[?1049l"
DESCRIPTION_LINES = 3
PROBE_TIMEOUT = 1.0

KEYS = {
    b"\x1b[A": "up", b"\x1bOA": "up", b"\x1b[B": "down", b"\x1bOB": "down",
    b"\x1b[C": "right", b"\x1bOC": "right", b"\x1b[D": "left", b"\x1bOD": "left",
    b"\r": "enter", b"\n": "enter", b"\x1b": "escape", b"\t": "tab", b"\x1b[Z": "backtab",
    b"\x1b[H": "home", b"\x1bOH": "home", b"\x1b[1~": "home", b"\x1b[7~": "home",
    b"\x1b[F": "end", b"\x1bOF": "end", b"\x1b[4~": "end", b"\x1b[8~": "end",
    b"\x7f": "backspace", b"\x08": "backspace", b"\x03": "interrupt", b"\x04": "interrupt",
}


# ------------------------------------------------------------ choix du mode
def _probe(run, argv: list[str]) -> str | None:
    """Sortie de `argv` si la commande réussit ; None si elle échoue ou n'existe pas."""
    try:
        r = run(argv, capture_output=True, text=True, timeout=PROBE_TIMEOUT)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout if r.returncode == 0 else None


def screen_reader_active(platform: str = sys.platform, run=subprocess.run,
                         exists: Callable[[str], bool] = os.path.exists) -> str | None:
    """Nom du lecteur d'écran actif, ou None. Une sonde en faute vaut « pas de lecteur »."""
    if platform == "darwin":
        if _probe(run, ["pgrep", "-x", "VoiceOver"]) is not None:
            return "VoiceOver"
        # clé non documentée par Apple, observée sur macOS : 1 quand VoiceOver est allumé
        key = _probe(run, ["defaults", "read", "com.apple.universalaccess", "voiceOverOnOffKey"])
        return "VoiceOver" if key is not None and key.strip() == "1" else None
    if platform.startswith("linux"):
        if _probe(run, ["pgrep", "-x", "orca"]) is not None:
            return "Orca"
        enabled = _probe(run, ["gsettings", "get", "org.gnome.desktop.a11y.applications",
                               "screen-reader-enabled"])
        if enabled is not None and enabled.strip() == "true":
            return "Orca"
        if exists("/sys/accessibility/speakup"):
            return "Speakup"
        if _probe(run, ["pgrep", "-x", "brltty"]) is not None:
            return "BRLTTY"
    return None


def ui_mode(pref: str, env: Mapping[str, str], isatty: bool,
            reader: Callable[[], str | None]) -> tuple[str, str]:
    """("tui" ou "line", raison) ; raison : no_tty, dumb, user, screen_reader, tui."""
    if not isatty:
        return "line", "no_tty"
    if env.get("TERM", "") in ("", "dumb"):
        return "line", "dumb"
    if pref in ("line", "tui"):
        return pref, "user"
    if reader():
        return "line", "screen_reader"
    return "tui", "tui"


# ------------------------------------------------------------ touches
def split_keys(data: bytes) -> list[bytes]:
    """Découpe un paquet d'octets bruts en une touche par élément : une séquence
    d'échappement complète (jusqu'à sa lettre ou son ~ final), ou un octet seul.

    Limite : suppose qu'une séquence n'est jamais coupée entre deux lectures du terminal.
    """
    out: list[bytes] = []
    i, n = 0, len(data)
    while i < n:
        if data[i:i + 2] == b"\x1bO" and i + 2 < n:
            # SS3 (ESC O A, ESC O P…) : le O est une lettre, la touche est l'octet suivant
            out.append(data[i:i + 3])
            i += 3
        elif data[i:i + 1] == b"\x1b":
            j = i + 1
            while j < n and not (65 <= data[j] <= 90 or 97 <= data[j] <= 122 or data[j:j + 1] == b"~"):
                j += 1
            if j < n:
                j += 1  # inclut la lettre / le ~ final
            out.append(data[i:j])
            i = j
        else:
            out.append(data[i:i + 1])
            i += 1
    return out


def decode_key(seq: bytes) -> str:
    """Nom d'une touche (« up », « enter »…), ou le caractère lui-même."""
    return KEYS.get(seq) or seq.decode("utf-8", "replace")


# ------------------------------------------------------------ modèle d'état
@dataclass(frozen=True)
class Option:
    label: str
    notes: tuple[str, ...] = ()
    tag: str = ""  # "recommended" (citron) ou "muted" (gris) ; le texte des notes porte le sens
    blocked: str = ""  # raison : l'option reste focalisable mais ne se valide pas
    detail: str = ""  # description affichée quand l'option a le focus


@dataclass
class Outcome:
    say: str | None = None
    redraw: str | None = None  # "focus", "line" (libellé focalisé changé) ou "description"
    old: int | None = None
    done: int | None = None
    cancelled: bool = False


class ChoiceModel:
    def __init__(self, title: str, question: str, options: list[Option], focus: int = 0, step: str = "",
                 language: str = "fr", body: tuple[str, ...] = (), detail: str = "", keys_bar: str = ""):
        self.title = title
        self.question = question
        self.options = options
        self.focus = focus
        self.step = step
        self.language = language
        self.body = body
        self.detail = detail  # description d'un écran sans option (capture de touche)
        self.keys_bar = keys_bar or t(language, "tui.keys_bar")
        self.showing_help = False

    def notes(self, i: int) -> tuple[str, ...]:
        o = self.options[i]
        blocked = (t(self.language, "tui.state_blocked").format(reason=o.blocked),) if o.blocked else ()
        return o.notes + blocked

    def spoken(self, i: int) -> str:
        return ", ".join((self.options[i].label, *self.notes(i)))

    def opening(self) -> str:
        question = ". ".join((self.question, *self.body))  # le résumé affiché est aussi dit
        return t(self.language, "tui.opening").format(question=question, focus=self.spoken(self.focus),
                                                      count=len(self.options))

    def description(self) -> str:
        if self.showing_help:
            return t(self.language, "tui.help")
        if not self.options:
            return self.detail
        # l'état est répété ici : une ligne trop longue pour l'écran est coupée à droite
        notes = ", ".join(self.notes(self.focus))
        state = f"{notes[:1].upper()}{notes[1:]}." if notes else ""
        return " ".join(part for part in (state, self.options[self.focus].detail) if part)

    def _focus(self, index: int) -> Outcome:
        if not self.options or index == self.focus:
            return Outcome()
        old, self.focus = self.focus, index
        self.showing_help = False
        return Outcome(say=self.spoken(index), redraw="focus", old=old)

    def handle(self, key: str) -> Outcome:
        count = len(self.options)
        if key in ("escape", "interrupt"):
            return Outcome(cancelled=True)
        if key == "?":
            self.showing_help = True
            return Outcome(say=t(self.language, "tui.help"), redraw="description")
        if not count:
            return Outcome()
        if key in ("down", "tab"):
            return self._focus((self.focus + 1) % count)
        if key in ("up", "backtab"):
            return self._focus((self.focus - 1) % count)
        if key == "home":
            return self._focus(0)
        if key == "end":
            return self._focus(count - 1)
        if len(key) == 1 and key in "123456789" and int(key) <= count:
            return self._focus(int(key) - 1)
        if key == "enter":
            o = self.options[self.focus]
            if o.blocked:
                return Outcome(say=t(self.language, "tui.blocked").format(label=o.label, reason=o.blocked))
            return Outcome(done=self.focus)
        return Outcome()


# ------------------------------------------------------------ rendu
def _goto(y: int) -> str:
    return f"\x1b[{y + 1};1H"


class Renderer:
    """Chaînes ANSI d'un écran `rows` x `cols`. Garde la fenêtre de défilement
    (`top`) entre deux appels : un défilement impose un redessin complet."""

    def __init__(self, style: Style, rows: int, cols: int):
        self.style = style
        self.rows = max(rows, 1)
        self.cols = max(cols, 1)
        self.top = 0

    # ---- géométrie
    def _list_top(self, model: ChoiceModel) -> int:
        top = 4 + (len(model.body) + 1 if model.body else 0)
        return top if top < self.rows else 0

    def _has_footer(self, model: ChoiceModel) -> bool:
        return self._list_top(model) + 1 + DESCRIPTION_LINES + 3 <= self.rows

    def description_rows(self, model: ChoiceModel) -> list[int]:
        if not self._has_footer(model):
            return []
        first = self.rows - 2 - DESCRIPTION_LINES
        return list(range(first, first + DESCRIPTION_LINES))

    def _capacity(self, model: ChoiceModel) -> int:
        end = self.rows - (DESCRIPTION_LINES + 3 if self._has_footer(model) else 0)
        return max(1, end - self._list_top(model))

    def _scroll(self, model: ChoiceModel) -> bool:
        """Ajuste `top` pour que le focus soit visible ; vrai si la fenêtre a bougé."""
        cap, old = self._capacity(model), self.top
        if model.focus < self.top:
            self.top = model.focus
        elif model.focus >= self.top + cap:
            self.top = model.focus - cap + 1
        return self.top != old

    def _row_of(self, model: ChoiceModel, i: int) -> int:
        return self._list_top(model) + i - self.top

    # ---- peinture
    @property
    def _bg(self) -> str | None:
        return "black" if self.style.depth else None

    def _line(self, y: int, content: str) -> str:
        erase_bg = f"\x1b[{self.style.bg_params('black')}m" if self.style.depth else ""
        return f"{_goto(y)}{erase_bg}\x1b[2K{content}"

    def _segments(self, segments: list[tuple[str, str | None, bool]], room: int | None = None) -> str:
        """[(texte, couleur, gras)] peints sur noir, coupés à `room` (la largeur par défaut)."""
        out = []
        room = self.cols if room is None else room
        for text, fg, bold in segments:
            text = text[:room]
            room -= len(text)
            if not text:
                continue
            if fg == "accent":
                out.append(self.style.accent(text))
            else:
                out.append(self.style.paint(text, fg=fg, bg=self._bg, bold=bold))
        return "".join(out)

    def _header(self, model: ChoiceModel) -> str:
        logo_text = f" steph {self.style.chevron} "  # lu pareil avec ou sans couleur
        room = self.cols - len(logo_text)
        if room < 0:
            return self._segments([(logo_text.strip(), "offwhite", True)])
        logo = self.style.logo() if self.style.depth else logo_text
        title = " " + model.title
        gap = room - len(title) - len(model.step)
        step = [(" " * gap + model.step, "gray", False)] if model.step and gap >= 1 else []
        return logo + self._segments([(title, "offwhite", True), *step], room)

    def _option(self, model: ChoiceModel, i: int, width: int) -> str:
        o = model.options[i]
        focused = i == model.focus
        mark = self.style.chevron if focused else " "
        num = str(i + 1) if i < 9 else " "
        head = f"{mark} {num}  {o.label:<{width}}"
        notes = model.notes(i)
        tail = ("  " + ", ".join(notes)) if notes else ""
        if focused:
            return self.style.selected((head + tail).ljust(self.cols)[:self.cols])  # barre pleine largeur
        label_fg = "gray" if o.blocked else "offwhite"
        tail_fg = "accent" if o.tag == "recommended" and not o.blocked else (
            "gray" if o.tag == "muted" or o.blocked else "offwhite")
        if tail_fg == "accent":
            return self._segments([(head, label_fg, False), ("  ", "offwhite", False), (tail[2:], "accent", False)])
        return self._segments([(head, label_fg, False), (tail, tail_fg, False)])

    def _label_width(self, model: ChoiceModel) -> int:
        return max((len(o.label) for o in model.options), default=0)

    def _description(self, model: ChoiceModel) -> str:
        rows = self.description_rows(model)
        if not rows:
            return ""
        text = model.description()
        wrapped = textwrap.wrap(text, self.cols) if text else []
        wrapped += [""] * len(rows)
        return "".join(self._line(y, self._segments([(line, "offwhite", False)]))
                       for y, line in zip(rows, wrapped))

    def _cursor(self, model: ChoiceModel) -> str:
        y = self._row_of(model, model.focus) if model.options else min(2, self.rows - 1)
        # attributs remis à zéro : aucune couleur ne fuit vers l'écran du shell à la sortie
        return f"{_goto(y)}\x1b[0m\x1b[?25h"

    def full(self, model: ChoiceModel) -> str:
        self._scroll(model)
        bg = f"\x1b[{self.style.bg_params('black')}m" if self.style.depth else ""
        parts = [f"\x1b[?25l{bg}\x1b[2J\x1b[H"]
        list_top = self._list_top(model)
        if list_top:
            parts.append(self._line(0, self._header(model)))
            parts.append(self._line(2, self._segments([(model.question, "offwhite", True)])))
            for k, line in enumerate(model.body):
                parts.append(self._line(4 + k, self._segments([(line, "offwhite", False)])))
        width = self._label_width(model)
        for i in range(self.top, min(len(model.options), self.top + self._capacity(model))):
            parts.append(self._line(self._row_of(model, i), self._option(model, i, width)))
        if self._has_footer(model):
            parts.append(self._description(model))
            parts.append(self._line(self.rows - 1, self._segments([(model.keys_bar, "gray", False)])))
        parts.append(self._cursor(model))
        return "".join(parts)

    def update(self, model: ChoiceModel, outcome: Outcome) -> str:
        if outcome.redraw == "description":
            return f"\x1b[?25l{self._description(model)}{self._cursor(model)}"
        if outcome.redraw == "line":
            line = self._option(model, model.focus, self._label_width(model))
            return f"\x1b[?25l{self._line(self._row_of(model, model.focus), line)}{self._cursor(model)}"
        if outcome.redraw != "focus":
            return ""
        if self._scroll(model):
            return self.full(model)
        width = self._label_width(model)
        # description d'abord, ancienne ligne, puis la nouvelle : le curseur finit sur le focus
        return "".join((
            "\x1b[?25l",
            self._description(model),
            self._line(self._row_of(model, outcome.old), self._option(model, outcome.old, width)),
            self._line(self._row_of(model, model.focus), self._option(model, model.focus, width)),
            self._cursor(model),
        ))


# ------------------------------------------------------------ boucle d'E/S
class Screen:
    """Un écran plein à la fois ; `read` rend une touche brute, `write` écrit du texte,
    `speak` dit une phrase (jamais affichée : l'écran est déjà dessiné)."""

    def __init__(self, read: Callable[[], bytes], write: Callable[[str], None],
                 size: Callable[[], tuple[int, int]], style: Style, speak: Callable[[str], None],
                 language: str = "fr"):
        self.read = read
        self.write = write
        self.size = size
        self.style = style
        self.speak = speak
        self.language = language
        self._model: ChoiceModel | None = None
        self._renderer: Renderer | None = None

    def _show(self, model: ChoiceModel) -> Renderer:
        self._model = model
        self._renderer = Renderer(self.style, *self.size())
        self.write(self._renderer.full(model))
        return self._renderer

    def redraw(self) -> None:
        """Après un redimensionnement : même écran, nouvelle taille."""
        if self._model is not None:
            top = self._renderer.top if self._renderer else 0
            renderer = Renderer(self.style, *self.size())
            renderer.top = top
            self._renderer = renderer
            self.write(renderer.full(self._model))

    def choose(self, model: ChoiceModel, intro: str = "") -> int | None:
        """Index validé, ou None (Échap, Ctrl+C). `intro` précède la première annonce :
        deux phrases séparées se couperaient l'une l'autre."""
        self._show(model)
        self.speak(f"{intro} {model.opening()}" if intro else model.opening())
        while True:
            outcome = model.handle(decode_key(self.read()))
            if outcome.say:
                self.speak(outcome.say)
            if outcome.cancelled:
                return None
            if outcome.done is not None:
                return outcome.done
            update = self._renderer.update(model, outcome)
            if update:
                self.write(update)

    def capture(self, title: str, prompt: str, step: str) -> str | None:
        """Une touche spéciale (séquence d'échappement complète), "" pour garder l'actuelle,
        None sur Ctrl+C."""
        self._show(ChoiceModel(title, prompt, [], step=step, language=self.language,
                               detail=t(self.language, "tui.capture_detail")))
        self.speak(prompt)
        seq = self.read()
        if decode_key(seq) == "interrupt":
            return None
        return seq.decode("utf-8", "replace") if len(seq) > 1 and seq.startswith(b"\x1b") else ""


@contextmanager
def session(write: Callable[[str], None]) -> Iterator[None]:
    """Écran alternatif pendant le bloc, écran du shell restauré quoi qu'il arrive."""
    write(ENTER_SCREEN)
    try:
        yield
    finally:
        write(LEAVE_SCREEN)


@contextmanager
def raw_terminal(fd: int) -> Iterator[None]:
    import termios
    import tty

    saved = termios.tcgetattr(fd)
    try:
        tty.setraw(fd, termios.TCSANOW)
        yield
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, saved)


def key_reader(fd: int) -> Callable[[], bytes]:
    """Lit le terminal et rend une touche à la fois ; fin de fichier -> EOFError."""
    pending: list[bytes] = []

    def read() -> bytes:
        while not pending:
            data = os.read(fd, 64)
            if not data:
                raise EOFError
            pending.extend(split_keys(data))
        return pending.pop(0)

    return read


def terminal_size(fd: int) -> tuple[int, int]:
    try:
        size = os.get_terminal_size(fd)
        return size.lines or 24, size.columns or 80
    except OSError:
        return 24, 80
