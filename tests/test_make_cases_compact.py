"""Tests de l'option --system de make_cases_compact.py (TRAIN_SYSTEM vs SUMMARY_SYSTEM).

Cas P11 : régénérés avec SUMMARY_SYSTEM (prod) au lieu de TRAIN_SYSTEM (protocole
d'entraînement, label.py:32) -> chute de qualité mesurée sur Gemma. `case_messages`
doit pouvoir produire les deux, sans changer le message utilisateur.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bench" / "matrix" / "finetune"))
sys.path.insert(0, str(ROOT / "bench" / "matrix"))

from label import TRAIN_SYSTEM  # noqa: E402
from make_cases_compact import case_messages  # noqa: E402
from steph.prompts import SUMMARY_SYSTEM  # noqa: E402


class TestCaseMessages:
    def test_default_system_is_summary_system(self):
        msgs = case_messages("df -h", 0, 0.1, "Racine 50G", 1, system="prod")
        assert msgs[0]["content"] == SUMMARY_SYSTEM

    def test_train_system_uses_train_system(self):
        msgs = case_messages("df -h", 0, 0.1, "Racine 50G", 1, system="train")
        assert msgs[0]["content"] == TRAIN_SYSTEM

    def test_train_system_has_no_few_shot_example(self):
        msgs = case_messages("df -h", 0, 0.1, "Racine 50G", 1, system="train")
        assert "Header.tsx" not in msgs[0]["content"]

    def test_user_message_unaffected_by_system_choice(self):
        prod = case_messages("df -h", 0, 0.1, "Racine 50G", 1, system="prod")
        train = case_messages("df -h", 0, 0.1, "Racine 50G", 1, system="train")
        assert prod[1] == train[1]
