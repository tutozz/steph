"""SFT rapide pour la boucle d'optimisation : LoRA ou affinage complet, perte sur la réponse seule,
évaluation plusieurs fois par époque, arrêt anticipé sur la perte val, meilleur état fusionné.

Script de P15 (Granite 4.0 H : chemin Mamba torch + Triton), suivi temps réel de K0 en plus :
out/metrics.jsonl à chaque pas, out/status.json, et out/control.json lu à chaque pas
(train_control.sh : stop, slower, eval).

SPDX-License-Identifier: MIT
"""
import argparse, json, math, os, random, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from train_lora import append_metrics, read_control, write_status  # noqa: E402

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

ap = argparse.ArgumentParser()
ap.add_argument("--model", required=True)
ap.add_argument("--train", required=True)
ap.add_argument("--val", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--mode", choices=["lora", "full"], default="lora")
ap.add_argument("--rank", type=int, default=16)
ap.add_argument("--alpha", type=int, default=32)
ap.add_argument("--dropout", type=float, default=0.05)
ap.add_argument("--lr", type=float, default=2e-4)
ap.add_argument("--wd", type=float, default=0.0)
ap.add_argument("--epochs", type=float, default=3)
ap.add_argument("--maxlen", type=int, default=1536)
ap.add_argument("--micro", type=int, default=8)
ap.add_argument("--batch", type=int, default=16)
ap.add_argument("--evals-per-epoch", type=int, default=4)
ap.add_argument("--patience", type=int, default=3)
ap.add_argument("--neftune", type=float, default=0.0)
ap.add_argument("--eos-weight", type=float, default=1.0)
ap.add_argument("--seed", type=int, default=42)
ap.add_argument("--freeze-emb", action="store_true", help="full : embeddings (liés à lm_head) gelés")
ap.add_argument("--targets", default="attn-mlp", help="attn-mlp (Gemma, Qwen), all-linear, ou liste de modules séparés par des virgules")
ap.add_argument("--gc", action="store_true", help="gradient checkpointing")
ap.add_argument("--save-adapter", action="store_true", help="lora : écrit aussi l'adaptateur du meilleur point dans out/adapter")
ap.add_argument("--no-merge", action="store_true", help="n'écrit pas out/merged (l'adaptateur suffit à la soupe)")
ap.add_argument("--dtype", choices=["float32", "bfloat16"], default="float32",
                help="poids de base ; bfloat16 fait tenir un 3B en LoRA sur 12 Go (adaptateur gardé en float32 par peft)")
a = ap.parse_args()

random.seed(a.seed); torch.manual_seed(a.seed); torch.cuda.manual_seed_all(a.seed)
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
    labels = ([-100] * len(p_ids) + c_ids)[-len(ids):]
    return ids, labels


def load(path):
    return [encode(json.loads(l)["messages"]) for l in open(path)]


train, val = load(a.train), load(a.val)
lens = sorted(len(i) for i, _ in train)
print(f"train {len(train)} val {len(val)} ; jetons médiane {lens[len(lens)//2]} max {lens[-1]}", flush=True)

try:
    # Granite 4.0 H : le chemin fusionné de mamba_ssm exige causal_conv1d CUDA (non compilé ici) et
    # contourne la LoRA de out_proj ; on garde la convolution torch et le balayage Triton.
    from transformers.models.granitemoehybrid import modeling_granitemoehybrid as _gmh
    _gmh.mamba2_split_conv1d_scan_combined = lambda *args, **kw: None
except ImportError:
    pass
model = AutoModelForCausalLM.from_pretrained(a.model, dtype=getattr(torch, a.dtype)).cuda()
logit_scale = getattr(model.config, "logits_scaling", 1.0) or 1.0
model.config.use_cache = False
if a.gc:
    model.gradient_checkpointing_enable()
    model.enable_input_require_grads()
if a.mode == "lora":
    from peft import LoraConfig, get_peft_model
    model = get_peft_model(model, LoraConfig(
        r=a.rank, lora_alpha=a.alpha, lora_dropout=a.dropout, task_type="CAUSAL_LM",
        target_modules="all-linear" if a.targets == "all-linear" else
        a.targets.split(",") if "," in a.targets else
        ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]))
inner = model.get_base_model() if a.mode == "lora" else model
if a.mode == "full" and a.freeze_emb:
    inner.get_input_embeddings().weight.requires_grad_(False)
trainable = [p for p in model.parameters() if p.requires_grad]
print(f"paramètres entraînables {sum(p.numel() for p in trainable):,}", flush=True)
if a.mode == "lora":
    print("cibles LoRA :", sorted({n.split(".")[-2] for n, _ in model.named_modules() if n.endswith(".lora_A")}), flush=True)
eos_id = tok.convert_tokens_to_ids("<end_of_turn>") if "<end_of_turn>" in tok.get_vocab() else tok.eos_token_id
print("chemin mamba :", getattr(sys.modules.get("transformers.models.granitemoehybrid.modeling_granitemoehybrid"), "mamba2_chunk_scan", None), flush=True)

if a.neftune > 0:
    def neft_hook(module, inp, output):
        if module.training:
            dims = output.size(1) * output.size(2)
            mag = a.neftune / math.sqrt(dims)
            output = output + torch.zeros_like(output).uniform_(-mag, mag)
        return output
    inner.get_input_embeddings().register_forward_hook(neft_hook)


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


def token_loss(ids, lab, att, weighted):
    # logits aux seules positions cibles : le vocabulaire de 262k rend le calcul complet trop lourd
    with torch.autocast("cuda", dtype=torch.bfloat16):
        hidden = inner.model(input_ids=ids, attention_mask=att).last_hidden_state[:, :-1]
        tgt = lab[:, 1:]
        keep = tgt != -100
        logits = inner.lm_head(hidden[keep]).float() / logit_scale
    t = tgt[keep]
    ce = torch.nn.functional.cross_entropy(logits, t, reduction="none")
    if weighted and a.eos_weight != 1.0:
        ce = ce * torch.where(t == eos_id, a.eos_weight, 1.0)
    return ce.sum(), keep.sum()


@torch.no_grad()
def evaluate():
    model.eval()
    tot, n = 0.0, 0
    for ids, lab, att in batches(val, 8):
        l, c = token_loss(ids, lab, att, False); tot += l.item(); n += c.item()
    model.train()
    return tot / n


def snapshot():
    return [p.detach().to("cpu", copy=True) for p in trainable]


steps_per_epoch = math.ceil(len(train) / a.batch)
total_steps = max(1, round(steps_per_epoch * a.epochs))
eval_every = max(1, steps_per_epoch // a.evals_per_epoch)
opt = torch.optim.AdamW(trainable, lr=a.lr, weight_decay=a.wd)
warm = max(1, int(0.03 * total_steps))
sched = torch.optim.lr_scheduler.LambdaLR(
    opt, lambda s: (s + 1) / warm if s < warm else 0.5 * (1 + math.cos(math.pi * (s - warm) / max(1, total_steps - warm))))
rng = random.Random(a.seed)
metrics, status, control = out / "metrics.jsonl", out / "status.json", out / "control.json"
write_status(status, state="running", pid=os.getpid(), step=0, total_steps=total_steps)
lr_scale = 1.0
v0 = evaluate()
append_metrics(metrics, {"step": 0, "epoch": 0.0, "val_loss": v0})
print(json.dumps({"eval_loss": round(v0, 4), "epoch": 0.0}), flush=True)
best = (v0, 0, snapshot() if a.epochs == 0 else None)
hist, step, t0, run_loss, run_tok = [], 0, time.time(), 0.0, 0
model.train()
stop = False
while step < total_steps and not stop:
    idx = list(range(len(train))); rng.shuffle(idx)
    # tri par longueur à l'intérieur de chaque groupe : moins de remplissage
    for s in range(0, len(idx), a.batch):
        if step >= total_steps:
            break
        group = sorted((train[i] for i in idx[s:s + a.batch]), key=lambda x: len(x[0]))
        ntok = sum(sum(1 for x in l if x != -100) for _, l in group)
        for ids, lab, att in batches(group, a.micro):
            l, c = token_loss(ids, lab, att, True)
            (l / ntok).backward()
            run_loss += l.item(); run_tok += c.item()
        torch.nn.utils.clip_grad_norm_(trainable, 1.0)
        step_loss = run_loss / max(run_tok, 1)
        opt.step(); sched.step(); opt.zero_grad(set_to_none=True); step += 1
        for g in opt.param_groups:
            g["lr"] *= lr_scale
        ep = round(step / steps_per_epoch, 3)
        append_metrics(metrics, {"step": step, "epoch": ep, "loss": round(step_loss, 4), "lr": opt.param_groups[0]["lr"],
                                 "s": round(time.time() - t0)})
        ctrl = read_control(control)
        if ctrl.get("action") == "stop":
            print(f"arrêt demandé à l'époque {ep}", flush=True); stop = True
        if "lr_scale" in ctrl:
            lr_scale *= float(ctrl["lr_scale"])
        if step % 10 == 0:
            print(json.dumps({"loss": round(run_loss / run_tok, 4), "epoch": ep, "lr": sched.get_last_lr()[0],
                              "s": round(time.time() - t0)}), flush=True)
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
log = {"args": vars(a), "val_before": v0, "best_val": best[0], "best_epoch": best[1], "evals": hist,
       "steps": step, "train_s": train_s, "vram_peak_mb": torch.cuda.max_memory_allocated() // 2**20}
json.dump(log, open(out / "train_log.json", "w"), indent=1)
print(f"meilleure perte val {best[0]:.4f} à l'époque {best[1]} ; {train_s} s", flush=True)
if a.save_adapter and a.mode == "lora":
    model.save_pretrained(out / "adapter")
    print("adaptateur écrit", flush=True)
write_status(status, state="stopped" if stop else "done", step=step, best_val=best[0], best_epoch=best[1])
if a.no_merge:
    sys.exit(0)
merged = model.merge_and_unload() if a.mode == "lora" else model
merged = merged.to(torch.bfloat16)
merged.config.use_cache = True
merged.save_pretrained(out / "merged")
tok.save_pretrained(out / "merged")
print("fusion écrite", flush=True)
