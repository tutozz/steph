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
