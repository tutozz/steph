"""Sélection du profil matériel adapté au GPU détecté, à partir des .toml de profiles/.

Un profil est un fichier .toml avec une table [match] (critères optionnels :
kind, vendor, pci_ids, name) et une table [settings] (n'importe quel champ de
Config). Voir profiles/README.md pour contribuer un profil."""

from __future__ import annotations

import fnmatch
import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path

from .config import Config
from .hardware import Gpu, detect_gpus_cached

PROFILES_DIR = Path(__file__).resolve().parent / "profiles"

# rang du kind pour départager un score égal : dedicated > integrated/apple
_KIND_RANK = {"dedicated": 1, "integrated": 0, "apple": 0}


@dataclass
class Profile:
    path: Path
    match: dict = field(default_factory=dict)
    settings: dict = field(default_factory=dict)


def load_profiles(profiles_dir: Path) -> list[Profile]:
    """Charge tous les .toml d'un dossier (et sous-dossiers), triés par chemin
    pour un ordre déterministe. Un fichier illisible ou mal formé est ignoré."""
    profiles = []
    for p in sorted(profiles_dir.rglob("*.toml")):
        try:
            data = tomllib.loads(p.read_text())
        except (OSError, tomllib.TOMLDecodeError):
            continue
        profiles.append(Profile(path=p, match=data.get("match", {}), settings=data.get("settings", {})))
    return profiles


def profile_name(prof: Profile, profiles_dir: Path) -> str:
    """Nom utilisable pour forcer ce profil via hardware_profile, ex. "gpu/intel-arc-140t"."""
    return prof.path.relative_to(profiles_dir).with_suffix("").as_posix()


def _sanitize(profiles: list[Profile]) -> list[str]:
    """Retire de [settings] les clés inconnues de Config et les signale."""
    known = {f.name for f in fields(Config)}
    warnings = []
    for prof in profiles:
        unknown = sorted(set(prof.settings) - known)
        if unknown:
            warnings.append(f"{prof.path.name} : clé(s) inconnue(s) ignorée(s) : {', '.join(unknown)}")
            for k in unknown:
                del prof.settings[k]
    return warnings


def _score(match: dict, gpu: Gpu) -> int | None:
    """Score de correspondance d'un [match] pour un GPU (8/4/2/1 pour
    pci_ids/name/vendor/kind), ou None dès qu'une clé présente ne correspond pas."""
    score = 0
    if "pci_ids" in match:
        if gpu.pci_id is None or gpu.pci_id not in match["pci_ids"]:
            return None
        score += 8
    if "name" in match:
        if not fnmatch.fnmatch(gpu.name.lower(), str(match["name"]).lower()):
            return None
        score += 4
    if "vendor" in match:
        if gpu.vendor != match["vendor"]:
            return None
        score += 2
    if "kind" in match:
        if gpu.kind != match["kind"]:
            return None
        score += 1
    return score


def select_profile(gpus: list[Gpu], profiles_dir: Path) -> tuple[Profile | None, list[str]]:
    """Meilleur profil pour les GPU détectés. Retourne aussi les avertissements
    (clés de [settings] inconnues) : jamais d'exception."""
    profiles = load_profiles(profiles_dir)
    warnings = _sanitize(profiles)

    if not gpus:
        cpu_profiles = [p for p in profiles if p.match.get("kind") == "cpu"]
        return (cpu_profiles[0] if cpu_profiles else None), warnings

    candidates = []  # (score, rang du kind, chemin, profil)
    for gpu in gpus:
        for prof in profiles:
            if prof.match.get("kind") == "cpu":
                continue
            score = _score(prof.match, gpu)
            if not score:
                continue
            candidates.append((score, _KIND_RANK.get(gpu.kind, 0), str(prof.path), prof))
    if not candidates:
        return None, warnings
    candidates.sort(key=lambda c: (-c[0], -c[1], c[2]))
    return candidates[0][3], warnings


def apply_hardware_profile(
    cfg: Config, profiles_dir: Path | None = None
) -> tuple[Profile | None, list[Gpu], list[str]]:
    """Résout cfg.hardware_profile ("auto"/"none"/nom forcé) et applique ses
    réglages sur cfg. La détection ne tourne qu'en mode "auto"."""
    profiles_dir = profiles_dir or PROFILES_DIR
    if cfg.hardware_profile == "none":
        return None, [], []
    if cfg.hardware_profile == "auto":
        gpus = detect_gpus_cached(cfg.llama_server)
        prof, warnings = select_profile(gpus, profiles_dir)
    else:
        gpus = []
        profiles = load_profiles(profiles_dir)
        warnings = _sanitize(profiles)
        prof = next((p for p in profiles if profile_name(p, profiles_dir) == cfg.hardware_profile), None)
        if prof is None:
            warnings.append(f"profil « {cfg.hardware_profile} » introuvable, défauts conservés")
    if prof is not None:
        for k, v in prof.settings.items():
            setattr(cfg, k, v)
    return prof, gpus, warnings
