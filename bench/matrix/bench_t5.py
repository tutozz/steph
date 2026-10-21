"""Banc pour les encodeurs-décodeurs (T5) : llama-server ne sait pas les servir.

llama-server n'appelle jamais llama_encode() : un GGUF T5 y produit du bruit. Ce banc lance
donc llama-completion une fois par cas, sur le message utilisateur seul (pas de gabarit de
chat), et produit un JSON lisible par score.py :

    python3 bench_t5.py --bin ~/llama/llama-completion --model m.gguf --label i5-t5 --threads 4 \
        --cases cases.json --out results/i5-t5.json

Deux premiers mots par cas : ``ttft`` mesure le processus entier (chargement compris, ce que
paierait steph en relançant llama-completion à chaque commande) ; ``ttft_resident`` retire le
temps de chargement du modèle, estimation de ce que paierait un processus résident (llama.cpp
ne compte pas l'encodeur dans « prompt eval time », d'où cette soustraction).
"""

import argparse
import json
import re
import statistics
import subprocess
import tempfile
import time
from pathlib import Path

from bench_run import sysinfo

HERE = Path(__file__).parent

NUM = r"(\d+(?:[.,]\d+)?)"
PERF = {
    "load_ms": rf"load time =\s*{NUM} ms",
    "prompt_ms": rf"prompt eval time =\s*{NUM} ms",
    "prompt_n": rf"prompt eval time =\s*{NUM} ms /\s*(\d+) tokens",
    "eval_ms": rf"\n[^\n]*?\beval time =\s*{NUM} ms",
    "gen_n": rf"\n[^\n]*?\beval time =\s*{NUM} ms /\s*(\d+) runs",
    "gen_tok_s": rf"\n[^\n]*?\beval time =[^\n]*?{NUM} tokens per second",
}


def parse_perf(log: str) -> dict:
    found = {}
    for key, pattern in PERF.items():
        matches = [m for m in re.finditer(pattern, log) if "prompt eval" not in m.group(0) or key.startswith("prompt")]
        if matches:
            value = matches[-1].groups()[-1]
            found[key] = int(value) if key.endswith("_n") else float(value.replace(",", "."))
    return found


def completion_cmd(binary: str, model: str, prompt_file: str, n_predict: int, threads: int, ctx: int,
                   seed: int, repeat_penalty: float, temperature: float) -> list:
    return [binary, "-m", model, "-f", prompt_file, "-no-cnv", "--no-display-prompt", "-n", str(n_predict),
            "-t", str(threads), "-c", str(ctx), "-b", str(ctx), "-ub", str(ctx), "-ngl", "0", "-s", str(seed), "--temp", str(temperature),
            "--top-p", "0.9", "--repeat-penalty", str(repeat_penalty)]


def run_case(cmd: list, timeout: float) -> dict:
    t0 = time.time()
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    first, chunks = None, []
    while True:
        b = proc.stdout.read1(4096) if hasattr(proc.stdout, "read1") else proc.stdout.read(1)
        if not b:
            break
        if first is None and b.strip():
            first = time.time() - t0
        chunks.append(b)
        if time.time() - t0 > timeout:
            proc.kill()
            break
    err = proc.stderr.read().decode("utf-8", "replace")
    proc.wait()
    total = time.time() - t0
    out = b"".join(chunks).decode("utf-8", "replace").replace("[end of text]", "").strip()
    row = {"ttft": round(first or total, 3), "total": round(total, 3), "out": out, **parse_perf(err)}
    if proc.returncode:
        row["error"] = " | ".join(l for l in err.splitlines() if " E " in l or "GGML_ASSERT" in l)[-300:]
    return row


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--cases", default=str(HERE / "cases.json"))
    ap.add_argument("--maxc", type=int, default=1500)
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--ctx", type=int, default=4096)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--repeat-penalty", type=float, default=1.1)
    ap.add_argument("--temperature", type=float, default=0.2)
    ap.add_argument("--timeout", type=float, default=180.0)
    a = ap.parse_args()

    from train_seq2seq import to_pair

    cases = [c for c in json.load(open(a.cases)) if c["kind"] == "qa" or c["maxc"] == a.maxc]
    result = {"label": a.label, "sys": sysinfo(), "config": vars(a), "runtime": "llama-completion", "rows": []}
    with tempfile.TemporaryDirectory() as tmp:
        prompt = Path(tmp) / "prompt.txt"
        for i, c in enumerate([cases[0]] + cases):
            prompt.write_text(to_pair(c["messages"])[0])
            n = 120 if c["kind"] == "qa" else 80
            row = run_case(completion_cmd(a.bin, a.model, str(prompt), n, a.threads, a.ctx, a.seed,
                                          a.repeat_penalty, a.temperature), a.timeout)
            if i == 0:
                continue
            row["ttft_resident"] = round(max(0.0, row["ttft"] - row.get("load_ms", 0) / 1000), 3)
            result["rows"].append({"id": c["id"], "fixture": c["fixture"], "kind": c["kind"], **row})
            print(f"{c['id']}: {row['ttft']} s | {row['out'][:90]}", flush=True)
    rows = result["rows"]
    for key in ("ttft", "ttft_resident", "total"):
        vals = sorted(r[key] for r in rows)
        result[f"{key}_median"] = round(statistics.median(vals), 3)
        result[f"{key}_p90"] = round(vals[min(len(vals) - 1, int(0.9 * len(vals)))], 3)
    result["load_ms_median"] = statistics.median(r.get("load_ms", 0) for r in rows)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    json.dump(result, open(a.out, "w"), ensure_ascii=False, indent=1)
    print(f"{a.label}: ttft p90 {result['ttft_p90']} résident p90 {result['ttft_resident_p90']} "
          f"total médian {result['total_median']}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
