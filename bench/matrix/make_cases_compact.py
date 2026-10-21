"""Génère les variantes de compaction/plafond de P11 : cases_compact_<variante>.json.

    uv run python bench/matrix/make_cases_compact.py
    uv run python bench/matrix/make_cases_compact.py --system train

Cinq variantes, mêmes 33 fixtures + 3 qa que cases.json (36 cas) :
- baseline_current : digest()/compact_output() actuels, maxc=1500 - référence, sans
               plafond de jetons.
- compact    : digest()/compact_output() avec la compaction sans perte (dedupe_lines,
               strip_noise, compact_table), maxc=1500 inchangé - isole l'effet de la
               compaction seule, à budget égal à l'existant.
- granite200 : compact + plafond ~200 jetons d'entrée sur Granite.
- granite300 : compact + plafond ~300 jetons d'entrée sur Granite.
- gemma350   : compact + plafond ~350 jetons d'entrée sur Gemma.

--system : prod (défaut, inchangé) envoie SUMMARY_SYSTEM (src/steph/prompts.py, le
prompt de production) ; train envoie TRAIN_SYSTEM (bench/matrix/finetune/label.py:32,
le protocole d'entraînement) - seul le prompt système change, jamais le message
utilisateur ni les cas QA (déjà sur QA_SYSTEM, indépendant du protocole affiné). Avec
train, les fichiers sortent en cases_compact_<variante>_train.json : les fichiers prod
existants ne sont jamais écrasés.

Le plafond en jetons se traduit en budget de caractères (chars_budget) par une régression
linéaire mesurée sur les résultats i5 déjà dans le dépôt : prompt_n réel de llama-server
(cache_prompt actif -> ce sont les jetons NEUFS après le préfixe système commun, pas le
total) contre la longueur du message utilisateur, sur les 36 cas de cases.json.
  granite (i5-soup-granite-uniform-Q4_K_M.json) : tokens ~= 32,07 + chars / 3,497
  gemma   (i5-judged-gemma-270m-s42-Q8_0.json)   : tokens ~= 118,33 + chars / 2,883
Seulement une estimation pour fabriquer les cas ; la vérité vient du banc GPU relancé sur
chaque variante (prompt_n réel rapporté dans le résultat).
"""

import argparse
import json
import sys
from pathlib import Path

from steph.digest import digest
from steph.prompts import QA_SYSTEM, summary_messages
from steph.textproc import compact_output

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "bench/matrix/finetune"))
from label import TRAIN_SYSTEM  # noqa: E402

QUESTIONS = ["Pourquoi le build a planté ?", "Il me reste combien de place sur le disque ?",
             "Quelle version de Python est installée ?"]

CALIBRATION = {"granite": (3.497, 32.07), "gemma": (2.883, 118.33)}


def chars_budget(model: str, max_tokens: int) -> int:
    chars_per_token, offset = CALIBRATION[model]
    return max(200, round((max_tokens - offset) * chars_per_token))


VARIANTS = {
    "baseline_current": 1500,
    "compact": 1500,
    "granite200": chars_budget("granite", 200),
    "granite300": chars_budget("granite", 300),
    "gemma350": chars_budget("gemma", 350),
}


def case_messages(cmd: str, exit_code: int | None, duration: float, out_text: str, nlines: int,
                  system: str = "prod") -> list[dict]:
    """SUMMARY_SYSTEM (prod, défaut) ou TRAIN_SYSTEM (train) ; message utilisateur inchangé."""
    msgs = summary_messages(cmd, exit_code, duration, out_text, nlines)
    if system == "train":
        msgs[0] = {"role": "system", "content": TRAIN_SYSTEM}
    return msgs


def load_fixtures() -> list[dict]:
    fx = json.load(open(ROOT / "bench/fixtures.json")) + json.load(open(ROOT / "bench/extra_fixtures.json"))
    for extra, cmd in (("df_proxmox.txt", "df -h"), ("ip_a_proxmox.txt", "ip a")):
        fx.append({"cmd": cmd, "exit": 0, "duration": 0.1, "output": (ROOT / "tests/data" / extra).read_text(),
                   "id": extra[:-4]})
    return fx


def qa_cases() -> list[dict]:
    """Historique construit une fois, comme dans make_cases.py : ne dépend pas du budget
    de la variante, seulement de la compaction (déjà active via digest() par défaut)."""
    hist = ("Commande : npm run build\nStatut : échec (code 1)\nSortie :\nsrc/components/Header.tsx:42:17 - error "
            "TS2339: Property 'titel' does not exist on type 'Props'. Did you mean 'title'?\n\n"
            "Commande : df -h\nStatut : succès\nSortie :\n"
            + digest("df -h", (ROOT / "tests/data/df_proxmox.txt").read_text()))
    return [{"id": f"qa{j}", "fixture": f"qa{j}", "cmd": q, "kind": "qa", "maxc": 0,
             "messages": [{"role": "system", "content": QA_SYSTEM},
                          {"role": "user", "content": f"Historique :\n{hist}\n\nQuestion : {q}"}]}
            for j, q in enumerate(QUESTIONS)]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--system", default="prod", choices=["prod", "train"],
                    help="prod (défaut) = SUMMARY_SYSTEM ; train = TRAIN_SYSTEM (label.py:32)")
    a = ap.parse_args()

    fx = load_fixtures()
    qa = qa_cases()
    for variant, mc in VARIANTS.items():
        cases = []
        for i, f in enumerate(fx):
            cid = f.get("id") or f"fx{i:02d}"
            lines = f["output"].splitlines()
            out_text = digest(f["cmd"], f["output"], mc) or compact_output(lines, mc)
            cases.append({"id": cid, "fixture": cid, "cmd": f["cmd"], "kind": "summary", "maxc": mc,
                          "messages": case_messages(f["cmd"], f["exit"], f["duration"], out_text, len(lines),
                                                    a.system)})
        cases += qa
        suffix = "_train" if a.system == "train" else ""
        path = ROOT / f"bench/matrix/cases_compact_{variant}{suffix}.json"
        json.dump(cases, open(path, "w"), ensure_ascii=False, indent=0)
        print(f"{variant}: {len(cases)} cas (maxc={mc}, system={a.system}) -> {path}")


if __name__ == "__main__":
    main()
