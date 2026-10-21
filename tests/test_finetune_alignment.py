"""P18 : garde-fou d'alignement entre le format d'entraînement du petit modèle affiné
(bench/matrix/finetune/label.py) et ce que steph lui enverrait en production
(tâches P18 et B3).

B3 (brancher le modèle affiné dans narrator.py) n'est pas encore faite. Ces tests
portent donc sur `prompts.finetuned_summary_messages`, la fonction proposée que B3
devra appeler à la place de `summary_messages()` quand `cfg.model` est un modèle
affiné. Ils échouent si `label.py` (ce que le corpus a appris) et `prompts.py` (ce
que steph enverrait) divergent, dans un sens ou dans l'autre : c'est exactement le
bogue d'origine (Gemma 82 -> 59, prompt SUMMARY_SYSTEM envoyé à un modèle qui n'a
appris que TRAIN_SYSTEM).
"""

import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bench" / "matrix" / "finetune"))

import build_feature_corpus  # noqa: E402
import label_features  # noqa: E402
from label import TRAIN_SYSTEM, TRAIN_SYSTEM_EN, build_messages, train_system_for  # noqa: E402

from steph.config import Config  # noqa: E402
from steph.digest import digest  # noqa: E402
from steph.narrator import (  # noqa: E402
    FINETUNED_DETAIL_CHARS,
    FINETUNED_QA_BUDGET_CHARS,
    FINETUNED_SUMMARY_CHARS,
    Narrator,
)
from steph.prompts import (  # noqa: E402
    DETAILS_SYSTEM,
    DETAILS_SYSTEM_FINETUNED,
    DETAILS_SYSTEM_FINETUNED_EN,
    PROGRESS_SYSTEM_FINETUNED,
    PROGRESS_SYSTEM_FINETUNED_EN,
    START_SYSTEM_FINETUNED,
    START_SYSTEM_FINETUNED_EN,
    SUMMARY_SYSTEM,
    SUMMARY_SYSTEM_FINETUNED,
    SUMMARY_SYSTEM_FINETUNED_EN,
    finetuned_summary_messages,
)
from steph.session import Session  # noqa: E402
from steph.textproc import compact_output  # noqa: E402

REC = {
    "cmd": "df -h",
    "exit": 0,
    "duration": 0.1,
    "output": (
        "Filesystem      Size  Used Avail Use% Mounted on\n"
        "/dev/root       953G  268G  685G  29% /\n"
    ),
}


def _sent(rec: dict, language: str = "fr") -> list[dict]:
    """Ce que finetuned_summary_messages enverrait, avec le même digest que narrator.py
    calcule avant d'appeler summary_messages (narrator.py:575) : passer la sortie brute
    non digérée ne testerait rien de réel, steph ne l'envoie jamais telle quelle."""
    lines = rec["output"].splitlines()
    out = digest(rec["cmd"], rec["output"], 1500, language=language) or compact_output(lines, 1500)
    return finetuned_summary_messages(rec["cmd"], rec["exit"], rec["duration"], out, len(lines), language=language)


def _trained(rec: dict, language: str = "fr") -> list[dict]:
    """Reproduit train_msgs de label.py:run_corpus.work() (label.py:163-165) : système
    TRAIN_SYSTEM, tour utilisateur de build_messages (celui envoyé à l'enseignant)."""
    user = build_messages(rec, 1500, language)[1]["content"]
    return [{"role": "system", "content": train_system_for(language)}, {"role": "user", "content": user}]


def test_finetuned_system_prompt_is_byte_identical_to_train_system():
    """Coeur du contrôle P18 : si label.py change TRAIN_SYSTEM sans que prompts.py
    suive (ou l'inverse), le prochain modèle affiné apprend un prompt que B3
    n'enverra jamais, ou reçoit un prompt qu'aucun modèle affiné n'a appris."""
    assert SUMMARY_SYSTEM_FINETUNED == TRAIN_SYSTEM


def test_finetuned_system_prompt_en_is_byte_identical_to_train_system_en():
    assert SUMMARY_SYSTEM_FINETUNED_EN == TRAIN_SYSTEM_EN


def test_finetuned_system_prompt_is_not_the_production_summary_prompt():
    """Régression du bogue d'origine : un modèle affiné n'a jamais vu SUMMARY_SYSTEM
    (long, avec exemples), seulement TRAIN_SYSTEM (court)."""
    assert SUMMARY_SYSTEM_FINETUNED != SUMMARY_SYSTEM


def test_finetuned_summary_messages_system_turn_matches_training_system():
    assert _sent(REC)[0]["content"] == _trained(REC)[0]["content"]


def test_finetuned_summary_messages_user_turn_matches_training_input():
    """Le tour utilisateur doit être EXACTEMENT celui que label.py a écrit dans les
    étiquettes d'entraînement pour un enregistrement équivalent : même digest, même
    gabarit Commande/Statut/Durée/Sortie. Casse si `finetuned_summary_messages`
    reconstruit un jour son propre gabarit au lieu de déléguer à `summary_messages`."""
    assert _sent(REC)[1]["content"] == _trained(REC)[1]["content"]


def test_finetuned_summary_messages_en_matches_training_input():
    sent = _sent(REC, language="en")
    trained = _trained(REC, language="en")
    assert sent[0]["content"] == trained[0]["content"]
    assert sent[1]["content"] == trained[1]["content"]


# ================================================================ B3 : chemin réel du Narrator
#
# Les tests ci-dessus comparent prompts.finetuned_summary_messages() à label.py, mais B3
# n'était pas branché dans narrator.py : rien ne garantissait que _finish() appelle
# réellement cette fonction en profil affiné. Ces tests font tourner le vrai Narrator
# (comme tests/test_narrator.py) pour fermer ce trou.

class _FakeSpeaker:
    """Double minimal de Speaker : consomme le flux tout de suite, sans thread ni audio."""

    def __init__(self):
        self.said: list[str] = []
        self.speaking = threading.Event()

    def say(self, text, interrupt=True, on_done=None):
        self.say_stream([text], interrupt=interrupt, on_done=on_done)

    def say_stream(self, pieces, interrupt=True, on_done=None):
        text = "".join(pieces)
        self.said.append(text)
        if on_done:
            on_done(text)

    def stop(self):
        pass


class _RecordingLLM:
    """Double de LLM qui capture les messages envoyés à .stream(), pour vérifier le chemin
    réel de narrator._finish plutôt que prompts.finetuned_summary_messages() en isolation."""

    def __init__(self, pieces):
        self.pieces = list(pieces)
        self.sent: list[list[dict]] = []
        self.completed: list[list[dict]] = []

    def stream(self, messages, max_tokens=90, **kw):
        self.sent.append(messages)
        yield from self.pieces

    def complete(self, messages, **kw):
        self.completed.append(messages)
        return "".join(self.pieces)


def _finished(session: Session, cmd: str, exit_code: int, output: str, active: float = 0.5):
    lines = output.splitlines()
    c = session.start(cmd)
    c.enter_at = c.start
    c.end = c.start + active
    c.exit = exit_code
    c.out.lines = list(lines)
    c.out.total_lines = len(lines)
    return c


# aucun résolveur déterministe (resolve()) ni famille de digest() ne reconnaît « customtool » :
# la commande passe forcément par le LLM, comme dans tests/test_narrator.py (LONG_OUTPUT).
_CMD = "customtool dump --all"
_LONG_OUTPUT = "\n".join(
    f"ligne {i:03d} : contenu qui dépasse largement le palier affiné de 587 caractères, pour de vrai"
    for i in range(30)
)


def test_finetuned_summary_chars_matches_the_granite200_tier_from_make_cases_compact():
    """FINETUNED_SUMMARY_CHARS (narrator.py) doit être lu depuis le palier retenu par P11,
    jamais réinventé : bench/matrix/make_cases_compact.py VARIANTS["granite200"]."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bench" / "matrix"))
    import make_cases_compact  # noqa: E402

    assert FINETUNED_SUMMARY_CHARS == make_cases_compact.VARIANTS["granite200"]


def test_finetuned_qa_budget_chars_matches_the_h2_decision_in_qa_corpus():
    """FINETUNED_QA_BUDGET_CHARS doit être le plafond réellement utilisé par P15a/H2 pour
    entraîner le mode questions (qa_corpus.py DEFAULT_BUDGET_CHARS), pas une valeur inventée."""
    import qa_corpus  # déjà sur sys.path : bench/matrix/finetune, inséré en tête de fichier

    assert FINETUNED_QA_BUDGET_CHARS == qa_corpus.DEFAULT_BUDGET_CHARS


def test_llm_profile_defaults_to_generic_until_the_b4_catalog_exists():
    """B4 (catalogue LLM) n'existe pas encore : rien ne permet de déduire le profil du seul
    champ `model`, le défaut ne doit donc jamais basculer seul vers le prompt affiné."""
    assert Config().llm_profile == "generic"


def test_narrator_finish_sends_finetuned_messages_matching_build_messages_when_profile_is_finetuned():
    """Coeur B3 : le message réellement envoyé par narrator._finish() en profil affiné doit
    être celui que label.build_messages() a écrit dans les étiquettes, pour un même
    enregistrement digéré au même plafond (FINETUNED_SUMMARY_CHARS)."""
    cfg = Config(llm_profile="finetuned")
    session = Session()
    llm = _RecordingLLM(["résultat."])
    nar = Narrator(cfg, session, _FakeSpeaker(), llm)
    nar.llm_ready = True
    c = _finished(session, _CMD, 0, _LONG_OUTPUT)
    nar._finish(c, "/home/user", "/home/user")

    assert len(llm.sent) == 1
    sent = llm.sent[0]
    rec = {"cmd": _CMD, "exit": 0, "duration": c.duration, "output": _LONG_OUTPUT}
    expected_user = build_messages(rec, FINETUNED_SUMMARY_CHARS, "fr")[1]["content"]
    assert sent[0]["content"] == TRAIN_SYSTEM
    assert sent[1]["content"] == expected_user


def test_narrator_finish_uses_the_generic_prompt_and_summary_chars_by_default():
    """Non-régression : sans `llm_profile = "finetuned"`, narrator._finish() garde le
    comportement de production actuel (SUMMARY_SYSTEM, plafond cfg.summary_chars)."""
    cfg = Config()  # llm_profile="generic" par défaut
    session = Session()
    llm = _RecordingLLM(["résultat."])
    nar = Narrator(cfg, session, _FakeSpeaker(), llm)
    nar.llm_ready = True
    c = _finished(session, _CMD, 0, _LONG_OUTPUT)
    nar._finish(c, "/home/user", "/home/user")

    sent = llm.sent[0]
    assert sent[0]["content"] == SUMMARY_SYSTEM
    out = digest(_CMD, _LONG_OUTPUT, cfg.summary_chars, "fr") or compact_output(_LONG_OUTPUT.splitlines(), cfg.summary_chars)
    assert out in sent[1]["content"]


def test_narrator_finish_caps_the_digest_to_the_finetuned_tier_instead_of_cfg_summary_chars():
    """Plafond d'entrée (B3, point 2) : en profil affiné, la sortie envoyée au modèle est
    celle digérée à FINETUNED_SUMMARY_CHARS (587, palier granite200), jamais à
    cfg.summary_chars (1500, calibré pour SUMMARY_SYSTEM), même si celui-ci garde sa valeur
    par défaut (donc rien ne masquerait accidentellement un oubli du plafond dédié)."""
    finetuned_out = digest(_CMD, _LONG_OUTPUT, FINETUNED_SUMMARY_CHARS, "fr") or compact_output(
        _LONG_OUTPUT.splitlines(), FINETUNED_SUMMARY_CHARS)
    generic_out = digest(_CMD, _LONG_OUTPUT, 1500, "fr") or compact_output(_LONG_OUTPUT.splitlines(), 1500)
    assert finetuned_out != generic_out  # le test doit bien porter sur deux plafonds distincts

    cfg = Config(llm_profile="finetuned")
    session = Session()
    llm = _RecordingLLM(["résultat."])
    nar = Narrator(cfg, session, _FakeSpeaker(), llm)
    nar.llm_ready = True
    c = _finished(session, _CMD, 0, _LONG_OUTPUT)
    nar._finish(c, "/home/user", "/home/user")

    sent_user = llm.sent[0][1]["content"]
    assert finetuned_out in sent_user
    assert generic_out not in sent_user


# ---------------------------------------------------------------- B3 : mode questions (H2)

def _seed_big_history(session: Session, n: int = 6) -> None:
    big = [f"ligne {i:04d} : " + "x" * 80 for i in range(40)]  # >> qa_block_chars (2500) par commande
    for i in range(n):
        c = session.start(f"cmd{i}")
        c.end = c.start + 0.1
        c.exit = 0
        c.out.lines = list(big)
        c.out.total_lines = len(big)


def test_qa_messages_caps_history_to_8000_chars_in_finetuned_profile():
    session = Session()
    _seed_big_history(session)
    nar = Narrator(Config(llm_profile="finetuned"), session, _FakeSpeaker(), _RecordingLLM([]))
    ctx = nar.qa_messages()[1]["content"]
    assert "commandes plus anciennes omises" in ctx


def test_qa_messages_keeps_the_36000_char_budget_in_generic_profile():
    session = Session()
    _seed_big_history(session)
    nar = Narrator(Config(), session, _FakeSpeaker(), _RecordingLLM([]))
    ctx = nar.qa_messages()[1]["content"]
    assert "commandes plus anciennes omises" not in ctx


# ---------------------------------------------------------------- K3 : corpus unifié (compose_k3.py)

def _k3_sent_and_trained(language: str):
    import compose_k3  # bench/matrix/finetune, déjà sur sys.path

    cfg = Config(llm_profile="finetuned", language=language)
    session = Session()
    llm = _RecordingLLM(["résultat."])
    nar = Narrator(cfg, session, _FakeSpeaker(), llm)
    nar.llm_ready = True
    c = _finished(session, _CMD, 1, _LONG_OUTPUT)
    nar._finish(c, "/home/user", "/home/user")
    rec = {"cmd": _CMD, "exit": 1, "duration": c.duration, "output": _LONG_OUTPUT}
    trained = compose_k3.rebuild_summary("x", rec, FINETUNED_SUMMARY_CHARS, language)
    return llm.sent[0], trained


def test_k3_french_summary_rows_match_what_the_narrator_sends():
    sent, trained = _k3_sent_and_trained("fr")
    assert sent[:2] == trained[:2]


def test_k3_english_summary_rows_match_what_the_narrator_sends():
    """K2 + K3 : l'anglais entre au corpus ; ses lignes doivent porter TRAIN_SYSTEM_EN et le
    tour utilisateur anglais que steph envoie en profil affiné, au même plafond."""
    sent, trained = _k3_sent_and_trained("en")
    assert sent[0]["content"] == TRAIN_SYSTEM_EN
    assert sent[:2] == trained[:2]


# ================================================================ B3b : détail, début, progression (K3)
#
# H3a/K3 ont livré un corpus entraîné pour ces trois fonctionnalités (bench/matrix/finetune/
# label_features.py, build_feature_corpus.py) : le test ci-dessus (`test_details_prompt_
# ignores_llm_profile_no_finetuned_equivalent_yet`) qui interdisait tout branchement est
# retiré, remplacé par les tests qui suivent. Corpus FR uniquement au moment de B3b
# (build_feature_corpus.py n'appelait jamais ses fonctions `*_messages` avec `language="en"`) :
# le profil affiné ne basculait ces trois fonctionnalités que si `cfg.language == "fr"`.
#
# B3c (commit cdb0802, R1 steph-speak v1.0) : le corpus anglais existe désormais
# (TRAIN_DETAILS_SYSTEM_EN, TRAIN_START_SYSTEM_EN, TRAIN_PROGRESS_SYSTEM_EN dans
# label_features.py, entrées construites par build_feature_corpus.py --lang en). Le
# profil affiné bascule donc aussi en anglais ; seule une langue hors fr/en resterait
# une erreur d'appelant.

def test_details_system_finetuned_is_byte_identical_to_train_details_system():
    assert DETAILS_SYSTEM_FINETUNED == label_features.TRAIN_DETAILS_SYSTEM


def test_details_system_finetuned_en_is_byte_identical_to_train_details_system_en():
    assert DETAILS_SYSTEM_FINETUNED_EN == label_features.TRAIN_DETAILS_SYSTEM_EN


def test_start_system_finetuned_is_byte_identical_to_train_start_system():
    assert START_SYSTEM_FINETUNED == label_features.TRAIN_START_SYSTEM


def test_start_system_finetuned_en_is_byte_identical_to_train_start_system_en():
    assert START_SYSTEM_FINETUNED_EN == label_features.TRAIN_START_SYSTEM_EN


def test_progress_system_finetuned_is_byte_identical_to_train_progress_system():
    assert PROGRESS_SYSTEM_FINETUNED == label_features.TRAIN_PROGRESS_SYSTEM


def test_progress_system_finetuned_en_is_byte_identical_to_train_progress_system_en():
    assert PROGRESS_SYSTEM_FINETUNED_EN == label_features.TRAIN_PROGRESS_SYSTEM_EN


def test_finetuned_detail_chars_matches_build_feature_corpus_max_chars():
    """FINETUNED_DETAIL_CHARS (narrator.py) doit être le plafond réellement utilisé pour
    construire le corpus détail (build_feature_corpus.py MAX_CHARS = 1500), pas une valeur
    inventée ni FINETUNED_SUMMARY_CHARS (587, propre au résumé/granite200)."""
    assert FINETUNED_DETAIL_CHARS == build_feature_corpus.MAX_CHARS


# ---------------------------------------------------------------- détail (narrator._details)

def test_narrator_details_sends_train_details_system_matching_build_feature_corpus_in_finetuned_fr():
    """Coeur B3b (détail) : le message réellement envoyé par narrator._details() en profil
    affiné français doit être celui que build_feature_corpus.detail_entry() a écrit au
    corpus, pour un même enregistrement digéré au même plafond (FINETUNED_DETAIL_CHARS)."""
    cfg = Config(llm_profile="finetuned")
    session = Session()
    llm = _RecordingLLM(["détail."])
    nar = Narrator(cfg, session, _FakeSpeaker(), llm)
    nar.llm_ready = True
    c = _finished(session, _CMD, 0, _LONG_OUTPUT)
    nar._details(c)

    rec = {"cmd": _CMD, "exit": 0, "duration": c.duration, "output": _LONG_OUTPUT}
    expected_user = build_feature_corpus.detail_entry(rec)["messages"][1]["content"]
    assert llm.sent[0][0]["content"] == label_features.TRAIN_DETAILS_SYSTEM
    assert llm.sent[0][1]["content"] == expected_user


def test_narrator_details_caps_the_input_to_1500_chars_only_in_finetuned_profile_fr():
    """Plafond d'entrée (B3b) : `_details()` doit digérer/compacter à FINETUNED_DETAIL_CHARS
    (1500) en profil affiné, jamais au plafond générique (`c.compact(6000)`, sans digest())
    que `_details()` garde hors profil affiné - même si celui-ci reste à sa valeur par
    défaut (donc rien ne masquerait accidentellement un oubli du plafond dédié)."""
    cfg = Config(llm_profile="finetuned")
    session = Session()
    llm = _RecordingLLM(["détail."])
    nar = Narrator(cfg, session, _FakeSpeaker(), llm)
    nar.llm_ready = True
    c = _finished(session, _CMD, 0, _LONG_OUTPUT)

    finetuned_out = (digest(_CMD, "\n".join(c.all_lines()), FINETUNED_DETAIL_CHARS, "fr")
                     or c.compact(FINETUNED_DETAIL_CHARS))
    generic_out = c.compact(6000)
    assert finetuned_out != generic_out  # le fixture doit distinguer les deux plafonds

    nar._details(c)
    sent_user = llm.sent[0][1]["content"]
    assert finetuned_out in sent_user
    assert generic_out not in sent_user


def test_narrator_details_sends_train_details_system_en_matching_build_feature_corpus_in_finetuned_en():
    """B3c : le corpus détail existe aussi en anglais (label_features.TRAIN_DETAILS_SYSTEM_EN,
    build_feature_corpus.detail_entry(lang="en")) - narrator._details() doit maintenant
    basculer aussi en anglais, exactement comme en français (voir test _fr ci-dessus)."""
    cfg = Config(llm_profile="finetuned", language="en")
    session = Session()
    llm = _RecordingLLM(["detail."])
    nar = Narrator(cfg, session, _FakeSpeaker(), llm)
    nar.llm_ready = True
    c = _finished(session, _CMD, 0, _LONG_OUTPUT)
    nar._details(c)

    rec = {"cmd": _CMD, "exit": 0, "duration": c.duration, "output": _LONG_OUTPUT}
    expected_user = build_feature_corpus.detail_entry(rec, lang="en")["messages"][1]["content"]
    assert llm.sent[0][0]["content"] == label_features.TRAIN_DETAILS_SYSTEM_EN
    assert llm.sent[0][1]["content"] == expected_user


def test_narrator_details_caps_the_input_to_1500_chars_only_in_finetuned_profile_en():
    """Même plafond dédié qu'en français (FINETUNED_DETAIL_CHARS, pas le générique 6000),
    cette fois avec un digest anglais."""
    cfg = Config(llm_profile="finetuned", language="en")
    session = Session()
    llm = _RecordingLLM(["detail."])
    nar = Narrator(cfg, session, _FakeSpeaker(), llm)
    nar.llm_ready = True
    c = _finished(session, _CMD, 0, _LONG_OUTPUT)

    finetuned_out = (digest(_CMD, "\n".join(c.all_lines()), FINETUNED_DETAIL_CHARS, "en")
                     or c.compact(FINETUNED_DETAIL_CHARS))
    generic_out = c.compact(6000)
    assert finetuned_out != generic_out  # le fixture doit distinguer les deux plafonds

    nar._details(c)
    sent_user = llm.sent[0][1]["content"]
    assert finetuned_out in sent_user
    assert generic_out not in sent_user


def test_narrator_details_keeps_the_generic_prompt_and_6000_cap_outside_finetuned_profile():
    """Non-régression : hors profil affiné, `_details()` garde exactement son comportement
    actuel (DETAILS_SYSTEM, `c.compact(6000)`)."""
    cfg = Config()
    session = Session()
    llm = _RecordingLLM(["détail."])
    nar = Narrator(cfg, session, _FakeSpeaker(), llm)
    nar.llm_ready = True
    c = _finished(session, _CMD, 0, _LONG_OUTPUT)
    nar._details(c)
    assert llm.sent[0][0]["content"] == DETAILS_SYSTEM
    assert c.compact(6000) in llm.sent[0][1]["content"]


# ---------------------------------------------------------------- annonce de début (narrator._tick)

def test_narrator_tick_sends_train_start_system_matching_build_feature_corpus_in_finetuned_fr():
    """Coeur B3b (début) : la commande ne matche aucun patron KNOWN_START (_CMD), donc
    narrator._tick() passe par le LLM ; en profil affiné français, il doit envoyer
    exactement ce que build_feature_corpus.start_entry() a écrit au corpus."""
    cfg = Config(llm_profile="finetuned")
    session = Session()
    llm = _RecordingLLM(["fait quelque chose."])
    nar = Narrator(cfg, session, _FakeSpeaker(), llm)
    nar.llm_ready = True
    c = session.start(_CMD)
    c.start -= 10.0  # au-delà de cfg.first_update_after (4.0 s par défaut)
    nar._tick()

    expected = build_feature_corpus.start_entry({"cmd": _CMD})["messages"]
    assert len(llm.completed) == 1
    assert llm.completed[0][0]["content"] == label_features.TRAIN_START_SYSTEM
    assert llm.completed[0][1]["content"] == expected[1]["content"] == _CMD


def test_narrator_tick_sends_train_start_system_en_matching_build_feature_corpus_in_finetuned_en():
    """B3c : TRAIN_START_SYSTEM_EN existe désormais (label_features.py, commit cdb0802) -
    narrator._tick() doit basculer en anglais exactement comme en français."""
    cfg = Config(llm_profile="finetuned", language="en")
    session = Session()
    llm = _RecordingLLM(["does something."])
    nar = Narrator(cfg, session, _FakeSpeaker(), llm)
    nar.llm_ready = True
    c = session.start(_CMD)
    c.start -= 10.0
    nar._tick()

    expected = build_feature_corpus.start_entry({"cmd": _CMD}, lang="en")["messages"]
    assert len(llm.completed) == 1
    assert llm.completed[0][0]["content"] == label_features.TRAIN_START_SYSTEM_EN
    assert llm.completed[0][1]["content"] == expected[1]["content"] == _CMD


def test_narrator_tick_keeps_the_generic_start_prompt_outside_finetuned_profile():
    """Non-régression : hors profil affiné, `_tick()` garde START_SYSTEM (production)."""
    from steph.prompts import START_SYSTEM

    cfg = Config()
    session = Session()
    llm = _RecordingLLM(["fait quelque chose."])
    nar = Narrator(cfg, session, _FakeSpeaker(), llm)
    nar.llm_ready = True
    c = session.start(_CMD)
    c.start -= 10.0
    nar._tick()
    assert llm.completed[0][0]["content"] == START_SYSTEM


# ---------------------------------------------------------------- progression (narrator._tick)

_TAIL_LINE = "ligne longue qui dépasse 166 caractères une fois répétée pour forcer le dépassement du plafond générique de 2500 caractères sur 15 lignes cumulées, afin que le test distingue vraiment les deux plafonds"


def _progressing(session: Session, cmd: str = _CMD):
    c = session.start(cmd)
    c.start -= 100.0  # au-delà de cfg.first_update_after (4 s par défaut)
    c.announced_start = True
    c.last_update_at = c.start  # au-delà de cfg.update_interval (12 s par défaut)
    c.last_output_at = c.start
    lines = [f"{_TAIL_LINE} {i}" for i in range(15)]
    c.out.lines = list(lines)
    c.out.total_lines = len(lines)
    c.lines_at_last_update = 0  # new_lines > 0 : force le passage par le LLM
    return c


def test_narrator_tick_sends_train_progress_system_and_uncapped_recent_in_finetuned_profile_fr():
    """Coeur B3b (progression) : en profil affiné français, `_tick()` doit envoyer
    PROGRESS_SYSTEM_FINETUNED (= TRAIN_PROGRESS_SYSTEM) et les 15 dernières lignes captées
    sans le plafond de 2500 caractères que le profil générique applique (aucun plafond de
    caractères supplémentaire dans build_feature_corpus.py:progress_windows, tail=15)."""
    cfg = Config(llm_profile="finetuned")
    session = Session()
    llm = _RecordingLLM([])
    nar = Narrator(cfg, session, _FakeSpeaker(), llm)
    nar.llm_ready = True
    c = _progressing(session)
    nar._tick()

    full_recent = "\n".join(c.out.lines)
    assert len(full_recent) > 2500  # le fixture doit dépasser le plafond générique
    assert len(llm.sent) == 1
    assert llm.sent[0][0]["content"] == label_features.TRAIN_PROGRESS_SYSTEM
    assert full_recent in llm.sent[0][1]["content"]  # aucune coupe à 2500 caractères


def test_narrator_tick_keeps_the_2500_char_cap_and_generic_prompt_outside_finetuned_profile():
    """Non-régression : hors profil affiné, `_tick()` garde exactement son comportement
    actuel (PROGRESS_SYSTEM, texte récent coupé à 2500 caractères)."""
    from steph.prompts import PROGRESS_SYSTEM

    cfg = Config()
    session = Session()
    llm = _RecordingLLM([])
    nar = Narrator(cfg, session, _FakeSpeaker(), llm)
    nar.llm_ready = True
    c = _progressing(session)
    nar._tick()

    full_recent = "\n".join(c.out.lines)
    assert len(full_recent) > 2500
    assert llm.sent[0][0]["content"] == PROGRESS_SYSTEM
    assert full_recent not in llm.sent[0][1]["content"]
    assert full_recent[-2500:] in llm.sent[0][1]["content"]


def test_narrator_tick_sends_train_progress_system_en_and_uncapped_recent_in_finetuned_profile_en():
    """B3c : TRAIN_PROGRESS_SYSTEM_EN existe désormais - `_tick()` doit basculer en anglais
    exactement comme en français (même prompt court, mêmes 15 dernières lignes non coupées)."""
    cfg = Config(llm_profile="finetuned", language="en")
    session = Session()
    llm = _RecordingLLM([])
    nar = Narrator(cfg, session, _FakeSpeaker(), llm)
    nar.llm_ready = True
    c = _progressing(session)
    nar._tick()

    full_recent = "\n".join(c.out.lines)
    assert len(full_recent) > 2500  # le fixture doit dépasser le plafond générique
    assert len(llm.sent) == 1
    assert llm.sent[0][0]["content"] == label_features.TRAIN_PROGRESS_SYSTEM_EN
    assert full_recent in llm.sent[0][1]["content"]  # aucune coupe à 2500 caractères
