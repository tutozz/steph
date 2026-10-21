"""Réglage de langue (F1a) : config, prompts, messages parlés (narrator), digest/resolve.

Non-régression : tout appel sans `language` (ou avec `language="fr"`) doit rendre
exactement les mêmes octets qu'avant l'ajout de la langue anglaise.
"""

from __future__ import annotations

import time

from steph.config import Config
from steph.digest import digest, resolve
from steph.narrator import Narrator, fmt_duration
from steph.session import Command, Session
from steph.strings import n, t

# ---------------------------------------------------------------- config

def test_language_defaults_to_french():
    assert Config().language == "fr"


def test_language_can_be_set_to_english():
    assert Config(language="en").language == "en"


def test_language_env_override(monkeypatch):
    monkeypatch.setenv("STEPH_LANGUAGE", "en")
    from steph.config import load_config
    assert load_config().language == "en"


# ---------------------------------------------------------------- prompts

def test_summary_messages_default_is_french_byte_identical():
    from steph.prompts import SUMMARY_SYSTEM, summary_messages
    msgs = summary_messages("ls", 0, 1.0, "a\nb", 2)
    assert msgs[0]["content"] == SUMMARY_SYSTEM
    assert msgs[1]["content"].startswith("Commande : ls\nStatut : succès (code 0)\n")


def test_summary_messages_english():
    from steph.prompts import SUMMARY_SYSTEM_EN, summary_messages
    msgs = summary_messages("ls", 0, 1.0, "a\nb", 2, language="en")
    assert msgs[0]["content"] == SUMMARY_SYSTEM_EN
    assert msgs[1]["content"].startswith("Command: ls\nStatus: success (code 0)\n")
    assert "Output:" in msgs[1]["content"]


def test_details_messages_english_is_distinct_and_english():
    from steph.prompts import details_messages, summary_messages
    d = details_messages("ls", 0, 1.0, "a", 1, language="en")
    s = summary_messages("ls", 0, 1.0, "a", 1, language="en")
    assert d[0]["content"] != s[0]["content"]
    assert "60 words" in d[0]["content"]


def test_progress_messages_english():
    from steph.prompts import progress_messages
    msgs = progress_messages("make", 5.0, "compiling foo.c", language="en")
    assert "Command: make" in msgs[1]["content"]
    assert "Running for 5 s" in msgs[1]["content"]
    assert "Last lines:" in msgs[1]["content"]


def test_progress_messages_default_french_byte_identical():
    from steph.prompts import PROGRESS_SYSTEM, progress_messages
    msgs = progress_messages("make", 5.0, "compilation")
    assert msgs[0]["content"] == PROGRESS_SYSTEM
    assert msgs[1]["content"] == "Commande : make\nEn cours depuis 5 s\nDernières lignes :\ncompilation"


def test_start_messages_english():
    from steph.prompts import START_SYSTEM_EN, start_messages
    msgs = start_messages("apt install nginx", language="en")
    assert msgs[0]["content"] == START_SYSTEM_EN
    assert msgs[1]["content"] == "apt install nginx"


def test_qa_system_english_exists_and_differs():
    from steph.prompts import QA_SYSTEM, QA_SYSTEM_EN
    assert QA_SYSTEM_EN != QA_SYSTEM
    assert "English" in QA_SYSTEM_EN


# ---------------------------------------------------------------- narrator : fmt_duration

def test_fmt_duration_french_default():
    assert fmt_duration(90) == "1 minute 30"


def test_fmt_duration_english():
    assert fmt_duration(90, language="en") == "1 minute 30"
    assert fmt_duration(1, language="en") == "1 second"
    assert fmt_duration(5, language="en") == "5 seconds"


def test_fmt_duration_french_singular_plural():
    assert fmt_duration(1) == "1 seconde"
    assert fmt_duration(5) == "5 secondes"


# ---------------------------------------------------------------- narrator : messages parlés

class FakeSpeaker:
    def __init__(self):
        self.said = []

        class Ev:
            def is_set(self_):
                return False

        class Q:
            def empty(self_):
                return True

        self.speaking = Ev()
        self._q = Q()

    def stop(self):
        pass

    def repeat(self):
        pass

    def say(self, text, interrupt=True, on_done=None):
        text = text.strip()
        if not text:
            return
        self.said.append(text)
        if on_done:
            on_done(text)

    def say_stream(self, pieces, interrupt=True, on_done=None):
        text = "".join(pieces).strip()
        if text:
            self.said.append(text)
        if on_done:
            on_done(text)


class DummyLLM:
    active = False
    last_done = 0.0

    def healthy(self):
        return True

    def stream(self, msgs, **kw):
        raise AssertionError("le LLM ne doit pas être appelé pour ce cas")

    def complete(self, msgs, **kw):
        raise AssertionError("le LLM ne doit pas être appelé pour ce cas")


def make_narrator(language: str = "fr", **cfg_kwargs) -> tuple[Narrator, FakeSpeaker]:
    sp = FakeSpeaker()
    nar = Narrator(Config(language=language, **cfg_kwargs), Session(), sp, DummyLLM())
    nar.llm_ready = True
    return nar, sp


def finish(nar, cmd, output, code=0, old_cwd="/home/x", cwd="/home/x"):
    c = Command(id=1, cmd=cmd, cwd=cwd)
    if output:
        c.feed(output.encode())
    c.exit = code
    c.end = c.start
    nar._finish(c, old_cwd, cwd)
    return c


def test_narrator_success_french():
    nar, sp = make_narrator("fr")
    finish(nar, "mycmd", "")
    assert sp.said[-1] == "OK."


def test_narrator_success_english():
    nar, sp = make_narrator("en")
    finish(nar, "mycmd", "")
    assert sp.said[-1] == "OK."


def test_narrator_failure_no_message_french():
    nar, sp = make_narrator("fr")
    finish(nar, "false", "", code=3)
    assert sp.said[-1] == "Échec, code 3, aucun message."


def test_narrator_failure_no_message_english():
    nar, sp = make_narrator("en")
    finish(nar, "false", "", code=3)
    assert sp.said[-1] == "Failed, code 3, no message."


def test_narrator_cd_french():
    nar, sp = make_narrator("fr")
    finish(nar, "", "", old_cwd="/home/x", cwd="/home/x/projects")
    assert sp.said[-1] == "Dossier projects."


def test_narrator_cd_english():
    nar, sp = make_narrator("en")
    finish(nar, "", "", old_cwd="/home/x", cwd="/home/x/projects")
    assert sp.said[-1] == "Folder projects."


def test_narrator_command_not_found_french():
    nar, sp = make_narrator("fr")
    finish(nar, "nope", "zsh: nope: command not found", code=127)
    assert sp.said[-1] == "Commande introuvable : nope."


def test_narrator_command_not_found_english():
    nar, sp = make_narrator("en")
    finish(nar, "nope", "zsh: nope: command not found", code=127)
    assert sp.said[-1] == "Command not found: nope."


def test_narrator_interactive_end_english():
    nar, sp = make_narrator("en")
    c = Command(id=1, cmd="ssh host", cwd="/")
    c.interactive = True
    c.exit = 0
    c.end = c.start
    nar._finish(c, "/", "/")
    assert sp.said[-1] == "End of ssh."


def test_narrator_qa_system_prompt_by_language():
    from steph import prompts
    nar_fr, _ = make_narrator("fr")
    nar_en, _ = make_narrator("en")
    assert nar_fr.qa_messages()[0]["content"] == prompts.QA_SYSTEM
    assert nar_en.qa_messages()[0]["content"] == prompts.QA_SYSTEM_EN
    assert nar_en.qa_messages()[1]["content"].startswith("Session history:")


# ---------------------------------------------------------------- narrator : _review, _key, _prompt_check

def test_narrator_review_no_command_english():
    nar, sp = make_narrator("en")
    nar._review("first")
    assert sp.said[-1] == "No command yet."


def test_narrator_key_details_no_command_english():
    nar, sp = make_narrator("en")
    nar._key("details")
    assert sp.said[-1] == "No command yet."


def _register(nar, cmd, output, code=0):
    c = nar.s.start(cmd)
    c.feed(output.encode())
    c.exit = code
    c.end = c.start
    return c


def test_narrator_review_start_and_end_english():
    nar, sp = make_narrator("en")
    _register(nar, "ls", "a\nb\nc")
    nar._review("first")
    assert sp.said[-1] == "a"
    nar._review("prev")
    assert sp.said[-1] == "Start."
    nar._review("last")
    assert sp.said[-1] == "c"
    nar._review("next")
    assert sp.said[-1] == "End."


def test_narrator_review_start_and_end_french():
    nar, sp = make_narrator("fr")
    _register(nar, "ls", "a\nb\nc")
    nar._review("first")
    nar._review("prev")
    assert sp.said[-1] == "Début."
    nar._review("last")
    nar._review("next")
    assert sp.said[-1] == "Fin."


def test_narrator_prompt_check_password_english():
    nar, sp = make_narrator("en")
    c = nar.s.start("ssh host")
    c.feed(b"Password:")
    c.last_output_at -= 10  # au-delà de prompt_idle
    nar._prompt_check(c, time.time())
    assert sp.said[-1] == "Password requested."


def test_narrator_prompt_check_password_french():
    nar, sp = make_narrator("fr")
    c = nar.s.start("ssh host")
    c.feed(b"Password:")
    c.last_output_at -= 10
    nar._prompt_check(c, time.time())
    assert sp.said[-1] == "Mot de passe demandé."


# ---------------------------------------------------------------- digest : structuré

def test_digest_network_english():
    out = digest("ip -br addr", "wlan0 UP 192.168.1.20/24\nlo UNKNOWN 127.0.0.1/8\ndocker0 DOWN\n", language="en")
    assert out.splitlines() == ["wlan0 192.168.1.20", "virtual networks: 1"]


def test_digest_disks_english():
    out = digest("df -h", "Filesystem Size Used Avail Use% Mounted on\n/dev/sda1 100G 50G 45G 53% /\n", language="en")
    assert out == "root: 45G free of 100G, 53%"


def test_digest_disks_french_default_unchanged():
    out = digest("df -h", "Filesystem Size Used Avail Use% Mounted on\n/dev/sda1 100G 50G 45G 53% /\n")
    assert out == "racine : 45G libres sur 100G, 53 %"


def test_digest_pci_english():
    out = digest("lspci", "00:02.0 VGA compatible controller: Intel UHD\n", language="en")
    assert out == "GPU: Intel UHD"


def test_digest_list_english():
    out = digest("ls", "a\nb\nc\n", language="en")
    assert out.startswith("3 items: a, b, c")


# ---------------------------------------------------------------- resolve : familles existantes

def test_resolve_compile_error_english():
    out = "main.c:14:5: error: 'coutn' undeclared (first use in this function)"
    assert resolve("gcc main.c", 1, out, language="en") == \
        "Failed. main.c line 14: coutn undeclared (first use in this function)."


def test_resolve_traceback_english():
    out = ('Traceback (most recent call last):\n'
           '  File "app.py", line 3, in <module>\n'
           '    raise KeyError("x")\n'
           'KeyError: x\n')
    assert resolve("python app.py", 1, out, language="en") == "Failed. app.py line 3: KeyError x."


def test_resolve_tests_pytest_english():
    out = "..F.E\n1 failed, 3 passed, 1 error in 0.42s\n"
    assert resolve("pytest -q", 1, out, language="en") == "Failed. 1 failed, 1 error, 3 passed."


def test_resolve_tests_all_passed_english():
    out = "..\n2 passed in 0.10s\n"
    assert resolve("pytest -q", 0, out, language="en") == "2 tests passed."


def test_resolve_apt_counts_english():
    out = "1 upgraded, 3 newly installed, 1 to remove and 0 not upgraded."
    assert resolve("apt-get install nginxx", 0, out, language="en") == "1 package upgraded, 3 installed, 1 removed."


def test_resolve_apt_lock_english():
    out = ("E: Could not get lock /var/lib/dpkg/lock-frontend. It is held by process 4321 (unattended-upgr)")
    assert resolve("sudo apt install nginx", 100, out, language="en") == \
        "Failed. dpkg lock held by unattended-upgr, process 4321."


def test_resolve_pip_installed_english():
    out = "Successfully installed requests-2.32.3 idna-3.10 charset-normalizer-3.4 urllib3-2.2"
    assert resolve("pip install requests", 0, out, language="en") == "requests 2.32.3 installed, with 3 dependencies."


def test_resolve_git_status_english():
    out = "On branch master\n\nNo commits yet\n\nUntracked files:\n  (use \"git add\" to track)\n\tREADME.md\n"
    assert resolve("git status", 0, out, language="en") == "Branch master, no commits yet, 1 file untracked."


def test_resolve_git_push_behind_english():
    out = (" ! [rejected]        main -> main (fetch first)\n"
           "error: failed to push some refs\n")
    assert resolve("git push", 1, out, language="en") == \
        "Failed. Push of main rejected: the remote has commits missing locally, run git pull."


def test_resolve_curl_error_english():
    out = "curl: (6) Could not resolve host: nonexistent.invalid"
    assert resolve("curl https://nonexistent.invalid/", 6, out, language="en") == \
        "Failed. Host nonexistent.invalid not found."


def test_resolve_ssh_denied_english():
    out = "root@srv: Permission denied (publickey,password)."
    assert resolve("ssh srv", 255, out, language="en") == "Failed. SSH access denied."


def test_resolve_ping_english():
    out = ("3 packets transmitted, 3 received, 0% packet loss, time 2003ms\n"
           "rtt min/avg/max/mdev = 0.020/0.024/0.030/0.005 ms\n")
    assert resolve("ping -c 3 127.0.0.1", 0, out, language="en") == "3 received out of 3, 0% loss, average 0.024 ms."


def test_resolve_file_error_english():
    out = "cat: /nonexistent/file.txt: No such file or directory"
    assert resolve("cat /nonexistent/file.txt", 1, out, language="en") == "Failed. file.txt: file not found."


def test_resolve_free_english():
    out = ("              total        used        free      shared  buff/cache   available\n"
           "Mem.:            31G        4.0G        1.0G        500M         26G         24G\n")
    assert resolve("free -h", 0, out, language="en") == "Memory: 24 GB available of 31 GB."


def test_resolve_systemctl_status_english():
    out = "● pipewire.service - PipeWire\n     Active: active (running) since Mon 2024-01-01; 2 days ago\n"
    assert resolve("systemctl --user status pipewire --no-pager | head -20", 0, out, language="en") == \
        "pipewire active for 2 days."


# ---------------------------------------------------------------- P12 : nouveaux résolveurs (go, ld/make,
# lspci direct, git diff/log/pull/clone, docker, node, ps) en anglais

def test_resolve_go_build_errors_english():
    out = ('# example.com/app/cmd\n./cmd/main.go:6:2: "fmt" imported and not used\n'
           './cmd/main.go:7:2: "strings" imported and not used\n'
           '# example.com/app/internal/report\n./internal/report/report.go:4:2: "time" imported and not used')
    assert resolve("go build ./...", 1, out, language="en") == \
        "Failed, 3 errors. main.go line 6: fmt imported and not used."


def test_resolve_go_test_failure_english():
    out = ("ok  \texample.com/app/internal/config\t0.004s\n--- FAIL: TestCalculateTotal (0.00s)\n"
           "    calc_test.go:22: expected 150, got 140\nFAIL\nFAIL\texample.com/app/internal/pricing\t0.011s\n"
           "ok  \texample.com/app/internal/storage\t0.006s")
    assert resolve("go test ./...", 1, out, language="en") == \
        "Failed. 1 test failed. Package pricing, TestCalculateTotal, calc_test.go line 22: expected 150, got 140."


def test_resolve_ld_undefined_reference_no_source_line_english():
    out = ("cc -O2 -c src/utils.c -o src/utils.o\nsrc/main.o: In function `main':\n"
           "main.c:(.text+0x2a): undefined reference to `parse_config'\n"
           "collect2: error: ld returned 1 exit status\nmake: *** [Makefile:12: app] Error 1")
    assert resolve("make", 2, out, language="en") == \
        "Failed. main.c: undefined reference to parse_config, Makefile line 12."


def test_resolve_ld_undefined_reference_with_source_line_english():
    out = ("build/net/socket_bridge.o: in function `net_connect':\n"
           "net/socket_bridge.c:88: undefined reference to `socket_configure'\n"
           "collect2: error: ld returned 1 exit status\nmake: *** [Makefile:42: dist/engine] Error 1")
    assert resolve("make", 2, out, language="en") == \
        "Failed. socket_bridge.c line 88: undefined reference to socket_configure."


def test_resolve_lspci_direct_english():
    out = ("00:02.0 VGA compatible controller: NVIDIA Corporation GA106 [GeForce RTX 3060] (rev a1)\n"
           "2a:00.0 Ethernet controller: Realtek Semiconductor RTL8111 PCI Express Gigabit Ethernet Controller\n")
    assert resolve("lspci", 0, out, language="en") == (
        "GPU: NVIDIA Corporation GA106 [GeForce RTX 3060], "
        "network: Realtek Semiconductor RTL8111 PCI Express Gigabit Ethernet Controller.")


def test_resolve_git_diff_stat_english():
    out = " a.py | 45 +++++++++\n b.py | 12 +--\n 4 files changed, 77 insertions(+), 16 deletions(-)"
    assert resolve("git diff --stat", 0, out, language="en") == "4 files changed, 77 insertions, 16 deletions."


def test_resolve_git_log_oneline_english():
    out = ("f3a9c21 fix: correct invoice rounding for partial refunds\n"
           "9d84b6e feat: add CSV export to reports page")
    assert resolve("git log --oneline -2", 0, out, language="en") == \
        "2 commits, last: fix: correct invoice rounding for partial refunds."


def test_resolve_git_pull_fast_forward_english():
    out = ("From github.com:example/webapp\n   a1b2c3d..f9e8d7c  main -> origin/main\n"
           "Updating a1b2c3d..f9e8d7c\nFast-forward\n"
           " a.py | 22 ++++++\n 3 files changed, 31 insertions(+), 13 deletions(-)")
    assert resolve("git pull", 0, out, language="en") == \
        "Pulled, fast-forward, 3 files changed, 31 insertions, 13 deletions."


def test_resolve_git_pull_up_to_date_english():
    assert resolve("git pull", 0, "Already up to date.", language="en") == "Nothing to pull, already up to date."


def test_resolve_git_clone_auth_failure_english():
    out = ("Cloning into 'private-repo'...\nremote: Support for password authentication was removed.\n"
           "fatal: Authentication failed for 'https://github.com/example/private-repo.git/'")
    assert resolve("git clone https://github.com/example/private-repo.git", 128, out, language="en") == \
        "Failed. Authentication refused for private-repo."


def test_resolve_docker_stats_near_limit_english():
    out = ("CONTAINER ID   NAME     CPU %     MEM USAGE / LIMIT     MEM %\n"
           "a1b2c3d4e5f6   web      2.31%     498.2MiB / 512MiB     97.30%\n"
           "b7c8d9e0f1a2   worker   88.42%    511.8MiB / 512MiB     99.96%\n")
    assert resolve("docker stats --no-stream", 0, out, language="en") == \
        "Container worker near the limit, 99.96% of 512MiB."


def test_resolve_docker_system_df_english():
    out = ("TYPE            TOTAL     ACTIVE    SIZE      RECLAIMABLE\n"
           "Images          14        6         3.8GB     2.1GB (55%)\n"
           "Build Cache     52        0         890MB     890MB (100%)")
    assert resolve("docker system df", 0, out, language="en") == \
        "images 3.8GB, 2.1GB reclaimable, build cache 890MB, fully reclaimable."


def test_resolve_docker_build_failure_english():
    out = ("#6 [2/8] WORKDIR /app\n#8 [4/8] RUN npm ci\n#10 [6/8] RUN npm run test\n"
           '#10 ERROR: process "/bin/sh -c npm run test" did not complete successfully: exit code 1\n'
           "Dockerfile:14\n--------------------\n  14 | >>> RUN npm run test\n--------------------\n")
    assert resolve("docker build -t webapp:latest .", 1, out, language="en") == \
        "Failed. Dockerfile line 14, step 6 of 8, npm run test, exit code 1."


def test_resolve_docker_build_success_english():
    out = "#10 naming to registry.example.com/webapp:latest done\n#10 DONE 0.5s"
    assert resolve("docker build -t registry.example.com/webapp:latest .", 0, out, language="en") == \
        "Done. Image webapp:latest built and tagged."


def test_resolve_docker_compose_unhealthy_english():
    out = "dependency failed to start: container app-api-1 is unhealthy"
    assert resolve("docker compose up -d", 1, out, language="en") == \
        "Failed. app-api-1 unhealthy, dependency not started."


def test_resolve_docker_images_english():
    out = ("REPOSITORY   TAG       IMAGE ID       CREATED         SIZE\n"
           "webapp       latest    3f2a91c8b7d4   2 hours ago     412MB\n"
           "postgres     15        6c8a2f9d1e3b   2 weeks ago     379MB\n"
           "redis        7-alpine  1a4f7c9b2d6e   3 weeks ago     41.2MB\n")
    assert resolve("docker images", 0, out, language="en") == \
        "webapp latest, 412MB; also postgres, redis."


def test_resolve_docker_ps_restarting_container_flagged_english():
    out = ("CONTAINER ID   IMAGE   COMMAND   CREATED   STATUS   PORTS   NAMES\n"
           'abc123   nginx   "nginx"   2 days ago   Up 2 days   80/tcp   web\n'
           'def456   vault   "vault"   2 days ago   Restarting (1) 5 seconds ago      db\n')
    assert resolve("docker ps", 0, out, language="en") == "2 containers, 1 active; db restart-looping."


def test_digest_list_truncated_label_english():
    out = "a\nb\nc\nd\ne\n"
    assert digest("ls | head -3", out, language="en").startswith("5 items shown: a, b, c")


def test_resolve_node_error_english():
    out = ("Server listening on port 3000\n/app/server.js:88\n    throw new Error(`Missing env var`);\n    ^\n\n"
           "Error: Missing env var: PAYMENT_SECRET_KEY\n"
           "    at loadConfig (/app/server.js:88:11)\n"
           "    at Object.<anonymous> (/app/server.js:12:1)\nNode.js v20.11.0")
    assert resolve("docker logs webapp-api-1", 0, out, language="en") == \
        "Error. server.js line 88: Missing env var: PAYMENT_SECRET_KEY."


def test_resolve_ps_sorted_by_cpu_english():
    out = ("USER     PID  %CPU %MEM    VSZ   RSS TTY      STAT START   TIME COMMAND\n"
           "user   18422  87.3  4.2  812340 172304 ?      Rl   09:14  12:47 /usr/bin/backup-agent --full\n")
    assert resolve("ps aux --sort=-%cpu", 0, out, language="en") == \
        "backup-agent at the top, 87.3% CPU, PID 18422."


# ---------------------------------------------------------------- P9 : préfixe de statut immédiat + masquage

def test_line_count_fact_english():
    from steph.narrator import _line_count_fact
    assert _line_count_fact(1, "en") == "1 line."
    assert _line_count_fact(6, "en") == "6 lines."


def test_drop_leading_status_recognizes_english_words():
    from steph.narrator import _drop_leading_status
    assert "".join(_drop_leading_status(iter(["Success. ", "All good."]))) == "All good."
    assert "".join(_drop_leading_status(iter(["Failed. ", "Disk full."]))) == "Disk full."


def test_short_command_says_success_immediately_english():
    from test_narrator import LONG_OUTPUT, _finished_command, _narrator

    cfg = Config(language="en")
    cfg.llm_prompt_tokens_per_sec = 1.0  # force un long délai : le fait sûr doit s'ajouter
    nar, session, sp, llm = _narrator(cfg, pieces=["Success. ", "Report generated."])
    c = _finished_command(session, "customtool process --batch", "/home/user", 0, LONG_OUTPUT, active=0.5)
    nar._finish(c, "/home/user", "/home/user")
    assert llm.calls == 1
    text = sp.said[0]
    assert text.startswith("Success. ")
    assert text.count("Success") == 1  # le modèle a répété le statut, il est retiré
    assert "6 lines." in text
    assert text.endswith("Report generated.")


def test_short_command_says_failure_with_exit_code_english():
    from test_narrator import LONG_OUTPUT, _finished_command, _narrator

    cfg = Config(language="en")
    cfg.llm_prompt_tokens_per_sec = 1.0
    nar, session, sp, _llm = _narrator(cfg, pieces=["Failed. ", "Cause: disk full."])
    c = _finished_command(session, "customtool process --batch", "/home/user", 3, LONG_OUTPUT, active=0.5)
    nar._finish(c, "/home/user", "/home/user")
    text = sp.said[0]
    assert text.startswith("Failed, code 3. ")
    assert text.count("Failed") == 1
    assert "6 lines." in text
    assert text.endswith("Cause: disk full.")


# ---------------------------------------------------------------- P13 : garde-fou d'ancrage en anglais

def test_grounding_not_found_english():
    from steph.grounding import ground, ground_stream
    inp = "Session history:\n[1] ~ $ npm run build   (code 1, 1 lines)\nHeader.tsx:42"
    out = "Python 3.11 installed."
    assert ground(inp, out, is_qa=True, language="en") == "Not in the history."
    assert "".join(ground_stream(iter([out]), inp, is_qa=True, language="en")) == "Not in the history."


def test_grounding_keeps_true_facts_english():
    from steph.grounding import ground
    inp = "Output:\nroot: 45G free of 100G, 53%"
    out = "Root 45G free of 100G, 53%."
    assert ground(inp, out, language="en") == out


def test_grounding_english_default_is_french():
    from steph.grounding import ground
    inp = "Sortie :\nracine : 8.9G libres sur 94G, 91 %"
    out = "Racine 8.9G libres sur 94G, 91 %."
    assert ground(inp, out) == out


# ---------------------------------------------------------------- non-régression fr (spot-check)

def test_resolve_git_status_french_default_unchanged():
    out = "On branch master\n\nNo commits yet\n\nUntracked files:\n  (use \"git add\" to track)\n\tREADME.md\n"
    assert resolve("git status", 0, out) == "Branche master, aucun commit, 1 fichier non suivi."


def test_strings_helpers():
    assert t("en", "ok") == "OK."
    assert n("en", 1, "resolve.tests.all_passed", "resolve.tests.all_passed_many") == "1 test passed"
    assert n("en", 2, "resolve.tests.all_passed", "resolve.tests.all_passed_many") == "2 tests passed"
    assert n("fr", 1, "resolve.tests.all_passed", "resolve.tests.all_passed_many") == "1 test réussi"


def test_narrator_command_not_found_inside_script_names_program_and_line():
    nar, sp = make_narrator("fr")
    finish(nar, "bash deploy.sh", "==> Build\ndeploy.sh: ligne 7: rsyncx : commande introuvable\n", code=127)
    assert sp.said[-1] == "Commande introuvable : rsyncx, deploy.sh ligne 7."


def test_narrator_grep_without_match_says_so():
    nar, sp = make_narrator("en")
    finish(nar, "grep -rn DATABASE_URL config", "", code=1)
    assert sp.said[-1] == "No match for DATABASE_URL."
