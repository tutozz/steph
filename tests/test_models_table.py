"""Tests de la partie pure de bench/matrix/models_table.py (tableau de fin de round, P6)."""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bench" / "matrix"))

import models_table as mt  # noqa: E402


def _row(fixture="fx00", out="ok", ttft=1.0, kind="summary"):
    return {"id": fixture, "fixture": fixture, "kind": kind, "ttft": ttft, "total": ttft + 0.1, "out": out}


def _write(path, rows, model="models/test-Q4_K_M.gguf", cases="cases.json", extra=None):
    payload = {"label": path.stem, "config": {"model": model, "cases": cases}, "rows": rows}
    if extra:
        payload.update(extra)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------- discover_result_files
class TestDiscoverResultFiles:
    def test_ignores_progress_json(self, tmp_path):
        _write(tmp_path / "model-a.json", [_row()])
        (tmp_path / "model-a.progress.json").write_text("{}", encoding="utf-8")
        names = {p.name for p in mt.discover_result_files([tmp_path])}
        assert names == {"model-a.json"}

    def test_ignores_judge_files_but_keeps_judged_models(self, tmp_path):
        _write(tmp_path / "judged-granite-350m-s42-Q4_K_M-b42.json", [_row()])
        (tmp_path / "judge-i5.json").write_text(json.dumps({"par_modele": {}}), encoding="utf-8")
        names = {p.name for p in mt.discover_result_files([tmp_path])}
        assert names == {"judged-granite-350m-s42-Q4_K_M-b42.json"}

    def test_ignores_server_log_and_non_json(self, tmp_path):
        _write(tmp_path / "model-a.json", [_row()])
        (tmp_path / "model-a.server.log").write_text("boot ok", encoding="utf-8")
        names = {p.name for p in mt.discover_result_files([tmp_path])}
        assert names == {"model-a.json"}

    def test_ignores_files_without_fixture_rows(self, tmp_path):
        # summary d'entraînement (schema différent, pas de "rows" exploitable) : ignoré
        (tmp_path / "judged-granite-350m-s42-Q4_K_M.json").write_text(
            json.dumps({"model": "x", "summary": {"total": 80.0}}), encoding="utf-8")
        # liste (fichiers du juge resolve()) : ignoré
        (tmp_path / "judge-resolve-rawctx.json").write_text(json.dumps([{"id": "fx00"}]), encoding="utf-8")
        assert mt.discover_result_files([tmp_path]) == []


# ---------------------------------------------------------------- average_with_range
class TestAverageWithRange:
    def test_mean_and_range_over_seeds(self):
        mean, lo, hi = mt.average_with_range([75.0, 80.7, 77.9])
        assert mean == pytest.approx((75.0 + 80.7 + 77.9) / 3)
        assert lo == 75.0
        assert hi == 80.7

    def test_single_value_range_collapses(self):
        mean, lo, hi = mt.average_with_range([82.8])
        assert (mean, lo, hi) == (82.8, 82.8, 82.8)

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            mt.average_with_range([])


# ---------------------------------------------------------------- fmt_cell (rendu FR)
class TestFmtCell:
    def test_single_value_no_range_shown(self):
        assert mt.fmt_cell(82.8, 82.8, 82.8) == "82,8"

    def test_range_shown_when_values_differ(self):
        assert mt.fmt_cell(77.87, 75.0, 80.7) == "77,9 (75,0–80,7)"

    def test_none_is_empty_cell(self):
        assert mt.fmt_cell(None, None, None) == ""


# ---------------------------------------------------------------- speed_stats : cellule vide si pas d'i5
class TestSpeedStats:
    def test_no_i5_file_leaves_every_cell_empty(self, tmp_path):
        stats = mt.speed_stats([])
        assert stats == {"ttft_median": None, "ttft_p90": None, "ram_mb": None}

    def test_single_i5_file_uses_its_own_values(self, tmp_path):
        p = tmp_path / "i5-model-a.json"
        _write(p, [_row()], extra={"ttft_median": 0.6, "ttft_p90": 2.3, "ram_peak_mb": 2545})
        stats = mt.speed_stats([p])
        assert stats["ttft_median"] == (0.6, 0.6, 0.6)
        assert stats["ttft_p90"] == (2.3, 2.3, 2.3)
        assert stats["ram_mb"] == 2545

    def test_multiple_rounds_give_median_and_range(self, tmp_path):
        p1 = tmp_path / "i5-vocab-full-Q8_0.json"
        p2 = tmp_path / "i5-vocab-full-Q8_0-r2.json"
        p3 = tmp_path / "i5-vocab-full-Q8_0-r3.json"
        _write(p1, [_row()], extra={"ttft_median": 1.5, "ttft_p90": 1.55, "ram_peak_mb": 690})
        _write(p2, [_row()], extra={"ttft_median": 1.6, "ttft_p90": 1.686, "ram_peak_mb": 700})
        _write(p3, [_row()], extra={"ttft_median": 1.6, "ttft_p90": 1.686, "ram_peak_mb": 700})
        stats = mt.speed_stats([p1, p2, p3])
        med, lo, hi = stats["ttft_p90"]
        assert med == 1.686
        assert (lo, hi) == (1.55, 1.686)


# ---------------------------------------------------------------- round_stem / seed_stem
class TestStems:
    def test_round_stem_strips_trailing_round_number(self):
        assert mt.round_stem("i5-vocab-full-Q8_0-r2.json") == mt.round_stem("i5-vocab-full-Q8_0.json")
        assert mt.round_stem("i5-vocab-full-Q8_0-r3.json") == "i5-vocab-full-Q8_0"

    def test_seed_stem_groups_bench_seeds(self):
        assert mt.seed_stem("judged-granite-350m-s42-Q4_K_M-b42.json") == \
            mt.seed_stem("judged-granite-350m-s42-Q4_K_M-b7.json")

    def test_seed_stem_none_when_no_seed_suffix(self):
        assert mt.seed_stem("homelab-rtx3060-gemma4-e2b.json") is None

    def test_round_stem_and_seed_stem_do_not_collide(self):
        # un round (-r2) n'est pas une graine (-b/-s) : les deux mécanismes restent distincts
        assert mt.seed_stem("i5-vocab-full-Q8_0-r2.json") is None


# ---------------------------------------------------------------- dedup de mesures identiques
class TestDedupIdenticalRows:
    def test_byte_identical_rows_counted_once(self, tmp_path):
        rows = [_row("fx00", "sortie identique")]
        p1 = tmp_path / "judged-granite-350m-s7-Q4_K_M-b42.json"
        p2 = tmp_path / "judged-granite-350m-s7.json"  # doublon historique du même run
        _write(p1, rows)
        _write(p2, rows)
        deduped = mt.dedup_identical_rows([p1, p2])
        assert len(deduped) == 1


# ---------------------------------------------------------------- classify_protocol
class TestClassifyProtocol:
    def test_long_steph_prompt_for_wave1_wave2_cases(self):
        assert mt.classify_protocol("cases_screen.json", "homelab-cpu2-gemma3-270m-crible.json") == "steph long"
        assert mt.classify_protocol("bench/matrix/cases.json", "mac-m3pro-metal-qwen3.5-9b.json") == "steph long"

    def test_short_finetune_prompt_for_ft_cases(self):
        assert mt.classify_protocol("cases_ft.json", "judged-granite-350m-s42-Q4_K_M-b42.json") == "court affiné"
        assert mt.classify_protocol("/root/steph-ft/bench/cases.json", "rtx3060-qwen3.5-0.8b-full-ft.json") == \
            "court affiné"

    def test_termspeak_from_filename(self):
        assert mt.classify_protocol(None, "opt-best-granite-termspeak-dev-fr.json") == "TermSpeak"


# ---------------------------------------------------------------- quality (v1/v2, tune/holdout/résumé)
class TestQuality:
    FACTS = {
        "_global_never": [],
        "_max_words": {"summary": 20, "qa": 30},
        "fx00": {"need": [r"\bok\b"], "never": []},
        "fx21": {"need": [r"\bko\b"], "never": []},
        "qa0": {"need": [r"\bok\b"], "never": []},
    }

    def test_full_score_when_all_facts_match(self):
        rows = [_row("fx00", "ok")]
        assert mt.quality(self.FACTS, rows, "all") == 100.0

    def test_holdout_only_keeps_holdout_fixtures(self):
        rows = [_row("fx00", "ok"), _row("fx21", "ko", kind="summary")]
        # fx00 hors contrôle, fx21 dans HOLDOUT (voir score.HOLDOUT)
        assert "fx21" in mt.HOLDOUT and "fx00" not in mt.HOLDOUT
        assert mt.quality(self.FACTS, rows, "holdout") == 100.0

    def test_holdout_summary_excludes_qa_cases(self):
        rows = [_row("fx21", "ko", kind="summary"), _row("qa0", "ok", kind="qa")]
        # qa0 est dans HOLDOUT mais de type "qa" : exclu du "résumé seul au contrôle"
        assert mt.quality(self.FACTS, rows, "holdout_summary") == 100.0
        only_qa_ids = {r["fixture"] for r in mt.filter_split(rows, "holdout_summary")}
        assert only_qa_ids == {"fx21"}

    def test_missing_row_yields_none(self):
        assert mt.quality(self.FACTS, [], "all") is None


# ---------------------------------------------------------------- find_local_gguf (taille)
class TestFindLocalGguf:
    def test_matches_by_token_overlap_and_exact_quant(self, tmp_path):
        (tmp_path / "judged-granite-350m-s42-Q4_K_M.gguf").write_bytes(b"0" * 1000)
        (tmp_path / "judged-granite-350m-s7-Q4_K_M.gguf").write_bytes(b"0" * 2000)
        found = mt.find_local_gguf(tmp_path, ["judged-granite-s42-Q4_K_M.gguf"])
        assert found is not None
        assert found.name == "judged-granite-350m-s42-Q4_K_M.gguf"

    def test_no_match_returns_none(self, tmp_path):
        (tmp_path / "some-other-model-Q4_K_M.gguf").write_bytes(b"0" * 10)
        assert mt.find_local_gguf(tmp_path, ["Qwen3.5-9B-Q4_K_M.gguf"]) is None
