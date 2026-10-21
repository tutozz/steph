#!/bin/bash
# G5d : mélange de G5c (mix-g5c, sha256 9ee83dd2… / b1d7ada3…) dont le correctif de langue de G3b (source langfix_en_fr,
# 125 lignes x2) est remplacé, à la même place, par celui de G5 (/root/steph-ft/g5/langfix, x2) : c'est la recette du
# mélange d'a-sft. Contamination par ligne (leak_check drop) du correctif, audit_pii et scan du mélange à 0 ; toute autre
# ligne doit rester identique et dans le même ordre. Sur l'hôte de la 3080 : le corpus n'en sort pas.
set -u
K=/root/steph-ft/g5d; R=$K/repo; F=$R/bench/matrix/finetune; V=$R/bench/matrix/v3; D=/root/steph-ft/data
SRC=$D/mix-g5c; OUT=$D/mix-g5d; LF=/root/steph-ft/g5/langfix/langfix.jsonl
SHA="9ee83dd2a9db89886cb90cf69728479a6fb8cbe302fd4a49c53b60faabd19b53 b1d7ada3836ab1db7a464e89188c6b97758f3cec9fbc38d2a6e324db4c8bb7aa"
note() { echo "$(date '+%d %H:%M') $*" >> $K/run.done; }
# liste de noms d'audit_pii copiée chmod 600 par l'appelant, effacée à la fin
trap 'shred -u $HOME/.config/steph/pii_names.tsv 2>/dev/null' EXIT
mkdir -p $K/logs $K/clean; cd $K
[ -f $OUT/train.jsonl ] && exit 0
[ "$(sha256sum $SRC/train.jsonl $SRC/val.jsonl | cut -d' ' -f1 | paste -sd' ')" = "$SHA" ] || { note "ARRÊT : mix-g5c différent"; exit 1; }
python3 $V/tools/leak_check.py prints $K/v3prints-head.json $V/cases/*.jsonl $V/cases/dev/*.jsonl $V/cases/test/*.jsonl > /dev/null
python3 $V/tools/leak_check.py drop $K/v3prints-head.json $LF $K/clean/langfix.jsonl > $K/logs/drop-langfix.log
note "SANS FUITE langfix G5 $(cut -c1-120 $K/logs/drop-langfix.log)"
mkdir -p $OUT
python3 - $SRC/train.jsonl $K/clean/langfix.jsonl $OUT/train.jsonl > $K/logs/swap.json <<'PY' || { note "ARRÊT : remplacement du correctif"; rm -rf $OUT; exit 1; }
import hashlib, json, sys
src, lf, out = sys.argv[1:4]
rows = open(src, encoding="utf-8").read().splitlines()
new = open(lf, encoding="utf-8").read().splitlines()
pos = [i for i, r in enumerate(rows) if json.loads(r)["source"] == "langfix_en_fr"]
assert pos == list(range(pos[0], pos[0] + len(pos))), "correctif G3b non contigu"
old = rows[pos[0]:pos[-1] + 1]
assert len(old) % 2 == 0 and old[:len(old) // 2] == old[len(old) // 2:], "correctif G3b pas en x2"
assert all(json.loads(r)["source"] == "langfix_en_fr" for r in new)
mixed = rows[:pos[0]] + new + new + rows[pos[-1] + 1:]
keep = lambda rs: [r for r in rs if json.loads(r)["source"] != "langfix_en_fr"]  # noqa: E731
h = lambda rs: hashlib.sha256("\n".join(rs).encode()).hexdigest()  # noqa: E731
assert keep(mixed) == keep(rows)
open(out, "w", encoding="utf-8").write("\n".join(mixed) + "\n")
print(json.dumps({"src": len(rows), "out": len(mixed), "removed_g3b": len(old), "added_g5": 2 * len(new), "at": pos[0],
                  "other_rows": len(keep(rows)), "other_sha_src": h(keep(rows)), "other_sha_out": h(keep(mixed))}))
PY
cp $SRC/val.jsonl $OUT/val.jsonl
note "REMPLACEMENT $(cat $K/logs/swap.json)"
python3 $F/audit_pii.py $OUT/train.jsonl $OUT/val.jsonl > $K/logs/pii-mix.log 2>&1 || { note "ARRÊT : audit_pii $(tail -1 $K/logs/pii-mix.log)"; rm -rf $OUT; exit 1; }
python3 $V/tools/leak_check.py scan $K/v3prints-head.json $K/logs/leak-mix.json $OUT/train.jsonl $OUT/val.jsonl > $K/logs/leak-mix.log 2>&1
grep -q '"rejected": \[\]' $K/logs/leak-mix.log || { note "ARRÊT : cas du banc dans le mix $(tail -1 $K/logs/leak-mix.log | cut -c1-120)"; rm -rf $OUT; exit 1; }
sha256sum $OUT/*.jsonl $LF $K/clean/langfix.jsonl > $K/logs/mix-sha.txt
note "MIX $(wc -l < $OUT/train.jsonl) / $(wc -l < $OUT/val.jsonl) ; audit_pii $(tail -1 $K/logs/pii-mix.log | cut -c1-60) ; fuite $(tail -1 $K/logs/leak-mix.log | cut -c1-80)"
