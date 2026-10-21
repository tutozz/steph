"""Shared pieces of the Gemma 4 E2B training scripts (G3): text-only loading with the per-layer
embeddings (PLE) kept on the CPU, answer-only encoding, softcapped logits at target positions,
and the mapping between LoRA adapter keys and the full checkpoint.

Why the PLE table stays on the CPU: Gemma 4 E2B holds 5.1 B bf16 parameters, of which 2.35 B
are the per-layer embedding table (4.7 GB), read by a lookup only. The decoder layers and the
main embedding (tied to lm_head) take 4.5 GB, which fits the 3080 10 GB with LoRA and activations.

SPDX-License-Identifier: MIT
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

ATTN_MLP = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]
TEXT_PREFIX = "model.language_model."
ADAPTER_PREFIX = "base_model.model."


def render(tok, messages: list[dict], gen: bool) -> str:
    return tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=gen, enable_thinking=False)


def encode(tok, messages: list[dict], maxlen: int, answer: str | None = None) -> tuple[list[int], list[int]]:
    """Token ids and labels, loss on the answer only; a long prompt is cut on the left, never the answer.

    `answer` replaces the last assistant turn (DPO: chosen or rejected over the same prompt)."""
    prompt_msgs = messages[:-1] if answer is None else messages
    answer = messages[-1]["content"] if answer is None else answer
    prompt = render(tok, prompt_msgs, True)
    full = render(tok, prompt_msgs + [{"role": "assistant", "content": answer}], False)
    assert full.startswith(prompt), "chat template: the prompt is not a prefix of the full conversation"
    p_ids = tok(prompt, add_special_tokens=False)["input_ids"]
    c_ids = tok(full[len(prompt):].rstrip("\n"), add_special_tokens=False)["input_ids"]
    ids = (p_ids + c_ids)[-maxlen:]
    labels = ([-100] * len(p_ids) + c_ids)[-len(ids):]
    return ids, labels


def softcap(logits, cap: float | None):
    """Gemma final logit softcapping, as Gemma4ForCausalLM.forward applies it."""
    if not cap:
        return logits
    import torch
    return torch.tanh(logits / cap) * cap


def checkpoint_key(adapter_key: str) -> str:
    """LoRA A key of a peft adapter over Gemma4TextModel -> weight key of the full Gemma 4 checkpoint."""
    assert adapter_key.startswith(ADAPTER_PREFIX) and adapter_key.endswith(".lora_A.weight"), adapter_key
    return TEXT_PREFIX + adapter_key[len(ADAPTER_PREFIX):].replace(".lora_A.weight", ".weight")


def adapter_deltas(folders: list[str]) -> dict:
    """Uniform soup of LoRA adapters: mean of scale * B @ A per target weight, keyed like the checkpoint."""
    from safetensors.torch import load_file

    acc: dict = {}
    for folder in folders:
        cfg = json.load(open(Path(folder) / "adapter_config.json"))
        assert not cfg.get("use_rslora") and not cfg.get("use_dora") and not cfg.get("fan_in_fan_out")
        scale = cfg["lora_alpha"] / cfg["r"]
        sd = load_file(str(Path(folder) / "adapter_model.safetensors"))
        for k in sd:
            if k.endswith("lora_A.weight"):
                d = (sd[k.replace("lora_A", "lora_B")].float() @ sd[k].float()) * scale
                name = checkpoint_key(k)
                acc[name] = acc.get(name, 0) + d
    return {name: d / len(folders) for name, d in acc.items()}


class TextLM:
    """Gemma 4 text decoder on the GPU, PLE lookup on the CPU (or on the GPU with ple_cpu=False)."""

    def __init__(self, path: str, ple_cpu: bool = True, deltas: dict | None = None, attn: str = "sdpa",
                 device: str = "cuda"):
        import torch
        from transformers import AutoConfig, Gemma4ForConditionalGeneration

        cfg = AutoConfig.from_pretrained(path)
        full = Gemma4ForConditionalGeneration.from_pretrained(path, dtype=torch.bfloat16, device_map="cpu",
                                                              attn_implementation=attn)
        if deltas:
            params = dict(full.named_parameters())
            with torch.no_grad():
                for name, d in deltas.items():
                    params[name].add_(d.to(params[name].dtype))
        text = full.model.language_model
        del full.model.audio_tower, full.model.vision_tower
        self.cap = cfg.text_config.final_logit_softcapping
        self.device = device
        self.ple_cpu = ple_cpu and device != "cpu"
        self.ple = text.embed_tokens_per_layer
        if self.ple_cpu:
            text.embed_tokens_per_layer = None
        text.to(device)
        if self.ple_cpu:
            text.embed_tokens_per_layer = self.ple
        text.config.use_cache = False
        self.text = text
        self.n_layers, self.ple_dim = cfg.text_config.num_hidden_layers, cfg.text_config.hidden_size_per_layer_input

    def per_layer_inputs(self, ids):
        cpu_ids = ids.cpu() if self.ple_cpu else ids
        out = self.ple(cpu_ids).reshape(*ids.shape, self.n_layers, self.ple_dim)
        return out.to(ids.device, non_blocking=True)

    def hidden(self, model, ids, att):
        """Last hidden states; `model` is the text model or its peft wrapper."""
        embeds = self.text.embed_tokens(ids)
        if embeds.requires_grad is False and self.text.is_gradient_checkpointing:
            embeds.requires_grad_(True)
        return model(inputs_embeds=embeds, per_layer_inputs=self.per_layer_inputs(ids), attention_mask=att,
                     use_cache=False).last_hidden_state

    def target_logits(self, model, ids, lab, att):
        """Float32 softcapped logits at the answer positions only (262k vocabulary), and the targets."""
        import torch

        with torch.autocast(self.device, dtype=torch.bfloat16):
            hidden = self.hidden(model, ids, att)[:, :-1]
            tgt = lab[:, 1:]
            keep = tgt != -100
            logits = torch.nn.functional.linear(hidden[keep], self.text.embed_tokens.weight).float()
        return softcap(logits, self.cap), tgt, keep
