"""Shared helpers of the bench v3 tools: production input rebuild, v3-fp1 fingerprints, prod path.

SPDX-License-Identifier: MIT
"""

import hashlib
import re
import sys
from pathlib import Path

V3 = Path(__file__).resolve().parents[1]
REPO = V3.parents[2]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "bench" / "matrix" / "finetune"))

from steph import prompts  # noqa: E402
from steph.config import Config  # noqa: E402
from steph.digest import digest, extract_facts, resolve  # noqa: E402
from steph.textproc import compact_output  # noqa: E402

MAX_CHARS = 587
VERBATIM_MAX_WORDS = 20  # config.read_verbatim_max_words


def output_lines(output_raw):
    return output_raw.split("\n") if output_raw else []


def production_facts(case, lang):
    """Code-extracted facts block (L5) as narrator adds it when config facts_block is on, else None."""
    if not Config().facts_block:
        return None
    return extract_facts(case["cmd"], case["exit"], "\n".join(output_lines(case["output_raw"])), lang)


def rebuild_summary_input(case, lang):
    """[system, user] exactly as narrator sends them with the finetuned profile (B3), facts block included."""
    lines = output_lines(case["output_raw"])
    out = digest(case["cmd"], "\n".join(lines), MAX_CHARS, lang) or compact_output(lines, MAX_CHARS)
    return prompts.finetuned_summary_messages(case["cmd"], case["exit"], case["duration_s"], out,
                                              case["nlines"], language=lang, facts=production_facts(case, lang))


QA_BLOCK_CHARS = 2500  # config.qa_block_chars ; budget : narrator.FINETUNED_QA_BUDGET_CHARS

# Sampling steph sends in production (X5): llm.LLM.stream / _payload, narrator._llm_say, server._ask.
# test_production_sampling.py fails as soon as src/steph drifts from these values.
PRODUCTION_PAYLOAD = {
    "summary": {"temperature": 0.2, "top_p": 0.9, "max_tokens": 90},
    "qa": {"temperature": 0.3, "top_p": 0.9, "max_tokens": 400},
}


def production_payload(task):
    return dict(PRODUCTION_PAYLOAD[task])


def rebuild_qa_input(case, lang):
    """[system, historique, accusé, question] exactement comme server._ask en profil affiné (P20)."""
    from qa_corpus import production_qa_messages
    records = [{"cmd": h["cmd"], "exit": h["exit"], "duration": h["duration_s"], "output": h["output_raw"]}
               for h in case["history"]]
    return production_qa_messages(records, case["cwd"], case["question"][lang], lang, QA_BLOCK_CHARS)


def reaches_model(case, lang):
    """False when steph answers without the model (narrator: empty, 127, verbatim, resolve()).

    Approximation of narrator._summarize with the default config and no per-command rule."""
    if case["task"] != "summary":
        return True
    text = case["output_raw"].strip()
    code = case["exit"]
    if not text:
        return False
    if code == 127 and re.search(r"not found|introuvable|non trouvée", text):
        return False
    if len(text.split()) <= VERBATIM_MAX_WORDS and len(text.split("\n")) <= 3:
        return False
    return not resolve(case["cmd"], code, text, lang)


# ---------------------------------------------------------------- v3-fp1 (DESIGN.md section 7)
HEX = re.compile(r"\b[0-9a-f]{6,}\b")
PATH = re.compile(r"(?:~|\.{1,2})?(?:/[\w.@+-]+)+/?")
DIGIT = re.compile(r"\d")
SPACE = re.compile(r"\s+")


def norm_line(line):
    s = line.lower()
    s = HEX.sub("h", s)
    s = PATH.sub("/p", s)
    s = DIGIT.sub("0", s)
    return SPACE.sub(" ", s).strip()


def line_fps(text):
    return {hashlib.sha1(n.encode()).hexdigest()[:12] for n in (norm_line(l) for l in text.split("\n")) if n}


def shingles(text, k=5):
    words = " ".join(norm_line(l) for l in text.split("\n")).split()
    return {hashlib.sha1(" ".join(words[i:i + k]).encode()).hexdigest()[:12] for i in range(max(0, len(words) - k + 1))}


def norm_cmd(cmd):
    parts = [p for p in cmd.replace("sudo ", "").split() if not p.startswith("-")]
    return " ".join(parts[:2]) if len(parts) > 1 and not re.search(r"[/.=]", parts[1]) else (parts[0] if parts else "")


def jaccard(a, b):
    return len(a & b) / len(a | b) if a and b else 0.0


def case_text(case):
    if case["task"] == "summary":
        return case["output_raw"]
    return "\n".join(h["output_raw"] for h in case["history"])
