"""Détection GPU : parsing de `llama-bench --list-devices`, complétion pci_id, cache."""

import subprocess

from steph import hardware
from steph.hardware import (
    Gpu,
    _complete_pci_ids,
    _parse_cuda,
    _parse_metal,
    _parse_vulkan,
    detect_gpus,
    detect_gpus_cached,
)

VULKAN_INTEGRATED = (
    "ggml_vulkan: 0 = Intel(R) Graphics (ARL) (Intel open-source Mesa driver) "
    "| uma: 1 | fp16: 1 | warp size: 32\n"
)
VULKAN_DEDICATED = "ggml_vulkan: 0 = NVIDIA GeForce RTX 3060 (NVIDIA) | uma: 0 | fp16: 1 | warp size: 32\n"
CUDA_OUTPUT = (
    "ggml_cuda_init: found 1 CUDA devices:\n"
    "  Device 0: NVIDIA GeForce RTX 3060, compute capability 8.6, VMM: yes\n"
)
METAL_OUTPUT = "ggml_metal_init: found device: Apple M2 Pro\n"


class _FakeResult:
    def __init__(self, stdout: str = "", stderr: str = ""):
        self.stdout = stdout
        self.stderr = stderr


# ---------------------------------------------------------------- parsing


def test_parse_vulkan_integrated_is_intel_uma():
    gpus = _parse_vulkan(VULKAN_INTEGRATED)
    assert gpus == [
        Gpu(vendor="intel", kind="integrated", name="Intel(R) Graphics (ARL) (Intel open-source Mesa driver)")
    ]


def test_parse_vulkan_dedicated_is_not_uma():
    gpus = _parse_vulkan(VULKAN_DEDICATED)
    assert gpus[0].kind == "dedicated"
    assert gpus[0].vendor == "nvidia"


def test_parse_vulkan_empty_output():
    assert _parse_vulkan("rien à voir ici\n") == []


def test_parse_cuda():
    assert _parse_cuda(CUDA_OUTPUT) == [Gpu(vendor="nvidia", kind="dedicated", name="NVIDIA GeForce RTX 3060")]


def test_parse_cuda_empty_output():
    assert _parse_cuda("") == []


def test_parse_metal_reads_apple_chip_name():
    assert _parse_metal(METAL_OUTPUT) == [Gpu(vendor="apple", kind="apple", name="Apple M2 Pro")]


def test_parse_metal_empty_output():
    assert _parse_metal("rien à voir ici\n") == []


# --------------------------------------------------------- complétion pci_id


def test_complete_pci_ids_single_vendor_match(tmp_path):
    device = tmp_path / "card0" / "device"
    device.mkdir(parents=True)
    (device / "vendor").write_text("0x8086\n")
    (device / "device").write_text("0x7d51\n")
    gpus = [Gpu(vendor="intel", kind="integrated", name="Intel(R) Graphics (ARL)")]
    _complete_pci_ids(gpus, tmp_path)
    assert gpus[0].pci_id == "8086:7d51"


def test_complete_pci_ids_no_matching_vendor_leaves_none(tmp_path):
    gpus = [Gpu(vendor="nvidia", kind="dedicated", name="NVIDIA GeForce RTX 3060")]
    _complete_pci_ids(gpus, tmp_path)
    assert gpus[0].pci_id is None


def test_complete_pci_ids_ambiguous_same_vendor_leaves_none(tmp_path):
    for i, dev in enumerate(["0x7d51", "0x7d55"]):
        device = tmp_path / f"card{i}" / "device"
        device.mkdir(parents=True)
        (device / "vendor").write_text("0x8086\n")
        (device / "device").write_text(f"{dev}\n")
    gpus = [Gpu(vendor="intel", kind="integrated", name="Intel(R) Graphics (ARL)")]
    _complete_pci_ids(gpus, tmp_path)
    assert gpus[0].pci_id is None


# ---------------------------------------------------------------- detect_gpus


def test_detect_gpus_never_raises_when_binary_missing(monkeypatch):
    # hors Apple Silicon : sinon le repli Metal détecterait la vraie machine
    monkeypatch.setattr(hardware.platform, "system", lambda: "Linux")
    monkeypatch.setattr(hardware.shutil, "which", lambda name: None)
    assert detect_gpus("/nonexistent/llama-server") == []


def test_detect_gpus_never_raises_on_subprocess_error(monkeypatch):
    def boom(*a, **kw):
        raise subprocess.TimeoutExpired(cmd="llama-bench", timeout=15)

    monkeypatch.setattr(hardware.platform, "system", lambda: "Linux")
    monkeypatch.setattr(hardware, "_llama_bench_path", lambda path: "/fake/llama-bench")
    monkeypatch.setattr(hardware.subprocess, "run", boom)
    assert detect_gpus("/fake/llama-server") == []


def test_detect_gpus_parses_vulkan_output(monkeypatch):
    monkeypatch.setattr(hardware, "_llama_bench_path", lambda path: "/fake/llama-bench")
    monkeypatch.setattr(hardware.platform, "system", lambda: "Windows")
    monkeypatch.setattr(hardware.subprocess, "run", lambda *a, **kw: _FakeResult(VULKAN_DEDICATED))
    gpus = detect_gpus("/fake/llama-server")
    assert gpus == [Gpu(vendor="nvidia", kind="dedicated", name="NVIDIA GeForce RTX 3060 (NVIDIA)")]


def test_detect_gpus_apple_fallback_when_no_bench(monkeypatch):
    monkeypatch.setattr(hardware, "_llama_bench_path", lambda path: None)
    monkeypatch.setattr(hardware.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(hardware.platform, "machine", lambda: "arm64")
    monkeypatch.setattr(hardware.subprocess, "run", lambda *a, **kw: _FakeResult("Apple M2 Pro\n"))
    assert detect_gpus("/whatever/llama-server") == [Gpu(vendor="apple", kind="apple", name="Apple M2 Pro")]


def test_detect_gpus_completes_pci_id_on_linux(tmp_path, monkeypatch):
    monkeypatch.setattr(hardware, "_llama_bench_path", lambda path: "/fake/llama-bench")
    monkeypatch.setattr(hardware.platform, "system", lambda: "Linux")
    monkeypatch.setattr(hardware.subprocess, "run", lambda *a, **kw: _FakeResult(VULKAN_INTEGRATED))
    device = tmp_path / "card0" / "device"
    device.mkdir(parents=True)
    (device / "vendor").write_text("0x8086\n")
    (device / "device").write_text("0x7d51\n")
    gpus = detect_gpus("/fake/llama-server", sysfs_root=tmp_path)
    assert gpus[0].pci_id == "8086:7d51"


# ------------------------------------------------------------------- cache


def test_detect_gpus_cached_avoids_second_subprocess_call(tmp_path, monkeypatch):
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        return _FakeResult(VULKAN_DEDICATED)

    monkeypatch.setattr(hardware, "_llama_bench_path", lambda path: "/fake/llama-bench")
    monkeypatch.setattr(hardware.subprocess, "run", fake_run)
    cache = tmp_path / "hardware.json"
    g1 = detect_gpus_cached("/fake/llama-server", cache_path=cache)
    g2 = detect_gpus_cached("/fake/llama-server", cache_path=cache)
    assert len(calls) == 1
    assert g1 == g2 == [Gpu(vendor="nvidia", kind="dedicated", name="NVIDIA GeForce RTX 3060 (NVIDIA)")]


def test_detect_gpus_cached_invalidated_when_llama_server_path_changes(tmp_path, monkeypatch):
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        return _FakeResult(VULKAN_DEDICATED)

    monkeypatch.setattr(hardware, "_llama_bench_path", lambda path: "/fake/llama-bench")
    monkeypatch.setattr(hardware.subprocess, "run", fake_run)
    cache = tmp_path / "hardware.json"
    detect_gpus_cached("/fake/llama-server-a", cache_path=cache)
    detect_gpus_cached("/fake/llama-server-b", cache_path=cache)
    assert len(calls) == 2
