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


def find_project_dir(module_file: Path) -> Path | None:
    """Racine du clone git (src/steph/config.py -> racine), None si steph est
    installé depuis un wheel (site-packages) ou par Homebrew."""
    root = Path(module_file).resolve().parents[2]
    return root if (root / "pyproject.toml").exists() else None


PROJECT_DIR = find_project_dir(Path(__file__))


def _find_llama_server() -> str:
    env = os.environ.get("STEPH_LLAMA_SERVER")
    if env:
        return env
    vendor = sorted((PROJECT_DIR / "vendor" / "llama").glob("llama-*/llama-server"), reverse=True) if PROJECT_DIR else []
    for cand in vendor:
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
    # generic : n'importe quel modèle configuré, prompts de production (SUMMARY_SYSTEM,
    # long, avec exemples). finetuned : `model` est un modèle affiné steph (label.py,
    # P15/P17) ; narrator._finish() envoie alors le prompt court réellement appris
    # (prompts.finetuned_summary_messages()) et plafonne l'entrée au palier retenu par P11.
    # Défaut "generic" tant que le catalogue LLM (B4) n'existe pas : rien ne permet de
    # déduire le profil du seul champ `model`.
    llm_profile: str = "generic"  # generic|finetuned
    llama_server: str = field(default_factory=_find_llama_server)
    llm_port: int = 8765
    llm_ctx: int = 32768  # partagé entre 2 slots : 0 = résumés, 1 = questions
    llm_gpu_layers: int = 99
    llm_gpu_fit_check: bool = True  # repli sur le processeur si le modèle ne tient pas dans la VRAM libre
    llm_parallel: int = 2
    llm_batch: int = 512
    llm_ubatch: int = 512
    llm_flash_attn: str = "auto"  # auto|on|off ; passé en -fa seulement si différent de "auto"
    llm_cache_type: str = "f16"  # passé en -ctk/-ctv seulement si différent de "f16"
    llm_extra_args: list[str] = field(default_factory=list)
    llm_env: dict[str, str] = field(default_factory=dict)  # variables d'env pour llama-server (ex. GGML_VK_*)
    # modèles qui ferment un raisonnement jamais ouvert (Granite 4.2) : coûte le premier mot
    buffer_reasoning: bool = False
    # vitesse de lecture du prompt par le modèle (jetons/s), pour estimer le délai avant
    # le premier jeton ; mesuré P7 sur Granite CPU (i5-7200U). Sans valeur explicite, load_config
    # prend celle du catalogue pour le modèle configuré ; steph setup écrit celle mesurée (B10)
    llm_prompt_tokens_per_sec: float = 210.0
    # garde-fou d'ancrage : coupe toute proposition dont un fait est absent de l'entrée ;
    # tamponne jusqu'à la ponctuation, donc retarde d'autant le premier mot d'une réponse
    ground_output: bool = True
    # L5 : bloc de faits extraits en code (digest.extract_facts) dans l'entrée du résumé.
    # Change l'entrée du modèle : activé sur décision utilisateur (+1,5 pt pour Gemma brut) ;
    # les prochains affinages doivent être entraînés avec ce bloc (docs/deterministic-aids.md)
    facts_block: bool = True
    # --- Mémoire (Q2b) ---
    # décharge llama-server après N min sans requête LLM (résumé, question, détail,
    # préchauffage compris), partagé entre toutes les fenêtres ; 0 = jamais
    llm_idle_unload_minutes: float = 10.0
    # recharge llama-server dès qu'une commande est tapée (avant même qu'elle finisse),
    # pour qu'il soit prêt au moment où le résumé en a besoin
    llm_anticipatory_reload: bool = True
    # attente max d'un rechargement en cours avant de replier sur le résumé déterministe ;
    # cold start mesuré à 4,05 s en Q1 (Mac, modèle Gemma 3,1 Go), marge incluse
    llm_reload_grace_seconds: float = 8.0
    # --- Matériel ---
    hardware_profile: str = "auto"  # auto|none|nom de fichier (ex. "gpu/intel-arc-140t")
    # --- Voix ---
    voice: str = str(DATA_DIR / "voices" / "fr_FR-siwis-medium.onnx")
    speech_rate: float = 1.25  # >1 = plus rapide
    tts_enabled: bool = True
    speech_log: str = ""  # fichier où journaliser chaque phrase dite (tests, débogage)
    # --- Comportement ---
    language: str = "fr"  # fr|en : langue des prompts et des messages parlés
    verbosity: int = 1  # 0 = erreurs seulement, 1 = bref, 2 = détaillé
    first_update_after: float = 4.0  # s avant la 1re annonce « en cours »
    update_interval: float = 12.0  # s entre deux points d'étape
    prompt_idle: float = 1.2  # s de silence avant de signaler une question posée
    read_verbatim_max_words: int = 20  # sortie courte : lue telle quelle
    announce_cd: bool = True
    qa_block_chars: int = 2500  # sortie gardée par commande pour le mode questions
    qa_budget_chars: int = 36000  # historique max envoyé au mode questions
    # D4 : questions à outils en lecture seule (liste des commandes + outils sur la session) ;
    # prototype mesuré, désactivé tant que le banc ne le justifie pas. Plafond atteint : mode actuel.
    qa_tools: bool = False
    qa_tools_max_calls: int = 3
    qa_tools_result_chars: int = 2500  # taille max d'un résultat d'outil, comme qa_block_chars
    qa_tools_timeout_seconds: float = 45.0  # tous les tours du modèle compris
    summary_chars: int = 1500  # sortie envoyée au LLM pour le résumé rapide (latence ∝ taille)
    # règles par commande (clé = premier mot) : mute, mute-all, verbatim, summary
    rules: dict[str, str] = field(default_factory=dict)
    # --- Touches (séquences brutes) ---
    key_menu: str = "\x1b[17~"  # F6 : menu parlé (réglages + actions)
    key_stop: str = "\x1b[19~"  # F8 : couper la parole
    key_repeat: str = "\x1b[20~"  # F9 : répéter
    key_ask: str = "\x1b[18~"  # F7 : ouvrir la fenêtre de questions
    key_details: str = "\x1b[21~"  # F10 : détail de la dernière commande
    # relecture ligne à ligne de la dernière sortie (séquences xterm de Maj+F5 à Maj+F8)
    key_line_first: str = "\x1b[15;2~"  # Maj+F5 : première ligne
    key_line_prev: str = "\x1b[17;2~"  # Maj+F6 : ligne précédente
    key_line_next: str = "\x1b[18;2~"  # Maj+F7 : ligne suivante
    key_line_last: str = "\x1b[19;2~"  # Maj+F8 : dernière ligne
    terminal_cmd: str = ""  # vide = auto (ptyxis, gnome-terminal, konsole, xterm)
    # interface de steph setup et du menu F6 : auto (plein écran, mode ligne si lecteur d'écran,
    # TERM=dumb ou pas de terminal), line, tui ; STEPH_UI la surcharge (docs/tui-a11y.md)
    ui: str = "auto"


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
    profile = getattr(cfg, "_hardware_debug", (None,))[0]
    explicit = ("llm_prompt_tokens_per_sec" in data or "STEPH_LLM_PROMPT_TOKENS_PER_SEC" in os.environ
                or (profile is not None and "llm_prompt_tokens_per_sec" in profile.settings))
    if not explicit:
        # 210 jetons/s vaut pour Granite : Gemma lit 7 fois moins vite sur l'i5 (G2), la phrase d'attente se taisait
        from .catalog import catalog_prompt_speed
        cfg.llm_prompt_tokens_per_sec = catalog_prompt_speed(cfg.model) or cfg.llm_prompt_tokens_per_sec
    return cfg
