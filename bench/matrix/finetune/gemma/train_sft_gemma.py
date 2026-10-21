#!/usr/bin/env python3
"""LoRA SFT of Gemma 4 E2B (G3), adapted from train_sft.py: answer-only loss, several evaluations
per epoch, early stop on the validation loss, best adapter kept. Always writes out/adapter; the
full bf16 checkpoint for llama.cpp comes from merge_gemma.py (soup of seeds included).

    python3 train_sft_gemma.py --model <gemma-4-E2B-it-qat-q4_0-unquantized> --train t.jsonl --val v.jsonl \
        --out out_dir [--generic-prompt] [--max-steps 20]

Gemma-specific: text decoder only (audio and vision towers dropped), per-layer embeddings on the
CPU (gemma_lib), bf16 base weights, final logit softcapping in the loss, and --generic-prompt to
train on the production generic prompts (gemma_format). Same real-time follow-up as train_sft.py:
out/metrics.jsonl, out/status.json, out/control.json.

SPDX-License-Identifier: MIT
"""
import argparse, json, math, os, random, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gemma_lib import ATTN_MLP, TextLM, encode  # noqa: E402
from gemma_format import to_generic  # noqa: E402
from train_lora import append_metrics, read_control, write_status  # noqa: E402

import torch
from transformers import AutoTokenizer


def vram(fn="max_memory_allocated"):
    return getattr(torch.cuda, fn)() // 2**20 if torch.cuda.is_available() else 0


ap = argparse.ArgumentParser()
ap.add_argument("--model", required=True)
ap.add_argument("--train", required=True)
ap.add_argument("--val", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--rank", type=int, default=16)
ap.add_argument("--alpha", type=int, default=32)
ap.add_argument("--dropout", type=float, default=0.05)
ap.add_argument("--lr", type=float, default=1e-4)
ap.add_argument("--epochs", type=float, default=2)
ap.add_argument("--maxlen", type=int, default=2048)
ap.add_argument("--micro", type=int, default=4)
ap.add_argument("--batch", type=int, default=16)
ap.add_argument("--evals-per-epoch", type=int, default=4)
ap.add_argument("--patience", type=int, default=3)
ap.add_argument("--seed", type=int, default=42)
ap.add_argument("--targets", default="attn-mlp", help="attn-mlp or a comma-separated list of module names")
ap.add_argument("--no-gc", action="store_true", help="disable gradient checkpointing")
ap.add_argument("--ple-gpu", action="store_true", help="per-layer embeddings on the GPU (+4.7 GB)")
ap.add_argument("--generic-prompt", action="store_true", help="rewrite system prompts to the production generic ones")
ap.add_argument("--max-steps", type=int, default=0, help="stop after N optimizer steps (memory and speed trial)")
ap.add_argument("--device", default="cuda", help="cpu: smoke test of the code path only")
ap.add_argument("--eval-only", action="store_true", help="validation loss of the base model, then exit")
ap.add_argument("--val-limit", type=int, default=0, help="keep only the first N validation rows")
a = ap.parse_args()

random.seed(a.seed); torch.manual_seed(a.seed); torch.cuda.manual_seed_all(a.seed)
out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
tok = AutoTokenizer.from_pretrained(a.model)


def load(path):
    rows, unknown = [], 0
    for line in open(path, encoding="utf-8"):
        if not line.strip():
            continue
        msgs = json.loads(line)["messages"]
        if a.generic_prompt:
            msgs, known = to_generic(msgs)
            unknown += not known
        rows.append(encode(tok, msgs, a.maxlen))
    if unknown:
        print(f"{path} : {unknown} lignes au prompt système inconnu, gardées telles quelles", flush=True)
    return rows


train, val = load(a.train), load(a.val)
if a.val_limit:
    val = val[:a.val_limit]
lens = sorted(len(i) for i, _ in train)
print(f"train {len(train)} val {len(val)} ; jetons médiane {lens[len(lens)//2]} max {lens[-1]}", flush=True)

t_load = time.time()
lm = TextLM(a.model, ple_cpu=not a.ple_gpu, device=a.device)
print(f"modèle chargé en {time.time() - t_load:.0f} s ; VRAM {vram('memory_allocated')} Mo", flush=True)
if not a.no_gc:
    lm.text.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
from peft import LoraConfig, get_peft_model  # noqa: E402
model = get_peft_model(lm.text, LoraConfig(r=a.rank, lora_alpha=a.alpha, lora_dropout=a.dropout,
                                           target_modules=ATTN_MLP if a.targets == "attn-mlp" else a.targets.split(",")))
trainable = [p for p in model.parameters() if p.requires_grad]
print(f"paramètres entraînables {sum(p.numel() for p in trainable):,}", flush=True)


def batches(data, size):
    for s in range(0, len(data), size):
        chunk = data[s:s + size]
        n = max(len(i) for i, _ in chunk)
        ids = torch.full((len(chunk), n), tok.pad_token_id)
        lab = torch.full((len(chunk), n), -100)
        att = torch.zeros((len(chunk), n), dtype=torch.long)
        for k, (i, l) in enumerate(chunk):
            ids[k, :len(i)] = torch.tensor(i); lab[k, :len(l)] = torch.tensor(l); att[k, :len(i)] = 1
        yield ids.to(a.device), lab.to(a.device), att.to(a.device)


def token_loss(ids, lab, att):
    logits, tgt, keep = lm.target_logits(model, ids, lab, att)
    return torch.nn.functional.cross_entropy(logits, tgt[keep], reduction="sum"), keep.sum()


@torch.no_grad()
def evaluate():
    model.eval()
    tot, n = 0.0, 0
    for ids, lab, att in batches(val, a.micro):
        l, c = token_loss(ids, lab, att); tot += l.item(); n += c.item()
    model.train()
    return tot / n


def snapshot():
    return [p.detach().to("cpu", copy=True) for p in trainable]


steps_per_epoch = math.ceil(len(train) / a.batch)
total_steps = max(1, round(steps_per_epoch * a.epochs))
if a.max_steps:
    total_steps = min(total_steps, a.max_steps)
eval_every = max(1, steps_per_epoch // a.evals_per_epoch)
opt = torch.optim.AdamW(trainable, lr=a.lr, weight_decay=0.0)
warm = max(1, int(0.03 * total_steps))
sched = torch.optim.lr_scheduler.LambdaLR(
    opt, lambda s: (s + 1) / warm if s < warm else 0.5 * (1 + math.cos(math.pi * (s - warm) / max(1, total_steps - warm))))
rng = random.Random(a.seed)
metrics, status, control = out / "metrics.jsonl", out / "status.json", out / "control.json"
write_status(status, state="running", pid=os.getpid(), step=0, total_steps=total_steps)
t_eval = time.time()
v0 = evaluate()
eval_s = time.time() - t_eval
append_metrics(metrics, {"step": 0, "epoch": 0.0, "val_loss": v0})
print(json.dumps({"eval_loss": round(v0, 4), "epoch": 0.0, "eval_s": round(eval_s, 1)}), flush=True)
if a.eval_only:
    json.dump({"args": vars(a), "val_before": v0, "eval_s": round(eval_s, 1)}, open(out / "eval_log.json", "w"), indent=1)
    sys.exit(0)
best = (v0, 0, None)
hist, step, t0, run_loss, run_tok, seen_tok, lr_scale = [], 0, time.time(), 0.0, 0, 0, 1.0
if torch.cuda.is_available():
    torch.cuda.reset_peak_memory_stats()
model.train()
stop = False
while step < total_steps and not stop:
    idx = list(range(len(train))); rng.shuffle(idx)
    for s in range(0, len(idx), a.batch):
        if step >= total_steps:
            break
        group = sorted((train[i] for i in idx[s:s + a.batch]), key=lambda x: len(x[0]))
        ntok = sum(sum(1 for x in l if x != -100) for _, l in group)
        seen_tok += sum(len(i) for i, _ in group)
        for ids, lab, att in batches(group, a.micro):
            l, c = token_loss(ids, lab, att)
            (l / ntok).backward()
            run_loss += l.item(); run_tok += c.item()
        torch.nn.utils.clip_grad_norm_(trainable, 1.0)
        opt.step(); sched.step(); opt.zero_grad(set_to_none=True); step += 1
        for g in opt.param_groups:
            g["lr"] *= lr_scale
        ep = round(step / steps_per_epoch, 3)
        el = time.time() - t0
        append_metrics(metrics, {"step": step, "epoch": ep, "loss": round(run_loss / max(run_tok, 1), 4),
                                 "lr": opt.param_groups[0]["lr"], "s": round(el), "tok_s": round(seen_tok / el),
                                 "vram_peak_mb": vram()})
        ctrl = read_control(control)
        if ctrl.get("action") == "stop":
            print(f"arrêt demandé à l'époque {ep}", flush=True); stop = True
        if "lr_scale" in ctrl:
            lr_scale *= float(ctrl["lr_scale"])
        if step % 5 == 0:
            print(json.dumps({"step": step, "loss": round(run_loss / max(run_tok, 1), 4), "epoch": ep, "s": round(el),
                              "s_per_step": round(el / step, 2), "tok_s": round(seen_tok / el),
                              "vram_peak_mb": vram()}), flush=True)
            run_loss, run_tok = 0.0, 0
        if step % eval_every == 0 or step == total_steps or ctrl.get("eval_now"):
            v = evaluate(); hist.append(v)
            print(json.dumps({"eval_loss": round(v, 4), "epoch": ep}), flush=True)
            append_metrics(metrics, {"step": step, "epoch": ep, "val_loss": v})
            if v < best[0]:
                best = (v, ep, snapshot())
            if len(hist) - 1 - hist.index(min(hist)) >= a.patience:
                print(f"arrêt anticipé à l'époque {ep}", flush=True); stop = True
        write_status(status, state="running", step=step, total_steps=total_steps, epoch=ep, best_val=best[0])
        if stop:
            break

train_s = round(time.time() - t0, 1)
if best[2] is not None:
    with torch.no_grad():
        for p, b in zip(trainable, best[2]):
            p.copy_(b.to(p.device))
log = {"args": vars(a), "val_before": v0, "best_val": best[0], "best_epoch": best[1], "evals": hist, "steps": step,
       "train_s": train_s, "s_per_step": round(train_s / max(step, 1), 2), "train_tok_s": round(seen_tok / max(train_s, 1e-9)),
       "eval_s_first": round(eval_s, 1), "vram_peak_mb": vram(),
       "vram_reserved_peak_mb": vram("max_memory_reserved")}
json.dump(log, open(out / "train_log.json", "w"), indent=1)
model.save_pretrained(out / "adapter")
print(f"meilleure perte val {best[0]:.4f} à l'époque {best[1]} ; {train_s} s ; adaptateur écrit", flush=True)
write_status(status, state="stopped" if stop else "done", step=step, best_val=best[0], best_epoch=best[1])
