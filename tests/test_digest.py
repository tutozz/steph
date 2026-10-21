"""Tri déterministe des sorties structurées, avant le modèle : réseau et disques."""

import json
from pathlib import Path

import pytest

from steph.digest import digest
from steph.prompts import summary_messages

DATA = Path(__file__).parent / "data"
BENCH = Path(__file__).parent.parent / "bench"


def fixtures() -> list[dict]:
    return [f for name in ("fixtures.json", "extra_fixtures.json") for f in json.loads((BENCH / name).read_text())]


def fixture(cmd: str) -> str:
    return next(f["output"] for f in fixtures() if f["cmd"] == cmd)


def test_ip_brief_keeps_active_ipv4_and_counts_docker():
    out = digest("ip -br addr", fixture("ip -br addr"))
    assert out.splitlines() == [
        "wlp0s20f3 192.168.1.20",
        "tailscale0 100.64.0.10",
        "tun0 10.9.0.2",
        "réseaux virtuels : 8",
    ]


def test_ip_a_on_proxmox_keeps_bridge_with_host_ip():
    out = digest("ip a", (DATA / "ip_a_proxmox.txt").read_text())
    lines = out.splitlines()
    assert lines[:3] == ["tailscale0 100.96.222.123", "vmbr0 192.168.1.200", "pan0 192.168.44.1"]
    assert lines[-1].startswith("réseaux virtuels : ")
    assert "lo" not in out.split() and "aa:bb" not in out


def test_ifconfig_macos_keeps_wifi_and_vpn():
    out = digest("ifconfig", (DATA / "ifconfig_macos.txt").read_text())
    assert out.splitlines() == ["en0 192.168.1.62", "utun4 100.68.82.46"]


def test_df_keeps_real_disks_only():
    out = digest("df -h", fixture("df -h"))
    assert out.splitlines() == [
        "racine : 685G libres sur 953G, 29 %",
        "boot : 284M libres sur 974M, 69 %",
    ]


def test_df_on_proxmox():
    out = digest("df -h", (DATA / "df_proxmox.txt").read_text())
    assert out.splitlines() == [
        "racine : 8.9G libres sur 94G, 91 %",
        "backup-hdd : 134G libres sur 442G, 70 %",
    ]


def test_lspci_keeps_gpu_and_network_at_800_chars():
    """Cas fx29 : sur 800 caractères, le GPU et le réseau tombaient dans le milieu tronqué."""
    out = digest("lspci", fixture("lspci"), max_chars=800)
    lines = out.splitlines()
    assert lines[0] == "GPU : NVIDIA Corporation GA106 [GeForce RTX 3060 Lite Hash Rate]"
    assert lines[1] == "réseau : Realtek Semiconductor Co., Ltd. RTL8111/8168/8411 PCI Express Gigabit Ethernet Controller"
    assert lines[2] == "chipset : Advanced Micro Devices, Inc. [AMD] Starship/Matisse Root Complex"
    assert lines[3] == "USB : 2"
    assert lines[4] == "autres périphériques : 14"
    assert len(out) < 800


LSPCI_K = """00:02.0 VGA compatible controller: Intel Corporation TigerLake-LP GT2 [Iris Xe Graphics] (rev 01)
\tDeviceName: Onboard IGD
\tSubsystem: Dell TigerLake-LP GT2 [Iris Xe Graphics]
\tKernel driver in use: i915
\tKernel modules: i915
00:14.3 Network controller: Intel Corporation Wi-Fi 6 AX201
\tSubsystem: Intel Corporation Wi-Fi 6 AX201
\tKernel driver in use: iwlwifi
\tKernel modules: iwlwifi
00:1f.3 Audio device: Intel Corporation Tiger Lake-LP Smart Sound Technology Audio Controller
\tSubsystem: Dell Device 0894
"""

LSPCI_NN = """00:02.0 VGA compatible controller [0300]: Intel Corporation TigerLake-LP GT2 [Iris Xe Graphics] [8086:9a49] (rev 01)
00:14.3 Network controller [0280]: Intel Corporation Wi-Fi 6 AX201 [8086:a0f0]
02:00.0 Ethernet controller [0200]: Realtek Semiconductor Co., Ltd. RTL8111/8168/8411 PCI Express Gigabit Ethernet Controller [10ec:8168] (rev 15)
00:00.0 Host bridge [0600]: Intel Corporation Device [8086:9a14] (rev 01)
"""


def test_lspci_dash_k_keeps_kernel_driver_for_gpu_and_network():
    out = digest("lspci -k", LSPCI_K)
    assert out.splitlines() == [
        "GPU : Intel Corporation TigerLake-LP GT2 [Iris Xe Graphics] (pilote : i915)",
        "réseau : Intel Corporation Wi-Fi 6 AX201 (pilote : iwlwifi)",
        "autres périphériques : 1",
    ]


def test_lspci_dash_nn_strips_hex_ids_and_revision():
    out = digest("lspci -nn", LSPCI_NN)
    assert out.splitlines() == [
        "GPU : Intel Corporation TigerLake-LP GT2 [Iris Xe Graphics]",
        "réseau : Intel Corporation Wi-Fi 6 AX201",
        "réseau : Realtek Semiconductor Co., Ltd. RTL8111/8168/8411 PCI Express Gigabit Ethernet Controller",
        "chipset : Intel Corporation Device",
    ]


def test_lspci_unparsable_output_falls_back_to_raw():
    assert digest("lspci", "lspci: command not found") is None


@pytest.mark.parametrize("cmd", ["ls -la", "git status", "npm run build", "ipconfig", "dfx"])
def test_other_commands_untouched(cmd):
    assert digest(cmd, "sortie brute\nligne 2") is None


def test_unparsable_output_falls_back_to_raw():
    assert digest("ip a", "Command 'ip' not found") is None


class RecordingLLM:
    active = False
    last_done = 0.0

    def __init__(self):
        self.sent = []

    def healthy(self):
        return True

    def stream(self, msgs, **kw):
        self.sent.append(msgs)
        yield "résumé"

    def complete(self, msgs, **kw):
        return "description"


def narrator_after(cmd, output, code=0):
    from test_rules import FakeSpeaker, run_cmd

    from steph.config import Config
    from steph.narrator import Narrator
    from steph.session import Session

    llm = RecordingLLM()
    nar = Narrator(Config(), Session(), FakeSpeaker(), llm)
    nar.llm_ready = True
    run_cmd(nar, cmd, output, code=code)
    return nar, llm


def test_narrator_sends_the_digest_of_the_full_output():
    # lspci is now said in code; grep output still reaches the model, through its digest
    cmd = "grep -rn 'def ' /home/alice/Projects/steph/src/steph/llm.py"
    _, llm = narrator_after(cmd, fixture(cmd))
    user = llm.sent[-1][1]["content"]
    assert "8 éléments : def __init__" in user


def test_details_key_keeps_a_detailed_prompt():
    nar, llm = narrator_after("npm run build", fixture("npm run build"))
    nar._details(nar.s.commands[-1])
    system = llm.sent[-1][0]["content"]
    assert system != summary_messages("x", 0, 0, "", 0)[0]["content"]
    assert "15 mots" not in system


def test_sudo_paths_and_options_are_recognised():
    assert digest("sudo /usr/sbin/ip -4 a", fixture("ip -br addr")).startswith("wlp0s20f3")
    assert digest("/sbin/ifconfig -a", (DATA / "ifconfig_macos.txt").read_text()).startswith("en0")
    assert digest("df -hT", fixture("df -h")).startswith("racine")


# ---------------------------------------------------------------- listes comptées en code
@pytest.mark.parametrize("cmd, expected", [
    ("docker ps", "9 conteneurs, 8 actifs ; shopapp_vault redémarre en boucle"),
    ("sort /etc/passwd | cut -d: -f1 | head -30", "30 éléments affichés : abrt, adm, akmods"),
    ("ls -la /etc | head -40", "37 éléments affichés : abrt, adjtime, aliases"),
    ("ls /home/alice/Projects/steph", "6 éléments : bench, pyproject.toml, README.md"),
    ("find /usr/share/doc -maxdepth 1 -name 'py*' | head -20", "20 éléments affichés : python-systemd, "),
    ("du -sh /home/alice/Projects/* 2>/dev/null | sort -h | tail",
     "10 éléments affichés, les plus gros : OLD_SHOPAPP 12G, "),
])
def test_lists_are_counted_in_code(cmd, expected):
    assert digest(cmd, fixture(cmd)).startswith(expected)


def test_docker_ps_healthy_containers_use_the_plain_count():
    """Sans conteneur Restarting/Exited, le format court d'origine reste inchangé."""
    out = ("CONTAINER ID   IMAGE   COMMAND   CREATED   STATUS   PORTS   NAMES\n"
           "abc123   nginx   \"nginx\"   2 days ago   Up 2 days   80/tcp   web\n"
           "def456   redis   \"redis\"   2 days ago   Up 2 days   6379/tcp   cache\n")
    assert digest("docker ps", out).startswith("2 conteneurs : web, cache")


def test_failed_list_command_not_counted():
    assert digest("ls /nope", "ls: /nope: Aucun fichier ou dossier de ce nom") is None


@pytest.mark.parametrize("cmd", ["cat notes.txt", "ls", "docker ps -q"])
def test_short_or_non_list_outputs_untouched(cmd):
    assert digest(cmd, "une\ndeux") is None


def test_list_count_keeps_the_content_for_the_model():
    lines = [f"2026-09-27 erreur n°{i} : disque {i} en panne" for i in range(40)]
    out = digest("journalctl -b | grep erreur", "\n".join(lines), max_chars=1500)
    assert out.splitlines()[0].startswith("40 éléments")
    assert "disque 39 en panne" in out  # la fin de la sortie reste visible


# ---------------------------------------------------------------- phrases entièrement résolues en code
import importlib.util

from steph.digest import resolve

CASES_DIR = BENCH.parent / "benchmark/tools/cases"
REAL = CASES_DIR / "real_outputs"


def fixture_case(cmd: str) -> tuple[str, int, str]:
    f = next(f for f in fixtures() if f["cmd"] == cmd)
    return f["cmd"], f["exit"], f["output"]


def bench_case(module: str, cid: str, lang: str = "en") -> tuple[str, int, str]:
    spec = importlib.util.spec_from_file_location(module, CASES_DIR / f"{module}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    case = next(c for c in mod.CASES if c["id"] == cid)
    out = case["output"]
    return case["cmd"], case["exit"], out[lang] if isinstance(out, dict) else out


@pytest.mark.parametrize("cmd, expected", [
    ("gcc -x c - -o /dev/null <<< 'int main(){ int x = ; return 0; }'",
     "Échec. stdin ligne 1 : expected expression before ; token."),
    ("npm run build",
     "Échec. Header.tsx ligne 42 : Property titel does not exist on type Props. Did you mean title?"),
])
def test_compile_errors_from_fixtures(cmd, expected):
    assert resolve(*fixture_case(cmd)) == expected


@pytest.mark.parametrize("cid, expected", [
    ("build-gcc-undeclared", "Échec. main.c ligne 14 : coutn undeclared (first use in this function)."),
    ("build-tsc-type-error",
     "Échec. utils.ts ligne 18 : Argument of type string is not assignable to parameter of type number."),
    ("build-rustc-borrow-e0502",
     "Échec. lib.rs ligne 47 : E0502, cannot borrow data as mutable because it is also borrowed as immutable."),
    ("runtime-python-traceback", "Échec. process_orders.py ligne 33 : KeyError discount_rate."),
])
def test_compile_and_runtime_errors_from_bench(cid, expected):
    assert resolve(*bench_case("dev_failures", cid)) == expected


def test_compile_error_count_when_several():
    out = ("src/a.ts:3:1 - error TS1005: ';' expected.\n\n3 x\n  ~\n"
           "src/b.ts:9:4 - error TS2304: Cannot find name 'foo'.\n\nFound 2 errors in 2 files.\n")
    assert resolve("npx tsc", 1, out) == "Échec, 2 erreurs dans 2 fichiers. a.ts ligne 3 : ; expected."


def test_python_traceback_from_fixture():
    assert resolve(*fixture_case("python3 -c 'import json; d={}; print(d[\"key\"])'")) == \
        "Échec. string ligne 1 : KeyError key."


def test_compile_error_ignored_on_success():
    # D6-A : une compilation réussie avec avertissement se dit comme telle, jamais comme un échec
    assert resolve("gcc main.c", 0, "main.c:3:1: warning: unused variable 'x'") == (
        "Compilation réussie avec avertissements dans main.c. Premier, ligne 3 : unused variable x.")


@pytest.mark.parametrize("cid, expected", [
    ("tests-pytest-failures",
     "Échec. 3 tests échoués, 118 réussis. Premier : test_apply_discount, test_orders.py ligne 47 : AssertionError."),
    ("tests-pytest-all-green", "42 tests réussis."),
    ("tests-jest-failing-suite",
     "Échec. 1 test échoué, 7 réussis. Premier : pricing utils, applies bulk discount, pricing.test.js ligne 14."),
    ("tests-cargo-test-failure",
     "Échec. 1 test échoué, 13 réussis. Premier : applies_bulk_rate, discount.rs ligne 38 : gauche 90, droite 81."),
])
def test_test_runners(cid, expected):
    assert resolve(*bench_case("dev_failures", cid)) == expected


def test_pytest_quiet_summary_counts_errors():
    out = "..F.E\n1 failed, 3 passed, 1 error in 0.42s\n"
    assert resolve("pytest -q", 1, out).startswith("Échec. 1 test échoué, 1 erreur, 3 réussis.")


def test_vitest_failing_suite():
    out = (
        " RUN  v5.0.2 /project\n\n"
        " ❯ src/sum.test.js (2 tests | 1 failed) 4ms\n"
        "   × fails on purpose 3ms\n\n"
        "⎯⎯⎯⎯⎯⎯⎯ Failed Tests 1 ⎯⎯⎯⎯⎯⎯⎯\n\n"
        " FAIL  src/sum.test.js > fails on purpose\n"
        "AssertionError: expected 4 to be 5\n\n"
        " Test Files  1 failed | 1 passed (2)\n"
        "      Tests  1 failed | 2 passed (3)\n"
    )
    assert resolve("npx vitest run", 1, out) == (
        "Échec. 1 test échoué, 2 réussis. Premier : fails on purpose, sum.test.js.")


def test_vitest_all_passed():
    out = " Test Files  2 passed (2)\n      Tests  3 passed (3)\n"
    assert resolve("npx vitest run", 0, out) == "3 tests réussis."


def test_eslint_multi_file_reports_count_and_first_error():
    out = (
        "\n/project/src/a.js\n"
        "  1:10  error    'foo' is defined but never used      no-unused-vars\n"
        "  3:9   warning  Expected '===' and instead saw '=='  eqeqeq\n"
        "  3:17  error    'console' is not defined             no-undef\n"
        "  3:29  error    'y' is not defined                   no-undef\n\n"
        "/project/src/b.js\n"
        "  1:10  error  'bar' is defined but never used              no-unused-vars\n"
        "  2:7   error  'unused' is assigned a value but never used  no-unused-vars\n\n"
        "/project/src/c.js\n"
        "  2:1  error  'console' is not defined  no-undef\n\n"
        "✖ 7 problems (6 errors, 1 warning)\n"
    )
    assert resolve("npx eslint src/", 1, out) == (
        "Échec, 6 erreurs et 1 avertissement. a.js ligne 1 : foo is defined but never used.")


def test_eslint_only_warnings_left_to_the_model():
    out = "\n/project/src/a.js\n  3:9  warning  Expected '===' and instead saw '=='  eqeqeq\n\n✖ 1 problem (0 errors, 1 warning)\n"
    assert resolve("npx eslint src/", 1, out) is None


def test_eslint_no_summary_line_left_to_the_model():
    assert resolve("npx eslint src/", 1, "some unrelated crash\n") is None


@pytest.mark.parametrize("cmd, code, path, expected", [
    ("sudo apt upgrade -y", 0, None, "12 paquets mis à jour."),
    ("sudo apt upgrade -y", 0, "apt_upgrade.en.txt", "12 paquets mis à jour."),
    ("sudo apt install nginx", 100, None, "Échec. Verrou dpkg tenu par unattended-upgr, processus 4321."),
    ("sudo apt install nginx", 100, "apt_lock.en.txt", "Échec. Verrou dpkg tenu par unattended-upgr, processus 4321."),
])
def test_apt(cmd, code, path, expected):
    out = (REAL / path).read_text() if path else fixture_case(cmd)[2]
    assert resolve(cmd, code, out) == expected


@pytest.mark.parametrize("out, code, expected", [
    ("0 upgraded, 0 newly installed, 0 to remove and 0 not upgraded.", 0, "Rien à faire, paquets déjà à jour."),
    ("1 upgraded, 3 newly installed, 1 to remove and 0 not upgraded.", 0, "1 paquet mis à jour, 3 installés, 1 enlevé."),
    ("E: Unable to locate package nginxx", 100, "Échec. Paquet nginxx introuvable."),
    ("E: Impossible de trouver le paquet nginxx", 100, "Échec. Paquet nginxx introuvable."),
    (("E: Could not open lock file /var/lib/dpkg/lock-frontend - open (13: Permission denied)\n"
      "E: Unable to acquire the dpkg frontend lock (/var/lib/dpkg/lock-frontend), are you root?"), 100,
     "Échec. Droits root requis."),
])
def test_apt_other_messages(out, code, expected):
    assert resolve("apt-get install nginxx", code, out) == expected


def test_apt_counts_not_claimed_on_failure():
    assert resolve("apt upgrade", 1, "12 upgraded, 0 newly installed, 0 to remove and 0 not upgraded.\nAbort.") is None


@pytest.mark.parametrize("cmd, code, out, expected", [
    ("pip install requests", 0, None, "requests 2.32.3 installé, avec 4 dépendances."),
    ("pip3 install requests", 0, ("Requirement already satisfied: requests in ./venv/lib/python3.12/site-packages (2.32.3)\n"
                                  "Requirement already satisfied: idna<4,>=2.5 in ./venv/lib/python3.12/site-packages (3.10)"),
     "requests déjà installé."),
    ("python3 -m pip install foo", 1, ("ERROR: Could not find a version that satisfies the requirement foo (from versions: none)\n"
                                       "ERROR: No matching distribution found for foo"), "Échec. Aucune version de foo trouvée."),
    ("pip install flask", 1, "error: externally-managed-environment\n\n× This environment is externally managed",
     "Échec. Environnement Python géré par le système, pip refusé."),
])
def test_pip(cmd, code, out, expected):
    assert resolve(cmd, code, out if out is not None else fixture_case(cmd)[2]) == expected


def test_pip_resolution_impossible():
    cmd, code, out = bench_case("vcs_packages", "pkg-pip-resolution-impossible")
    assert resolve(cmd, code, out) == "Échec. Conflit de dépendances entre flask 2.0.1 et werkzeug 3.0.1."


@pytest.mark.parametrize("path", [None, "git_status.en.txt"])
def test_git_status_untracked(path):
    cmd = "git -C /home/alice/Projects/steph status"
    out = (REAL / path).read_text() if path else fixture_case(cmd)[2]
    assert resolve(cmd, 0, out) == "Branche master, aucun commit, 7 fichiers non suivis."


@pytest.mark.parametrize("out, expected", [
    ("On branch main\nYour branch is up to date with 'origin/main'.\n\nnothing to commit, working tree clean\n",
     "Branche main, rien à valider."),
    (("Sur la branche main\nVotre branche est en avance sur 'origin/main' de 2 commits.\n"
      "  (utilisez \"git push\" pour publier vos commits locaux)\n\n"
      "Modifications qui seront validées :\n  (utilisez \"git restore --staged <fichier>...\" pour désindexer)\n"
      "\tmodifié :         a.py\n\n"
      "Modifications qui ne seront pas validées :\n  (utilisez \"git add <fichier>...\" pour mettre à jour ce qui sera validé)\n"
      "\tmodifié :         b.py\n\tmodifié :         c.py\n"),
     "Branche main, en avance de 2 commits, 1 fichier prêt à valider, 2 modifiés."),
])
def test_git_status_variants(out, expected):
    assert resolve("git status", 0, out) == expected


@pytest.mark.parametrize("path", [None, "git_push.txt"])
def test_git_push_rejected(path):
    out = (REAL / path).read_text() if path else fixture_case("git push")[2]
    assert resolve("git push", 1, out) == "Échec. Push de main refusé : le distant a des commits absents en local, faire git pull."


@pytest.mark.parametrize("lang", ["en", "fr"])
def test_git_merge_conflict(lang):
    cmd, code, out = bench_case("vcs_packages", "git-merge-conflict", lang)
    assert resolve(cmd, code, out) == "Échec. Conflit dans retry.py, gateway.py."


def test_git_push_up_to_date():
    assert resolve("git push", 0, "Everything up-to-date") == "Rien à pousser, déjà à jour."


@pytest.mark.parametrize("cmd, code, out, expected", [
    ("curl -qsS https://nonexistent.invalid/", 6, None, "Échec. Hôte nonexistent.invalid introuvable."),
    ("curl http://localhost:8080/", 7, "curl: (7) Failed to connect to localhost port 8080 after 0 ms: Connection refused",
     "Échec. Connexion refusée : localhost port 8080."),
    ("curl -f https://example.com/x", 22, "curl: (22) The requested URL returned error: 404", "Échec. Erreur HTTP 404."),
    ("curl -m 5 https://example.com/", 28, "curl: (28) Connection timed out after 5001 milliseconds",
     "Échec. Délai dépassé : example.com."),
    ("curl -I https://example.com/", 0, "HTTP/2 301\nlocation: https://www.example.com/\n\nHTTP/2 200\ncontent-type: text/html",
     "HTTP 200."),
    ("ssh -o BatchMode=yes -o ConnectTimeout=3 nobody@127.0.0.1 true", 255, None, "Échec. Clé d'hôte SSH non vérifiée."),
    ("ssh srv", 255, "ssh: Could not resolve hostname srv: Name or service not known", "Échec. Hôte srv introuvable."),
    ("ssh srv", 255, "ssh: connect to host srv port 22: Connection refused", "Échec. Connexion refusée : srv port 22."),
    ("ssh srv", 255, "root@srv: Permission denied (publickey,password).", "Échec. Accès SSH refusé."),
    ("ping -c 3 127.0.0.1", 0, None, "3 reçus sur 3, 0 % de perte, moyenne 0.024 ms."),
    ("ping x.invalid", 2, "ping: x.invalid: Name or service not known", "Échec. Hôte x.invalid introuvable."),
])
def test_network(cmd, code, out, expected):
    assert resolve(cmd, code, out if out is not None else fixture_case(cmd)[2]) == expected


def test_ping_english_and_unreachable():
    assert resolve("ping -c 3 127.0.0.1", 0, (REAL / "ping_local.en.txt").read_text()) == \
        "3 reçus sur 3, 0 % de perte, moyenne 0.024 ms."
    cmd, code, out = bench_case("system_state", "net-ping-unreachable")
    assert resolve(cmd, code, out) == "Échec. 0 reçu sur 4, 100 % de perte, hôte injoignable."


def test_curl_tls():
    cmd, code, out = bench_case("system_state", "net-curl-tls-expired")
    assert resolve(cmd, code, out) == "Échec. TLS, expired.example.com : certificat expiré."


@pytest.mark.parametrize("cmd, expected", [
    ("cat /nonexistent/file.txt", "Échec. file.txt : fichier introuvable."),
    ("rm /etc/hostname", "Échec. hostname : permission refusée."),
    ("tar czf /tmp/x.tgz /nonexistent", "Échec. nonexistent : fichier introuvable."),
])
def test_file_errors_never_invent_a_line(cmd, expected):
    said = resolve(*fixture_case(cmd))
    assert said == expected and "ligne" not in said


@pytest.mark.parametrize("cmd, expected", [
    ("free -h", "Mémoire : 24 Go disponibles sur 31 Go."),
    ("systemctl --user status pipewire --no-pager | head -20", "pipewire actif depuis 2 jours."),
    ("df -h", "racine : 685G libres sur 953G, 29 %. boot : 284M libres sur 974M, 69 %."),
    ("ip -br addr", "wlp0s20f3 192.168.1.20, tailscale0 100.64.0.10, tun0 10.9.0.2. Plus 8 réseaux virtuels."),
    ("ls -la /etc | head -40", "37 éléments affichés : abrt, adjtime, aliases."),
    ("docker ps", "9 conteneurs, 8 actifs ; shopapp_vault redémarre en boucle."),
    ("dnf check-update --cacheonly 2>&1 | tail -30",
     "19 éléments affichés : xen-licenses, xfsprogs, xorg-x11-drv-nvidia."),
])
def test_system_state_from_fixtures(cmd, expected):
    assert resolve(*fixture_case(cmd)) == expected


def test_docker_ps_restarting_container_flagged():
    """fx22 / TermSpeak ctr-docker-ps-restarting : un conteneur Restarting doit être signalé."""
    out = (REAL / "docker_ps.txt").read_text()
    assert resolve("docker ps", 0, out) == "9 conteneurs, 8 actifs ; shop_vault redémarre en boucle."


def test_free_takes_last_sample():
    cmd, code, out = bench_case("system_state", "mem-free-h")
    assert resolve(cmd, code, out) == "Mémoire : 398 Mo disponibles sur 15 Go."


@pytest.mark.parametrize("cmd, out", [
    ("journalctl -b | grep erreur", "\n".join(f"erreur {i}" for i in range(10))),
    ("grep -rn 'def ' src/", "a.py:1:def a\nb.py:2:def b\nc.py:3:def c"),
    ("lspci", "lspci: command not found"),
    ("uname -a", "Linux devbox 7.0.9 x86_64 GNU/Linux"),
    ("systemctl status nginx", "● nginx.service - nginx\n     Active: failed (Result: exit-code) since Mon; 2min ago"),
])
def test_left_to_the_model(cmd, out):
    assert resolve(cmd, 0, out) is None


def test_systemctl_status_not_counted_as_a_list():
    cmd, _, out = fixture_case("systemctl --user status pipewire --no-pager | head -20")
    assert not (digest(cmd, out) or "").startswith("18 éléments")


def test_narrator_says_the_resolved_sentence_without_llm():
    nar, llm = narrator_after("git push", fixture("git push"), code=1)
    assert llm.sent == []
    assert nar.sp.said[-1] == "Échec. Push de main refusé : le distant a des commits absents en local, faire git pull."


def test_narrator_verbatim_rule_wins_over_resolution():
    from test_rules import FakeSpeaker, run_cmd

    from steph.config import Config
    from steph.narrator import Narrator
    from steph.session import Session

    nar = Narrator(Config(rules={"git": "verbatim"}), Session(), FakeSpeaker(), RecordingLLM())
    nar.llm_ready = True
    said = run_cmd(nar, "git push", fixture("git push"), code=1)
    assert "Push de main refusé" not in said[-1]


def test_git_push_success():
    out = "To github.com:acme/app.git\n   1a2b3c4..5d6e7f8  main -> main\n"
    assert resolve("git push", 0, out) == "Push de main fait."


def test_narrator_long_failure_keeps_one_failure_word():
    from test_rules import FakeSpeaker, run_cmd

    from steph.config import Config
    from steph.narrator import Narrator
    from steph.session import Session

    nar = Narrator(Config(), Session(), FakeSpeaker(), RecordingLLM())
    nar.llm_ready = True
    said = run_cmd(nar, "git push", fixture("git push"), code=1, duration=30)
    assert said[-1] == ("Échec, code 1. Push de main refusé : le distant a des commits absents "
                         "en local, faire git pull. Après 30 secondes.")
    assert said[-1].count("Échec") == 1


@pytest.mark.parametrize("cmd, out", [
    ("cat report.txt", "Tests:       1 failed, 7 passed, 8 total"),
    ("grep -r passed logs/", "===== 3 failed, 2 passed in 1.0s ====="),
])
def test_file_viewers_are_not_mistaken_for_the_tool_they_show(cmd, out):
    assert resolve(cmd, 0, out) is None


def test_free_without_available_column_left_to_the_model():
    out = ("             total       used       free     shared    buffers     cached\n"
           "Mem:          7.8G       7.1G       700M        0B       200M       3.1G\n"
           "-/+ buffers/cache:       3.8G       4.0G\n")
    assert resolve("free -h", 0, out) is None


def test_systemctl_listing_still_counted():
    out = "\n".join(f"unit{i}.service loaded active running Service {i}" for i in range(5))
    assert digest("systemctl list-units --type=service | head", out).startswith("5 éléments")


# ---------------------------------------------------------------- go build / go test
def test_go_build_unused_imports():
    out = ('# example.com/app/cmd\n./cmd/main.go:6:2: "fmt" imported and not used\n'
           './cmd/main.go:7:2: "strings" imported and not used\n'
           '# example.com/app/internal/report\n./internal/report/report.go:4:2: "time" imported and not used')
    said = resolve("go build ./...", 1, out)
    assert said == "Échec, 3 erreurs. main.go ligne 6 : fmt imported and not used."


def test_go_test_first_failure_and_package():
    out = ("ok  \texample.com/app/internal/config\t0.004s\n--- FAIL: TestCalculateTotal (0.00s)\n"
           "    calc_test.go:22: expected 150, got 140\nFAIL\nFAIL\texample.com/app/internal/pricing\t0.011s\n"
           "ok  \texample.com/app/internal/storage\t0.006s")
    said = resolve("go test ./...", 1, out)
    assert said == "Échec. 1 test échoué. Paquet pricing, TestCalculateTotal, calc_test.go ligne 22 : expected 150, got 140."


def test_go_success_left_to_the_model():
    assert resolve("go build ./...", 0, "") is None
    # D6-A : un go test réussi est dit par paquet (tests/test_digest_d6_a.py)
    assert resolve("go test ./...", 0, "ok  \texample.invalid/app\t0.004s") == "1 paquet réussi : app."


# ---------------------------------------------------------------- make / cc : référence non définie (linker)
def test_make_linker_undefined_reference_no_source_line():
    out = ("cc -O2 -c src/utils.c -o src/utils.o\ncc -O2 -c src/main.c -o src/main.o\n"
           "cc -o app src/main.o src/utils.o\nsrc/main.o: In function `main':\n"
           "main.c:(.text+0x2a): undefined reference to `parse_config'\n"
           "collect2: error: ld returned 1 exit status\nmake: *** [Makefile:12: app] Error 1")
    assert resolve("make", 2, out) == "Échec. main.c : référence non définie à parse_config, Makefile ligne 12."


def test_make_linker_undefined_reference_with_source_line():
    out = ("cc -o dist/engine build/*/*.o -lpthread -lm\n"
           "build/net/socket_bridge.o: in function `net_connect':\n"
           "net/socket_bridge.c:88: undefined reference to `socket_configure'\n"
           "collect2: error: ld returned 1 exit status\nmake: *** [Makefile:42: dist/engine] Error 1")
    assert resolve("make", 2, out) == "Échec. socket_bridge.c ligne 88 : référence non définie à socket_configure."


# ---------------------------------------------------------------- lspci, câblé sur resolve()
def test_lspci_resolved_directly():
    out = ("00:02.0 VGA compatible controller: NVIDIA Corporation GA106 [GeForce RTX 3060] (rev a1)\n"
           "2a:00.0 Ethernet controller: Realtek Semiconductor RTL8111 PCI Express Gigabit Ethernet Controller\n")
    said = resolve("lspci", 0, out)
    assert said == "GPU : NVIDIA Corporation GA106 [GeForce RTX 3060], réseau : Realtek Semiconductor RTL8111 PCI Express Gigabit Ethernet Controller."


def test_lspci_single_device_still_resolved():
    assert resolve("lspci", 0, "00:02.0 VGA compatible controller: Intel Corporation UHD Graphics 620") == \
        "GPU : Intel Corporation UHD Graphics 620."


def test_lspci_unparsable_left_to_the_model():
    assert resolve("lspci", 0, "lspci: command not found") is None


# ---------------------------------------------------------------- git diff --stat, log --oneline, pull, clone
def test_git_diff_stat_fr_and_en():
    out_fr = (" a.py | 45 +++++++++\n b.py | 12 +--\n"
              " 4 fichiers modifiés, 77 insertions(+), 16 suppressions(-)")
    out_en = (" a.py | 45 +++++++++\n b.py | 12 +--\n"
              " 4 files changed, 77 insertions(+), 16 deletions(-)")
    expected = "4 fichiers modifiés, 77 insertions, 16 suppressions."
    assert resolve("git diff --stat", 0, out_fr) == expected
    assert resolve("git diff --stat", 0, out_en) == expected


def test_git_log_oneline_counts_and_keeps_latest_subject():
    out = "\n".join([
        "f3a9c21 fix: correct invoice rounding for partial refunds",
        "9d84b6e feat: add CSV export to reports page",
        "2b5f7a1 chore: bump lodash to 4.17.21",
    ])
    assert resolve("git log --oneline -3", 0, out) == \
        "3 commits, dernier : fix: correct invoice rounding for partial refunds."


def test_git_pull_fast_forward_fr_and_en():
    out_fr = ("Depuis github.com:example/webapp\n   a1b2c3d..f9e8d7c  main -> origin/main\n"
              "Mise à jour a1b2c3d..f9e8d7c\nAvance rapide\n"
              " a.py | 22 ++++++\n 3 fichiers modifiés, 31 insertions(+), 13 suppressions(-)")
    out_en = ("From github.com:example/webapp\n   a1b2c3d..f9e8d7c  main -> origin/main\n"
              "Updating a1b2c3d..f9e8d7c\nFast-forward\n"
              " a.py | 22 ++++++\n 3 files changed, 31 insertions(+), 13 deletions(-)")
    expected = "Tiré, avance rapide, 3 fichiers modifiés, 31 insertions, 13 suppressions."
    assert resolve("git pull", 0, out_fr) == expected
    assert resolve("git pull", 0, out_en) == expected


def test_git_clone_auth_failure_fr_and_en():
    out_fr = ("Clonage dans 'private-repo'...\nremote: Support for password authentication was removed.\n"
              "fatal : échec d'authentification pour 'https://github.com/example/private-repo.git/'")
    out_en = ("Cloning into 'private-repo'...\nremote: Support for password authentication was removed.\n"
              "fatal: Authentication failed for 'https://github.com/example/private-repo.git/'")
    expected = "Échec. Authentification refusée pour private-repo."
    assert resolve("git clone https://github.com/example/private-repo.git", 128, out_fr) == expected
    assert resolve("git clone https://github.com/example/private-repo.git", 128, out_en) == expected


# ---------------------------------------------------------------- docker : stats, system df, build, compose, images
def test_docker_stats_near_limit():
    out = ("CONTAINER ID   NAME     CPU %     MEM USAGE / LIMIT     MEM %\n"
           "a1b2c3d4e5f6   web      2.31%     498.2MiB / 512MiB     97.30%\n"
           "b7c8d9e0f1a2   worker   88.42%    511.8MiB / 512MiB     99.96%\n"
           "c3d4e5f6a7b8   redis    0.15%     42.1MiB / 256MiB      16.45%\n")
    assert resolve("docker stats --no-stream", 0, out) == "Conteneur worker proche de la limite, 99,96 % de 512MiB."


def test_docker_stats_below_threshold_left_to_the_model():
    out = ("CONTAINER ID   NAME   CPU %     MEM USAGE / LIMIT     MEM %\n"
           "a1b2c3d4e5f6   web    2.31%     100.0MiB / 512MiB     19.50%\n")
    assert resolve("docker stats --no-stream", 0, out) is None


def test_docker_system_df():
    out = ("TYPE            TOTAL     ACTIVE    SIZE      RECLAIMABLE\n"
           "Images          14        6         3.8GB     2.1GB (55%)\n"
           "Containers      6         2         412MB     380MB (92%)\n"
           "Local Volumes   9         3         1.7GB     1.2GB (70%)\n"
           "Build Cache     52        0         890MB     890MB (100%)")
    said = resolve("docker system df", 0, out)
    assert said == "images 3,8GB, 2,1GB récupérables, cache de build 890MB, entièrement récupérable."
    assert "70" not in said.split("images")[0]


def test_docker_build_failure_reports_dockerfile_line_and_step():
    out = ("#6 [2/8] WORKDIR /app\n#6 CACHED\n#8 [4/8] RUN npm ci\n#8 CACHED\n"
           "#10 [6/8] RUN npm run test\n#10 7.8 Tests:       1 failed, 42 passed, 43 total\n"
           '#10 ERROR: process "/bin/sh -c npm run test" did not complete successfully: exit code 1\n'
           "Dockerfile:14\n--------------------\n  14 | >>> RUN npm run test\n--------------------\n"
           'ERROR: failed to solve: process "/bin/sh -c npm run test" did not complete successfully: exit code 1')
    said = resolve("docker build -t webapp:latest .", 1, out)
    assert said == "Échec. Dockerfile ligne 14, étape 6 sur 8, npm run test, code de sortie 1."


def test_docker_build_success_names_the_image():
    out = ("#9 [6/6] RUN npm run build\n#9 DONE 8.9s\n#10 exporting to image\n"
           "#10 writing image sha256:3f2a91c8b7d4 done\n"
           "#10 naming to registry.example.com/webapp:latest done\n#10 DONE 0.5s")
    assert resolve("docker build -t registry.example.com/webapp:latest .", 0, out) == \
        "Terminé. Image webapp:latest construite et taguée."


def test_docker_compose_unhealthy_dependency():
    out = ("[+] Running 4/5\n ✔ Container app-db-1          Healthy\n"
           " ⚿ Container app-api-1         Waiting\n"
           "dependency failed to start: container app-api-1 is unhealthy")
    assert resolve("docker compose up -d", 1, out) == "Échec. app-api-1 malsain, dépendance non démarrée."


def test_docker_images_first_and_others():
    out = ("REPOSITORY   TAG       IMAGE ID       CREATED         SIZE\n"
           "webapp       latest    3f2a91c8b7d4   2 hours ago     412MB\n"
           "webapp       v1.3.0    9d1b7e2f5a6c   3 days ago      408MB\n"
           "postgres     15        6c8a2f9d1e3b   2 weeks ago     379MB\n"
           "redis        7-alpine  1a4f7c9b2d6e   3 weeks ago     41.2MB\n")
    assert resolve("docker images", 0, out) == "webapp latest, 412MB ; aussi postgres, redis."


# ---------------------------------------------------------------- traces Node.js (docker logs, etc.)
def test_node_stack_trace_resolved_even_when_the_command_itself_succeeds():
    out = ("> node server.js\nServer listening on port 3000\n"
           "/app/server.js:88\n    throw new Error(`Missing env var: ${key}`);\n    ^\n\n"
           "Error: Missing env var: PAYMENT_SECRET_KEY\n"
           "    at loadConfig (/app/server.js:88:11)\n"
           "    at Object.<anonymous> (/app/server.js:12:1)\nNode.js v20.11.0")
    assert resolve("docker logs webapp-api-1", 0, out) == "Erreur. server.js ligne 88 : Missing env var: PAYMENT_SECRET_KEY."


# ---------------------------------------------------------------- ps aux --sort
def test_ps_sorted_by_cpu_reports_the_top_process():
    out = ("USER     PID  %CPU %MEM    VSZ   RSS TTY      STAT START   TIME COMMAND\n"
           "user   18422  87.3  4.2  812340 172304 ?      Rl   09:14  12:47 /usr/bin/backup-agent --full\n"
           "redis   3253  14.5  0.1  250356 140886 ?      S    14:52   1:58 sshd: user@pts/0\n")
    assert resolve("ps aux --sort=-%cpu", 0, out) == "backup-agent au plus haut, 87,3 % CPU, PID 18422."


def test_ps_sorted_by_mem_reports_the_top_process():
    out = ("USER     PID %CPU %MEM    VSZ   RSS TTY      STAT START   TIME COMMAND\n"
           "mysql   2142 18.3 54.9 3184532 892456 ?      Sl   Sep25 142:03 /usr/sbin/mysqld\n"
           "app     3301  3.9 19.1 1245680 312048 ?      Sl   09:40  88:44 java -jar app.jar\n")
    assert resolve("ps aux --sort=-%mem | head -15", 0, out) == "mysqld au plus haut, 54,9 % RAM, PID 2142."


def test_ps_without_sort_flag_left_to_the_model():
    out = ("USER     PID %CPU %MEM    VSZ   RSS TTY      STAT START   TIME COMMAND\n"
           "root       1  0.0  0.1   1234   567 ?      Ss   Sep25   0:01 /sbin/init\n")
    assert resolve("ps aux", 0, out) is None


# ---------------------------------------------------------------- sections (sorties longues à blocs)
def _multi_file_warnings(n: int) -> str:
    blocks = []
    for i in range(n):
        blocks.append(f"/project/src/mod{i}.js\n  {i + 1}:1  warning  'x{i}' is assigned a value but never used  no-unused-vars\n")
    return "\n" + "\n".join(blocks) + f"\n✖ {n} problems (0 errors, {n} warnings)\n"


def test_digest_groups_long_multi_file_output_into_sections():
    out = _multi_file_warnings(6)
    result = digest("npx eslint src/", out, 1500)
    assert result is not None
    first_line = result.splitlines()[0]
    assert first_line.startswith("6 sections : mod0.js, mod1.js, mod2.js")


def test_digest_does_not_section_short_output():
    out = _multi_file_warnings(2)
    assert digest("npx eslint src/", out, 1500) is None


# ---------------------------------------------------------------- L1 : exactitude des phrases en code

from steph.digest import grep_no_match, not_found_sentence

_APT_SIM_INSTALL = (
    "Reading package lists...\nBuilding dependency tree...\nReading state information...\n"
    "The following NEW packages will be installed:\n  libfoo1 libbar2 qemu-system-x86\n"
    "0 upgraded, 3 newly installed, 0 to remove and 4 not upgraded.\n"
    "Inst libfoo1 (1.0-1 Debian:13/stable [amd64])\n"
    "Inst libbar2 (2.1-3 Debian:13/stable [amd64])\n"
    "Inst qemu-system-x86 (1:10.0 Debian:13/stable [amd64])\n"
    "Conf libfoo1 (1.0-1 Debian:13/stable [amd64])\n"
    "Conf libbar2 (2.1-3 Debian:13/stable [amd64])\n"
    "Conf qemu-system-x86 (1:10.0 Debian:13/stable [amd64])\n"
)
_APT_SIM_REMOVE = (
    "Les paquets suivants seront ENLEVÉS :\n  gdm3 gnome gnome-shell\n"
    "0 mis à jour, 0 nouvellement installés, 3 à enlever et 87 non mis à jour.\n"
    "Remv gnome [1:48+2]\nRemv gdm3 [48.0-2]\nRemv gnome-shell [48.7-0]\n"
)


@pytest.mark.parametrize("cmd, lang, expected", [
    ("apt-get -s install qemu-system-x86", "fr",
     "Simulation seulement : qemu-system-x86 serait installé avec ses dépendances."),
    ("sudo apt-get --simulate install qemu-system-x86", "en",
     "Simulation only: qemu-system-x86 would be installed with its dependencies."),
    ("apt install --dry-run qemu-system-x86 libfoo1", "fr",
     "Simulation seulement : qemu-system-x86 et libfoo1 seraient installés avec leurs dépendances."),
    ("apt-get -s install libfoo1 libbar2 qemu-system-x86", "fr",
     "Simulation seulement : libfoo1, libbar2 et qemu-system-x86 seraient installés."),
])
def test_apt_simulation_install_never_says_installed(cmd, lang, expected):
    assert resolve(cmd, 0, _APT_SIM_INSTALL, lang) == expected


def test_apt_simulation_remove_counts_from_remv_lines():
    assert resolve("apt-get -s remove gnome-shell", 0, _APT_SIM_REMOVE) == \
        "Simulation seulement : 3 paquets seraient enlevés, dont gnome-shell."
    assert resolve("apt-get -s remove gnome-shell", 0, _APT_SIM_REMOVE, "en") == \
        "Simulation only: 3 packages would be removed, including gnome-shell."


def test_apt_simulation_without_named_package_uses_counts():
    out = "3 upgraded, 1 newly installed, 0 to remove and 0 not upgraded.\nInst a [1] (2 x)\nInst b [1] (2 x)\n"
    assert resolve("apt-get -s upgrade", 0, out) == "Simulation seulement : 3 paquets seraient mis à jour, 1 installé."
    assert resolve("apt-get -s upgrade", 0, out, "en") == "Simulation only: 3 packages would be upgraded, 1 installed."


def test_apt_simulation_already_installed_package_is_not_named():
    out = "qemu-system-x86 is already the newest version.\n0 upgraded, 0 newly installed, 0 to remove and 0 not upgraded.\n"
    assert resolve("apt-get -s install qemu-system-x86", 0, out) == "Rien à faire, paquets déjà à jour."


def test_apt_simulation_mentions_removals_during_install():
    out = _APT_SIM_INSTALL.replace("0 to remove", "1 to remove") + "Remv oldpkg [1.0]\n"
    assert resolve("apt-get -s install qemu-system-x86", 0, out) == (
        "Simulation seulement : qemu-system-x86 serait installé avec ses dépendances, 1 paquet serait enlevé.")


def test_apt_simulation_unreadable_output_is_left_to_the_model():
    assert resolve("apt-get -s install foo", 0, "Inst foo (1.0 x)\n") is None


def test_apt_real_install_still_counted():
    out = "0 upgraded, 3 newly installed, 0 to remove and 0 not upgraded.\nSetting up foo (1.0) ...\n"
    assert resolve("sudo apt-get install -y foo", 0, out) == "3 paquets installés."


@pytest.mark.parametrize("fw, out, lang, expected", [
    ("bash", "==> Building\n==> Syncing\ndeploy.sh: ligne 7: rsyncx : commande introuvable", "fr",
     "Commande introuvable : rsyncx, deploy.sh ligne 7."),
    ("bash", "deploy.sh: line 7: rsyncx: command not found", "en",
     "Command not found: rsyncx, deploy.sh line 7."),
    ("deploy.sh", "./deploy.sh: 12: rsyncx: not found", "fr", "Commande introuvable : rsyncx, deploy.sh ligne 12."),
    ("zsh", "build.zsh:3: command not found: cmakex", "fr", "Commande introuvable : cmakex, build.zsh ligne 3."),
    ("ncdu", "bash: line 1: ncdu: command not found", "fr", "Commande introuvable : ncdu."),
    ("snap", "sh: 1: snap: not found", "en", "Command not found: snap."),
    ("pip", "bash: ligne 1: pip : commande introuvable", "fr", "Commande introuvable : pip."),
    ("nope", "zsh: command not found: nope", "fr", "Commande introuvable : nope."),
    ("nope", "", "fr", "Commande introuvable : nope."),
])
def test_not_found_names_the_missing_program(fw, out, lang, expected):
    assert not_found_sentence(fw, out, lang) == expected


@pytest.mark.parametrize("cmd, code, lang, expected", [
    ("grep -rn DATABASE_URL config", 1, "fr", "Aucune correspondance pour DATABASE_URL."),
    ("grep -rn DATABASE_URL config", 1, "en", "No match for DATABASE_URL."),
    ("rg -i 'todo list' src", 1, "fr", "Aucune correspondance pour todo list."),
    ("grep -A 3 -e foo -e bar file.txt", 1, "fr", "Aucune correspondance pour foo ou bar."),
    ("grep -A3 --include=*.py -rq needle .", 1, "en", "No match for needle."),
    ("cat app.log | grep ERROR", 1, "fr", "Aucune correspondance pour ERROR."),
    ("grep -m 2 -- -v notes.txt", 1, "fr", "Aucune correspondance pour -v."),
])
def test_grep_exit_one_without_output_says_no_match(cmd, code, lang, expected):
    assert grep_no_match(cmd, code, lang) == expected


@pytest.mark.parametrize("cmd, code", [
    ("grep -rn DATABASE_URL config", 2),       # erreur, pas une absence
    ("grep -rn DATABASE_URL config", 0),
    ("grep -v foo file", 1),                    # -v : aucune ligne sans le motif
    ("grep -L foo *.txt", 1),
    ("grep -f patterns.txt file", 1),           # motif dans un fichier : inconnu ici
    ("grep foo file && echo ok", 1),            # le code peut venir d'une autre commande
    ("grep foo file | wc -l", 1),
    ("rg --files", 1),
    ("git grep foo", 1),
    ("grep", 1),
])
def test_grep_no_match_stays_silent_when_unsure(cmd, code):
    assert grep_no_match(cmd, code, "fr") is None


_CHAINED = (
    "INFO batch 70\n"
    "Traceback (most recent call last):\n"
    '  File "/home/user/job/job.py", line 14, in main\n    run()\n'
    '  File "/home/user/job/job.py", line 8, in step\n    raise KeyError(\'region\')\n'
    "KeyError: 'region'\n\n"
    "The above exception was the direct cause of the following exception:\n\n"
    "Traceback (most recent call last):\n"
    '  File "/home/user/job/job.py", line 17, in <module>\n    main()\n'
    '  File "/home/user/job/job.py", line 16, in main\n    raise RuntimeError("route job aborted") from e\n'
    "RuntimeError: route job aborted\n"
)


def test_chained_traceback_gives_root_cause_then_final():
    assert resolve("python3 job.py", 1, _CHAINED) == \
        "Échec. job.py ligne 8 : KeyError region, puis RuntimeError route job aborted."
    assert resolve("python3 job.py", 1, _CHAINED, "en") == \
        "Failed. job.py line 8: KeyError region, then RuntimeError route job aborted."


def test_traceback_during_handling_also_chains():
    out = _CHAINED.replace("The above exception was the direct cause of the following exception:",
                           "During handling of the above exception, another exception occurred:")
    assert resolve("python3 job.py", 1, out).startswith("Échec. job.py ligne 8 : KeyError region, puis ")


def test_chained_traceback_too_long_keeps_final_only():
    out = _CHAINED.replace("KeyError: 'region'",
                           "ValueError: invalid literal for int() with base 10: 'three' in column qty of the stock file")
    assert resolve("python3 job.py", 1, out) == "Échec. job.py ligne 16 : RuntimeError route job aborted."


_PYTEST_COLLECT = (
    "collected 1 item / 1 error\n\n"
    "==================================== ERRORS ====================================\n"
    "____________________ ERROR collecting tests/test_config.py _____________________\n"
    "ImportError while importing test module '/home/user/src/tests/test_config.py'.\n"
    "Traceback:\n"
    "tests/test_config.py:1: in <module>\n    from feedsync.config import load\n"
    "feedsync/config.py:1: in <module>\n    import yaml\n"
    "E   ModuleNotFoundError: No module named 'yaml'\n"
    "=========================== short test summary info ============================\n"
    "ERROR tests/test_config.py\n"
    "!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!\n"
    "=============================== 1 error in 0.16s ===============================\n"
)


def test_pytest_collection_error_names_file_and_cause():
    assert resolve("pytest", 2, _PYTEST_COLLECT) == \
        "Échec. 1 erreur. Erreur de collecte : test_config.py, ModuleNotFoundError: No module named yaml."
    assert resolve("pytest", 2, _PYTEST_COLLECT, "en") == \
        "Failed. 1 error. Collection error: test_config.py, ModuleNotFoundError: No module named yaml."
    assert "Premier : ," not in resolve("pytest", 2, _PYTEST_COLLECT)


def test_apt_simulation_remove_single_package_is_named():
    out = "0 upgraded, 0 newly installed, 1 to remove and 0 not upgraded.\nRemv foo [1.0]\n"
    assert resolve("apt-get -s remove foo", 0, out) == "Simulation seulement : foo serait enlevé."


# ---------------------------------------------------------------- autotools : ./configure et make réussi (L2)
# Sorties écrites d'après les messages standard d'autoconf et de GNU make ; famille repérée sur
# les cas dev v3-build-native-0056, 0061, 0070, 0073, 0091 (le modèle recopie « checking gawk »).

def _configure_ok(tail: str = "") -> str:
    return ("checking for a BSD-compatible install... /usr/bin/install -c\n"
            "checking for gcc... gcc\nchecking whether the C compiler works... yes\n"
            "configure: creating ./config.status\n"
            "config.status: creating Makefile\nconfig.status: creating src/Makefile\n"
            "config.status: creating config.h\nconfig.status: executing depfiles commands" + tail)


def test_configure_success_names_generated_files_fr_and_en():
    assert resolve("./configure", 0, _configure_ok()) == "Configuration réussie, Makefile et config.h générés."
    assert resolve("./configure --prefix=/usr", 0, _configure_ok(), "en") == \
        "Configure succeeded, Makefile and config.h generated."


def test_configure_success_without_config_h():
    out = _configure_ok().replace("config.status: creating config.h\n", "")
    assert resolve("../configure", 0, out) == "Configuration réussie, Makefile généré."


@pytest.mark.parametrize("tail", [
    "\n\nOption     Change with configure's option   Current value\n"
    "Media      --with-media=MEDIA               A4",
    "\n\n  Default installation directories:\n    program:   /usr/local/bin/",
])
def test_configure_closing_table_left_to_the_model(tail):
    assert resolve("./configure", 0, _configure_ok(tail)) is None


def test_configure_warning_left_to_the_model():
    out = _configure_ok().replace("configure: creating", "configure: WARNING: libpsl was not found\nconfigure: creating")
    assert resolve("./configure", 0, out) is None


def test_configure_compound_or_unknown_argument_left_to_the_model():
    assert resolve("./configure && make", 0, _configure_ok()) is None
    assert resolve("./configure", 0, "config.status: creating src/Makefile\nconfig.status: creating config.h") is None


def test_configure_failure_says_last_error_first_sentence():
    out = ("checking for pkg-config... no\n"
           "configure: error: in '/home/user/src/wget-1.25.0':\n"
           "configure: error: The pkg-config script could not be found or is too old.  Make sure it\n"
           "is in your PATH or set the PKG_CONFIG environment variable to the full\n"
           "path to pkg-config.\nSee 'config.log' for more details")
    assert resolve("./configure", 1, out) == \
        "Échec. configure : The pkg-config script could not be found or is too old."
    assert resolve("./configure", 1, out, "en") == \
        "Failed. configure: The pkg-config script could not be found or is too old."


def test_configure_failure_inline_error_drops_log_hint_and_dollar():
    out = ("checking for vsnprintf... yes\n"
           "checking for suitable m4... configure: error: No usable m4 in $PATH or /usr/5bin "
           "(see config.log for reasons).")
    assert resolve("./configure", 1, out) == "Échec. configure : No usable m4 in PATH or /usr/5bin."


def test_configure_failure_without_sentence_end():
    out = "checking whether the C compiler works... no\nconfigure: error: C compiler cannot create executables\n" \
          "See 'config.log' for more details"
    assert resolve("./configure", 77, out, "en") == "Failed. configure: C compiler cannot create executables."


@pytest.mark.parametrize("out", [
    # message vide, détail sur des lignes « *** »
    "checking for curses.h... no\nconfigure: error: \n  *** No curses lib was found.  Please install it",
    # message coupé en fin de ligne, sans fin de phrase
    "configure: error: cannot find install-sh, install.sh, or shtool in\n\".\" \"./..\" \"./../..\"",
])
def test_configure_failure_unreadable_message_left_to_the_model(out):
    assert resolve("./configure", 1, out) is None


def _make_ok(dirs, body: str = "", enter: str = "Entering directory", leave: str = "Leaving directory",
             quotes: str = "''") -> str:
    lines = []
    for depth, d in dirs:
        lines.append(f"make[{depth}]: {enter} {quotes[0]}{d}{quotes[1]}")
    lines.append(body or "  CC       grep.o\n  CCLD     grep")
    for depth, d in reversed(dirs):
        lines.append(f"make[{depth}]: {leave} {quotes[0]}{d}{quotes[1]}")
    return "\n".join(lines)


GREP_DIRS = [(1, "/home/user/src/grep-3.11"), (2, "/home/user/src/grep-3.11/lib"), (2, "/home/user/src/grep-3.11/src")]


def test_make_success_names_project_and_version_fr_and_en():
    out = _make_ok(GREP_DIRS)
    assert resolve("make -j8", 0, out) == "Compilation de grep 3.11 terminée, aucune erreur ni avertissement."
    assert resolve("make -j8", 0, out, "en") == "grep 3.11 build completed, no errors or warnings."


def test_make_success_french_messages_and_elision():
    dirs = [(1, "/home/user/src/enscript-1.6.6"), (2, "/home/user/src/enscript-1.6.6/src")]
    out = _make_ok(dirs, enter="on entre dans le répertoire", leave="on quitte le répertoire", quotes="«»")
    out = out.replace("make[1]:", "make[1] :").replace("make[2]:", "make[2] :").replace("«", "« ").replace("»", " »")
    assert resolve("make", 0, out) == "Compilation d'enscript 1.6.6 terminée, aucune erreur ni avertissement."


def test_make_success_warnings_name_the_first_file_never_a_count():
    one = "utimens.c:383:17: warning: 'update_timespec' accessing 16 bytes [-Wstringop-overflow=]"
    two = one + "\n" + one.replace("383", "596")
    other = two + "\nstat.c:12:5: warning: unused variable 'x' [-Wunused-variable]"
    assert resolve("make", 0, _make_ok(GREP_DIRS, one)) == "Compilation de grep 3.11 terminée, avertissement dans utimens.c."
    assert resolve("make", 0, _make_ok(GREP_DIRS, two)) == "Compilation de grep 3.11 terminée, avertissements dans utimens.c."
    assert resolve("make", 0, _make_ok(GREP_DIRS, other), "en") == \
        "grep 3.11 build completed, warnings, the first in utimens.c."


def test_make_install_success():
    out = _make_ok([(1, "/home/user/src/make-4.4.1")], " /usr/bin/install -c make '/stage/usr/local/bin'")
    assert resolve("make install DESTDIR=/stage", 0, out) == \
        "Installation de make 4.4.1 terminée, aucune erreur ni avertissement."


def test_make_success_without_versioned_directory_is_anonymous():
    out = _make_ok([(1, "/home/user/proj/build"), (2, "/home/user/proj/build/src")])
    assert resolve("make", 0, out, "en") == "Build completed, no errors or warnings."
    unrelated = _make_ok([(1, "/home/user/a/foo-1.0"), (1, "/home/user/b/bar-2.0")])
    assert resolve("make", 0, unrelated) == "Compilation terminée, aucune erreur ni avertissement."


@pytest.mark.parametrize("cmd, out", [
    # la dernière ligne porte déjà le bilan de l'outil
    ("make", "gcc -c src/main.c -o build/main.o\ngcc -o kvstored build/main.o\nbuilt kvstored (69 objects)"),
    ("make", _make_ok(GREP_DIRS) + "\nbuilt grep (12 objects)"),
    # cibles qui ne compilent pas ou ne compilent pas seulement
    ("make test", _make_ok(GREP_DIRS)),
    ("make check", _make_ok(GREP_DIRS)),
    ("make -n", _make_ok(GREP_DIRS)),
    ("make -C lib", _make_ok(GREP_DIRS)),
    ("make clean && make", _make_ok(GREP_DIRS)),
    # avertissement ou erreur hors du format compilateur
    ("make", _make_ok(GREP_DIRS, "libtool: warning: remember to run 'libtool --finish /usr/lib'")),
    ("make", _make_ok(GREP_DIRS, "ar: `u' modifier ignored since `D' is the default (see `U')")),
    ("make", _make_ok(GREP_DIRS, "make[2]: [Makefile:12: doc] Error 1 (ignored)")),
    ("make", _make_ok(GREP_DIRS, "main.c:3:1: error: expected ';' before '}' token")),
])
def test_make_success_left_to_the_model(cmd, out):
    assert resolve(cmd, 0, out) is None


def test_make_flags_are_not_mistaken_for_warnings():
    body = "gcc -Wall -Wno-deprecated-declarations -Werror=format-security -c strerror.c -o strerror.o"
    assert resolve("make", 0, _make_ok(GREP_DIRS, body)) == \
        "Compilation de grep 3.11 terminée, aucune erreur ni avertissement."


def test_make_success_project_from_the_common_parent_of_subdirectories():
    # ncurses enchaîne « cd man && make » : aucun make n'entre dans le dossier racine
    out = _make_ok([(1, "/home/user/src/ncurses-6.5/man"), (1, "/home/user/src/ncurses-6.5/c++")])
    assert resolve("make", 0, out) == "Compilation de ncurses 6.5 terminée, aucune erreur ni avertissement."


def test_make_success_mixed_absolute_and_relative_directories_do_not_crash():
    out = _make_ok([(1, "/home/user/src/grep-3.11"), (2, "grep-3.11/lib")])
    assert resolve("make", 0, out) == "Compilation terminée, aucune erreur ni avertissement."


def test_make_success_compiler_note_belongs_to_its_warning():
    # clang, GNU hello 2.12.1 sur macOS : la note qui suit l'avertissement contient « deprecated »
    body = ("lib/strerror.c:59:7: warning: 'sprintf' is deprecated [-Wdeprecated-declarations]\n"
            "/usr/include/_stdio.h:278:1: note: 'sprintf' has been explicitly marked deprecated here\n"
            "1 warning generated.")
    assert resolve("make", 0, _make_ok(GREP_DIRS, body), "en") == "grep 3.11 build completed, warning in strerror.c."


@pytest.mark.parametrize("body", [
    # GNU make 3.81 sur un arbre déjà à jour (GNU hello 2.12.1, macOS) : rien n'a été compilé
    "/usr/bin/make  all-recursive\nMaking all in po\nmake[2]: Nothing to be done for `all'.",
    "make[2] : Rien à faire pour « all ».",
    "make[1]: 'grep' is up to date.",
])
def test_make_with_nothing_built_left_to_the_model(body):
    assert resolve("make", 0, _make_ok(GREP_DIRS, body)) is None


def test_make_print_directory_flag_accepted():
    assert resolve("make -w -j4", 0, _make_ok(GREP_DIRS), "en") == "grep 3.11 build completed, no errors or warnings."


def test_configure_failure_cut_inside_parentheses_drops_the_open_parenthesis():
    out = "configure: error: libfoo is required (e.g. from the libfoo-dev package)\nSee 'config.log' for more details"
    assert resolve("./configure", 1, out, "en") == "Failed. configure: libfoo is required."


# ---------------------------------------------------------------- Z15 : un compte juste par listing
DNF_CMD = "dnf check-update --cacheonly 2>&1 | tail -30"


@pytest.mark.parametrize("lang, expected", [
    ("fr", "19 éléments affichés : xen-licenses, xfsprogs, xorg-x11-drv-nvidia."),
    ("en", "19 items shown: xen-licenses, xfsprogs, xorg-x11-drv-nvidia."),
])
def test_dnf_count_skips_headers_obsoleted_rows_and_repeated_packages(lang, expected):
    """Faux si « Obsoleting packages » ou une ligne indentée compte comme paquet, ou si un paquet de deux dépôts compte deux fois."""
    cmd, code, out = fixture_case(DNF_CMD)
    assert resolve(cmd, code, out, lang) == expected


def test_ls_total_line_and_dot_entries_are_not_counted():
    """Faux si « total N » ou « . » et « .. » comptent comme éléments."""
    out = "total 12\ndrwxr-xr-x 2 u u 4096 Jan 1 10:00 .\ndrwxr-xr-x 9 u u 4096 Jan 1 10:00 ..\n" + "".join(
        f"-rw-r--r-- 1 u u 10 Jan 1 10:00 f{i}\n" for i in range(5))
    assert resolve("ls -la | head -20", 0, out, "fr") == "5 éléments affichés : f0, f1, f2."
    assert resolve("ls -la | head -20", 0, out, "en") == "5 items shown: f0, f1, f2."


@pytest.mark.parametrize("cmd, expected", [
    ("ls -la /etc | head -40", "37 éléments affichés : abrt, adjtime, aliases."),
    ("find /usr/share/doc -maxdepth 1 -name 'py*' | head -20",
     "20 éléments affichés : python-systemd, python3-argcomplete, python3-attrs."),
    ("sort /etc/passwd | cut -d: -f1 | head -30", "30 éléments affichés : abrt, adm, akmods."),
])
def test_truncated_listing_phrase_is_single_and_not_doubled(cmd, expected):
    """Faux si la phrase répète un second compte, un nom de la liste ou un en-tête."""
    said = resolve(*fixture_case(cmd))
    assert said == expected and said.count("éléments") == 1
