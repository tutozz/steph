import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bench/matrix/finetune"))

from fix_labels import fix_label, invented_number, output_of  # noqa: E402


def test_invented_line_is_removed():
    out = "ls: impossible d'accéder à '/nope': Aucun fichier ou dossier de ce nom"
    assert fix_label("Échec. /nope ligne 1 : fichier absent.", out) == "Échec. /nope : fichier absent."


def test_exit_code_is_not_a_line():
    out = "tar: archive.tar: Cannot open: No such file or directory\ntar: Error is not recoverable"
    assert "ligne 2" not in fix_label("Échec. archive.tar ligne 2 : introuvable.", out)


def test_real_python_line_is_kept():
    out = 'File "app.py", line 3, in <module>\nModuleNotFoundError: No module named flask'
    assert fix_label("Échec. app.py ligne 3 : module flask manquant.", out) == "Échec. app.py ligne 3 : module flask manquant."


def test_real_tsc_line_is_kept():
    out = "src/Header.tsx:42:17 - error TS2339: Property 'titel' does not exist"
    assert "ligne 42" in fix_label("Échec. Header.tsx ligne 42 : titel inconnu.", out)


def test_number_absent_from_output_is_flagged():
    assert invented_number("37 éléments, 1516 lignes.", "37 éléments : a, b, c")
    assert not invented_number("37 éléments : a, b, c.", "37 éléments : a, b, c")


# K2 : fix_labels.py était figé sur le français (regex « ligne », marqueur « Sortie : »,
# espace typographique avant « : »). Les étiquettes EN disent « line » et « Output: ».


def test_output_of_splits_on_english_marker():
    user = "Command: df -h\nStatus: success\nOutput:\nroot 685G free of 953G"
    assert output_of(user, language="en") == "\nroot 685G free of 953G"


def test_invented_line_is_removed_english():
    out = "ls: cannot access '/nope': No such file or directory"
    assert fix_label("Failed. /nope line 1: file missing.", out, language="en") == "Failed. /nope: file missing."


def test_real_line_is_kept_english():
    out = 'File "app.py", line 3, in <module>\nModuleNotFoundError: No module named flask'
    result = fix_label("Failed. app.py line 3: missing flask module.", out, language="en")
    assert result == "Failed. app.py line 3: missing flask module."


def test_english_fix_never_adds_a_space_before_colon():
    """Règle typographique française (espace avant « : ») absente en anglais : ne pas
    la propager, sinon le fix introduit une faute dans les étiquettes EN."""
    out = "ls: cannot access '/nope': No such file or directory"
    result = fix_label("Failed. /nope line 1: file missing.", out, language="en")
    assert " :" not in result
    assert result.count(":") == 1
