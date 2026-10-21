"""Tests du narrateur : masquage du premier jeton du LLM (P9) + non-régression.

`FakeSpeaker`/`FakeLLM` remplacent le vrai thread audio et le vrai serveur llama : les
tests appellent `_finish` directement, dans le thread du test, sans réseau ni son.
"""

import json
import threading
import time
from pathlib import Path

import pytest

from steph.config import Config
from steph.narrator import (
    Narrator,
    _drop_leading_status,
    _estimate_first_token_seconds,
    _estimate_prefix_seconds,
    _line_count_fact,
)
from steph.session import Session

BENCH = Path(__file__).parent.parent / "bench"


def _fixture(cmd: str) -> str:
    fixtures = json.loads((BENCH / "fixtures.json").read_text())
    return next(f["output"] for f in fixtures if f["cmd"] == cmd)


class FakeSpeaker:
    """Double de Speaker : consomme le flux tout de suite, sans thread ni audio."""

    def __init__(self):
        self.said: list[str] = []

    def say(self, text, interrupt=True, on_done=None):
        self.say_stream([text], interrupt=interrupt, on_done=on_done)

    def say_stream(self, pieces, interrupt=True, on_done=None):
        text = "".join(pieces)
        self.said.append(text)
        if on_done:
            on_done(text)

    def stop(self):
        pass


class FakeLLM:
    """Double de LLM : renvoie un flux de morceaux fixé, jamais de vrai serveur."""

    def __init__(self, pieces):
        self.pieces = list(pieces)
        self.calls = 0
        self.active = 0
        self.last_done = 0.0
        self.healthy_value = True
        self.ensure_calls = 0
        self.stopped = False
        self._idle_seconds = 0.0

    def stream(self, messages, max_tokens=90, **kw):
        self.calls += 1
        yield from self.pieces

    def complete(self, messages, **kw):
        self.calls += 1
        return "".join(self.pieces)

    def healthy(self) -> bool:
        return self.healthy_value

    def ensure_server(self, wait: float = 60.0) -> bool:
        self.ensure_calls += 1
        return self.healthy_value

    def stop_server(self) -> None:
        self.stopped = True
        self.healthy_value = False

    def idle_seconds(self) -> float:
        return self._idle_seconds

    def try_unload_idle(self, idle_minutes: float) -> bool:
        if idle_minutes <= 0 or self._idle_seconds < idle_minutes * 60 or not self.healthy_value:
            return False
        self.stop_server()
        return True


def _finished_command(session, cmd, cwd, exit_code, out_lines, active=0.5):
    c = session.start(cmd)
    c.enter_at = c.start
    c.end = c.start + active
    c.exit = exit_code
    c.out.lines = list(out_lines)
    c.out.total_lines = len(out_lines)
    return c


def _narrator(cfg=None, pieces=()):
    cfg = cfg or Config()
    session = Session()
    sp = FakeSpeaker()
    llm = FakeLLM(pieces)
    n = Narrator(cfg, session, sp, llm)
    n.llm_ready = True  # court-circuite le sondage de santé : pas de vrai serveur
    return n, session, sp, llm


# 6 lignes génériques, aucun résolveur déterministe ne doit les reconnaître
LONG_OUTPUT = [f"étape {i} : préparation" for i in range(1, 7)]


# ---------------------------------------------------------------- helpers purs (P9)

def test_estimate_first_token_seconds_uses_the_chars_per_token_ratio_and_configured_speed():
    cfg = Config()
    cfg.llm_prompt_tokens_per_sec = 100.0
    msgs = [{"role": "system", "content": "x" * 320}]  # 320 car. / 3,2 = 100 jetons
    assert _estimate_first_token_seconds(msgs, cfg) == pytest.approx(1.0)


def test_estimate_prefix_seconds_scales_with_speech_rate():
    cfg = Config()
    cfg.speech_rate = 1.0  # BASE_SPEECH_WORDS_PER_SEC = 2,5 mots/s à vitesse 1.0
    assert _estimate_prefix_seconds("un deux trois", cfg) == pytest.approx(3 / 2.5)
    cfg.speech_rate = 2.5
    assert _estimate_prefix_seconds("un deux trois", cfg) == pytest.approx(3 / (2.5 * 2.5))


def test_line_count_fact_agrees_in_number():
    assert _line_count_fact(1) == "1 ligne."
    assert _line_count_fact(6) == "6 lignes."


def test_drop_leading_status_strips_success_and_failure_without_touching_the_rest():
    assert "".join(_drop_leading_status(iter(["Succès. ", "Tout va bien."]))) == "Tout va bien."
    assert "".join(_drop_leading_status(iter(["Échec. ", "Fichier introuvable."]))) == "Fichier introuvable."


def test_drop_leading_status_works_across_chunk_boundaries():
    assert "".join(_drop_leading_status(iter(["Su", "ccès", ". reste du texte"]))) == "reste du texte"


def test_drop_leading_status_does_not_truncate_a_word_that_only_starts_like_status():
    # « Échecs » (pluriel) n'est pas « Échec » : sans limite de mot (\b) dans la regex,
    # la première version de ce code coupait « Échecs multiples » en « s multiples ».
    text = "Échecs multiples relevés."
    assert "".join(_drop_leading_status(iter([text]))) == text


def test_drop_leading_status_leaves_unrelated_text_untouched():
    text = "Le fichier est prêt, rien à signaler ici."
    assert "".join(_drop_leading_status(iter([text]))) == text


# ---------------------------------------------------------------- statut immédiat (étape 1)

def test_short_command_says_success_immediately_before_the_model_speaks():
    cfg = Config()
    cfg.llm_prompt_tokens_per_sec = 1.0  # force un long délai : le fait sûr doit s'ajouter
    n, session, sp, llm = _narrator(cfg, pieces=["Succès. ", "Rapport généré."])
    c = _finished_command(session, "customtool process --batch", "/home/user", 0, LONG_OUTPUT, active=0.5)
    n._finish(c, "/home/user", "/home/user")
    assert llm.calls == 1
    text = sp.said[0]
    assert text.startswith("Succès. ")
    assert text.count("Succès") == 1  # le modèle a répété le statut, il est retiré
    assert "6 lignes." in text  # fait sûr : nombre de lignes, jamais inventé
    assert text.endswith("Rapport généré.")
    assert c.summary == text  # on_done a bien été appelé avec le texte final


def test_short_command_says_failure_with_the_exit_code_immediately():
    cfg = Config()
    cfg.llm_prompt_tokens_per_sec = 1.0
    n, session, sp, llm = _narrator(cfg, pieces=["Échec. ", "Cause : disque plein."])
    c = _finished_command(session, "customtool process --batch", "/home/user", 3, LONG_OUTPUT, active=0.5)
    n._finish(c, "/home/user", "/home/user")
    text = sp.said[0]
    assert text.startswith("Échec, code 3. ")
    assert text.count("Échec") == 1
    assert "6 lignes." in text
    assert text.endswith("Cause : disque plein.")


# ---------------------------------------------------------------- fait sûr conditionnel (étape 2)

def test_no_extra_fact_when_the_prefix_alone_already_covers_the_first_token_delay():
    cfg = Config()
    cfg.llm_prompt_tokens_per_sec = 10_000_000.0  # délai quasi nul : le préfixe seul suffit
    n, session, sp, llm = _narrator(cfg, pieces=["Rien à signaler."])
    c = _finished_command(session, "customtool process --batch", "/home/user", 0, LONG_OUTPUT, active=0.5)
    n._finish(c, "/home/user", "/home/user")
    assert sp.said[0] == "Succès. Rien à signaler."


# ------------------------------------- commandes longues : statut en tête, durée en fin (étape 3)

def test_long_command_success_says_status_first_and_duration_last():
    cfg = Config()
    cfg.llm_prompt_tokens_per_sec = 10_000_000.0  # isole le test du doublon, sans le fait sûr
    n, session, sp, llm = _narrator(cfg, pieces=["Succès. ", "Tout est bon."])
    c = _finished_command(session, "customtool process --batch", "/home/user", 0, LONG_OUTPUT, active=5.0)
    n._finish(c, "/home/user", "/home/user")
    assert sp.said[0] == "Succès. Tout est bon. En 5 secondes."


def test_long_command_failure_says_status_first_and_duration_last():
    cfg = Config()
    cfg.llm_prompt_tokens_per_sec = 10_000_000.0
    n, session, sp, llm = _narrator(cfg, pieces=["Échec. ", "Cause : disque plein."])
    c = _finished_command(session, "customtool process --batch", "/home/user", 3, LONG_OUTPUT, active=84.0)
    n._finish(c, "/home/user", "/home/user")
    assert sp.said[0] == "Échec, code 3. Cause : disque plein. Après 1 minute 24."


def test_long_command_interrupted_says_status_first_and_duration_last():
    cfg = Config()
    cfg.llm_prompt_tokens_per_sec = 10_000_000.0
    n, session, sp, llm = _narrator(cfg, pieces=["On y était presque."])
    c = _finished_command(session, "customtool process --batch", "/home/user", 130, LONG_OUTPUT, active=84.0)
    n._finish(c, "/home/user", "/home/user")
    assert sp.said[0] == "Interrompu. On y était presque. Après 1 minute 24."


def test_long_command_success_without_output():
    n, session, sp, llm = _narrator()
    c = _finished_command(session, "sync", "/home/user", 0, [], active=84.0)
    n._finish(c, "/home/user", "/home/user")
    assert sp.said == ["Succès, en 1 minute 24."]


def test_long_command_failure_without_output():
    n, session, sp, llm = _narrator()
    c = _finished_command(session, "sync", "/home/user", 3, [], active=84.0)
    n._finish(c, "/home/user", "/home/user")
    assert sp.said == ["Échec, code 3, aucun message, après 1 minute 24."]


def test_long_command_interrupted_without_output():
    n, session, sp, llm = _narrator()
    c = _finished_command(session, "sync", "/home/user", 130, [], active=84.0)
    n._finish(c, "/home/user", "/home/user")
    assert sp.said == ["Interrompu, après 1 minute 24."]


# ---------------------------------------------------------------- non-régression : chemins hors scope

def test_verbatim_short_output_never_reaches_the_llm():
    cfg = Config()
    n, session, sp, llm = _narrator(cfg, pieces=["ne doit jamais être lu"])
    c = _finished_command(session, "customtool status", "/home/user", 0, ["fait."], active=0.5)
    n._finish(c, "/home/user", "/home/user")
    assert llm.calls == 0
    assert sp.said == ["fait."]


def test_verbatim_read_drops_symbol_runs():
    n, session, sp, llm = _narrator(Config(), pieces=["ne doit jamais être lu"])
    c = _finished_command(session, "make", "/home/user", 2,
                          ["make: *** Pas de cible spécifiée et aucun makefile n'a été trouvé. Arrêt."])
    n._finish(c, "/home/user", "/home/user")
    assert llm.calls == 0
    assert sp.said and "*" not in sp.said[0]
    assert "make: Pas de cible spécifiée" in sp.said[0]


def test_verbatim_read_drops_log_tags_and_arrows():
    n, session, sp, llm = _narrator(Config(), pieces=["ne doit jamais être lu"])
    c = _finished_command(session, "helm lint storefront", "/home/user", 0,
                          ["==> Linting storefront", "[INFO] Chart.yaml: icon is recommended",
                           "1 chart(s) linted, 0 chart(s) failed"])
    n._finish(c, "/home/user", "/home/user")
    assert sp.said == ["Linting storefront. Chart.yaml: icon is recommended. 1 chart(s) linted, 0 chart(s) failed"]


def test_resolve_path_never_reaches_the_llm():
    cfg = Config()
    n, session, sp, llm = _narrator(cfg, pieces=["ne doit jamais être lu"])
    output = _fixture("df -h")
    c = _finished_command(session, "df -h", "/home/user", 0, output.splitlines(), active=0.5)
    n._finish(c, "/home/user", "/home/user")
    assert llm.calls == 0
    assert sp.said and "685G" in sp.said[0]


def test_interactive_session_never_reaches_the_llm():
    cfg = Config()
    n, session, sp, llm = _narrator(cfg, pieces=["ne doit jamais être lu"])
    c = _finished_command(session, "ssh hote", "/home/user", 0, ["dernière ligne affichée"], active=0.5)
    c.interactive = True
    n._finish(c, "/home/user", "/home/user")
    assert llm.calls == 0
    assert sp.said == ["Fin de ssh."]


def test_fullscreen_session_never_reaches_the_llm():
    cfg = Config()
    n, session, sp, llm = _narrator(cfg, pieces=["ne doit jamais être lu"])
    c = _finished_command(session, "htop", "/home/user", 0, [], active=0.5)
    c.used_fullscreen = True
    n._finish(c, "/home/user", "/home/user")
    assert llm.calls == 0
    assert sp.said == []  # succès plein écran : rien à dire


class _WarmLLM(FakeLLM):
    def __init__(self):
        super().__init__(())
        self.completed: list[list[dict]] = []

    def complete(self, messages, **kw):
        self.completed.append(messages)
        return ""


@pytest.mark.parametrize("profile", ["generic", "finetuned"])
def test_warm_caches_the_summary_system_prompt_of_the_active_profile(profile):
    from steph import prompts

    cfg = Config()
    cfg.llm_profile = profile
    llm = _WarmLLM()
    Narrator(cfg, Session(), FakeSpeaker(), llm).warm_system_prompts()
    build = prompts.finetuned_summary_messages if profile == "finetuned" else prompts.summary_messages
    assert llm.completed[0][0] == build("true", 0, 0.0, "", 0, language=cfg.language)[0]


def test_fallback_is_said_when_grounding_drops_the_whole_answer():
    n, _, sp, _ = _narrator(pieces=["Échec. 42 fichiers manquants."])
    msgs = [{"role": "system", "content": "s"}, {"role": "user", "content": "Sortie :\nerreur inconnue"}]
    n._llm_say(msgs, "code 1, 1 ligne.", prefix="Échec, code 1. ", strip_status=True)
    assert sp.said[-1] == "Échec, code 1. code 1, 1 ligne."


def test_fallback_is_said_when_only_the_status_survives_grounding_without_strip_status():
    # chemin des détails (strip_status=False) : « Échec. » seul ne dit rien d'utile
    n, _, sp, _ = _narrator(pieces=["Échec. 42 fichiers manquants."])
    msgs = [{"role": "system", "content": "s"}, {"role": "user", "content": "Sortie :\nerreur inconnue"}]
    n._llm_say(msgs, "code 1, 1 ligne.")
    assert sp.said[-1] == "code 1, 1 ligne."


def test_status_followed_by_a_grounded_clause_is_kept_without_strip_status():
    n, _, sp, _ = _narrator(pieces=["Échec. ", "erreur inconnue."])
    msgs = [{"role": "system", "content": "s"}, {"role": "user", "content": "Sortie :\nerreur inconnue"}]
    n._llm_say(msgs, "repli")
    assert sp.said[-1] == "Échec. erreur inconnue."


# --------------------------------------------------- durée en suffixe du flux LLM (étape 3)

def test_llm_say_appends_the_suffix_after_the_stream():
    n, _, sp, _ = _narrator(pieces=["Tout est bon."])
    msgs = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]
    n._llm_say(msgs, "repli", prefix="Succès. ", suffix=" En 5 secondes.")
    assert sp.said[-1] == "Succès. Tout est bon. En 5 secondes."


def test_llm_say_puts_the_fallback_before_the_suffix_when_grounding_empties_the_answer():
    n, _, sp, _ = _narrator(pieces=["Échec. 42 fichiers manquants."])
    msgs = [{"role": "system", "content": "s"}, {"role": "user", "content": "Sortie :\nerreur inconnue"}]
    n._llm_say(msgs, "code 1, 1 ligne.", prefix="Échec, code 1. ", suffix=" Après 1 minute.", strip_status=True)
    assert sp.said[-1] == "Échec, code 1. code 1, 1 ligne. Après 1 minute."


# ------------------------------------------- déchargement au repos + rechargement anticipé (Q2b)

def test_maybe_unload_idle_llm_does_nothing_when_disabled():
    cfg = Config()
    cfg.llm_idle_unload_minutes = 0
    n, _, _, llm = _narrator(cfg)
    llm._idle_seconds = 999999
    n._maybe_unload_idle_llm()
    assert llm.stopped is False
    assert n.llm_ready is True


def test_maybe_unload_idle_llm_does_nothing_below_the_threshold():
    cfg = Config()
    cfg.llm_idle_unload_minutes = 10
    n, _, _, llm = _narrator(cfg)
    llm._idle_seconds = 5 * 60
    n._maybe_unload_idle_llm()
    assert llm.stopped is False
    assert n.llm_ready is True


def test_maybe_unload_idle_llm_unloads_and_logs_after_the_threshold():
    cfg = Config()
    cfg.llm_idle_unload_minutes = 10
    logs = []
    n, _, _, llm = _narrator(cfg)
    n._log = lambda msg: logs.append(msg)
    llm._idle_seconds = 11 * 60
    n._maybe_unload_idle_llm()
    assert llm.stopped is True
    assert n.llm_ready is False
    assert any("déchargé" in m for m in logs)


def test_maybe_unload_idle_llm_never_interrupts_a_generation_in_this_window():
    cfg = Config()
    cfg.llm_idle_unload_minutes = 10
    n, _, _, llm = _narrator(cfg)
    llm._idle_seconds = 11 * 60
    llm.active = 1
    n._maybe_unload_idle_llm()
    assert llm.stopped is False
    assert n.llm_ready is True


def test_maybe_unload_idle_llm_never_interrupts_its_own_warmup():
    cfg = Config()
    cfg.llm_idle_unload_minutes = 10
    n, _, _, llm = _narrator(cfg)
    n._warming = True
    llm._idle_seconds = 11 * 60
    n._maybe_unload_idle_llm()
    assert llm.stopped is False
    assert n.llm_ready is True


def test_maybe_unload_idle_llm_resyncs_when_another_window_already_unloaded():
    """`try_unload_idle` renvoie False sans rien faire si un autre processus a déjà
    déchargé le serveur : cette fenêtre doit s'aligner sur `healthy()` sans le
    journaliser comme si elle l'avait fait elle-même."""
    cfg = Config()
    cfg.llm_idle_unload_minutes = 10
    logs = []
    n, _, _, llm = _narrator(cfg)
    n._log = lambda msg: logs.append(msg)
    llm._idle_seconds = 11 * 60
    llm.healthy_value = False  # déjà arrêté ailleurs : try_unload_idle ne fait rien
    n._maybe_unload_idle_llm()
    assert llm.stopped is False
    assert n.llm_ready is False
    assert not any("déchargé" in m for m in logs)


def test_on_command_start_triggers_an_anticipatory_reload_when_not_ready():
    n, session, sp, llm = _narrator()
    n.llm_ready = False
    llm.healthy_value = True
    n.on_command_start("find / -maxdepth 1")
    assert n._recovered.wait(1.0)
    assert llm.ensure_calls == 1
    assert n.llm_ready is True


def test_on_command_start_does_nothing_when_already_ready():
    n, session, sp, llm = _narrator()
    n.llm_ready = True
    n.on_command_start("pwd")
    assert llm.ensure_calls == 0


def test_on_command_start_respects_the_anticipatory_reload_setting():
    cfg = Config()
    cfg.llm_anticipatory_reload = False
    n, session, sp, llm = _narrator(cfg)
    n.llm_ready = False
    n.on_command_start("find / -maxdepth 1")
    time.sleep(0.05)
    assert llm.ensure_calls == 0
    assert n._recovering is False


def test_llm_say_falls_back_immediately_when_nothing_is_recovering():
    """Pas de rechargement en cours (sondage récent déjà négatif) : repli déterministe
    tout de suite, sans attendre ni toucher au modèle."""
    n, _, sp, llm = _narrator(pieces=["ne doit jamais être lu"])
    n.llm_ready = False
    n._last_health = time.time()  # empêche _llm_ok() de relancer un sondage
    n._recovering = False
    msgs = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]
    n._llm_say(msgs, "repli déterministe", prefix="Succès. ")
    assert sp.said == ["Succès. repli déterministe"]
    assert llm.calls == 0


def test_llm_say_waits_for_an_in_progress_reload_then_streams_the_real_summary():
    cfg = Config()
    cfg.llm_reload_grace_seconds = 2.0
    n, _, sp, llm = _narrator(cfg, pieces=["Le vrai résumé."])
    n.llm_ready = False
    n._last_health = time.time()
    n._recovering = True
    n._recovered.clear()

    def finish_reload():
        time.sleep(0.05)
        n.llm_ready = True
        n._recovering = False
        n._recovered.set()

    threading.Thread(target=finish_reload).start()
    msgs = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]
    n._llm_say(msgs, "repli jamais utilisé", prefix="Succès. ")
    assert sp.said[-1] == "Succès. Le vrai résumé."
    assert llm.calls == 1


def test_llm_say_falls_back_after_the_grace_period_expires_without_calling_the_llm():
    cfg = Config()
    cfg.llm_reload_grace_seconds = 0.05
    n, _, sp, llm = _narrator(cfg, pieces=["ne doit jamais être lu"])
    n.llm_ready = False
    n._last_health = time.time()
    n._recovering = True
    n._recovered.clear()  # ne sera jamais mis à True dans ce test : simule un rechargement bloqué
    msgs = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]
    n._llm_say(msgs, "repli déterministe", prefix="Succès. ")
    assert sp.said[-1] == "Succès. repli déterministe"
    assert llm.calls == 0
