"""Détection étendue du matériel : cœurs, RAM, drapeaux CPU, VRAM par GPU.

Chaque source (`/proc/cpuinfo`, `/proc/meminfo`, `sysctl`, `vm_stat`, `nvidia-smi`) a une
fonction pure qui parse un texte enregistré, séparée de la fonction qui lance la commande.
"""

from steph.hardware import (
    Gpu,
    parse_cpuinfo_linux,
    parse_meminfo_linux,
    parse_nvidia_smi_vram,
    parse_sysctl_macos_cpu,
    parse_vm_stat_macos,
)


def _cpuinfo_block(n: int, physical_id: str, cpu_cores: str, flags: str) -> str:
    return (
        f"processor\t: {n}\n"
        "vendor_id\t: GenuineIntel\n"
        f"physical id\t: {physical_id}\n"
        f"cpu cores\t: {cpu_cores}\n"
        f"flags\t\t: {flags}\n"
    )


# ---------------------------------------------------------------- /proc/cpuinfo (Linux)

def test_cpuinfo_counts_physical_and_logical_cores_with_hyperthreading():
    """6 cœurs, 12 threads (HT) sur un seul socket : un bloc par thread logique."""
    flags = "fpu vme de pse tsc msr pae mce cx8 apic avx2 bmi1 bmi2"
    text = "\n".join(_cpuinfo_block(n, "0", "6", flags) for n in range(12))
    info = parse_cpuinfo_linux(text)
    assert (info.physical_cores, info.logical_cores) == (6, 12)
    assert info.avx2 is True
    assert info.avx512 is False
    assert info.avx_vnni is False
    assert info.amx is False


def test_cpuinfo_counts_cores_across_two_physical_packages():
    text = "\n".join(_cpuinfo_block(n, str(n // 4), "4", "fpu avx2") for n in range(8))
    info = parse_cpuinfo_linux(text)
    assert (info.physical_cores, info.logical_cores) == (8, 8)


def test_cpuinfo_detects_avx512_avx_vnni_and_amx_sapphire_rapids():
    flags = "fpu avx2 avx512f avx512dq avx512cd avx512bw avx512vl avx_vnni amx_bf16 amx_tile amx_int8"
    text = _cpuinfo_block(0, "0", "1", flags)
    info = parse_cpuinfo_linux(text)
    assert info.avx512 is True
    assert info.avx_vnni is True
    assert info.amx is True


def test_cpuinfo_without_cpu_cores_field_falls_back_to_logical_count():
    """VM ou ARM sans champ « cpu cores » : on suppose pas d'hyperthreading."""
    block = "processor\t: {n}\nvendor_id\t: GenuineARM\nflags\t\t: fpu\n"
    text = "\n".join(block.format(n=n) for n in range(4))
    info = parse_cpuinfo_linux(text)
    assert (info.physical_cores, info.logical_cores) == (4, 4)


# ---------------------------------------------------------------- /proc/meminfo (Linux)

MEMINFO = """MemTotal:       32869540 kB
MemFree:         3456789 kB
MemAvailable:   20971520 kB
Buffers:          123456 kB
Cached:          8765432 kB
"""


def test_meminfo_converts_kb_to_mb():
    info = parse_meminfo_linux(MEMINFO)
    assert (info.total_mb, info.available_mb) == (32099, 20480)


def test_meminfo_missing_fields_are_none():
    info = parse_meminfo_linux("SomeOtherField: 123 kB\n")
    assert (info.total_mb, info.available_mb) == (None, None)


# ---------------------------------------------------------------- sysctl machdep.cpu (macOS)

SYSCTL_INTEL_MAC = """hw.physicalcpu: 6
hw.logicalcpu: 12
machdep.cpu.brand_string: Intel(R) Core(TM) i7-9750H CPU @ 2.60GHz
machdep.cpu.features: FPU VME DE PSE TSC MSR PAE MCE CX8 APIC SSE3 AVX1.0 RDRAND F16C
machdep.cpu.leaf7_features: RDWRFSGS BMI1 AVX2 SMEP BMI2 ERMS AVX512F AVX512DQ AVX512CD AVX512BW AVX512VL
"""


def test_sysctl_macos_cpu_reads_core_counts_and_flags():
    info = parse_sysctl_macos_cpu(SYSCTL_INTEL_MAC)
    assert (info.physical_cores, info.logical_cores) == (6, 12)
    assert info.avx2 is True
    assert info.avx512 is True
    assert info.avx_vnni is False
    assert info.amx is False


def test_sysctl_macos_cpu_missing_keys_return_defaults():
    info = parse_sysctl_macos_cpu("machdep.cpu.brand_string: Apple M3 Pro\n")
    assert (info.physical_cores, info.logical_cores) == (None, None)
    assert (info.avx2, info.avx512, info.avx_vnni, info.amx) == (False, False, False, False)


# ---------------------------------------------------------------- vm_stat (macOS)

VM_STAT = """Mach Virtual Memory Statistics: (page size of 16384 bytes)
Pages free:                              200000.
Pages active:                            500000.
Pages inactive:                          300000.
Pages speculative:                       10000.
Pages wired down:                        400000.
Pages purgeable:                         5000.
"""


def test_vm_stat_macos_computes_available_from_free_inactive_and_speculative():
    info = parse_vm_stat_macos(VM_STAT, total_bytes=17179869184, page_size=16384)
    assert info.total_mb == 16384
    assert info.available_mb == 7968


def test_vm_stat_macos_without_total_bytes_leaves_total_none():
    info = parse_vm_stat_macos(VM_STAT, total_bytes=0, page_size=16384)
    assert info.total_mb is None


# ---------------------------------------------------------------- nvidia-smi (VRAM)

def test_nvidia_smi_vram_parses_single_gpu():
    vram = parse_nvidia_smi_vram("NVIDIA GeForce RTX 3060, 12288\n")
    assert vram == {"NVIDIA GeForce RTX 3060": 12288}


def test_nvidia_smi_vram_parses_multiple_gpus():
    vram = parse_nvidia_smi_vram("NVIDIA GeForce RTX 3060, 12288\nNVIDIA GeForce RTX 3080, 10240\n")
    assert vram == {"NVIDIA GeForce RTX 3060": 12288, "NVIDIA GeForce RTX 3080": 10240}


def test_nvidia_smi_vram_ignores_unparsable_lines():
    assert parse_nvidia_smi_vram("NVIDIA-SMI has failed because...\n") == {}


# ---------------------------------------------------------------- runners (best-effort)

def test_detect_cpu_never_raises_on_an_unknown_platform(monkeypatch):
    from steph import hardware

    monkeypatch.setattr(hardware.platform, "system", lambda: "FreeBSD")
    info = hardware.detect_cpu()
    assert (info.physical_cores, info.logical_cores) == (None, None)


def test_detect_memory_never_raises_on_an_unknown_platform(monkeypatch):
    from steph import hardware

    monkeypatch.setattr(hardware.platform, "system", lambda: "FreeBSD")
    info = hardware.detect_memory()
    assert (info.total_mb, info.available_mb) == (None, None)


def test_detect_gpu_vram_uses_unified_memory_for_apple_gpu(monkeypatch):
    from steph import hardware

    monkeypatch.setattr(hardware.shutil, "which", lambda name: None)
    monkeypatch.setattr(hardware, "detect_memory", lambda: hardware.MemoryInfo(total_mb=16384, available_mb=8000))
    gpus = [Gpu(vendor="apple", kind="apple", name="Apple M3 Pro")]
    assert hardware.detect_gpu_vram(gpus) == {"Apple M3 Pro": 16384}


def test_detect_gpu_vram_returns_empty_without_nvidia_smi_or_apple_gpu(monkeypatch):
    from steph import hardware

    monkeypatch.setattr(hardware.shutil, "which", lambda name: None)
    gpus = [Gpu(vendor="amd", kind="dedicated", name="Radeon RX 6800")]
    assert hardware.detect_gpu_vram(gpus) == {}
