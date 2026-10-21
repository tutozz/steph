"""Tests de la partie pure de train_lora.py : batch auto, contrôle temps réel,
arrêt anticipé, masquage de la perte, planification du taux d'apprentissage.

Aucun import torch/transformers/peft ici : train_lora.py garde ces imports à
l'intérieur des fonctions qui en ont besoin, pour que ces tests tournent même
sans torch installé.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bench" / "matrix" / "finetune"))

from train_lora import (
    append_metrics,
    build_labels,
    choose_batch,
    pad_batch,
    read_control,
    scheduled_lr,
    should_stop_early,
    write_status,
)


class TestChooseBatch:
    def test_cpu_or_unknown_vram_falls_back_to_batch_one(self):
        batch, accum = choose_batch(None, vocab_size=32000)
        assert batch == 1
        assert accum == 16

    def test_small_vram_small_vocab(self):
        batch, accum = choose_batch(6 * 1024, vocab_size=32000)
        assert batch >= 1
        assert batch * accum >= 16

    def test_large_vocab_forces_small_batch_even_on_tight_vram(self):
        # Gemma 3, 262 000 jetons, 6 Go de VRAM : le piège documenté (lot 1 à 2).
        batch, _ = choose_batch(6 * 1024, vocab_size=262_000)
        assert batch <= 2

    def test_more_vram_never_shrinks_the_batch(self):
        small, _ = choose_batch(6 * 1024, vocab_size=262_000)
        large, _ = choose_batch(48 * 1024, vocab_size=262_000)
        assert large >= small

    def test_effective_batch_always_reaches_the_target(self):
        for vram, vocab in [(6 * 1024, 32000), (24 * 1024, 151936), (48 * 1024, 262000), (None, 32000)]:
            batch, accum = choose_batch(vram, vocab, target_effective=16)
            assert batch * accum >= 16

    def test_large_vocab_shrinks_the_batch_at_equal_vram(self):
        small_vocab_batch, _ = choose_batch(24 * 1024, vocab_size=32000)
        large_vocab_batch, _ = choose_batch(24 * 1024, vocab_size=262000)
        assert large_vocab_batch < small_vocab_batch


class TestReadControl:
    def test_missing_file_returns_empty_dict(self, tmp_path):
        assert read_control(tmp_path / "control.json") == {}

    def test_stop_action_is_parsed_and_the_file_is_consumed(self, tmp_path):
        p = tmp_path / "control.json"
        p.write_text(json.dumps({"action": "stop"}))
        data = read_control(p)
        assert data == {"action": "stop"}
        assert not p.exists()  # à usage unique : jamais relu au pas suivant

    def test_lr_scale_and_eval_now_are_parsed(self, tmp_path):
        p = tmp_path / "control.json"
        p.write_text(json.dumps({"lr_scale": 0.5, "eval_now": True}))
        data = read_control(p)
        assert data["lr_scale"] == 0.5
        assert data["eval_now"] is True

    def test_malformed_json_is_ignored_but_kept_for_retry(self, tmp_path):
        # Écriture concurrente par ssh depuis train_control.sh : peut être lue à moitié écrite.
        p = tmp_path / "control.json"
        p.write_text("{not json")
        data = read_control(p)
        assert data == {}
        assert p.exists()  # pas supprimé : retenté au pas suivant une fois l'écriture finie


class TestShouldStopEarly:
    def test_not_enough_evaluations_never_stops(self):
        assert should_stop_early([0.9, 0.8], patience=3) is False

    def test_still_improving_does_not_stop(self):
        assert should_stop_early([0.9, 0.7, 0.5, 0.4], patience=3) is False

    def test_stops_after_patience_evaluations_without_improvement(self):
        assert should_stop_early([0.9, 0.4, 0.45, 0.46, 0.47], patience=3) is True

    def test_does_not_stop_one_evaluation_short_of_patience(self):
        assert should_stop_early([0.9, 0.4, 0.45, 0.46], patience=3) is False

    def test_a_new_best_resets_the_counter(self):
        assert should_stop_early([0.9, 0.4, 0.45, 0.3, 0.31], patience=3) is False


class TestBuildLabels:
    def test_masks_everything_before_the_assistant_response(self):
        assert build_labels([1, 2, 3], [1, 2, 3, 4, 5, 6]) == [-100, -100, -100, 4, 5, 6]

    def test_keeps_the_assistant_response_untouched(self):
        labels = build_labels([1, 2], [1, 2, 7, 8, 9])
        assert labels[2:] == [7, 8, 9]
        assert all(v == -100 for v in labels[:2])

    def test_falls_back_to_the_longest_common_prefix_on_template_drift(self):
        # Le gabarit peut diverger légèrement entre les deux rendus (ex. jeton de fin) :
        # on masque au plus long préfixe commun plutôt que de planter.
        assert build_labels([1, 2, 3, 99], [1, 2, 3, 4, 5]) == [-100, -100, -100, 4, 5]

    def test_empty_prompt_masks_nothing(self):
        assert build_labels([], [1, 2, 3]) == [1, 2, 3]


class TestPadBatch:
    def test_pads_to_the_longest_sequence(self):
        padded, mask = pad_batch([[1, 2, 3], [1, 2]], pad_value=0)
        assert padded == [[1, 2, 3], [1, 2, 0]]
        assert mask == [[1, 1, 1], [1, 1, 0]]

    def test_single_sequence_is_untouched(self):
        padded, mask = pad_batch([[5, 6]], pad_value=0)
        assert padded == [[5, 6]]
        assert mask == [[1, 1]]


class TestScheduledLr:
    def test_warmup_ramps_up_linearly(self):
        lr0 = scheduled_lr(0, total_steps=100, warmup_steps=10, base_lr=2e-4)
        lr5 = scheduled_lr(5, total_steps=100, warmup_steps=10, base_lr=2e-4)
        lr9 = scheduled_lr(9, total_steps=100, warmup_steps=10, base_lr=2e-4)
        assert lr0 < lr5 < lr9 <= 2e-4

    def test_decays_after_warmup_towards_zero(self):
        after_warmup = scheduled_lr(10, total_steps=100, warmup_steps=10, base_lr=2e-4)
        near_end = scheduled_lr(99, total_steps=100, warmup_steps=10, base_lr=2e-4)
        assert near_end < after_warmup

    def test_zero_warmup_starts_directly_in_decay_phase(self):
        assert scheduled_lr(0, total_steps=100, warmup_steps=0, base_lr=2e-4) <= 2e-4


class TestMetricsAndStatus:
    def test_append_metrics_writes_one_json_line_per_call(self, tmp_path):
        p = tmp_path / "metrics.jsonl"
        append_metrics(p, {"step": 1, "loss": 0.5})
        append_metrics(p, {"step": 2, "loss": 0.4})
        lines = p.read_text().splitlines()
        assert len(lines) == 2
        assert json.loads(lines[0]) == {"step": 1, "loss": 0.5}
        assert json.loads(lines[1]) == {"step": 2, "loss": 0.4}

    def test_write_status_produces_readable_json_overwritten_each_time(self, tmp_path):
        p = tmp_path / "status.json"
        write_status(p, state="running", step=3)
        assert json.loads(p.read_text()) == {"state": "running", "step": 3}
        write_status(p, state="done", step=10)
        assert json.loads(p.read_text()) == {"state": "done", "step": 10}
