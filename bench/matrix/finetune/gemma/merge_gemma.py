#!/usr/bin/env python3
"""Full Gemma 4 E2B checkpoint with the uniform soup of LoRA adapters merged in, for llama.cpp.

    python3 merge_gemma.py --model <gemma-4-E2B-it-qat-q4_0-unquantized> --adapters a1 a2 ... [--add dpo/adapter] --out merged_dir

--adapters are averaged (SFT soup); each --add adapter is added at full weight on top (DPO trained
over that soup by train_dpo_gemma.py).

CPU only, bf16. Audio and vision towers are kept untouched, so convert_hf_to_gguf.py sees the
same Gemma4ForConditionalGeneration checkpoint as the original and writes the text model only.

SPDX-License-Identifier: MIT
"""

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gemma_lib import adapter_deltas  # noqa: E402

import torch
from transformers import Gemma4ForConditionalGeneration

ap = argparse.ArgumentParser()
ap.add_argument("--model", required=True)
ap.add_argument("--adapters", nargs="+", required=True)
ap.add_argument("--add", nargs="*", default=[])
ap.add_argument("--out", required=True)
a = ap.parse_args()

deltas = adapter_deltas(a.adapters)
for folder in a.add:
    for name, d in adapter_deltas([folder]).items():
        deltas[name] = deltas.get(name, 0) + d
full = Gemma4ForConditionalGeneration.from_pretrained(a.model, dtype=torch.bfloat16, device_map="cpu")
params = dict(full.named_parameters())
missing = [n for n in deltas if n not in params]
assert not missing, f"clés absentes du modèle : {missing[:3]}"
with torch.no_grad():
    for name, d in deltas.items():
        params[name].copy_((params[name].float() + d).to(torch.bfloat16))
full.save_pretrained(a.out)
for f in ("tokenizer.json", "tokenizer_config.json", "chat_template.jinja", "processor_config.json", "generation_config.json"):
    if (Path(a.model) / f).exists():
        shutil.copy(Path(a.model) / f, Path(a.out) / f)
print(f"{len(deltas)} matrices fusionnées ({len(a.adapters)} en soupe, {len(a.add)} ajoutés) -> {a.out}", flush=True)
