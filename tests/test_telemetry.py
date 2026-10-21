"""T1 : onnxruntime (utilisé par Piper) ne doit jamais joindre la télémétrie de Microsoft.

Constat : onnxruntime embarque le SDK 1DS et journalise un événement de chargement de
modèle à chaque session (`InferenceSession`), sans que rien côté steph ne conditionne cet
appel. Mesuré une fois (2026-09-28) : sur Linux (i5 Debian 13), ce journal se traduit par
une vraie connexion HTTPS vers mobile.events.data.microsoft.com (20.42.x.x, 13.89.x.x) ;
sur ce Mac, dans les mêmes conditions, aucune connexion n'a été observée sur plusieurs
essais, sans que la cause de l'écart soit identifiée. La variable d'environnement
ORT_DISABLE_TELEMETRY, documentée dans onnxruntime/Privacy.md, empêche la création du
transmetteur avant même l'initialisation : c'est la seule garantie valable sur les deux
systèmes ; `disable_telemetry_events()` est ajoutée en plus, en défense en profondeur.
"""

from __future__ import annotations

import os
import socket
import types

import pytest

from steph.config import DATA_DIR, Config

REAL_VOICE = DATA_DIR / "voices" / "fr_FR-siwis-medium.onnx"
needs_real_voice = pytest.mark.skipif(not REAL_VOICE.exists(), reason="voix Piper non installée sur cette machine")


def test_importing_tts_disables_onnxruntime_telemetry_env(monkeypatch):
    import importlib

    monkeypatch.delenv("ORT_DISABLE_TELEMETRY", raising=False)
    import steph.tts as tts

    importlib.reload(tts)
    assert os.environ.get("ORT_DISABLE_TELEMETRY") == "1"


@needs_real_voice
def test_loading_a_voice_calls_onnxruntime_disable_telemetry_events(monkeypatch):
    import onnxruntime

    from steph.tts import Speaker

    calls = []
    monkeypatch.setattr(onnxruntime, "disable_telemetry_events", lambda: calls.append(True))
    cfg = Config()
    cfg.voice = str(REAL_VOICE)
    sp = Speaker(cfg)
    try:
        assert sp.voice is not None  # la voix a bien chargé, sinon le test ne prouve rien
        assert calls == [True]
    finally:
        sp.close()


def _guarded_connect(real_connect):
    def guarded(self, address, *a, **kw):
        host = address[0] if isinstance(address, tuple) else address
        if isinstance(host, str) and host not in ("127.0.0.1", "::1", "localhost"):
            raise AssertionError(f"connexion réseau non-loopback interdite ici : {address!r}")
        return real_connect(self, address, *a, **kw)

    return guarded


@needs_real_voice
def test_loading_a_voice_never_opens_a_non_loopback_socket(monkeypatch):
    """Garde-fou : échoue si un code touché par le chargement de la voix tente une
    connexion réseau hors 127.0.0.1/::1 (télémétrie ou toute autre régression future)."""
    monkeypatch.setattr(socket.socket, "connect", _guarded_connect(socket.socket.connect))
    from steph.tts import Speaker

    cfg = Config()
    cfg.voice = str(REAL_VOICE)
    sp = Speaker(cfg)
    try:
        assert sp.voice is not None
    finally:
        sp.close()


def test_guard_actually_catches_a_non_loopback_connection(monkeypatch):
    """Preuve que le garde-fou ci-dessus détecterait une vraie fuite : sans lui, une
    connexion vers une adresse de test (RFC 5737) échouerait silencieusement (réseau ou
    DNS absent) ; avec lui, il lève avant toute E/S, donc avant de dépendre du réseau."""
    monkeypatch.setattr(socket.socket, "connect", _guarded_connect(socket.socket.connect))
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with pytest.raises(AssertionError):
            s.connect(("203.0.113.1", 443))
    finally:
        s.close()


def test_uninstall_removes_leftover_onnxruntime_telemetry_dir(tmp_path):
    from steph import uninstall

    data = tmp_path / "data"
    (data / "models").mkdir(parents=True)
    conf = tmp_path / "config"
    conf.mkdir()
    run = tmp_path / "run"
    run.mkdir()
    onnx_dir = tmp_path / "msft" / "DeveloperTools" / ".onnxruntime"
    onnx_dir.mkdir(parents=True)
    (onnx_dir / "onnxruntime.db").write_bytes(b"x")
    (onnx_dir / "deviceid").write_text("abc")

    out = []
    code = uninstall.run_uninstall(
        data, conf, run, keep_models=False, yes=True, ask=None, out=out.append,
        run=lambda *a, **kw: types.SimpleNamespace(returncode=0), uv=None, prefix="",
        onnx_dir=onnx_dir,
    )
    assert code == 0
    assert not onnx_dir.exists()


def test_onnxruntime_telemetry_dir_is_platform_specific(monkeypatch, tmp_path):
    from steph import uninstall

    monkeypatch.setattr(uninstall.sys, "platform", "darwin")
    monkeypatch.setenv("HOME", str(tmp_path))
    mac = uninstall.onnxruntime_telemetry_dir()
    assert mac == tmp_path / "Library" / "Application Support" / "Microsoft" / "DeveloperTools" / ".onnxruntime"

    monkeypatch.setattr(uninstall.sys, "platform", "linux")
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    linux = uninstall.onnxruntime_telemetry_dir()
    assert linux == tmp_path / ".cache" / "Microsoft" / "DeveloperTools" / ".onnxruntime"
