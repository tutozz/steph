"""Vitesse de la machine au setup (B10) : quel modèle rend un premier résumé à temps.

La RAM ne suffit pas : l'i5-7200U a 15 Go, mais Gemma y lit le prompt à 28 jetons/s et
son premier résumé arrive à 27 s au p90 (bench/matrix/results/gemma/G2-i5.md).

Seuil : premier résumé prédit au p90 sous 3 s. C'est le p90 mesuré de steph-speak v1.0 sur
l'i5 (2,26 s, 36 cas) avec 30 % de marge pour l'erreur de prédiction (proxy T4 : 10 à 15 %),
et le repère « résumés sous 3 s » déjà suivi par G2. Il faut 255 jetons/s à Gemma
(766 jetons au p90), soit ~1 800 mesurés sur le petit modèle : l'i5 en est à 9 fois moins.
"""

from __future__ import annotations

import json
import socket
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable

from .catalog import ModelChoice
from .config import Config
from .strings import t

TARGET_FIRST_SUMMARY_P90 = 3.0
# ~200 jetons : 7 s au pire pour Gemma sur l'i5, moins d'une seconde pour le petit modèle
MEASURE_PROMPT = "\n".join(
    f"-rw-r--r--  1 user  staff  {1024 + 37 * i} Sep 30 10:{i:02d} build-report-{i}.log" for i in range(10))
WARMUP_PROMPT = "ls -la"


@dataclass
class Verdict:
    recommended: ModelChoice | None = None  # None : le catalogue n'a pas de rôles, rien ne change
    base: ModelChoice | None = None
    small: ModelChoice | None = None
    reference: ModelChoice | None = None  # modèle déjà présent qui a servi à la mesure
    measured_tps: float | None = None
    base_p90: float | None = None
    fast: bool = False
    measured: bool = False
    reason: str = ""  # measured|ram|gpu|cpu


def predict_tokens_per_sec(target: ModelChoice, reference: ModelChoice | None, measured: float | None) -> float:
    """Lecture du prompt de `target` sur cette machine, d'après la mesure faite sur `reference`."""
    if measured and reference is not None and reference.prompt_tokens_per_sec > 0:
        return measured * target.prompt_tokens_per_sec / reference.prompt_tokens_per_sec
    return target.prompt_tokens_per_sec


def first_summary_p90(model: ModelChoice, tokens_per_sec: float) -> float | None:
    if tokens_per_sec <= 0 or model.summary_prompt_tokens_p90 <= 0:
        return None
    return model.summary_prompt_tokens_p90 / tokens_per_sec


def reference_model(models: list[ModelChoice]) -> ModelChoice | None:
    """Le plus petit modèle déjà sur le disque : la mesure dure le moins longtemps."""
    present = [m for m in models if m.prompt_tokens_per_sec > 0 and Path(m.path).is_file()]
    return min(present, key=lambda m: m.size_mb) if present else None


def assess(models: list[ModelChoice], reference: ModelChoice | None, measured: float | None,
           gpu: bool, vram_blocked: bool = False) -> Verdict:
    """vram_blocked : la mesure a tourné sur GPU mais le modèle de base n'y tiendra pas (VRAM libre)."""
    base = next((m for m in models if m.role == "base" and not m.not_recommended), None)
    small = next((m for m in models if m.role == "small"), None)
    if base is None or small is None:
        return Verdict()
    verdict = Verdict(base=base, small=small, reference=reference, measured_tps=measured,
                      measured=bool(measured and reference is not None))
    if base.out_of_scope:
        verdict.reason = "ram"
    elif vram_blocked:
        verdict.reason = "vram"
        verdict.measured = False  # la vitesse mesurée sur GPU ne se transpose pas au modèle de base
    elif verdict.measured:
        verdict.base_p90 = first_summary_p90(base, predict_tokens_per_sec(base, reference, measured))
        verdict.fast = verdict.base_p90 is not None and verdict.base_p90 <= TARGET_FIRST_SUMMARY_P90
        verdict.reason = "measured"
    else:
        # sans mesure : une carte graphique reconnue lit vite, un processeur seul non (G2, G6)
        verdict.fast = gpu
        verdict.reason = "gpu" if gpu else "cpu"
    verdict.recommended = base if verdict.fast else small
    return verdict


def apply(models: list[ModelChoice], verdict: Verdict) -> list[ModelChoice]:
    """Copies des choix : recommandation selon la vitesse, vitesse prédite pour cette machine."""
    out = []
    for m in models:
        tps = predict_tokens_per_sec(m, verdict.reference, verdict.measured_tps) if verdict.measured else \
            m.prompt_tokens_per_sec
        rec = m.recommended if verdict.recommended is None else m is verdict.recommended
        out.append(replace(m, recommended=rec, prompt_tokens_per_sec=round(tps, 1)))
    return out


def format_seconds(seconds: float, language: str) -> str:
    text = f"{seconds:.0f}" if seconds >= 10 else f"{seconds:.1f}".removesuffix(".0")
    return text.replace(".", ",") if language == "fr" else text


def seconds_phrase(seconds: float, language: str) -> str:
    text = format_seconds(seconds, language)
    # français : singulier en dessous de 2 (« 1,4 seconde ») ; anglais : seulement pour 1
    one = float(text.replace(",", ".")) < 2 if language == "fr" else text == "1"
    return f"{text} {t(language, 'speed.second' if one else 'speed.seconds')}"


def message_lines(verdict: Verdict, language: str) -> list[str]:
    """Phrases courtes, une par ligne d'écran (80 colonnes), dites dans l'ordre."""
    if verdict.recommended is None:
        return []
    if verdict.reason == "ram":
        lines = [t(language, "speed.ram")]
    elif verdict.reason == "vram":
        lines = [t(language, "speed.vram")]
    elif verdict.reason == "measured":
        lines = [t(language, "speed.measured").format(seconds=seconds_phrase(verdict.base_p90, language)),
                 t(language, "speed.fast" if verdict.fast else "speed.slow").format(
                     target=format_seconds(TARGET_FIRST_SUMMARY_P90, language))]
    else:
        lines = [t(language, "speed.failed" if verdict.reference is not None else "speed.no_model"),
                 t(language, "speed.gpu" if verdict.reason == "gpu" else "speed.cpu")]
    return [*lines, t(language, "speed.other")]


def message(verdict: Verdict, language: str) -> str:
    return " ".join(message_lines(verdict, language))


# ------------------------------------------------------------ mesure réelle
def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _healthy(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=0.5) as r:
            return r.status == 200
    except (urllib.error.URLError, OSError, TimeoutError):
        return False


def _post(port: int, path: str, body: dict, timeout: float) -> dict:
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", json.dumps(body).encode(),
                                 {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def _launch(args: list[str], env: dict):
    return subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            stdin=subprocess.DEVNULL, env=env, start_new_session=True)


def measure_prompt_speed(cfg: Config, model_path: str, *, launch: Callable = _launch,
                         healthy: Callable[[int], bool] = _healthy, post: Callable = _post,
                         load_timeout: float = 60.0, request_timeout: float = 30.0) -> float | None:
    """Jetons de prompt lus par seconde par `model_path` sur cette machine, ou None.

    Serveur à part, sur un port libre : celui de steph peut tourner dans une autre fenêtre."""
    from .hardware import effective_gpu_layers
    from .llm import _build_env

    port = _free_port()
    args = [cfg.llama_server, "-m", model_path, "--host", "127.0.0.1", "--port", str(port),
            "-c", "2048", "-ngl", str(effective_gpu_layers(cfg, model_path)[0]), "--parallel", "1", "--no-webui",
            "-b", str(cfg.llm_batch), "-ub", str(cfg.llm_ubatch), "--cache-ram", "0", *cfg.llm_extra_args]
    try:
        proc = launch(args, _build_env(cfg, Path(cfg.llama_server)))
    except OSError:
        return None
    try:
        deadline = time.monotonic() + load_timeout
        while not healthy(port):
            if proc.poll() is not None or time.monotonic() > deadline:
                return None
            time.sleep(0.1)
        body = {"n_predict": 1, "cache_prompt": False, "temperature": 0}
        post(port, "/completion", {**body, "prompt": WARMUP_PROMPT}, request_timeout)
        timings = post(port, "/completion", {**body, "prompt": MEASURE_PROMPT}, request_timeout).get("timings") or {}
        tps = float(timings.get("prompt_per_second") or 0)
        return tps if tps > 0 else None
    except (OSError, ValueError, TypeError):
        return None
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
