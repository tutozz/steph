"""P20 : masquage de l'attente des questions (F7).

Une question dont l'historique n'est pas encore lu par le modèle attend toute la lecture du
prompt : jusqu'à 14 s sur l'i5 pour 3 000 jetons. Une phrase courte part tout de suite,
dite seulement : ni la fenêtre de questions, ni l'historique des échanges, ni l'entrée du
modèle ne la voient. Historique déjà préchauffé : aucune phrase, la réponse arrive en 0,3 s.
"""

import queue
import threading
import time

from steph.config import Config
from steph.narrator import Narrator
from steph.server import ControlServer
from steph.session import Session
from steph.strings import t as tr
from steph.tts import prewarm_phrases

LONG_OUTPUT = "\n".join(f"ligne {i} : compilation du module {i}" for i in range(80))


class Speaker:
    def __init__(self):
        self.speaking = threading.Event()
        self._q: queue.Queue = queue.Queue()
        self.said: list[str] = []
        self._threads: list[threading.Thread] = []

    def say(self, text, interrupt=True, on_done=None, force=False):
        self.say_stream([text], interrupt, on_done, force)

    def say_stream(self, pieces, interrupt=True, on_done=None, force=False):
        # le flux d'une question arrive pendant _ask : consommé à part, comme le vrai Speaker
        th = threading.Thread(target=lambda: self.said.append("".join(pieces)), daemon=True)
        th.start()
        self._threads.append(th)

    def join(self):
        for th in self._threads:
            th.join(timeout=5)

    def stop(self):
        pass


class LLM:
    def __init__(self, answer="Compilation, 80 lignes."):
        self.answer = answer
        self.streamed: list[list[dict]] = []
        self.warmed: list[list[dict]] = []
        self.active = 0
        self.last_done = 0.0
        self.healthy_value = True

    def stream(self, messages, **kw):
        self.streamed.append(messages)
        yield from self.answer.split(" ")[:1]
        for w in self.answer.split(" ")[1:]:
            yield " " + w

    def complete(self, messages, **kw):
        self.warmed.append(messages)
        return ""

    def healthy(self):
        return self.healthy_value

    def idle_seconds(self):
        return 3600.0

    def try_unload_idle(self, minutes):
        self.healthy_value = False
        return True


def _setup(language="fr", tokens_per_sec=10.0, output=LONG_OUTPUT):
    cfg = Config()
    cfg.llm_profile = "finetuned"
    cfg.language = language
    cfg.ground_output = False
    cfg.llm_prompt_tokens_per_sec = tokens_per_sec
    s = Session()
    s.cwd = "~/app"
    sp = Speaker()
    llm = LLM()
    nar = Narrator(cfg, s, sp, llm)
    nar.llm_ready = True
    _command(s, "make", output)
    srv = ControlServer.__new__(ControlServer)
    srv.nar = nar
    return nar, srv, sp, llm


def _command(s, cmd, output):
    c = s.start(cmd)
    c.feed(output.encode())
    c.end = c.start + 2
    c.exit = 0


def _ask(srv, question="Combien de lignes ?", speak=True):
    sent = []
    srv._ask(question, lambda obj: sent.append(obj.get("t", "")) or True, speak=speak)
    srv.nar.sp.join()
    return "".join(sent)


def _warm(nar):
    nar._warm_pending = True
    nar._maybe_warm()
    deadline = time.time() + 5
    while nar._warming and time.time() < deadline:
        time.sleep(0.01)
    assert not nar._warming


def test_cold_history_says_the_wait_phrase_first():
    nar, srv, sp, llm = _setup()
    _ask(srv)
    assert sp.said[-1].startswith(tr("fr", "qa_wait"))


def test_wait_phrase_never_reaches_the_window_nor_the_exchange_history():
    nar, srv, sp, llm = _setup()
    text = _ask(srv)
    phrase = tr("fr", "qa_wait")
    assert phrase not in text
    assert text == "Compilation, 80 lignes."
    assert phrase not in nar.s.qa[-1]["a"]


def test_model_input_keeps_the_trained_question_format():
    nar, srv, sp, llm = _setup()
    prefix = nar.qa_messages()
    _ask(srv, "Combien de lignes ?")
    assert llm.streamed[-1] == prefix + [{"role": "user", "content": "(dossier actuel : ~/app)\nCombien de lignes ?"}]


def test_no_wait_phrase_once_the_history_is_warm():
    nar, srv, sp, llm = _setup()
    _warm(nar)
    _ask(srv)
    assert sp.said[-1] == "Compilation, 80 lignes."


def test_no_wait_phrase_when_reading_the_prompt_is_faster_than_the_phrase():
    nar, srv, sp, llm = _setup(tokens_per_sec=1e6)
    _ask(srv)
    assert sp.said[-1] == "Compilation, 80 lignes."


def test_second_question_without_new_command_needs_no_phrase():
    nar, srv, sp, llm = _setup()
    _ask(srv, "Combien de lignes ?")
    _ask(srv, "Quel module en dernier ?")
    assert sp.said[-1] == "Compilation, 80 lignes."


def test_new_command_after_the_warm_brings_the_phrase_back():
    nar, srv, sp, llm = _setup()
    _warm(nar)
    _command(nar.s, "make test", LONG_OUTPUT)
    _ask(srv)
    assert sp.said[-1].startswith(tr("fr", "qa_wait"))


def test_unloaded_model_forgets_the_warm_history():
    nar, srv, sp, llm = _setup()
    nar.cfg.llm_idle_unload_minutes = 1
    _warm(nar)
    nar._maybe_unload_idle_llm()
    assert nar.llm_ready is False
    llm.healthy_value = True
    nar.llm_ready = True
    _ask(srv)
    assert sp.said[-1].startswith(tr("fr", "qa_wait"))


def test_interrupted_warm_does_not_count_as_warm():
    nar, srv, sp, llm = _setup()

    def fail(messages, **kw):
        raise ConnectionError("coupé")

    llm.complete = fail
    _warm(nar)
    assert nar._warm_pending is True
    _ask(srv)
    assert sp.said[-1].startswith(tr("fr", "qa_wait"))


def test_muted_question_says_nothing():
    nar, srv, sp, llm = _setup()
    text = _ask(srv, speak=False)
    assert sp.said == []
    assert text == "Compilation, 80 lignes."


def test_english_wait_phrase():
    nar, srv, sp, llm = _setup(language="en")
    _ask(srv, "How many lines?")
    assert sp.said[-1].startswith(tr("en", "qa_wait"))
    assert tr("en", "qa_wait") != tr("fr", "qa_wait")


def test_wait_phrase_is_short_and_prewarmed():
    for language in ("fr", "en"):
        phrase = tr(language, "qa_wait").strip()
        assert 0 < len(phrase) <= 40
        assert phrase in prewarm_phrases(language)
