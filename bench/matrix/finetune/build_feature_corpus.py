#!/usr/bin/env python3
"""H3a : construit, pour chaque fonctionnalité hors résumé, les entrées au format exact
que steph envoie (les fonctions `*_messages` de `steph.prompts`), à partir de captures
réelles - jamais de texte inventé pour l'entrée ni pour la sortie.

Règle de H2 (docs/research-retraining.md) : digests en code d'abord, le modèle
n'intervient que là où le code ne suffit pas.
  - F10 (détail), début, progression : aucune nouvelle capture, réutilise le corpus
    résumé déjà anonymisé (corpus/{macos,linux-low,linux-dev}.jsonl).
  - Erreurs multiples et résultats de tests : `resolve()` (src/steph/digest.py) répond
    déjà en code pour gcc/clang/tsc/rustc/eslint/pytest/jest/vitest/cargo/go ; seuls
    les enregistrements où `resolve()` rend `None` atteindraient réellement le LLM en
    production, donc seuls ceux-là entrent au corpus (corpus/features-*.jsonl, K2).
  - Flux (journaux en continu) : fenêtres glissantes filtrées par `flux_window()`
    (nouvelles erreurs/avertissements seulement), sur les captures réelles de flux.

Usage :
    python3 build_feature_corpus.py --corpus-dir corpus --out-dir corpus/features

N'appelle aucun serveur LLM : la construction des messages est pure et locale.
L'étiquetage par l'enseignant est une étape séparée (label_features.py).
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from audit_pii import DEFAULT_NAMES, load_names, scan_text  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))
from steph.digest import digest, resolve  # noqa: E402
from steph.prompts import details_messages, progress_messages, start_messages  # noqa: E402
from steph.textproc import compact_output, flux_window  # noqa: E402

from label import build_messages  # noqa: E402

MAX_CHARS = 1500
LONG_RUNNING_CATEGORIES = {"compilation", "paquets", "conteneurs", "dev"}


# --------------------------------------------------------------------------- I/O

def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def scan_and_drop(rows: list[dict], names) -> tuple[list[dict], int]:
    """Filet de sécurité (comme finalize_labels.py) : un digest ou une compaction peut
    tronquer un chemin déjà anonymisé pile après « /home/user » ou « /Users/user » et
    laisser un fragment (« /home/u ») que le scanner générique ne reconnaît plus comme
    le mot « user » complet - rare, jamais une vraie fuite mesurée ici, mais on ne
    publie que ce qui scanne à 0, jamais ce qu'on a seulement expliqué."""
    kept, dropped = [], 0
    for row in rows:
        text = "\n".join(m["content"] for m in row["messages"])
        if scan_text(text, names):
            dropped += 1
            continue
        kept.append(row)
    return kept, dropped


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def tag_ids(records: list[dict], prefix: str) -> list[dict]:
    for i, r in enumerate(records):
        r.setdefault("id", f"{prefix}:{r.get('machine', prefix)}:{i}")
    return records


def sample(records: list[dict], n: int, seed: int = 42) -> list[dict]:
    pool = list(records)
    random.Random(seed).shuffle(pool)
    return pool[:n]


# --------------------------------------------------------------------------- digest commun

def _digest_or_compact(cmd: str, output: str, max_chars: int = MAX_CHARS, lang: str = "fr") -> str:
    lines = output.splitlines()
    return digest(cmd, output, max_chars, lang) or compact_output(lines, max_chars)


def _source(name: str, lang: str) -> str:
    # suffixe « .en » : convention de build_dataset_release.language_for_source
    return name + (".en" if lang == "en" else "")


# --------------------------------------------------------------------------- F10 (détail)

def detail_entry(rec: dict, lang: str = "fr") -> dict:
    out = _digest_or_compact(rec["cmd"], rec["output"], MAX_CHARS, lang)
    messages = details_messages(rec["cmd"], rec["exit"], rec["duration"], out, len(rec["output"].splitlines()),
                                language=lang)
    return {"source": _source("detail", lang), "mode": "detail", "id": rec.get("id"), "machine": rec.get("machine"),
            "category": rec.get("category"), "messages": messages}


# --------------------------------------------------------------------------- annonce de début

def start_entry(rec: dict, lang: str = "fr") -> dict:
    messages = start_messages(rec["cmd"], language=lang)
    return {"source": _source("start", lang), "mode": "start", "id": rec.get("id"), "machine": rec.get("machine"),
            "category": rec.get("category"), "messages": messages}


# --------------------------------------------------------------------------- progression

def progress_windows(output: str, duration: float, fractions: tuple[float, ...] = (0.3, 0.6, 0.9),
                     min_total_lines: int = 12, tail: int = 15) -> list[tuple[float, str]]:
    """Fenêtres glissantes d'une sortie déjà captée, jusqu'au bout : simule ce que steph
    verrait à différents instants d'une commande encore en cours (P11/H2 : « fenêtres
    glissantes des sorties longues existantes »). Pure, sans effet de bord."""
    lines = [l for l in output.splitlines() if l.strip()]
    if len(lines) < min_total_lines:
        return []
    windows = []
    for frac in fractions:
        cutoff = max(1, int(len(lines) * frac))
        recent = "\n".join(lines[max(0, cutoff - tail):cutoff])
        elapsed = max(1.0, duration * frac)
        windows.append((elapsed, recent))
    return windows


def progress_entries(rec: dict, lang: str = "fr") -> list[dict]:
    entries = []
    for i, (elapsed, recent) in enumerate(progress_windows(rec["output"], rec["duration"])):
        messages = progress_messages(rec["cmd"], elapsed, recent, language=lang)
        entries.append({"source": _source("progress", lang), "mode": "progress", "id": f"{rec.get('id')}:w{i}",
                        "machine": rec.get("machine"), "category": rec.get("category"), "messages": messages})
    return entries


# --------------------------------------------------------------------------- erreurs multiples / tests

def summary_residual(records: list[dict]) -> tuple[list[dict], dict]:
    """`resolve()` répond déjà en code (P4/P12 + H3a : ESLint, vitest) pour la plupart
    des builds et suites de tests captés : ces cas-là n'atteignent jamais le LLM en
    production, donc pas de place au corpus. Seul le résidu (resolve() -> None) est
    gardé : c'est la seule part qui verrait vraiment le modèle."""
    kept, stats = [], {"total": 0, "resolved_in_code": 0, "residual": 0}
    for r in records:
        stats["total"] += 1
        if resolve(r["cmd"], r["exit"], r["output"]) is not None:
            stats["resolved_in_code"] += 1
            continue
        stats["residual"] += 1
        kept.append(r)
    return kept, stats


def summary_entry(rec: dict) -> dict:
    messages = build_messages(rec, MAX_CHARS)
    return {"source": "summary_residual", "mode": "summary", "id": rec.get("id"), "machine": rec.get("machine"),
            "category": rec.get("category"), "messages": messages}


# --------------------------------------------------------------------------- flux (journaux en continu)

def flux_deltas(output: str, n_windows: int = 4) -> list[list[str]]:
    """Découpe une capture de flux continu en tranches successives de lignes : chaque
    tranche simule ce qui vient d'apparaître depuis le point d'étape précédent. Pure."""
    lines = [l for l in output.splitlines() if l.strip()]
    if not lines:
        return []
    n_windows = max(1, min(n_windows, len(lines)))
    size = max(1, -(-len(lines) // n_windows))  # ceil
    return [lines[i:i + size] for i in range(0, len(lines), size)][:n_windows]


def flux_entries(rec: dict, step_seconds: float = 20.0) -> list[dict]:
    entries = []
    for i, delta in enumerate(flux_deltas(rec["output"])):
        text = flux_window(delta)
        if not text:
            continue
        elapsed = (i + 1) * step_seconds
        messages = progress_messages(rec["cmd"], elapsed, text)
        entries.append({"source": "flux", "mode": "flux", "id": f"{rec.get('id')}:w{i}",
                        "machine": rec.get("machine"), "category": rec.get("category"), "messages": messages})
    return entries


# --------------------------------------------------------------------------- CLI

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--corpus-dir", default="corpus", type=Path)
    ap.add_argument("--out-dir", default="corpus/features", type=Path)
    ap.add_argument("--n-detail", type=int, default=800)
    ap.add_argument("--n-start", type=int, default=400)
    ap.add_argument("--n-progress-sources", type=int, default=250,
                    help="enregistrements sources (avant fenêtrage, ~3 fenêtres chacun)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--lang", choices=("fr", "en"), default="fr",
                    help="en : captures anglaises de K2 (*.en.jsonl), prompts anglais, fichiers *.en.jsonl ; "
                         "ni résidu ni flux (aucune capture anglaise de ce type)")
    ap.add_argument("--names", default=None,
                    help="défaut : STEPH_PII_NAMES ou ~/.config/steph/pii_names.tsv (audit_pii.py)")
    args = ap.parse_args()

    names = load_names(args.names or os.environ.get("STEPH_PII_NAMES", DEFAULT_NAMES))

    lang = args.lang
    suffix = ".en" if lang == "en" else ""
    existing_files = (["macos.en.jsonl", "linux-low.en.jsonl"] if lang == "en"
                      else ["macos.jsonl", "linux-low.jsonl", "linux-dev.jsonl"])
    existing = []
    for name in existing_files:
        existing += tag_ids(read_jsonl(args.corpus_dir / name), name.removesuffix(".jsonl"))
    print(f"corpus existant (résumé) : {len(existing)} enregistrements ({', '.join(existing_files)})")

    feature_files = [] if lang == "en" else ["features-macos.jsonl", "features-linux-low.jsonl"]
    features = []
    for name in feature_files:
        features += tag_ids(read_jsonl(args.corpus_dir / name), name.removesuffix(".jsonl"))
    print(f"corpus H3a (erreurs/tests/flux) : {len(features)} enregistrements ({', '.join(feature_files)})")

    total_dropped = 0

    def finish(label: str, filename: str, rows: list[dict]) -> list[dict]:
        nonlocal total_dropped
        kept, dropped = scan_and_drop(rows, names)
        total_dropped += dropped
        write_jsonl(args.out_dir / filename, kept)
        extra = f" ({dropped} écartée(s) par le scanner)" if dropped else ""
        print(f"{label} : {len(kept)} entrées{extra} -> {args.out_dir / filename}")
        return kept

    # ---- détail (F10) ----
    detail_pool = sample(existing, min(args.n_detail, len(existing)), args.seed)
    detail_rows = finish("détail", f"detail{suffix}.jsonl", [detail_entry(r, lang) for r in detail_pool])

    # ---- début ----
    start_pool = sample(existing, min(args.n_start, len(existing)), args.seed + 1)
    start_rows = finish("début", f"start{suffix}.jsonl", [start_entry(r, lang) for r in start_pool])

    # ---- progression (fenêtres glissantes de sorties longues existantes) ----
    long_running = [r for r in existing if r.get("category") in LONG_RUNNING_CATEGORIES]
    progress_pool = sample(long_running, min(args.n_progress_sources, len(long_running)), args.seed + 2)
    progress_rows = finish("progression", f"progress{suffix}.jsonl",
                           [e for r in progress_pool for e in progress_entries(r, lang)])
    print(f"  ({len(progress_pool)} sources longues avant fenêtrage)")

    if lang == "en":
        total = len(detail_rows) + len(start_rows) + len(progress_rows)
        print(f"TOTAL entrées prêtes pour l'étiquetage : {total} ({total_dropped} écartée(s) au total par le scanner)")
        return 0

    # ---- erreurs multiples / résultats de tests (résidu non résolu en code) ----
    err_test = [r for r in features if r.get("category") in ("errors", "tests")]
    residual, stats = summary_residual(err_test)
    summary_rows = finish("erreurs/tests", "summary_residual.jsonl", [summary_entry(r) for r in residual])
    print(f"  (couverture resolve() : {json.dumps(stats, ensure_ascii=False)})")

    # ---- flux (journaux en continu) ----
    flux_sources = [r for r in features if r.get("category") == "flux"]
    flux_rows = finish("flux", "flux.jsonl", [e for r in flux_sources for e in flux_entries(r)])
    print(f"  ({len(flux_sources)} sources avant fenêtrage)")

    total = len(detail_rows) + len(start_rows) + len(progress_rows) + len(summary_rows) + len(flux_rows)
    print(f"TOTAL entrées prêtes pour l'étiquetage : {total} ({total_dropped} écartée(s) au total par le scanner)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
