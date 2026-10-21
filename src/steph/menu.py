"""Menu parlé (F6) : machine à états pure, aucune E/S ici.

Le proxy pousse chaque touche via `handle()`, lit `render()` (écran complet) puis
`render_update()` (seulement ce qui a changé, curseur sur l'élément focalisé) pour
dessiner l'écran alternatif, et applique lui-même la parole (`MenuResult.say`), les
actions (`MenuResult.action`, transmises au narrateur ou à `on_ask`) et les
réglages (`MenuResult.setting`, appliqués à `cfg` puis persistés). Rendu partagé avec
`steph setup` : `tui.Renderer` (docs/tui-a11y.md).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import setup
from .config import Config
from .strings import t
from .term_style import Style
from .tui import ChoiceModel, Option, Outcome, Renderer, decode_key, split_keys  # noqa: F401  (split_keys réexporté)

UP = (b"\x1b[A", b"\x1bOA")
DOWN = (b"\x1b[B", b"\x1bOB")
LEFT = (b"\x1b[D", b"\x1bOD")
RIGHT = (b"\x1b[C", b"\x1bOC")
ENTER = b"\r"
BACKSPACE = b"\x7f"
ESCAPE = b"\x1b"

RATE_MIN, RATE_MAX = setup.RATE_MIN, setup.RATE_MAX
RATE_STEP = 0.25


@dataclass
class MenuResult:
    say: str | None = None
    action: str | None = None
    setting: tuple[str, object] | None = None
    closed: bool = False


class _Entry:
    """Un élément de menu : libellé dynamique (valeur courante incluse) et,
    selon le type, une action à l'Entrée et/ou un réglage à gauche/droite."""

    def __init__(self, label: Callable[[], str], on_enter: Callable[[], MenuResult] | None = None,
                 on_adjust: Callable[[int], MenuResult] | None = None, desc: str = ""):
        self.label = label
        self.on_enter = on_enter
        self.on_adjust = on_adjust
        self.desc = desc  # clé de strings.py : description affichée quand l'élément a le focus


class Menu:
    def __init__(self, cfg: Config, help_text: str = "", voices_dir: Path | None = None,
                 style: Style | None = None):
        self.cfg = cfg
        self.help_text = help_text
        self.style = style or Style(None)
        self.voices_dir = Path(voices_dir) if voices_dir is not None else Path(cfg.voice).parent
        self._main = self._build_main()
        self._settings = self._build_settings()
        self.stack: list[list[_Entry]] = [self._main]
        self.cursors: list[int] = [0]
        self._renderer: Renderer | None = None
        self._drawn: tuple | None = None  # (niveau, taille, focus, libellés) du dernier dessin

    # ------------------------------------------------------------ état courant
    @property
    def items(self) -> list[_Entry]:
        return self.stack[-1]

    @property
    def cursor(self) -> int:
        return self.cursors[-1]

    def _t(self, key: str) -> str:
        return t(self.cfg.language, key)

    def opening_announcement(self) -> str:
        items = self.items
        return self._t("menu.opening").format(first=items[0].label(), count=len(items))

    # ------------------------------------------------------------ niveau principal
    def _build_main(self) -> list[_Entry]:
        def action(name: str) -> Callable[[], MenuResult]:
            return lambda: MenuResult(action=name, closed=True)

        return [
            _Entry(lambda: self._t("menu.stop"), on_enter=action("stop"), desc="menu.desc.stop"),
            _Entry(lambda: self._t("menu.repeat"), on_enter=action("repeat"), desc="menu.desc.repeat"),
            _Entry(lambda: self._t("menu.details"), on_enter=action("details"), desc="menu.desc.details"),
            _Entry(lambda: self._t("menu.ask"), on_enter=action("ask"), desc="menu.desc.ask"),
            _Entry(lambda: self._t("menu.first"), on_enter=action("first"), desc="menu.desc.first"),
            _Entry(lambda: self._t("menu.last"), on_enter=action("last"), desc="menu.desc.last"),
            _Entry(lambda: self._t("menu.settings"), on_enter=self._enter_settings, desc="menu.desc.settings"),
            _Entry(lambda: self._t("menu.help"), on_enter=self._help, desc="menu.desc.help"),
            _Entry(lambda: self._t("menu.close"),
                   on_enter=lambda: MenuResult(say=self._t("menu.closed"), closed=True), desc="menu.desc.close"),
        ]

    def _help(self) -> MenuResult:
        return MenuResult(say=self.help_text or self._t("menu.no_help"))

    def _enter_settings(self) -> MenuResult:
        self.stack.append(self._settings)
        self.cursors.append(0)
        items = self.items
        return MenuResult(say=self._t("menu.settings_opening").format(first=items[0].label(), count=len(items)))

    # ------------------------------------------------------------ sous-menu réglages
    def _build_settings(self) -> list[_Entry]:
        adjust = "menu.desc.adjust"
        return [
            _Entry(self._tts_label, on_enter=lambda: self._tts_adjust(1), on_adjust=self._tts_adjust, desc=adjust),
            _Entry(self._rate_label, on_enter=lambda: self._rate_adjust(1), on_adjust=self._rate_adjust,
                   desc=adjust),
            _Entry(self._verbosity_label, on_enter=lambda: self._verbosity_adjust(1),
                   on_adjust=self._verbosity_adjust, desc=adjust),
            _Entry(self._announce_cd_label, on_enter=lambda: self._announce_cd_adjust(1),
                   on_adjust=self._announce_cd_adjust, desc=adjust),
            _Entry(self._voice_label, on_enter=lambda: self._voice_adjust(1), on_adjust=self._voice_adjust,
                   desc=adjust),
            _Entry(lambda: self._t("menu.back"), on_enter=self._back, desc="menu.desc.back"),
        ]

    def _tts_label(self) -> str:
        return self._t("menu.tts_on" if self.cfg.tts_enabled else "menu.tts_off")

    def _tts_adjust(self, _direction: int) -> MenuResult:
        self.cfg.tts_enabled = not self.cfg.tts_enabled
        text = self._t("menu.tts_on_say" if self.cfg.tts_enabled else "menu.tts_off_say")
        return MenuResult(say=text, setting=("tts_enabled", self.cfg.tts_enabled))

    def _rate_label(self) -> str:
        return self._t("menu.rate").format(rate=setup._number(self.cfg.speech_rate, self.cfg.language))

    def _rate_adjust(self, direction: int) -> MenuResult:
        rate = round(min(RATE_MAX, max(RATE_MIN, self.cfg.speech_rate + direction * RATE_STEP)), 2)
        self.cfg.speech_rate = rate
        return MenuResult(say=self._t("menu.rate_say").format(rate=setup._number(rate, self.cfg.language)),
                          setting=("speech_rate", rate))

    def _verbosity_label(self) -> str:
        return self._t("menu.verbosity").format(level=self._t(f"menu.verbosity.{self.cfg.verbosity}"))

    def _verbosity_adjust(self, direction: int) -> MenuResult:
        level = min(2, max(0, self.cfg.verbosity + direction))
        self.cfg.verbosity = level
        return MenuResult(say=self._t("menu.verbosity_say").format(level=self._t(f"menu.verbosity.{level}")),
                          setting=("verbosity", level))

    def _announce_cd_label(self) -> str:
        return self._t("menu.cd").format(state=self._t("menu.yes" if self.cfg.announce_cd else "menu.no"))

    def _announce_cd_adjust(self, _direction: int) -> MenuResult:
        self.cfg.announce_cd = not self.cfg.announce_cd
        text = self._t("menu.cd_on" if self.cfg.announce_cd else "menu.cd_off")
        return MenuResult(say=text, setting=("announce_cd", self.cfg.announce_cd))

    def _voices(self) -> list[Path]:
        return setup.list_voices(self.voices_dir)

    def _voice_index(self, voices: list[Path]) -> int:
        for i, v in enumerate(voices):
            if str(v) == self.cfg.voice:
                return i
        return 0

    def _voice_label(self) -> str:
        voices = self._voices()
        if len(voices) <= 1:
            return self._t("menu.voice_single")
        return self._t("menu.voice").format(name=setup.voice_label(voices[self._voice_index(voices)]))

    def _voice_adjust(self, direction: int) -> MenuResult:
        voices = self._voices()
        if len(voices) <= 1:
            return MenuResult(say=self._t("menu.voice_single_say"))
        idx = (self._voice_index(voices) + direction) % len(voices)
        path = str(voices[idx])
        self.cfg.voice = path
        return MenuResult(say=self._t("menu.voice_say").format(name=setup.voice_label(voices[idx])),
                          setting=("voice", path))

    # ------------------------------------------------------------ navigation
    def _back(self) -> MenuResult:
        if len(self.stack) == 1:
            return MenuResult()
        self.stack.pop()
        self.cursors.pop()
        return MenuResult(say=self.items[self.cursor].label())

    def _move(self, step: int) -> MenuResult:
        return self._focus((self.cursor + step) % len(self.items))

    def _focus(self, index: int) -> MenuResult:
        if index == self.cursor:
            return MenuResult()
        self.cursors[-1] = index
        return MenuResult(say=self.items[index].label())

    def handle(self, key: bytes) -> MenuResult:
        if key == ESCAPE or key == self.cfg.key_menu.encode():
            return MenuResult(say=self._t("menu.closed"), closed=True)
        name = decode_key(key)
        if name in ("up", "backtab"):
            return self._move(-1)
        if name in ("down", "tab"):
            return self._move(1)
        if name == "home":
            return self._focus(0)
        if name == "end":
            return self._focus(len(self.items) - 1)
        if len(name) == 1 and name in "123456789" and int(name) <= len(self.items):
            return self._focus(int(name) - 1)
        if name == "?":
            return self._help()
        if key == ENTER:
            entry = self.items[self.cursor]
            return entry.on_enter() if entry.on_enter else MenuResult()
        if key in LEFT:
            entry = self.items[self.cursor]
            return entry.on_adjust(-1) if entry.on_adjust else self._back()
        if key in RIGHT:
            entry = self.items[self.cursor]
            return entry.on_adjust(1) if entry.on_adjust else MenuResult()
        if key == BACKSPACE:
            return self._back()
        return MenuResult()

    # ------------------------------------------------------------ rendu
    def _model(self) -> ChoiceModel:
        main = len(self.stack) == 1
        options = [Option(e.label(), detail=self._t(e.desc) if e.desc else "") for e in self.items]
        return ChoiceModel(self._t("menu.title"), self._t("menu.actions" if main else "menu.settings"), options,
                           focus=self.cursor, language=self.cfg.language, keys_bar=self._t("menu.help_line"))

    def _state(self, rows: int, cols: int, model: ChoiceModel) -> tuple:
        return (len(self.stack), (rows, cols), self.cursor, tuple(o.label for o in model.options))

    def render(self, rows: int, cols: int) -> bytes:
        """Écran complet : ouverture, changement de niveau, redimensionnement."""
        model = self._model()
        self._renderer = Renderer(self.style, rows, cols)
        self._drawn = self._state(rows, cols, model)
        return self._renderer.full(model).encode()

    def render_update(self, rows: int, cols: int) -> bytes:
        """Seulement ce qui a changé depuis le dernier dessin ; b"" si rien."""
        model = self._model()
        state = self._state(rows, cols, model)
        drawn, self._drawn = self._drawn, state
        if drawn is None or self._renderer is None or drawn[:2] != state[:2]:
            return self.render(rows, cols)
        if drawn[2] != state[2]:
            return self._renderer.update(model, Outcome(redraw="focus", old=drawn[2])).encode()
        if drawn[3] != state[3]:
            return self._renderer.update(model, Outcome(redraw="line")).encode()
        return b""
