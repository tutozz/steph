#!/usr/bin/env python3
"""R3-T3 : fusion hors ligne d'un adaptateur LoRA (entraîné en QLoRA) dans la base en bf16, sur CPU.

    python3 merge_lora.py --base <HF> --adapter <dossier adapter> --out <HF fusionné>

SPDX-License-Identifier: MIT
"""
import argparse

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

ap = argparse.ArgumentParser()
ap.add_argument("--base", required=True)
ap.add_argument("--adapter", required=True)
ap.add_argument("--out", required=True)
a = ap.parse_args()
model = AutoModelForCausalLM.from_pretrained(a.base, dtype=torch.bfloat16)
model = PeftModel.from_pretrained(model, a.adapter).merge_and_unload()
model.config.use_cache = True
model.save_pretrained(a.out)
AutoTokenizer.from_pretrained(a.base).save_pretrained(a.out)
print("fusion écrite", a.out)
