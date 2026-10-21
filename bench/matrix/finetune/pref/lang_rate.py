#!/usr/bin/env python3
"""Taux de bonne langue des réponses d'un résultat Steph Speak Bench (méthode L2p, docs/l2p-multilingual.md).

    python3 lang_rate.py <résultat run.py> [...]

Profils de trigrammes de caractères par langue, appris sur les réponses de référence du banc
(data/v1/<langue>/{dev,test}.jsonl), comparés par cosinus ; le cyrillique est classé russe
directement. Borne basse : le vocabulaire technique anglais tire les réponses vers « en ».
Imprime, par fichier, la langue attendue, le nombre de réponses non vides et le % bien classé.

SPDX-License-Identifier: MIT
"""

import collections
import json
import math
import re
import sys
from pathlib import Path

DATA = Path(__file__).resolve().parents[4] / "benchmark/data/v1"
LANGS = ("en", "fr", "de", "es", "pt", "ru")


def trigrams(text: str) -> collections.Counter:
    text = " " + re.sub(r"[^\w]+", " ", text.lower()).strip() + " "
    return collections.Counter(text[i:i + 3] for i in range(len(text) - 2))


def profiles(data: Path = DATA) -> dict[str, collections.Counter]:
    out = {}
    for lang in LANGS:
        counts = collections.Counter()
        for split in ("dev", "test"):
            for line in (data / lang / f"{split}.jsonl").read_text(encoding="utf-8").splitlines():
                if line.strip():
                    counts.update(trigrams(json.loads(line)["reference"]))
        out[lang] = counts
    return out


def cosine(a: collections.Counter, b: collections.Counter) -> float:
    dot = sum(v * b.get(k, 0) for k, v in a.items())
    na, nb = math.sqrt(sum(v * v for v in a.values())), math.sqrt(sum(v * v for v in b.values()))
    return dot / (na * nb) if na and nb else 0.0


def classify(text: str, profs: dict[str, collections.Counter]) -> str:
    letters = [c for c in text if c.isalpha()]
    if letters and sum("Ѐ" <= c <= "ӿ" for c in letters) > len(letters) / 2:
        return "ru"
    grams = trigrams(text)
    return max(LANGS, key=lambda lang: cosine(grams, profs[lang]))


def main() -> None:
    profs = profiles()
    out = {}
    for path in sys.argv[1:]:
        res = json.load(open(path))
        answers = [r["answer"] for r in res["rows"] if (r.get("answer") or "").strip()]
        right = sum(classify(a, profs) == res["lang"] for a in answers)
        out[Path(path).name] = {"lang": res["lang"], "n": len(answers), "right_lang_pct": round(100 * right / len(answers), 1)}
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
