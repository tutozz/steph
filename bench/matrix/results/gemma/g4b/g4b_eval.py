#!/usr/bin/env python3
"""G4b : G3b Q4_0 contre G3b off-ple3 (PLE en Q3_K), banc v3 test aligné L5, 3 graines.

    PYTHONPATH=<v3/tools>:<round-3/r3t2p3>:<finetune>:<g3b> python3 g4b_eval.py <runs/> <verdicts/> <vide/> <harness/> <out.json>

Réutilise g3b_eval.py (mêmes statistiques : power_v3, score_production, lang_v3), avec deux modèles.

SPDX-License-Identifier: MIT
"""

import g3b_eval

g3b_eval.MODELS = ("g3b-q4", "g3b-ple3")
g3b_eval.PAIRS = (("g3b-ple3", "g3b-q4"),)
g3b_eval.HARNESS = {"g3b-q4": "test.generic.json", "g3b-ple3": "test.generic.json"}

if __name__ == "__main__":
    g3b_eval.main()
