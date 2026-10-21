"""Sélection du profil matériel : score de correspondance GPU <-> fichier .toml, précédence."""

import argparse
from pathlib import Path

from steph import cli, config as config_module
from steph import profile as profile_module
from steph.config import Config
from steph.hardware import Gpu
from steph.profile import Profile, load_profiles, select_profile


def _write(base: Path, name: str, content: str) -> None:
    p = base / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)


# ------------------------------------------------------------------ parsing


def test_load_profiles_parses_match_and_settings(tmp_path):
    _write(tmp_path, "cpu.toml", '[match]\nkind = "cpu"\n\n[settings]\nllm_gpu_layers = 0\n')
    profiles = load_profiles(tmp_path)
    assert len(profiles) == 1
    assert isinstance(profiles[0], Profile)
    assert profiles[0].match == {"kind": "cpu"}
    assert profiles[0].settings == {"llm_gpu_layers": 0}


def test_load_profiles_ignores_unparsable_file(tmp_path):
    _write(tmp_path, "broken.toml", "ceci n'est pas du toml [[[")
    assert load_profiles(tmp_path) == []


# ------------------------------------------------------------------ scoring


def test_pci_id_beats_vendor_and_kind(tmp_path):
    _write(tmp_path, "vendor_kind.toml", '[match]\nvendor = "intel"\nkind = "integrated"\n[settings]\nllm_batch = 1\n')
    _write(tmp_path, "gpu/by_pci.toml", '[match]\npci_ids = ["8086:7d51"]\n[settings]\nllm_batch = 2\n')
    gpu = Gpu(vendor="intel", kind="integrated", name="Intel Graphics", pci_id="8086:7d51")
    prof, warnings = select_profile([gpu], tmp_path)
    assert prof.settings["llm_batch"] == 2
    assert warnings == []


def test_dedicated_beats_integrated_at_equal_score(tmp_path):
    _write(tmp_path, "integrated.toml", '[match]\nkind = "integrated"\n[settings]\nllm_batch = 1\n')
    _write(tmp_path, "dedicated.toml", '[match]\nkind = "dedicated"\n[settings]\nllm_batch = 2\n')
    igpu = Gpu(vendor="intel", kind="integrated", name="Intel Graphics")
    dgpu = Gpu(vendor="nvidia", kind="dedicated", name="NVIDIA GeForce RTX 3060")
    prof, _ = select_profile([igpu, dgpu], tmp_path)
    assert prof.settings["llm_batch"] == 2


def test_no_gpu_selects_cpu_profile(tmp_path):
    _write(tmp_path, "cpu.toml", '[match]\nkind = "cpu"\n[settings]\nllm_gpu_layers = 0\n')
    _write(tmp_path, "dedicated.toml", '[match]\nkind = "dedicated"\n[settings]\n')
    prof, _ = select_profile([], tmp_path)
    assert prof.settings["llm_gpu_layers"] == 0


def test_no_gpu_and_no_cpu_profile_returns_none(tmp_path):
    _write(tmp_path, "dedicated.toml", '[match]\nkind = "dedicated"\n[settings]\n')
    prof, _ = select_profile([], tmp_path)
    assert prof is None


def test_unknown_setting_key_ignored_and_reported(tmp_path):
    _write(tmp_path, "cpu.toml", '[match]\nkind = "cpu"\n[settings]\nllm_batch = 4\nnonexistent_field = 1\n')
    prof, warnings = select_profile([], tmp_path)
    assert "nonexistent_field" not in prof.settings
    assert prof.settings["llm_batch"] == 4
    assert any("nonexistent_field" in w for w in warnings)


def test_no_matching_profile_returns_none(tmp_path):
    _write(tmp_path, "gpu/amd_only.toml", '[match]\nvendor = "amd"\n[settings]\n')
    gpu = Gpu(vendor="intel", kind="dedicated", name="Intel Arc")
    prof, _ = select_profile([gpu], tmp_path)
    assert prof is None


def test_name_glob_is_case_insensitive(tmp_path):
    _write(tmp_path, "gpu/rtx.toml", '[match]\nname = "*rtx 3060*"\n[settings]\nllm_batch = 9\n')
    gpu = Gpu(vendor="nvidia", kind="dedicated", name="NVIDIA GeForce RTX 3060")
    prof, _ = select_profile([gpu], tmp_path)
    assert prof.settings["llm_batch"] == 9


# ---------------------------------------------------------- précédence globale


def test_precedence_profile_below_config_toml_below_env(tmp_path, monkeypatch):
    profiles_dir = tmp_path / "profiles"
    _write(profiles_dir, "cpu.toml", '[match]\nkind = "cpu"\n[settings]\nllm_batch = 256\n')
    monkeypatch.setattr(profile_module, "PROFILES_DIR", profiles_dir)
    monkeypatch.setattr(profile_module, "detect_gpus_cached", lambda llama_server_path, **kw: [])

    config_toml = tmp_path / "config.toml"
    monkeypatch.setattr(config_module, "CONFIG_PATH", config_toml)

    cfg = config_module.load_config(apply_profile=True)
    assert cfg.llm_batch == 256  # défaut (512) battu par le profil

    config_toml.write_text("llm_batch = 1024\n")
    cfg = config_module.load_config(apply_profile=True)
    assert cfg.llm_batch == 1024  # config.toml bat le profil

    monkeypatch.setenv("STEPH_LLM_BATCH", "2048")
    cfg = config_module.load_config(apply_profile=True)
    assert cfg.llm_batch == 2048  # env bat tout


def test_apply_profile_false_skips_detection_entirely(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(profile_module, "detect_gpus_cached", lambda *a, **kw: calls.append(1) or [])
    monkeypatch.setattr(config_module, "CONFIG_PATH", tmp_path / "absent.toml")
    config_module.load_config(apply_profile=False)
    assert calls == []


def test_forced_profile_by_name(tmp_path, monkeypatch):
    profiles_dir = tmp_path / "profiles"
    _write(profiles_dir, "gpu/intel-arc-140t.toml", '[match]\nvendor = "intel"\npci_ids = ["8086:7d51"]\n[settings]\nllm_batch = 7\n')
    monkeypatch.setattr(profile_module, "PROFILES_DIR", profiles_dir)
    cfg = Config()
    cfg.hardware_profile = "gpu/intel-arc-140t"
    prof, gpus, warnings = profile_module.apply_hardware_profile(cfg)
    assert prof is not None
    assert cfg.llm_batch == 7
    assert gpus == []
    assert warnings == []


def test_hardware_profile_none_disables_detection_and_settings(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(profile_module, "detect_gpus_cached", lambda *a, **kw: calls.append(1) or [])
    cfg = Config()
    cfg.hardware_profile = "none"
    prof, gpus, warnings = profile_module.apply_hardware_profile(cfg)
    assert prof is None
    assert gpus == []
    assert warnings == []
    assert calls == []


# ------------------------------------------------------------------- cmd_profile


def test_cmd_profile_runs_and_prints_command_line(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "load_config", lambda apply_profile=False: Config())
    monkeypatch.setattr("steph.hardware.detect_gpus_cached", lambda *a, **kw: [])
    assert cli.cmd_profile(argparse.Namespace()) == 0
    out = capsys.readouterr().out
    assert "GPU détectés" in out
    assert "Commande llama-server" in out
    assert "llama-server" in out or "-m" in out
