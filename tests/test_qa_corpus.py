"""Tests de la partie pure de bench/matrix/finetune/qa_corpus.py (P15a).

Aucun réseau, aucun judge_lib, aucun appel à un serveur : seule la composition
des sessions et la décision d'acceptation sont testées ici. Les fonctions qui
parlent au teacher et au juge sont exercées à la main sur les machines GPU
(étape P15a) car elles ont besoin d'un serveur réel.
"""

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bench" / "matrix" / "finetune"))

from qa_corpus import (
    CANONICAL_ABSENT,
    CANONICAL_ABSENT_BY_LANG,
    build_example,
    combine_verdicts,
    decide_label,
    is_abstention,
    is_bench_contaminated,
    make_absent_question,
    make_present_question,
    output_lines,
    pick_sessions,
    qa_prefix_messages,
    session_key,
)


def rec(cmd, exit=0, duration=0.5, output="ligne\n", machine="linux-dev", id_=None):
    return {"cmd": cmd, "exit": exit, "duration": duration, "output": output, "machine": machine,
            "id": id_ or f"{machine}:{cmd}"}


class TestQaPrefixMessages:
    def test_shape_matches_narrator_qa_messages(self):
        msgs = qa_prefix_messages("[1] ? $ true   (code 0, 0 s, 0 lignes)\n(aucune sortie)")
        assert [m["role"] for m in msgs] == ["system", "user", "assistant"]
        assert msgs[1]["content"].startswith("Historique de la session :\n[1] ")
        assert msgs[2]["content"] == "Compris, j'ai l'historique."


class TestPickSessions:
    def test_sessions_within_min_max_size(self):
        records = [rec(f"cmd{i}") for i in range(20)]
        rng = random.Random(42)
        sessions = pick_sessions(records, rng, n_sessions=5, min_cmds=2, max_cmds=6)
        assert len(sessions) == 5
        for s in sessions:
            assert 2 <= len(s) <= 6

    def test_deterministic_with_same_seed(self):
        records = [rec(f"cmd{i}") for i in range(20)]
        a = pick_sessions(records, random.Random(7), n_sessions=4)
        b = pick_sessions(records, random.Random(7), n_sessions=4)
        assert [[r["id"] for r in s] for s in a] == [[r["id"] for r in s] for s in b]

    def test_no_duplicate_record_within_a_session(self):
        records = [rec(f"cmd{i}") for i in range(6)]
        rng = random.Random(1)
        sessions = pick_sessions(records, rng, n_sessions=3, min_cmds=2, max_cmds=6)
        for s in sessions:
            assert len({r["id"] for r in s}) == len(s)


class TestOutputLinesAndContamination:
    def test_output_lines_keeps_long_lines_only(self):
        text = "Sortie :\nab\nune ligne suffisamment longue pour compter\n"
        lines = output_lines(text)
        assert "une ligne suffisamment longue pour compter" in lines
        assert "ab" not in lines

    def test_contaminated_when_two_lines_shared(self):
        banned = {"une ligne suffisamment longue pour compter ici", "deuxieme ligne longue aussi tres precise"}
        out = "une ligne suffisamment longue pour compter ici\ndeuxieme ligne longue aussi tres precise\n"
        assert is_bench_contaminated(out, banned)

    def test_not_contaminated_with_one_shared_line(self):
        banned = {"une ligne suffisamment longue pour compter ici"}
        out = "une ligne suffisamment longue pour compter ici\nautre chose de complètement différent ici\n"
        assert not is_bench_contaminated(out, banned)


class TestQuestions:
    def test_present_question_targets_a_session_command(self):
        session = [rec("gcc -o a a.c", exit=0), rec("git status", exit=0)]
        rng = random.Random(3)
        category, question = make_present_question(session, rng)
        assert category in {"status", "exit_code", "error_cause", "count_lines", "duration", "which_last", "which_failed"}
        assert question.strip().endswith("?")

    def test_error_cause_only_offered_when_a_command_failed(self):
        session = [rec("true", exit=0), rec("false", exit=1)]
        seen = {make_present_question(session, random.Random(i))[0] for i in range(60)}
        assert "error_cause" in seen

    def test_absent_question_never_targets_the_session(self):
        session = [rec("gcc -o a a.c"), rec("git status")]
        pool = [rec("docker ps", id_="distractor:1"), rec("ls -la", id_="distractor:2")]
        rng = random.Random(5)
        category, _question, target = make_absent_question(session, pool, rng)
        assert category == "absent"
        session_cmds = {r["cmd"] for r in session}
        assert target is None or target["cmd"] not in session_cmds


class TestVerdictAndLabel:
    def test_combine_verdicts_both_invention(self):
        assert combine_verdicts("invention", "invention") == "invention"

    def test_combine_verdicts_split_is_douteux(self):
        assert combine_verdicts("invention", "ok") == "douteux"
        assert combine_verdicts("ok", "invention") == "douteux"

    def test_combine_verdicts_both_ok(self):
        assert combine_verdicts("ok", "ok") == "ok"

    def test_decide_label_rejects_anything_not_ok(self):
        assert decide_label("status", "Succès.", "invention") is None
        assert decide_label("status", "Succès.", "douteux") is None

    def test_decide_label_present_keeps_raw_answer(self):
        assert decide_label("status", "Succès.", "ok") == "Succès."

    def test_decide_label_absent_forces_canonical_phrase(self):
        assert decide_label("absent", "Introuvable, désolé.", "ok") == CANONICAL_ABSENT
        assert CANONICAL_ABSENT == "Pas dans l'historique."

    def test_decide_label_rejects_unjustified_abstention_on_present_question(self):
        # le fait EST dans le contexte envoyé (catégorie != absent) : le juge ne le sait
        # pas, il ne vérifie que les faits affirmés à tort, pas les refus injustifiés.
        assert decide_label("duration", "Pas dans l'historique.", "ok") is None
        assert decide_label("count_lines", "Introuvable dans l'historique.", "ok") is None

    def test_is_abstention(self):
        assert is_abstention("Pas dans l'historique.")
        assert is_abstention("pas dans l'historique, désolé")
        assert not is_abstention("Succès, 3 lignes.")


class TestBuildExampleAndKey:
    def test_build_example_appends_question_and_answer(self):
        prefix = qa_prefix_messages("ctx")
        ex = build_example(prefix, "Ça a marché ?", "Succès.")
        assert ex["messages"][-2] == {"role": "user", "content": "Ça a marché ?"}
        assert ex["messages"][-1] == {"role": "assistant", "content": "Succès."}
        assert ex["source"] == "qa-synth"

    def test_session_key_stable_and_sensitive_to_question(self):
        k1 = session_key("ctx-a", "question 1")
        k2 = session_key("ctx-a", "question 1")
        k3 = session_key("ctx-a", "question 2")
        assert k1 == k2
        assert k1 != k3
        assert len(k1) == 64  # sha256 hex


class TestEnglish:
    """--lang en : même historique que la production anglaise (narrator.qa_messages, language="en")."""

    def test_prefix_uses_english_system_header_and_ack(self):
        from steph import prompts, strings
        msgs = qa_prefix_messages("ctx", "en")
        assert msgs[0]["content"] == prompts.QA_SYSTEM_EN
        assert msgs[1]["content"] == strings.t("en", "qa_history_header").format(ctx="ctx")
        assert msgs[2]["content"] == strings.t("en", "qa_history_ack")

    def test_french_prefix_unchanged_by_default(self):
        from steph import prompts
        assert qa_prefix_messages("ctx")[0]["content"] == prompts.QA_SYSTEM
        assert qa_prefix_messages("ctx", "fr") == qa_prefix_messages("ctx")

    def test_english_canonical_absent_is_the_phrase_of_the_english_prompt(self):
        from steph import prompts
        assert CANONICAL_ABSENT_BY_LANG["en"] == "Not in the history."
        assert CANONICAL_ABSENT_BY_LANG["en"] in prompts.QA_SYSTEM_EN
        assert CANONICAL_ABSENT_BY_LANG["fr"] == CANONICAL_ABSENT

    def test_present_questions_are_english(self):
        session = [rec("true", exit=0), rec("false", exit=1)]
        for i in range(40):
            _category, question = make_present_question(session, random.Random(i), "en")
            assert "«" not in question and question.endswith("?")
            assert question.split()[0] in {"Did", "What", "How", "Why", "Which"}

    def test_absent_questions_are_english(self):
        session = [rec("gcc -o a a.c")]
        pool = [rec("docker ps", id_="d:1")]
        for i in range(20):
            category, question, _ = make_absent_question(session, pool, random.Random(i), "en")
            assert category == "absent" and "«" not in question and question.endswith("?")

    def test_decide_label_english_absent_and_abstention(self):
        assert decide_label("absent", "Nothing about it.", "ok", "en") == "Not in the history."
        assert decide_label("duration", "Not in the history.", "ok", "en") is None
        assert is_abstention("Not in the history.")

    def test_english_example_source_marks_the_language(self):
        ex = build_example(qa_prefix_messages("ctx", "en"), "Did it work?", "Success.", lang="en")
        assert ex["source"] == "qa-synth.en"
        assert build_example(qa_prefix_messages("ctx"), "Ça a marché ?", "Succès.")["source"] == "qa-synth"


def test_error_weight_favours_error_cause_questions():
    session = [rec("true", exit=0), rec("false", exit=1)]
    def count(weight):
        return sum(make_present_question(session, random.Random(i), "fr", error_weight=weight)[0] == "error_cause"
                   for i in range(300))
    assert count(4) > 2 * count(1)


def test_decide_label_rejects_present_answer_that_also_abstains():
    # « Non. Code 1. Pas dans l'historique. » : réponse et refus mêlés, rien de stable à apprendre
    assert decide_label("status", "Non. Code 1. Perte 100 %. Pas dans l'historique.", "ok") is None
    assert decide_label("status", "Failed, code 1. Not in the history.", "ok", "en") is None
    assert decide_label("status", "Non, code 1.", "ok") == "Non, code 1."


def test_judge_sees_the_question():
    # X4a : le juge ne voyait que l'historique ; une réponse ancrée mais fausse passait toujours
    from qa_corpus import judge_answer
    seen = []

    def fake_judge(ctx, phrase, pass_id="A"):
        seen.append(ctx)
        return {"verdict": "ok"}

    judge_answer(fake_judge, "[1] ~ $ ls\nfichier.txt", "fichier.txt", "Quelle est la dernière commande ?")
    assert len(seen) == 2
    assert all(c.startswith("[1] ~ $ ls\nfichier.txt") and c.endswith("Question : Quelle est la dernière commande ?")
               for c in seen)


def test_judge_question_label_english():
    from qa_corpus import judge_answer
    seen = []
    judge_answer(lambda ctx, phrase, pass_id="A": seen.append(ctx) or {"verdict": "ok"},
                 "ctx", "Yes.", "Did it work?", lang="en")
    assert seen[0].endswith("Question: Did it work?")


# --------------------------------------------------------------------------- X4 : format de production (P20)
def _production(records, cwd, question, lang):
    """Ce que steph envoie vraiment : Session remplie commande par commande, historique relu après
    chacune (la coupe des blocs anciens se fait au fil de l'eau), puis server._ask."""
    from steph.config import Config
    from steph.narrator import Narrator
    from steph.session import Session

    s = Session()
    nar = Narrator(Config(language=lang, llm_profile="finetuned"), s, None, None)
    for r in records:
        s.cwd = r.get("cwd", cwd)
        c = s.start(r["cmd"])
        if r["output"]:
            c.feed((r["output"] if r["output"].endswith("\n") else r["output"] + "\n").encode())
        c.start, c.end, c.exit = 1e9, 1e9 + r["duration"], r["exit"]
        nar.qa_messages()
    s.cwd = cwd
    return nar.qa_messages() + [{"role": "user", "content": f"(dossier actuel : {s.cwd})\n{question}"}]


def test_training_messages_match_production():
    from qa_corpus import production_qa_messages
    records = [rec("make", exit=2, duration=1.2, output="gcc -c main.c\nmain.c:8: error: count\n"),
               rec("ls", output="a.txt\nb.txt")]
    got = production_qa_messages(records, "~/projet", "Pourquoi le make a échoué ?", "fr")
    assert got == _production(records, "~/projet", "Pourquoi le make a échoué ?", "fr")
    assert [m["role"] for m in got] == ["system", "user", "assistant", "user"]
    assert got[2]["content"] == "Compris, j'ai l'historique."
    assert "[1] ~/projet $ make" in got[1]["content"]
    assert got[-1]["content"] == "(dossier actuel : ~/projet)\nPourquoi le make a échoué ?"


def test_training_messages_english_keep_french_cwd_prefix():
    from qa_corpus import production_qa_messages
    records = [rec("true", output=""), rec("false", exit=1, output="")]
    got = production_qa_messages(records, "~", "Did it fail?", "en")
    assert got == _production(records, "~", "Did it fail?", "en")
    assert got[2]["content"] == "Understood, I have the history."
    assert got[-1]["content"] == "(dossier actuel : ~)\nDid it fail?"


def test_training_messages_cut_old_blocks_like_production():
    from qa_corpus import production_qa_messages
    big = "\n".join(f"ligne {i} " + "x" * 60 for i in range(60))
    records = [rec(f"cat f{i}", output=big) for i in range(9)]
    got = production_qa_messages(records, "~/p", "Combien ?", "fr")
    assert got == _production(records, "~/p", "Combien ?", "fr")
    assert "commandes plus anciennes omises" in got[1]["content"]


def test_production_question_format_unchanged():
    # garde : le format de la question vit en ligne dans server._ask ; s'il change, le corpus doit suivre
    src = (Path(__file__).resolve().parents[1] / "src" / "steph" / "server.py").read_text()
    assert 'f"(dossier actuel : {s.cwd})\\n{question}"' in src
