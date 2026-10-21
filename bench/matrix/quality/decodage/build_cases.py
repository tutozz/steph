"""Génère les fichiers de cas de l'axe décodage à partir de cases_p1.json / cases_p2.json.

Ajoute un champ "payload" par cas : grammaire "Échec." pour les cas summary en échec,
grammaire ligne unique bornée pour les autres cas summary, rien pour les cas qa (sauf
variante --with-qa, pour vérifier que la grammaire ne casse pas les questions).

    python3 build_cases.py cases_p1.json cases_p1_grammar.json
    python3 build_cases.py cases_p1.json cases_p1_grammar_qa.json --with-qa
"""

import argparse
import json
from pathlib import Path

HERE = Path(__file__).parent
LINE140 = (HERE / "line140.gbnf").read_text()
LINE140_ECHEC = (HERE / "line140-echec.gbnf").read_text()


def is_echec(case: dict) -> bool:
    user = next((m["content"] for m in case["messages"] if m["role"] == "user"), "")
    return "échec" in user.lower() or "code 1" in user.lower()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--with-qa", action="store_true", help="applique aussi la grammaire ligne aux cas qa")
    a = ap.parse_args()

    cases = json.load(open(a.src))
    for c in cases:
        if c["kind"] == "qa":
            if a.with_qa:
                c["payload"] = {"grammar": LINE140}
            continue
        c["payload"] = {"grammar": LINE140_ECHEC if is_echec(c) else LINE140}

    Path(a.dst).write_text(json.dumps(cases, ensure_ascii=False, indent=1))
    print(f"{a.dst} : {len(cases)} cas, {'avec' if a.with_qa else 'sans'} grammaire sur les qa")


if __name__ == "__main__":
    main()
