"""Installation hors d'un clone (wheel PyPI, Homebrew) : pas de chemin de dépôt inventé."""

from steph import config


def test_project_dir_found_in_clone(tmp_path):
    (tmp_path / "pyproject.toml").write_text("")
    (tmp_path / "src" / "steph").mkdir(parents=True)
    assert config.find_project_dir(tmp_path / "src" / "steph" / "config.py") == tmp_path


def test_project_dir_none_in_site_packages(tmp_path):
    pkg = tmp_path / "lib" / "python3.13" / "site-packages" / "steph"
    pkg.mkdir(parents=True)
    assert config.find_project_dir(pkg / "config.py") is None


def test_llama_server_lookup_without_project_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "PROJECT_DIR", None)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.delenv("STEPH_LLAMA_SERVER", raising=False)
    assert config._find_llama_server()  # ne plante pas, retombe sur le PATH


def test_python_is_capped_below_versions_without_onnxruntime_wheels():
    """uv choisit le Python le plus récent : sans plafond, il prend 3.15 et piper-tts ne s'installe pas."""
    import tomllib
    from pathlib import Path
    spec = tomllib.loads((Path(__file__).resolve().parents[1] / "pyproject.toml").read_text())
    assert "<3.15" in spec["project"]["requires-python"].replace(" ", "")
