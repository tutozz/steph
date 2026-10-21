"""Corpus rows (short training prompts of label.py and label_features.py) rewritten to the
production generic profile that steph sends to raw Gemma 4 E2B (llm_profile = generic).

Only the system turn changes: the user turn (Commande/Statut/Durée/Sortie) is already the
production one, and questions already use QA_SYSTEM. A row whose system prompt is not a
known training prompt is left unchanged, and counted by the caller.

SPDX-License-Identifier: MIT
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import label  # noqa: E402
import label_features as lf  # noqa: E402
from steph import prompts  # noqa: E402

TRAIN_TO_GENERIC = {
    label.TRAIN_SYSTEM: prompts.SUMMARY_SYSTEM,
    label.TRAIN_SYSTEM_EN: prompts.SUMMARY_SYSTEM_EN,
    lf.TRAIN_DETAILS_SYSTEM: prompts.DETAILS_SYSTEM,
    lf.TRAIN_DETAILS_SYSTEM_EN: prompts.DETAILS_SYSTEM_EN,
    lf.TRAIN_PROGRESS_SYSTEM: prompts.PROGRESS_SYSTEM,
    lf.TRAIN_PROGRESS_SYSTEM_EN: prompts.PROGRESS_SYSTEM_EN,
    lf.TRAIN_START_SYSTEM: prompts.START_SYSTEM,
    lf.TRAIN_START_SYSTEM_EN: prompts.START_SYSTEM_EN,
}
GENERIC = set(TRAIN_TO_GENERIC.values()) | {prompts.QA_SYSTEM, prompts.QA_SYSTEM_EN}


def to_generic(messages: list[dict]) -> tuple[list[dict], bool]:
    """Returns the messages with the production generic system prompt, and whether the row is known."""
    if not messages or messages[0]["role"] != "system":
        return messages, False
    system = messages[0]["content"]
    if system in GENERIC:
        return messages, True
    if system in TRAIN_TO_GENERIC:
        return [{"role": "system", "content": TRAIN_TO_GENERIC[system]}] + messages[1:], True
    return messages, False
