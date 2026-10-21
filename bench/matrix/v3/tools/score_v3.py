#!/usr/bin/env python3
"""Quality score of bench v3 runs: facts per prompt language, same rule as rescore.score_case.

    python3 score_v3.py [--split dev|test|all] [--spoken] [--per-case] <run.json> [...]

A run is a bench_run.py result on a harness file from assemble.py: row id `<case id>@<fr|en>`.
Per answer: `clean()` of bench/matrix/score.py, then `plain()`; 0 if a global never
(facts.v2.json `_global_never`) or a case never of that language matches; otherwise the share
of `need` facts met; x0.8 beyond `max_words`. `--spoken` first prefixes the status that steph
says in code before a summary (P9), as score_compact.py does.

SPDX-License-Identifier: MIT
"""

import argparse
import json
import re
import sys
from pathlib import Path

V3 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V3.parent))
from score import clean, plain  # noqa: E402

GLOBAL_NEVER = json.load(open(V3.parent / "facts.v2.json"))["_global_never"]
STATUS_ECHO = re.compile(r"^\s*(Succès|Échec|Success|Failed)\b[.,:]?\s*")
CODE = re.compile(r"\(code (-?\d+)\)")
PREFIX = {"fr": ("Succès. ", "Échec, code {code}. "), "en": ("Success. ", "Failed, code {code}. ")}


SMALL = {
    "zero": 0, "un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "six": 6, "sept": 7, "huit": 8,
    "neuf": 9, "dix": 10, "onze": 11, "douze": 12, "treize": 13, "quatorze": 14, "quinze": 15, "seize": 16,
    "vingt": 20, "vingts": 20, "trente": 30, "quarante": 40, "cinquante": 50, "soixante": 60,
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
    "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
    "seventy": 70, "eighty": 80, "ninety": 90,
}
HUNDRED = {"cent", "cents", "hundred"}
THOUSAND = {"mille", "thousand"}
LONE_ARTICLES = {"un", "une", "one"}
NUMBER_TOKENS = re.compile(r"[a-z]+|\d+|[^a-z\d]+")
DECIMAL = re.compile(r"\b(\d+(?:[.,]\d+)*|un|une|one) (virgule|point) (\d+|un|une|one)\b")
PERCENT = re.compile(r"\b(\d+) (?:percent|pourcent)\b")


def _is_number_word(w):
    return w in SMALL or w in HUNDRED or w in THOUSAND


TENS_FR = {"vingt", "trente", "quarante", "cinquante", "soixante"}


def _joins(prev, connector, nxt):
    """« vingt et un », « soixante et onze », « one hundred and five »: never « cinq et un »."""
    if connector == "et":
        return prev in TENS_FR and nxt in ("un", "une", "onze")
    return connector == "and" and prev in HUNDRED | THOUSAND and _is_number_word(nxt)


def _value(words):
    total, current, prev = 0, 0, None
    for w in words:
        if w in THOUSAND:
            total, current = total + (current or 1) * 1000, 0
        elif w in HUNDRED:
            current = current - current % 100 + (current % 100 or 1) * 100
        elif w in ("vingt", "vingts") and prev == "quatre":
            current += 80 - 4
        else:
            current += SMALL[w]
        prev = w
    return total + current


def number_view(text):
    """Number words written out (FR, EN) turned into digits: « trente-six » -> « 36 ». A lone
    « un », « une » or « one » stays: it is mostly an article, and facts already spell it."""
    toks = NUMBER_TOKENS.findall(text.replace("pour cent", "pourcent"))
    out, i = [], 0
    while i < len(toks):
        if not _is_number_word(toks[i]):
            out.append(toks[i])
            i += 1
            continue
        words, j, end = [toks[i]], i + 1, i + 1
        while j + 1 < len(toks) and toks[j] in (" ", "-") and (
                _is_number_word(toks[j + 1]) or (j + 3 < len(toks) and toks[j + 2] in (" ", "-")
                                                  and _joins(words[-1], toks[j + 1], toks[j + 3]))):
            if toks[j + 1] in ("et", "and"):
                j += 2
            words.append(toks[j + 1])
            j += 2
            end = j
        if len(words) == 1 and words[0] in LONE_ARTICLES:
            out.append(words[0])
        elif len(words) > 1 and all(w in SMALL and SMALL[w] < 10 for w in words):
            out.append("".join(str(SMALL[w]) for w in words))  # digits read one by one: « trois huit neuf »
        else:
            out.append(str(_value(words)))
        i = end
    view, previous = "".join(out), None
    while view != previous:  # « 198 point 51 point 100 » : one dot per pass
        previous = view
        view = DECIMAL.sub(lambda m: f"{1 if m.group(1) in LONE_ARTICLES else m.group(1)}"
                                     f"{',' if m.group(2) == 'virgule' else '.'}"
                                     f"{1 if m.group(3) in LONE_ARTICLES else m.group(3)}", view)
    return PERCENT.sub(r"\1 %", view)


ABSENCE = re.compile(
    r"\b(?:absente?s?|absence|missing|lacks?|lacked|lacking|nowhere|not located|found no|(?:does|do|did) not have|doesn.t have"
    r"|(?:could not|couldn.t|cannot|can.t|unable to) (?:find|locate)|faute de trouver|not present|(?:could not|cannot|can.t) be located|(?:n.est|ne sont) pas presente?s?"
    r"|manquante?s?|manquent|manque|(?:n.(?:a|ont) )?pas ete trouvee?s?|ne (?:le |la |les )?trouve pas|impossible de trouver)\b")


def absence_view(text):
    """Absence said otherwise (« lacks », « est absente », « n'a pas été trouvé ») also reads as
    the canonical « introuvable » / « not found » that absence facts spell."""
    return ABSENCE.sub("introuvable / not found", text)


def any_match(patterns, text):
    return any(re.search(p, text) for p in patterns)


def score_answer(case, lang, out):
    text = plain(clean(out))
    numbers = number_view(text)
    views = (text, numbers, absence_view(numbers))
    facts = case["facts"]
    hit = lambda patterns: any(any_match(patterns, v) for v in views)  # noqa: E731
    if hit(GLOBAL_NEVER) or any(hit(f[lang]) for f in facts["never"]):
        return 0.0
    need = facts["need"]
    s = sum(hit(f[lang]) for f in need) / len(need)
    if len(clean(out).split()) > case["max_words"]:
        s *= 0.8
    return s


def spoken(out, user, lang):
    m = CODE.search(user)
    if not m:
        return out
    code = int(m.group(1))
    ok, failed = PREFIX[lang]
    return (ok if code == 0 else failed.format(code=code)) + STATUS_ECHO.sub("", out, count=1)


def parse_row_id(row_id):
    case_id, lang = row_id.rsplit("@", 1)
    return case_id, lang


def mean_pct(xs):
    return round(100 * sum(xs) / len(xs), 1) if xs else None


def score_file(cases, path, said=False, harness=None, only=None):
    rows = json.load(open(path))["rows"]
    per, missing = {}, 0
    for r in rows:
        case_id, lang = parse_row_id(r["id"])
        if case_id not in cases or (only is not None and r["id"] not in only):
            continue
        if r.get("out") is None:
            missing += 1
            continue
        out = r["out"]
        case = cases[case_id]
        if said and case["task"] == "summary" and harness:
            user = [m for m in harness[r["id"]]["messages"] if m["role"] == "user"][0]["content"]
            out = spoken(out, user, lang)
        per[r["id"]] = score_answer(case, lang, out)
    by_family = {}
    for rid, s in per.items():
        by_family.setdefault(cases[parse_row_id(rid)[0]]["family"], []).append(s)
    return {
        "label": json.load(open(path)).get("label"),
        "quality": mean_pct(list(per.values())),
        "fr": mean_pct([s for rid, s in per.items() if rid.endswith("@fr")]),
        "en": mean_pct([s for rid, s in per.items() if rid.endswith("@en")]),
        "summary": mean_pct([s for rid, s in per.items() if cases[parse_row_id(rid)[0]]["task"] == "summary"]),
        "qa": mean_pct([s for rid, s in per.items() if cases[parse_row_id(rid)[0]]["task"] == "qa"]),
        "by_family": {k: mean_pct(v) for k, v in sorted(by_family.items())},
        "n": len(per),
        "missing": missing,
        "per_case": per,
    }


def load_cases(split="all"):
    splits = ("dev", "test") if split == "all" else (split,)
    cases = {}
    for s in splits:
        for f in sorted((V3 / "cases" / s).glob("*.jsonl")):
            for line in open(f):
                if line.strip():
                    c = json.loads(line)
                    cases[c["id"]] = c
    return cases


def load_harness(split="all"):
    splits = ("dev", "test") if split == "all" else (split,)
    rows = {}
    for s in splits:
        p = V3 / "harness" / f"{s}.json"
        if p.exists():
            rows.update({c["id"]: c for c in json.load(open(p))})
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--split", default="all", choices=["dev", "test", "all"])
    ap.add_argument("--spoken", action="store_true")
    ap.add_argument("--reaches-model", action="store_true", help="only answers steph sends to the model")
    ap.add_argument("--per-case", action="store_true")
    a = ap.parse_args()
    cases, harness = load_cases(a.split), load_harness(a.split)
    only = {rid for rid, h in harness.items() if h.get("reaches_model", True)} if a.reaches_model else None
    for p in a.runs:
        res = score_file(cases, p, a.spoken, harness, only)
        if not a.per_case:
            del res["per_case"]
        print(json.dumps({"file": Path(p).name, **res}, ensure_ascii=False))


if __name__ == "__main__":
    main()
