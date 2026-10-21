"""Lit journal.tsv et affiche le meilleur essai par categorie de levier (tune uniquement)."""
import csv
from pathlib import Path

J = Path("bench/matrix/results/quality/entree/journal.tsv")

rows = list(csv.DictReader(open(J), delimiter="\t"))
for r in rows:
    print(f"{r['essai']:>3} {r['modele']:<8} {r['variante']:<55} tune={r['tune']:<6} holdout={r['holdout']}")
