#!/usr/bin/env python3
"""Composite production score of bench v3: what the user actually hears.

    python3 score_production.py [--split dev] [--harness h.json] [--no-ground] [--per-case] <run.json> [...]

Per row, as narrator._finish and server._ask do with the default config: if steph speaks in code
(empty output, 127, short output read as is, resolve()), the answer is that sentence and the model
answer of the run is ignored; otherwise the model answer goes through the grounding guard
(ground_output, on by default), its echoed status is dropped and the status said in code is
prefixed; a fully grounded-out summary becomes the code-built fallback. Same scale as score_v3.

Not modelled: per-command rules, the line-count filler said while the prompt is read, the
duration suffix of long commands, interactive and full-screen sessions.

`--harness`: the harness the run was produced on (generic_harness.py output for raw models);
the grounding guard reads its user messages. Default: harness/<split>.json (finetuned profile).

SPDX-License-Identifier: MIT
"""

import argparse
import json
import re
from pathlib import Path

import v3lib  # noqa: F401  (puts src/ on sys.path)
import score_v3
from steph.digest import grep_no_match, not_found_sentence, resolve
from steph import grounding
from steph.narrator import SILENT_OK, first_word, fmt_duration
from steph.strings import t as _t
from steph.textproc import important_lines, strip_ansi, strip_symbol_runs

FIRST_UPDATE_AFTER = 4.0  # config.first_update_after
NOT_FOUND_127 = re.compile(r"not found|introuvable|non trouvée")
DROPPED_LINES = ("^C", "^Z", "^\\")


def _lines(case):
    return [l for l in v3lib.output_lines(case["output_raw"]) if l.strip() and l.strip() not in DROPPED_LINES]


def _long(case):
    return case["duration_s"] >= FIRST_UPDATE_AFTER


def status_prefix(case, lang):
    """Status narrator says before a summary (P9): long commands get « Interrompu. » for 130."""
    code = case["exit"]
    if code is None:
        return ""
    if code == 0:
        return _t(lang, "narrator.status_success")
    if code == 130 and _long(case):
        return _t(lang, "narrator.status_interrupted")
    return _t(lang, "narrator.status_failed").format(code=code)


def code_answer(case, lang):
    """Sentence steph says without the model, or None when the model is asked (narrator._finish)."""
    lines = _lines(case)
    text = "\n".join(lines).strip()
    code, fw, long_cmd = case["exit"], first_word(case["cmd"]), _long(case)
    dur = fmt_duration(case["duration_s"], lang)
    if code == 127 and (NOT_FOUND_127.search(text) or not text):
        return not_found_sentence(fw, text, lang)
    if not text:
        if no_match := grep_no_match(case["cmd"], code, lang):
            return no_match
        if code == 0:
            if long_cmd:
                return _t(lang, "narrator.no_output_success_long").format(dur=dur)
            return "" if fw in SILENT_OK else _t(lang, "ok")
        if code == 130:
            return (_t(lang, "narrator.no_output_interrupted_long").format(dur=dur) if long_cmd
                    else _t(lang, "interrupted"))
        if long_cmd:
            return _t(lang, "narrator.no_output_failed_long").format(code=code, dur=dur)
        return _t(lang, "failed_no_message").format(code=code)
    prefix = status_prefix(case, lang) if long_cmd else ""
    if len(text.split()) <= v3lib.VERBATIM_MAX_WORDS and len(lines) <= 3:
        say = strip_symbol_runs(strip_ansi(text)).replace("\n", ". ")
        if code not in (0, None):
            say = _t(lang, "error_code").format(code=code, say=say)
        return prefix + say
    said = resolve(case["cmd"], code, case["output_raw"], lang)
    if not said:
        return None
    failed_word = _t(lang, "resolve.failed").rstrip(".")
    if prefix and said.startswith(failed_word):
        said = said.split(" ", 1)[1]
    return prefix + said


def fallback_summary(case, lang):
    lines = _lines(case)
    imp = important_lines(lines, 2)
    last = strip_ansi(imp[-1] if (imp and case["exit"]) else lines[-1]).strip()[:160]
    status = "OK" if case["exit"] == 0 else _t(lang, "fallback_code").format(code=case["exit"])
    return _t(lang, "fallback_summary").format(status=status, n=len(lines), last=last)


def production_answer(case, lang, out, model_input, ground=True):
    """(sentence heard, source) for one row: source is code, model or model-fallback."""
    if case["task"] == "qa":
        text = grounding.ground(model_input, out, True, lang) if ground else out
        return text, "model"
    said = code_answer(case, lang)
    if said is not None:
        return said, "code"
    text = grounding.ground(model_input, out, False, lang) if ground else out
    prefix = status_prefix(case, lang)
    # narrator._drop_leading_status retire l'écho du statut : s'il était seul, le repli part
    text = score_v3.STATUS_ECHO.sub("", text.strip(), count=1)
    if not text.strip(" ."):
        return prefix + fallback_summary(case, lang), "model-fallback"
    return prefix + text, "model"



def model_input(row):
    """User turns the model saw, minus the question itself (server._ask grounds on the history)."""
    users = [m["content"] for m in row["messages"] if m["role"] == "user"]
    return "\n".join(users[:-1] if len(users) > 1 else users)


def score_run(cases, path, harness, ground_output=True):
    data = json.load(open(path))
    per = {}
    for r in data["rows"]:
        case_id, lang = score_v3.parse_row_id(r["id"])
        if case_id not in cases or r["id"] not in harness:
            continue
        case = cases[case_id]
        text, src = production_answer(case, lang, r.get("out") or "", model_input(harness[r["id"]]), ground_output)
        per[r["id"]] = {"score": score_v3.score_answer(case, lang, text), "source": src, "said": text}
    scores = [p["score"] for p in per.values()]
    code = [p for p in per.values() if p["source"] == "code"]
    by_family = {}
    for rid, p in per.items():
        by_family.setdefault(cases[score_v3.parse_row_id(rid)[0]]["family"], []).append(p["score"])
    return {
        "label": data.get("label"),
        "quality": score_v3.mean_pct(scores),
        "code_share": round(100 * len(code) / len(per), 1) if per else None,
        "code_quality": score_v3.mean_pct([p["score"] for p in code]),
        "model_quality": score_v3.mean_pct([p["score"] for p in per.values() if p["source"] != "code"]),
        "fallback": sum(p["source"] == "model-fallback" for p in per.values()),
        "fr": score_v3.mean_pct([p["score"] for rid, p in per.items() if rid.endswith("@fr")]),
        "en": score_v3.mean_pct([p["score"] for rid, p in per.items() if rid.endswith("@en")]),
        "by_family": {k: score_v3.mean_pct(v) for k, v in sorted(by_family.items())},
        "n": len(per),
        "per_case": per,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--split", default="dev", choices=["dev", "test", "all"])
    ap.add_argument("--harness", help="harness the run was produced on (default: harness/<split>.json)")
    ap.add_argument("--no-ground", action="store_true", help="skip the grounding guard (ground_output off)")
    ap.add_argument("--per-case", action="store_true")
    a = ap.parse_args()
    cases = score_v3.load_cases(a.split)
    harness = ({h["id"]: h for h in json.load(open(a.harness))} if a.harness else score_v3.load_harness(a.split))
    for p in a.runs:
        res = score_run(cases, p, harness, not a.no_ground)
        if not a.per_case:
            del res["per_case"]
        print(json.dumps({"file": Path(p).name, **res}, ensure_ascii=False))


if __name__ == "__main__":
    main()
