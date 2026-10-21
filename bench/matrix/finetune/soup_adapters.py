"""Soupe de poids : fusion de chaque adaptateur LoRA dans la base, moyenne uniforme et soupe gloutonne,
perte val calculée exactement comme train_sft.py (perte sur la réponse seule, autocast bf16).
Script de P15 (soup_p15.py), repris tel quel pour K3.

SPDX-License-Identifier: MIT
"""
import argparse, copy, json, shutil
from pathlib import Path

import torch
from safetensors.torch import load_file
from transformers import AutoModelForCausalLM, AutoTokenizer

ap = argparse.ArgumentParser()
ap.add_argument("--model", required=True)
ap.add_argument("--val", required=True)
ap.add_argument("--adapters", nargs="+", required=True, help="nom=dossier_adaptateur")
ap.add_argument("--out", required=True)
ap.add_argument("--maxlen", type=int, default=1536)
a = ap.parse_args()
out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
tok = AutoTokenizer.from_pretrained(a.model)


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
    return ids, ([-100] * len(p_ids) + c_ids)[-len(ids):]


val = [encode(json.loads(l)["messages"]) for l in open(a.val)]

# même chemin Mamba que train.py : convolution torch et balayage Triton
from transformers.models.granitemoehybrid import modeling_granitemoehybrid as _gmh
_gmh.mamba2_split_conv1d_scan_combined = lambda *args, **kw: None
model = AutoModelForCausalLM.from_pretrained(a.model, dtype=torch.float32).cuda().eval()
logit_scale = getattr(model.config, "logits_scaling", 1.0) or 1.0
params = dict(model.named_parameters())
base = {}


def deltas_of(folder):
    cfg = json.load(open(Path(folder) / "adapter_config.json"))
    assert not cfg.get("use_rslora") and not cfg.get("use_dora") and not cfg.get("fan_in_fan_out")
    scale = cfg["lora_alpha"] / cfg["r"]
    sd = load_file(str(Path(folder) / "adapter_model.safetensors"))
    d = {}
    for k in sd:
        if not k.endswith("lora_A.weight"):
            continue
        name = k.replace("base_model.model.", "", 1).replace(".lora_A.weight", ".weight")
        assert name in params, name
        B = sd[k.replace("lora_A", "lora_B")].float()
        d[name] = (B @ sd[k].float()) * scale
        base.setdefault(name, params[name].detach().cpu().clone())
    assert len(d) == sum(k.endswith("lora_A.weight") for k in sd)
    return d


@torch.no_grad()
def load_mix(members):
    for name, w in base.items():
        acc = sum(D[m][name] for m in members) / len(members)
        params[name].copy_((w + acc).cuda())


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


@torch.no_grad()
def val_loss():
    tot, n = 0.0, 0
    for ids, lab, att in batches(val, 8):
        with torch.autocast("cuda", dtype=torch.bfloat16):
            hidden = model.model(input_ids=ids, attention_mask=att).last_hidden_state[:, :-1]
            tgt = lab[:, 1:]; keep = tgt != -100
            logits = model.lm_head(hidden[keep]).float() / logit_scale
        tot += torch.nn.functional.cross_entropy(logits, tgt[keep], reduction="sum").item(); n += keep.sum().item()
    return tot / n


D = {}
for spec in a.adapters:
    name, folder = spec.split("=", 1)
    D[name] = deltas_of(folder)
    print(f"adaptateur {name} : {len(D[name])} matrices", flush=True)
names = list(D)
assert all(set(D[n]) == set(base) for n in names)

report = {"base_val": None, "seeds": {}}
report["base_val"] = round(val_loss(), 4)
for n in names:
    load_mix([n]); report["seeds"][n] = round(val_loss(), 4)
    print(f"{n} fusionné : val {report['seeds'][n]}", flush=True)
order = sorted(names, key=lambda n: report["seeds"][n])
load_mix(names); report["uniform"] = {"members": names, "val": round(val_loss(), 4)}
print(f"uniforme : val {report['uniform']['val']}", flush=True)
greedy, best, steps = [order[0]], report["seeds"][order[0]], []
for n in order[1:]:
    load_mix(greedy + [n]); v = val_loss()
    steps.append({"try": n, "val": round(v, 4), "kept": v < best})
    print(f"glouton + {n} : val {v:.4f} ({'gardé' if v < best else 'rejeté'})", flush=True)
    if v < best:
        greedy.append(n); best = v
report["greedy"] = {"members": greedy, "val": round(best, 4), "steps": steps}
report["best_seed"] = order[0]


def save(members, folder):
    load_mix(members)
    m = copy.deepcopy(model).to(torch.bfloat16)
    m.config.use_cache = True
    m.save_pretrained(folder); tok.save_pretrained(folder)
    for f in ["config.json", "tokenizer.model", "tokenizer_config.json", "tokenizer.json",
              "special_tokens_map.json", "added_tokens.json"]:
        if (Path(a.model) / f).exists():
            shutil.copy(Path(a.model) / f, Path(folder) / f)
    del m; torch.cuda.empty_cache()


save(names, out / "merged-uniform")


json.dump(report, open(out / "soup_report.json", "w"), indent=1)
print(json.dumps(report), flush=True)
