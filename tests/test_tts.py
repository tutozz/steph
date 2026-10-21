"""Speaker : parole forcée (menu, même voix coupée), rechargement de la voix et du débit."""

import pytest

from steph.config import DATA_DIR, Config
from steph.tts import Speaker

REAL_VOICE = DATA_DIR / "voices" / "fr_FR-siwis-medium.onnx"


def wait_done(sp: Speaker) -> None:
    import time

    time.sleep(0.05)
    while sp.speaking.is_set() or not sp._q.empty():
        time.sleep(0.01)


def test_muted_speaker_stays_silent_without_force(tmp_path):
    cfg = Config()
    cfg.tts_enabled = False
    log = tmp_path / "speech.log"
    cfg.speech_log = str(log)
    sp = Speaker(cfg)
    try:
        assert sp.voice is None  # pas de synthèse chargée : voix coupée
        sp.say("silence attendu")
        wait_done(sp)
        assert sp.last_text == "silence attendu"  # journalisé quand même
    finally:
        sp.close()


def test_force_bypasses_tts_enabled_flag_for_speak_one(tmp_path, monkeypatch):
    cfg = Config()
    cfg.tts_enabled = False
    sp = Speaker(cfg)
    try:
        calls = []
        monkeypatch.setattr(sp, "_speak_one", lambda text, gen: calls.append(text))
        sp.say("jamais", force=False)
        wait_done(sp)
        assert calls == []
        sp.say("toujours", force=True)
        wait_done(sp)
        assert calls == ["toujours"]
    finally:
        sp.close()


def test_say_stream_accepts_force(monkeypatch):
    cfg = Config()
    cfg.tts_enabled = False
    sp = Speaker(cfg)
    try:
        calls = []
        monkeypatch.setattr(sp, "_speak_one", lambda text, gen: calls.append(text))
        sp.say_stream(["a", "b"], force=True)
        wait_done(sp)
        assert calls  # au moins un appel : la voix a bien parlé malgré tts_enabled=False
    finally:
        sp.close()


def test_reload_voice_updates_cfg_and_reloads(tmp_path):
    cfg = Config()
    cfg.tts_enabled = False  # pas de voix chargée au départ
    sp = Speaker(cfg)
    try:
        assert sp.voice is None
        sp.reload_voice(str(tmp_path / "does-not-exist.onnx"))
        assert cfg.voice == str(tmp_path / "does-not-exist.onnx")
        assert sp.voice is None  # fichier inexistant : repli silencieux, pas d'exception
    finally:
        sp.close()


@pytest.mark.skipif(not REAL_VOICE.exists(), reason="voix Piper non installée sur cette machine")
def test_reload_voice_actually_loads_a_real_voice():
    cfg = Config()
    cfg.tts_enabled = True
    cfg.voice = str(REAL_VOICE)
    sp = Speaker(cfg)
    try:
        assert sp.voice is not None
        sp.voice = None  # simule un état sans voix chargée
        sp.reload_voice(str(REAL_VOICE))
        assert sp.voice is not None
        assert cfg.voice == str(REAL_VOICE)
    finally:
        sp.close()


def test_set_rate_updates_cfg_without_reloading_model(tmp_path, monkeypatch):
    cfg = Config()
    cfg.tts_enabled = False
    sp = Speaker(cfg)
    try:
        called = []
        monkeypatch.setattr(sp, "_load_voice", lambda: called.append(True))
        sp.set_rate(2.0)
        assert cfg.speech_rate == 2.0
        assert called == []  # pas de rechargement complet du modèle pour un simple débit
    finally:
        sp.close()
