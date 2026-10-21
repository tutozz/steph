"""Catalogue des modèles (point d'accroche B4) : niveau matériel et recommandation."""

import json
from pathlib import Path

import pytest

from steph import catalog

# schéma de docs/voice-bench/reference/options.json, source de vérité du futur catalogue B4
CATALOG = {
    "tiers": [
        {"id": "N1", "cpu_physical_cores_min": 1, "ram_gb_min": 4},
        {"id": "N2", "cpu_physical_cores_min": 2, "ram_gb_min": 4},
        {"id": "N3", "cpu_physical_cores_min": 4, "ram_gb_min": 8},
        {"id": "N4", "cpu_physical_cores_min": 6, "ram_gb_min": 8},
        {"id": "GPU", "vram_gb_min": 4},
    ],
    "recommended": {"N1": {"llm": "llm/small"}, "N3": {"llm": "llm/big"}, "GPU": {"llm": "llm/big"}},
    "options": [
        {"id": "llm/small", "kind": "llm", "label": "Petit", "file": "small.gguf", "size_mb": 533,
         "requires": {"cpu_physical_cores_min": 1, "ram_gb_min": 4}},
        {"id": "llm/big", "kind": "llm", "label": "Grand", "file": "big.gguf", "size_mb": 3300,
         "requires": {"cpu_physical_cores_min": 2, "ram_gb_min": 6}},
        {"id": "tts/x", "kind": "tts", "label": "Voix"},
    ],
}


def test_missing_catalog_is_empty(tmp_path):
    assert catalog.load_catalog(tmp_path / "absent.json") == {}
    assert catalog.llm_choices({}, tmp_path, catalog.Machine(4, 16, 0)) == []


def test_tier_follows_cores_ram_and_vram():
    assert catalog.detect_tier(CATALOG, catalog.Machine(1, 4, 0)) == "N1"
    assert catalog.detect_tier(CATALOG, catalog.Machine(4, 16, 0)) == "N3"
    assert catalog.detect_tier(CATALOG, catalog.Machine(8, 32, 0)) == "N4"
    assert catalog.detect_tier(CATALOG, catalog.Machine(4, 16, 8)) == "GPU"
    assert catalog.detect_tier(CATALOG, catalog.Machine(None, None, 0)) is None


def test_choices_mark_recommended_and_out_of_scope(tmp_path):
    choices = catalog.llm_choices(CATALOG, tmp_path, catalog.Machine(1, 4, 0))
    assert [c.label for c in choices] == ["Petit", "Grand"]
    small, big = choices
    assert small.recommended and not small.out_of_scope
    assert big.out_of_scope and not big.recommended
    assert small.path == str(tmp_path / "small.gguf")


def test_load_catalog_reads_json(tmp_path):
    p = tmp_path / "catalog.json"
    p.write_text(json.dumps(CATALOG))
    assert catalog.load_catalog(p)["tiers"][0]["id"] == "N1"


# ------------------------------------------------------------ B4 : requires.vram_gb_min bloque bien


VRAM_CATALOG = {
    "tiers": [{"id": "N1", "cpu_physical_cores_min": 1, "ram_gb_min": 4}, {"id": "GPU", "vram_gb_min": 4}],
    "recommended": {"N1": {"llm": "llm/small"}, "GPU": {"llm": "llm/gpu-only"}},
    "options": [
        {"id": "llm/small", "kind": "llm", "label": "Petit", "file": "small.gguf", "size_mb": 500,
         "requires": {"cpu_physical_cores_min": 1, "ram_gb_min": 4, "vram_gb_min": 0}},
        {"id": "llm/gpu-only", "kind": "llm", "label": "Gros GPU", "file": "gpu.gguf", "size_mb": 5000,
         "requires": {"cpu_physical_cores_min": 2, "ram_gb_min": 7, "vram_gb_min": 6}},
    ],
}


def test_fits_blocks_gpu_only_option_without_enough_vram():
    choices = catalog.llm_choices(VRAM_CATALOG, Path("/models"), catalog.Machine(8, 16, 0))
    small, gpu = choices
    assert not small.out_of_scope
    assert gpu.out_of_scope  # 0 Go de VRAM, requires vram_gb_min 6


def test_fits_allows_gpu_only_option_with_enough_vram():
    choices = catalog.llm_choices(VRAM_CATALOG, Path("/models"), catalog.Machine(8, 16, 8))
    _small, gpu = choices
    assert not gpu.out_of_scope


# ------------------------------------------------------------ B4/B6 : detect_machine lit la VRAM réelle


def test_detect_machine_reads_real_vram(monkeypatch):
    from steph import hardware

    monkeypatch.setattr(hardware, "detect_cpu", lambda: hardware.CpuInfo(physical_cores=4))
    monkeypatch.setattr(hardware, "detect_memory", lambda: hardware.MemoryInfo(total_mb=16384))
    gpu = hardware.Gpu(vendor="nvidia", kind="dedicated", name="RTX 3060")
    monkeypatch.setattr("steph.hardware.detect_gpus_cached", lambda *a, **k: [gpu])
    monkeypatch.setattr("steph.hardware.detect_gpu_vram", lambda gpus, free=False: {"RTX 3060": 12288})
    machine = catalog.detect_machine()
    assert machine.physical_cores == 4
    assert machine.ram_gb == 16.0
    assert machine.vram_gb == 12.0


def test_detect_machine_without_gpu_has_zero_vram(monkeypatch):
    from steph import hardware

    monkeypatch.setattr(hardware, "detect_cpu", lambda: hardware.CpuInfo(physical_cores=2))
    monkeypatch.setattr(hardware, "detect_memory", lambda: hardware.MemoryInfo(total_mb=8192))
    monkeypatch.setattr("steph.hardware.detect_gpus_cached", lambda *a, **k: [])
    monkeypatch.setattr("steph.hardware.detect_gpu_vram", lambda gpus, free=False: {})
    assert catalog.detect_machine().vram_gb == 0.0


# ------------------------------------------------------------ B4 : available et source sur ModelChoice


AVAIL_CATALOG = {
    "tiers": [{"id": "N1", "cpu_physical_cores_min": 1, "ram_gb_min": 4}],
    "recommended": {"N1": {"llm": "llm/soon"}},
    "options": [
        {"id": "llm/soon", "kind": "llm", "label": "Bientôt", "file": "soon.gguf", "size_mb": 200,
         "source": "org/soon-GGUF", "available": False, "requires": {"cpu_physical_cores_min": 1, "ram_gb_min": 4}},
        {"id": "llm/now", "kind": "llm", "label": "Maintenant", "file": "now.gguf", "size_mb": 500,
         "source": "org/now-GGUF", "requires": {"cpu_physical_cores_min": 1, "ram_gb_min": 4}},
    ],
}


def test_choices_expose_availability_and_source(tmp_path):
    soon, now = catalog.llm_choices(AVAIL_CATALOG, tmp_path, catalog.Machine(4, 16, 0))
    assert soon.available is False and soon.source == "org/soon-GGUF"
    assert now.available is True and now.source == "org/now-GGUF"  # available absent -> True par défaut


# ------------------------------------------------------------ B9 : not_recommended sur ModelChoice


NOT_RECOMMENDED_CATALOG = {
    "tiers": [{"id": "N1", "cpu_physical_cores_min": 1, "ram_gb_min": 4}],
    "recommended": {"N1": {"llm": "llm/best"}},
    "options": [
        {"id": "llm/best", "kind": "llm", "label": "Meilleur", "file": "best.gguf", "size_mb": 200,
         "requires": {"cpu_physical_cores_min": 1, "ram_gb_min": 4}},
        {"id": "llm/fallback", "kind": "llm", "label": "Secours", "file": "fallback.gguf", "size_mb": 3300,
         "not_recommended": True, "requires": {"cpu_physical_cores_min": 1, "ram_gb_min": 4}},
    ],
}


def test_choices_expose_not_recommended(tmp_path):
    best, fallback = catalog.llm_choices(NOT_RECOMMENDED_CATALOG, tmp_path, catalog.Machine(4, 16, 0))
    assert best.not_recommended is False  # absent du catalogue -> False par défaut
    assert fallback.not_recommended is True


# ------------------------------------------------------------ B4 : tts_choices, symétrique de llm_choices


TTS_CATALOG = {
    "tiers": [{"id": "N1", "cpu_physical_cores_min": 1, "ram_gb_min": 4}],
    "recommended": {"N1": {"llm": "llm/small", "tts": "tts/a"}},
    "options": [
        {"id": "llm/small", "kind": "llm", "label": "Petit", "file": "small.gguf", "size_mb": 500,
         "requires": {"cpu_physical_cores_min": 1, "ram_gb_min": 4}},
        {"id": "tts/a", "kind": "tts", "label": "Voix A", "file": "a.onnx", "size_mb": 60,
         "requires": {"cpu_physical_cores_min": 1, "ram_gb_min": 1}},
        {"id": "tts/b", "kind": "tts", "label": "Voix B", "file": "b.onnx", "size_mb": 400,
         "requires": {"cpu_physical_cores_min": 8, "ram_gb_min": 8}},
    ],
}


def test_tts_choices_mirrors_llm_choices(tmp_path):
    choices = catalog.tts_choices(TTS_CATALOG, tmp_path, catalog.Machine(1, 4, 0))
    assert [c.label for c in choices] == ["Voix A", "Voix B"]
    a, b = choices
    assert a.recommended and not a.out_of_scope
    assert b.out_of_scope and not b.recommended
    assert a.path == str(tmp_path / "a.onnx")
    # llm_choices ne doit pas répondre pour une entrée tts, et réciproquement
    assert catalog.llm_choices(TTS_CATALOG, tmp_path, catalog.Machine(1, 4, 0))[0].label == "Petit"


def test_tts_choices_missing_catalog_is_empty(tmp_path):
    assert catalog.tts_choices({}, tmp_path, catalog.Machine(4, 16, 0)) == []


# ------------------------------------------------------------ B4/B9 : le vrai data/catalog.json


def test_real_catalog_matches_b9_decision():
    """Décision utilisateur 2026-09-28 (B9) : Qwen3.5 9B retiré ; B10 ajoute le Gemma affiné."""
    real = catalog.load_catalog()
    assert real, "data/catalog.json doit exister et être lisible (B4)"
    llm_ids = {o["id"] for o in real["options"] if o["kind"] == "llm"}
    assert llm_ids == {"llm/steph-universal", "llm/steph-base", "llm/gemma-4-e2b"}
    universal = next(o for o in real["options"] if o["id"] == "llm/steph-universal")
    assert universal["profile"] == "finetuned"
    assert universal["available"] is True  # Z1 : G5 a-sft publié
    assert not universal.get("not_recommended")
    gemma = next(o for o in real["options"] if o["id"] == "llm/gemma-4-e2b")
    assert gemma["profile"] == "generic"
    assert gemma.get("available", True) is True
    assert gemma["not_recommended"] is True  # proposé en attendant, jamais recommandé face à steph-speak


def test_real_catalog_tts_options_are_all_piper():
    """tts.py ne charge que des voix Piper (PiperVoice.load) : Kokoro doit rester hors du catalogue B6."""
    real = catalog.load_catalog()
    tts_ids = [o["id"] for o in real["options"] if o["kind"] == "tts"]
    assert tts_ids  # au moins une voix
    assert all("kokoro" not in i for i in tts_ids)
    assert all(i.startswith("tts/piper-") for i in tts_ids)


def test_real_catalog_recommends_the_universal_model_everywhere():
    """« Modèle universel » (A9) : recommandé à tous les niveaux, pas seulement sur GPU."""
    real = catalog.load_catalog()
    for tier in real["tiers"]:
        assert real["recommended"][tier["id"]]["llm"] == "llm/steph-universal"


def test_real_catalog_fits_a_cheap_cpu_machine():
    real = catalog.load_catalog()
    machine = catalog.Machine(physical_cores=1, ram_gb=4, vram_gb=0)
    choices = catalog.llm_choices(real, Path("/models"), machine)
    universal = next(c for c in choices if c.profile == "finetuned")
    assert not universal.out_of_scope
    gemma = next(c for c in choices if c.profile == "generic")
    assert gemma.out_of_scope  # trop peu de cœurs et de RAM pour Gemma (N1 < N2)


def test_real_catalog_gemma_runs_without_a_gpu_on_a_comfortable_cpu_machine():
    """Gemma est le modèle générique déjà servi par défaut aujourd'hui (install.sh), sans GPU :
    son seuil (B9) ne doit pas exiger de VRAM, seulement assez de cœurs et de RAM (N2 et plus)."""
    real = catalog.load_catalog()
    machine = catalog.Machine(physical_cores=4, ram_gb=8, vram_gb=0)
    choices = catalog.llm_choices(real, Path("/models"), machine)
    gemma = next(c for c in choices if c.profile == "generic")
    assert not gemma.out_of_scope


# ------------------------------------------------------------ B10 : Gemma affiné et vitesse par modèle


def test_real_catalog_has_the_fine_tuned_gemma_as_base_model():
    real = catalog.load_catalog()
    base = next(o for o in real["options"] if o["id"] == "llm/steph-base")
    assert base["label"].startswith("steph-speak")  # famille de modèles affinés (docs/naming.md)
    assert "Gemma 4 E2B" in base["label"]
    assert base["available"] is True  # Z1 : G3b off-ple3 publié
    assert base["sha256"] == "eb6e76076b819d9e7a1bbb01e38e8cbf256eb3bd741b6cb0c6311a4a7ed3b429"  # G4b off-ple3
    assert base["size_mb"] == 2432
    assert base["profile"] == "generic"  # G3b tourne avec le prompt générique (G4b)
    assert base["role"] == "base" and not base.get("not_recommended")
    assert base["requires"]["ram_gb_min"] == 6  # RAM pic 3,9 Go : les machines de 4 Go gardent le petit


def test_real_catalog_roles_and_prompt_speeds():
    real = catalog.load_catalog()
    llm = {o["id"]: o for o in real["options"] if o["kind"] == "llm"}
    assert llm["llm/steph-universal"]["role"] == "small"
    assert llm["llm/gemma-4-e2b"]["role"] == "base"
    # vitesse de lecture du prompt sur l'i5-7200U (G2) : la machine lente de référence
    assert llm["llm/steph-universal"]["prompt_tokens_per_sec"] == 200
    assert llm["llm/steph-base"]["prompt_tokens_per_sec"] == 28
    assert llm["llm/gemma-4-e2b"]["prompt_tokens_per_sec"] == 28
    assert llm["llm/steph-base"]["summary_prompt_tokens_p90"] == 766
    assert llm["llm/gemma-4-e2b"]["summary_prompt_tokens_p90"] == 766
    assert llm["llm/steph-universal"]["summary_prompt_tokens_p90"] > 0


def test_choices_expose_id_role_and_prompt_speed(tmp_path):
    real = catalog.load_catalog()
    choices = {c.id: c for c in catalog.llm_choices(real, tmp_path, catalog.Machine(4, 8, 0))}
    base = choices["llm/steph-base"]
    assert base.role == "base" and base.prompt_tokens_per_sec == 28 and base.summary_prompt_tokens_p90 == 766
    assert choices["llm/steph-universal"].role == "small"


def test_eight_gb_machine_can_take_the_base_model_but_four_gb_cannot(tmp_path):
    real = catalog.load_catalog()
    by_id = lambda m: {c.id: c for c in catalog.llm_choices(real, tmp_path, m)}  # noqa: E731
    assert not by_id(catalog.Machine(4, 8, 0))["llm/steph-base"].out_of_scope
    assert by_id(catalog.Machine(4, 4, 0))["llm/steph-base"].out_of_scope


def test_catalog_prompt_speed_by_model_file():
    assert catalog.catalog_prompt_speed("/x/models/gemma-4-E2B_q4_0-it.gguf") == 28
    assert catalog.catalog_prompt_speed("/x/models/unknown.gguf") is None


# ------------------------------------------------------------ Z1 : modèles publiés (G5 a-sft, G3b off-ple3)

PUBLISHED = {
    "llm/steph-universal": {
        "source": "lsmdx/steph-speak-granite-4.0-h-350M-v2-GGUF",
        "file": "steph-speak-granite-4.0-h-350M-sft-v2.0-Q4_K_M.gguf",
        "sha256": "0a4b8f42884a6cc87ac8958528f7c1f95bc702f08b3cb0ee7ea32063e1717199",
        "size_bytes": 222662112,
    },
    "llm/steph-base": {
        "source": "lsmdx/steph-speak-gemma-4-E2B-v2-GGUF",
        "file": "steph-speak-gemma-4-E2B-sft-v2.0-off-ple3.gguf",
        "sha256": "eb6e76076b819d9e7a1bbb01e38e8cbf256eb3bd741b6cb0c6311a4a7ed3b429",
        "size_bytes": 2432011840,
    },
}


@pytest.mark.parametrize("model_id", sorted(PUBLISHED))
def test_published_models_point_to_real_hf_files(model_id):
    expected = PUBLISHED[model_id]
    opt = next(o for o in catalog.load_catalog()["options"] if o["id"] == model_id)
    assert opt["available"] is True
    assert opt["source"] == expected["source"] and opt["file"] == expected["file"]
    assert opt["sha256"] == expected["sha256"]
    assert opt["size_mb"] == round(expected["size_bytes"] / 1_000_000)
    assert len(opt["sha256"]) == 64


def test_published_names_follow_the_naming_schema():
    """docs/open-source.md 2.2 : steph-speak-<base>-<taille>-<méthode>-v<maj>.<min>-<quant>.gguf ;
    pas de segment de langue (fr + en), dépôt -v<maj>-GGUF."""
    for expected in PUBLISHED.values():
        assert expected["file"].startswith("steph-speak-") and expected["file"].endswith(".gguf")
        assert "-fr-" not in expected["file"] and "-v2.0" in expected["file"]
        assert expected["source"].startswith("lsmdx/steph-speak-") and expected["source"].endswith("-v2-GGUF")


def test_small_model_replaces_the_private_v1_file():
    small = next(o for o in catalog.load_catalog()["options"] if o["id"] == "llm/steph-universal")
    assert "steph-speak-granite-4.0-h-350M-dpo-v1.0-Q4_K_M.gguf" in small["replaces"]


def test_catalog_has_no_private_or_placeholder_source_left():
    for o in catalog.load_catalog()["options"]:
        if o["kind"] == "llm" and o.get("available"):
            assert o["source"] and o["file"].endswith(".gguf")


def _opts(**extra):
    small = {"id": "llm/s", "kind": "llm", "label": "S", "source": "o/s-GGUF", "file": "s-v2.gguf", "sha256": "ab" * 32, "size_mb": 1,
             "available": True, "role": "small", "replaces": ["s-v1.gguf"], "requires": {}, "min_tier": "N1"}
    return {"version": 1, "tiers": [{"id": "N1", "label": "x"}], "recommended": {"N1": {"llm": "llm/s"}},
            "options": [{**small, **extra}]}


def test_install_model_is_the_recommended_published_small_model(tmp_path):
    cat = _opts()
    assert catalog.install_model(cat, tmp_path / "models", None, update=False) == ("o/s-GGUF", "s-v2.gguf", "ab" * 32)


def test_install_model_is_none_when_recommended_is_not_published(tmp_path):
    assert catalog.install_model(_opts(available=False), tmp_path / "models", None, update=False) is None
    assert catalog.install_model(_opts(source=""), tmp_path / "models", None, update=False) is None


def test_update_keeps_a_present_current_model(tmp_path):
    models = tmp_path / "models"
    models.mkdir()
    (models / "gemma.gguf").write_bytes(b"x")
    assert catalog.install_model(_opts(), models, str(models / "gemma.gguf"), update=True) == "keep"


def test_update_replaces_a_legacy_v1_model(tmp_path):
    models = tmp_path / "models"
    models.mkdir()
    (models / "s-v1.gguf").write_bytes(b"x")
    assert catalog.install_model(_opts(), models, str(models / "s-v1.gguf"), update=True) == ("o/s-GGUF", "s-v2.gguf", "ab" * 32)


def test_update_without_any_model_downloads_the_default(tmp_path):
    assert catalog.install_model(_opts(), tmp_path / "m", str(tmp_path / "m" / "gone.gguf"), update=True) == \
        ("o/s-GGUF", "s-v2.gguf", "ab" * 32)


def test_fresh_install_ignores_the_config_model(tmp_path):
    models = tmp_path / "models"
    models.mkdir()
    (models / "gemma.gguf").write_bytes(b"x")
    assert catalog.install_model(_opts(), models, str(models / "gemma.gguf"), update=False) == ("o/s-GGUF", "s-v2.gguf", "ab" * 32)


def test_migrate_points_config_to_the_replacement(tmp_path):
    models, cfg = tmp_path / "models", tmp_path / "config.toml"
    models.mkdir()
    (models / "s-v1.gguf").write_bytes(b"x")
    (models / "s-v2.gguf").write_bytes(b"y")
    cfg.write_text(f'model = "{models / "s-v1.gguf"}"\nrate = 1.2\n')
    new = catalog.migrate_config(_opts(), models, cfg)
    assert new == str(models / "s-v2.gguf")
    text = cfg.read_text()
    assert f'model = "{models / "s-v2.gguf"}"' in text and "rate = 1.2" in text
    assert (models / "s-v1.gguf").exists()  # rien n'est supprimé


def test_migrate_does_nothing_without_the_new_file_or_a_legacy_model(tmp_path):
    models, cfg = tmp_path / "models", tmp_path / "config.toml"
    models.mkdir()
    cfg.write_text(f'model = "{models / "s-v1.gguf"}"\n')
    assert catalog.migrate_config(_opts(), models, cfg) is None  # v2 pas téléchargé
    assert "s-v1.gguf" in cfg.read_text()
    cfg.write_text(f'model = "{models / "other.gguf"}"\n')
    (models / "s-v2.gguf").write_bytes(b"y")
    assert catalog.migrate_config(_opts(), models, cfg) is None
    assert catalog.migrate_config(_opts(), models, tmp_path / "absent.toml") is None


def test_every_published_llm_carries_a_full_sha256():
    for o in catalog.load_catalog()["options"]:
        if o["kind"] == "llm" and o.get("available") and o["id"] != "llm/gemma-4-e2b":
            assert len(o["sha256"]) == 64


def test_model_choice_exposes_the_sha256(tmp_path):
    choices = catalog.llm_choices(catalog.load_catalog(), tmp_path, catalog.Machine(8, 32, 8))
    small = next(c for c in choices if c.id == "llm/steph-universal")
    assert small.sha256 == "0a4b8f42884a6cc87ac8958528f7c1f95bc702f08b3cb0ee7ea32063e1717199"


def _adopt_setup(tmp_path):
    models = tmp_path / "models"
    models.mkdir()
    (models / "s-v2.gguf").write_bytes(b"y")
    return models, tmp_path / "config" / "config.toml"


def test_adopt_writes_model_and_profile_when_there_is_no_config(tmp_path):
    models, cfg = _adopt_setup(tmp_path)
    cat = _opts(profile="finetuned", prompt_tokens_per_sec=300)
    assert catalog.adopt_model(cat, models, cfg, "s-v2.gguf") == str(models / "s-v2.gguf")
    text = cfg.read_text()
    assert f'model = "{models / "s-v2.gguf"}"' in text
    assert 'llm_profile = "finetuned"' in text and "llm_prompt_tokens_per_sec = 300.0" in text


def test_adopt_replaces_a_configured_model_missing_from_disk(tmp_path):
    models, cfg = _adopt_setup(tmp_path)
    cfg.parent.mkdir()
    cfg.write_text(f'model = "{models / "gone.gguf"}"\nspeech_rate = 1.5\n')
    assert catalog.adopt_model(_opts(profile="finetuned"), models, cfg, "s-v2.gguf")
    assert "s-v2.gguf" in cfg.read_text() and "speech_rate = 1.5" in cfg.read_text()


def test_adopt_keeps_a_configured_model_present_on_disk(tmp_path):
    models, cfg = _adopt_setup(tmp_path)
    (models / "mine.gguf").write_bytes(b"x")
    cfg.parent.mkdir()
    cfg.write_text(f'model = "{models / "mine.gguf"}"\n')
    assert catalog.adopt_model(_opts(profile="finetuned"), models, cfg, "s-v2.gguf") is None
    assert "mine.gguf" in cfg.read_text() and "llm_profile" not in cfg.read_text()


def test_adopt_ignores_a_file_the_catalog_does_not_know_or_that_is_absent(tmp_path):
    models, cfg = _adopt_setup(tmp_path)
    assert catalog.adopt_model(_opts(), models, cfg, "unknown.gguf") is None
    (models / "s-v2.gguf").unlink()
    assert catalog.adopt_model(_opts(), models, cfg, "s-v2.gguf") is None
    assert not cfg.exists()
