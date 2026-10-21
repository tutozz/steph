"""`steph update` : met à jour steph, llama.cpp, le modèle et la voix.

Depuis un clone git : `git pull --ff-only`, puis scripts/install.sh --update,
qui porte seul la logique de téléchargement (llama.cpp, modèle, voix).
Installé par uv tool ou Homebrew : indique la commande à lancer.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable

from .term_style import Style, for_stream


def _is_clone(project_dir: Path | None) -> bool:
    return bool(project_dir) and (project_dir / ".git").exists() and (project_dir / "scripts" / "install.sh").exists()


def _git(run, d: Path, *args: str) -> subprocess.CompletedProcess:
    return run(["git", "-C", str(d), *args], capture_output=True, text=True)


def _check_clone(d: Path, run, out, style: Style) -> None:
    """Compare HEAD au dépôt distant sans rien modifier (ls-remote, pas de fetch)."""
    head = _git(run, d, "rev-parse", "HEAD")
    upstream = _git(run, d, "rev-parse", "--abbrev-ref", "@{u}")
    remote, _, branch = upstream.stdout.strip().partition("/")
    if head.returncode or upstream.returncode or not branch:
        out("steph : pas de branche distante suivie, vérification impossible.")
        return
    remote_head = _git(run, d, "ls-remote", remote, f"refs/heads/{branch}")
    if remote_head.returncode or not remote_head.stdout.strip():
        out("steph : dépôt distant injoignable.")
    elif remote_head.stdout.split()[0] == head.stdout.strip():
        out("steph : à jour.")
    elif not _git(run, d, "merge-base", "--is-ancestor", remote_head.stdout.split()[0], "HEAD").returncode:
        out("steph : à jour, avec des commits locaux non publiés.")
    else:
        out(style.accent("steph : nouvelle version disponible."))


def _update_homebrew_llama(check: bool, run, out) -> None:
    llama, brew = shutil.which("llama-server"), shutil.which("brew")
    if not (llama and brew and llama.startswith(str(Path(brew).parent.parent))):
        out("llama.cpp : installé hors Homebrew, à mettre à jour à la main.")
        return
    # --check ne doit rien modifier, pas même l'index Homebrew
    env = {**os.environ, "HOMEBREW_NO_AUTO_UPDATE": "1"} if check else None
    outdated = run(["brew", "outdated", "--quiet", "llama.cpp"], capture_output=True, text=True, env=env)
    if not outdated.stdout.strip():
        out("llama.cpp : à jour.")
    elif check:
        out("llama.cpp : mise à jour Homebrew disponible.")
    else:
        run(["brew", "upgrade", "llama.cpp"])


def run_update(project_dir: Path | None, check: bool,
               run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
               out: Callable[[str], None] = print, style: Style | None = None) -> int:
    style = style or Style(None)
    if _is_clone(project_dir):
        install = project_dir / "scripts" / "install.sh"
        if check:
            _check_clone(project_dir, run, out, style)
            return run(["bash", str(install), "--check"]).returncode
        if run(["git", "-C", str(project_dir), "pull", "--ff-only"]).returncode:
            out(style.strong("steph : git pull a échoué (modifications locales ou historique divergent). "
                             "Rien d'autre n'a été mis à jour."))
            return 1
        return run(["bash", str(install), "--update"]).returncode

    upgrade = "brew upgrade steph" if "/Cellar/" in sys.prefix else "uv tool upgrade steph"
    out(f"steph : installé sans clone git ; pour le mettre à jour, lancez : {upgrade}")
    _update_homebrew_llama(check, run, out)
    return 0


def main(check: bool) -> int:
    from .config import PROJECT_DIR
    # flush : ces lignes doivent précéder la sortie de install.sh
    return run_update(PROJECT_DIR, check, out=lambda line: print(line, flush=True), style=for_stream(sys.stdout))
