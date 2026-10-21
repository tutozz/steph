"""Génère bench/matrix/cases.json : les messages exacts que steph envoie au modèle.

    uv run python bench/matrix/make_cases.py

Tri (digest) et compaction de steph appliqués ici, sur le Mac : les machines de test
n'ont besoin que de llama-server et de bench_run.py.
"""

import json
from pathlib import Path

from steph.digest import digest
from steph.prompts import QA_SYSTEM, summary_messages
from steph.textproc import compact_output

ROOT = Path(__file__).resolve().parents[2]
QUESTIONS = ["Pourquoi le build a planté ?", "Il me reste combien de place sur le disque ?",
             "Quelle version de Python est installée ?"]


def main() -> None:
    fx = json.load(open(ROOT / "bench/fixtures.json")) + json.load(open(ROOT / "bench/extra_fixtures.json"))
    for extra, cmd in (("df_proxmox.txt", "df -h"), ("ip_a_proxmox.txt", "ip a")):
        fx.append({"cmd": cmd, "exit": 0, "duration": 0.1, "output": (ROOT / "tests/data" / extra).read_text(),
                   "id": extra[:-4]})
    cases = []
    for i, f in enumerate(fx):
        cid = f.get("id") or f"fx{i:02d}"
        lines = f["output"].splitlines()
        for maxc in (1500, 800):
            out = digest(f["cmd"], f["output"], maxc) or compact_output(lines, maxc)
            cases.append({"id": f"{cid}@{maxc}", "fixture": cid, "cmd": f["cmd"], "kind": "summary", "maxc": maxc,
                          "messages": summary_messages(f["cmd"], f["exit"], f["duration"], out, len(lines))})
    hist = ("Commande : npm run build\nStatut : échec (code 1)\nSortie :\nsrc/components/Header.tsx:42:17 - error "
            "TS2339: Property 'titel' does not exist on type 'Props'. Did you mean 'title'?\n\n"
            "Commande : df -h\nStatut : succès\nSortie :\n"
            + digest("df -h", (ROOT / "tests/data/df_proxmox.txt").read_text()))
    for j, q in enumerate(QUESTIONS):
        cases.append({"id": f"qa{j}", "fixture": f"qa{j}", "cmd": q, "kind": "qa", "maxc": 0,
                      "messages": [{"role": "system", "content": QA_SYSTEM},
                                   {"role": "user", "content": f"Historique :\n{hist}\n\nQuestion : {q}"}]})
    out = ROOT / "bench/matrix/cases.json"
    json.dump(cases, open(out, "w"), ensure_ascii=False, indent=0)
    print(f"{len(cases)} cas : {out}")


if __name__ == "__main__":
    main()
