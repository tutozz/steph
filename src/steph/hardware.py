"""Détection GPU pour choisir automatiquement un profil matériel (voir profile.py).

Source principale : `llama-bench --list-devices`, binaire voisin de llama-server.
Ne lève jamais d'exception vers l'appelant : en cas d'échec, la liste est vide
(profil cpu)."""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

from .config import RUNTIME_DIR

CACHE_PATH = RUNTIME_DIR / "hardware.json"

_VENDOR_HEX = {"intel": "0x8086", "amd": "0x1002", "nvidia": "0x10de"}


@dataclass
class Gpu:
    vendor: str  # "nvidia" | "amd" | "intel" | "apple" | "other"
    kind: str  # "dedicated" | "integrated" | "apple"
    name: str
    pci_id: str | None = None


def _vendor_from_name(name: str) -> str:
    n = name.lower()
    if "intel" in n:
        return "intel"
    if "amd" in n or "radeon" in n:
        return "amd"
    if "nvidia" in n or "geforce" in n or "quadro" in n or "rtx" in n:
        return "nvidia"
    return "other"


def _parse_vulkan(output: str) -> list[Gpu]:
    gpus = []
    for line in output.splitlines():
        m = re.search(r"ggml_vulkan:\s*\d+\s*=\s*(.+?)\s*\|\s*uma:\s*(\d)", line)
        if not m:
            continue
        name = m.group(1).strip()
        kind = "integrated" if m.group(2) == "1" else "dedicated"
        gpus.append(Gpu(vendor=_vendor_from_name(name), kind=kind, name=name))
    return gpus


def _parse_cuda(output: str) -> list[Gpu]:
    gpus = []
    for line in output.splitlines():
        m = re.search(r"Device\s+\d+:\s*(.+?),\s*compute capability", line)
        if m:
            gpus.append(Gpu(vendor="nvidia", kind="dedicated", name=m.group(1).strip()))
    return gpus


def _parse_metal(output: str) -> list[Gpu]:
    for line in output.splitlines():
        if "ggml_metal" in line:
            m = re.search(r"Apple\s+M\d(?:\s+(?:Pro|Max|Ultra))?", line)
            if m:
                return [Gpu(vendor="apple", kind="apple", name=m.group(0))]
    return []


def _detect_apple_fallback() -> list[Gpu]:
    """Format Metal exact incertain : sur Apple Silicon, on suppose un GPU intégré."""
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        return []
    try:
        r = subprocess.run(
            ["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True, text=True, timeout=5
        )
        name = (r.stdout or "").strip()
    except (OSError, subprocess.SubprocessError):
        name = ""
    return [Gpu(vendor="apple", kind="apple", name=name or "Apple Silicon")]


def _complete_pci_ids(gpus: list[Gpu], sysfs_root: Path) -> None:
    """Complète pci_id (Linux) via /sys/class/drm/card*/device/{vendor,device}.
    N'associe que si un seul GPU du même vendeur est présent."""
    by_vendor: dict[str, list[str]] = {}
    for device_dir in sorted(sysfs_root.glob("card*/device")):
        vfile, dfile = device_dir / "vendor", device_dir / "device"
        if not (vfile.exists() and dfile.exists()):
            continue
        try:
            vhex, dhex = vfile.read_text().strip(), dfile.read_text().strip()
        except OSError:
            continue
        for vendor, h in _VENDOR_HEX.items():
            if vhex == h:
                by_vendor.setdefault(vendor, []).append(f"{vhex[2:]}:{dhex[2:]}")
    for gpu in gpus:
        ids = by_vendor.get(gpu.vendor)
        if ids and len(ids) == 1:
            gpu.pci_id = ids[0]


def _llama_bench_path(llama_server_path: str) -> str | None:
    cand = Path(llama_server_path).parent / "llama-bench"
    if cand.exists():
        return str(cand)
    return shutil.which("llama-bench")


def _run_llama_bench(bench_path: str) -> str:
    exe = Path(bench_path)
    env = dict(os.environ)
    if exe.parent.name.startswith("llama-") or exe.parent.name == "bin":
        for var in ("LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH"):
            env[var] = f"{exe.parent}:{env.get(var, '')}"
    r = subprocess.run([bench_path, "--list-devices"], capture_output=True, text=True, timeout=15, env=env)
    return (r.stdout or "") + (r.stderr or "")


def _detect_gpus(llama_server_path: str, sysfs_root: Path | None) -> list[Gpu]:
    bench = _llama_bench_path(llama_server_path)
    output = ""
    if bench:
        try:
            output = _run_llama_bench(bench)
        except (OSError, subprocess.SubprocessError):
            output = ""
    gpus = _parse_cuda(output) or _parse_vulkan(output) or _parse_metal(output)
    if not gpus:
        gpus = _detect_apple_fallback()
    if gpus and platform.system() == "Linux":
        _complete_pci_ids(gpus, sysfs_root or Path("/sys/class/drm"))
    return gpus


def detect_gpus(llama_server_path: str, sysfs_root: Path | None = None) -> list[Gpu]:
    """Détecte les GPU disponibles pour llama.cpp. Jamais d'exception : aucun
    GPU trouvé ou erreur -> liste vide (profil cpu)."""
    try:
        return _detect_gpus(llama_server_path, sysfs_root)
    except Exception:
        return []


@dataclass
class CpuInfo:
    physical_cores: int | None = None
    logical_cores: int | None = None
    avx2: bool = False
    avx512: bool = False
    avx_vnni: bool = False
    amx: bool = False


@dataclass
class MemoryInfo:
    total_mb: int | None = None
    available_mb: int | None = None


def parse_cpuinfo_linux(text: str) -> CpuInfo:
    """Parse /proc/cpuinfo : un bloc par cœur logique, séparés par une ligne vide.
    Cœurs physiques : somme de « cpu cores » par « physical id » ; sans ce champ
    (VM, ARM), on suppose l'absence d'hyperthreading."""
    blocks = [b for b in text.split("\n\n") if b.strip()]
    per_package: dict[str, int] = {}
    flags: set[str] = set()
    for block in blocks:
        fields: dict[str, str] = {}
        for line in block.splitlines():
            key, sep, value = line.partition(":")
            if sep:
                fields[key.strip()] = value.strip()
        if "flags" in fields and not flags:
            flags = set(fields["flags"].split())
        cores = fields.get("cpu cores")
        if cores and cores.isdigit():
            per_package[fields.get("physical id", "0")] = int(cores)
    logical = len(blocks) or None
    physical = sum(per_package.values()) if per_package else logical
    return CpuInfo(
        physical_cores=physical,
        logical_cores=logical,
        avx2="avx2" in flags,
        avx512=any(f.startswith("avx512") for f in flags),
        avx_vnni="avx_vnni" in flags,
        amx=any(f.startswith("amx") for f in flags),
    )


def parse_meminfo_linux(text: str) -> MemoryInfo:
    """Parse /proc/meminfo (valeurs en kB)."""
    values: dict[str, int] = {}
    for line in text.splitlines():
        m = re.match(r"(\w+):\s*(\d+)\s*kB", line)
        if m:
            values[m.group(1)] = int(m.group(2))
    total, available = values.get("MemTotal"), values.get("MemAvailable")
    return MemoryInfo(
        total_mb=total // 1024 if total is not None else None,
        available_mb=available // 1024 if available is not None else None,
    )


def parse_sysctl_macos_cpu(text: str) -> CpuInfo:
    """Parse la sortie de `sysctl machdep.cpu hw.physicalcpu hw.logicalcpu`."""
    values: dict[str, str] = {}
    for line in text.splitlines():
        key, sep, value = line.partition(":")
        if sep:
            values[key.strip()] = value.strip()
    flags = {f.lower() for f in (values.get("machdep.cpu.features", "").split()
                                  + values.get("machdep.cpu.leaf7_features", "").split())}

    def as_int(key: str) -> int | None:
        v = values.get(key)
        return int(v) if v and v.isdigit() else None

    return CpuInfo(
        physical_cores=as_int("hw.physicalcpu"),
        logical_cores=as_int("hw.logicalcpu"),
        avx2="avx2" in flags,
        avx512=any(f.startswith("avx512") for f in flags),
        avx_vnni="avx_vnni" in flags or "avxvnni" in flags,
        amx=any(f.startswith("amx") for f in flags),
    )


def parse_vm_stat_macos(text: str, total_bytes: int, page_size: int = 4096) -> MemoryInfo:
    """Parse `vm_stat` : mémoire disponible approchée par libre + inactive + spéculative,
    l'estimation usuelle sur macOS en l'absence d'un équivalent de MemAvailable."""
    pages: dict[str, int] = {}
    for line in text.splitlines():
        m = re.match(r"Pages ([\w ]+?):\s*(\d+)\.?\s*$", line)
        if m:
            pages[m.group(1).strip()] = int(m.group(2))
    free = pages.get("free", 0) + pages.get("inactive", 0) + pages.get("speculative", 0)
    available = free * page_size
    return MemoryInfo(
        total_mb=total_bytes // (1024 * 1024) if total_bytes else None,
        available_mb=available // (1024 * 1024) if available else None,
    )


def parse_nvidia_smi_vram(text: str) -> dict[str, int]:
    """Parse `nvidia-smi --query-gpu=name,memory.total --format=csv,noheader,nounits`."""
    vram: dict[str, int] = {}
    for line in text.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) == 2 and parts[1].isdigit():
            vram[parts[0]] = int(parts[1])
    return vram


def detect_cpu() -> CpuInfo:
    """Cœurs et drapeaux CPU. Jamais d'exception : échec ou plateforme inconnue -> valeurs vides."""
    try:
        if platform.system() == "Linux":
            return parse_cpuinfo_linux(Path("/proc/cpuinfo").read_text())
        if platform.system() == "Darwin":
            r = subprocess.run(["sysctl", "machdep.cpu", "hw.physicalcpu", "hw.logicalcpu"],
                                capture_output=True, text=True, timeout=5)
            return parse_sysctl_macos_cpu(r.stdout)
    except (OSError, subprocess.SubprocessError):
        pass
    return CpuInfo()


def detect_memory() -> MemoryInfo:
    """RAM totale et disponible. Jamais d'exception : échec ou plateforme inconnue -> valeurs vides."""
    try:
        if platform.system() == "Linux":
            return parse_meminfo_linux(Path("/proc/meminfo").read_text())
        if platform.system() == "Darwin":
            total = subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, timeout=5)
            page = subprocess.run(["sysctl", "-n", "hw.pagesize"], capture_output=True, text=True, timeout=5)
            vm = subprocess.run(["vm_stat"], capture_output=True, text=True, timeout=5)
            return parse_vm_stat_macos(vm.stdout, int(total.stdout.strip() or 0), int(page.stdout.strip() or 4096))
    except (OSError, subprocess.SubprocessError, ValueError):
        pass
    return MemoryInfo()


def detect_gpu_vram(gpus: list[Gpu]) -> dict[str, int]:
    """VRAM par GPU en Mo : nvidia-smi si présent, mémoire unifiée pour Apple, sinon rien."""
    smi = shutil.which("nvidia-smi")
    if smi:
        try:
            r = subprocess.run([smi, "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                                capture_output=True, text=True, timeout=5)
            vram = parse_nvidia_smi_vram(r.stdout)
            if vram:
                return vram
        except (OSError, subprocess.SubprocessError):
            pass
    apple = [g for g in gpus if g.vendor == "apple"]
    if apple:
        mem = detect_memory()
        if mem.total_mb:
            return {g.name: mem.total_mb for g in apple}
    return {}


def detect_gpus_cached(
    llama_server_path: str, sysfs_root: Path | None = None, cache_path: Path | None = None
) -> list[Gpu]:
    """Comme detect_gpus, avec un cache JSON invalidé dès que llama_server_path change."""
    cache_path = cache_path or CACHE_PATH
    try:
        if cache_path.exists():
            data = json.loads(cache_path.read_text())
            if data.get("llama_server") == llama_server_path:
                return [Gpu(**g) for g in data["gpus"]]
    except (OSError, ValueError, TypeError, KeyError):
        pass
    gpus = detect_gpus(llama_server_path, sysfs_root)
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps({"llama_server": llama_server_path, "gpus": [asdict(g) for g in gpus]}))
    except OSError:
        pass
    return gpus
