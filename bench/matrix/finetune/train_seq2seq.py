#!/usr/bin/env python3
"""Affinage complet d'un encodeur-décodeur (famille T5) sur le corpus de steph.

    python3 train_seq2seq.py --model base-flan-t5-small --train train.jsonl --val val.jsonl --out out_dir

Entrée de l'encodeur : le message utilisateur de steph (commande, statut, sortie), sans le
prompt système, qui est constant dans le corpus. Sortie du décodeur : l'étiquette. Le
meilleur modèle selon la perte de validation est sauvegardé dans ``out_dir/best``.

SPDX-License-Identifier: MIT
"""

from __future__ import annotations

import argparse
import json
import random
import time
from pathlib import Path


def to_pair(messages: list[dict]) -> tuple[str, str]:
    users = [m["content"] for m in messages if m["role"] == "user"]
    if not users:
        raise ValueError("no user message")
    answers = [m["content"] for m in messages if m["role"] == "assistant"]
    return users[-1], answers[-1] if answers else ""


def load_pairs(path: str) -> list[tuple[str, str]]:
    return [to_pair(json.loads(line)["messages"]) for line in open(path) if line.strip()]


def run(a) -> None:
    import torch
    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

    random.seed(a.seed)
    torch.manual_seed(a.seed)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    tok = AutoTokenizer.from_pretrained(a.model)
    model = AutoModelForSeq2SeqLM.from_pretrained(a.model).cuda()
    if a.gc:
        model.gradient_checkpointing_enable()
        model.config.use_cache = False

    def encode(pairs):
        return [(tok(s, truncation=True, max_length=a.max_source).input_ids,
                 tok(t, truncation=True, max_length=a.max_target).input_ids) for s, t in pairs]

    train, val = encode(load_pairs(a.train)), encode(load_pairs(a.val))

    def collate(batch):
        src_len = max(len(s) for s, _ in batch)
        tgt_len = max(len(t) for _, t in batch)
        ids = torch.full((len(batch), src_len), tok.pad_token_id)
        mask = torch.zeros((len(batch), src_len), dtype=torch.long)
        labels = torch.full((len(batch), tgt_len), -100)
        for i, (s, t) in enumerate(batch):
            ids[i, :len(s)], mask[i, :len(s)], labels[i, :len(t)] = torch.tensor(s), 1, torch.tensor(t)
        return ids.cuda(), mask.cuda(), labels.cuda()

    def loss_of(batch):
        ids, mask, labels = collate(batch)
        with torch.autocast("cuda", dtype=torch.bfloat16):
            return model(input_ids=ids, attention_mask=mask, labels=labels).loss

    def evaluate():
        model.eval()
        total, n = 0.0, 0
        with torch.no_grad():
            for i in range(0, len(val), a.batch):
                chunk = val[i:i + a.batch]
                total += loss_of(chunk).item() * len(chunk)
                n += len(chunk)
        model.train()
        return total / n

    steps_per_epoch = -(-len(train) // (a.batch * a.accum))
    total_steps = steps_per_epoch * a.epochs
    opt = torch.optim.AdamW(model.parameters(), lr=a.lr, weight_decay=0.01)
    sched = torch.optim.lr_scheduler.LambdaLR(
        opt, lambda s: min(1.0, (s + 1) / max(1, int(0.05 * total_steps))) * max(0.0, 1 - s / total_steps))
    metrics = open(out / "metrics.jsonl", "a")
    best, bad_epochs, t0 = float("inf"), 0, time.time()
    model.train()
    for epoch in range(1, a.epochs + 1):
        order = list(range(len(train)))
        random.shuffle(order)
        batches = [[train[j] for j in order[i:i + a.batch]] for i in range(0, len(order), a.batch)]
        running = []
        for k, batch in enumerate(batches):
            loss = loss_of(batch) / a.accum
            loss.backward()
            running.append(loss.item() * a.accum)
            if (k + 1) % a.accum == 0 or k + 1 == len(batches):
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                opt.step()
                sched.step()
                opt.zero_grad()
        val_loss = evaluate()
        rec = {"epoch": epoch, "train_loss": round(sum(running) / len(running), 4), "val_loss": round(val_loss, 4),
               "elapsed_s": round(time.time() - t0, 1),
               "vram_peak_mb": round(torch.cuda.max_memory_allocated() / 2**20)}
        metrics.write(json.dumps(rec) + "\n")
        metrics.flush()
        print(json.dumps(rec), flush=True)
        if val_loss < best:
            best, bad_epochs = val_loss, 0
            model.save_pretrained(out / "best")
            tok.save_pretrained(out / "best")
        else:
            bad_epochs += 1
            if bad_epochs >= a.patience:
                break
    (out / "summary.json").write_text(json.dumps({"best_val": best, "args": vars(a),
                                                  "train_s": round(time.time() - t0, 1)}))
    print("DONE_TRAINING", flush=True)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--train", required=True)
    ap.add_argument("--val", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--epochs", type=int, default=10)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--accum", type=int, default=2)
    ap.add_argument("--patience", type=int, default=2)
    ap.add_argument("--max-source", type=int, default=1024)
    ap.add_argument("--max-target", type=int, default=96)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--gc", action="store_true")
    run(ap.parse_args(argv))


if __name__ == "__main__":
    main()
