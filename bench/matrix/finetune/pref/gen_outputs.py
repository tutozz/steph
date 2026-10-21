#!/usr/bin/env python3
"""Génère les sorties du modèle affiné sur les entrées du corpus d'entraînement (P16).

    python3 gen_outputs.py --data <dossier train.jsonl/val.jsonl> --port 8950 --out gen.jsonl \
        --seeds 42 7 123 [--temperature 0.2]

Même décodage que le banc (top_p 0.9, repeat_penalty du banc, graine fixée) pour relever les
inventions que le modèle fait réellement. Reprise automatique : une ligne par (split, idx, seed,
temperature). Le fichier de sortie contient du corpus : il reste sur la machine.

SPDX-License-Identifier: MIT
"""

import argparse
import json
import os
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed


def ask(port, messages, seed, temperature, max_tokens, repeat_penalty):
    body = json.dumps({
        "messages": messages, "max_tokens": max_tokens, "temperature": temperature, "top_p": 0.9,
        "repeat_penalty": repeat_penalty, "seed": seed, "chat_template_kwargs": {"enable_thinking": False},
    }).encode()
    req = urllib.request.Request(f"http://127.0.0.1:{port}/v1/chat/completions", body,
                                 {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read())["choices"][0]["message"]["content"].strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--port", type=int, default=8950)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seeds", type=int, nargs="+", default=[42, 7, 123])
    ap.add_argument("--temperature", type=float, default=0.2)
    ap.add_argument("--max-tokens", type=int, default=80)
    ap.add_argument("--parallel", type=int, default=8)
    ap.add_argument("--repeat-penalty", type=float, default=1.1)
    a = ap.parse_args()

    done = set()
    if os.path.exists(a.out):
        for line in open(a.out):
            r = json.loads(line)
            done.add((r["split"], r["idx"], r["seed"], r["temperature"]))
    todo = []
    for split in ("train", "val"):
        for idx, line in enumerate(open(os.path.join(a.data, f"{split}.jsonl"))):
            msgs = json.loads(line)["messages"][:-1]
            for seed in a.seeds:
                if (split, idx, seed, a.temperature) not in done:
                    todo.append((split, idx, seed, msgs))
    print(f"{len(todo)} générations à faire, {len(done)} déjà faites", flush=True)
    with open(a.out, "a") as out, ThreadPoolExecutor(max_workers=a.parallel) as ex:
        futs = {ex.submit(ask, a.port, m, s, a.temperature, a.max_tokens, a.repeat_penalty): (sp, i, s) for sp, i, s, m in todo}
        for n, fut in enumerate(as_completed(futs), 1):
            sp, i, s = futs[fut]
            try:
                text = fut.result()
            except Exception as e:
                print(f"erreur {sp}/{i}/{s} : {e}", flush=True)
                continue
            out.write(json.dumps({"split": sp, "idx": i, "seed": s, "temperature": a.temperature, "out": text},
                                 ensure_ascii=False) + "\n")
            if n % 500 == 0:
                out.flush()
                print(f"  {n}/{len(todo)}", flush=True)
    print("fini", flush=True)


if __name__ == "__main__":
    main()
