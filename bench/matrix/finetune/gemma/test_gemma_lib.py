"""Tests of gemma_lib: python3 -m pytest bench/matrix/finetune/gemma/test_gemma_lib.py
(GEMMA_TOK=<gemma dir> also runs the encoding tests against the real chat template).

SPDX-License-Identifier: MIT
"""

import json
import os

import pytest
import torch
from gemma_lib import adapter_deltas, checkpoint_key, encode, softcap
from safetensors.torch import save_file

KEY = "base_model.model.layers.3.self_attn.q_proj.lora_A.weight"


def test_checkpoint_key_points_to_the_language_model_weight():
    assert checkpoint_key(KEY) == "model.language_model.layers.3.self_attn.q_proj.weight"


def test_checkpoint_key_rejects_a_lora_b_key():
    with pytest.raises(AssertionError):
        checkpoint_key(KEY.replace("lora_A", "lora_B"))


def test_softcap_matches_gemma_formula_and_bounds_logits():
    x = torch.tensor([-1000.0, -3.0, 0.0, 3.0, 1000.0])
    y = softcap(x, 30.0)
    assert torch.allclose(y, torch.tanh(x / 30.0) * 30.0)
    assert y.abs().max() <= 30.0
    assert torch.equal(softcap(x, None), x)


def _adapter(folder, a, b, r=2, alpha=4):
    folder.mkdir()
    (folder / "adapter_config.json").write_text(json.dumps({"r": r, "lora_alpha": alpha}))
    save_file({KEY: a, KEY.replace("lora_A", "lora_B"): b}, str(folder / "adapter_model.safetensors"))


def test_adapter_deltas_average_scaled_products(tmp_path):
    a1, b1 = torch.randn(2, 5), torch.randn(3, 2)
    a2, b2 = torch.randn(2, 5), torch.randn(3, 2)
    _adapter(tmp_path / "s1", a1, b1)
    _adapter(tmp_path / "s2", a2, b2)
    d = adapter_deltas([str(tmp_path / "s1"), str(tmp_path / "s2")])
    expected = ((b1 @ a1) * 2 + (b2 @ a2) * 2) / 2
    assert list(d) == ["model.language_model.layers.3.self_attn.q_proj.weight"]
    assert torch.allclose(d["model.language_model.layers.3.self_attn.q_proj.weight"], expected, atol=1e-6)


needs_tok = pytest.mark.skipif(not os.environ.get("GEMMA_TOK"), reason="GEMMA_TOK not set")
MSGS = [{"role": "system", "content": "Résume."}, {"role": "user", "content": "Sortie :\n" + "ligne\n" * 400},
        {"role": "assistant", "content": "400 lignes."}]


@needs_tok
def test_encode_trains_on_the_answer_only():
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(os.environ["GEMMA_TOK"])
    ids, lab = encode(tok, MSGS, 4096)
    answer = [t for t in lab if t != -100]
    assert len(ids) == len(lab)
    assert tok.decode(answer).startswith("400 lignes.")
    assert lab[: len(lab) - len(answer)] == [-100] * (len(lab) - len(answer))


@needs_tok
def test_encode_cuts_the_prompt_not_the_answer():
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(os.environ["GEMMA_TOK"])
    full_ids, full_lab = encode(tok, MSGS, 4096)
    ids, lab = encode(tok, MSGS, 64)
    assert len(ids) == 64
    assert [t for t in lab if t != -100] == [t for t in full_lab if t != -100]


@needs_tok
def test_encode_with_replacement_answer_equals_the_same_conversation():
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(os.environ["GEMMA_TOK"])
    assert encode(tok, MSGS[:-1], 4096, "400 lignes.") == encode(tok, MSGS, 4096)


def test_lora_gguf_combination_is_exactly_the_soup_plus_the_added_adapter(tmp_path):
    from lora_gguf import combine
    a1, b1, a2, b2, a3, b3 = (torch.randn(2, 5), torch.randn(3, 2), torch.randn(2, 5), torch.randn(3, 2),
                              torch.randn(2, 5), torch.randn(3, 2))
    _adapter(tmp_path / "s1", a1, b1)
    _adapter(tmp_path / "s2", a2, b2)
    _adapter(tmp_path / "dpo", a3, b3)
    factors, rank = combine([str(tmp_path / "s1"), str(tmp_path / "s2")], [str(tmp_path / "dpo")])
    lora_a, lora_b = factors["layers.3.self_attn.q_proj"]
    expected = adapter_deltas([str(tmp_path / "s1"), str(tmp_path / "s2")])["model.language_model.layers.3.self_attn.q_proj.weight"]
    expected = expected + (b3 @ a3) * 2
    assert rank == 6
    assert torch.allclose(lora_b @ lora_a, expected, atol=1e-5)
