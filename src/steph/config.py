"""Configuration : valeurs par défaut + surcharge par ~/.config/steph/config.toml."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path

DATA_DIR = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "steph"
CONFIG_PATH = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "steph" / "config.toml"
# macOS n'a pas de XDG_RUNTIME_DIR ; /tmp reste court (limite de 104 octets des sockets Unix)
RUNTIME_DIR = Path(os.environ.get("XDG_RUNTIME_DIR", f"/tmp/steph-{os.getuid()}")) / "steph"
PROJECT_DIR = Path(__file__).resolve().parents[2]


def _find_llama_server() -> str:
    env = os.environ.get("STEPH_LLAMA_SERVER")
    if env:
        return env
    for cand in sorted((PROJECT_DIR / "vendor" / "llama").glob("llama-*/llama-server"), reverse=True):
        return str(cand)
    for cand in sorted((DATA_DIR / "llama").glob("llama-*/llama-server"), reverse=True):
        return str(cand)
    import shutil
    # Homebrew (macOS : brew install llama.cpp) ou paquet système
    return shutil.which("llama-server") or "llama-server"


@dataclass
class Config:
    # --- LLM ---
    model: str = str(DATA_DIR / "models" / "gemma-4-E2B_q4_0-it.gguf")
    llama_server: str = field(default_factory=_find_llama_server)
    llm_port: int = 8765
    llm_ctx: int = 32768  # partagé entre 2 slots : 0 = résumés, 1 = questions
    llm_gpu_layers: int = 99
    llm_parallel: int = 2
    llm_batch: int = 512
    llm_ubatch: int = 512
    llm_flash_attn: str = "auto"  # auto|on|off ; passé en -fa seulement si différent de "auto"
    llm_cache_type: str = "f16"  # passé en -ctk/-ctv seulement si différent de "f16"
    llm_extra_args: list[str] = field(default_factory=list)
    llm_env: dict[str, str] = field(default_factory=dict)  # variables d'env pour llama-server (ex. GGML_VK_*)
    # --- Matériel ---
    hardware_profile: str = "auto"  # auto|none|nom de fichier (ex. "gpu/intel-arc-140t")
    # --- Voix ---
    voice: str = str(DATA_DIR / "voices" / "fr_FR-siwis-medium.onnx")
    speech_rate: float = 1.25  # >1 = plus rapide
    tts_enabled: bool = True
    speech_log: str = ""  # fichier où journaliser chaque phrase dite (tests, débogage)
    # --- Comportement ---
    verbosity: int = 1  # 0 = erreurs seulement, 1 = bref, 2 = détaillé
    first_update_after: float = 4.0  # s avant la 1re annonce « en cours »
    update_interval: float = 12.0  # s entre deux points d'étape
    prompt_idle: float = 1.2  # s de silence avant de signaler une question posée
    read_verbatim_max_words: int = 20  # sortie courte : lue telle quelle
    announce_cd: bool = True
    qa_block_chars: int = 2500  # sortie gardée par commande pour le mode questions
    qa_budget_chars: int = 36000  # historique max envoyé au mode questions
    summary_chars: int = 1500  # sortie envoyée au LLM pour le résumé rapide (latence ∝ taille)
    # --- Touches (séquences brutes) ---
    key_stop: str = "\x1b[19~"  # F8 : couper la parole
    key_repeat: str = "\x1b[20~"  # F9 : répéter
    key_ask: str = "\x1b[18~"  # F7 : ouvrir la fenêtre de questions
    key_details: str = "\x1b[21~"  # F10 : détail de la dernière commande
    terminal_cmd: str = ""  # vide = auto (ptyxis, gnome-terminal, konsole, xterm)


def load_config(apply_profile: bool = False) -> Config:
    """apply_profile=True détecte le matériel et applique le profil correspondant
    (voir profile.py) avant la surcharge par config.toml puis par les variables
    d'environnement. Seuls les points d'entrée qui lancent llama-server doivent
    le passer à True : la détection lance un binaire, inutile pour `steph ask`/`ctl`."""
    cfg = Config()
    data = tomllib.loads(CONFIG_PATH.read_text()) if CONFIG_PATH.exists() else {}
    # hardware_profile doit être résolu avant le profil lui-même, donc avant
    # le reste de la surcharge (priorité : défauts < profil < config.toml < env)
    if "hardware_profile" in data:
        cfg.hardware_profile = data["hardware_profile"]
    env_hardware_profile = os.environ.get("STEPH_HARDWARE_PROFILE")
    if env_hardware_profile is not None:
        cfg.hardware_profile = env_hardware_profile
    if apply_profile:
        from .profile import apply_hardware_profile
        cfg._hardware_debug = apply_hardware_profile(cfg)  # utilisé par `steph profile`
    known = {f.name for f in fields(Config)}
    for k, v in data.items():
        if k in known:
            setattr(cfg, k, v)
    for f in fields(Config):
        env = os.environ.get(f"STEPH_{f.name.upper()}")
        if env is not None:
            cur = getattr(cfg, f.name)
            if isinstance(cur, (list, dict)):
                continue  # STEPH_* ne surcharge pas les champs liste/dict
            if isinstance(cur, bool):
                setattr(cfg, f.name, env.lower() in ("1", "true", "oui", "yes"))
            else:
                setattr(cfg, f.name, type(cur)(env))
    for name in ("model", "voice"):
        setattr(cfg, name, os.path.expanduser(getattr(cfg, name)))
    return cfg
