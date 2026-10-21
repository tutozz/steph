"""`steph uninstall` : retire ce que l'installation a ajouté.

Supprime le dossier de données (modèles, voix, clone `src` et son llama.cpp),
la configuration, le dossier d'exécution, puis la commande installée par
`uv tool`. Ne touche ni à uv ni à un llama.cpp Homebrew : d'autres outils
peuvent s'en servir. L'installeur ne modifie aucun fichier de démarrage du shell.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable

from .setup import YES, TtyPrompter, open_tty
from .strings import t
from .term_style import Style, for_stream


def _size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file() and not p.is_symlink())


def _human(n: int, language: str) -> str:
    for unit, factor in (("G", 1 << 30), ("M", 1 << 20), ("k", 1 << 10)):
        if n >= factor:
            value = f"{n / factor:.1f}"
            if language == "fr":
                value = value.replace(".", ",")
            return f"{value} {unit}{'o' if language == 'fr' else 'B'}"
    return f"{n} {'o' if language == 'fr' else 'B'}"


def find_uv() -> str | None:
    import os

    local_bin = str(Path(os.environ.get("HOME", Path.home())) / ".local" / "bin")
    return shutil.which("uv") or shutil.which("uv", path=local_bin)


def onnxruntime_telemetry_dir() -> Path:
    """Cache local créé par onnxruntime (Piper) : identifiant d'appareil et file d'attente
    de télémétrie (T1). Partagé avec tout autre outil basé sur onnxruntime sur cette
    machine ; steph ne le crée plus depuis la désactivation dans tts.py, mais un reste
    d'avant cette correction peut traîner."""
    import os

    if sys.platform == "darwin":
        base = Path(os.environ.get("HOME", str(Path.home()))) / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", str(Path(os.environ.get("HOME", str(Path.home()))) / ".cache")))
    return base / "Microsoft" / "DeveloperTools" / ".onnxruntime"


def _remove(path: Path) -> None:
    # deux passes : Finder ou Spotlight peuvent recréer un .DS_Store pendant la première
    for _ in range(2):
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path, ignore_errors=True)
        else:
            path.unlink(missing_ok=True)
        if not path.exists():
            return


def targets(data_dir: Path, config_dir: Path, runtime_dir: Path, keep_models: bool,
           onnx_dir: Path | None = None) -> list[Path]:
    paths = []
    if data_dir.exists():
        if keep_models:
            paths += sorted(p for p in data_dir.iterdir() if p.name != "models")
        else:
            paths.append(data_dir)
    paths += [p for p in (config_dir, runtime_dir, onnx_dir) if p and p.exists()]
    return paths


def run_uninstall(data_dir: Path, config_dir: Path, runtime_dir: Path, keep_models: bool, yes: bool,
                  ask: Callable[[str], str] | None, out: Callable[[str], None],
                  run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
                  uv: str | None = None, prefix: str = "", language: str = "fr",
                  remove: Callable[[Path], None] = _remove, onnx_dir: Path | None = None,
                  style: Style | None = None) -> int:
    """`ask` vaut None sans terminal : il faut alors `yes` pour agir."""
    homebrew = "/Cellar/" in prefix
    uv_tool = bool(uv) and not homebrew and "/uv/tools/" in prefix.replace("\\", "/")
    paths = targets(data_dir, config_dir, runtime_dir, keep_models, onnx_dir)
    if not paths and not uv_tool:
        out(t(language, "uninstall.nothing"))
        return 0

    style = style or Style(None)
    out(style.strong(t(language, "uninstall.header")))
    for p in paths:
        out(t(language, "uninstall.item").format(path=p, size=_human(_size(p), language)))
    if uv_tool:
        out(t(language, "uninstall.tool"))

    if not yes:
        if ask is None:
            out(t(language, "uninstall.no_tty"))
            return 1
        try:
            answer = ask(t(language, "uninstall.confirm"))
        except EOFError:
            answer = ""
        if answer.strip().lower() not in YES:
            out(t(language, "uninstall.cancelled"))
            return 0

    for p in paths:
        remove(p)
    left = [p for p in paths if p.exists()]
    # en dernier : le programme qui tourne vit dans cet environnement uv
    if uv_tool:
        run([uv, "tool", "uninstall", "steph"], capture_output=True, text=True)
    if keep_models:
        out(t(language, "uninstall.models_kept").format(path=data_dir / "models"))
    if homebrew:
        out(t(language, "uninstall.brew"))
    out(t(language, "uninstall.kept"))
    for p in left:
        out(t(language, "uninstall.left").format(path=p))
    if left:
        return 1
    out(style.accent(t(language, "uninstall.done")))
    return 0


def main(keep_models: bool, yes: bool) -> int:
    from .config import CONFIG_PATH, DATA_DIR, RUNTIME_DIR, load_config

    language = load_config().language
    # /tmp/steph-<uid> nous appartient en entier ; XDG_RUNTIME_DIR non : seul son sous-dossier steph part
    runtime = RUNTIME_DIR.parent if RUNTIME_DIR.parent.name.startswith("steph-") else RUNTIME_DIR
    tty = None if yes else open_tty()
    ask = TtyPrompter(*tty).ask if tty else None
    try:
        return run_uninstall(DATA_DIR, CONFIG_PATH.parent, runtime, keep_models, yes, ask,
                             out=lambda line: print(line, flush=True), uv=find_uv(),
                             prefix=sys.prefix, language=language, onnx_dir=onnxruntime_telemetry_dir(),
                             style=for_stream(sys.stdout))
    finally:
        for stream in tty or ():
            stream.close()
