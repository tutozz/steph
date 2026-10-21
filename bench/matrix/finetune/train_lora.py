#!/usr/bin/env python3
"""Script d'entraînement LoRA commun à toutes les machines du labo.

    python3 train_lora.py --model <id HF ou dossier> --train train.jsonl --val val.jsonl --out out_dir

Perte calculée seulement sur la réponse de l'assistant, gabarit de chat du modèle
(``enable_thinking=False`` quand il existe), lot et accumulation choisis automatiquement
selon la VRAM libre et la taille du vocabulaire (``--batch auto``), arrêt anticipé sur la
perte de validation, et contrôle en temps réel par fichier (``control.json``) pendant que
``metrics.jsonl`` et ``status.json`` s'écrivent à chaque pas.

Pièges déjà rencontrés, et où ce script les évite :
- ``TrainingArguments.warmup_ratio`` est refusé par transformers 5 : la rampe de
  ``scheduled_lr`` est calculée à la main, jamais via ``TrainingArguments``.
- Gemma 3 (vocabulaire 262 000 jetons) sature 6 Go de VRAM : ``choose_batch`` réduit le lot
  au-delà de 100 000 jetons de vocabulaire, et le gradient checkpointing est toujours actif.
- Qwen3.5 : les tenseurs MTP doivent être recollés avant la conversion GGUF (rappel affiché
  par ``finish()``, la conversion elle-même reste manuelle).

Les fonctions de ce module qui n'importent ni torch ni transformers ni peft sont en tête de
fichier : elles restent testables sans ces paquets (voir tests/test_train_lora.py). Les
imports lourds sont faits à l'intérieur des fonctions qui en ont besoin.

SPDX-License-Identifier: MIT
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import time
from pathlib import Path
from typing import Any

IGNORE_INDEX = -100
DEFAULT_TARGET_EFFECTIVE_BATCH = 16


# ---------------------------------------------------------------------------
# Partie pure : aucun import torch/transformers/peft, testable sans eux.
# ---------------------------------------------------------------------------


def choose_batch(
    vram_free_mb: float | None,
    vocab_size: int,
    target_effective: int = DEFAULT_TARGET_EFFECTIVE_BATCH,
    max_batch: int = 16,
) -> tuple[int, int]:
    """Choisit lot et accumulation pour un lot effectif proche de `target_effective`.

    Un grand vocabulaire (tête lm_head à 100k+ jetons) coûte cher en mémoire par exemple
    du lot (logits de taille lot x longueur x vocabulaire) : le budget est réduit d'autant,
    indépendamment de la VRAM libre. Sans VRAM connue (CPU), le choix le plus sûr est un
    lot de 1 entièrement compensé par l'accumulation.
    """
    if not vram_free_mb or vram_free_mb <= 0:
        return 1, target_effective

    gb = vram_free_mb / 1024
    if gb < 8:
        batch = 1
    elif gb < 16:
        batch = 2
    elif gb < 24:
        batch = 4
    elif gb < 48:
        batch = 8
    else:
        batch = 16

    if vocab_size >= 200_000:
        batch = max(1, batch // 4)
    elif vocab_size >= 100_000:
        batch = max(1, batch // 2)

    batch = min(batch, max_batch)
    grad_accum = max(1, round(target_effective / batch))
    return batch, grad_accum


def read_control(path: Path) -> dict[str, Any]:
    """Lit control.json s'il existe, sinon {}. Consommé (supprimé) une fois lu avec succès.

    Une lecture pendant une écriture ssh concurrente peut tomber sur un JSON à moitié
    écrit : dans ce cas le fichier n'est PAS supprimé, pour retenter au pas suivant.
    """
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    path.unlink(missing_ok=True)
    return data if isinstance(data, dict) else {}


def should_stop_early(val_losses: list[float], patience: int) -> bool:
    """Arrêt anticipé : vrai si la perte val n'a plus baissé depuis `patience` évaluations."""
    if len(val_losses) <= patience:
        return False
    best_idx = min(range(len(val_losses)), key=lambda i: val_losses[i])
    return (len(val_losses) - 1 - best_idx) >= patience


def build_labels(prompt_ids: list[int], full_ids: list[int], ignore_index: int = IGNORE_INDEX) -> list[int]:
    """Masque la perte sur tout ce qui précède la réponse de l'assistant.

    Le gabarit de chat peut diverger légèrement entre le rendu du prompt seul (avec balise
    de génération) et celui de la conversation complète : on masque au plus long préfixe
    commun plutôt que de supposer une égalité stricte des deux rendus.
    """
    common = 0
    for a, b in zip(prompt_ids, full_ids):
        if a != b:
            break
        common += 1
    return [ignore_index] * common + list(full_ids[common:])


def pad_batch(sequences: list[list[int]], pad_value: int) -> tuple[list[list[int]], list[list[int]]]:
    """Complète des séquences de longueurs différentes à la même longueur, avec le masque."""
    max_len = max(len(s) for s in sequences)
    padded, mask = [], []
    for s in sequences:
        pad_n = max_len - len(s)
        padded.append(list(s) + [pad_value] * pad_n)
        mask.append([1] * len(s) + [0] * pad_n)
    return padded, mask


def scheduled_lr(step: int, total_steps: int, warmup_steps: int, base_lr: float) -> float:
    """Rampe linéaire puis décroissance linéaire vers 0, calculée à la main.

    Fait exprès sans passer par ``TrainingArguments`` : son ``warmup_ratio`` est refusé par
    transformers 5, alors qu'un nombre de pas calculé ici ne dépend d'aucune de ses options.
    """
    if warmup_steps > 0 and step < warmup_steps:
        return base_lr * (step + 1) / warmup_steps
    remaining = max(total_steps - warmup_steps, 1)
    progress = (step - warmup_steps) / remaining
    return base_lr * max(0.0, 1.0 - progress)


def append_metrics(path: Path, record: dict) -> None:
    """Ajoute une ligne à metrics.jsonl."""
    with path.open("a") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def write_status(path: Path, **fields) -> None:
    """Écrit status.json de façon atomique (fichier temporaire puis renommage)."""
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(fields, ensure_ascii=False))
    tmp.replace(path)


def load_jsonl(path: Path) -> list[dict]:
    with path.open() as f:
        return [json.loads(line) for line in f if line.strip()]


def is_qwen35(model_id: str) -> bool:
    low = model_id.lower()
    return "qwen3.5" in low or "qwen3-5" in low


def iter_micro_batches(n: int, batch_size: int, seed: int, epoch: int) -> list[list[int]]:
    """Ordre mélangé (déterministe par epoch) des indices, découpé en lots de `batch_size`."""
    order = list(range(n))
    random.Random(seed + epoch).shuffle(order)
    return [order[i : i + batch_size] for i in range(0, n, batch_size)]


# ---------------------------------------------------------------------------
# Partie torch/transformers/peft : imports faits à l'intérieur des fonctions,
# pour que la partie pure ci-dessus reste importable sans ces paquets.
# ---------------------------------------------------------------------------


def detect_device(pref: str) -> str:
    if pref != "auto":
        return pref
    import torch

    return "cuda" if torch.cuda.is_available() else "cpu"


def detect_vram_free_mb(device: str) -> float | None:
    if device != "cuda":
        return None
    import torch

    free, _total = torch.cuda.mem_get_info()
    return free / (1024 * 1024)


def detect_bf16(device: str, pref: str) -> bool:
    if pref == "true":
        return True
    if pref == "false":
        return False
    import torch

    return device == "cuda" and torch.cuda.is_bf16_supported()


def render_chat_ids(tokenizer, messages: list[dict], add_generation_prompt: bool) -> list[int]:
    kwargs = dict(add_generation_prompt=add_generation_prompt, tokenize=True)
    try:
        enc = tokenizer.apply_chat_template(messages, enable_thinking=False, **kwargs)
    except TypeError:
        enc = tokenizer.apply_chat_template(messages, **kwargs)
    # transformers 5 renvoie un BatchEncoding (dict-like) plutôt qu'une liste brute d'ids.
    return list(enc) if isinstance(enc, list) else list(enc["input_ids"])


def tokenize_example(tokenizer, messages: list[dict], max_len: int) -> dict:
    prompt_ids = render_chat_ids(tokenizer, messages[:-1], add_generation_prompt=True)
    full_ids = render_chat_ids(tokenizer, messages, add_generation_prompt=False)
    if len(full_ids) > max_len:
        over = len(full_ids) - max_len
        full_ids = full_ids[over:]
        prompt_ids = prompt_ids[over:] if over < len(prompt_ids) else []
    labels = build_labels(prompt_ids, full_ids)
    return {"input_ids": full_ids, "labels": labels}


def collate(examples: list[dict], pad_token_id: int, device):
    import torch

    ids = [e["input_ids"] for e in examples]
    labels = [e["labels"] for e in examples]
    padded_ids, mask = pad_batch(ids, pad_token_id)
    padded_labels, _ = pad_batch(labels, IGNORE_INDEX)
    return (
        torch.tensor(padded_ids, device=device),
        torch.tensor(mask, device=device),
        torch.tensor(padded_labels, device=device),
    )


def training_step(model, optimizer, micro_batches: list[list[dict]], device, pad_token_id: int):
    import torch

    optimizer.zero_grad()
    total_loss = 0.0
    total_tokens = 0
    for micro in micro_batches:
        input_ids, attention_mask, labels = collate(micro, pad_token_id, device)
        outputs = model(input_ids=input_ids, attention_mask=attention_mask, labels=labels)
        (outputs.loss / len(micro_batches)).backward()
        total_loss += outputs.loss.item()
        total_tokens += int(attention_mask.sum().item())
    trainable = [p for p in model.parameters() if p.requires_grad]
    grad_norm = torch.nn.utils.clip_grad_norm_(trainable, max_norm=1.0)
    optimizer.step()
    return total_loss / len(micro_batches), float(grad_norm), total_tokens


def evaluate(model, val_examples: list[dict], device, pad_token_id: int, batch_size: int = 4) -> float:
    import torch

    model.eval()
    total_loss, n_batches = 0.0, 0
    with torch.no_grad():
        for i in range(0, len(val_examples), batch_size):
            chunk = val_examples[i : i + batch_size]
            input_ids, attention_mask, labels = collate(chunk, pad_token_id, device)
            outputs = model(input_ids=input_ids, attention_mask=attention_mask, labels=labels)
            total_loss += outputs.loss.item()
            n_batches += 1
    model.train()
    return total_loss / max(n_batches, 1)


def save_adapter(model, path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(path)


def merge_and_save(model, tokenizer, out_dir: Path) -> Path:
    merged_dir = out_dir / "merged"
    merged_dir.mkdir(parents=True, exist_ok=True)
    merged = model.merge_and_unload()
    merged.save_pretrained(merged_dir)
    tokenizer.save_pretrained(merged_dir)
    return merged_dir


def finish(args, model, tokenizer, out_dir: Path) -> None:
    if args.merge:
        merged_dir = merge_and_save(model, tokenizer, out_dir)
        target = str(merged_dir)
    else:
        target = f"<dossier fusionné : relancer avec --resume-from {out_dir / 'best'} --merge --epochs 0>"
    print("conversion GGUF (à lancer à la main, jamais exécutée par ce script) :")
    if is_qwen35(args.model):
        print("  ATTENTION Qwen3.5 : recoller les tenseurs MTP avant la conversion (voir la doc du modèle).")
    print(f"  python3 convert_hf_to_gguf.py {target} --outfile {target}.gguf")


def build_model(args, device: str, bf16: bool):
    import torch
    from peft import LoraConfig, PeftModel, get_peft_model
    from transformers import AutoModelForCausalLM

    dtype = torch.bfloat16 if bf16 else torch.float32
    model = AutoModelForCausalLM.from_pretrained(args.model, dtype=dtype)
    model.to(device)
    model.config.use_cache = False
    model.gradient_checkpointing_enable()

    if args.resume_from:
        model = PeftModel.from_pretrained(model, args.resume_from, is_trainable=True)
    else:
        lora_config = LoraConfig(
            r=args.rank,
            lora_alpha=args.alpha,
            lora_dropout=args.dropout,
            target_modules="all-linear",
            task_type="CAUSAL_LM",
        )
        model = get_peft_model(model, lora_config)

    # Requis avec le gradient checkpointing sur un modèle dont l'embedding est gelé (peft) :
    # sans ça le graphe de calcul ne remonte jamais jusqu'aux couches LoRA.
    if hasattr(model, "enable_input_require_grads"):
        model.enable_input_require_grads()
    return model


def run(args) -> None:
    import torch
    from transformers import AutoTokenizer

    out_dir: Path = args.out
    metrics_path = out_dir / "metrics.jsonl"
    status_path = out_dir / "status.json"
    control_path = out_dir / "control.json"
    best_dir = out_dir / "best"

    device = detect_device(args.device)
    bf16 = detect_bf16(device, args.bf16)

    tokenizer = AutoTokenizer.from_pretrained(args.model)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    train_rows = load_jsonl(args.train)
    val_rows = load_jsonl(args.val)
    train_examples = [tokenize_example(tokenizer, r["messages"], args.max_len) for r in train_rows]
    val_examples = [tokenize_example(tokenizer, r["messages"], args.max_len) for r in val_rows]

    vocab_size = getattr(tokenizer, "vocab_size", len(tokenizer))
    vram_free = detect_vram_free_mb(device)
    auto_batch, auto_accum = choose_batch(vram_free, vocab_size)
    batch_size = auto_batch if args.batch == "auto" else args.batch
    grad_accum = auto_accum if args.grad_accum == "auto" else args.grad_accum

    model = build_model(args, device, bf16)
    optimizer = torch.optim.AdamW((p for p in model.parameters() if p.requires_grad), lr=args.lr)

    steps_per_epoch = max(1, math.ceil(len(train_examples) / (batch_size * grad_accum)))
    total_steps = steps_per_epoch * args.epochs
    warmup_steps = max(1, round(0.03 * total_steps))
    eval_every = args.eval_every if args.eval_every else max(1, steps_per_epoch // 10)

    best_val = math.inf
    val_history: list[float] = []
    lr_scale = 1.0
    global_step = 0
    epoch_step = 0
    stop_requested = False
    start_time = time.time()
    last_step_time = start_time

    write_status(status_path, state="running", pid=os.getpid(), step=0, epoch=0)

    def run_step(accum_indices: list[list[int]], epoch: int) -> None:
        # Un pas d'optimisation sur `accum_indices` micro-lots (le dernier groupe d'une
        # epoch peut être plus petit que `grad_accum` : le lot effectif est alors réduit,
        # mais le pas a quand même lieu, pour ne jamais perdre silencieusement ces exemples.
        nonlocal global_step, epoch_step, lr_scale, stop_requested, best_val, last_step_time
        micro_batches = [[train_examples[i] for i in idx] for idx in accum_indices]
        loss, grad_norm, tokens = training_step(model, optimizer, micro_batches, device, tokenizer.pad_token_id)
        global_step += 1
        epoch_step += 1

        lr = scheduled_lr(global_step, total_steps, warmup_steps, args.lr) * lr_scale
        for g in optimizer.param_groups:
            g["lr"] = lr

        now = time.time()
        step_time = max(now - last_step_time, 1e-6)
        last_step_time = now
        eta = (total_steps - global_step) * step_time
        vram_mb = torch.cuda.memory_allocated() / (1024 * 1024) if device == "cuda" else None

        append_metrics(
            metrics_path,
            {
                "step": global_step,
                "epoch": epoch + epoch_step / max(steps_per_epoch, 1),
                "loss": loss,
                "val_loss": val_history[-1] if val_history else None,
                "grad_norm": grad_norm,
                "lr": lr,
                "tokens_per_sec": tokens / step_time,
                "vram_mb": vram_mb,
                "eta_seconds": eta,
            },
        )

        ctrl = read_control(control_path)
        if ctrl.get("action") == "stop":
            stop_requested = True
        if "lr_scale" in ctrl:
            lr_scale *= float(ctrl["lr_scale"])
        force_eval = bool(ctrl.get("eval_now"))

        if force_eval or global_step % eval_every == 0:
            val_loss = evaluate(model, val_examples, device, tokenizer.pad_token_id, batch_size=batch_size)
            val_history.append(val_loss)
            append_metrics(metrics_path, {"step": global_step, "epoch": epoch, "val_loss": val_loss})
            if val_loss < best_val:
                best_val = val_loss
                save_adapter(model, best_dir)
            if should_stop_early(val_history, args.patience):
                stop_requested = True

        write_status(status_path, state="running", step=global_step, epoch=epoch,
                     best_val_loss=None if math.isinf(best_val) else best_val)

    for epoch in range(args.epochs):
        if stop_requested:
            break
        epoch_step = 0
        batches = iter_micro_batches(len(train_examples), batch_size, args.seed, epoch)
        accum: list[list[int]] = []
        for indices in batches:
            accum.append(indices)
            if len(accum) < grad_accum:
                continue
            run_step(accum, epoch)
            accum = []
            if stop_requested:
                break
        if accum and not stop_requested:
            run_step(accum, epoch)

    if not best_dir.exists():
        # jamais évalué (jeu de validation vide ou entraînement trop court) : on garde le dernier état
        save_adapter(model, best_dir)

    finish(args, model, tokenizer, out_dir)
    write_status(status_path, state="stopped" if stop_requested else "done", step=global_step,
                 best_val_loss=None if math.isinf(best_val) else best_val)


def auto_int(value: str):
    return value if value == "auto" else int(value)


def parse_args(argv=None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Entraînement LoRA commun à toutes les machines steph.")
    ap.add_argument("--model", required=True, help="id Hugging Face ou dossier du modèle de base")
    ap.add_argument("--train", type=Path, required=True)
    ap.add_argument("--val", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--rank", type=int, default=16)
    ap.add_argument("--alpha", type=int, default=32)
    ap.add_argument("--dropout", type=float, default=0.05)
    ap.add_argument("--lr", type=float, default=2e-4)
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--max-len", dest="max_len", type=int, default=1536)
    ap.add_argument("--batch", type=auto_int, default="auto")
    ap.add_argument("--grad-accum", dest="grad_accum", type=auto_int, default="auto")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--resume-from", dest="resume_from", type=Path, default=None,
                     help="adaptateur existant à continuer")
    ap.add_argument("--device", choices=["auto", "cuda", "cpu"], default="auto")
    ap.add_argument("--bf16", choices=["auto", "true", "false"], default="auto")
    ap.add_argument("--eval-every", dest="eval_every", type=int, default=None,
                     help="pas entre deux évaluations (défaut : 10 fois par epoch)")
    ap.add_argument("--patience", type=int, default=3)
    ap.add_argument("--merge", action="store_true", help="fusionner l'adaptateur dans le modèle de base à la fin")
    return ap.parse_args(argv)


def main(argv=None) -> None:
    args = parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    status_path = args.out / "status.json"
    try:
        run(args)
    except KeyboardInterrupt:
        write_status(status_path, state="stopped")
    except Exception as exc:
        write_status(status_path, state="error", error=str(exc))
        raise


if __name__ == "__main__":
    main()
