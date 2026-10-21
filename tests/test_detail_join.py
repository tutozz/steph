"""X4 : le détail garde ses points. L'enseignant écrit un point par ligne ; `clean()` les joignait
par une espace, sans ponctuation (défaut de chaîne trouvé en X4a, docs/labeling-audit.md)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bench" / "matrix"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bench" / "matrix" / "finetune"))

import label_features  # noqa: E402
from score import clean  # noqa: E402


def test_points_join_lines_with_a_period():
    assert clean("Erreur E404\n3 paquets absents\nregistre npm", points=True) == "Erreur E404. 3 paquets absents. registre npm"


def test_points_do_not_double_existing_punctuation():
    assert clean("Erreur E404.\nfichier absent :\nmain.c!", points=True) == "Erreur E404. fichier absent : main.c!"


def test_points_single_line_unchanged():
    assert clean("3 tests passés, 1 échoué", points=True) == "3 tests passés, 1 échoué"


def test_default_join_unchanged_for_summaries():
    assert clean("Succès\n3 fichiers") == "Succès 3 fichiers"


def test_detail_label_keeps_points():
    label, reason = label_features.judge("Erreur E404\n3 paquets absents", 60, mode="detail")
    assert (label, reason) == ("Erreur E404. 3 paquets absents", "ok")


def test_other_feature_modes_keep_space_join():
    label, _ = label_features.judge("Compile\nle module", 12, mode="progress")
    assert label == "Compile le module"
