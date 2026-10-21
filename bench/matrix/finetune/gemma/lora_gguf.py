#!/usr/bin/env python3
"""One peft adapter equal to the soup of SFT adapters plus the DPO adapter, keyed for
convert_lora_to_gguf.py, so llama.cpp can apply it at runtime over the official QAT Q4_0 GGUF.

    python3 lora_gguf.py --adapters s42 s7 s123 s2024 [--add dpo/adapter] --out soup_adapter
    python3 llama.cpp/convert_lora_to_gguf.py --base <gemma-4-E2B-it-qat-q4_0-unquantized> --outtype f16 soup_adapter

Exact, not an approximation: the mean of n rank-r products is the product of the concatenated
factors, B scaled by 1/n (rank n*r). Scales are folded into B and lora_alpha = r, so the scale is 1.

SPDX-License-Identifier: MIT
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gemma_lib import ADAPTER_PREFIX, TEXT_PREFIX  # noqa: E402


def combine(soup: list[str], add: list[str]) -> tuple[dict, int]:
    """Concatenated (A, B) per target, keys as in the full checkpoint, and the total rank."""
    import torch
    from safetensors.torch import load_file

    parts: dict[str, list] = {}
    weighted = [(f, 1.0 / len(soup)) for f in soup] + [(f, 1.0) for f in add]
    for folder, weight in weighted:
        cfg = json.load(open(Path(folder) / "adapter_config.json"))
        assert not cfg.get("use_rslora") and not cfg.get("use_dora") and not cfg.get("fan_in_fan_out")
        scale = cfg["lora_alpha"] / cfg["r"] * weight
        sd = load_file(str(Path(folder) / "adapter_model.safetensors"))
        for k in sd:
            if k.endswith(".lora_A.weight"):
                name = k[len(ADAPTER_PREFIX):].replace(".lora_A.weight", "")
                b = sd[k.replace("lora_A", "lora_B")].float() * scale
                parts.setdefault(name, []).append((sd[k].float(), b))
    ranks = {sum(a.shape[0] for a, _ in v) for v in parts.values()}
    assert len(ranks) == 1, f"rangs différents selon les cibles : {ranks}"
    out = {name: (torch.cat([a for a, _ in v], 0), torch.cat([b for _, b in v], 1)) for name, v in parts.items()}
    return out, ranks.pop()


def main() -> None:
    from safetensors.torch import save_file

    ap = argparse.ArgumentParser()
    ap.add_argument("--adapters", nargs="+", required=True)
    ap.add_argument("--add", nargs="*", default=[])
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    factors, rank = combine(a.adapters, a.add)
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    tensors = {}
    for name, (lora_a, lora_b) in factors.items():
        key = ADAPTER_PREFIX + TEXT_PREFIX + name
        tensors[key + ".lora_A.weight"] = lora_a.contiguous()
        tensors[key + ".lora_B.weight"] = lora_b.contiguous()
    save_file(tensors, str(out / "adapter_model.safetensors"))
    targets = sorted({n.rsplit(".", 1)[-1] for n in factors})
    json.dump({"peft_type": "LORA", "r": rank, "lora_alpha": rank, "target_modules": targets, "bias": "none",
               "fan_in_fan_out": False, "use_rslora": False, "use_dora": False, "task_type": "CAUSAL_LM"},
              open(out / "adapter_config.json", "w"), indent=1)
    print(f"{len(factors)} cibles, rang {rank} -> {out}", flush=True)


if __name__ == "__main__":
    main()
