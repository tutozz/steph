#!/usr/bin/env python3
"""G4 : texte de calibration imatrix depuis les entrées publiques du banc v3 dev (profil generic), au gabarit Gemma 4.

    calib.py <dev.generic.json> <tokenizer dir> <out.txt>
"""
import json
import random
import sys

from transformers import AutoTokenizer

rows = json.load(open(sys.argv[1]))
tok = AutoTokenizer.from_pretrained(sys.argv[2])
random.Random(0).shuffle(rows)
with open(sys.argv[3], "w") as f:
    for r in rows:
        f.write(tok.apply_chat_template(r["messages"], tokenize=False, add_generation_prompt=True))
        f.write("\n")
print(len(rows), "prompts")
