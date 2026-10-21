"""Tests de t9_calibrate_a7.py : tirage stratifié et précision/rappel pondérés. Aucun réseau."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import t9_calibrate_a7 as ca  # noqa: E402


def v(i, final):
    return {"id": f"c{i}@fr", "model_file": "r.json", "phrase": f"p{i}", "final": final}


def test_sample_keeps_all_flagged_then_fills_with_ok():
    verdicts = [v(i, "invention") for i in range(3)] + [v(i, "douteux") for i in range(3, 5)] + \
               [v(i, "ok") for i in range(5, 50)] + [v(99, "erreur")]
    s = ca.sample(verdicts, n=10, seed=1)
    finals = [x["final"] for x in s]
    assert finals.count("invention") == 3 and finals.count("douteux") == 2 and finals.count("ok") == 5
    assert "erreur" not in finals
    assert ca.sample(verdicts, n=10, seed=1) == s


def test_metrics_weighted_by_stratum():
    # strate ok : 5 tirés sur 45 (poids 9) ; strate invention : 3 sur 3 (poids 1)
    rows = [{"final": "invention", "ref": "invention"}, {"final": "invention", "ref": "invention"},
            {"final": "invention", "ref": "ok"}] + [{"final": "ok", "ref": "ok"}] * 4 + [{"final": "ok", "ref": "invention"}]
    m = ca.metrics(rows, population={"invention": 3, "ok": 45}, positive=("invention",))
    assert m["raw"]["precision"] == pytest.approx(2 / 3)
    assert m["raw"]["recall"] == pytest.approx(2 / 3)
    # rappel pondéré : vrais positifs 2 ; manqués 1 x poids 45/5 = 9
    assert m["weighted"]["recall"] == pytest.approx(2 / 11)
    assert m["weighted"]["precision"] == pytest.approx(2 / 3)
