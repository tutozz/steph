"""L5 : faits extraits en code et ajoutés à l'entrée du modèle, derrière `facts_block` (vrai par défaut depuis la décision utilisateur du 2026-09-29).

Sorties écrites d'après les formats publics des outils (documentation de GCC, autoconf, GNU make,
bash, pytest, unittest, cargo, ruff, npm), jamais recopiées d'un cas du banc v3.
"""

import pytest

from steph import prompts
from steph.config import Config
from steph.digest import extract_facts as facts
from steph.session import Session

from test_narrator import FakeLLM, FakeSpeaker, _finished_command
from steph.narrator import Narrator


# ---------------------------------------------------------------- extraction

GCC_FAIL = """\
parser.c: In function 'parse_line':
parser.c:42:17: error: 'tokn' undeclared (first use in this function); did you mean 'token'?
   42 |     return tokn;
      |            ^~~~
parser.c:57:5: warning: unused variable 'len' [-Wunused-variable]
make: *** [Makefile:12: parser.o] Error 1
"""


def test_compiler_error_gives_file_line_and_message_when_the_command_failed():
    got = facts("make", 2, GCC_FAIL, "fr")
    assert any(f.startswith("Erreur : parser.c ligne 42 : tokn undeclared") for f in got)


def test_compiler_warnings_name_the_files_without_counting_them():
    out = ("util.c:10:5: warning: unused variable 'x' [-Wunused-variable]\n"
           "io.c:3:1: warning: implicit declaration of function 'foo'\n"
           "util.c:22:9: warning: comparison of integer expressions of different signedness\n"
           "gcc -o app util.o io.o\n")
    got = facts("make", 0, out, "fr")
    assert "Avertissements dans : util.c, io.c" in got
    assert not any("Erreur" in f for f in got)


def test_no_error_fact_on_success_even_if_a_line_says_error():
    out = "\n".join(f"2026-01-0{i} ERROR: disk quota reached for job {i}" for i in range(1, 8))
    assert not any(f.startswith("Erreur") for f in facts("grep -n ERROR app.log", 0, out, "fr"))


def test_configure_error_is_the_last_configure_error_line():
    out = ("checking for gcc... gcc\nchecking for curses.h... no\n"
           "configure: error: in '/src/tool-1.2':\n"
           "configure: error: curses library not found, install libncurses-dev\n"
           "See 'config.log' for more details\n")
    got = facts("./configure", 1, out, "en")
    assert "Error: curses library not found, install libncurses-dev" in got


def test_configure_success_lists_the_generated_files():
    out = "checking for gawk... gawk\n" * 5 + (
        "config.status: creating Makefile\nconfig.status: creating lib/Makefile\n"
        "config.status: creating src/Makefile\nconfig.status: creating config.h\n"
        "config.status: executing depfiles commands\n")
    got = facts("./configure", 0, out, "fr")
    assert "Fichiers générés : Makefile, config.h (4 fichiers)" in got


def test_make_names_the_project_from_the_shortest_entering_directory():
    out = ("make  all-recursive\n"
           "make[1]: Entering directory '/home/user/build/grep-3.11'\n"
           "make[2]: Entering directory '/home/user/build/grep-3.11/lib'\n"
           "  CC       regex.o\n  AR       libgreputils.a\n"
           "make[2]: Leaving directory '/home/user/build/grep-3.11/lib'\n")
    assert "Projet : grep-3.11" in facts("make -j8", 0, out, "fr")


def test_make_project_in_french_locale():
    out = ("make[1] : on entre dans le répertoire « /home/user/src/cpio-2.15 »\n"
           "  CC       main.o\n  CCLD     cpio\n"
           "make[1] : on quitte le répertoire « /home/user/src/cpio-2.15 »\n")
    assert "Project: cpio-2.15" in facts("make", 0, out, "en")


def test_shell_script_line_error_is_kept_even_when_the_script_exits_zero():
    out = ("Sauvegarde des factures...\n"
           "./backup.sh: line 7: rsyncx: command not found\n"
           "Sauvegarde terminée\n")
    got = facts("./backup.sh", 0, out, "fr")
    assert "Erreur du script : backup.sh ligne 7 : rsyncx: command not found" in got


def test_python_traceback_gives_the_last_frame_and_the_exception():
    out = ('Traceback (most recent call last):\n'
           '  File "/app/main.py", line 12, in <module>\n    run()\n'
           '  File "/app/core.py", line 30, in run\n    cfg["region"]\n'
           "KeyError: 'region'\n")
    got = facts("python3 main.py", 1, out, "en")
    assert "Error: core.py line 30: KeyError region" in got


def test_tool_summary_lines_are_copied_verbatim():
    pytest_out = "tests/test_a.py ..F.\n" + "=" * 20 + " 1 failed, 3 passed in 0.12s " + "=" * 20 + "\n"
    assert "Bilan de l'outil : 1 failed, 3 passed in 0.12s" in facts("pytest", 1, pytest_out, "fr")
    unittest_out = "test_a ... ok\ntest_b ... FAIL\n" + "-" * 70 + "\nRan 2 tests in 0.001s\n\nFAILED (failures=1)\n"
    got = facts("python3 -m unittest", 1, unittest_out, "fr")
    assert "Bilan de l'outil : Ran 2 tests in 0.001s ; FAILED (failures=1)" in got
    ruff_out = "src/a.py:1:8: F401 [*] `os` imported but unused\nFound 12 errors.\n[*] 5 fixable with the `--fix` option.\n"
    assert "Tool summary: Found 12 errors. ; [*] 5 fixable with the `--fix` option." in facts("ruff check .", 1, ruff_out, "en")
    npm_out = "npm warn deprecated inflight@1.0.6\n\nadded 214 packages, and audited 215 packages in 9s\n\nfound 0 vulnerabilities\n"
    got = facts("npm install", 0, npm_out, "en")
    assert "Tool summary: added 214 packages, and audited 215 packages in 9s ; found 0 vulnerabilities" in got


def test_generic_last_line_with_a_count_is_a_summary():
    out = "\n".join(f"copie de export-{i:02d}.csv" for i in range(1, 9)) + "\nBilan : 8 fichiers copiés\n"
    assert "Bilan de l'outil : Bilan : 8 fichiers copiés" in facts("./collect.sh", 0, out, "fr")


def test_first_failed_test_is_named():
    out = ("test_parse (test_feed.FeedTest.test_parse) ... ok\n"
           "test_dates (test_feed.FeedTest.test_dates) ... FAIL\n"
           + "=" * 70 + "\nFAIL: test_dates (test_feed.FeedTest.test_dates)\n" + "-" * 70 + "\n"
           "Ran 2 tests in 0.002s\n\nFAILED (failures=1)\n")
    assert "Premier test en échec : test_dates" in facts("python3 -m unittest -v", 1, out, "fr")
    cargo = "running 3 tests\n---- tests::sums_rows stdout ----\nthread panicked\n\ntest result: FAILED. 2 passed; 1 failed; 0 ignored\n"
    assert "First failing test: tests::sums_rows" in facts("cargo test", 101, cargo, "en")


def test_error_lines_that_are_not_tests_name_no_failing_test():
    out = "#1 [internal] load build definition\n#1 DONE 0.0s\nERROR: failed to solve: dockerfile parse error on line 3\n"
    got = facts("docker build .", 1, out, "en")
    assert not any(f.startswith("First failing test") for f in got)
    assert "Error: ERROR: failed to solve: dockerfile parse error on line 3" in got


def test_generic_error_is_the_last_error_line_and_keeps_apostrophes():
    out = ("psql: error: connection to server on socket failed: Connection refused\n"
           "update-alternatives: erreur: pas d'alternatives pour java\n")
    assert facts("update-alternatives --display java", 2, out, "fr") == [
        "Erreur : update-alternatives: erreur: pas d'alternatives pour java"]


def test_a_pointer_to_a_log_file_is_never_the_main_error():
    out = ("npm error code EBADENGINE\nnpm error engine Unsupported engine\n"
           "npm error A complete log of this run can be found in: /home/user/.npm/_logs/debug-0.log\n")
    assert "Error: npm error engine Unsupported engine" in facts("npm ci", 1, out, "en")


@pytest.mark.parametrize("last", [
    "13:14     warning  truthy value should be one of [false, true]  (truthy)",
    "Aug 11 16:34:55 host systemd[1105]: backup.service: Failed with result 'exit-code'.",
    "2026-09-01 10:00:02 job 12 failed",
    "'bureau/compta_2024_11.txt' -> '/tmp/copie/compta_2024_11.txt'",
    "npm error A complete log of this run can be found in: /home/user/.npm/_logs/debug-0.log",
    "make: *** [Makefile:297: all] Error 2",
    "rsync(57497): warning: child 57498 exited with status 255",
    'connection to server at "db" (10.0.0.2), port 5432 failed: FATAL:  database "shop" does not exist',
    "Erreur ligne 6 : commande tar (code 2)",
])
def test_last_line_that_is_data_or_a_diagnostic_is_not_a_summary(last):
    out = "\n".join(f"step {c}" for c in "abcdef") + "\n" + last + "\n"
    assert not any(f.startswith("Bilan") for f in facts("./run.sh", 1, out, "fr"))


def test_nothing_to_say_gives_an_empty_list():
    out = "\n".join(f"line {c}" for c in "abcdefgh")
    assert facts("cat notes.txt", 0, out, "fr") == []


def test_facts_are_capped():
    out = GCC_FAIL + "Ran 2 tests in 0.1s\nFAILED (failures=1)\n"
    got = facts("make check", 2, out, "fr")
    assert 1 <= len(got) <= 5
    assert all(len(f) <= 200 for f in got)


# ---------------------------------------------------------------- entrée du modèle

def test_summary_messages_are_unchanged_without_facts():
    base = prompts.summary_messages("make", 2, 1.0, "sortie", 5)
    assert prompts.summary_messages("make", 2, 1.0, "sortie", 5, facts=None) == base
    assert prompts.summary_messages("make", 2, 1.0, "sortie", 5, facts=[]) == base
    fine = prompts.finetuned_summary_messages("make", 2, 1.0, "sortie", 5)
    assert prompts.finetuned_summary_messages("make", 2, 1.0, "sortie", 5, facts=[]) == fine


@pytest.mark.parametrize("language,header,out_label", [("fr", "Faits extraits en code :", "Sortie :"),
                                                       ("en", "Facts extracted by code:", "Output:")])
def test_facts_block_sits_between_the_header_and_the_output(language, header, out_label):
    msgs = prompts.summary_messages("make", 2, 1.0, "sortie", 5, language=language, facts=["A", "B"])
    user = msgs[1]["content"]
    assert f"{header}\n- A\n- B\n{out_label}\n" in user
    assert msgs[0] == prompts.summary_messages("make", 2, 1.0, "sortie", 5, language=language)[0]
    fine = prompts.finetuned_summary_messages("make", 2, 1.0, "sortie", 5, language=language, facts=["A"])
    assert f"{header}\n- A\n{out_label}\n" in fine[1]["content"]


# ---------------------------------------------------------------- narrator

class _RecordingLLM(FakeLLM):
    def __init__(self, pieces):
        super().__init__(pieces)
        self.messages = []

    def stream(self, messages, max_tokens=90, **kw):
        self.messages.append(messages)
        yield from super().stream(messages, max_tokens, **kw)


def _summary_input(cfg):
    llm = _RecordingLLM(["Échec."])
    n = Narrator(cfg, Session(), FakeSpeaker(), llm)
    n.llm_ready = True
    lines = ["configure: running checks"] * 6 + ["./lib/env.sh: line 9: VERSION: unbound variable"]
    c = _finished_command(n.s, "./setup.sh", "/home/user", 1, lines)
    n._finish(c, "/home/user", "/home/user")
    return llm.messages[0][1]["content"]


def test_facts_block_is_on_by_default():
    assert Config().facts_block is True
    assert "Faits extraits" in _summary_input(Config())


def test_facts_block_can_be_turned_off():
    assert "Faits extraits" not in _summary_input(Config(facts_block=False))


@pytest.mark.parametrize("profile", ["generic", "finetuned"])
def test_facts_block_reaches_the_model_when_enabled(profile):
    cfg = Config(facts_block=True, llm_profile=profile)
    assert "Faits extraits en code :\n- Erreur du script : env.sh ligne 9 : VERSION: unbound variable" in _summary_input(cfg)
