#!/usr/bin/env python3
"""Steph Speak Bench runner: ask a model to speak terminal outputs, score the answers, time them.

Standard library only (Python 3.9+). Works with any OpenAI-compatible server:

    python3 benchmark/run.py --base-url http://127.0.0.1:8080/v1 --model qwen3.5-2b --lang en --split test

Other modes, no server needed:

    python3 benchmark/run.py --reference            # scores the reference answers (expect 100)
    python3 benchmark/run.py --rescore results/x.json

SPDX-License-Identifier: MIT
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import platform
import re
import shutil
import statistics
import subprocess
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BENCHMARK = "steph-speak-bench"
HERE = Path(__file__).resolve().parent
DEFAULT_DATA = HERE / "data" / "v1"
DEFAULT_OUT = HERE / "results"
LANGS = ("en", "fr", "de", "es", "pt", "ru")


# ---------------------------------------------------------------- data

def load_config(data_dir: Path) -> dict:
    data_dir = Path(data_dir)
    return {"prompts": json.loads((data_dir / "prompts.json").read_text(encoding="utf-8")),
            "scoring": json.loads((data_dir / "scoring.json").read_text(encoding="utf-8"))}


SPLITS = ("dev", "test")


def case_files(data_dir: Path, lang: str, split: str = "all") -> list:
    return [Path(data_dir) / lang / f"{s}.jsonl" for s in SPLITS if split in ("all", s)]


def load_cases(data_dir: Path, lang: str, split: str = "all") -> list:
    return [json.loads(line) for path in case_files(data_dir, lang, split)
            for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def source_lines(case: dict) -> int:
    if case["task"] == "qa":
        return sum(len(h["output"].splitlines()) for h in case["history"])
    return len(case["output"].splitlines())


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# ---------------------------------------------------------------- prompt construction

def status_text(code, p: dict) -> str:
    if code is None:
        return p.get("status_unknown", "?")
    if code == 0:
        return p["status_ok"]
    if code == 130:
        return p["status_interrupted"]
    if code > 128:
        return p["status_signal"].format(code=code)
    return p["status_fail"].format(code=code)


def clip(text: str, budget: int, head_share: float, marker: str) -> str:
    """Head and tail of the output within `budget` characters, the middle replaced by a marker line."""
    text = text.rstrip("\n")
    if len(text) <= budget:
        return text
    lines = [line if len(line) <= budget // 2 else line[: budget // 2] for line in text.split("\n")]
    head_budget = int(budget * head_share)
    head, used = [], 0
    for line in lines:
        if used + len(line) + 1 > head_budget:
            break
        head.append(line)
        used += len(line) + 1
    tail, used = [], 0
    for line in reversed(lines[len(head):]):
        if used + len(line) + 1 > budget - head_budget:
            break
        tail.append(line)
        used += len(line) + 1
    tail.reverse()
    omitted = len(lines) - len(head) - len(tail)
    if omitted <= 0:
        return "\n".join(lines)
    return "\n".join(head + [marker.format(n=omitted)] + tail)


def build_messages(case: dict, prompts: dict) -> list:
    p, budget = prompts[case["lang"]], prompts["input"]
    if case["task"] == "qa":
        entries = []
        for h in case["history"]:
            out = clip(h["output"], budget["max_history_entry_chars"], budget["head_share"], p["omitted"])
            entries.append(p["history_entry"].format(cmd=h["cmd"], status=status_text(h["exit"], p),
                                                     output=out if out.strip() else p["empty_output"]))
        user = p["qa_user"].format(history="\n\n".join(entries), question=case["question"])
        return [{"role": "system", "content": p["qa_system"]}, {"role": "user", "content": user}]
    out = clip(case["output"], budget["max_output_chars"], budget["head_share"], p["omitted"])
    user = p["summary_user"].format(cmd=case["cmd"], status=status_text(case["exit"], p),
                                    duration=f"{case['duration']:.1f}", nlines=len(case["output"].splitlines()),
                                    output=out if out.strip() else p["empty_output"])
    return [{"role": "system", "content": p["summary_system"]}, {"role": "user", "content": user}]


def override_summary_system(prompts: dict, text: str) -> dict:
    """Replace the summary system prompt for every language, e.g. to score a fine-tuned
    model with the short system prompt it actually learned instead of Steph Speak Bench's own.
    The qa system prompt and every other key are left untouched."""
    return {lang: ({**p, "summary_system": text} if lang in LANGS else p) for lang, p in prompts.items()}


# ---------------------------------------------------------------- scoring (deterministic)

def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.replace("’", "'").replace("‘", "'").replace("ʼ", "'")
    lines = (re.sub(r"[^\S\n]+", " ", line).strip() for line in text.split("\n"))
    return "\n".join(line for line in lines if line)


def score_case(case: dict, answer: str, scoring: dict) -> dict:
    """1 point per expected fact found, 0 if any forbidden pattern matches, times length_penalty if too long."""
    text = normalize(answer or "")
    forbidden = [p for p in scoring["global_forbidden"] + case["forbidden"] if re.search(p, text)]
    hits = [bool(re.search(p, text)) for p in case["expected"]]
    words = len((answer or "").split())
    over = words > case["max_words"]
    score = 0.0 if forbidden else sum(hits) / len(hits)
    if over and not forbidden:
        score *= scoring["length_penalty"]
    return {"score": round(score, 4), "facts_hit": sum(hits), "facts_total": len(hits),
            "forbidden_hit": forbidden, "over_length": over, "words": words}


def percentile(values: list, q: float):
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(q * len(ordered)))]


def pct(x: float) -> float:
    return round(100 * x, 1)


def summarize(rows: list) -> dict:
    scored = [r for r in rows if "score" in r]

    def group(key):
        out = {}
        for name in sorted({r[key] for r in scored}):
            sub = [r["score"] for r in scored if r[key] == name]
            out[name] = {"n": len(sub), "score": pct(statistics.mean(sub))}
        return out

    timed = [r for r in rows if r.get("ttft") is not None]
    summary = {
        "n": len(scored),
        "score": pct(statistics.mean(r["score"] for r in scored)) if scored else None,
        "fact_recall": pct(sum(r["facts_hit"] for r in scored) / max(1, sum(r["facts_total"] for r in scored))),
        "forbidden_rate": pct(sum(bool(r["forbidden_hit"]) for r in scored) / max(1, len(scored))),
        "over_length_rate": pct(sum(r["over_length"] for r in scored) / max(1, len(scored))),
        "errors": sum(1 for r in rows if r.get("error")),
        "by_category": group("category"),
        "by_task": group("task"),
    }
    if timed:
        ttft, total = [r["ttft"] for r in timed], [r["total"] for r in timed]
        tok = [r["tok_s"] for r in timed if r.get("tok_s")]
        summary.update({
            "ttft_median_s": round(statistics.median(ttft), 3), "ttft_p90_s": round(percentile(ttft, 0.9), 3),
            "total_median_s": round(statistics.median(total), 3), "total_p90_s": round(percentile(total, 0.9), 3),
            "tok_s_median": round(statistics.median(tok), 1) if tok else None,
        })
    return summary


def judge_summary(rows: list) -> dict | None:
    judged = [r["judge"] for r in rows if isinstance(r.get("judge"), dict) and "verdict" in r["judge"]]
    failed = sum(1 for r in rows if isinstance(r.get("judge"), dict) and "error" in r["judge"])
    if not judged:
        return {"n": 0, "hallucination_rate": None, "judge_errors": failed}
    bad = sum(j["verdict"] == "hallucination" for j in judged)
    return {"n": len(judged), "hallucination_rate": pct(bad / len(judged)), "judge_errors": failed}


def rescore(result: dict, cases_by_id: dict, scoring: dict) -> dict:
    rows = []
    for row in result["rows"]:
        case = cases_by_id[row["id"]]
        rows.append({**row, **score_case(case, row.get("answer") or "", scoring)})
    return {**result, "rows": rows, "summary": summarize(rows)}


# ---------------------------------------------------------------- HTTP client

def http_json(url: str, api_key: str = "", body: dict | None = None, timeout: float = 5.0):
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    data = json.dumps(body).encode() if body is not None else None
    with urllib.request.urlopen(urllib.request.Request(url, data, headers), timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def chat_stream(base_url: str, api_key: str, body: dict, timeout: float) -> dict:
    """Stream one chat completion. TTFT is the delay to the first spoken character, reasoning excluded."""
    headers = {"Content-Type": "application/json", "Accept": "text/event-stream"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(f"{base_url.rstrip('/')}/chat/completions", json.dumps(body).encode(), headers)
    t0 = time.perf_counter()
    first, text, reasoning, usage, timings = None, [], [], None, None
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        for raw in resp:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                break
            chunk = json.loads(payload)
            usage = chunk.get("usage") or usage
            timings = chunk.get("timings") or timings
            for choice in chunk.get("choices") or []:
                delta = choice.get("delta") or {}
                piece = delta.get("content") or ""
                think = delta.get("reasoning_content") or delta.get("reasoning") or ""
                if think:
                    reasoning.append(think)
                if piece:
                    if first is None and piece.strip():
                        first = time.perf_counter() - t0
                    text.append(piece)
    total = time.perf_counter() - t0
    tokens = (usage or {}).get("completion_tokens") or (timings or {}).get("predicted_n")
    tok_s = (timings or {}).get("predicted_per_second")
    if not tok_s and tokens and first is not None and total > first:
        tok_s = tokens / (total - first)
    return {"answer": "".join(text).strip(), "reasoning": "".join(reasoning).strip() or None,
            "ttft": round(first if first is not None else total, 3), "total": round(total, 3),
            "completion_tokens": tokens, "tok_s": round(tok_s, 1) if tok_s else None}


# ---------------------------------------------------------------- machine and backend metadata

def run_quiet(cmd: list) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:
        return ""


def hardware() -> dict:
    info = {"os": platform.platform(terse=True), "arch": platform.machine(), "cpu_threads": os.cpu_count()}
    if Path("/proc/cpuinfo").exists():
        names = [l.split(":", 1)[1].strip() for l in open("/proc/cpuinfo") if l.startswith("model name")]
        info["cpu"] = names[0] if names else None
        mem = [l for l in open("/proc/meminfo") if l.startswith("MemTotal")]
        info["ram_gb"] = round(int(mem[0].split()[1]) / 1024 ** 2, 1) if mem else None
    elif sys.platform == "darwin":
        info["cpu"] = run_quiet(["sysctl", "-n", "machdep.cpu.brand_string"]) or None
        memsize = run_quiet(["sysctl", "-n", "hw.memsize"])
        info["ram_gb"] = round(int(memsize) / 1024 ** 3, 1) if memsize.isdigit() else None
    gpus = []
    if shutil.which("nvidia-smi"):
        out = run_quiet(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"])
        gpus = [g.strip() for g in out.splitlines() if g.strip()]
    elif sys.platform == "darwin" and platform.machine() == "arm64" and info.get("cpu"):
        gpus = [f"{info['cpu']} (integrated)"]
    elif shutil.which("lspci"):
        out = run_quiet(["lspci"])
        gpus = [l.split(": ", 1)[1] for l in out.splitlines() if re.search(r"VGA|3D controller|Display", l)]
    info["gpu"] = gpus or None
    return info


def detect_backend(base_url: str, api_key: str) -> dict:
    root = base_url.rstrip("/")
    server = root[:-3] if root.endswith("/v1") else root
    probes = [
        (f"{server}/props", lambda j: ("llama.cpp", j.get("build_info")) if "default_generation_settings" in j else None),
        (f"{server}/api/version", lambda j: ("Ollama", j.get("version")) if "version" in j else None),
        (f"{server}/version", lambda j: ("vLLM", j.get("version")) if "version" in j else None),
    ]
    for url, read in probes:
        try:
            found = read(http_json(url, api_key))
        except Exception:
            continue
        if found:
            return {"name": found[0], "version": found[1]}
    try:
        owners = {m.get("owned_by") for m in http_json(f"{root}/models", api_key).get("data", [])}
    except Exception:
        return {"name": None, "version": None}
    names = {"llamacpp": "llama.cpp", "vllm": "vLLM", "library": "Ollama", "ollama": "Ollama",
             "organization_owner": "LM Studio"}
    return {"name": next((names[o] for o in owners if o in names), None), "version": None}


def is_local(base_url: str) -> bool:
    return urllib.parse.urlparse(base_url).hostname in ("127.0.0.1", "localhost", "::1", "0.0.0.0")


# ---------------------------------------------------------------- judge (optional, never mixed with the score)

def judge_answer(case: dict, messages: list, answer: str, prompts: dict, args) -> dict:
    j = prompts["judge"]
    body = {"model": args.judge_model, "temperature": 0, "max_tokens": 2048 if args.judge_thinking else 400,
            "stream": False,
            "messages": [{"role": "system", "content": j["system"]},
                         {"role": "user", "content": j["user"].format(input=messages[-1]["content"], answer=answer)}]}
    if not args.judge_thinking:
        body["chat_template_kwargs"] = {"enable_thinking": False}
    try:
        reply = http_json(f"{args.judge_base_url.rstrip('/')}/chat/completions", args.judge_api_key, body, args.timeout)
        content = reply["choices"][0]["message"]["content"]
        found = re.search(r"\{.*\}", content, re.S)
        verdict = json.loads(found.group(0)) if found else {}
        if verdict.get("verdict") not in ("supported", "hallucination"):
            return {"error": "unparsable judge reply", "raw": content[:300]}
        return {"verdict": verdict["verdict"], "unsupported": verdict.get("unsupported", [])}
    except Exception as exc:
        return {"error": str(exc)[:200]}


# ---------------------------------------------------------------- output

def print_table(result: dict) -> None:
    s = result["summary"]
    print(f"\n{BENCHMARK} {result['lang']} {result['split']} - {result['model']['label']}")
    print(f"{'category':<16} {'n':>4} {'score':>7}")
    for name, g in s["by_category"].items():
        print(f"{name:<16} {g['n']:>4} {g['score']:>7.1f}")
    print(f"{'ALL':<16} {s['n']:>4} {s['score']:>7.1f}")
    print(f"fact recall {s['fact_recall']} %, forbidden {s['forbidden_rate']} %, "
          f"over length {s['over_length_rate']} %, errors {s['errors']}")
    if "ttft_median_s" in s:
        print(f"TTFT median {s['ttft_median_s']} s, p90 {s['ttft_p90_s']} s; total median {s['total_median_s']} s; "
              f"{s['tok_s_median']} tok/s")
    if result.get("judge"):
        print(f"judge ({result['judge']['model']}): hallucination {result['judge']['summary']}")


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9.]+", "-", text.lower()).strip("-")[:60] or "model"


def run_lang(args, lang: str, config: dict) -> dict:
    cases = load_cases(args.data, lang, args.split)[: args.limit or None]
    prompts, scoring = config["prompts"], config["scoring"]
    reference = args.reference
    result = {
        "benchmark": BENCHMARK, "data_version": Path(args.data).name, "lang": lang, "split": args.split,
        "data_sha256": {f"{lang}/{p.name}": sha256(p) for p in case_files(args.data, lang, args.split)},
        "config_sha256": {"prompts": sha256(Path(args.data) / "prompts.json"),
                          "scoring": sha256(Path(args.data) / "scoring.json")},
        "date": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "model": {"label": "reference" if reference else (args.label or args.model), "name": args.model},
        "protocol": {"temperature": args.temperature, "max_tokens": args.max_tokens,
                     "thinking_disabled": not args.allow_thinking, "warmup": not args.no_warmup,
                     "extra_body": json.loads(args.extra_body) if args.extra_body else None,
                     "system_prompt_file": args.system_prompt_file or None,
                     "system_prompt_override": (prompts["fr"]["summary_system"]
                                                if args.system_prompt_file else None)},
        "rows": [],
    }
    if not reference:
        result["backend"] = {**detect_backend(args.base_url, args.api_key),
                             **({"name": args.backend} if args.backend else {})}
        result["hardware"] = hardware() if is_local(args.base_url) and not args.hardware else None
        result["hardware_note"] = args.hardware or (None if is_local(args.base_url) else "remote server, not detected")
        result["notes"] = args.notes

    def body(messages, max_tokens):
        b = {"model": args.model, "messages": messages, "temperature": args.temperature, "max_tokens": max_tokens,
             "stream": True, "stream_options": {"include_usage": True}, "seed": 0}
        if not args.allow_thinking:
            b["chat_template_kwargs"] = {"enable_thinking": False}
        if args.extra_body:
            b.update(json.loads(args.extra_body))
        return b

    if not reference and not args.no_warmup and cases:
        warm = {"lang": lang, "task": "summary", "cmd": "echo ready", "exit": 0, "duration": 0.0, "output": "ready\n"}
        try:
            chat_stream(args.base_url, args.api_key, body(build_messages(warm, prompts), 8), args.timeout)
        except Exception as exc:
            print(f"warmup failed: {exc}", file=sys.stderr)

    for i, case in enumerate(cases, 1):
        messages = build_messages(case, prompts)
        row = {"id": case["id"], "category": case["category"], "task": case["task"]}
        if reference:
            row["answer"] = case["reference"]
        else:
            max_tokens = args.max_tokens or (128 if case["task"] == "qa" else 96)
            try:
                row.update(chat_stream(args.base_url, args.api_key, body(messages, max_tokens), args.timeout))
            except (urllib.error.URLError, OSError, ValueError) as exc:
                row.update({"answer": None, "error": str(exc)[:200]})
        row.update(score_case(case, row.get("answer") or "", scoring))
        if args.judge_model and row.get("answer"):
            row["judge"] = judge_answer(case, messages, row["answer"], prompts, args)
        result["rows"].append(row)
        if not args.quiet:
            print(f"[{i}/{len(cases)}] {case['id']:<32} {row['score']:.2f} "
                  f"{'' if row.get('ttft') is None else str(row['ttft']) + ' s'}", file=sys.stderr, flush=True)

    result["summary"] = summarize(result["rows"])
    if args.judge_model:
        result["judge"] = {"model": args.judge_model, "summary": judge_summary(result["rows"])}
    return result


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Steph Speak Bench runner (OpenAI-compatible servers).")
    ap.add_argument("--base-url", default="http://127.0.0.1:8080/v1")
    ap.add_argument("--model", default="default", help="model name sent in each request")
    ap.add_argument("--label", default="", help="name shown in the results (defaults to --model)")
    ap.add_argument("--api-key", default=os.environ.get("OPENAI_API_KEY", ""))
    ap.add_argument("--lang", default="en", choices=[*LANGS, "all"])
    ap.add_argument("--split", default="test", choices=["dev", "test", "all"])
    ap.add_argument("--data", default=str(DEFAULT_DATA))
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="directory for the JSON results")
    ap.add_argument("--limit", type=int, default=0, help="first N cases only (smoke test)")
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--max-tokens", type=int, default=0, help="default 96 for summaries, 128 for questions")
    ap.add_argument("--timeout", type=float, default=180.0)
    ap.add_argument("--allow-thinking", action="store_true", help="do not send chat_template_kwargs.enable_thinking=false")
    ap.add_argument("--extra-body", default="", help="JSON merged into each request")
    ap.add_argument("--no-warmup", action="store_true")
    ap.add_argument("--backend", default="", help="override the detected backend name")
    ap.add_argument("--hardware", default="", help="free-text hardware description (required for remote servers)")
    ap.add_argument("--notes", default="", help="free-text notes stored in the result (quantization, flags)")
    ap.add_argument("--judge-base-url", default="", help="optional LLM judge for hallucinations")
    ap.add_argument("--judge-model", default="")
    ap.add_argument("--judge-api-key", default=os.environ.get("JUDGE_API_KEY", ""))
    ap.add_argument("--judge-thinking", action="store_true", help="let the judge reason before answering")
    ap.add_argument("--system-prompt-file", default="",
                     help="replace the summary system prompt with this file's content for every language "
                          "(e.g. a fine-tuned model's own training prompt) ; stored in the result, not the "
                          "leaderboard default")
    ap.add_argument("--reference", action="store_true", help="score the reference answers, no server")
    ap.add_argument("--rescore", nargs="*", default=None, metavar="RESULT", help="recompute scores of result files")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)
    config = load_config(args.data)
    if args.judge_model and not args.judge_base_url:
        ap.error("--judge-model needs --judge-base-url")
    if args.system_prompt_file:
        text = Path(args.system_prompt_file).read_text(encoding="utf-8").strip()
        config["prompts"] = override_summary_system(config["prompts"], text)

    if args.rescore is not None:
        for path in args.rescore:
            result = json.loads(Path(path).read_text(encoding="utf-8"))
            by_id = {c["id"]: c for c in load_cases(args.data, result["lang"], "all")}
            print_table(rescore(result, by_id, config["scoring"]))
        return 0

    for lang in (list(LANGS) if args.lang == "all" else [args.lang]):
        result = run_lang(args, lang, config)
        print_table(result)
        if not args.reference and result["summary"]["errors"] == len(result["rows"]):
            print("every request failed: no result written (is the server up?)", file=sys.stderr)
            return 1
        if args.reference:
            continue
        stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S")
        out = Path(args.out) / f"{stamp}_{slug(result['model']['label'])}_{lang}_{args.split}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"written: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
