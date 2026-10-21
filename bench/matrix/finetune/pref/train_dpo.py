#!/usr/bin/env python3
"""Entraînement de préférences anti-invention (P16) : DPO avec terme SFT sur la réponse choisie
(variante RPO), LoRA neuve posée sur la soupe uniforme des adaptateurs SFT.

    python3 train_dpo.py --model <base HF> --sft-adapters a1 a2 ... --pairs pairs-train.jsonl \
        --val-pairs pairs-val.jsonl --val val.jsonl --out out_dir --seed 42

Référence DPO = soupe SFT (adaptateur désactivé), log-probabilités de référence calculées une
fois au départ. Même chemin Mamba et même perte « réponse seule » que soup/train.py. Écrit
out_dir/adapter (LoRA seule) et out_dir/train_log.json.

SPDX-License-Identifier: MIT
"""

import argparse
import json
import math
import random
import sys
import time
from pathlib import Path

import torch
import torch.nn.functional as F
from safetensors.torch import load_file
from transformers import AutoModelForCausalLM, AutoTokenizer

sys.path += [str(Path(__file__).resolve().parent), str(Path(__file__).resolve().parents[1] / "loop" / "r3t4")]

ap = argparse.ArgumentParser()
ap.add_argument("--model", required=True)
ap.add_argument("--sft-adapters", nargs="*", default=[], help="vide : la référence est --model tel quel (R2-C1)")
ap.add_argument("--pairs", required=True)
ap.add_argument("--val-pairs", required=True)
ap.add_argument("--val", required=True, help="val SFT : suit la perte sur les étiquettes (dérive)")
ap.add_argument("--out", required=True)
ap.add_argument("--rank", type=int, default=16)
ap.add_argument("--alpha", type=int, default=32)
ap.add_argument("--lr", type=float, default=2e-5)
ap.add_argument("--beta", type=float, default=0.1)
ap.add_argument("--sft-weight", type=float, default=1.0)
ap.add_argument("--epochs", type=float, default=3)
ap.add_argument("--batch", type=int, default=16)
ap.add_argument("--micro", type=int, default=8)
ap.add_argument("--maxlen", type=int, default=1536)
ap.add_argument("--seed", type=int, default=42)
ap.add_argument("--mask-rejected", action="store_true",
                help="Mask-DPO (R3-T4) : log-probabilité de la rejetée sur ses seuls empans inventés (rejected_spans)")
a = ap.parse_args()

random.seed(a.seed); torch.manual_seed(a.seed); torch.cuda.manual_seed_all(a.seed)
out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
tok = AutoTokenizer.from_pretrained(a.model)


def render(messages, gen):
    return tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=gen)


def encode(prompt_msgs, answer, spans=None):
    prompt = render(prompt_msgs, True)
    full = render(prompt_msgs + [{"role": "assistant", "content": answer}], False)
    assert full.startswith(prompt)
    p_ids = tok(prompt, add_special_tokens=False)["input_ids"]
    completion = full[len(prompt):].rstrip("\n")
    enc = tok(completion, add_special_tokens=False, return_offsets_mapping=spans is not None)
    c_ids = enc["input_ids"]
    c_lab = c_ids
    if spans is not None:
        from mask_pairs import token_keep
        keep = token_keep(enc["offset_mapping"], [tuple(x) for x in spans], completion.index(answer))
        c_lab = [t if k else -100 for t, k in zip(c_ids, keep)]
    ids = (p_ids + c_ids)[-a.maxlen:]
    return ids, ([-100] * len(p_ids) + c_lab)[-len(ids):]


def load_pairs(path):
    rows = [json.loads(l) for l in open(path)]
    pairs = [(encode(r["prompt"], r["chosen"]),
              encode(r["prompt"], r["rejected"], r["rejected_spans"] if a.mask_rejected else None)) for r in rows]
    kept = [p for p in pairs if any(x != -100 for x in p[1][1])]
    if len(kept) != len(pairs):
        print(f"{path} : {len(pairs) - len(kept)} paires sans jeton rejeté après masque, écartées", flush=True)
    return kept


train, val_pairs = load_pairs(a.pairs), load_pairs(a.val_pairs)
val_sft = [encode(m[:-1], m[-1]["content"]) for m in (json.loads(l)["messages"] for l in open(a.val))]
print(f"paires train {len(train)} val {len(val_pairs)} ; val SFT {len(val_sft)}", flush=True)

from transformers.models.granitemoehybrid import modeling_granitemoehybrid as _gmh  # noqa: E402
_gmh.mamba2_split_conv1d_scan_combined = lambda *args, **kw: None
model = AutoModelForCausalLM.from_pretrained(a.model, dtype=torch.float32).cuda()
logit_scale = getattr(model.config, "logits_scaling", 1.0) or 1.0
model.config.use_cache = False
params = dict(model.named_parameters())
acc = {}
with torch.no_grad():
    for folder in a.sft_adapters:
        cfg = json.load(open(Path(folder) / "adapter_config.json"))
        assert not cfg.get("use_rslora") and not cfg.get("use_dora") and not cfg.get("fan_in_fan_out")
        scale = cfg["lora_alpha"] / cfg["r"]
        sd = load_file(str(Path(folder) / "adapter_model.safetensors"))
        for k in sd:
            if k.endswith("lora_A.weight"):
                name = k.replace("base_model.model.", "", 1).replace(".lora_A.weight", ".weight")
                d = (sd[k.replace("lora_A", "lora_B")].float() @ sd[k].float()) * scale
                acc[name] = acc.get(name, 0) + d
    for name, d in acc.items():
        params[name].add_((d / len(a.sft_adapters)).cuda())
print(f"soupe SFT : {len(acc)} matrices, {len(a.sft_adapters)} adaptateurs", flush=True)
del acc, params

from peft import LoraConfig, get_peft_model  # noqa: E402
model.gradient_checkpointing_enable()
model.enable_input_require_grads()
model = get_peft_model(model, LoraConfig(r=a.rank, lora_alpha=a.alpha, lora_dropout=0.0,
                                         task_type="CAUSAL_LM", target_modules="all-linear"))
inner = model.get_base_model()
trainable = [p for p in model.parameters() if p.requires_grad]
print(f"paramètres entraînables {sum(p.numel() for p in trainable):,}", flush=True)


def pad(seqs):
    n = max(len(i) for i, _ in seqs)
    ids = torch.full((len(seqs), n), tok.pad_token_id)
    lab = torch.full((len(seqs), n), -100)
    att = torch.zeros((len(seqs), n), dtype=torch.long)
    for k, (i, l) in enumerate(seqs):
        ids[k, :len(i)] = torch.tensor(i); lab[k, :len(l)] = torch.tensor(l); att[k, :len(i)] = 1
    return ids.cuda(), lab.cuda(), att.cuda()


def seq_logps(seqs):
    """Somme des log-probabilités de la réponse et nombre de jetons, par séquence."""
    ids, lab, att = pad(seqs)
    with torch.autocast("cuda", dtype=torch.bfloat16):
        hidden = inner.model(input_ids=ids, attention_mask=att).last_hidden_state[:, :-1]
        tgt = lab[:, 1:]
        keep = tgt != -100
        logits = inner.lm_head(hidden[keep]).float() / logit_scale
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
    dpo = -F.logsigmoid(margin)
    sft = -lp[:k] / n[:k]
    return dpo + a.sft_weight * sft, margin


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
           "vram_peak_mb": torch.cuda.max_memory_allocated() // 2**20}, open(out / "train_log.json", "w"), indent=1)
print("adaptateur écrit", flush=True)
