#!/usr/bin/env python3
"""G5e : mélange de G5d dont les étiquettes T9 de mauvaise langue reprennent l'étiquette X4-L5 (celle d'a-sft), puis
corrections T9 sous prompt anglais (hors étiquette française) triplées pour revenir à la part de prompts EN d'a-sft (36,3 %).

    PYTHONPATH=<round-3/r3t2p3> python3 g5e_mix.py <mix-g5d/> <final-x4-l5/> <mix-extra-r1/> <out/>   -> JSON de comptes

Langue du prompt : celle du message système (lang_v3, toujours nette sur ce mélange). Une ligne T9 change si son étiquette
est nettement dans l'autre langue (lang_v3 non indécis), si X4-L5 porte la même entrée sous le même message système, et si
l'étiquette X4-L5 n'est pas, elle aussi, dans l'autre langue. Les indécis restent. Les lignes du mix-extra de R1 et du
correctif de langue ne sont pas des lignes T9 : elles ne changent pas. Toute autre ligne garde son texte et son ordre.

SPDX-License-Identifier: MIT
"""

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

from lang_v3 import classify

EN_CORR_COPIES = 3  # x3 : 36,8 % de prompts EN ; x2 donnerait 35,2 % (a-sft 36,3 %)


def load(p):
    return Path(p).read_text(encoding="utf-8").splitlines()


def key(row):
    m = row["messages"]
    return m[0]["content"], next(c["content"] for c in m if c["role"] == "user")


def sha(lines):
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


def x4_labels(d):
    out = {}
    for f in sorted(Path(d).glob("*.jsonl")):
        for line in load(f):
            r = json.loads(line)
            out.setdefault(key(r), []).append(r["messages"][-1]["content"])
    return out


def relabel(lines, x4, extra, stats, tag):
    out, changed = [], []
    for i, line in enumerate(lines):
        r = json.loads(line)
        src = r["source"]
        if line in extra or src == "langfix_en_fr":
            out.append(line)
            continue
        plang = classify(r["messages"][0]["content"])
        llang = classify(r["messages"][-1]["content"])
        if llang is None or llang == plang:
            out.append(line)
            continue
        cands = x4.get(key(r))
        if not cands:
            stats[f"{tag}_wrong_no_x4"][src] += 1
            out.append(line)
            continue
        good = [c for c in cands if classify(c) != llang]
        if not good:
            stats[f"{tag}_wrong_x4_also_wrong"][src] += 1
            out.append(line)
            continue
        new = good[0]
        if len(set(good)) > 1:
            stats[f"{tag}_x4_ambiguous_first_taken"][src] += 1
        r["messages"][-1]["content"] = new
        out.append(json.dumps(r, ensure_ascii=False))
        changed.append(i)
        stats[f"{tag}_replaced"][f"{src}:{plang}"] += 1
    return out, changed


def en_share(lines):
    langs = [classify(json.loads(l)["messages"][0]["content"]) for l in lines]
    return round(100 * langs.count("en") / len(langs), 2)


def wrong_pairs(lines):
    c = Counter()
    for line in lines:
        m = json.loads(line)["messages"]
        p, lab = classify(m[0]["content"]), classify(m[-1]["content"])
        if lab is not None and lab != p:
            c[f"prompt_{p}_label_{lab}"] += 1
    return dict(c)


def main():
    src, x4d, extrad, outd = sys.argv[1:5]
    x4 = x4_labels(x4d)
    extra = set(load(Path(extrad) / "train.jsonl")) | set(load(Path(extrad) / "val.jsonl"))
    stats = {k: Counter() for k in ("train_wrong_no_x4", "train_wrong_x4_also_wrong", "train_x4_ambiguous_first_taken",
                                     "train_replaced", "val_wrong_no_x4", "val_wrong_x4_also_wrong",
                                     "val_x4_ambiguous_first_taken", "val_replaced")}
    report = {}
    Path(outd).mkdir(parents=True, exist_ok=True)
    for split in ("train", "val"):
        rows = load(Path(src) / f"{split}.jsonl")
        new, changed = relabel(rows, x4, extra, stats, split)
        keep = lambda ls: [l for i, l in enumerate(ls) if i not in set(changed)]  # noqa: E731
        assert len(new) == len(rows) and keep(new) == keep(rows)
        added = []
        if split == "train":
            # une correction EN restée à étiquette FR (sans X4-L5 dans la bonne langue) n'est pas dupliquée
            corr_en = [l for l in new if json.loads(l)["source"].startswith("t9-corr")
                       and classify(json.loads(l)["messages"][0]["content"]) == "en"
                       and classify(json.loads(l)["messages"][-1]["content"]) != "fr"]
            added = corr_en * (EN_CORR_COPIES - 1)
        final = new + added
        assert final[:len(new)] == new
        Path(outd, f"{split}.jsonl").write_text("\n".join(final) + "\n", encoding="utf-8")
        report[split] = {"rows_in": len(rows), "rows_out": len(final), "relabeled": len(changed), "added_en_corrections": len(added),
                         "other_rows": len(keep(rows)), "other_sha_in": sha(keep(rows)), "other_sha_out": sha(keep(new)),
                         "en_prompt_pct_in": en_share(rows), "en_prompt_pct_out": en_share(final),
                         "wrong_lang_labels_in": wrong_pairs(rows), "wrong_lang_labels_out": wrong_pairs(final)}
    report["detail"] = {k: dict(v) for k, v in stats.items()}
    report["en_corrections_copies"] = EN_CORR_COPIES
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
