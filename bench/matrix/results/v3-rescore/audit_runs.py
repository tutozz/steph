#!/usr/bin/env python3
"""X3 : règles d'audit_pii (scan_text, liste privée de noms comprise) sur chaque sortie brute de
bench_run et chaque phrase jugée, avant commit.

    python3 audit_runs.py <fichier.json> [...]     code 0 si aucune trouvaille non relue

Une trouvaille relue à la main et reconnue fausse (sortie qui recopie une empreinte du banc public,
adresse MAC de remplissage, « exemple.com »...) est listée dans reviewed.json, clé « <id>|<type>|<sha1 de la sortie, 12> »
(une autre sortie sur le même cas repasse en revue), avec sa raison ; seules les autres font échouer l'audit. N'imprime jamais une valeur trouvée.

SPDX-License-Identifier: MIT
"""

import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "finetune"))
import audit_pii  # noqa: E402


def main():
    names = audit_pii.load_names(audit_pii.DEFAULT_NAMES)
    reviewed = json.load(open(HERE / "reviewed.json"))
    new, known = [], 0
    for p in sys.argv[1:]:
        d = json.load(open(p))
        rows = d["rows"] if isinstance(d, dict) else d
        for r in rows:
            text = r.get("out") or r.get("phrase") or ""
            for t in set(audit_pii.scan_text(text, names)):
                key = f"{r['id']}|{t}|{hashlib.sha1(text.encode()).hexdigest()[:12]}"
                if key in reviewed:
                    known += 1
                else:
                    new.append((Path(p).name, key))
    for f, key in sorted(set(new)):
        print(f"{f}: {key}")
    print(f"{len(new)} trouvailles non relues, {known} relues (reviewed.json)")
    return 1 if new else 0


if __name__ == "__main__":
    raise SystemExit(main())
