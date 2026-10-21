"""Lanceur de banc portable : une configuration llama-server, tous les cas, un JSON.

Sans dépendance (Python 3.9+), pour tourner sur n'importe quelle machine de test :
    python3 bench_run.py --server ~/llama/llama-server --model m.gguf --label mac-metal-gemma \
        --ngl 99 --threads 6 --out results/mac-metal-gemma.json

Les requêtes reprennent celles de steph (src/steph/llm.py) : cache du prompt, raisonnement
coupé, slot 0, température 0,2. Les cas (cases.json) sont précalculés sur le Mac par
bench/matrix/make_cases.py, avec le tri et la compaction de steph.
"""

import argparse
import json
import os
import platform
import shutil
import signal
import socket
import statistics
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent


def progress(out: str, **state) -> None:
    """<out>.progress.json, réécrit à chaque étape : suivi en direct par le tableau de bord."""
    p = Path(out).with_suffix(".progress.json")
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps({**state, "t": round(time.time(), 1)}, ensure_ascii=False))
    tmp.replace(p)


def post_stream(port: int, messages: list, max_tokens: int, timeout: float, payload: dict | None = None):
    body = json.dumps({
        "messages": messages, "max_tokens": max_tokens, "temperature": 0.2, "top_p": 0.9,
        "stream": True, "cache_prompt": True, "id_slot": 0,
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


class Sampler(threading.Thread):
    """RAM du serveur (RSS) et mémoire GPU NVIDIA, au pic, toutes les 0,5 s."""

    def __init__(self, pid: int):
        super().__init__(daemon=True)
        self.pid, self.ram_mb, self.vram_mb, self.stop = pid, 0, 0, False

    def run(self):
        smi = shutil.which("nvidia-smi")
        while not self.stop:
            try:
                rss = subprocess.run(["ps", "-o", "rss=", "-p", str(self.pid)], capture_output=True, text=True).stdout
                self.ram_mb = max(self.ram_mb, int(rss.strip() or 0) // 1024)
                if smi:
                    q = subprocess.run([smi, "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                                       capture_output=True, text=True).stdout
                    self.vram_mb = max(self.vram_mb, max((int(x) for x in q.split() if x.isdigit()), default=0))
            except Exception:
                pass
            time.sleep(0.5)


def port_in_use(port: int) -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def sysinfo() -> dict:
    info = {"machine": platform.node(), "os": platform.platform(), "arch": platform.machine()}
    try:
        if Path("/proc/cpuinfo").exists():
            info["cpu"] = next(l.split(":", 1)[1].strip() for l in open("/proc/cpuinfo") if l.startswith("model name"))
        else:
            info["cpu"] = subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True, text=True).stdout.strip()
    except Exception:
        pass
    return info


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--cases", default=str(HERE / "cases.json"))
    ap.add_argument("--maxc", type=int, default=1500, help="budget de sortie à tester (0 = tous)")
    ap.add_argument("--port", type=int, default=8830)
    ap.add_argument("--ngl", default="0")
    ap.add_argument("--threads", type=int, default=0)
    ap.add_argument("--ctx", type=int, default=8192)
    ap.add_argument("--ubatch", type=int, default=512)
    ap.add_argument("--parallel", type=int, default=1)
    ap.add_argument("--flash-attn", default="auto", choices=["auto", "on", "off"])
    ap.add_argument("--cache-type", default="f16")
    # a hybrid Mamba model (Granite H) copies its whole recurrent state per prompt-cache checkpoint: several GB
    ap.add_argument("--cache-ram", default="0", help="--cache-ram de llama-server en Mo (0 = désactivé, comme la production affinée)")
    ap.add_argument("--device", default="", help="--device de llama-server (ex. Vulkan0)")
    ap.add_argument("--extra", default="", help="arguments llama-server en plus")
    ap.add_argument("--abort-ttft", type=float, default=15.0, help="médiane des 4 premiers cas au-delà : hors budget")
    ap.add_argument("--timeout", type=float, default=180.0)
    ap.add_argument("--payload", default="", help="JSON fusionné dans chaque requête (grammar, temperature, stop...)")
    a = ap.parse_args()

    cases = [c for c in json.load(open(a.cases)) if c["kind"] == "qa" or a.maxc == 0 or c["maxc"] == a.maxc]
    cmd = [a.server, "-m", a.model, "--host", "127.0.0.1", "--port", str(a.port), "-c", str(a.ctx),
           "-ngl", str(a.ngl), "--no-webui", "--jinja", "--reasoning-budget", "0",
           "-b", str(max(a.ubatch, 512)), "-ub", str(a.ubatch), "--parallel", str(a.parallel),
           "--cache-ram", str(a.cache_ram)]
    if a.threads:
        cmd += ["-t", str(a.threads)]
    if a.flash_attn != "auto":
        cmd += ["-fa", a.flash_attn]
    if a.cache_type != "f16":
        cmd += ["-ctk", a.cache_type, "-ctv", a.cache_type]
    if a.device:
        cmd += ["--device", a.device]
    cmd += a.extra.split()

    result = {"label": a.label, "sys": sysinfo(), "config": vars(a), "cmdline": cmd, "rows": []}
    if port_in_use(a.port):
        # our server could not bind and the run would silently query someone else's model
        result["error"] = f"port {a.port} déjà occupé par un autre serveur"
        print(result["error"], file=sys.stderr)
        return 1
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    log = open(Path(a.out).with_suffix(".server.log"), "w")
    t0 = time.time()
    progress(a.out, label=a.label, phase="chargement", done=0, total=len(cases))
    srv = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    sampler = Sampler(srv.pid)
    sampler.start()
    try:
        while True:
            if srv.poll() is not None:
                result["error"] = "llama-server arrêté au chargement (voir .server.log)"
                return finish(result, a.out, sampler)
            try:
                if json.load(urllib.request.urlopen(f"http://127.0.0.1:{a.port}/health", timeout=2)).get("status") == "ok":
                    break
            except Exception:
                pass
            if time.time() - t0 > 600:
                result["error"] = "chargement plus long que 10 min"
                return finish(result, a.out, sampler)
            time.sleep(0.5)
        result["load_s"] = round(time.time() - t0, 2)
        progress(a.out, label=a.label, phase="chauffe", done=0, total=len(cases), load_s=result["load_s"])
        post_stream(a.port, cases[0]["messages"], 8, a.timeout)  # chauffe, comme le préchauffage de steph
        for i, c in enumerate(cases):
            try:
                payload = {**(json.loads(a.payload) if a.payload else {}), **c.get("payload", {})}
                ttft, total, out, tm = post_stream(a.port, c["messages"], 120 if c["kind"] == "qa" else 80, a.timeout,
                                                   payload)
            except Exception as e:
                result["rows"].append({"id": c["id"], "fixture": c["fixture"], "kind": c["kind"], "error": str(e)[:200], "out": None})
                continue
            result["rows"].append({
                "id": c["id"], "fixture": c["fixture"], "kind": c["kind"], "ttft": round(ttft or total, 3),
                "total": round(total, 3), "out": out,
                "prompt_n": tm.get("prompt_n"), "prompt_ms": tm.get("prompt_ms"),
                "gen_n": tm.get("predicted_n"), "gen_tok_s": tm.get("predicted_per_second"),
            })
            tt = [r["ttft"] for r in result["rows"] if "ttft" in r]
            progress(a.out, label=a.label, phase="cas", done=i + 1, total=len(cases),
                     last_ttft=tt[-1] if tt else None,
                     ttft_median=round(statistics.median(tt), 3) if tt else None)
            if i == 3:
                first = [r["ttft"] for r in result["rows"] if "ttft" in r]
                if first and statistics.median(first) > a.abort_ttft:
                    result["out_of_budget"] = True
                    break
        return finish(result, a.out, sampler)
    finally:
        try:
            os.killpg(srv.pid, signal.SIGTERM)
            srv.wait(timeout=20)
        except Exception:
            try:
                os.killpg(srv.pid, signal.SIGKILL)
            except Exception:
                pass


def finish(result: dict, out: str, sampler: Sampler) -> int:
    sampler.stop = True
    state = "erreur" if result.get("error") else "hors budget" if result.get("out_of_budget") else "fini"
    progress(out, label=result["label"], phase=state, done=len(result["rows"]), total=len(result["rows"]))
    rows = [r for r in result["rows"] if "ttft" in r]
    if rows:
        tt = sorted(r["ttft"] for r in rows)
        result["ttft_median"] = round(statistics.median(tt), 3)
        result["ttft_p90"] = round(tt[min(len(tt) - 1, int(0.9 * len(tt)))], 3)
        result["total_median"] = round(statistics.median(r["total"] for r in rows), 3)
        gen = [r["gen_tok_s"] for r in rows if r.get("gen_tok_s")]
        result["gen_tok_s_median"] = round(statistics.median(gen), 1) if gen else None
    result["ram_peak_mb"], result["vram_peak_mb"] = sampler.ram_mb, sampler.vram_mb
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    json.dump(result, open(out, "w"), ensure_ascii=False, indent=1)
    print(f"{result['label']}: ttft {result.get('ttft_median')} p90 {result.get('ttft_p90')} "
          f"total {result.get('total_median')} ram {result['ram_peak_mb']} vram {result['vram_peak_mb']} "
          f"{'HORS BUDGET' if result.get('out_of_budget') else result.get('error', '')}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
