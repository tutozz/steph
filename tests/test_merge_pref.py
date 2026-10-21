import json
import subprocess
import sys
from pathlib import Path

import pytest

torch = pytest.importorskip("torch")
safetensors_torch = pytest.importorskip("safetensors.torch")

SCRIPT = Path(__file__).resolve().parents[1] / "bench/matrix/finetune/pref/merge_pref.py"


def adapter(folder, a, b, alpha=2, r=1):
    folder.mkdir(parents=True)
    (folder / "adapter_config.json").write_text(json.dumps({"lora_alpha": alpha, "r": r}))
    safetensors_torch.save_file({"base_model.model.lin.lora_A.weight": torch.tensor([[a]]),
                                 "base_model.model.lin.lora_B.weight": torch.tensor([[b]])},
                                str(folder / "adapter_model.safetensors"))


def merged(tmp_path, *extra):
    base = tmp_path / "base"
    base.mkdir(exist_ok=True)
    safetensors_torch.save_file({"lin.weight": torch.tensor([[1.0]])}, str(base / "model.safetensors"))
    out = tmp_path / "out"
    subprocess.run([sys.executable, str(SCRIPT), "--base", str(base), "--out", str(out),
                    "--sft", str(tmp_path / "sft"), "--pref", str(tmp_path / "pref"), *extra], check=True, capture_output=True)
    return float(safetensors_torch.load_file(str(out / "model.safetensors"))["lin.weight"].float())


def test_scales_weight_each_delta(tmp_path):
    adapter(tmp_path / "sft", 1.0, 2.0)   # delta 2 * 1 * alpha/r 2 = 4
    adapter(tmp_path / "pref", 1.0, 0.5)  # delta 1
    assert merged(tmp_path) == pytest.approx(6.0)
    assert merged(tmp_path, "--sft-scale", "0.5") == pytest.approx(4.0)
    assert merged(tmp_path, "--sft-scale", "0.5", "--pref-scale", "0") == pytest.approx(3.0)
