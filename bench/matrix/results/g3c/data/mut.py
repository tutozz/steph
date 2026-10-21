#!/usr/bin/env python3
"""Deterministic fault injection in a source file (run as hidden setup in the sandbox).

    mut.py OP FILE [N]
OPs: ret (N-th single-line return value replaced by a neutral value), cmp (N-th == or != flipped),
     syn (syntax error appended), off (N-th "+ 1" becomes "+ 2"), semi (N-th line ending in ";" loses it),
     unused (unused local variable in the first function body), brace (N-th closing brace line removed).
Exit 3 when nothing matched, so the generator can check its targets.
"""
import re, sys

op, path = sys.argv[1], sys.argv[2]
n = int(sys.argv[3]) if len(sys.argv) > 3 else 1
src = open(path, encoding="utf-8").read()
lines = src.split("\n")
ext = path.rsplit(".", 1)[-1]


def nth(pred):
    k = 0
    for i, l in enumerate(lines):
        if pred(l):
            k += 1
            if k == n:
                return i
    sys.exit(3)


if op == "ret":
    neutral = {"py": "None", "js": "undefined", "ts": "undefined", "go": None, "rs": None}.get(ext)
    i = nth(lambda l: re.match(r"^\s+return \S", l) and not l.rstrip().endswith(("(", "[", "{", "\\", ",")) and "return None" not in l)
    ind = re.match(r"^(\s*)", lines[i]).group(1)
    lines[i] = f"{ind}return {neutral}" + (";" if ext in ("js", "ts") else "")
elif op == "cmp":
    i = nth(lambda l: (" == " in l or " != " in l) and not l.strip().startswith(("#", "//", "*")))
    l = lines[i]
    lines[i] = l.replace(" == ", " != ", 1) if " == " in l else l.replace(" != ", " == ", 1)
elif op == "off":
    i = nth(lambda l: " + 1" in l and not l.strip().startswith(("#", "//")))
    lines[i] = lines[i].replace(" + 1", " + 2", 1)
elif op == "syn":
    lines.append({"py": "def fin_de_fichier(:\n    pass", "js": "function finDeFichier( {", "ts": "function finDeFichier( {",
                  "go": "func finDeFichier( {", "rs": "fn fin_de_fichier( {", "c": "static int fin_de_fichier( {"}[ext])
elif op == "semi":
    i = nth(lambda l: l.rstrip().endswith(";") and not l.strip().startswith(("//", "*", "#", "for")))
    lines[i] = lines[i].rstrip()[:-1]
elif op == "brace":
    i = nth(lambda l: l.strip() == "}")
    del lines[i]
elif op == "unused":
    pat = {"go": r"^func .*\{\s*$", "rs": r"^\s*(pub )?fn .*\{\s*$", "c": r"^[a-z].*\)\s*\{\s*$",
           "py": r"^\s*def .*:\s*$", "js": r"^\s*function .*\{\s*$", "ts": r"^\s*(export )?function .*\{\s*$"}[ext]
    i = nth(lambda l: re.match(pat, l))
    stmt = {"go": "totalTemp := 0", "rs": "let total_temp = 0;", "c": "int total_temp = 0;",
            "py": "total_temp = 0", "js": "const totalTemp = 0;", "ts": "const totalTemp = 0;"}[ext]
    j = i + 1
    while j < len(lines) and not lines[j].strip():
        j += 1
    ind = re.match(r"^(\s*)", lines[j]).group(1) if j < len(lines) else "    "
    lines.insert(i + 1, ind + stmt)
else:
    sys.exit(2)
open(path, "w", encoding="utf-8").write("\n".join(lines))
