#!/usr/bin/env python3
"""Soin d'un Granite 4.0 H élagué (X1, théorie T2) : affinage complet, perte = alpha * entropie croisée
sur la réponse + (1 - alpha) * T² * KL(professeur || élève) à température T, professeur = modèle non élagué.

    python3 heal_kd.py --student <HF élagué> --teacher <HF complet> --train train.jsonl --val val.jsonl --out <dossier>

Embeddings gelés (liés à lm_head) : ils ne changent pas avec l'élagage et c'est un quart des paramètres.
Évaluation plusieurs fois par époque (entropie croisée val), arrêt anticipé, meilleur état écrit en
bfloat16 dans out/merged. Mêmes rendus de gabarit et même coupe à maxlen que train_sft.py.

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

sys.path.insert(0, str(Path(__file__).parent))
from prune_granite import encode, patch_mamba  # noqa: E402

from transformers import AutoModelForCausalLM, AutoTokenizer  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--student", required=True)
ap.add_argument("--teacher", required=True)
ap.add_argument("--train", required=True)
ap.add_argument("--val", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--lr", type=float, default=5e-5)
ap.add_argument("--epochs", type=float, default=2)
ap.add_argument("--alpha", type=float, default=0.5)
ap.add_argument("--temp", type=float, default=2.0)
ap.add_argument("--maxlen", type=int, default=1536)
ap.add_argument("--micro", type=int, default=4)
ap.add_argument("--batch", type=int, default=16)
ap.add_argument("--evals-per-epoch", type=int, default=4)
ap.add_argument("--patience", type=int, default=3)
ap.add_argument("--seed", type=int, default=42)
a = ap.parse_args()

random.seed(a.seed); torch.manual_seed(a.seed); torch.cuda.manual_seed_all(a.seed)
out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
tok = AutoTokenizer.from_pretrained(a.student)
train = [encode(tok, json.loads(l)["messages"], a.maxlen) for l in open(a.train)]
val = [encode(tok, json.loads(l)["messages"], a.maxlen) for l in open(a.val)]
print(f"train {len(train)} val {len(val)}", flush=True)

patch_mamba()
student = AutoModelForCausalLM.from_pretrained(a.student, dtype=torch.float32).cuda()
teacher = AutoModelForCausalLM.from_pretrained(a.teacher, dtype=torch.bfloat16).cuda().eval()
for m in (student, teacher):
    m.config.use_cache = False
for p in teacher.parameters():
    p.requires_grad_(False)
student.gradient_checkpointing_enable()
student.enable_input_require_grads()
student.get_input_embeddings().weight.requires_grad_(False)
scale = getattr(student.config, "logits_scaling", 1.0) or 1.0
trainable = [p for p in student.parameters() if p.requires_grad]
print(f"couches élève {len(student.model.layers)} professeur {len(teacher.model.layers)} ; "
      f"paramètres entraînables {sum(p.numel() for p in trainable):,}", flush=True)


def batches(data, size):
    for s in range(0, len(data), size):
        chunk = data[s:s + size]
        n = max(len(i) for i, _ in chunk)
        ids = torch.full((len(chunk), n), tok.pad_token_id)
        lab = torch.full((len(chunk), n), -100)
        att = torch.zeros((len(chunk), n), dtype=torch.long)
        for k, (i, l) in enumerate(chunk):
            ids[k, :len(i)] = torch.tensor(i); lab[k, :len(l)] = torch.tensor(l); att[k, :len(i)] = 1
        yield ids.cuda(), lab.cuda(), att.cuda()


def losses(ids, lab, att, kd):
    tgt = lab[:, 1:]
    keep = tgt != -100
    with torch.autocast("cuda", dtype=torch.bfloat16):
        hs = student.model(input_ids=ids, attention_mask=att).last_hidden_state[:, :-1]
        s_logits = student.lm_head(hs[keep]).float() / scale
    ce = F.cross_entropy(s_logits, tgt[keep], reduction="sum")
    if not kd:
        return ce, None, keep.sum()
    with torch.no_grad(), torch.autocast("cuda", dtype=torch.bfloat16):
        ht = teacher.model(input_ids=ids, attention_mask=att).last_hidden_state[:, :-1]
        t_logits = teacher.lm_head(ht[keep]).float() / scale
    t_logp = F.log_softmax(t_logits / a.temp, -1)
    del t_logits
    kl = F.kl_div(F.log_softmax(s_logits / a.temp, -1), t_logp, log_target=True, reduction="sum") * a.temp ** 2
    return ce, kl, keep.sum()


@torch.no_grad()
def evaluate():
    student.eval()
    tot, n = 0.0, 0
    for ids, lab, att in batches(val, 8):
        ce, _, c = losses(ids, lab, att, False); tot += ce.item(); n += c.item()
    student.train()
    return tot / n


steps_per_epoch = math.ceil(len(train) / a.batch)
total = max(1, round(steps_per_epoch * a.epochs))
eval_every = max(1, steps_per_epoch // a.evals_per_epoch)
# foreach=False : pas de copies temporaires de tous les paramètres (6 Go de VRAM sur l'A1000)
opt = torch.optim.AdamW(trainable, lr=a.lr, weight_decay=0.0, foreach=False)
warm = max(1, int(0.03 * total))
sched = torch.optim.lr_scheduler.LambdaLR(
    opt, lambda s: (s + 1) / warm if s < warm else 0.5 * (1 + math.cos(math.pi * (s - warm) / max(1, total - warm))))
metrics = open(out / "metrics.jsonl", "a")
v0 = evaluate()
print(json.dumps({"eval_ce": round(v0, 4), "epoch": 0}), flush=True)
metrics.write(json.dumps({"step": 0, "val_ce": v0}) + "\n"); metrics.flush()
best, hist, step, t0 = (v0, 0.0, [p.detach().cpu().clone() for p in trainable]), [], 0, time.time()
rng = random.Random(a.seed)
student.train()
stop = False
while step < total and not stop:
    idx = list(range(len(train))); rng.shuffle(idx)
    for s in range(0, len(idx), a.batch):
        if step >= total:
            break
        group = sorted((train[i] for i in idx[s:s + a.batch]), key=lambda x: len(x[0]))
        ntok = sum(sum(1 for x in l if x != -100) for _, l in group)
        ce_sum = kl_sum = 0.0
        for ids, lab, att in batches(group, a.micro):
            ce, kl, _ = losses(ids, lab, att, True)
            ((a.alpha * ce + (1 - a.alpha) * kl) / ntok).backward()
            ce_sum += ce.item(); kl_sum += kl.item()
        torch.nn.utils.clip_grad_norm_(trainable, 1.0)
        opt.step(); sched.step(); opt.zero_grad(set_to_none=True); step += 1
        ep = round(step / steps_per_epoch, 3)
        metrics.write(json.dumps({"step": step, "epoch": ep, "ce": round(ce_sum / ntok, 4), "kl": round(kl_sum / ntok, 4),
                                  "lr": sched.get_last_lr()[0], "s": round(time.time() - t0)}) + "\n"); metrics.flush()
        if step % 20 == 0:
            print(json.dumps({"step": step, "epoch": ep, "ce": round(ce_sum / ntok, 4), "kl": round(kl_sum / ntok, 4),
                              "s": round(time.time() - t0)}), flush=True)
        if step % eval_every == 0 or step == total:
            v = evaluate(); hist.append(v)
            print(json.dumps({"eval_ce": round(v, 4), "epoch": ep}), flush=True)
            metrics.write(json.dumps({"step": step, "epoch": ep, "val_ce": v}) + "\n"); metrics.flush()
            if v < best[0]:
                best = (v, ep, [p.detach().cpu().clone() for p in trainable])
            if len(hist) - 1 - hist.index(min(hist)) >= a.patience:
                print(f"arrêt anticipé à l'époque {ep}", flush=True); stop = True; break

with torch.no_grad():
    for p, b in zip(trainable, best[2]):
        p.copy_(b.to(p.device))
log = {"args": vars(a), "val_before": v0, "best_val": best[0], "best_epoch": best[1], "evals": hist, "steps": step,
       "train_s": round(time.time() - t0, 1), "vram_peak_mb": torch.cuda.max_memory_allocated() // 2**20}
json.dump(log, open(out / "train_log.json", "w"), indent=1)
print(f"meilleure entropie croisée val {best[0]:.4f} à l'époque {best[1]}", flush=True)
student = student.to(torch.bfloat16)
student.config.use_cache = True
student.save_pretrained(out / "merged")
tok.save_pretrained(out / "merged")
print("modèle écrit", flush=True)
