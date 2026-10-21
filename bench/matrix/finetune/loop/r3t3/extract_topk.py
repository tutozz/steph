#!/usr/bin/env python3
"""R3-T3 : logits top-k de l'enseignant sur les positions de réponse du mix, pour train_kd.py.

    python3 extract_topk.py --teacher <HF> [--adapter <LoRA> --qlora] --tok <HF de l'élève> --data train.jsonl [...] --out topk.pt [--k 32]

Rendu et coupe identiques à train_sft.py, avec le tokeniseur de l'élève (octet pour octet celui de
l'enseignant, vérifié) : les identifiants vus par l'enseignant sont ceux que verra l'élève. Clé = sha256 du
rendu complet ; valeur = (indices int32 [n, k], logits float16 [n, k]) après division par logits_scaling,
positions dans l'ordre croissant. Le fichier reste sur l'hôte du corpus.

SPDX-License-Identifier: MIT
"""
import argparse
import hashlib
import json

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

ap = argparse.ArgumentParser()
ap.add_argument("--teacher", required=True)
ap.add_argument("--tok", required=True)
ap.add_argument("--data", nargs="+", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--k", type=int, default=32)
ap.add_argument("--maxlen", type=int, default=1536)
ap.add_argument("--adapter", help="adaptateur LoRA de l'enseignant, appliqué sans fusion")
ap.add_argument("--qlora", action="store_true", help="base NF4, comme à l'entraînement : l'objet entraîné, et tient à côté d'un juge 9B")
a = ap.parse_args()

tok = AutoTokenizer.from_pretrained(a.tok)


def render(messages, gen):
    try:
        return tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=gen, enable_thinking=False)
    except TypeError:
        return tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=gen)


def encode(messages):
    prompt, full = render(messages[:-1], True), render(messages, False)
    assert full.startswith(prompt)
    p_ids = tok(prompt, add_special_tokens=False)["input_ids"]
    c_ids = tok(full[len(prompt):].rstrip("\n"), add_special_tokens=False)["input_ids"]
    ids = (p_ids + c_ids)[-a.maxlen:]
    labels = ([-100] * len(p_ids) + c_ids)[-len(ids):]
    return ids, labels, hashlib.sha256(full.encode()).hexdigest()


if a.qlora:
    from transformers import BitsAndBytesConfig
    model = AutoModelForCausalLM.from_pretrained(a.teacher, dtype=torch.bfloat16, device_map={"": 0}, quantization_config=BitsAndBytesConfig(
        load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=torch.bfloat16))
else:
    model = AutoModelForCausalLM.from_pretrained(a.teacher, dtype=torch.bfloat16).cuda()
if a.adapter:
    from peft import PeftModel
    model = PeftModel.from_pretrained(model, a.adapter).get_base_model()
model.eval()
scale = getattr(model.config, "logits_scaling", 1.0) or 1.0
rows = [encode(json.loads(line)["messages"]) for p in a.data for line in open(p)]
out, top1 = {}, [0, 0]
with torch.no_grad():
    for n, (ids, lab, key) in enumerate(rows, 1):
        if key in out:
            continue
        x = torch.tensor([ids]).cuda()
        hidden = model.model(input_ids=x).last_hidden_state[0, :-1]
        tgt = torch.tensor(lab[1:]).cuda()
        keep = tgt != -100
        logits = model.lm_head(hidden[keep]).float() / scale
        val, idx = logits.topk(a.k, dim=-1)
        out[key] = (idx.to(torch.int32).cpu(), val.to(torch.float16).cpu())
        top1[0] += int((idx[:, 0] == tgt[keep]).sum()); top1[1] += int(keep.sum())
        if n % 500 == 0:
            print(f"{n}/{len(rows)}", flush=True)
torch.save(out, a.out)
print(json.dumps({"examples": len(out), "tokens": top1[1], "k": a.k,
                  "teacher_top1_agreement_with_label": round(top1[0] / max(top1[1], 1), 4)}))
