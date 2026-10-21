#!/usr/bin/env python3
"""Mesure TTFT/total/tokens-s/RAM pour un modele GGUF servi par llama-server, CPU seul."""
import argparse
import http.client
import json
import os
import signal
import statistics
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, "/root/stephbench/src")
from prompts import summary_messages
from textproc import compact_output

SUBSET_CMDS = {
    "npm run build",
    "sudo apt upgrade -y",
    "cat /nonexistent/file.txt",
    "df -h",
    "git push",
    "ls -la /etc | head -40",
    "docker ps",
}


def load_fixtures(full=False):
    fx = json.load(open("/root/stephbench/src/fixtures.json")) + json.load(
        open("/root/stephbench/src/extra_fixtures.json")
    )
    if full:
        return fx
    out = [f for f in fx if f["cmd"] in SUBSET_CMDS or f["cmd"].startswith("python3 -c")]
    return out


def vmhwm(pid):
    try:
        with open(f"/proc/{pid}/status") as fh:
            for line in fh:
                if line.startswith("VmHWM"):
                    return int(line.split()[1])
    except (FileNotFoundError, ProcessLookupError):
        return None
    return None


def cgroup_peak():
    try:
        with open("/proc/self/cgroup") as fh:
            line = fh.readline().strip()
        path = line.split(":")[-1]
        with open(f"/sys/fs/cgroup{path}/memory.peak") as fh:
            return int(fh.read().strip()) // 1024
    except Exception:
        return None


def start_server(model_path, port, threads, engine_dir):
    exe = f"{engine_dir}/llama-server"
    args = [
        exe, "-m", model_path, "--host", "127.0.0.1", "--port", str(port),
        "-c", "4096", "-ngl", "0", "-t", str(threads), "--jinja",
        "--reasoning-budget", "0", "--no-webui",
    ]
    log = open(f"/root/stephbench/logs/server_{port}.log", "ab")
    env = dict(os.environ)
    env["LD_LIBRARY_PATH"] = f"{engine_dir}:{env.get('LD_LIBRARY_PATH', '')}"
    return subprocess.Popen(args, stdout=log, stderr=log, env=env, start_new_session=True)


def wait_health(port, timeout=180):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1) as r:
                if r.status == 200:
                    return time.time() - t0
        except Exception:
            pass
        time.sleep(0.3)
    return None


def payload(messages, max_tokens):
    return {
        "messages": messages, "max_tokens": max_tokens, "temperature": 0.2,
        "top_p": 0.9, "stream": True, "cache_prompt": True,
        "chat_template_kwargs": {"enable_thinking": False},
    }


def stream_call(port, messages, max_tokens=80, timeout=90):
    body = json.dumps(payload(messages, max_tokens))
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    t0 = time.time()
    first = None
    text = ""
    ntok = 0
    try:
        conn.request("POST", "/v1/chat/completions", body=body, headers={"Content-Type": "application/json"})
        r = conn.getresponse()
        if r.status != 200:
            raise ConnectionError(f"HTTP {r.status}: {r.read()[:300]!r}")
        for raw in r:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                delta = json.loads(data)["choices"][0].get("delta", {})
            except Exception:
                continue
            piece = delta.get("content")
            if piece:
                if first is None:
                    first = time.time() - t0
                text += piece
                ntok += 1
    finally:
        conn.close()
    total = time.time() - t0
    return first, total, text.strip(), ntok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--engine-dir", required=True)
    ap.add_argument("--threads", type=int, required=True)
    ap.add_argument("--port", type=int, default=8812)
    ap.add_argument("--maxc", type=int, default=6000)
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--label", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    fixtures = load_fixtures(args.full)
    if not fixtures:
        print(f"ERREUR {args.label} : aucune fixture", file=sys.stderr)
        sys.exit(1)

    proc = start_server(args.model, args.port, args.threads, args.engine_dir)
    load_time = wait_health(args.port, 180)
    if load_time is None:
        try:
            proc.terminate()
        except Exception:
            pass
        json.dump({"label": args.label, "status": "load_fail"}, open(args.out, "w"), indent=1)
        print(f"FIN {args.label} CHARGEMENT ECHOUE")
        return

    stream_call(args.port, [{"role": "user", "content": "Bonjour"}], 10)

    rows = []
    early_ttft = []
    aborted = False
    for i, f in enumerate(fixtures):
        lines = f["output"].splitlines()
        msgs = summary_messages(
            f["cmd"], f["exit"], f["duration"], compact_output(lines, args.maxc), len(lines)
        )
        try:
            first, total, text, ntok = stream_call(args.port, msgs, 80)
        except Exception as e:
            rows.append({"cmd": f["cmd"], "error": str(e)})
            continue
        rows.append({
            "cmd": f["cmd"], "ttft": round(first or 0, 3), "total": round(total, 3),
            "ntok": ntok, "toksec": round(ntok / total, 2) if total > 0 else 0, "out": text,
        })
        if i < 2 and first is not None:
            early_ttft.append(first)
        if len(early_ttft) == 2 and statistics.median(early_ttft) > 15:
            aborted = True
            break

    server_pid = proc.pid
    hwm = vmhwm(server_pid)
    peak = cgroup_peak()

    try:
        proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=10)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass

    ttfts = [r["ttft"] for r in rows if "ttft" in r]
    totals = [r["total"] for r in rows if "total" in r]
    toksecs = [r["toksec"] for r in rows if "toksec" in r]
    result = {
        "label": args.label, "model": args.model, "threads": args.threads,
        "maxc": args.maxc, "full": args.full, "load_s": round(load_time, 2),
        "aborted_unusable": aborted, "n_fixtures": len(fixtures), "n_done": len(rows),
        "ttft_median": round(statistics.median(ttfts), 3) if ttfts else None,
        "ttft_max": round(max(ttfts), 3) if ttfts else None,
        "total_median": round(statistics.median(totals), 3) if totals else None,
        "toksec_median": round(statistics.median(toksecs), 3) if toksecs else None,
        "ram_vmhwm_kb": hwm, "ram_cgroup_peak_kb": peak,
        "rows": rows,
    }
    json.dump(result, open(args.out, "w"), ensure_ascii=False, indent=1)
    print(
        f"FIN {args.label} load={load_time:.1f}s ttft_med={result['ttft_median']} "
        f"total_med={result['total_median']} toksec={result['toksec_median']} "
        f"ram_kb={hwm} aborted={aborted}"
    )


if __name__ == "__main__":
    main()
