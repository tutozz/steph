"""Catalogue des modèles (LLM et voix TTS) : niveau de la machine et choix recommandé.

Schéma de `docs/voice-bench/reference/options.json` (tiers, recommended, options),
rempli par B4 dans `data/catalog.json`. Sans fichier, le catalogue est vide et
`steph setup` ne pose ni la question du modèle ni celle de la voix par catalogue.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

# STEPH_CATALOG : surcharge pour les tests d'intégration (isole du vrai catalogue B4,
# qui peut proposer un téléchargement réel), comme STEPH_LLAMA_SERVER dans config.py.
CATALOG_PATH = Path(os.environ.get("STEPH_CATALOG", str(Path(__file__).parent / "data" / "catalog.json")))


@dataclass
class Machine:
    physical_cores: int | None
    ram_gb: float | None
    vram_gb: float


@dataclass
class ModelChoice:
    label: str
    path: str
    size_mb: int
    profile: str
    recommended: bool
    out_of_scope: bool
    available: bool = True  # False : décidé (catalogue) mais pas encore publié, rien à télécharger
    source: str = ""  # dépôt Hugging Face (ex. "org/repo-GGUF"), vide si non applicable
    not_recommended: bool = False  # True : proposé en attendant seulement, jamais recommandé (B9)
    id: str = ""
    role: str = ""  # small|base : B10 recommande l'un ou l'autre selon la vitesse mesurée
    # lecture du prompt (jetons/s) : valeur du catalogue (i5-7200U), puis prédite pour cette machine par speed.apply
    prompt_tokens_per_sec: float = 0.0
    summary_prompt_tokens_p90: int = 0
    sha256: str = ""  # empreinte vérifiée après téléchargement, vide si non publiée


def load_catalog(path: Path = CATALOG_PATH) -> dict:
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return {}


def detect_machine() -> Machine:
    from .config import load_config
    from .hardware import detect_cpu, detect_gpu_vram, detect_gpus_cached, detect_memory

    cpu, mem = detect_cpu(), detect_memory()
    ram = mem.total_mb / 1024 if mem.total_mb else None
    gpus = detect_gpus_cached(load_config().llama_server)
    vram_by_gpu = detect_gpu_vram(gpus)
    vram_gb = max(vram_by_gpu.values()) / 1024 if vram_by_gpu else 0.0
    return Machine(cpu.physical_cores, ram, vram_gb)


def detect_tier(catalog: dict, machine: Machine) -> str | None:
    best = None
    for tier in catalog.get("tiers", []):
        if "vram_gb_min" in tier:
            if machine.vram_gb >= tier["vram_gb_min"]:
                return tier["id"]
            continue
        if machine.physical_cores is None or machine.ram_gb is None:
            continue
        if (machine.physical_cores >= tier.get("cpu_physical_cores_min", 0)
                and machine.ram_gb >= tier.get("ram_gb_min", 0)):
            best = tier["id"]
    return best


def _fits(option: dict, machine: Machine) -> bool:
    req = option.get("requires", {})
    if machine.physical_cores is not None and machine.physical_cores < req.get("cpu_physical_cores_min", 0):
        return False
    if machine.ram_gb is not None and machine.ram_gb < req.get("ram_gb_min", 0):
        return False
    vram_min = req.get("vram_gb_min", 0)
    return not vram_min or machine.vram_gb >= vram_min


def _choices(catalog: dict, kind: str, dest_dir: Path, machine: Machine) -> list[ModelChoice]:
    tier = detect_tier(catalog, machine)
    # un niveau sans recommandation propre hérite de celle du niveau inférieur (N2 -> N1)
    recommended = None
    for t in catalog.get("tiers", []):
        rec = catalog.get("recommended", {}).get(t["id"], {}).get(kind)
        if rec and "vram_gb_min" not in t:
            recommended = rec
        if t["id"] == tier:
            recommended = catalog.get("recommended", {}).get(tier, {}).get(kind, recommended)
            break
    return [
        ModelChoice(label=o["label"], path=str(Path(dest_dir) / o["file"]), size_mb=o.get("size_mb", 0),
                    profile=o.get("profile", "generic"), recommended=o["id"] == recommended,
                    out_of_scope=not _fits(o, machine), available=o.get("available", True),
                    source=o.get("source", ""), not_recommended=o.get("not_recommended", False),
                    id=o.get("id", ""), role=o.get("role", ""),
                    prompt_tokens_per_sec=float(o.get("prompt_tokens_per_sec", 0)),
                    summary_prompt_tokens_p90=int(o.get("summary_prompt_tokens_p90", 0)),
                    sha256=o.get("sha256", ""))
        for o in catalog.get("options", []) if o.get("kind") == kind
    ]


def llm_choices(catalog: dict, models_dir: Path, machine: Machine) -> list[ModelChoice]:
    return _choices(catalog, "llm", models_dir, machine)


def tts_choices(catalog: dict, voices_dir: Path, machine: Machine) -> list[ModelChoice]:
    return _choices(catalog, "tts", voices_dir, machine)


def catalog_prompt_speed(model_path: str, catalog: dict | None = None) -> float | None:
    """Vitesse de lecture du prompt que le catalogue donne au fichier `model_path`, ou None."""
    name = Path(model_path).name
    for o in (load_catalog() if catalog is None else catalog).get("options", []):
        if o.get("kind") == "llm" and o.get("file") == name and o.get("prompt_tokens_per_sec"):
            return float(o["prompt_tokens_per_sec"])
    return None


# ------------------------------------------------------------ installation et mise à jour (Z1, B9b)
def _llm_options(catalog: dict) -> list[dict]:
    return [o for o in catalog.get("options", []) if o.get("kind") == "llm"]


def _recommended_published(catalog: dict) -> dict | None:
    """Modèle recommandé au niveau le plus bas, s'il est publié : sûr sur toute machine.
    `steph setup` propose ensuite le modèle de base si la vitesse mesurée le permet."""
    tiers = [t["id"] for t in catalog.get("tiers", []) if "vram_gb_min" not in t]
    rec_id = next((catalog.get("recommended", {}).get(t, {}).get("llm") for t in tiers
                   if catalog.get("recommended", {}).get(t, {}).get("llm")), None)
    opt = next((o for o in _llm_options(catalog) if o["id"] == rec_id), None)
    return opt if opt and opt.get("available", True) and opt.get("source") else None


def install_model(catalog: dict, models_dir: Path, current_model: str | None, update: bool):
    """Modèle que scripts/install.sh télécharge par défaut : (dépôt HF, fichier, sha256), "keep" ou None.

    "keep" : mise à jour d'une installation dont le modèle configuré est présent et n'est pas
    un ancien fichier remplacé par le catalogue. None : rien de publié, l'installeur retombe sur Gemma."""
    opt = _recommended_published(catalog)
    if opt is None:
        return None
    if update and current_model:
        name = Path(current_model).name
        replaced = {r for o in _llm_options(catalog) for r in o.get("replaces", [])}
        if Path(current_model).is_file() and name not in replaced:
            return "keep"
    return opt["source"], opt["file"], opt.get("sha256", "")


def migrate_config(catalog: dict, models_dir: Path, config_path: Path) -> str | None:
    """Pointe config.toml vers le fichier qui remplace un ancien modèle, une fois celui-ci téléchargé.

    Retourne le nouveau chemin, ou None si rien ne change. L'ancien fichier n'est jamais supprimé."""
    import tomllib
    try:
        current = tomllib.loads(config_path.read_text()).get("model")
    except (OSError, tomllib.TOMLDecodeError):
        return None
    if not current:
        return None
    name = Path(current).name
    for o in _llm_options(catalog):
        target = Path(models_dir) / o["file"]
        if name in o.get("replaces", []) and target.is_file():
            from .setup import save_settings
            answers = {"model": str(target), "llm_profile": o.get("profile", "generic")}
            if o.get("prompt_tokens_per_sec"):
                answers["llm_prompt_tokens_per_sec"] = float(o["prompt_tokens_per_sec"])
            save_settings(config_path, answers)
            return str(target)
    return None


def adopt_model(catalog: dict, models_dir: Path, config_path: Path, file: str) -> str | None:
    """Fait pointer config.toml vers `file`, le modèle que l'installeur vient de télécharger.

    Sans cela, une installation sans `steph setup` (pas de terminal, refus) retombe sur le défaut
    de config.py. Un `model` déjà configuré et présent sur le disque est un choix : il reste.
    Retourne le chemin adopté, ou None si rien ne change."""
    import tomllib
    option = next((o for o in _llm_options(catalog) if o.get("file") == file), None)
    target = Path(models_dir) / file
    if option is None or not target.is_file():
        return None
    try:
        current = tomllib.loads(config_path.read_text()).get("model")
    except (OSError, tomllib.TOMLDecodeError):
        current = None
    if current and Path(os.path.expanduser(current)).is_file():
        return None
    from .setup import save_settings
    answers = {"model": str(target), "llm_profile": option.get("profile", "generic")}
    if option.get("prompt_tokens_per_sec"):
        answers["llm_prompt_tokens_per_sec"] = float(option["prompt_tokens_per_sec"])
    save_settings(config_path, answers)
    return str(target)


def main(argv: list[str] | None = None) -> int:
    """`python -m steph.catalog install-model [--update]` : « dépôt fichier », « keep » ou rien.
    `python -m steph.catalog migrate` : met config.toml à jour après le téléchargement."""
    import sys
    from .config import CONFIG_PATH, DATA_DIR
    args = sys.argv[1:] if argv is None else argv
    models_dir, catalog = DATA_DIR / "models", load_catalog()
    if args[:1] == ["install-model"]:
        current = None
        if "--update" in args:
            import tomllib
            try:
                current = tomllib.loads(CONFIG_PATH.read_text()).get("model")
            except (OSError, tomllib.TOMLDecodeError):
                pass
            current = os.path.expanduser(current) if current else str(models_dir / "gemma-4-E2B_q4_0-it.gguf")
        pick = install_model(catalog, models_dir, current, "--update" in args)
        print(pick if isinstance(pick, str) else " ".join(pick) if pick else "")
        return 0
    if args[:1] == ["migrate"]:
        new = migrate_config(catalog, models_dir, CONFIG_PATH)
        if new:
            print(f"steph : modèle remplacé dans {CONFIG_PATH} : {new}")
        return 0
    if args[:1] == ["adopt"] and len(args) == 2:
        new = adopt_model(catalog, models_dir, CONFIG_PATH, args[1])
        if new:
            print(f"steph : modèle configuré dans {CONFIG_PATH} : {new}")
        return 0
    print("usage : python -m steph.catalog install-model [--update] | migrate | adopt FICHIER", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
