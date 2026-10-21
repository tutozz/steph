#!/usr/bin/env python3
"""Mesure RAM (pic et repos) et TTFT de llama-server, un jeu de réglages CLI à la fois.

Q2c (docs/mission-finetune.md) : comprendre pourquoi Granite 4.0 H 350M Q4_K_M pèse
~2,5 Go de RSS sur l'i5-7200U (fichier GGUF de 223 Mo) et tester des réglages pour réduire
ce poids sans perdre en vitesse ni en qualité.

Reprend le protocole de requête de bench/matrix/bench_run.py (cache_prompt, slot 0,
température 0,2, cases.json), mais ajoute deux mesures que bench_run.py ne fait pas :

- « repos avant » : RSS juste après /health, avant la première requête (charge du modèle et
  repack CPU compris, aucune requête traitée).
- « repos après » : RSS 2 s après la dernière requête, serveur inactif, tous les buffers de
  calcul déjà alloués (contrairement à « repos avant », le premier passage peut allouer des
  buffers supplémentaires à la première requête).
- « pic » : maximum RSS échantillonné en continu (0,2 s) pendant tout le run, comme
  bench_run.py.

Exemple :
    python3 granite_ram.py --server /root/stephbench-g2/bin/llama-b11205/llama-server \\
        --model models/p15-granite-uniform-Q4_K_M.gguf --label p15-baseline \\
        --out results/p15-baseline.json --cases /root/stephbench-ft/cases_ft36.json \\
        --ctx 4096 --ubatch 64 --batch 512 --parallel 1 --threads 4 --extra "--no-repack"
"""

import argparse
import json
import os
import signal
import statistics
import subprocess
import threading
import time
import urllib.request
from pathlib import Path


def rss_mb(pid: int) -> int:
    try:
        out = subprocess.run(["ps", "-o", "rss=", "-p", str(pid)], capture_output=True, text=True).stdout
        return int(out.strip() or 0) // 1024
    except Exception:
        return 0


class PeakSampler(threading.Thread):
    def __init__(self, pid: int, interval: float = 0.2):
        super().__init__(daemon=True)
        self.pid, self.interval, self.peak_mb, self.stop_flag = pid, interval, 0, False

    def run(self):
        while not self.stop_flag:
            self.peak_mb = max(self.peak_mb, rss_mb(self.pid))
            time.sleep(self.interval)


def post_stream(port: int, messages: list, max_tokens: int, timeout: float, payload: dict | None = None):
    body = json.dumps({
        "messages": messages, "max_tokens": max_tokens, "temperature": 0.2, "top_p": 0.9,
        "stream": True, "cache_prompt": True, "id_slot": 0, "seed": 42,
        "chat_template_kwargs": {"enable_thinking": False},
        **(payload or {}),
    }).encode()
    req = urllib.request.Request(f"http://127.0.0.1:{port}/v1/chat/completions", body,
                                  {"Content-Type": "application/json"})
    t0 = time.time()
    first, text, timings = None, "", {}
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        for raw in resp:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data: ") or line == "data: [DONE]":
                continue
            chunk = json.loads(line[6:])
            timings = chunk.get("timings") or timings
            for ch in chunk.get("choices", []):
                piece = (ch.get("delta") or {}).get("content") or ""
                if piece and first is None:
                    first = time.time() - t0
                text += piece
    return first, time.time() - t0, text.strip(), timings


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--cases", required=True)
    ap.add_argument("--maxc", type=int, default=1500)
    ap.add_argument("--port", type=int, default=8899)
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--ctx", type=int, default=4096)
    ap.add_argument("--batch", type=int, default=512)
    ap.add_argument("--ubatch", type=int, default=64)
    ap.add_argument("--parallel", type=int, default=1)
    ap.add_argument("--cache-type", default="f16")
    ap.add_argument("--extra", default="", help="arguments llama-server en plus (--no-repack, -lm none, ...)")
    ap.add_argument("--timeout", type=float, default=180.0)
    ap.add_argument("--settle-s", type=float, default=2.0, help="attente avant l'échantillon repos")
    a = ap.parse_args()

    cases = [c for c in json.load(open(a.cases)) if c["kind"] == "qa" or a.maxc == 0 or c["maxc"] == a.maxc]
    cmd = [a.server, "-m", a.model, "--host", "127.0.0.1", "--port", str(a.port), "-c", str(a.ctx),
           "-ngl", "0", "--no-webui", "--jinja", "--reasoning-budget", "0",
           "-b", str(a.batch), "-ub", str(a.ubatch), "--parallel", str(a.parallel), "-t", str(a.threads)]
    if a.cache_type != "f16":
        cmd += ["-ctk", a.cache_type, "-ctv", a.cache_type]
    if a.extra:
        cmd += a.extra.split()

    result = {"label": a.label, "cmdline": cmd, "rows": []}
    out_path = Path(a.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    log = open(out_path.with_suffix(".server.log"), "w")
    t0 = time.time()
    srv = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    sampler = PeakSampler(srv.pid)
    sampler.start()
    try:
        while True:
            if srv.poll() is not None:
                result["error"] = "llama-server arrêté au chargement (voir .server.log)"
                return finish(result, out_path, sampler, srv.pid)
            try:
                if json.load(urllib.request.urlopen(f"http://127.0.0.1:{a.port}/health", timeout=2)).get("status") == "ok":
                    break
            except Exception:
                pass
            if time.time() - t0 > 300:
                result["error"] = "chargement plus long que 5 min"
                return finish(result, out_path, sampler, srv.pid)
            time.sleep(0.3)
        result["load_s"] = round(time.time() - t0, 2)

        time.sleep(a.settle_s)
        result["ram_repos_avant_mb"] = rss_mb(srv.pid)

        post_stream(a.port, cases[0]["messages"], 8, a.timeout)  # chauffe, comme steph
        for c in cases:
            try:
                ttft, total, out, tm = post_stream(a.port, c["messages"], 120 if c["kind"] == "qa" else 80, a.timeout)
            except Exception as e:
                result["rows"].append({"id": c["id"], "fixture": c["fixture"], "kind": c["kind"], "error": str(e)[:200], "out": None})
                continue
            result["rows"].append({
                "id": c["id"], "fixture": c["fixture"], "kind": c["kind"], "ttft": round(ttft or total, 3),
                "total": round(total, 3), "out": out,
                "prompt_n": tm.get("prompt_n"), "gen_n": tm.get("predicted_n"),
                "gen_tok_s": tm.get("predicted_per_second"),
            })

        time.sleep(a.settle_s)
        result["ram_repos_apres_mb"] = rss_mb(srv.pid)
        return finish(result, out_path, sampler, srv.pid)
    finally:
        try:
            os.killpg(srv.pid, signal.SIGTERM)
            srv.wait(timeout=20)
        except Exception:
            try:
                os.killpg(srv.pid, signal.SIGKILL)
            except Exception:
                pass


def finish(result: dict, out_path: Path, sampler: PeakSampler, pid: int) -> int:
    time.sleep(0.3)
    sampler.stop_flag = True
    rows = [r for r in result["rows"] if "ttft" in r]
    if rows:
        tt = sorted(r["ttft"] for r in rows)
        result["ttft_median"] = round(statistics.median(tt), 3)
        result["ttft_p90"] = round(tt[min(len(tt) - 1, int(0.9 * len(tt)))], 3)
        gen = [r["gen_tok_s"] for r in rows if r.get("gen_tok_s")]
        result["gen_tok_s_median"] = round(statistics.median(gen), 1) if gen else None
    result["ram_peak_mb"] = sampler.peak_mb
    json.dump(result, open(out_path, "w"), ensure_ascii=False, indent=1)
    print(f"{result['label']}: ttft {result.get('ttft_median')} p90 {result.get('ttft_p90')} "
          f"repos_avant {result.get('ram_repos_avant_mb')} repos_apres {result.get('ram_repos_apres_mb')} "
          f"pic {result.get('ram_peak_mb')} {result.get('error', '')}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
