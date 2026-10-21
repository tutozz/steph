"""D6 lot A : tests, lint et typage, compilation dits en code (docs/code-first-d6.md).

Chaque sortie suit le format documenté de l'outil ; la provenance est notée au-dessus de chaque
groupe. Une phrase dite en code doit être juste, sinon `resolve()` se tait et laisse le modèle.
"""

from steph.digest import resolve

# ================================================================ unittest
# Source : documentation Python, module unittest (« Ran N tests in Xs », « OK (skipped=N) »,
# « FAILED (failures=N, errors=N) », blocs « FAIL: nom (module.Classe.nom) »,
# chargeur en échec « unittest.loader._FailedTest »).

_UT_FAILED = """\
test_env_int_cast (tests.test_loader.EnvTest.test_env_int_cast) ... FAIL
test_env_prefix (tests.test_loader.EnvTest.test_env_prefix) ... ok
test_port_default (tests.test_loader.PortTest.test_port_default) ... ERROR

======================================================================
ERROR: test_port_default (tests.test_loader.PortTest.test_port_default)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/home/user/src/configloader/tests/test_loader.py", line 39, in test_port_default
    self.assertEqual(port({}), 8000)
  File "/home/user/src/configloader/configloader/loader.py", line 19, in port
    return cfg["port"]
KeyError: 'port'

======================================================================
FAIL: test_env_int_cast (tests.test_loader.EnvTest.test_env_int_cast)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/home/user/src/configloader/tests/test_loader.py", line 12, in test_env_int_cast
    self.assertEqual(env_int("N"), 4)
AssertionError: '4' != 4

----------------------------------------------------------------------
Ran 3 tests in 0.004s

FAILED (failures=1, errors=1)
"""


def test_unittest_failures_and_errors_counted_with_one_named_test():
    assert resolve("python -m unittest discover -v", 1, _UT_FAILED) == (
        "Échec. 1 échec et 1 erreur sur 3 tests, dont test_port_default, loader.py ligne 19 : KeyError, port.")


def test_unittest_failures_only_names_the_first_reported_block():
    out = "\n".join(f"test_ticket_{i:02d} (test_ticket.TestTicket.test_ticket_{i:02d}) ... "
                    + ("FAIL" if i in (0, 12, 59) else "ok") for i in range(74))
    for i, line in ((0, 5), (12, 29), (59, 123)):
        out += (f"\n\n{'=' * 70}\nFAIL: test_ticket_{i:02d} (test_ticket.TestTicket.test_ticket_{i:02d})\n{'-' * 70}\n"
                "Traceback (most recent call last):\n"
                f'  File "/home/user/ut-ticket/test_ticket.py", line {line}, in test_ticket_{i:02d}\n'
                f"    self.assertEqual(sorted([{i}, 1]), [1, {i}][::-1])\n"
                f"AssertionError: Lists differ: [1, {i}] != [{i}, 1]\n")
    out += f"\n{'-' * 70}\nRan 74 tests in 0.001s\n\nFAILED (failures=3)\n"
    assert resolve("python3 -m unittest -v test_ticket", 1, out) == (
        "Échec. 3 échecs sur 74 tests, dont test_ticket_00, test_ticket.py ligne 5.")
    assert resolve("python3 -m unittest -v test_ticket", 1, out, "en") == (
        "Failed. 3 failures out of 74 tests, including test_ticket_00, test_ticket.py line 5.")


def test_unittest_all_passed_with_skipped():
    out = "..s.s...\n" + "-" * 70 + "\nRan 8 tests in 0.002s\n\nOK (skipped=2)\n"
    assert resolve("python -m unittest", 0, out) == "6 tests réussis, 2 ignorés."
    assert resolve("python -m unittest", 0, out, "en") == "6 tests passed, 2 skipped."


def test_unittest_all_passed_singular():
    out = ".\n" + "-" * 70 + "\nRan 1 test in 0.000s\n\nOK\n"
    assert resolve("python -m unittest", 0, out) == "1 test réussi."


def test_unittest_subtests_more_failures_than_tests_drop_the_total():
    out = ("F\n" + "=" * 70 + "\nFAIL: test_even (t.T.test_even) (i=1)\n" + "-" * 70 + "\n"
           "Traceback (most recent call last):\n  File \"/p/t.py\", line 6, in test_even\n"
           "    self.assertEqual(i % 2, 0)\nAssertionError: 1 != 0\n\n"
           + "=" * 70 + "\nFAIL: test_even (t.T.test_even) (i=3)\n" + "-" * 70 + "\n"
           "Traceback (most recent call last):\n  File \"/p/t.py\", line 6, in test_even\n"
           "    self.assertEqual(i % 2, 0)\nAssertionError: 1 != 0\n\n"
           + "-" * 70 + "\nRan 1 test in 0.001s\n\nFAILED (failures=2)\n")
    assert resolve("python -m unittest t", 1, out) == "Échec. 2 échecs, dont test_even, t.py ligne 6."


def test_unittest_import_failure_names_module_and_cause():
    out = """\
E
======================================================================
ERROR: test_parser (unittest.loader._FailedTest.test_parser)
----------------------------------------------------------------------
ImportError: Failed to import test module: test_parser
Traceback (most recent call last):
  File "/usr/lib/python3.13/unittest/loader.py", line 137, in loadTestsFromName
    module = __import__(module_name)
  File "/home/user/src/tomlish/tomlish/parser.py", line 1, in <module>
    from tomlish.lexer import tokenize
ModuleNotFoundError: No module named 'tomlish.lexer'


----------------------------------------------------------------------
Ran 1 test in 0.000s

FAILED (errors=1)
"""
    assert resolve("python -m unittest tests.test_parser", 1, out) == (
        "Échec. Import du module de test test_parser impossible : ModuleNotFoundError, No module named tomlish.lexer.")


def test_unittest_unknown_result_keys_left_to_the_model():
    out = "x\n" + "-" * 70 + "\nRan 1 test in 0.000s\n\nOK (expected failures=1)\n"
    assert resolve("python -m unittest", 0, out) is None


# ================================================================ go test par paquet
# Source : `go help test` et `go help testflag` : lignes « ok  \tpaquet\t0.004s », « (cached) »,
# « ?   \tpaquet\t[no test files] », « FAIL\tpaquet\t… », « coverage: N% of statements » ;
# depuis Go 1.22, un paquet sans test sous -cover imprime « \tpaquet\t\tcoverage: 0.0% of statements ».

def test_go_test_success_names_packages_and_packages_without_tests():
    out = ("?   \texample.invalid/kvstore/cmd/kvctl\t[no test files]\n"
           "ok  \texample.invalid/kvstore/codec\t(cached)\n"
           "?   \texample.invalid/kvstore/internal/version\t[no test files]\n"
           "ok  \texample.invalid/kvstore/store\t(cached)\n")
    assert resolve("go test ./...", 0, out) == "2 paquets réussis : codec et store. Sans tests : kvctl et version."
    assert resolve("go test ./...", 0, out, "en") == "2 packages passed: codec and store. No tests: kvctl and version."


def test_go_test_verbose_success_still_counts_packages():
    out = ("?   \texample.invalid/kvstore/cmd/kvctl\t[no test files]\n=== RUN   TestRoundTrip\n"
           "--- PASS: TestRoundTrip (0.00s)\nPASS\nok  \texample.invalid/kvstore/codec\t0.392s\n")
    assert resolve("go test -v ./...", 0, out) == "1 paquet réussi : codec. Sans tests : kvctl."


def test_go_test_cover_says_the_coverage_of_each_package():
    out = ("\texample.invalid/kvstore/cmd/kvctl\t\tcoverage: 0.0% of statements\n"
           "ok  \texample.invalid/kvstore/codec\t0.183s\tcoverage: 100.0% of statements\n"
           "?   \texample.invalid/kvstore/internal/version\t[no test files]\n"
           "ok  \texample.invalid/kvstore/store\t0.183s\tcoverage: 72.5% of statements\n")
    assert resolve("go test -cover ./...", 0, out) == (
        "2 paquets réussis : codec 100 % et store 72,5 %. Sans tests : kvctl et version.")
    assert resolve("go test -cover ./...", 0, out, "en") == (
        "2 packages passed: codec 100% and store 72.5%. No tests: kvctl and version.")


def test_go_test_many_packages_named_three_then_counted():
    out = "".join(f"ok  \texample.invalid/app/p{i}\t0.01s\n" for i in range(6))
    assert resolve("go test ./...", 0, out) == "6 paquets réussis : p0, p1, p2 et 3 autres."


def test_go_test_json_or_truncated_output_left_to_the_model():
    assert resolve("go test -json ./...", 0, '{"Action":"pass","Package":"x"}\n{"Action":"pass"}\n') is None
    out = "ok  \texample.invalid/a\t0.01s\nok  \texample.invalid/b\t0.01s\n"
    assert resolve("go test ./... | head -n 2", 0, out) is None


# go test en échec : en -v, le journal du test précède sa ligne « --- FAIL » ; sans -v, il la suit,
# indenté. Les sous-tests (t.Run) échouent sous leur parent, qui échoue aussi.

def test_go_test_verbose_message_belongs_to_the_failing_test_not_the_next_one():
    out = ("=== RUN   TestBilling01\n--- PASS: TestBilling01 (0.00s)\n=== RUN   TestBilling02\n"
           "    billing_test.go:7: Len = 2, want 3\n--- FAIL: TestBilling02 (0.00s)\n=== RUN   TestBilling03\n"
           "--- PASS: TestBilling03 (0.00s)\n=== RUN   TestBilling15\n    billing_test.go:40: Len = 15, want 16\n"
           "--- FAIL: TestBilling15 (0.00s)\nFAIL\nFAIL\texample.invalid/billing\t0.192s\nFAIL\n")
    assert resolve("go test -v -count=1 .", 1, out) == (
        "Échec. 2 tests échoués. Paquet billing, TestBilling02, billing_test.go ligne 7 : Len = 2, want 3.")


def test_go_test_subtests_count_the_failing_leaves():
    lines = ["=== RUN   TestPrice"]
    for i in range(6):
        lines.append(f"=== RUN   TestPrice/qty_{i:02d}")
        if i in (1, 4):
            lines.append(f"    price_test.go:51: Price({i},3) = {i * 3 - 1}, want {i * 3}")
    lines.append("--- FAIL: TestPrice (0.00s)")
    for i in range(6):
        lines.append(f"    --- {'FAIL' if i in (1, 4) else 'PASS'}: TestPrice/qty_{i:02d} (0.00s)")
    lines += ["FAIL", "FAIL\texample.invalid/shop\t0.263s", "FAIL"]
    assert resolve("go test -v ./...", 1, "\n".join(lines)) == (
        "Échec. 2 tests échoués. Paquet shop, TestPrice qty_01, price_test.go ligne 51 : Price(1,3) = 2, want 3.")


def test_go_test_non_verbose_subtest_message_follows_its_fail_line():
    out = ("--- FAIL: TestPrice (0.00s)\n    --- FAIL: TestPrice/qty_08 (0.00s)\n"
           "        price_test.go:51: Price(8,3) = 23, want 24\nFAIL\nFAIL\texample.invalid/shop\t0.2s\nFAIL\n")
    assert resolve("go test ./...", 1, out) == (
        "Échec. 1 test échoué. Paquet shop, TestPrice qty_08, price_test.go ligne 51 : Price(8,3) = 23, want 24.")


def test_go_test_parallel_logs_are_not_attributed():
    out = ("=== RUN   TestA\n=== PAUSE TestA\n=== RUN   TestB\n=== PAUSE TestB\n=== CONT  TestA\n"
           "=== CONT  TestB\n    a_test.go:9: boom\n--- FAIL: TestA (0.00s)\n--- PASS: TestB (0.00s)\n"
           "FAIL\nFAIL\texample.invalid/p\t0.1s\n")
    assert resolve("go test -v ./...", 1, out) == "Échec. 1 test échoué. Paquet p, TestA."


# ================================================================ panique Go
# Source : runtime Go, messages « panic: … », « fatal error: all goroutines are asleep - deadlock! »,
# pile « goroutine N [état]: » puis « fonction(…) » et « \tfichier:ligne +0x… ».

def test_go_panic_nil_pointer_names_function_and_line():
    out = ("warming cache\npanic: runtime error: invalid memory address or nil pointer dereference\n"
           "[signal SIGSEGV: segmentation violation code=0x1 addr=0x0 pc=0x4981ac]\n\n"
           "goroutine 1 [running]:\nmain.(*Cache).Get(...)\n\t/home/user/src/go-cache/main.go:9\n"
           "main.main()\n\t/home/user/src/go-cache/main.go:14 +0x4c\nexit status 2\n")
    assert resolve("go run .", 1, out) == (
        "Échec. Panique : runtime error: invalid memory address or nil pointer dereference. "
        "Dans Cache.Get, main.go ligne 9.")


def test_go_deadlock_names_the_blocked_line():
    out = ("fatal error: all goroutines are asleep - deadlock!\n\ngoroutine 1 [chan send]:\n"
           "main.main()\n\t/Users/user/src/go-pipeline/main.go:8 +0x48\nexit status 2\n")
    assert resolve("go run main.go", 1, out) == (
        "Échec. Interblocage : toutes les goroutines sont bloquées. Dans main, main.go ligne 8.")
    assert resolve("go run main.go", 1, out, "en") == (
        "Failed. Deadlock: all goroutines are asleep. In main, main.go line 8.")


def test_go_panic_skips_runtime_frames():
    out = ("panic: boom\n\ngoroutine 1 [running]:\nruntime.gopanic(...)\n\t/usr/lib/go/src/runtime/panic.go:770\n"
           "main.run(0x2)\n\t/src/app/run.go:21 +0x1d\nmain.main()\n\t/src/app/main.go:5 +0x18\n")
    assert resolve("./app", 2, out) == "Échec. Panique : boom. Dans run, run.go ligne 21."


# ================================================================ deno test, jest sans test, couverture
# Sources : manuel Deno (`deno test` : « ok | N passed | N failed (Xms) », section « FAILURES »
# « nom => ./fichier:ligne:colonne ») ; Jest (« No tests found, exiting with code 1 »,
# « N files checked. ») ; tableau texte d'Istanbul (« File | % Stmts | % Branch | % Funcs | % Lines »).

def test_deno_all_passed():
    out = ("Check trim_test.ts\nrunning 5 tests from ./trim_test.ts\ntrimLines ... ok (221µs)\n\n"
           "ok | 5 passed | 0 failed (2ms)\n")
    assert resolve("deno test", 0, out) == "5 tests réussis."


def test_deno_failures_name_the_first_one():
    out = ("running 3 tests from ./trim_test.ts\na ... ok (1ms)\nb ... FAILED (1ms)\nc ... ok (1ms)\n\n"
           " ERRORS \n\nb => ./trim_test.ts:12:6\nerror: AssertionError: Values are not equal.\n\n"
           " FAILURES \n\nb => ./trim_test.ts:12:6\n\nFAILED | 2 passed | 1 failed (5ms)\n\n"
           "error: Test failed\n")
    assert resolve("deno test", 1, out) == "Échec. 1 test échoué, 2 réussis. Premier : b, trim_test.ts ligne 12."


def test_jest_no_tests_found():
    out = ("No tests found, exiting with code 1\nRun with `--passWithNoTests` to exit with code 0\n"
           "In /home/user/src/empty-lib\n  2 files checked.\n"
           "  testMatch: **/__tests__/**/*.[jt]s?(x) - 0 matches\n")
    assert resolve("npx jest", 1, out) == "Échec. Aucun test trouvé, 2 fichiers examinés."
    assert resolve("npx jest", 1, out, "en") == "Failed. No tests found, 2 files checked."


def test_jest_coverage_table_adds_line_coverage():
    out = ("PASS src/filter.test.js\n----------|---------|----------|---------|---------|---\n"
           "File      | % Stmts | % Branch | % Funcs | % Lines | Uncovered Line #s \n"
           "----------|---------|----------|---------|---------|---\n"
           "All files |     100 |    87.5 |     100 |   92.31 |                   \n"
           "Test Suites: 2 passed, 2 total\nTests:       7 passed, 7 total\n")
    assert resolve("npx jest --coverage", 0, out) == "7 tests réussis, couverture des lignes 92,31 %."
    assert resolve("npx jest --coverage", 0, out, "en") == "7 tests passed, 92.31% line coverage."


# ================================================================ pytest : lignes déjà dites en code
# Source : documentation pytest (« -v » : « chemin::test FAILED », résumé court « FAILED id - Type: msg »,
# blocs « ___ nom ___ » avec lignes « E   Type: message » et dernière ligne « fichier:ligne: Type ») ;
# pytest-timeout (« Failed: Timeout (>Ns) from pytest-timeout »).

def _pytest_block(name, lines, where):
    return f"{'_' * 20} {name} {'_' * 20}\n\n    def {name}():\n" + "".join(f"E       {l}\n" for l in lines) + f"\n{where}\n"


def test_pytest_first_failure_adds_exception_type_and_short_message():
    out = ("..F\n" + "=" * 30 + " FAILURES " + "=" * 30 + "\n"
           + _pytest_block("test_rating_delete_16", ["ZeroDivisionError: division by zero"],
                           "tests/test_rating.py:52: ZeroDivisionError")
           + "=" * 20 + " short test summary info " + "=" * 20 + "\n"
           "FAILED tests/test_rating.py::test_rating_delete_16 - ZeroDivisionError: divis...\n"
           "=" * 10 + " 1 failed, 2 passed in 0.06s " + "=" * 10 + "\n")
    assert resolve("pytest -v", 1, out) == (
        "Échec. 1 test échoué, 2 réussis. Premier : test_rating_delete_16, "
        "test_rating.py ligne 52 : ZeroDivisionError, division by zero.")


def test_pytest_long_exception_message_keeps_the_type_only():
    out = (_pytest_block("test_billing_update_42",
                         ["RuntimeError: the connection pool was exhausted after waiting thirty seconds"],
                         "tests/test_billing.py:130: RuntimeError")
           + "FAILED tests/test_billing.py::test_billing_update_42 - RuntimeError: the conn...\n"
           "1 failed, 84 passed in 0.05s\n")
    assert resolve("pytest -q", 1, out) == (
        "Échec. 1 test échoué, 84 réussis. Premier : test_billing_update_42, test_billing.py ligne 130 : RuntimeError.")


def test_pytest_six_word_message_is_read():
    out = (_pytest_block("test_billing_update_42", ["AttributeError: 'NoneType' object has no attribute 'billing'"],
                         "tests/test_billing.py:130: AttributeError")
           + "FAILED tests/test_billing.py::test_billing_update_42 - AttributeError: 'NoneT...\n"
           "1 failed, 84 passed in 0.05s\n")
    assert resolve("pytest -q", 1, out, "en") == (
        "Failed. 1 failed, 84 passed. First: test_billing_update_42, test_billing.py line 130: "
        "AttributeError, NoneType object has no attribute billing.")


def test_pytest_bare_assert_takes_the_type_from_the_last_line():
    out = (_pytest_block("test_upload_delete_06", ["assert 0.6000000000000001 == 0.65 ± 6.5e-07"],
                         "tests/test_upload.py:22: AssertionError")
           + "FAILED tests/test_upload.py::test_upload_delete_06 - assert 0.600000000000000...\n"
           "1 failed, 77 passed in 0.07s\n")
    assert resolve("pytest -rA -q", 1, out) == (
        "Échec. 1 test échoué, 77 réussis. Premier : test_upload_delete_06, test_upload.py ligne 22 : AssertionError.")


def test_pytest_setup_error_names_the_error_class_and_message():
    out = ("...EE\n" + "=" * 30 + " ERRORS " + "=" * 30 + "\n"
           "______ ERROR at setup of test_insert_user ______\n\n    @pytest.fixture\n    def conn():\n"
           ">       c = connect()\n\ntests/test_repo.py:6: \n_ _ _ _ _ _\n"
           ">               sock.connect(sa)\nE               ConnectionRefusedError: [Errno 111] Connection refused\n\n"
           "/usr/lib/python3.13/socket.py:849: ConnectionRefusedError\n"
           "=" * 20 + " short test summary info " + "=" * 20 + "\n"
           "ERROR tests/test_repo.py::test_insert_user - ConnectionRefusedError: [Errno 1...\n"
           "ERROR tests/test_repo.py::test_select_orders - ConnectionRefusedError: [Errno...\n"
           "=" * 10 + " 3 passed, 2 errors in 0.10s " + "=" * 10 + "\n")
    assert resolve("pytest", 1, out) == (
        "Échec. 2 erreurs, 3 réussis. Premier : test_insert_user, test_repo.py ligne 6 : "
        "ConnectionRefusedError, Connection refused.")


def test_pytest_timeout_is_said_in_words():
    out = ("..F.\n" + _pytest_block("test_refill_after_wait", ["Failed: Timeout (>2.0s) from pytest-timeout."],
                                     "ratelimit/bucket.py:9: Failed")
           + "tests/test_bucket.py:14: \n"
           "FAILED tests/test_bucket.py::test_refill_after_wait - Failed: Timeout (>2.0s)...\n"
           "=" * 10 + " 1 failed, 3 passed in 2.06s " + "=" * 10 + "\n")
    assert resolve("pytest --timeout=2", 1, out) == (
        "Échec. 1 test échoué, 3 réussis. Premier : test_refill_after_wait, test_bucket.py ligne 14 : "
        "délai de 2 s dépassé.")
    assert resolve("pytest --timeout=2", 1, out, "en").endswith("test_bucket.py line 14: timed out after 2 s.")


def test_pytest_verbose_lines_name_the_first_failure_without_short_summary():
    out = ("tests/test_refunds.py::test_refund_00 PASSED    [  1%]\n"
           "tests/test_refunds.py::test_refund_03 FAILED    [  6%]\n"
           "tests/test_refunds.py::test_refund_04 PASSED    [  7%]\n"
           + _pytest_block("test_refund_03", ["assert 0.30000000000000004 == 0.31"],
                           "tests/test_refunds.py:13: AssertionError")
           + "=" * 20 + " short test summary info " + "=" * 20 + "\n"
           "SKIPPED [1] tests/test_refunds.py:27: gateway sandbox down\n"
           "=" * 5 + " 1 failed, 2 passed, 1 skipped in 0.05s " + "=" * 5 + "\n")
    assert resolve("pytest -v -rs", 1, out) == (
        "Échec. 1 test échoué, 2 réussis. Premier : test_refund_03, test_refunds.py ligne 13 : AssertionError.")


def test_pytest_sentence_stays_under_twenty_words():
    out = (_pytest_block("test_a_rather_long_test_name", ["sqlite3.OperationalError: unable to open database file"],
                         "tests/test_endpoints.py:6: OperationalError")
           + "ERROR tests/test_endpoints.py::test_a_rather_long_test_name - sqlite3.OperationalError: u...\n"
           "20 passed, 12 errors in 0.04s\n")
    said = resolve("pytest -q", 1, out)
    assert said == ("Échec. 12 erreurs, 20 réussis. Premier : test_a_rather_long_test_name, test_endpoints.py ligne 6 : "
                    "OperationalError, unable to open database file.")
    assert len(said.split()) <= 20


# ================================================================ cargo test : valeurs d'assert_eq!
# Source : std::assert_eq! (« assertion `left == right` failed » puis « left: … », « right: … »).

def test_cargo_test_first_failure_says_left_and_right():
    out = ("running 4 tests\ntest tests::set_and_get ... ok\ntest tests::capacity_rounds_up ... FAILED\n\n"
           "failures:\n\n---- tests::capacity_rounds_up stdout ----\n\n"
           "thread 'tests::capacity_rounds_up' (8371832) panicked at src/lib.rs:20:31:\n"
           "assertion `left == right` failed\n  left: 64\n right: 128\n"
           "note: run with `RUST_BACKTRACE=1` environment variable to display a backtrace\n\n\n"
           "failures:\n    tests::capacity_rounds_up\n\n"
           "test result: FAILED. 3 passed; 1 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s\n")
    assert resolve("cargo test", 101, out) == (
        "Échec. 1 test échoué, 3 réussis. Premier : capacity_rounds_up, lib.rs ligne 20 : gauche 64, droite 128.")
    assert resolve("cargo test", 101, out, "en").endswith("lib.rs line 20: left 64, right 128.")


def test_cargo_test_complex_values_are_not_read():
    out = ("---- tests::cfg stdout ----\nthread 'tests::cfg' panicked at src/lib.rs:9:5:\n"
           "assertion `left == right` failed\n  left: Config { a: 1, b: \"x\" }\n right: Config { a: 2, b: \"x\" }\n"
           "test result: FAILED. 0 passed; 1 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s\n")
    assert resolve("cargo test", 101, out) == "Échec. 1 test échoué. Premier : cfg, lib.rs ligne 9."


# ================================================================ ruff
# Source : documentation ruff (« Found N errors. », « [*] N fixable with the `--fix` option »,
# « All checks passed! », formats concis « f:l:c: CODE » et complet « --> f:l:c » ; échec de
# configuration « ruff failed » puis « Cause: TOML parse error at line N »).

def _ruff_concise(path, n):
    return "".join(f"{path}:{i + 1}:5: F841 Local variable `x{i}` is assigned to but never used\n" for i in range(n))


def test_ruff_counts_errors_file_and_fixable():
    out = (_ruff_concise("report/core.py", 5) + "Found 5 errors.\n"
           "[*] 2 fixable with the `--fix` option (3 hidden fixes can be enabled with the `--unsafe-fixes` option).\n")
    assert resolve("ruff check --output-format=concise .", 1, out) == (
        "Échec. Ruff : 5 erreurs dans report/core.py, 2 corrigeables automatiquement.")
    assert resolve("ruff check --output-format=concise .", 1, out, "en") == (
        "Failed. Ruff: 5 errors in report/core.py, 2 fixable automatically.")


def test_ruff_full_format_several_files_names_the_main_one():
    out = ("F401 [*] `os` imported but unused\n --> tool/runner.py:1:8\n  |\n1 | import os\n\n"
           "B006 Do not use mutable data structures\n --> tool/runner.py:4:21\n\n"
           "E501 Line too long\n --> src/deep/pkg/util.py:9:89\n\n"
           "Found 3 errors.\n[*] 1 fixable with the `--fix` option.\n")
    assert resolve("ruff check tool", 1, out) == (
        "Échec. Ruff : 3 erreurs dans 2 fichiers, surtout tool/runner.py, 1 corrigeable automatiquement.")


def test_ruff_long_paths_keep_the_last_two_parts():
    out = _ruff_concise("src/app/models/user.py", 2) + "Found 2 errors.\n"
    assert resolve("ruff check src", 1, out) == "Échec. Ruff : 2 erreurs dans models/user.py."


def test_ruff_all_checks_passed():
    assert resolve("ruff check .", 0, "All checks passed!\n") == "Ruff : aucun problème."
    assert resolve("ruff check .", 0, "All checks passed!\n", "en") == "Ruff: all checks passed."


def test_ruff_config_error_names_file_line_and_field():
    out = ("ruff failed\n  Cause: Failed to parse /home/user/projects/billing/pyproject.toml\n"
           "  Cause: TOML parse error at line 11, column 1\n   |\n11 | max-complexity = 8\n   | ^^^^^^^^^^^^^^\n"
           "unknown field `max-complexity`, expected one of `allowed-confusables`, `dummy-variable-rgx`\n")
    assert resolve("ruff check src", 2, out) == (
        "Échec. Configuration de ruff invalide, pyproject.toml ligne 11 : unknown field max-complexity.")


def test_ruff_without_summary_left_to_the_model():
    assert resolve("ruff check .", 1, _ruff_concise("a.py", 30)) is None


# ================================================================ ESLint : configuration, avertissements
# Source : ESLint 9 (« ESLint couldn't find an eslint.config.(js|mjs|cjs) file. ») et versions
# antérieures (« ESLint couldn't find a configuration file. ») ; résumé « ✖ N problems (E errors, W warnings) ».

def test_eslint_v9_missing_flat_config():
    out = ("\nOops! Something went wrong! :(\n\nESLint: 9.39.5\n\n"
           "ESLint couldn't find an eslint.config.(js|mjs|cjs) file.\n\n"
           "From ESLint v9.0.0, the default configuration file is now eslint.config.js.\n")
    assert resolve("eslint deploy.js", 2, out) == "Échec. ESLint ne trouve aucun fichier eslint.config."
    assert resolve("eslint deploy.js", 2, out, "en") == "Failed. ESLint found no eslint.config file."


def test_eslint_errors_and_warnings_both_counted():
    out = ("\n/p/src/cart/basket.js\n   1:10  error    'formatPrice' is defined but never used  no-unused-vars\n"
           "  11:3   warning  Unexpected console statement             no-console\n"
           "  17:9   error    'discount' is assigned a value but never used  no-unused-vars\n\n"
           "✖ 3 problems (2 errors, 1 warning)\n")
    assert resolve("npx eslint src", 1, out) == (
        "Échec, 2 erreurs et 1 avertissement. basket.js ligne 1 : formatPrice is defined but never used.")


# ================================================================ pylint, shellcheck, yamllint, mypy
# Sources : pylint (« Your code has been rated at X/10 », messages « f:l:c: C0114: … ») ;
# ShellCheck, format tty (« In f line N: » puis « ^-- SC2034 (warning): … ») ;
# yamllint, format standard (« fichier » puis « l:c  niveau  message  (règle) ») ;
# mypy (« f:l: error: msg  [code] », « Found N errors in M files », « Success: no issues found »).

def test_pylint_score_and_message_count():
    out = ("************* Module core\n"
           "invoice/core.py:1:0: C0114: Missing module docstring (missing-module-docstring)\n"
           "invoice/core.py:3:0: W0102: Dangerous default value [] as argument (dangerous-default-value)\n"
           "invoice/core.py:9:4: E1101: Module 'os' has no 'foo' member (no-member)\n\n"
           "-----------------------------------\nYour code has been rated at 1.66/10\n")
    assert resolve("pylint invoice/core.py", 22, out) == (
        "Échec. Pylint : note de 1,66 sur 10, 3 messages, dont 1 erreur.")
    assert resolve("pylint invoice/core.py", 22, out, "en") == (
        "Failed. Pylint score 1.66 out of 10, 3 messages, including 1 error.")


def test_pylint_perfect_score():
    out = "\n" + "-" * 70 + "\nYour code has been rated at 10.00/10 (previous run: 9.50/10, +0.50)\n"
    assert resolve("pylint app", 0, out) == "Pylint : note de 10 sur 10."


def test_shellcheck_counts_findings_and_reads_the_first():
    out = ("\nIn backup.sh line 5:\nRETENTION=14\n^-------^ SC2034 (warning): RETENTION appears unused. "
           "Verify use (or export if used externally).\n\n\nIn backup.sh line 7:\ncd $DEST\n"
           "^------^ SC2164 (warning): Use 'cd ... || exit' or 'cd ... || return' in case cd fails.\n\n"
           "In backup.sh line 8:\nfor f in $(ls $SRC/*.csv); do\n         ^--------------^ SC2045 (error): "
           "Iterating over ls output is fragile. Use globs.\n              ^--^ SC2086 (info): Double quote to "
           "prevent globbing and word splitting.\n\nFor more information:\n"
           "  https://www.shellcheck.net/wiki/SC2045 -- Iterating over ls output is fragi...\n")
    assert resolve("shellcheck backup.sh", 1, out) == (
        "Échec. ShellCheck : 4 remarques. backup.sh ligne 5 : SC2034, RETENTION appears unused.")
    assert resolve("shellcheck backup.sh", 1, out, "en") == (
        "Failed. ShellCheck: 4 findings. backup.sh line 5: SC2034, RETENTION appears unused.")


def test_yamllint_counts_errors_and_warnings_and_reads_the_first_error():
    out = ("./ci.yaml\n  1:1       warning  missing document start \"---\"  (document-start)\n"
           "  4:16      error    too many spaces inside brackets  (brackets)\n"
           "  9:5       error    wrong indentation: expected 6 but found 4  (indentation)\n\n"
           "./compose.yml\n  11:34     error    trailing spaces  (trailing-spaces)\n")
    assert resolve("yamllint .", 1, out) == (
        "Échec, 3 erreurs et 1 avertissement. ci.yaml ligne 4 : too many spaces inside brackets.")


def test_yamllint_warnings_only():
    out = ("./ci.yaml\n  1:1       warning  missing document start \"---\"  (document-start)\n"
           "  2:1       warning  truthy value should be one of [false, true]  (truthy)\n"
           "./a.yml\n  1:1       warning  missing document start \"---\"  (document-start)\n")
    assert resolve("yamllint .", 0, out) == "Aucune erreur, 3 avertissements. ci.yaml ligne 1 : missing document start."


def test_mypy_errors_counted_with_files():
    out = ("src/app.py:12: error: Incompatible types in assignment (expression has type \"str\", variable has type"
           " \"int\")  [assignment]\nsrc/db.py:4: error: Module \"x\" has no attribute \"y\"  [attr-defined]\n"
           "src/db.py:9: note: Revealed type is \"builtins.int\"\nFound 2 errors in 2 files (checked 7 source files)\n")
    assert resolve("mypy src", 1, out) == (
        "Échec, 2 erreurs dans 2 fichiers. app.py ligne 12 : Incompatible types in assignment.")


def test_mypy_success():
    out = "\n".join(["note: x"] * 4) + "\nSuccess: no issues found in 12 source files\n"
    assert resolve("mypy .", 0, out) == "Mypy : aucun problème dans 12 fichiers."


def test_tsc_found_errors_in_files():
    out = ("src/a.ts:3:1 - error TS1005: ';' expected.\n\n3 x\n  ~\n"
           "src/b.ts:9:4 - error TS2304: Cannot find name 'foo'.\n\nFound 2 errors in 2 files.\n")
    assert resolve("npx tsc", 1, out) == "Échec, 2 erreurs dans 2 fichiers. a.ts ligne 3 : ; expected."


# ================================================================ cargo réussi, clippy
# Source : cargo (« Compiling nom vX (chemin) », « Checking … », « Locking N packages »,
# « warning: `nom` (lib) generated N warnings (run `cargo clippy --fix …` to apply M suggestions) »,
# « Finished `dev` profile … in Ns », « error: could not compile … due to N previous errors; M warnings emitted »).

def test_cargo_build_success_names_the_crate():
    out = ("    Updating crates.io index\n     Locking 15 packages to latest compatible versions\n"
           "   Compiling memchr v2.8.3\n   Compiling logscan v0.2.0 (/home/user/src/logscan)\n"
           "    Finished `dev` profile [unoptimized + debuginfo] target(s) in 8.95s\n")
    assert resolve("cargo build", 0, out) == "Compilation de logscan terminée, sans avertissement, 15 paquets verrouillés."
    assert resolve("cargo build", 0, out, "en") == "Build of logscan finished, no warnings, 15 packages locked."


def test_cargo_clippy_counts_warnings_and_fixable():
    out = ("    Checking tally v0.1.0 (/Users/user/projects/rs-clippy)\nwarning: unneeded `return` statement\n"
           "  --> src/lib.rs:28:5\n\nwarning: `tally` (lib) generated 27 warnings (run `cargo clippy --fix --lib "
           "-p tally` to apply 26 suggestions)\n    Finished `dev` profile [unoptimized + debuginfo] target(s) in 0.12s\n")
    assert resolve("cargo clippy", 0, out) == (
        "Clippy : vérification de tally terminée, 27 avertissements, 26 corrigeables automatiquement.")


def test_cargo_several_warning_summaries_are_not_added():
    out = ("   Compiling a v0.1.0 (/p/a)\nwarning: unused\nwarning: `a` (lib) generated 2 warnings\n"
           "warning: `a` (lib test) generated 2 warnings (2 duplicates)\n   Compiling b v0.1.0 (/p/b)\n"
           "    Finished `dev` profile [unoptimized + debuginfo] target(s) in 1.2s\n")
    assert resolve("cargo build", 0, out) == "Compilation terminée, avec avertissements."


def test_cargo_failed_build_adds_the_warnings_emitted():
    out = ("    Checking sysmon v0.1.0 (/home/user/src/sysmon)\nwarning: unused import: `std::fs`\n"
           " --> src/main.rs:2:5\n\nerror[E0282]: type annotations needed for `Vec<_>`\n --> src/metrics.rs:4:9\n"
           "  |\n4 |     let mut samples = Vec::new();\n\nwarning: `sysmon` (bin \"sysmon\") generated 8 warnings\n"
           "error: could not compile `sysmon` (bin \"sysmon\") due to 1 previous error; 8 warnings emitted\n")
    assert resolve("cargo check", 101, out) == (
        "Échec, 1 erreur et 8 avertissements. metrics.rs ligne 4 : E0282, type annotations needed for Vec<_>.")


# ================================================================ panique Rust
# Source : std (Rust 1.73+ : « thread 'main' panicked at f.rs:L:C: » puis le message ; avant :
# « panicked at 'msg', f.rs:L:C ») ; Debug de std::io::Error (« Os { code, kind, message } »).

def test_rust_panic_message_cut_on_words():
    out = ("   Compiling csvsum v0.1.0 (/Users/user/src/csvsum)\n    Finished `dev` profile in 0.23s\n"
           "     Running `target/debug/csvsum data.csv`\n\nthread 'main' (8325608) panicked at src/main.rs:9:21:\n"
           "index out of bounds: the len is 3 but the index is 3\n"
           "note: run with `RUST_BACKTRACE=1` environment variable to display a backtrace\n")
    assert resolve("cargo run -- data.csv", 101, out) == (
        "Échec. Panique à main.rs ligne 9 : index out of bounds: the len is 3 but the index is 3.")


def test_rust_panic_unwrap_on_io_error_says_the_io_message():
    out = ("     Running `target/debug/confload`\n\nthread 'main' (2029791) panicked at src/main.rs:4:59:\n"
           "called `Result::unwrap()` on an `Err` value: Os { code: 2, kind: NotFound, message: \"No such file or "
           "directory\" }\nnote: run with `RUST_BACKTRACE=1` environment variable to display a backtrace\n")
    assert resolve("cargo run", 101, out) == (
        "Échec. Panique à main.rs ligne 4 : unwrap sur une erreur, No such file or directory.")
    assert resolve("cargo run", 101, out, "en") == (
        "Failed. Panic at main.rs line 4: unwrap on an error, No such file or directory.")


def test_rust_panic_old_format():
    out = "thread 'main' panicked at 'attempt to divide by zero', src/main.rs:3:13\nnote: run with backtrace\n"
    assert resolve("./target/debug/calc", 101, out) == (
        "Échec. Panique à main.rs ligne 3 : attempt to divide by zero.")


# ================================================================ gcc, clang : réussite avec avertissements
# Source : manuels GCC et Clang (« f:l:c: warning: msg [-Wflag] », clang « N warnings generated. »,
# gcc en locale fr_FR « attention : » ou « avertissement : »). Le compte de gcc n'est jamais fait :
# il n'imprime pas de total et les lignes ne donnent pas le compte réel (L2).

_GCC_WARN = ("legacy.c: In function ‘parse_level’:\n"
             "legacy.c:6:43: warning: unused parameter ‘unused_hint’ [-Wunused-parameter]\n"
             "    6 | static int parse_level(const char *s, int unused_hint) {\n"
             "      |                                       ~~~~^~~~~~~~~~~\n"
             "legacy.c: In function ‘ratio’:\n"
             "legacy.c:59:12: warning: ‘pct’ may be used uninitialized [-Wmaybe-uninitialized]\n"
             "   59 |     return pct;\n      |            ^~~\n")


def test_gcc_success_with_warnings_names_file_and_first_warning():
    assert resolve("gcc -Wall -Wextra -O2 -c legacy.c", 0, _GCC_WARN) == (
        "Compilation réussie avec avertissements dans legacy.c. Premier, ligne 6 : unused parameter unused_hint.")
    assert resolve("gcc -Wall -Wextra -O2 -c legacy.c", 0, _GCC_WARN, "en") == (
        "Compiled with warnings in legacy.c. First, line 6: unused parameter unused_hint.")


def test_clang_success_uses_its_own_warning_total():
    out = _GCC_WARN.replace("legacy.c", "sensor.c") + "2 warnings generated.\n"
    assert resolve("clang -Wall -c sensor.c", 0, out) == (
        "Compilation réussie avec 2 avertissements dans sensor.c. Premier, ligne 6 : unused parameter unused_hint.")


def test_gcc_success_several_files_names_the_file_of_the_first_warning():
    out = _GCC_WARN + "util.c:3:5: warning: unused variable ‘n’ [-Wunused-variable]\n    3 | int n;\n"
    assert resolve("gcc -c legacy.c util.c", 0, out) == (
        "Compilation réussie avec avertissements dans legacy.c et util.c. Premier, legacy.c ligne 6 : "
        "unused parameter unused_hint.")


def test_gcc_french_warnings_are_not_read_in_an_english_sentence():
    out = ("legacy.c: Dans la fonction « parse_level »:\n"
           "legacy.c:6:43: attention : paramètre « unused_hint » inutilisé [-Wunused-parameter]\n"
           "    6 | static int parse_level(const char *s, int unused_hint) {\n"
           "legacy.c:9:3: attention : variable « x » inutilisée [-Wunused-variable]\n")
    assert resolve("gcc -Wall -c legacy.c", 0, out, "en") == "Compiled with warnings in legacy.c. First, line 6."
    assert resolve("gcc -Wall -c legacy.c", 0, out) == (
        "Compilation réussie avec avertissements dans legacy.c. Premier, ligne 6 : paramètre unused_hint inutilisé.")


def test_compiler_success_without_warning_left_alone():
    out = "\n".join(f"note: {i}" for i in range(5))
    assert resolve("gcc -c a.c", 0, out) is None


# ================================================================ édition de liens macOS (ld64)
# Source : ld64 (« Undefined symbols for architecture arm64: », « "_sym", referenced from: »,
# « _fn in obj.o ») ; un symbole C porte un « _ » de tête sous Mach-O.

def test_ld64_undefined_symbol_named_with_its_caller():
    out = ("Undefined symbols for architecture arm64:\n  \"_hash_bytes\", referenced from:\n"
           "      _main in main-72fd86.o\nld: symbol(s) not found for architecture arm64\n"
           "clang: error: linker command failed with exit code 1 (use -v to see invocation)\n")
    assert resolve("clang -o hashdemo main.c hash.c", 1, out) == (
        "Échec. Édition de liens : symbole hash_bytes non défini, utilisé dans main.")
    assert resolve("clang -o hashdemo main.c hash.c", 1, out, "en") == (
        "Failed. Link error: undefined symbol hash_bytes, referenced from main.")


def test_ld64_several_undefined_symbols_counted():
    out = ("Undefined symbols for architecture x86_64:\n  \"_a\", referenced from:\n      _main in m.o\n"
           "  \"_b\", referenced from:\n      _main in m.o\nld: symbol(s) not found for architecture x86_64\n")
    assert resolve("cc m.c", 1, out) == "Échec. Édition de liens : 2 symboles non définis, dont a."


# ================================================================ commandes enchaînées, phrase trop longue
# Une commande suivie d'une autre (&&, ;, ||, tube) mêle deux sorties : un bilan de compilation ou de
# lint tairait la sortie du programme lancé ensuite. Ces phrases restent au modèle.

def test_chained_commands_are_left_to_the_model():
    program = "count=12 total=65\nmean=5.42 median=5\n"
    assert resolve("gcc -Wall -o stats stats.c && ./stats data.txt", 0, _GCC_WARN + program) is None
    cargo = ("   Compiling app v0.1.0 (/p/app)\n    Finished `dev` profile [unoptimized + debuginfo] target(s) in 1.0s\n"
             "hello\n")
    assert resolve("cargo build && ./target/debug/app", 0, cargo) is None
    assert resolve("go test ./... ; echo fini", 0, "ok  \texample.invalid/a\t0.01s\nfini\n") is None
    assert resolve("ruff check . && pytest", 1, _ruff_concise("a.py", 2) + "Found 2 errors.\n") is None


def test_gcc_long_first_warning_drops_the_message():
    out = ("sensor.c: In function ‘read_0’:\nsensor.c:10:14: warning: format ‘%d’ expects argument of type ‘int’, "
           "but argument 2 has type ‘double’ [-Wformat=]\n   10 |     printf(\"%d\\n\", r->value);\n")
    assert resolve("gcc -Wall -Wextra -c sensor.c", 0, out, "en") == "Compiled with warnings in sensor.c. First, line 10."


def test_go_test_panic_names_the_failing_test_not_the_runtime():
    out = ("--- FAIL: TestParse (0.00s)\npanic: runtime error: index out of range [3] with length 3 [recovered]\n"
           "\tpanic: runtime error: index out of range [3] with length 3\n\ngoroutine 7 [running]:\n"
           "testing.tRunner.func1.2({0x5bd0a0, 0xc000014108})\n\t/usr/local/go/src/testing/testing.go:1632 +0x230\n"
           "FAIL\texample.invalid/p\t0.01s\n")
    assert resolve("go test ./...", 1, out) == "Échec. 1 test échoué. Paquet p, TestParse."


# Jest : un seuil de couverture manqué fait échouer la commande alors que tous les tests passent
# (« Jest: "global" coverage threshold for lines (100%) not met ») ; la phrase garde l'échec.

def test_all_tests_passed_but_command_failed_keeps_the_failure():
    out = ("File      | % Stmts | % Branch | % Funcs | % Lines | Uncovered Line #s\n"
           "All files |   30.64 |    16.66 |   14.28 |   30.64 |\n"
           'Jest: "global" coverage threshold for lines (100%) not met: 30.64%\n'
           "Tests:       40 passed, 40 total\n")
    assert resolve("npx jest src/parse.test.ts", 1, out) == "Échec. 40 tests réussis, couverture des lignes 30,64 %."
