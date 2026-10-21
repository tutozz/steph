#!/usr/bin/env python3
"""Anti-invention preference training of Gemma 4 E2B (G3), adapted from pref/train_dpo.py: DPO with
an SFT term on the chosen answer (RPO variant), new LoRA over the uniform soup of the SFT adapters.

    python3 train_dpo_gemma.py --model <gemma-4-E2B-it-qat-q4_0-unquantized> --sft-adapters a1 a2 ... \
        --pairs pairs-train.jsonl --val-pairs pairs-val.jsonl --val val.jsonl --out out_dir [--generic-prompt]

Reference = SFT soup with the adapter disabled, log-probabilities computed once at start. Pairs rows:
{"prompt": [messages without the answer], "chosen": str, "rejected": str}. Writes out_dir/adapter;
merge_gemma.py --adapters <SFT seeds> --add out_dir/adapter then writes the merged checkpoint.

SPDX-License-Identifier: MIT
"""
import argparse, json, math, random, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gemma_lib import ATTN_MLP, TextLM, adapter_deltas, encode  # noqa: E402
from gemma_format import to_generic  # noqa: E402

import torch
import torch.nn.functional as F
from transformers import AutoTokenizer


def vram(fn="max_memory_allocated"):
    return getattr(torch.cuda, fn)() // 2**20 if torch.cuda.is_available() else 0


ap = argparse.ArgumentParser()
ap.add_argument("--model", required=True)
ap.add_argument("--sft-adapters", nargs="*", default=[], help="empty: the reference is --model as is")
ap.add_argument("--pairs", required=True)
ap.add_argument("--val-pairs", required=True)
ap.add_argument("--val", required=True, help="SFT val: follows the loss on the labels (drift)")
ap.add_argument("--out", required=True)
ap.add_argument("--rank", type=int, default=16)
ap.add_argument("--alpha", type=int, default=32)
ap.add_argument("--lr", type=float, default=1e-5)
ap.add_argument("--beta", type=float, default=0.1)
ap.add_argument("--sft-weight", type=float, default=1.0)
ap.add_argument("--epochs", type=float, default=3)
ap.add_argument("--batch", type=int, default=16)
ap.add_argument("--micro", type=int, default=4)
ap.add_argument("--maxlen", type=int, default=2048)
ap.add_argument("--seed", type=int, default=42)
ap.add_argument("--generic-prompt", action="store_true")
ap.add_argument("--max-steps", type=int, default=0)
ap.add_argument("--device", default="cuda", help="cpu: smoke test of the code path only")
a = ap.parse_args()

random.seed(a.seed); torch.manual_seed(a.seed); torch.cuda.manual_seed_all(a.seed)
out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
tok = AutoTokenizer.from_pretrained(a.model)


def prompt_of(msgs):
    return to_generic(msgs + [{"role": "assistant", "content": ""}])[0][:-1] if a.generic_prompt else msgs


def load_pairs(path):
    rows = [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]
    return [(encode(tok, prompt_of(r["prompt"]), a.maxlen, r["chosen"]),
             encode(tok, prompt_of(r["prompt"]), a.maxlen, r["rejected"])) for r in rows]


train, val_pairs = load_pairs(a.pairs), load_pairs(a.val_pairs)
val_sft = []
for line in open(a.val, encoding="utf-8"):
    if line.strip():
        m = json.loads(line)["messages"]
        val_sft.append(encode(tok, to_generic(m)[0] if a.generic_prompt else m, a.maxlen))
print(f"paires train {len(train)} val {len(val_pairs)} ; val SFT {len(val_sft)}", flush=True)

lm = TextLM(a.model, deltas=adapter_deltas(a.sft_adapters) if a.sft_adapters else None, device=a.device)
print(f"soupe SFT : {len(a.sft_adapters)} adaptateurs ; VRAM {vram('memory_allocated')} Mo", flush=True)
lm.text.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
from peft import LoraConfig, get_peft_model  # noqa: E402
model = get_peft_model(lm.text, LoraConfig(r=a.rank, lora_alpha=a.alpha, lora_dropout=0.0, target_modules=ATTN_MLP))
trainable = [p for p in model.parameters() if p.requires_grad]
print(f"paramètres entraînables {sum(p.numel() for p in trainable):,}", flush=True)


def pad(seqs):
    n = max(len(i) for i, _ in seqs)
    ids = torch.full((len(seqs), n), tok.pad_token_id)
    lab = torch.full((len(seqs), n), -100)
    att = torch.zeros((len(seqs), n), dtype=torch.long)
    for k, (i, l) in enumerate(seqs):
        ids[k, :len(i)] = torch.tensor(i); lab[k, :len(l)] = torch.tensor(l); att[k, :len(i)] = 1
    return ids.to(a.device), lab.to(a.device), att.to(a.device)


def seq_logps(seqs):
    """Sum of the answer log-probabilities and token count, per sequence."""
    ids, lab, att = pad(seqs)
    logits, tgt, keep = lm.target_logits(model, ids, lab, att)
    tok_lp = torch.gather(F.log_softmax(logits, -1), 1, tgt[keep].unsqueeze(1)).squeeze(1)
    row = keep.nonzero()[:, 0]
    sums = torch.zeros(len(seqs), device=tok_lp.device).index_add(0, row, tok_lp)
    return sums, keep.sum(1)


@torch.no_grad()
def reference(pairs):
    ref = []
    with model.disable_adapter():
        for s in range(0, len(pairs), a.micro):
            chunk = pairs[s:s + a.micro]
            lp, _ = seq_logps([c for c, _ in chunk] + [r for _, r in chunk])
            ref += list(zip(lp[:len(chunk)].tolist(), lp[len(chunk):].tolist()))
    return ref


def pair_loss(chunk, ref):
    lp, n = seq_logps([c for c, _ in chunk] + [r for _, r in chunk])
    k = len(chunk)
    rc = torch.tensor([x for x, _ in ref], device=lp.device)
    rr = torch.tensor([y for _, y in ref], device=lp.device)
    margin = a.beta * ((lp[:k] - rc) - (lp[k:] - rr))
    return -F.logsigmoid(margin) + a.sft_weight * (-lp[:k] / n[:k]), margin


@torch.no_grad()
def evaluate():
    model.eval()
    losses, margins = [], []
    for s in range(0, len(val_pairs), a.micro):
        l, m = pair_loss(val_pairs[s:s + a.micro], val_ref[s:s + a.micro])
        losses += l.tolist(); margins += m.tolist()
    tot, n = 0.0, 0
    for s in range(0, len(val_sft), a.micro):
        lp, c = seq_logps(val_sft[s:s + a.micro]); tot -= lp.sum().item(); n += c.sum().item()
    model.train()
    return {"pair_loss": round(sum(losses) / len(losses), 4), "acc": round(sum(m > 0 for m in margins) / len(margins), 3),
            "margin": round(sum(margins) / len(margins), 3), "sft_val": round(tot / n, 4)}


t0 = time.time()
train_ref, val_ref = reference(train), reference(val_pairs)
print(f"références calculées en {time.time() - t0:.0f} s", flush=True)
hist = [dict(evaluate(), epoch=0.0)]
print(json.dumps(hist[-1]), flush=True)

steps_per_epoch = math.ceil(len(train) / a.batch)
total = max(1, round(steps_per_epoch * a.epochs))
if a.max_steps:
    total = min(total, a.max_steps)
opt = torch.optim.AdamW(trainable, lr=a.lr, weight_decay=0.0)
warm = max(1, int(0.1 * total))
sched = torch.optim.lr_scheduler.LambdaLR(
    opt, lambda s: (s + 1) / warm if s < warm else 0.5 * (1 + math.cos(math.pi * (s - warm) / max(1, total - warm))))
rng = random.Random(a.seed)
model.train()
step = 0
while step < total:
    idx = list(range(len(train))); rng.shuffle(idx)
    for s in range(0, len(idx), a.batch):
        if step >= total:
            break
        group = idx[s:s + a.batch]
        run, mar = 0.0, 0.0
        for m in range(0, len(group), a.micro):
            sub = group[m:m + a.micro]
            l, mg = pair_loss([train[i] for i in sub], [train_ref[i] for i in sub])
            (l.sum() / len(group)).backward()
            run += l.sum().item(); mar += mg.sum().item()
        torch.nn.utils.clip_grad_norm_(trainable, 1.0)
        opt.step(); sched.step(); opt.zero_grad(set_to_none=True); step += 1
        if step % 5 == 0:
            print(json.dumps({"step": step, "loss": round(run / len(group), 4), "margin": round(mar / len(group), 3),
                              "s": round(time.time() - t0)}), flush=True)
        if step % steps_per_epoch == 0 or step == total:
            hist.append(dict(evaluate(), epoch=round(step / steps_per_epoch, 2)))
            print(json.dumps(hist[-1]), flush=True)

model.save_pretrained(out / "adapter")
json.dump({"args": vars(a), "evals": hist, "steps": step, "train_s": round(time.time() - t0, 1),
           "vram_peak_mb": vram()}, open(out / "train_log.json", "w"), indent=1)
print("adaptateur écrit", flush=True)
