"""Score de qualité d'un résultat de banc : faits attendus présents, interdits absents, longueur.

    python bench/matrix/score.py results/*.json      -> une ligne par fichier

Par cas : 1 point par fait attendu présent, 0 si un interdit apparaît, puis ×0,8 si la
réponse dépasse la longueur permise. Score d'une configuration : moyenne des cas, en %.
"""

import json
import re
import sys
import unicodedata
from pathlib import Path

FACTS = json.load(open(Path(__file__).with_name("facts.json")))


def plain(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in text if not unicodedata.combining(c)).replace("’", "'")


def clean(out: str, points: bool = False) -> str:
    """Ce que steph dirait après nettoyage : sans raisonnement, sans code, sans écho, une ligne.

    points : le détail s'écrit un point par ligne ; joindre sans ponctuation en faisait une suite
    de mots-clés (X4a). Une ligne déjà ponctuée garde sa ponctuation.
    """
    out = re.sub(r"<think>.*?</think>", "", out, flags=re.S)
    out = re.sub(r"</?think>", "", out)
    out = re.sub(r"```\w*", "", out)
    lines = [l.strip(" \"'«»") for l in out.splitlines()
             if l.strip() and not re.match(r"(Commande|Statut|Durée|Sortie|Historique|Question)\s*:", l.strip())]
    if points:
        lines = [l if re.search(r"[.!?:;,]$", l) else l + "." for l in lines[:-1]] + lines[-1:]
    return " ".join(lines)


def score_case(fixture: str, kind: str, out: str) -> float:
    facts = FACTS.get(fixture)
    if not facts:
        return float("nan")
    text = plain(out)
    if any(re.search(p, text) for p in FACTS["_global_never"] + facts.get("never", [])):
        return 0.0
    need = facts["need"]
    s = sum(bool(re.search(p, text)) for p in need) / len(need)
    if len(out.split()) > FACTS["_max_words"][kind]:
        s *= 0.8
    return s


# Jeu de contrôle : jamais utilisé pour choisir un réglage, seulement pour vérifier à la fin.
HOLDOUT = {"fx21", "fx22", "fx23", "fx24", "fx25", "fx26", "fx27", "fx28", "fx29", "fx30",
           "df_proxmox", "ip_a_proxmox", "qa0", "qa1", "qa2"}


def score_result(path: str, cleaned: bool = False, split: str = "all") -> dict:
    r = json.load(open(path))
    rows = [row for row in r.get("rows", []) if row.get("out") is not None]
    if split == "tune":
        rows = [row for row in rows if row["fixture"] not in HOLDOUT]
    elif split == "holdout":
        rows = [row for row in rows if row["fixture"] in HOLDOUT]
    scores = [score_case(row["fixture"], row["kind"], clean(row["out"]) if cleaned else row["out"]) for row in rows]
    scores = [s for s in scores if s == s]
    return {"label": r.get("label"), "quality": round(100 * sum(scores) / len(scores), 1) if scores else None,
            "n": len(scores)}


if __name__ == "__main__":
    for p in sys.argv[1:]:
        raw, net = score_result(p), score_result(p, cleaned=True)
        tune, hold = score_result(p, True, "tune"), score_result(p, True, "holdout")
        print(json.dumps({**raw, "quality_cleaned": net["quality"], "tune": tune["quality"],
                          "holdout": hold["quality"]}, ensure_ascii=False))
