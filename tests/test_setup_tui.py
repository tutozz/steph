"""M6 : `steph setup` plein écran - déroulé, états, voix, confirmation, repli en mode ligne."""

import tomllib

import pytest

from steph import setup, setup_tui, tui
from steph.config import Config
from steph.term_style import Style

DOWN, UP, ENTER, ESC = b"\x1b[B", b"\x1b[A", b"\r", b"\x1b"


class Term:
    """Terminal simulé : touches scriptées, écritures et paroles journalisées."""

    def __init__(self, keys):
        self.keys = list(keys)
        self.out = []
        self.said = []

    def read(self):
        if not self.keys:
            raise AssertionError(f"plus de touche ; dernière parole : {self.said[-1:]}")
        return self.keys.pop(0)

    def screen(self, language="fr"):
        return tui.Screen(self.read, self.out.append, lambda: (24, 80), Style(None), self.said.append, language)


def voices_dir(tmp_path, names=("fr_FR-siwis-medium", "fr_FR-tom-medium")):
    d = tmp_path / "voices"
    d.mkdir(exist_ok=True)
    for name in names:
        (d / f"{name}.onnx").write_bytes(b"")
    return d


def catalog(tmp_path):
    present = tmp_path / "steph-speak.gguf"
    present.write_bytes(b"x")
    return [
        setup.ModelChoice(label="steph-speak", path=str(present), size_mb=223, profile="finetuned",
                          recommended=True, out_of_scope=False),
        setup.ModelChoice(label="Gemma 4 E2B", path=str(tmp_path / "gemma.gguf"), size_mb=3300, profile="generic",
                          recommended=False, out_of_scope=False, not_recommended=True, source="org/gemma"),
        setup.ModelChoice(label="Qwen 3 8B", path=str(tmp_path / "qwen.gguf"), size_mb=5000, profile="generic",
                          recommended=False, out_of_scope=True, source="org/qwen"),
    ]


def collect(tmp_path, keys, cfg=None, models=(), voices_catalog=(), config_exists=False, language="fr",
            model_note=()):
    term = Term(keys)
    cfg = cfg or Config(language=language)
    vdir = voices_dir(tmp_path)
    if cfg.voice == Config().voice:
        cfg.voice = str(vdir / "fr_FR-siwis-medium.onnx")
    plan = setup_tui.collect(cfg, term.screen(language), tmp_path / "config.toml", config_exists,
                             list(models), list(voices_catalog), vdir, model_note=model_note)
    return plan, term


# ------------------------------------------------------------ déroulé


def test_all_defaults_keep_current_values(tmp_path):
    # voix, débit, détail, touches, confirmation : Entrée partout
    plan, term = collect(tmp_path, [ENTER] * 5)
    assert plan.answers == {"voice": str(tmp_path / "voices" / "fr_FR-siwis-medium.onnx"),
                            "speech_rate": 1.25, "verbosity": 1}
    assert plan.model is None and plan.voice is None and not plan.keep_existing
    assert not term.keys


def test_arrows_change_each_answer(tmp_path):
    keys = [DOWN, ENTER,  # voix 2
            DOWN, ENTER,  # débit 1,5
            DOWN, ENTER,  # détail 2
            ENTER,  # touches actuelles
            ENTER]  # enregistrer
    plan, _ = collect(tmp_path, keys)
    assert plan.answers["voice"].endswith("fr_FR-tom-medium.onnx")
    assert plan.answers["speech_rate"] == 1.5
    assert plan.answers["verbosity"] == 2


def test_digit_jumps_then_enter_validates(tmp_path):
    plan, _ = collect(tmp_path, [ENTER, b"1", ENTER, b"1", ENTER, ENTER, ENTER])
    assert plan.answers["speech_rate"] == 0.5
    assert plan.answers["verbosity"] == 0


def test_catalog_states_are_said_and_blocked_model_is_refused(tmp_path):
    keys = [b"3", ENTER,  # Qwen : bloqué, raison dite
            UP, ENTER,  # Gemma
            ENTER, ENTER, ENTER, ENTER, ENTER]
    plan, term = collect(tmp_path, keys, models=catalog(tmp_path))
    assert plan.model.label == "Gemma 4 E2B"
    assert term.said[0].startswith("Configuration de steph, plein écran.")
    assert "Modèle de langage. steph-speak, recommandé, actuel" not in term.said[0]  # pas le modèle actuel
    assert "Modèle de langage. steph-speak, recommandé. 3 choix." in term.said[0]
    assert "Qwen 3 8B, bloqué : hors de portée de cette machine" in term.said
    assert "Qwen 3 8B : hors de portée de cette machine. Choisissez une autre option." in term.said
    assert "Gemma 4 E2B, non recommandé : pas optimisé pour steph" in term.said


def test_model_descriptions_give_size_and_download_state(tmp_path):
    _, term = collect(tmp_path, [DOWN, ESC], models=catalog(tmp_path))
    screen = "".join(term.out)
    assert "223 Mo, déjà sur le disque." in screen
    # description coupée sur deux lignes à 80 colonnes : les morceaux, pas la phrase entière
    assert "Non recommandé : pas optimisé pour steph. 3 300 Mo," in screen
    assert "téléchargé après la" in screen and "confirmation." in screen


def test_current_model_is_focused_and_marked_current(tmp_path):
    models = catalog(tmp_path)
    cfg = Config(model=models[0].path)
    _, term = collect(tmp_path, [ESC], cfg=cfg, models=models)
    assert "Modèle de langage. steph-speak, recommandé, actuel. 3 choix." in term.said[0]


def test_step_counter_counts_only_the_screens_shown(tmp_path):
    _, term = collect(tmp_path, [ESC], models=catalog(tmp_path))
    assert "étape 1 sur 6" in term.out[0]

    without_catalog = tmp_path / "without-catalog"
    without_catalog.mkdir()
    _, term = collect(without_catalog, [ESC])
    assert "étape 1 sur 5" in term.out[0]


def test_rate_screen_lists_values_and_marks_normal_and_current(tmp_path):
    _, term = collect(tmp_path, [ENTER, ESC])
    rate_screen = term.out[-1]
    assert "Débit de parole" in rate_screen
    assert "1,25" in rate_screen and "actuel" in rate_screen and "normal" in rate_screen
    assert term.said[-1] == "Débit de parole. 1,25, actuel. 11 choix. Point d'interrogation pour l'aide."


def test_unusual_current_rate_is_kept_in_the_list(tmp_path):
    plan, _ = collect(tmp_path, [ENTER, ENTER, ENTER, ENTER, ENTER], cfg=Config(speech_rate=1.1))
    assert plan.answers["speech_rate"] == 1.1


def test_choosing_other_keys_captures_each_key(tmp_path):
    keys = [ENTER, ENTER, ENTER, DOWN, ENTER,
            b"\x1b[17~", ENTER] + [b"a"] * (len(setup.KEY_ACTIONS) - 2) + [ENTER]
    plan, term = collect(tmp_path, keys)
    assert plan.answers["key_menu"] == "\x1b[17~"
    assert "key_ask" not in plan.answers
    assert "Appuyez sur la touche pour ouvrir le menu." in term.said
    assert any("Touches : 1 changées" in o for o in term.out)


def test_confirmation_summarizes_before_saving(tmp_path):
    _, term = collect(tmp_path, [ENTER] * 4 + [ESC])
    confirm = term.out[-1]
    for line in ("Voix : siwis medium", "Débit : 1,25", "Niveau de détail : Bref", "Touches : inchangées"):
        assert line in confirm
    assert "Enregistrer" in confirm and "Quitter sans enregistrer" in confirm
    assert term.said[-1].startswith("Enregistrer ces réglages. Voix : siwis medium. Débit : 1,25. "
                                    "Niveau de détail : Bref. Touches : inchangées. Enregistrer. 2 choix.")


@pytest.mark.parametrize("keys", [[ESC], [ENTER, ESC], [ENTER] * 4 + [DOWN, ENTER], [b"\x03"]])
def test_escape_quit_or_ctrl_c_returns_none(tmp_path, keys):
    plan, _ = collect(tmp_path, keys)
    assert plan is None


def test_ctrl_c_during_key_capture_cancels(tmp_path):
    plan, _ = collect(tmp_path, [ENTER, ENTER, ENTER, DOWN, ENTER, b"\x03"])
    assert plan is None


def test_existing_config_defaults_to_keep(tmp_path):
    plan, term = collect(tmp_path, [ENTER], config_exists=True)
    assert plan.keep_existing
    assert term.said[0].endswith("Un fichier de configuration existe déjà. Le garder tel quel. 2 choix. "
                                 "Point d'interrogation pour l'aide.")


def test_existing_config_can_be_edited(tmp_path):
    plan, _ = collect(tmp_path, [UP, ENTER] + [ENTER] * 5, config_exists=True)
    assert plan is not None and not plan.keep_existing and plan.answers["speech_rate"] == 1.25


def test_english_setup(tmp_path):
    _, term = collect(tmp_path, [ESC], language="en")
    assert term.said[0].startswith("steph setup, full screen.")
    assert "Voice. siwis medium, current. 2 choices." in term.said[0]
    assert "step 1 of 5" in term.out[0]


def test_every_focus_change_is_said_exactly(tmp_path):
    _, term = collect(tmp_path, [DOWN, DOWN, ESC])
    assert term.said[1:] == ["tom medium", "siwis medium, actuel"]


# ------------------------------------------------------------ application du plan


def test_apply_plan_downloads_after_the_screen_and_writes_config(tmp_path):
    models = catalog(tmp_path)
    plan = setup_tui.Plan(model=models[1], answers={"speech_rate": 1.5})
    got, said = [], []
    code = setup.apply_plan(plan, Config(), tmp_path / "config.toml", said.append,
                            download=lambda c: got.append(c.label) or True)
    assert code == 0 and got == ["Gemma 4 E2B"]
    data = tomllib.loads((tmp_path / "config.toml").read_text())
    assert data == {"model": models[1].path, "llm_profile": "generic", "speech_rate": 1.5}
    assert said[-1].startswith("Configuration enregistrée")


def test_apply_plan_failed_download_keeps_the_old_model(tmp_path):
    models = catalog(tmp_path)
    plan = setup_tui.Plan(model=models[1], answers={"verbosity": 2})
    said = []
    setup.apply_plan(plan, Config(), tmp_path / "config.toml", said.append, download=lambda c: False)
    assert tomllib.loads((tmp_path / "config.toml").read_text()) == {"verbosity": 2}
    assert any(s.startswith("Téléchargement de Gemma 4 E2B impossible") for s in said)


def test_apply_plan_keep_existing_writes_nothing(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("llm_port = 9000\n")
    said = []
    assert setup.apply_plan(setup_tui.Plan(keep_existing=True), Config(), path, said.append) == 0
    assert path.read_text() == "llm_port = 9000\n"
    assert said == ["Configuration inchangée."]


# ------------------------------------------------------------ main : choix du mode


class FakeVoice:
    def __init__(self, *_):
        self.said, self.spoken = [], []

    def say(self, text):
        self.said.append(text)

    def speak(self, text):
        self.spoken.append(text)

    def close(self):
        pass


def test_main_uses_line_mode_and_says_why_when_a_screen_reader_is_on(tmp_path, monkeypatch):
    import io

    voice = FakeVoice()
    monkeypatch.setattr(setup, "_Voice", lambda cfg: voice)
    monkeypatch.setattr(setup, "load_config", lambda: Config(tts_enabled=False))
    monkeypatch.setattr(setup, "open_tty", lambda: (io.StringIO(""), io.StringIO()))
    monkeypatch.setattr(setup, "_tty_mode", lambda cfg, tty_in, tty_out: ("line", "screen_reader", "VoiceOver"))
    monkeypatch.setattr(setup, "_setup_models", lambda cfg: [])
    monkeypatch.setattr(setup, "_setup_voices", lambda cfg: [])
    called = []
    monkeypatch.setattr(setup, "_main_tui", lambda *a, **k: called.append(1) or 0)
    assert setup.main(tmp_path / "config.toml") == 1  # fin de saisie en mode ligne : abandon
    assert called == []
    assert voice.said[0] == ("Lecteur d'écran détecté, VoiceOver : configuration en mode ligne. "
                             "STEPH_UI=tui force le plein écran.")
    assert not (tmp_path / "config.toml").exists()


def test_main_uses_the_full_screen_when_no_screen_reader(tmp_path, monkeypatch):
    import io

    monkeypatch.setattr(setup, "_Voice", FakeVoice)
    monkeypatch.setattr(setup, "load_config", lambda: Config(tts_enabled=False))
    monkeypatch.setattr(setup, "open_tty", lambda: (io.StringIO(""), io.StringIO()))
    monkeypatch.setattr(setup, "_tty_mode", lambda cfg, tty_in, tty_out: ("tui", "tui", None))
    monkeypatch.setattr(setup, "_main_tui", lambda *a, **k: 7)
    assert setup.main(tmp_path / "config.toml") == 7


def test_tty_mode_reads_config_ui_and_term(monkeypatch):
    import io

    class FakeTty(io.StringIO):
        def isatty(self):
            return True

    monkeypatch.setenv("TERM", "dumb")
    assert setup._tty_mode(Config(), FakeTty(), FakeTty())[:2] == ("line", "dumb")
    monkeypatch.setenv("TERM", "xterm-256color")
    assert setup._tty_mode(Config(ui="line"), FakeTty(), FakeTty())[:2] == ("line", "user")
    monkeypatch.setattr(tui, "screen_reader_active", lambda: "Orca")
    assert setup._tty_mode(Config(), FakeTty(), FakeTty()) == ("line", "screen_reader", "Orca")
    monkeypatch.setattr(tui, "screen_reader_active", lambda: None)
    assert setup._tty_mode(Config(), FakeTty(), FakeTty()) == ("tui", "tui", None)


# ------------------------------------------------------------ B10 : verdict de vitesse


def test_speed_verdict_is_shown_and_said_on_the_model_screen(tmp_path):
    lines = ["Vitesse mesurée : premier résumé estimé à 27 secondes avec le modèle de base.",
             "Au-dessus du seuil de 3 secondes : petit modèle recommandé.", "L'autre choix reste possible."]
    plan, term = collect(tmp_path, [ENTER, ENTER, ENTER, ENTER, ENTER, ENTER], models=catalog(tmp_path),
                         model_note=lines)
    opening = next(s for s in term.said if "Vitesse mesurée" in s)
    assert ("Vitesse mesurée : premier résumé estimé à 27 secondes avec le modèle de base. "
            "Au-dessus du seuil de 3 secondes : petit modèle recommandé. L'autre choix reste possible") in opening
    assert ".." not in opening
    screen = "".join(term.out)
    assert all(line.rstrip(".") in screen for line in lines)  # une ligne par phrase, rien de coupé


def test_model_detail_gives_the_first_summary_estimate(tmp_path):
    m = setup.ModelChoice(label="steph-speak base", path=str(tmp_path / "b.gguf"), size_mb=2432, profile="generic",
                          recommended=True, out_of_scope=False, prompt_tokens_per_sec=280.0,
                          summary_prompt_tokens_p90=766)
    option = setup_tui.catalog_option(m, "", "fr")
    assert "premier résumé en 2,7 secondes environ" in option.detail


def test_apply_plan_writes_the_prompt_speed_of_the_chosen_model(tmp_path):
    m = setup.ModelChoice(label="steph-speak base", path=str(tmp_path / "b.gguf"), size_mb=2432, profile="generic",
                          recommended=True, out_of_scope=False, prompt_tokens_per_sec=280.0,
                          summary_prompt_tokens_p90=766)
    (tmp_path / "b.gguf").write_bytes(b"x")
    path = tmp_path / "config.toml"
    setup.apply_plan(setup_tui.Plan(model=m), Config(), path, lambda s: None)
    assert tomllib.loads(path.read_text())["llm_prompt_tokens_per_sec"] == 280.0


def test_first_setup_focuses_the_speed_pick_not_the_built_in_model(tmp_path):
    models = catalog(tmp_path)
    (tmp_path / "gemma.gguf").write_bytes(b"x")
    cfg = Config(model=models[1].path)  # défaut intégré, aucun config.toml
    _, term = collect(tmp_path, [ESC], cfg=cfg, models=models)
    assert "steph-speak, recommandé. 3 choix." in term.said[0]


def test_rerun_focuses_the_model_chosen_in_config_toml(tmp_path):
    models = catalog(tmp_path)
    (tmp_path / "gemma.gguf").write_bytes(b"x")
    (tmp_path / "config.toml").write_text(f'model = "{models[1].path}"\n')
    cfg = Config(model=models[1].path)
    _, term = collect(tmp_path, [UP, ENTER, ESC], cfg=cfg, models=models, config_exists=True)
    assert any("Gemma 4 E2B, non recommandé : pas optimisé pour steph, actuel. 3 choix." in s for s in term.said)
