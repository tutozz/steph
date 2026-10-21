"""`steph setup` : assistant de configuration, au clavier et à voix haute.

Écrit ~/.config/steph/config.toml en ne touchant que les clés demandées : les
autres réglages, les commentaires et les tables ([rules]…) restent en place.
"""

from __future__ import annotations

import json
import re
import sys
import tomllib
from pathlib import Path
from typing import Callable

from . import speed
from .catalog import ModelChoice, detect_machine, detect_tier, llm_choices, load_catalog, tts_choices
from .config import CONFIG_PATH, DATA_DIR, Config, load_config
from .strings import t
from .term_style import Style, for_stream

# bornes partagées avec le menu F6 (menu.py les importe d'ici)
RATE_MIN, RATE_MAX = 0.5, 3.0
YES = ("o", "oui", "y", "yes")
KEY_ACTIONS = ("key_menu", "key_ask", "key_stop", "key_repeat", "key_details",
               "key_line_first", "key_line_prev", "key_line_next", "key_line_last")
FIRST_RUN_MARKER = DATA_DIR / "setup-offered"


# ------------------------------------------------------------ logique pure
def format_toml_value(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    # les échappements JSON (\u001b, \", \\) sont des échappements TOML valides
    return json.dumps(str(value), ensure_ascii=False)


def update_config_text(text: str, answers: dict) -> str:
    """Remplace ou ajoute chaque clé de `answers` au niveau racine du TOML."""
    lines = text.splitlines()
    first_table = next((i for i, line in enumerate(lines) if re.match(r"\s*\[", line)), len(lines))
    for key, value in answers.items():
        new_line = f"{key} = {format_toml_value(value)}"
        pattern = re.compile(rf"\s*{re.escape(key)}\s*=")
        for i in range(first_table):
            if pattern.match(lines[i]):
                lines[i] = new_line
                break
        else:
            at = first_table
            # garder la ligne vide qui sépare la racine de la première table
            while at > 0 and at < len(lines) and not lines[at - 1].strip():
                at -= 1
            lines.insert(at, new_line)
            first_table += 1
    return "\n".join(lines) + "\n"


def save_settings(config_path: Path, answers: dict) -> None:
    """Applique `answers` à `config_path` (menu F6) : mêmes garanties que
    `update_config_text`, rien d'autre n'est touché."""
    existing = config_path.read_text() if config_path.exists() else ""
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(update_config_text(existing, answers))


def parse_rate(answer: str, default: float) -> float | None:
    answer = answer.strip().replace(",", ".")
    if not answer:
        return default
    try:
        rate = float(answer)
    except ValueError:
        return None
    return rate if RATE_MIN <= rate <= RATE_MAX else None


def parse_choice(answer: str, count: int, default: int) -> int | None:
    """Choix numéroté de 1 à `count` ; réponse vide = `default`."""
    answer = answer.strip()
    if not answer:
        return default
    return int(answer) if answer.isdigit() and 1 <= int(answer) <= count else None


def list_voices(voices_dir: Path) -> list[Path]:
    return sorted(voices_dir.glob("*.onnx")) if voices_dir.is_dir() else []


def voice_label(path: Path) -> str:
    # fr_FR-siwis-medium -> « siwis medium »
    return " ".join(path.stem.split("-")[1:]) or path.stem


def _number(x: float, language: str = "fr") -> str:
    return f"{x:g}".replace(".", ",") if language == "fr" else f"{x:g}"


def _model_listing(models: list[ModelChoice], language: str, style: Style | None = None) -> str:
    style = style or Style(None)
    parts = []
    for i, m in enumerate(models, 1):
        notes = [t(language, "setup.model_size").format(size=m.size_mb)]
        estimate = first_summary_note(m, language)
        if estimate:
            notes.append(estimate)
        if m.recommended:
            notes.append(style.accent(t(language, "setup.model_recommended")))
        if m.not_recommended:
            notes.append(style.muted(t(language, "setup.model_not_recommended")))
        present = Path(m.path).is_file()
        # un fichier déjà présent tourne déjà : les balises de blocage ne s'appliquent qu'à un téléchargement
        if not present and not m.available:
            notes.append(style.muted(t(language, "setup.model_unavailable")))
        elif not present and m.out_of_scope:
            notes.append(style.muted(t(language, "setup.model_out_of_scope")))
        parts.append(f"{i} {m.label}, {', '.join(notes)}")
    return ", ".join(parts)


def first_summary_note(m: ModelChoice, language: str) -> str:
    """« premier résumé en 2,7 secondes environ », ou vide si la vitesse du modèle est inconnue."""
    p90 = speed.first_summary_p90(m, m.prompt_tokens_per_sec)
    if p90 is None:
        return ""
    return t(language, "setup.model_first_summary").format(seconds=speed.seconds_phrase(p90, language))


def _model_answers(choice: ModelChoice) -> dict:
    answers = {"model": choice.path, "llm_profile": choice.profile}
    if choice.prompt_tokens_per_sec > 0:
        answers["llm_prompt_tokens_per_sec"] = choice.prompt_tokens_per_sec
    return answers


def _acquirable(m: ModelChoice) -> bool:
    """Sélectionnable : déjà sur le disque, ou publié et compatible avec cette machine (B6)."""
    return Path(m.path).is_file() or (m.available and not m.out_of_scope)


def _default_choice(items: list[ModelChoice], current_path: str) -> int:
    return (next((i for i, m in enumerate(items, 1) if m.path == current_path), None)
            or next((i for i, m in enumerate(items, 1) if m.recommended and _acquirable(m)), None)
            or next(i for i, m in enumerate(items, 1) if _acquirable(m)))


def chosen_model(cfg: Config, config_text: str) -> str:
    """Le modèle choisi par la personne (config.toml ou STEPH_MODEL), vide s'il n'est que le
    défaut intégré : au premier setup, Entrée prend alors le choix recommandé par la vitesse (B10)."""
    import os
    try:
        in_file = "model" in tomllib.loads(config_text)
    except tomllib.TOMLDecodeError:
        in_file = False
    return cfg.model if in_file or "STEPH_MODEL" in os.environ else ""


def _choice_parser(items: list[ModelChoice], default: int, lang: str, say):
    """Comme parse_choice, mais refuse (avec la raison) un choix bloqué (B6)."""
    def parse(answer: str):
        n = parse_choice(answer, len(items), default)
        if n is None:
            return None
        m = items[n - 1]
        if _acquirable(m):
            return n
        reason = t(lang, "setup.model_unavailable" if not m.available else "setup.model_out_of_scope")
        say(t(lang, "setup.model_blocked").format(label=m.label, reason=reason))
        return None
    return parse


def _download_llm(choice: ModelChoice, path: Path, lang: str) -> bool:
    from . import fetch
    url = f"https://huggingface.co/{choice.source}/resolve/main/{path.name}"
    return fetch.download(url, path, choice.label, lang, speak=True, poll=1.0, retries=3,
                          sha256=choice.sha256 or None) == 0


def _download_voice(choice: ModelChoice, path: Path) -> bool:
    # les voix Piper ont besoin de deux fichiers (.onnx + .onnx.json) : le module officiel
    # les télécharge ensemble, plutôt que de reconstruire ses deux URL ici
    from piper.download_voices import download_voice
    try:
        download_voice(path.stem, path.parent)
    except Exception:
        return False
    return path.is_file()


def _ensure_downloaded(choice: ModelChoice, lang: str) -> bool:
    """Télécharge le fichier choisi (jamais appelé si déjà présent : voir `_run_setup`)."""
    path = Path(choice.path)
    if not choice.available or not choice.source:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    return _download_voice(choice, path) if path.suffix == ".onnx" else _download_llm(choice, path, lang)


def _acquire(choice: ModelChoice, download: Callable[[ModelChoice], bool], say, lang: str) -> bool:
    """Vrai si le fichier est prêt (déjà présent, ou téléchargé à l'instant)."""
    if Path(choice.path).is_file() or download(choice):
        return True
    say(t(lang, "setup.download_failed").format(label=choice.label))
    return False


# ------------------------------------------------------------ déroulé
def run_setup(cfg: Config, config_path: Path, ask: Callable[[str], str], say: Callable[[str], None],
              voices_dir: Path, capture_key: Callable[[], str], models: list[ModelChoice] | None = None,
              voices: list[ModelChoice] | None = None,
              download: Callable[[ModelChoice], bool] | None = None, style: Style | None = None,
              model_intro: str = "") -> int:
    """`ask` lève EOFError en fin de saisie : la configuration est alors abandonnée,
    jamais complétée par les valeurs par défaut.

    `models`/`voices` : catalogue B4 (`catalog.llm_choices`/`tts_choices`). Sans `voices`
    (None ou vide), la question de la voix retombe sur `list_voices(voices_dir)` (fichiers
    déjà présents), comme avant B6. `download` : injecté par les tests ; en production,
    `_ensure_downloaded` (steph.fetch pour un GGUF, piper.download_voices pour une voix).
    `model_intro` : verdict de vitesse (B10), dit juste avant la question du modèle."""
    lang = cfg.language
    try:
        return _run_setup(cfg, config_path, ask, say, voices_dir, capture_key, models or [], voices or [], lang,
                          download, style or Style(None), model_intro)
    except EOFError:
        say(t(lang, "setup.aborted"))
        return 1


def _run_setup(cfg, config_path, ask, say, voices_dir, capture_key, models, voices_catalog, lang,
               download=None, style: Style = Style(None), model_intro: str = "") -> int:
    def question(prompt: str, parse, hint: str):
        say(prompt)
        while True:
            value = parse(ask("> "))
            if value is not None:
                return value
            say(t(lang, "setup.retry").format(hint=hint))

    def range_hint(high: int) -> str:
        return t(lang, "setup.hint_range").format(low=1, high=high)

    existing = config_path.read_text() if config_path.exists() else ""
    if config_path.exists():
        say(t(lang, "setup.existing").format(path=config_path))
        if ask("> ").strip().lower() not in YES:
            say(t(lang, "setup.unchanged"))
            return 0

    answers: dict = {}
    do_download = download or (lambda choice: _ensure_downloaded(choice, lang))

    def acquire(choice: ModelChoice) -> bool:
        return _acquire(choice, do_download, say, lang)

    # un catalogue existe mais rien n'y est sélectionnable (tout est bloqué) : pas de question,
    # comme sans catalogue - jamais de boucle infinie sur un choix impossible
    if models and any(_acquirable(m) for m in models):
        default = _default_choice(models, chosen_model(cfg, existing))
        if model_intro:
            say(model_intro)
        n = question(t(lang, "setup.model").format(listing=_model_listing(models, lang, style), default=default),
                     _choice_parser(models, default, lang, say), range_hint(len(models)))
        if acquire(models[n - 1]):
            answers.update(_model_answers(models[n - 1]))

    if voices_catalog and any(_acquirable(v) for v in voices_catalog):
        default = _default_choice(voices_catalog, cfg.voice)
        n = question(t(lang, "setup.voice_catalog").format(listing=_model_listing(voices_catalog, lang, style),
                                                            default=default),
                     _choice_parser(voices_catalog, default, lang, say), range_hint(len(voices_catalog)))
        if acquire(voices_catalog[n - 1]):
            answers["voice"] = voices_catalog[n - 1].path
    else:
        voices = list_voices(voices_dir)
        if voices:
            current = next((i for i, v in enumerate(voices, 1) if str(v) == cfg.voice), 1)
            listing = ", ".join(f"{i} {voice_label(v)}" for i, v in enumerate(voices, 1))
            n = question(t(lang, "setup.voice").format(listing=listing, current=current),
                         lambda a: parse_choice(a, len(voices), current), range_hint(len(voices)))
            answers["voice"] = str(voices[n - 1])

    low, high = _number(RATE_MIN, lang), _number(RATE_MAX, lang)
    answers["speech_rate"] = question(
        t(lang, "setup.rate").format(low=low, high=high, current=_number(cfg.speech_rate, lang)),
        lambda a: parse_rate(a, cfg.speech_rate), t(lang, "setup.hint_rate").format(low=low, high=high))

    answers["verbosity"] = question(
        t(lang, "setup.verbosity").format(current=cfg.verbosity),
        lambda a: cfg.verbosity if not a.strip() else (int(a) if a.strip() in ("0", "1", "2") else None),
        t(lang, "setup.hint_range").format(low=0, high=2))

    keys = question(t(lang, "setup.keys"), lambda a: parse_choice(a, 2, 1), range_hint(2))
    if keys == 2:
        for name in KEY_ACTIONS:
            say(t(lang, "setup.press_key").format(label=t(lang, "setup.key." + name.removeprefix("key_"))))
            seq = capture_key()
            if seq:
                answers[name] = seq
            else:
                say(t(lang, "setup.key_kept"))

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(update_config_text(existing, answers))
    say(style.accent(t(lang, "setup.saved").format(path=config_path)))
    return 0


def apply_plan(plan, cfg: Config, config_path: Path, say: Callable[[str], None],
               download: Callable[[ModelChoice], bool] | None = None, style: Style | None = None) -> int:
    """Applique un `setup_tui.Plan` après la sortie du plein écran : téléchargements en
    lignes sur l'écran du shell, puis écriture de config.toml (mêmes garanties que le mode ligne)."""
    lang = cfg.language
    style = style or Style(None)
    if plan.keep_existing:
        say(t(lang, "setup.unchanged"))
        return 0
    do_download = download or (lambda choice: _ensure_downloaded(choice, lang))
    answers: dict = {}
    if plan.model is not None and _acquire(plan.model, do_download, say, lang):
        answers.update(_model_answers(plan.model))
    if plan.voice is not None and _acquire(plan.voice, do_download, say, lang):
        answers["voice"] = plan.voice.path
    answers.update(plan.answers)
    existing = config_path.read_text() if config_path.exists() else ""
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(update_config_text(existing, answers))
    say(style.accent(t(lang, "setup.saved").format(path=config_path)))
    return 0


# clés écrites par l'installeur (catalog adopt) : elles ne disent rien des choix de l'utilisateur
INSTALLER_KEYS = {"model", "llm_profile", "llm_prompt_tokens_per_sec"}


def _user_configured(config_path: Path) -> bool:
    if not config_path.exists():
        return False
    import tomllib
    try:
        keys = set(tomllib.loads(config_path.read_text()))
    except tomllib.TOMLDecodeError:
        return True
    return not keys <= INSTALLER_KEYS or not keys


def should_run_first_setup(config_path: Path, marker: Path, ask: Callable[[str], str], interactive: bool,
                           language: str = "fr") -> bool:
    """Proposé une seule fois, au premier `steph` sans réglage de l'utilisateur ; refusable."""
    if _user_configured(config_path) or marker.exists() or not interactive:
        return False
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.touch()
    return ask(t(language, "setup.first_run")).strip().lower() in YES


# ------------------------------------------------------------ I/O réelles
def open_tty():
    """Le terminal de contrôle, (lecture, écriture), ou None (ssh sans -t, CI).

    Sous `curl | sh`, stdin est le tuyau du script : les réponses se lisent ici.
    Deux flux : un terminal n'est pas positionnable, « r+ » en mode texte échoue."""
    try:
        inp = open("/dev/tty", encoding="utf-8", errors="replace")
    except OSError:
        return None
    try:
        return inp, open("/dev/tty", "w", encoding="utf-8")
    except OSError:
        inp.close()
        return None


class TtyPrompter:
    """Pose la question sur `stream` et lit la réponse ; fin de fichier -> EOFError."""

    def __init__(self, inp, out=None):
        self.inp = inp
        self.out = out or inp

    def ask(self, prompt: str) -> str:
        self.out.write(prompt)
        self.out.flush()
        line = self.inp.readline()
        if not line:
            raise EOFError
        return line.rstrip("\r\n")


def capture_key_from_tty(fd: int) -> str:
    """Lit une touche brute (séquence d'échappement complète) sur le terminal."""
    import os
    import select
    import termios
    import tty

    saved = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        data = os.read(fd, 16)
        # le reste d'une séquence (ESC [ 1 9 ~) arrive dans la foulée
        while select.select([fd], [], [], 0.05)[0]:
            data += os.read(fd, 16)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, saved)
    seq = data.decode(errors="replace")
    # une lettre ou Échap seule deviendrait intapable dans le shell : on ne garde
    # que les touches spéciales (séquences d'échappement complètes)
    return seq if len(seq) > 1 and seq.startswith("\x1b") else ""


class _Voice:
    """Affiche et dit chaque message ; muet si la synthèse est indisponible."""

    def __init__(self, cfg: Config):
        self.speaker = None
        try:
            from .tts import Speaker
            self.speaker = Speaker(cfg) if cfg.tts_enabled else None
        except Exception:
            self.speaker = None

    def say(self, text: str) -> None:
        print(text, flush=True)
        if self.speaker:
            from .textproc import strip_ansi
            self.speaker.say(strip_ansi(text))

    def speak(self, text: str) -> None:
        """Dit sans afficher : en plein écran, le texte est déjà dessiné."""
        if self.speaker:
            self.speaker.say(text)

    def close(self) -> None:
        if not self.speaker:
            return
        import time
        time.sleep(0.2)
        while self.speaker.speaking.is_set() or not self.speaker._q.empty():
            time.sleep(0.05)
        self.speaker.close()


def _setup_models(cfg: Config) -> list[ModelChoice]:
    """Tout le catalogue LLM (B6 télécharge ce qui manque au moment du choix)."""
    catalog = load_catalog()
    if not catalog:
        return []
    return llm_choices(catalog, Path(cfg.model).parent, detect_machine())


def _setup_llm(cfg: Config, say: Callable[[str], None]) -> tuple[list[ModelChoice], list[str]]:
    """Catalogue LLM classé par la vitesse de cette machine (B10), et le verdict à dire, phrase par phrase.

    Mesure avec un modèle déjà sur le disque ; sans modèle, estimation d'après le matériel."""
    models = _setup_models(cfg)
    if not models:
        return [], []
    machine = detect_machine()
    reference = speed.reference_model(models)
    measured = None
    if reference is not None:
        say(t(cfg.language, "setup.speed_measuring"))
        measured = speed.measure_prompt_speed(load_config(apply_profile=True), reference.path)
    verdict = speed.assess(models, reference, measured, gpu=detect_tier(load_catalog(), machine) == "GPU")
    return speed.apply(models, verdict), speed.message_lines(verdict, cfg.language)


def _setup_voices(cfg: Config) -> list[ModelChoice]:
    """Tout le catalogue de voix TTS (B6) ; vide -> repli sur les voix déjà présentes."""
    catalog = load_catalog()
    if not catalog:
        return []
    return tts_choices(catalog, Path(cfg.voice).parent, detect_machine())


def _tty_mode(cfg: Config, tty_in, tty_out) -> tuple[str, str, str | None]:
    """(mode, raison, lecteur d'écran détecté) ; voir docs/tui-a11y.md."""
    import os

    from . import tui

    found: list[str] = []

    def reader() -> str | None:
        name = tui.screen_reader_active()
        if name:
            found.append(name)
        return name

    isatty = tty_in.isatty() and tty_out.isatty()
    mode, reason = tui.ui_mode(cfg.ui, os.environ, isatty, reader)
    return mode, reason, (found[0] if found else None)


def _main_tui(cfg: Config, config_path: Path, tty_in, tty_out, voice: "_Voice") -> int:
    import signal

    from . import setup_tui, tui

    def write(text: str) -> None:
        tty_out.write(text)
        tty_out.flush()

    style = for_stream(tty_out)
    # catalogue, matériel et mesure de vitesse avant le plein écran : quelques secondes, dites en ligne
    (models, note), voices = _setup_llm(cfg, voice.say), _setup_voices(cfg)
    screen = tui.Screen(tui.key_reader(tty_in.fileno()), write, lambda: tui.terminal_size(tty_out.fileno()),
                        style, voice.speak, cfg.language)
    previous = signal.signal(signal.SIGWINCH, lambda *_: screen.redraw())
    try:
        with tui.raw_terminal(tty_in.fileno()), tui.session(write):
            plan = setup_tui.collect(cfg, screen, config_path, config_path.exists(), models, voices,
                                     Path(cfg.voice).parent, model_note=note)
    except EOFError:
        plan = None
    finally:
        signal.signal(signal.SIGWINCH, previous)
    if plan is None:
        voice.say(t(cfg.language, "setup.aborted"))
        return 1
    return apply_plan(plan, cfg, config_path, voice.say, style=style)


def main(config_path: Path = CONFIG_PATH) -> int:
    cfg = load_config()
    tty = open_tty()
    if tty is None:
        print(t(cfg.language, "setup.no_tty"), flush=True)
        return 1
    tty_in, tty_out = tty
    voice = _Voice(cfg)
    try:
        mode, reason, reader = _tty_mode(cfg, tty_in, tty_out)
        if mode == "tui":
            return _main_tui(cfg, config_path, tty_in, tty_out, voice)
        prompter = TtyPrompter(tty_in, tty_out)
        style = for_stream(sys.stdout)
        if reason == "screen_reader":
            voice.say(t(cfg.language, "tui.line_fallback").format(name=reader))
        elif style.depth:
            # logo affiché seulement (jamais dit par la voix) : une ligne, un seul mot lu
            print(style.logo(), flush=True)
        models, note = _setup_llm(cfg, voice.say)
        return run_setup(cfg, config_path, ask=prompter.ask, say=voice.say,
                         voices_dir=Path(cfg.voice).parent,
                         capture_key=lambda: capture_key_from_tty(tty_in.fileno()),
                         models=models, voices=_setup_voices(cfg), style=style, model_intro=" ".join(note))
    except KeyboardInterrupt:
        print()
        voice.say(t(cfg.language, "setup.aborted"))
        return 1
    finally:
        voice.close()
        tty_in.close()
        tty_out.close()


def first_run(config_path: Path = CONFIG_PATH, marker: Path = FIRST_RUN_MARKER) -> None:
    """Appelé par `steph` avant d'ouvrir le shell. Sans terminal, rien n'est
    proposé ni marqué : la question reviendra au prochain lancement interactif."""
    if config_path.exists() or marker.exists() or not sys.stdin.isatty():
        return
    cfg = load_config()
    voice = _Voice(cfg)
    prompter = TtyPrompter(sys.stdin, sys.stdout)

    def ask(prompt: str) -> str:
        voice.say(prompt)
        try:
            return prompter.ask("> ")
        except (EOFError, KeyboardInterrupt):
            print()
            return ""

    try:
        accepted = should_run_first_setup(config_path, marker, ask=ask, interactive=True, language=cfg.language)
    finally:
        voice.close()
    if accepted:
        main(config_path)
