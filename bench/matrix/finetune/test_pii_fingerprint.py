"""Tests de pii_fingerprint.py (P21) : empreintes salées des termes privés, recherche
de jetons par empreinte, sans jamais rendre le texte trouvé. Noms fictifs uniquement."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from pii_fingerprint import make_fingerprints, scan_file, scan_text  # noqa: E402

SALT = "00" * 16


def _fp(tmp_path, lines):
    names = tmp_path / "names.tsv"
    names.write_text("# commentaire\n" + "\n".join(lines) + "\n", encoding="utf-8")
    return make_fingerprints(str(names), SALT)


def test_fingerprints_hold_no_clear_term(tmp_path):
    fp = _fp(tmp_path, ["Zorglub\tuser", "jean-zed"])
    dumped = json.dumps(fp).lower()
    assert "zorglub" not in dumped and "jean" not in dumped
    assert set(fp["hashes"].values()) == {"n01", "n02"}


def test_case_and_word_boundaries(tmp_path):
    fp = _fp(tmp_path, ["Zorglub"])
    assert scan_text("ssh ZORGLUB@box", fp) == ["n01"]
    assert scan_text("/home/zorglub/src", fp) == ["n01"]
    assert scan_text("zorglubs et xzorglub", fp) == []


def test_separator_variants_of_multi_word_term(tmp_path):
    fp = _fp(tmp_path, ["jean-zed"])
    for text in ("Jean Zed", "jean.zed", "jean_zed", "JeanZed", "jean-zed-laptop"):
        assert scan_text(text, fp) == ["n01"], text
    assert scan_text("jean, zed", fp) == []


def test_accented_form_matches_ascii_term(tmp_path):
    fp = _fp(tmp_path, ["zoe"])
    assert scan_text("merci Zoé", fp) == ["n01"]


def test_scan_file_reports_line_and_field_only(tmp_path):
    fp = _fp(tmp_path, ["Zorglub"])
    data = tmp_path / "d.jsonl"
    rows = [
        {"messages": [{"role": "user", "content": "rien"}, {"role": "assistant", "content": "Zorglub a lancé"}]},
        {"prompt": "rien", "rejected": "x", "chosen": "y"},
        {"prompt": "chez zorglub", "chosen": "ok"},
    ]
    data.write_text("\n".join(json.dumps(r) for r in rows) + "\nnot json zorglub\n", encoding="utf-8")
    hits = scan_file(str(data), fp)
    assert hits == [
        {"line": 1, "field": "messages[1](assistant)", "id": "n01"},
        {"line": 3, "field": "prompt", "id": "n01"},
        {"line": 4, "field": "<raw>", "id": "n01"},
    ]


def test_term_with_other_separator(tmp_path):
    fp = _fp(tmp_path, ["zed@lab-x"])
    assert scan_text("mail ZED@LAB-X ok", fp) == ["n01"]
