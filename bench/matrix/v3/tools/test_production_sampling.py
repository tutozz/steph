"""X5 : le harnais du banc v3 échantillonne comme la production (src/steph), résumé et question.

    python3 -m pytest bench/matrix/v3/tools/test_production_sampling.py -q

SPDX-License-Identifier: MIT
"""

import inspect
import json
import re

import v3lib  # noqa: F401  (met src/ dans sys.path)
from steph.llm import LLM
from steph.narrator import Narrator
from steph.server import ControlServer


def production_top_p():
    return LLM._payload(object.__new__(LLM), [], 1, 0.0, False)["top_p"]


def test_summary_payload_is_the_narrator_one():
    expected = {
        "temperature": inspect.signature(LLM.stream).parameters["temperature"].default,
        "top_p": production_top_p(),
        "max_tokens": inspect.signature(Narrator._llm_say).parameters["max_tokens"].default,
    }
    assert v3lib.production_payload("summary") == expected


def test_qa_payload_is_the_server_ask_one():
    src = inspect.getsource(ControlServer._ask)
    m = re.search(r"llm\.stream\(msgs, max_tokens=(\d+), temperature=([\d.]+)", src)
    assert m, "appel du modèle introuvable dans ControlServer._ask"
    expected = {"temperature": float(m.group(2)), "top_p": production_top_p(), "max_tokens": int(m.group(1))}
    assert v3lib.production_payload("qa") == expected


def test_harness_rows_carry_the_production_payload():
    for split in ("dev", "test"):
        for row in json.load(open(v3lib.V3 / "harness" / f"{split}.json")):
            assert row.get("payload") == v3lib.production_payload(row["kind"]), row["id"]
