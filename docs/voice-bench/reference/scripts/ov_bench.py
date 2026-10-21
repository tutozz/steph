#!/usr/bin/env python3
"""Mesure TTFT/total/tokens-s/RAM pour un modele OpenVINO int4 (openvino_genai), CPU seul."""
import argparse
import json
import resource
import statistics
import sys
import time

sys.path.insert(0, "/root/stephbench/src")
from prompts import summary_messages
from textproc import compact_output

import openvino_genai as ov_genai

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
    return [f for f in fx if f["cmd"] in SUBSET_CMDS or f["cmd"].startswith("python3 -c")]


def cgroup_peak():
    try:
        with open("/proc/self/cgroup") as fh:
            line = fh.readline().strip()
        path = line.split(":")[-1]
        with open(f"/sys/fs/cgroup{path}/memory.peak") as fh:
            return int(fh.read().strip()) // 1024
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model-dir", required=True)
    ap.add_argument("--threads", type=int, required=True)
    ap.add_argument("--maxc", type=int, default=6000)
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--label", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--no-think", action="store_true", help="force un bloc <think> vide (modeles Qwen)")
    args = ap.parse_args()

    fixtures = load_fixtures(args.full)
    if not fixtures:
        print(f"ERREUR {args.label} : aucune fixture", file=sys.stderr)
        sys.exit(1)

    t0 = time.time()
    try:
        pipe = ov_genai.LLMPipeline(args.model_dir, "CPU", INFERENCE_NUM_THREADS=args.threads)
    except TypeError:
        pipe = ov_genai.LLMPipeline(args.model_dir, "CPU")
    load_time = time.time() - t0

    gen_cfg = pipe.get_generation_config()
    gen_cfg.max_new_tokens = 80
    gen_cfg.temperature = 0.2
    gen_cfg.top_p = 0.9
    gen_cfg.do_sample = True
    # sinon generate() re-applique le gabarit par-dessus notre prompt deja
    # forme (et le forcage du <think> vide se retrouve hors position)
    gen_cfg.apply_chat_template = False

    tok = pipe.get_tokenizer()

    def build_prompt(msgs):
        # extra_context={"enable_thinking": False} n'est pas fiable selon les
        # bindings openvino_genai (teste : ignore silencieusement le kwarg) ;
        # on force donc un bloc <think> vide, comme --reasoning-budget 0 de
        # llama.cpp, si le gabarit du modele connait le thinking.
        prompt = tok.apply_chat_template(msgs, True)
        if args.no_think and prompt.rstrip().endswith("<|im_start|>assistant"):
            prompt = prompt.rstrip() + "\n<think>\n\n</think>\n\n"
        return prompt

    def run_one(prompt, max_tokens):
        cfg = gen_cfg
        cfg.max_new_tokens = max_tokens
        t0 = time.time()
        state = {}
        parts = []

        def streamer(piece):
            if "first" not in state:
                state["first"] = time.time() - t0
            parts.append(piece)
            return False

        pipe.generate(prompt, cfg, streamer=streamer)
        total = time.time() - t0
        text = "".join(parts).strip()
        return state.get("first"), total, text, len(parts)

    # rechauffe
    run_one(build_prompt([{"role": "user", "content": "Bonjour"}]), 10)

    rows = []
    early_ttft = []
    aborted = False
    for i, f in enumerate(fixtures):
        lines = f["output"].splitlines()
        msgs = summary_messages(
            f["cmd"], f["exit"], f["duration"], compact_output(lines, args.maxc), len(lines)
        )
        prompt = build_prompt(msgs)
        try:
            first, total, text, ntok = run_one(prompt, 80)
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

    hwm = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    peak = cgroup_peak()

    ttfts = [r["ttft"] for r in rows if "ttft" in r]
    totals = [r["total"] for r in rows if "total" in r]
    toksecs = [r["toksec"] for r in rows if "toksec" in r]
    result = {
        "label": args.label, "engine": "openvino", "model": args.model_dir, "threads": args.threads,
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
