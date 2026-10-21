"""Z11 : le GPU se décide sur la VRAM libre, pas sur la VRAM totale (RTX 3080 de 10 Go
dont 3,3 Go libres, partagée avec une passerelle IA)."""

import subprocess
from pathlib import Path

from steph import catalog, hardware, speed
from steph.config import Config
from steph.hardware import Gpu
from steph.llm import _build_args

# sortie réelle de `nvidia-smi --query-gpu=name,memory.free --format=csv,noheader,nounits` sur une machine du labo
SMI_FREE = "Quadro P400, 1993\nNVIDIA GeForce RTX 3080, 3349\n"


class _Result:
    def __init__(self, stdout):
        self.stdout = stdout


def _fake_smi(monkeypatch, stdout, calls=None):
    monkeypatch.setattr(hardware.shutil, "which", lambda name: "/usr/bin/nvidia-smi")

    def run(cmd, **kw):
        if calls is not None:
            calls.append(cmd)
        return _Result(stdout)

    monkeypatch.setattr(hardware.subprocess, "run", run)


def _model(tmp_path, mb):
    path = tmp_path / "m.gguf"
    with open(path, "wb") as f:
        f.truncate(mb * 1024 * 1024)
    return str(path)


# ------------------------------------------------------------ détection


def test_free_vram_asks_nvidia_smi_for_memory_free(monkeypatch):
    calls = []
    _fake_smi(monkeypatch, SMI_FREE, calls)
    assert hardware.detect_gpu_vram([], free=True) == {"Quadro P400": 1993, "NVIDIA GeForce RTX 3080": 3349}
    assert any("memory.free" in part for part in calls[0])


def test_total_vram_still_asks_memory_total(monkeypatch):
    calls = []
    _fake_smi(monkeypatch, "NVIDIA GeForce RTX 3080, 10240\n", calls)
    assert hardware.detect_gpu_vram([]) == {"NVIDIA GeForce RTX 3080": 10240}
    assert any("memory.total" in part for part in calls[0])


# ------------------------------------------------------------ décision


def test_base_model_does_not_fit_in_the_free_vram_of_a_shared_card():
    layers, why = hardware.plan_gpu_layers(99, 2432, 3349, "fr")
    assert layers == 0
    assert "3349" in why and "2432" in why and "processeur" in why


def test_small_model_fits_in_the_free_vram_of_a_shared_card():
    assert hardware.plan_gpu_layers(99, 223, 3349, "fr") == (99, "")


def test_unknown_free_vram_changes_nothing():
    """Metal (mémoire unifiée), AMD, Intel : aucune mesure de VRAM libre, comportement d'avant."""
    assert hardware.plan_gpu_layers(99, 2432, None, "fr") == (99, "")


def test_cpu_profile_stays_on_cpu_without_message():
    assert hardware.plan_gpu_layers(0, 2432, 100, "fr") == (0, "")


def test_reason_is_in_the_configured_language():
    assert "CPU" in hardware.plan_gpu_layers(99, 2432, 3349, "en")[1]


def test_effective_layers_use_the_model_size_and_the_free_vram(monkeypatch, tmp_path):
    _fake_smi(monkeypatch, SMI_FREE)
    cfg = Config(model=_model(tmp_path, 2432), llm_gpu_layers=99)
    assert hardware.effective_gpu_layers(cfg)[0] == 0
    cfg = Config(model=_model(tmp_path, 223), llm_gpu_layers=99)
    assert hardware.effective_gpu_layers(cfg) == (99, "")


def test_fit_check_can_be_turned_off(monkeypatch, tmp_path):
    _fake_smi(monkeypatch, SMI_FREE)
    cfg = Config(model=_model(tmp_path, 2432), llm_gpu_layers=99, llm_gpu_fit_check=False)
    assert hardware.effective_gpu_layers(cfg) == (99, "")


def test_missing_model_file_changes_nothing(monkeypatch, tmp_path):
    _fake_smi(monkeypatch, SMI_FREE)
    cfg = Config(model=str(tmp_path / "absent.gguf"), llm_gpu_layers=99)
    assert hardware.effective_gpu_layers(cfg) == (99, "")


# ------------------------------------------------------------ lancement et choix


def test_server_command_falls_back_to_cpu_when_the_model_does_not_fit(monkeypatch, tmp_path):
    _fake_smi(monkeypatch, SMI_FREE)
    args = _build_args(Config(model=_model(tmp_path, 2432), llm_gpu_layers=99), "/x/llama-server")
    assert args[args.index("-ngl") + 1] == "0"


def test_server_command_keeps_the_gpu_when_the_model_fits(monkeypatch, tmp_path):
    _fake_smi(monkeypatch, SMI_FREE)
    args = _build_args(Config(model=_model(tmp_path, 223), llm_gpu_layers=99), "/x/llama-server")
    assert args[args.index("-ngl") + 1] == "99"


def test_speed_measure_runs_on_cpu_when_the_model_does_not_fit(monkeypatch, tmp_path):
    _fake_smi(monkeypatch, SMI_FREE)
    launched = []

    class Proc:
        def poll(self):
            return None

        def terminate(self): ...

        def wait(self, timeout=None):
            return 0

    speed.measure_prompt_speed(Config(llm_gpu_layers=99), _model(tmp_path, 2432),
                               launch=lambda args, env: launched.append(args) or Proc(),
                               healthy=lambda p: True, post=lambda *a: {"timings": {"prompt_per_second": 5}})
    assert launched[0][launched[0].index("-ngl") + 1] == "0"


def test_machine_reports_free_vram_not_total(monkeypatch):
    monkeypatch.setattr(hardware, "detect_cpu", lambda: hardware.CpuInfo(physical_cores=6))
    monkeypatch.setattr(hardware, "detect_memory", lambda: hardware.MemoryInfo(total_mb=64000))
    monkeypatch.setattr(hardware, "detect_gpus_cached",
                        lambda *a, **k: [Gpu(vendor="nvidia", kind="dedicated", name="RTX 3080")])

    def fake(gpus, free=False):
        return {"RTX 3080": 3349 if free else 10240}

    monkeypatch.setattr(hardware, "detect_gpu_vram", fake)
    assert round(catalog.detect_machine().vram_gb, 1) == 3.3


# ------------------------------------------------------------ verdict du setup


def _models(tmp_path):
    from test_speed import _base, _small  # noqa: E402
    return _small(tmp_path), _base(tmp_path)


def test_gpu_speed_measured_on_the_small_model_does_not_promise_the_base_model(tmp_path):
    small, base = _models(tmp_path)
    verdict = speed.assess([small, base], small, 2000.0, gpu=True, vram_blocked=True)
    assert verdict.recommended is small and not verdict.fast
    assert verdict.reason == "vram"
    assert "Mémoire" in speed.message(verdict, "fr") and "GPU" in speed.message(verdict, "fr")


def test_vram_not_blocked_keeps_the_speed_verdict(tmp_path):
    small, base = _models(tmp_path)
    assert speed.assess([small, base], small, 2000.0, gpu=True).recommended is base
