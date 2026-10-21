import os
import subprocess
import time
from pathlib import Path

import pytest

from steph.config import Config
from steph.llm import LLM, _build_args, _build_env
from steph.narrator import clean_llm_text


def _clean(pieces, **kw):
    return "".join(clean_llm_text(iter(pieces), **kw))


# ---------------------------------------------------------------- mode par défaut : flux
# jeton par jeton (le premier mot est la métrique n°1 de steph)

def test_clean_llm_text_streams_the_first_piece_immediately_by_default():
    """Sans buffer_reasoning, rien ne doit retenir un morceau qui ne contient pas de
    balise : le premier mot doit sortir dès qu'il arrive, pas à la fin du flux."""
    gen = clean_llm_text(iter(["Bonjour ", "le fichier est prêt."]))
    assert next(gen) == "Bonjour "


def test_clean_llm_text_passes_through_when_no_think_tags():
    assert _clean(["Bonjour ", "le fichier est prêt."]) == "Bonjour le fichier est prêt."


def test_clean_llm_text_strips_an_explicit_think_block():
    assert _clean(["<think>secret", " reasoning</think>", "réponse publique"]) == "réponse publique"


def test_clean_llm_text_says_nothing_for_an_unclosed_think_block():
    assert _clean(["<think>", "jamais fermé, jamais dit"]) == ""


def test_clean_llm_text_handles_tags_split_across_chunks():
    assert _clean(["<thi", "nk>secret</thi", "nk>", "réponse"]) == "réponse"


def test_clean_llm_text_strips_markdown_in_surviving_text():
    assert _clean(["**gras** et `code`"]) == "gras et code"


def test_clean_llm_text_default_mode_strips_an_isolated_closing_tag_without_replaying_it():
    """Sans buffer_reasoning, le raisonnement déjà parti ne peut pas être rappelé (déjà
    dit à voix haute) : seule la balise littérale ne doit pas se retrouver dans le texte."""
    pieces = ["raisonnement qui fuit ", "encore du raisonnement ", "</think>", "réponse finale"]
    out = _clean(pieces)
    assert "</think>" not in out
    assert out.endswith("réponse finale")


# ---------------------------------------------------------------- buffer_reasoning=True :
# modèles connus pour fermer un raisonnement jamais ouvert (Granite 4.2)

def test_clean_llm_text_buffered_discards_reasoning_before_an_isolated_closing_tag():
    pieces = ["raisonnement qui fuit ", "encore du raisonnement ", "</think>", "réponse finale"]
    assert _clean(pieces, buffer_reasoning=True) == "réponse finale"


def test_clean_llm_text_buffered_still_passes_through_when_no_think_tags():
    assert _clean(["Bonjour ", "le fichier est prêt."], buffer_reasoning=True) == "Bonjour le fichier est prêt."


def test_clean_llm_text_buffered_does_not_stream_before_the_stream_resolves():
    """Le prix du mode buffer_reasoning : rien ne part tant qu'aucune balise n'a tranché."""
    gen = clean_llm_text(iter(["Bonjour ", "le fichier est prêt."]), buffer_reasoning=True)
    assert next(gen) == "Bonjour le fichier est prêt."


def test_build_args_defaults_omit_flash_attn_and_cache_type():
    args = _build_args(Config(), "/opt/llama/llama-server")
    assert "-fa" not in args
    assert "-ctk" not in args
    assert "-ctv" not in args
    assert args[:3] == ["/opt/llama/llama-server", "-m", Config().model]


def test_build_args_includes_flash_attn_and_cache_type_when_set():
    cfg = Config()
    cfg.llm_flash_attn = "on"
    cfg.llm_cache_type = "q8_0"
    args = _build_args(cfg, "/opt/llama/llama-server")
    assert args[args.index("-fa") + 1] == "on"
    assert args[args.index("-ctk") + 1] == "q8_0"
    assert args[args.index("-ctv") + 1] == "q8_0"


def test_build_args_uses_parallel_batch_ubatch_from_config():
    cfg = Config()
    cfg.llm_parallel = 4
    cfg.llm_batch = 1024
    cfg.llm_ubatch = 256
    args = _build_args(cfg, "/opt/llama/llama-server")
    assert args[args.index("--parallel") + 1] == "4"
    assert args[args.index("-b") + 1] == "1024"
    assert args[args.index("-ub") + 1] == "256"


def test_build_args_extra_args_come_last():
    cfg = Config()
    cfg.llm_extra_args = ["--foo", "bar"]
    args = _build_args(cfg, "/opt/llama/llama-server")
    assert args[-2:] == ["--foo", "bar"]


def test_build_env_merges_llm_env():
    cfg = Config()
    cfg.llm_env = {"GGML_VK_VISIBLE_DEVICES": "0"}
    env = _build_env(cfg, Path("/opt/llama-b1234/llama-server"))
    assert env["GGML_VK_VISIBLE_DEVICES"] == "0"


def test_build_env_sets_library_path_next_to_llama_binary():
    env = _build_env(Config(), Path("/opt/llama-b1234/llama-server"))
    assert env["LD_LIBRARY_PATH"].startswith("/opt/llama-b1234")
    assert env["DYLD_LIBRARY_PATH"].startswith("/opt/llama-b1234")


def test_dead_child_is_not_alive(tmp_path):
    llm = LLM(Config())
    llm.pidfile = tmp_path / "llama-server.pid"
    proc = subprocess.Popen(["true"])
    llm.pidfile.write_text(str(proc.pid))
    time.sleep(0.3)  # le fils est mort mais pas encore récolté : zombie
    assert not llm._pid_alive()


def test_running_child_is_alive(tmp_path):
    llm = LLM(Config())
    llm.pidfile = tmp_path / "llama-server.pid"
    proc = subprocess.Popen(["sleep", "5"])
    try:
        llm.pidfile.write_text(str(proc.pid))
        assert llm._pid_alive()
    finally:
        proc.kill()
        proc.wait()


# ---------------------------------------------------------------- déchargement au repos (Q2b)

def test_idle_seconds_is_zero_when_never_touched(tmp_path):
    llm = LLM(Config())
    llm.activity_file = tmp_path / "llama-server.activity"
    assert llm.idle_seconds() == 0.0


def test_touch_activity_resets_idle_seconds_to_near_zero(tmp_path):
    llm = LLM(Config())
    llm.activity_file = tmp_path / "llama-server.activity"
    llm.touch_activity()
    assert llm.idle_seconds() < 1.0


def _backdate(path: Path, seconds_ago: float) -> None:
    then = time.time() - seconds_ago
    path.write_text(str(then))
    os.utime(path, (then, then))


def test_try_unload_idle_does_nothing_when_disabled(tmp_path):
    llm = LLM(Config())
    llm.activity_file = tmp_path / "activity"
    _backdate(llm.activity_file, 3600)
    assert llm.try_unload_idle(0) is False


def test_try_unload_idle_does_nothing_before_the_threshold(tmp_path):
    llm = LLM(Config())
    llm.activity_file = tmp_path / "activity"
    llm.touch_activity()
    assert llm.try_unload_idle(10) is False


def test_try_unload_idle_stops_a_healthy_server_once_idle_enough(tmp_path, monkeypatch):
    llm = LLM(Config())
    llm.activity_file = tmp_path / "activity"
    llm.busy_dir = tmp_path / "busy"
    _backdate(llm.activity_file, 700)  # au-delà de 10 min
    monkeypatch.setattr(llm, "healthy", lambda: True)
    stopped = []
    monkeypatch.setattr(llm, "stop_server", lambda: stopped.append(True))
    assert llm.try_unload_idle(10) is True
    assert stopped == [True]


def test_try_unload_idle_does_nothing_when_already_stopped(tmp_path, monkeypatch):
    llm = LLM(Config())
    llm.activity_file = tmp_path / "activity"
    llm.busy_dir = tmp_path / "busy"
    _backdate(llm.activity_file, 700)
    monkeypatch.setattr(llm, "healthy", lambda: False)
    monkeypatch.setattr(llm, "stop_server", lambda: pytest.fail("ne doit pas être appelé"))
    assert llm.try_unload_idle(10) is False


def test_try_unload_idle_never_stops_a_busy_server(tmp_path, monkeypatch):
    """Aucun déchargement pendant une génération, même dans une autre fenêtre : le
    marqueur `busy_dir` est le seul signal partagé entre processus."""
    llm = LLM(Config())
    llm.activity_file = tmp_path / "activity"
    llm.busy_dir = tmp_path / "busy"
    _backdate(llm.activity_file, 700)
    monkeypatch.setattr(llm, "healthy", lambda: True)
    stopped = []
    monkeypatch.setattr(llm, "stop_server", lambda: stopped.append(True))
    marker = llm._mark_busy()
    assert llm.try_unload_idle(10) is False
    assert stopped == []
    llm._unmark_busy(marker)


def test_busy_marker_is_cleared_and_then_allows_unload(tmp_path, monkeypatch):
    llm = LLM(Config())
    llm.activity_file = tmp_path / "activity"
    llm.busy_dir = tmp_path / "busy"
    _backdate(llm.activity_file, 700)
    monkeypatch.setattr(llm, "healthy", lambda: True)
    stopped = []
    monkeypatch.setattr(llm, "stop_server", lambda: stopped.append(True))
    marker = llm._mark_busy()
    assert llm._any_busy() is True
    assert llm.try_unload_idle(10) is False
    llm._unmark_busy(marker)
    assert llm._any_busy() is False
    assert llm.try_unload_idle(10) is True
    assert stopped == [True]


class _FakeSseResponse:
    status = 200

    def __init__(self, lines: list[bytes]):
        self._lines = lines

    def __iter__(self):
        return iter(self._lines)


class _FakeHTTPConnection:
    """Double de http.client.HTTPConnection : une réponse SSE fixée, aucun réseau."""

    sock = None

    def __init__(self, *a, **kw):
        pass

    def request(self, *a, **kw):
        pass

    def getresponse(self):
        return _FakeSseResponse([
            b'data: {"choices":[{"delta":{"content":"salut"}}]}\n',
            b"data: [DONE]\n",
        ])

    def close(self):
        pass


def test_stream_foreground_touches_activity_and_clears_the_busy_marker(tmp_path, monkeypatch):
    import http.client

    monkeypatch.setattr(http.client, "HTTPConnection", _FakeHTTPConnection)
    llm = LLM(Config())
    llm.activity_file = tmp_path / "activity"
    llm.busy_dir = tmp_path / "busy"
    out = list(llm.stream([{"role": "user", "content": "salut"}]))
    assert out == ["salut"]
    assert llm.idle_seconds() < 1.0
    assert llm._any_busy() is False


def test_stream_background_touches_activity_without_a_busy_marker(tmp_path, monkeypatch):
    """Le préchauffage (background=True) compte comme activité (déchargement) mais
    n'est pas suivi comme une génération utilisateur (`busy_dir`)."""
    import http.client

    monkeypatch.setattr(http.client, "HTTPConnection", _FakeHTTPConnection)
    llm = LLM(Config())
    llm.activity_file = tmp_path / "activity"
    llm.busy_dir = tmp_path / "busy"
    out = list(llm.stream([{"role": "user", "content": "salut"}], background=True))
    assert out == ["salut"]
    assert llm.idle_seconds() < 1.0
    assert llm._any_busy() is False


def test_build_args_finetuned_profile_disables_the_prompt_checkpoint_cache_and_shrinks_the_context():
    cfg = Config()
    cfg.llm_profile = "finetuned"
    args = _build_args(cfg, "llama-server")
    assert args[args.index("--cache-ram") + 1] == "0"
    assert args[args.index("-c") + 1] == "8192"


def test_build_args_generic_profile_keeps_the_context_and_the_checkpoint_cache():
    args = _build_args(Config(), "llama-server")
    assert "--cache-ram" not in args
    assert args[args.index("-c") + 1] == str(Config().llm_ctx)


class _CutSseConnection(_FakeHTTPConnection):
    """Flux coupé avant [DONE] : ce que voit un préchauffage interrompu par abort_background()."""

    def getresponse(self):
        return _FakeSseResponse([])


def test_stream_background_cut_before_done_raises_so_the_warm_resumes(tmp_path, monkeypatch):
    import http.client

    import pytest

    monkeypatch.setattr(http.client, "HTTPConnection", _CutSseConnection)
    llm = LLM(Config())
    llm.activity_file = tmp_path / "activity"
    llm.busy_dir = tmp_path / "busy"
    with pytest.raises(ConnectionError):
        llm.complete([{"role": "user", "content": "ok"}], max_tokens=1, slot=1, background=True)
