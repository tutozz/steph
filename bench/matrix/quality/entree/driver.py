"""Pilote un lot d'essais axe C (entree) : genere les cas, lance sur homelab, rapatrie,
note le score, ecrit le journal. Invariants homelab a chaque commande (nice -n 19, dossiers
autorises, pas de VM/apt). Un essai = un JSON dans results/quality/entree/ + une ligne de
journal.tsv.

    python3 driver.py <fichier_lot.json>

Chaque entree du lot : {label, maxc, model, modeltag, profile, opts:{...}, note}
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(".")
MATRIX = ROOT / "bench" / "matrix"
QDIR = MATRIX / "quality" / "entree"
RESULTS = MATRIX / "results" / "quality" / "entree"
JOURNAL = RESULTS / "journal.tsv"
SERVER = "/root/stephbench-matrix/bin/vulkan/llama-b11205/llama-server"
REMOTE_DIR = "/root/stephbench-matrix/quality-c"
PORT = 8870

sys.path.insert(0, str(MATRIX))
import score as S  # noqa: E402

_run_no = [0]


def sh(cmd: list[str], timeout: int = 240) -> str:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(f"echec {cmd}: {r.stderr[-2000:]}")
    return r.stdout


def run_one(spec: dict) -> dict:
    label, maxc, model, tag, profile = spec["label"], spec["maxc"], spec["model"], spec["modeltag"], spec["profile"]
    opts = spec.get("opts", {})
    run_label = f"q-entree-{tag}-{label}"
    gen_args = ["python3", str(QDIR / "gen_cases.py"), label, str(maxc), f"profile={profile}"]
    gen_args += [f"{k}={v}" for k, v in opts.items()]
    sh(gen_args)
    local_cases = QDIR / f"cases_{label}.json"
    remote_cases = f"{REMOTE_DIR}/cases_{label}.json"
    sh(["scp", "-q", str(local_cases), f"homelab:{remote_cases}"])
    remote_out = f"{REMOTE_DIR}/results/{run_label}.json"
    bench_cmd = (
        f"cd {REMOTE_DIR} && nice -n 19 python3 bench_run.py --server {SERVER} --model {model} "
        f"--label {run_label} --cases {remote_cases} --maxc {maxc} --port {PORT} --ngl 99 "
        f"--device Vulkan0 --out {remote_out}"
    )
    sh(["ssh", "homelab", bench_cmd], timeout=240)
    local_out = RESULTS / f"{run_label}.json"
    sh(["scp", "-q", f"homelab:{remote_out}", str(local_out)])
    tune = S.score_result(str(local_out), True, "tune")
    hold = S.score_result(str(local_out), True, "holdout")
    _run_no[0] += 1
    line = f"{_run_no[0]}\t{tag}\t{label} ({spec.get('note', '')})\t{tune['quality']}\t{hold['quality']}\t{spec.get('note', '')}\n"
    RESULTS.mkdir(parents=True, exist_ok=True)
    with open(JOURNAL, "a") as f:
        f.write(line)
    result = {"label": run_label, "tune": tune["quality"], "holdout": hold["quality"], "n_tune": tune["n"]}
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return result


def main() -> None:
    batch = json.load(open(sys.argv[1]))
    # numero de reprise : compte les lignes deja ecrites
    if JOURNAL.exists():
        _run_no[0] = max(0, sum(1 for _ in open(JOURNAL)) - 1)  # -1 : ligne d'entete
    for spec in batch:
        try:
            run_one(spec)
        except Exception as e:
            print(f"ERREUR {spec.get('label')}: {e}", file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
