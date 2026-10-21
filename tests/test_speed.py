"""B10 : choix du modèle selon la vitesse mesurée de la machine, pas seulement la RAM."""

import subprocess

import pytest

from steph import config as config_module
from steph import speed
from steph.catalog import ModelChoice
from steph.config import Config


def _small(tmp_path, present=True, available=True):
    path = tmp_path / "small.gguf"
    if present:
        path.write_bytes(b"x")
    return ModelChoice(label="steph-speak petit", path=str(path), size_mb=223, profile="finetuned",
                       recommended=True, out_of_scope=False, available=available, id="llm/small",
                       role="small", prompt_tokens_per_sec=200.0, summary_prompt_tokens_p90=270)


def _base(tmp_path, present=False, out_of_scope=False, not_recommended=False, id="llm/base"):
    path = tmp_path / f"{id.split('/')[1]}.gguf"
    if present:
        path.write_bytes(b"x")
    return ModelChoice(label="steph-speak base", path=str(path), size_mb=2432, profile="generic",
                       recommended=False, out_of_scope=out_of_scope, available=True, id=id, role="base",
                       prompt_tokens_per_sec=28.0, summary_prompt_tokens_p90=766,
                       not_recommended=not_recommended)


# ------------------------------------------------------------ prédiction


def test_threshold_is_three_seconds():
    assert speed.TARGET_FIRST_SUMMARY_P90 == 3.0


def test_prediction_scales_the_measure_by_the_catalog_ratio(tmp_path):
    small, base = _small(tmp_path), _base(tmp_path)
    # i5 : v1.0 lit à 200 jetons/s, Gemma à 28 ; 1 000 mesurés sur le petit -> 140 pour Gemma
    assert speed.predict_tokens_per_sec(base, small, 1000.0) == pytest.approx(140.0)
    assert speed.predict_tokens_per_sec(small, small, 1000.0) == pytest.approx(1000.0)


def test_prediction_without_measure_is_the_catalog_value(tmp_path):
    small, base = _small(tmp_path), _base(tmp_path)
    assert speed.predict_tokens_per_sec(base, None, None) == 28.0
    assert speed.predict_tokens_per_sec(base, small, None) == 28.0


def test_first_summary_p90_matches_the_i5_measure(tmp_path):
    # G2 : 766 jetons au p90 lus à 28 jetons/s -> 27,3 s mesurés sur l'i5
    assert speed.first_summary_p90(_base(tmp_path), 28.0) == pytest.approx(27.36, abs=0.01)
    assert speed.first_summary_p90(_base(tmp_path), 0.0) is None


# ------------------------------------------------------------ référence de mesure


def test_reference_is_the_smallest_model_already_on_disk(tmp_path):
    small, big = _small(tmp_path), _base(tmp_path, present=True)
    assert speed.reference_model([big, small]) is small
    (other := tmp_path / "other").mkdir()
    big = _base(other, present=True)
    assert speed.reference_model([_small(other, present=False), big]) is big


def test_no_reference_without_any_model_on_disk(tmp_path):
    assert speed.reference_model([_small(tmp_path, present=False), _base(tmp_path)]) is None


# ------------------------------------------------------------ verdict


def test_fast_machine_recommends_the_base_model(tmp_path):
    small, base = _small(tmp_path), _base(tmp_path)
    # 2 000 jetons/s sur le petit -> 280 sur Gemma -> 766 / 280 = 2,7 s
    verdict = speed.assess([small, base], small, 2000.0, gpu=False)
    assert verdict.recommended is base
    assert verdict.fast and verdict.measured
    assert verdict.base_p90 == pytest.approx(2.74, abs=0.01)


def test_i5_like_machine_recommends_the_small_model(tmp_path):
    small, base = _small(tmp_path), _base(tmp_path)
    verdict = speed.assess([small, base], small, 200.0, gpu=False)
    assert verdict.recommended is small
    assert not verdict.fast
    assert verdict.base_p90 == pytest.approx(27.36, abs=0.01)


def test_measure_taken_on_gemma_itself_is_used_directly(tmp_path):
    small, raw = _small(tmp_path, present=False), _base(tmp_path, present=True, not_recommended=True, id="llm/raw")
    base = _base(tmp_path)
    verdict = speed.assess([small, base, raw], raw, 300.0, gpu=False)
    assert verdict.recommended is base  # 766 / 300 = 2,55 s
    assert verdict.base is base  # le brut non recommandé n'est jamais le modèle de base proposé


def test_without_measure_a_gpu_recommends_the_base_model(tmp_path):
    small, base = _small(tmp_path, present=False), _base(tmp_path)
    verdict = speed.assess([small, base], None, None, gpu=True)
    assert verdict.recommended is base and not verdict.measured
    verdict = speed.assess([small, base], None, None, gpu=False)
    assert verdict.recommended is small and not verdict.measured


def test_base_model_out_of_reach_by_ram_recommends_the_small_model(tmp_path):
    small, base = _small(tmp_path), _base(tmp_path, out_of_scope=True)
    verdict = speed.assess([small, base], small, 10_000.0, gpu=True)
    assert verdict.recommended is small
    assert verdict.reason == "ram"


def test_catalog_without_roles_gives_no_verdict(tmp_path):
    plain = ModelChoice(label="x", path=str(tmp_path / "x.gguf"), size_mb=1, profile="generic",
                        recommended=True, out_of_scope=False)
    assert speed.assess([plain], None, None, gpu=False).recommended is None


# ------------------------------------------------------------ application aux choix


def test_apply_moves_the_recommendation_and_sets_each_predicted_speed(tmp_path):
    small, base = _small(tmp_path), _base(tmp_path)
    verdict = speed.assess([small, base], small, 2000.0, gpu=False)
    new_small, new_base = speed.apply([small, base], verdict)
    assert new_base.recommended and not new_small.recommended
    assert new_small.prompt_tokens_per_sec == pytest.approx(2000.0)
    assert new_base.prompt_tokens_per_sec == pytest.approx(280.0)
    assert small.recommended  # les choix d'origine ne sont pas modifiés


def test_apply_without_verdict_keeps_the_catalog_recommendation(tmp_path):
    small, base = _small(tmp_path), _base(tmp_path)
    verdict = speed.Verdict()
    assert [m.recommended for m in speed.apply([small, base], verdict)] == [True, False]


# ------------------------------------------------------------ message dit à la personne


def test_message_fast_names_the_estimate_the_threshold_and_the_free_choice(tmp_path):
    small, base = _small(tmp_path), _base(tmp_path)
    lines = speed.message_lines(speed.assess([small, base], small, 2000.0, gpu=False), "fr")
    assert lines == ["Vitesse mesurée : premier résumé estimé à 2,7 secondes avec le modèle de base.",
                     "Sous le seuil de 3 secondes : modèle de base recommandé.",
                     "L'autre choix reste possible."]


def test_message_slow_in_english(tmp_path):
    small, base = _small(tmp_path), _base(tmp_path)
    assert speed.message(speed.assess([small, base], small, 200.0, gpu=False), "en") == (
        "Measured speed: first summary estimated at 27 seconds with the base model. "
        "Above the 3 second threshold: small model recommended. The other choice remains available.")


def test_message_estimate_without_model_on_disk(tmp_path):
    small, base = _small(tmp_path, present=False), _base(tmp_path)
    assert speed.message(speed.assess([small, base], None, None, gpu=False), "fr") == (
        "Vitesse non mesurée, aucun modèle installé. Processeur seul : petit modèle recommandé. "
        "L'autre choix reste possible.")
    assert speed.message(speed.assess([small, base], None, None, gpu=True), "fr") == (
        "Vitesse non mesurée, aucun modèle installé. Carte graphique reconnue : modèle de base recommandé. "
        "L'autre choix reste possible.")


def test_message_when_the_measure_failed(tmp_path):
    small, base = _small(tmp_path), _base(tmp_path)
    verdict = speed.assess([small, base], small, None, gpu=False)
    assert speed.message(verdict, "fr").startswith("Mesure de vitesse impossible. Processeur seul")


def test_message_ram(tmp_path):
    small, base = _small(tmp_path), _base(tmp_path, out_of_scope=True)
    assert speed.message(speed.assess([small, base], small, 10_000.0, gpu=True), "fr") == (
        "Mémoire insuffisante pour le modèle de base : petit modèle recommandé. L'autre choix reste possible.")


def test_no_message_without_verdict():
    assert speed.message(speed.Verdict(), "fr") == ""
    assert speed.message_lines(speed.Verdict(), "fr") == []


@pytest.mark.parametrize("language", ["fr", "en"])
def test_every_message_line_fits_an_80_column_screen(tmp_path, language):
    small, base = _small(tmp_path), _base(tmp_path)
    verdicts = [speed.assess([small, base], small, tps, gpu=False) for tps in (2000.0, 20.0, None)]
    verdicts.append(speed.assess([small, base], None, None, gpu=True))
    verdicts.append(speed.assess([small, _base(tmp_path, out_of_scope=True)], small, 20.0, gpu=False))
    for verdict in verdicts:
        for line in speed.message_lines(verdict, language):
            assert len(line) <= 80, line


def test_real_labels_name_the_roles_said_by_the_verdict():
    from steph import catalog

    labels = {o["id"]: o["label"] for o in catalog.load_catalog()["options"]}
    assert "petit modèle" in labels["llm/steph-universal"]
    assert "modèle de base" in labels["llm/steph-base"]


def test_seconds_are_spoken_simply():
    assert speed.format_seconds(2.74, "fr") == "2,7"
    assert speed.format_seconds(2.74, "en") == "2.7"
    assert speed.format_seconds(27.36, "fr") == "27"
    assert speed.format_seconds(3.0, "fr") == "3"


# ------------------------------------------------------------ mesure réelle (serveur simulé)


class FakeProc:
    def __init__(self, dies=False):
        self.dies = dies
        self.terminated = self.killed = False

    def poll(self):
        return 1 if self.dies else None

    def terminate(self):
        self.terminated = True

    def wait(self, timeout=None):
        return 0

    def kill(self):
        self.killed = True


def _measure(tmp_path, proc=None, healthy=True, response=None, launch_error=False):
    cfg = Config(llama_server=str(tmp_path / "llama-server"))
    launched, posted = [], []
    proc = proc or FakeProc()

    def launch(args, env):
        if launch_error:
            raise OSError("absent")
        launched.append(args)
        return proc

    def post(port, path, body, timeout):
        posted.append((path, body))
        return response if response is not None else {"timings": {"prompt_n": 180, "prompt_per_second": 812.5}}

    result = speed.measure_prompt_speed(cfg, str(tmp_path / "m.gguf"), launch=launch, healthy=lambda port: healthy,
                                        post=post, load_timeout=0.3)
    return result, launched, posted, proc


def test_measure_reads_prompt_speed_and_always_stops_the_server(tmp_path):
    result, launched, posted, proc = _measure(tmp_path)
    assert result == 812.5
    assert proc.terminated
    args = launched[0]
    assert args[args.index("-m") + 1] == str(tmp_path / "m.gguf")
    # hybride Mamba : sans --cache-ram 0, llama-server gonfle de plusieurs Go (CLAUDE.md)
    assert args[args.index("--cache-ram") + 1] == "0"
    assert args[args.index("--port") + 1] != str(Config().llm_port)  # jamais le port du serveur de steph
    # préchauffage court, puis la mesure sans cache de prompt
    assert len(posted) == 2
    assert all(body["n_predict"] == 1 and body["cache_prompt"] is False for _, body in posted)
    assert len(posted[1][1]["prompt"]) > len(posted[0][1]["prompt"])


def test_measure_returns_none_when_llama_server_is_missing(tmp_path):
    assert _measure(tmp_path, launch_error=True)[0] is None


def test_measure_returns_none_and_stops_when_the_server_never_gets_ready(tmp_path):
    result, _, posted, proc = _measure(tmp_path, healthy=False)
    assert result is None and posted == [] and proc.terminated


def test_measure_returns_none_when_the_server_dies(tmp_path):
    result, _, posted, _ = _measure(tmp_path, proc=FakeProc(dies=True), healthy=False)
    assert result is None and posted == []


def test_measure_returns_none_without_timings(tmp_path):
    assert _measure(tmp_path, response={"content": "x"})[0] is None
    assert _measure(tmp_path, response={"timings": {"prompt_per_second": 0}})[0] is None


def test_measure_returns_none_when_the_request_fails(tmp_path):
    cfg = Config(llama_server=str(tmp_path / "llama-server"))
    proc = FakeProc()

    def post(*a):
        raise OSError("refused")

    assert speed.measure_prompt_speed(cfg, "m.gguf", launch=lambda args, env: proc, healthy=lambda p: True,
                                      post=post, load_timeout=0.3) is None
    assert proc.terminated


def test_measure_kills_a_server_that_ignores_terminate(tmp_path):
    class Stubborn(FakeProc):
        def wait(self, timeout=None):
            if not self.killed:
                raise subprocess.TimeoutExpired("llama-server", timeout)
            return 0

    _, _, _, proc = _measure(tmp_path, proc=Stubborn())
    assert proc.killed


# ------------------------------------------------------------ config : vitesse par modèle


def test_load_config_takes_the_prompt_speed_of_the_configured_model_from_the_catalog(tmp_path, monkeypatch):
    monkeypatch.setattr(config_module, "CONFIG_PATH", tmp_path / "absent.toml")
    monkeypatch.delenv("STEPH_LLM_PROMPT_TOKENS_PER_SEC", raising=False)
    monkeypatch.delenv("STEPH_MODEL", raising=False)
    cfg = config_module.load_config()
    # modèle par défaut : Gemma 4 E2B, 28 jetons/s sur l'i5 (G2), pas les 210 de Granite
    assert cfg.model.endswith("gemma-4-E2B_q4_0-it.gguf")
    assert cfg.llm_prompt_tokens_per_sec == 28.0


def test_load_config_keeps_an_explicit_prompt_speed(tmp_path, monkeypatch):
    path = tmp_path / "config.toml"
    path.write_text("llm_prompt_tokens_per_sec = 640.0\n")
    monkeypatch.setattr(config_module, "CONFIG_PATH", path)
    monkeypatch.delenv("STEPH_LLM_PROMPT_TOKENS_PER_SEC", raising=False)
    assert config_module.load_config().llm_prompt_tokens_per_sec == 640.0
    monkeypatch.setenv("STEPH_LLM_PROMPT_TOKENS_PER_SEC", "99")
    assert config_module.load_config().llm_prompt_tokens_per_sec == 99.0


def test_load_config_keeps_the_default_for_a_model_outside_the_catalog(tmp_path, monkeypatch):
    path = tmp_path / "config.toml"
    path.write_text('model = "/models/other.gguf"\n')
    monkeypatch.setattr(config_module, "CONFIG_PATH", path)
    monkeypatch.delenv("STEPH_LLM_PROMPT_TOKENS_PER_SEC", raising=False)
    assert config_module.load_config().llm_prompt_tokens_per_sec == 210.0
