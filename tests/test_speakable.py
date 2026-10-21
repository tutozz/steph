"""Lecture telle quelle (L4) : les suites de symboles ne sont pas lues à voix haute.

Exemples tirés des sorties publiques de GNU make, nslookup, helm lint et prettier (split dev
du banc v3 : v3-build-native-0008, v3-network-0019, v3-containers-0022, v3-lint-format-0003).
"""

from steph.textproc import strip_symbol_runs


def test_make_asterisks_are_dropped():
    assert strip_symbol_runs("make: *** Pas de cible spécifiée. Arrêt.") == "make: Pas de cible spécifiée. Arrêt."
    assert (strip_symbol_runs("Makefile:7: *** séparateur manquant. Arrêt.")
            == "Makefile:7: séparateur manquant. Arrêt.")


def test_nslookup_double_asterisk_is_dropped():
    assert (strip_symbol_runs("** server can't find x.invalid: NXDOMAIN")
            == "server can't find x.invalid: NXDOMAIN")


def test_helm_arrow_and_info_tag_are_dropped():
    text = "==> Linting storefront\n[INFO] Chart.yaml: icon is recommended\n1 chart(s) linted, 0 chart(s) failed"
    assert strip_symbol_runs(text) == ("Linting storefront\nChart.yaml: icon is recommended\n"
                                       "1 chart(s) linted, 0 chart(s) failed")


def test_warning_and_error_tags_keep_their_word():
    text = "[warn] src/utils/money.js\n[ERROR] build failed"
    assert strip_symbol_runs(text) == "warn src/utils/money.js\nERROR build failed"


def test_heading_hashes_and_wrapping_dashes_are_dropped():
    assert strip_symbol_runs("### Résumé\n===\nfini") == "Résumé\n===\nfini"
    assert strip_symbol_runs("--- example.com ping statistics ---") == "example.com ping statistics"


def test_symbols_carrying_a_fact_are_kept():
    # apt-cache policy : *** marque la version installée (v3-packages-system-0066)
    assert strip_symbol_runs(" *** 2.41-12+deb13u3 100") == " *** 2.41-12+deb13u3 100"
    # ls -l : ---------- est le mode, aucune permission (v3-permissions-users-0013)
    line = "----------  1 user  wheel   6 Sep 28 04:08 notes.txt"
    assert strip_symbol_runs(line) == line
    assert strip_symbol_runs("----------\n-rw-r--r--") == "----------\n-rw-r--r--"
    # diff -u : --- désigne l'ancien fichier, face à +++ (v3-files-0019)
    assert strip_symbol_runs("--- a.conf.orig\n+++ a.conf") == "--- a.conf.orig\n+++ a.conf"
    # go test : --- FAIL porte le verdict (v3-tests-0061)
    assert strip_symbol_runs("--- FAIL: TestPrice (0.00s)") == "--- FAIL: TestPrice (0.00s)"
    # colonnes soulignées (kubectl describe, sqlite) : la ligne reste entière
    assert strip_symbol_runs("----     ------     ----") == "----     ------     ----"


def test_meaningful_single_symbols_are_kept():
    for text in ("TCP *:8765 (LISTEN)",
                 "*         staging   staging",
                 "vm_stat: illegal option -- x",
                 "uname : option non reconnue '--arch'",
                 "2*(3+4)*5 = 70",
                 "# Keyspace",
                 "**/*.py",
                 "Address: 192.0.2.200#53",
                 "a => b",
                 "[main 8fc5f2f] Corrige l'arrondi",
                 "[1] 4242"):
        assert strip_symbol_runs(text) == text


def test_only_symbols_keeps_the_original():
    assert strip_symbol_runs("***") == "***"
    assert strip_symbol_runs("###\n***") == "###\n***"
