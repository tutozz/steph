"""Variantes de prompt pour petits modèles : génère cases_p1.json et cases_p2.json.

    uv run python bench/matrix/variants.py

P1 : prompt court, une seule règle choisie selon le type de commande, aucun exemple
(les petits modèles recopient les exemples du prompt système).
P2 : P1 plus deux exemples en vrais tours de dialogue, sur des commandes absentes du banc.
"""

import json
import re
from pathlib import Path

HERE = Path(__file__).parent

BASE = ("Tu résumes la sortie d'une commande pour une personne aveugle qui écoute. "
        "Réponds en une seule ligne de 15 mots maximum, en français, en mots-clés, sans phrase. "
        "N'écris que ce qui figure dans la sortie ; n'invente rien.")

RULES = {
    "echec": "La commande a échoué : commence par « Échec. », puis la cause, et le fichier et la ligne s'ils sont écrits.",
    "liste": "La sortie commence par un compte : répète exactement ce compte et les 3 noms qui le suivent.",
    "reseau": "Donne chaque interface avec son adresse IPv4, telles qu'écrites en tête de la sortie.",
    "disque": "Donne l'espace libre de chaque disque, tel qu'écrit dans la sortie.",
    "memoire": "Donne la mémoire totale et la mémoire disponible.",
    "materiel": "Donne le GPU, le contrôleur réseau et le chipset.",
    "succes": "Donne le résultat utile, avec les nombres en chiffres.",
}

SHOTS = [
    ("Commande : python3 app.py\nStatut : échec (code 1)\nDurée : 0.3 s ; 4 lignes affichées\nSortie :\n"
     "Traceback (most recent call last):\n  File \"app.py\", line 3, in <module>\n    import flask\n"
     "ModuleNotFoundError: No module named 'flask'",
     "Échec. app.py ligne 3 : module flask manquant."),
    ("Commande : wc -l ventes.csv\nStatut : succès (code 0)\nDurée : 0.0 s ; 1 lignes affichées\nSortie :\n1204 ventes.csv",
     "1204 lignes dans ventes.csv."),
]


def category(cmd: str, status: str, output: str) -> str:
    if "échec" in status:
        return "echec"
    prog = cmd.split("|")[0].split()[0].rsplit("/", 1)[-1] if cmd.strip() else ""
    if prog == "sudo" and len(cmd.split()) > 1:
        prog = cmd.split()[1]
    if prog in ("ip", "ifconfig"):
        return "reseau"
    if prog == "df":
        return "disque"
    if prog == "free":
        return "memoire"
    if prog == "lspci":
        return "materiel"
    if re.match(r"\d+ (éléments|conteneurs)", output):
        return "liste"
    return "succes"


def variant(case: dict, shots: bool) -> dict:
    user = case["messages"][1]["content"]
    if case["kind"] == "qa":
        return case
    status = re.search(r"Statut : (.*)", user).group(1)
    output = user.split("Sortie :\n", 1)[-1]
    system = BASE + " " + RULES[category(case["cmd"], status, output)]
    msgs = [{"role": "system", "content": system}]
    if shots:
        for u, a in SHOTS:
            msgs += [{"role": "user", "content": u}, {"role": "assistant", "content": a}]
    msgs.append({"role": "user", "content": user})
    return {**case, "messages": msgs}


def main() -> None:
    cases = json.load(open(HERE / "cases.json"))
    for name, shots in (("p1", False), ("p2", True)):
        out = [variant(c, shots) for c in cases]
        json.dump(out, open(HERE / f"cases_{name}.json", "w"), ensure_ascii=False, indent=0)
        print(name, len(out), "cas")


if __name__ == "__main__":
    main()
