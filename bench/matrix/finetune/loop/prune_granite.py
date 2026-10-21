#!/usr/bin/env python3
"""Élagage de couches de Granite 4.0 H (X1, théorie T2) : influence de chaque couche, choix, découpe.

    python3 prune_granite.py score --model <HF> --data train.jsonl --val val.jsonl --n 200 --drops 4 7 9 --out scores.json
    python3 prune_granite.py cut --model <HF> --drop 3 5 8 --out <dossier HF élagué>

score : influence de bloc à la ShortGPT (BI = 1 - cosinus moyen entre l'entrée et la sortie de la
couche, sur tous les jetons de n entrées tirées du mix), et distance angulaire d'un bloc contigu de k
couches (arccos / pi). Les couches d'attention ne sont jamais retirées : il n'y en a que quatre et elles
seules voient loin dans l'entrée. Pour chaque k, deux candidats (les k couches de plus faible BI ;
le bloc contigu de mamba seules le plus proche de l'identité) sont évalués sans soin, perte val sur la
réponse seule, et le meilleur est retenu. Seuls des nombres sont écrits, jamais de texte du corpus.

cut : renumérote les couches gardées dans le state dict, réécrit layer_types et num_hidden_layers.

SPDX-License-Identifier: MIT
"""

import argparse
import json
import math
import random
import shutil
from pathlib import Path

import torch
from safetensors.torch import load_file, save_file


def patch_mamba():
    # même contournement que train_sft.py : pas de causal_conv1d CUDA, convolution torch et balayage Triton
    try:
        from transformers.models.granitemoehybrid import modeling_granitemoehybrid as gmh
        gmh.mamba2_split_conv1d_scan_combined = lambda *args, **kw: None
    except ImportError:
        pass


def encode(tok, messages, maxlen):
    def render(msgs, gen):
        return tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=gen)
    prompt, full = render(messages[:-1], True), render(messages, False)
    p_ids = tok(prompt, add_special_tokens=False)["input_ids"]
    c_ids = tok(full[len(prompt):].rstrip("\n"), add_special_tokens=False)["input_ids"]
    ids = (p_ids + c_ids)[-maxlen:]
    labels = ([-100] * len(p_ids) + c_ids)[-len(ids):]
    return ids, labels


@torch.no_grad()
def autocast(device):
    return torch.autocast(device, dtype=torch.bfloat16, enabled=device == "cuda")


def layer_stats(model, rows, blocks, device):
    layers = model.model.layers
    n_layers = len(layers)
    acts = {}

    def hook(i):
        def fn(mod, args, kwargs, out):
            acts[i] = (args[0] if args else kwargs["hidden_states"]).detach(), (out[0] if isinstance(out, tuple) else out).detach()
        return fn

    handles = [layers[i].register_forward_hook(hook(i), with_kwargs=True) for i in range(n_layers)]
    bi_sum = torch.zeros(n_layers, dtype=torch.float64)
    ang = {k: torch.zeros(n_layers - k + 1, dtype=torch.float64) for k in blocks}
    ntok = 0
    for ids, _ in rows:
        x = torch.tensor([ids]).to(device)
        with autocast(device):
            model.model(input_ids=x)
        hin = [acts[i][0][0].float() for i in range(n_layers)]
        hout = [acts[i][1][0].float() for i in range(n_layers)]
        for i in range(n_layers):
            bi_sum[i] += (1 - torch.nn.functional.cosine_similarity(hin[i], hout[i], dim=-1)).sum().item()
        for k in blocks:
            for s in range(n_layers - k + 1):
                c = torch.nn.functional.cosine_similarity(hin[s], hout[s + k - 1], dim=-1).clamp(-1, 1)
                ang[k][s] += (torch.arccos(c) / math.pi).sum().item()
        ntok += len(ids)
    for h in handles:
        h.remove()
    return (bi_sum / ntok).tolist(), {k: (v / ntok).tolist() for k, v in ang.items()}


@torch.no_grad()
def val_loss(model, rows, scale, device):
    tot, n = 0.0, 0
    for ids, lab in rows:
        x, y = torch.tensor([ids]).to(device), torch.tensor([lab]).to(device)
        with autocast(device):
            h = model.model(input_ids=x).last_hidden_state[:, :-1]
            t = y[:, 1:]
            keep = t != -100
            logits = model.lm_head(h[keep]).float() / scale
        tot += torch.nn.functional.cross_entropy(logits, t[keep], reduction="sum").item()
        n += keep.sum().item()
    return tot / n


def with_layers(model, types, keep):
    model.model.layers = torch.nn.ModuleList([model._all_layers[i] for i in keep])
    model.config.layer_types = [types[i] for i in keep]
    model.config.num_hidden_layers = len(keep)


def score(a):
    from transformers import AutoModelForCausalLM, AutoTokenizer
    patch_mamba()
    tok = AutoTokenizer.from_pretrained(a.model)
    lines = open(a.data).readlines()
    random.Random(a.seed).shuffle(lines)
    rows = [encode(tok, json.loads(l)["messages"], a.maxlen) for l in lines[:a.n]]
    val = [encode(tok, json.loads(l)["messages"], a.maxlen) for l in open(a.val)][:a.n_val]
    model = AutoModelForCausalLM.from_pretrained(a.model, dtype=torch.float32).to(a.device).eval()
    model.config.use_cache = False
    scale = getattr(model.config, "logits_scaling", 1.0) or 1.0
    types = list(model.config.layer_types)
    n_layers = len(types)
    attn = [i for i, t in enumerate(types) if t != "mamba" and "linear" not in t]
    bi, ang = layer_stats(model, rows, a.drops, a.device)
    model._all_layers = list(model.model.layers)
    report = {"model": a.model, "n_rows": len(rows), "n_val": len(val), "layer_types": types, "attention": attn,
              "bi": [round(x, 5) for x in bi], "val_full": round(val_loss(model, val, scale, a.device), 4), "drops": {}}
    for k in a.drops:
        mamba = [i for i in range(n_layers) if i not in attn]
        shortgpt = sorted(sorted(mamba, key=lambda i: bi[i])[:k])
        spans = [s for s in range(n_layers - k + 1) if not any(s <= j < s + k for j in attn)]
        best_s = min(spans, key=lambda s: ang[k][s]) if spans else None
        cands = {"shortgpt": shortgpt}
        if best_s is not None:
            cands["block"] = list(range(best_s, best_s + k))
        res = {}
        for name, drop in cands.items():
            with_layers(model, types, [i for i in range(n_layers) if i not in drop])
            res[name] = {"drop": drop, "val_loss": round(val_loss(model, val, scale, a.device), 4)}
            with_layers(model, types, list(range(n_layers)))
        if best_s is not None:
            res["block"]["angular"] = round(ang[k][best_s], 5)
        res["chosen"] = min(("shortgpt", "block") if "block" in res else ("shortgpt",), key=lambda c: res[c]["val_loss"])
        report["drops"][k] = res
        print(k, json.dumps(res), flush=True)
    json.dump(report, open(a.out, "w"), indent=1)


def cut(a):
    src, out = Path(a.model), Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    cfg = json.load(open(src / "config.json"))
    n = cfg["num_hidden_layers"]
    drop = set(a.drop)
    keep = [i for i in range(n) if i not in drop]
    new_idx = {old: new for new, old in enumerate(keep)}
    sd = load_file(str(src / "model.safetensors"))
    res = {}
    for k, v in sd.items():
        if k.startswith("model.layers."):
            i = int(k.split(".")[2])
            if i in drop:
                continue
            k = f"model.layers.{new_idx[i]}." + k.split(".", 3)[3]
        res[k] = v.contiguous()
    save_file(res, str(out / "model.safetensors"), metadata={"format": "pt"})
    cfg["layer_types"] = [cfg["layer_types"][i] for i in keep]
    cfg["num_hidden_layers"] = len(keep)
    json.dump(cfg, open(out / "config.json", "w"), indent=2)
    for f in src.iterdir():
        if f.is_file() and f.name not in ("model.safetensors", "config.json") and not f.name.endswith((".sig", ".md")):
            shutil.copy(f, out / f.name)
    print(f"{n} -> {len(keep)} couches, retirées {sorted(drop)}, {len(res)} tenseurs")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("score")
    s.add_argument("--model", required=True)
    s.add_argument("--data", required=True)
    s.add_argument("--val", required=True)
    s.add_argument("--n", type=int, default=200)
    s.add_argument("--n-val", dest="n_val", type=int, default=10**9)
    s.add_argument("--device", default="cuda")
    s.add_argument("--maxlen", type=int, default=1536)
    s.add_argument("--seed", type=int, default=42)
    s.add_argument("--drops", type=int, nargs="+", default=[4, 7])
    s.add_argument("--out", required=True)
    c = sub.add_parser("cut")
    c.add_argument("--model", required=True)
    c.add_argument("--drop", type=int, nargs="+", required=True)
    c.add_argument("--out", required=True)
    a = ap.parse_args()
    score(a) if a.cmd == "score" else cut(a)


if __name__ == "__main__":
    main()
