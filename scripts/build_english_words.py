"""Génère src/steph/data/english_words.txt.gz : mots que steph prononce à l'anglaise.

Outil de développement, lancé à la main quand on veut régénérer la liste :
    uv run --with wordfreq python scripts/build_english_words.py Lexique383.tsv

Lexique383.tsv vient de http://www.lexique.org/databases/Lexique383/Lexique383.zip.
Un mot aussi français (rate, file, sort) est préfixé de « ~ » : steph ne le dit à
l'anglaise que dans un contexte technique.

Données : wordfreq (Robyn Speer) et Lexique 3.83 (New et Pallier), licence CC BY-SA 4.0.
Voir NOTICE.
"""

import csv
import gzip
import sys
from pathlib import Path

from wordfreq import iter_wordlist, zipf_frequency

MIN_EN = 1.3  # zipf : garde les commandes (grep, awk, mkdir), rares même en anglais
MIN_GAP = 0.15  # plus courant en anglais qu'en français
MAX_FR = 4.5  # au-delà, c'est un mot français courant (a, on, est, table)
MIN_LEN = 3
FRENCH_WORD = 5.0  # occurrences par million (livres + films) : au-delà, vrai mot français

OUT = Path(__file__).resolve().parent.parent / "src" / "steph" / "data" / "english_words.txt.gz"


def french_frequencies(lexique: str) -> dict[str, float]:
    freq: dict[str, float] = {}
    with open(lexique, encoding="utf-8") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            w = row["ortho"].lower()
            n = float(row["freqlivres"] or 0) + float(row["freqfilms2"] or 0)
            freq[w] = max(freq.get(w, 0.0), n)
    return freq


def main() -> None:
    french = french_frequencies(sys.argv[1])
    words = []
    for w in iter_wordlist("en", wordlist="large"):
        en = zipf_frequency(w, "en")
        if en < MIN_EN:
            break
        if len(w) < MIN_LEN or not (w.isascii() and w.isalpha()):
            continue
        fr = zipf_frequency(w, "fr")
        if en - fr >= MIN_GAP and fr < MAX_FR:
            words.append("~" + w if french.get(w, 0.0) >= FRENCH_WORD else w)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(gzip.compress("\n".join(sorted(words)).encode(), 9, mtime=0))
    ambiguous = sum(w.startswith("~") for w in words)
    print(f"{len(words)} mots dont {ambiguous} aussi français, {OUT.stat().st_size // 1024} Ko : {OUT}")


if __name__ == "__main__":
    main()
