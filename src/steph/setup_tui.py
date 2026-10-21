"""`steph setup` plein écran (M6) : mêmes questions que le mode ligne, une par écran.

`collect` ne fait que recueillir les choix : aucun téléchargement ni écriture pendant que
l'écran alternatif est affiché. `setup.apply_plan` les applique ensuite, sur l'écran du
shell, où la progression des téléchargements s'écrit en lignes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import setup
from .catalog import ModelChoice
from .config import Config
from .strings import t
from .tui import ChoiceModel, Option, Screen

RATE_STEP = 0.25


@dataclass
class Plan:
    keep_existing: bool = False
    model: ModelChoice | None = None  # à acquérir avant d'écrire model et llm_profile
    voice: ModelChoice | None = None  # voix du catalogue, à acquérir avant d'écrire voice
    answers: dict = field(default_factory=dict)  # écrit tel quel


def _size(size_mb: int, lang: str) -> str:
    grouped = f"{size_mb:,}"
    return grouped.replace(",", " ") if lang == "fr" else grouped


def catalog_option(m: ModelChoice, current_path: str, lang: str) -> Option:
    notes, tag = [], ""
    if m.recommended:
        notes.append(t(lang, "setup.model_recommended"))
        tag = "recommended"
    if m.not_recommended:
        notes.append(t(lang, "setup.model_not_recommended"))
        tag = "muted"
    if m.path == current_path:
        notes.append(t(lang, "tui.state_current"))
    present = Path(m.path).is_file()
    blocked = ""
    # un fichier déjà présent tourne déjà : les blocages ne visent qu'un téléchargement (B6)
    if not present and not m.available:
        blocked = t(lang, "setup.model_unavailable")
    elif not present and m.out_of_scope:
        blocked = t(lang, "setup.model_out_of_scope")
    where = t(lang, "tui.installed" if present else "tui.to_download")
    estimate = setup.first_summary_note(m, lang)
    detail = f"{t(lang, 'setup.model_size').format(size=_size(m.size_mb, lang))}, {where}"
    detail += f", {estimate}." if estimate else "."
    return Option(m.label, notes=tuple(notes), tag=tag, blocked=blocked, detail=detail)


def rate_values(current: float) -> list[float]:
    count = round((setup.RATE_MAX - setup.RATE_MIN) / RATE_STEP) + 1
    values = [round(setup.RATE_MIN + i * RATE_STEP, 2) for i in range(count)]
    return values if current in values else sorted([*values, current])


def collect(cfg: Config, screen: Screen, config_path: Path, config_exists: bool, models: list[ModelChoice],
            voices_catalog: list[ModelChoice], voices_dir: Path,
            model_note: list[str] | tuple[str, ...] = ()) -> Plan | None:
    """Plan de configuration, ou None si l'utilisateur quitte (Échap, Ctrl+C, Quitter).

    `model_note` : verdict de vitesse (B10), une phrase par ligne, affiché et dit avec la question du modèle."""
    lang = cfg.language

    def say(key: str) -> str:
        return t(lang, key)

    title = say("tui.title")
    use_models = bool(models) and any(setup._acquirable(m) for m in models)
    use_catalog = bool(voices_catalog) and any(setup._acquirable(v) for v in voices_catalog)
    local_voices = [] if use_catalog else setup.list_voices(voices_dir)
    steps = [name for name, shown in (("model", use_models), ("voice", use_catalog or bool(local_voices)),
                                      ("rate", True), ("verbosity", True), ("keys", True), ("confirm", True))
             if shown]
    intro = [say("tui.screen_open")]

    def ask(step: str | None, question: str, options: list[Option], focus: int = 0,
            body: tuple[str, ...] = ()) -> int | None:
        label = say("tui.step").format(n=steps.index(step) + 1, total=len(steps)) if step else ""
        model = ChoiceModel(title, question, options, focus=focus, step=label, language=lang, body=body)
        text = intro.pop() if intro else ""
        return screen.choose(model, intro=text)

    def current(flag: bool) -> tuple[str, ...]:
        return (say("tui.state_current"),) if flag else ()

    plan = Plan()
    summary: list[str] = []
    config_text = config_path.read_text() if config_exists and config_path.exists() else ""

    if config_exists:
        detail = say("tui.existing_detail").format(path=config_path)
        n = ask(None, say("tui.existing"), [Option(say("tui.existing_edit"), detail=detail),
                                             Option(say("tui.existing_keep"), detail=detail)], focus=1)
        if n is None:
            return None
        if n == 1:
            return Plan(keep_existing=True)

    if use_models:
        n = ask("model", say("tui.model"), [catalog_option(m, cfg.model, lang) for m in models],
                focus=setup._default_choice(models, setup.chosen_model(cfg, config_text)) - 1,
                # sans point final : la lecture joint les lignes par « . »
                body=tuple(line.rstrip(".") for line in model_note))
        if n is None:
            return None
        plan.model = models[n]
        summary.append(say("tui.summary_model").format(value=models[n].label))

    if use_catalog:
        n = ask("voice", say("tui.voice"), [catalog_option(v, cfg.voice, lang) for v in voices_catalog],
                focus=setup._default_choice(voices_catalog, cfg.voice) - 1)
        if n is None:
            return None
        plan.voice = voices_catalog[n]
        summary.append(say("tui.summary_voice").format(value=voices_catalog[n].label))
    elif local_voices:
        focus = next((i for i, v in enumerate(local_voices) if str(v) == cfg.voice), 0)
        n = ask("voice", say("tui.voice"),
                [Option(setup.voice_label(v), notes=current(str(v) == cfg.voice)) for v in local_voices], focus)
        if n is None:
            return None
        plan.answers["voice"] = str(local_voices[n])
        summary.append(say("tui.summary_voice").format(value=setup.voice_label(local_voices[n])))

    rates = rate_values(cfg.speech_rate)
    rate_detail = say("tui.rate_detail")
    n = ask("rate", say("tui.rate"),
            [Option(setup._number(r, lang),
                    notes=((say("tui.rate_normal"),) if r == 1 else ()) + current(r == cfg.speech_rate),
                    detail=rate_detail) for r in rates],
            rates.index(cfg.speech_rate))
    if n is None:
        return None
    plan.answers["speech_rate"] = rates[n]
    summary.append(say("tui.summary_rate").format(value=setup._number(rates[n], lang)))

    level = min(2, max(0, cfg.verbosity))
    n = ask("verbosity", say("tui.verbosity"),
            [Option(say(f"tui.verbosity.{i}"), notes=current(i == cfg.verbosity)) for i in range(3)], level)
    if n is None:
        return None
    plan.answers["verbosity"] = n
    summary.append(say("tui.summary_verbosity").format(value=say(f"tui.verbosity.{n}")))

    n = ask("keys", say("tui.keys"), [Option(say("tui.keys_keep"), detail=say("tui.keys_keep_detail")),
                                       Option(say("tui.keys_choose"), detail=say("tui.keys_choose_detail"))])
    if n is None:
        return None
    changed = 0
    if n == 1:
        step = say("tui.step").format(n=steps.index("keys") + 1, total=len(steps))
        for name in setup.KEY_ACTIONS:
            label = say("setup.key." + name.removeprefix("key_"))
            seq = screen.capture(title, say("setup.press_key").format(label=label), step)
            if seq is None:
                return None
            if seq:
                plan.answers[name] = seq
                changed += 1
    summary.append(say("tui.summary_keys_changed").format(count=changed) if changed
                   else say("tui.summary_keys_kept"))

    n = ask("confirm", say("tui.confirm"), [Option(say("tui.save")), Option(say("tui.quit"))],
            body=tuple(summary))
    return plan if n == 0 else None
