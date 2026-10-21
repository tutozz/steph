"""Remove invented line numbers from teacher labels, deterministically.

    python3 fix_labels.py final/train.jsonl final/train.fixed.jsonl [--lang en]

The teacher copied the prompt example « fichier ligne 42 » (English: "file line 42") and wrote
« ligne N » / "line N" even when N is not a line number in the output (exit code, column,
nothing at all). Such a fragment is removed; the rest of the label is kept. Rows whose label
still cites a number absent from the output are dropped. `--lang en` switches the line marker
("line" instead of "ligne"), the output-section marker ("Output:" instead of "Sortie :") and
disables the French space-before-colon cleanup, which would otherwise misspell English labels.

SPDX-License-Identifier: MIT
"""

import json
import re
import sys

LINE_BY_LANG = {
    "fr": re.compile(r"\s*(?:,\s*)?ligne (\d+)"),
    "en": re.compile(r"\s*(?:,\s*)?line (\d+)"),
}
OUTPUT_MARKER_BY_LANG = {"fr": "Sortie :", "en": "Output:"}


def output_of(user: str, language: str = "fr") -> str:
    return user.split(OUTPUT_MARKER_BY_LANG[language], 1)[-1]


def grounded_line(n: str, output: str) -> bool:
    """True when n appears in the output as a line number (Python, gcc, tsc, grep -n styles)."""
    patterns = (rf"\bline {n}\b", rf"\bligne {n}\b", rf":{n}:", rf":{n}\b(?!\.\d)", rf"\({n},")
    return any(re.search(p, output) for p in patterns)


def fix_label(label: str, output: str, language: str = "fr") -> str:
    def drop(m: re.Match) -> str:
        return m.group(0) if grounded_line(m.group(1), output) else ""

    fixed = LINE_BY_LANG[language].sub(drop, label)
    fixed = re.sub(r"\s{2,}", " ", fixed)
    if language == "fr":
        fixed = re.sub(r"\s+:", " :", fixed)  # espace typographique français avant « : »
    return fixed.strip()


def invented_number(label: str, output: str) -> bool:
    return any(n not in output for n in re.findall(r"\d{2,}", label))


def main(src: str, dst: str, language: str = "fr") -> None:
    kept, fixed, dropped = [], 0, 0
    for line in open(src):
        row = json.loads(line)
        user, label = row["messages"][1]["content"], row["messages"][2]["content"]
        out = output_of(user, language)
        new = fix_label(label, out, language)
        if new != label:
            fixed += 1
        if not new or invented_number(new, out):
            dropped += 1
            continue
        row["messages"][2]["content"] = new
        kept.append(row)
    with open(dst, "w") as f:
        f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in kept)
    print(f"{len(kept)} gardées, {fixed} corrigées (ligne inventée retirée), {dropped} écartées (nombre absent)")


if __name__ == "__main__":
    argv = sys.argv[1:]
    lang = "fr"
    if "--lang" in argv:
        i = argv.index("--lang")
        lang = argv[i + 1]
        del argv[i:i + 2]
    main(argv[0], argv[1], lang)
