#!/usr/bin/env python3
"""Corpus capture for steph fine-tuning (K2 : English corpus).

Runs varied terminal commands (compilation, packages, git, files, network,
system, interactive) and writes one JSON record per line: cmd, exit,
duration, output, machine, category. Locale is parametrized so the same
generator can capture in French (default, unset LANG) or in English
(--lang en, LANG/LC_ALL forced to an English locale).

Safety differs by profile:
  - macos, linux-dev: local sandbox only (own directory), no sudo, no system
    package install, no container run/stop, no service enable/start/stop.
  - linux-low: the same, plus no destructive command and no package-manager
    mutation at all (read-only package inspection instead of real installs) -
    this profile targets a remote machine with an explicit "read-only system,
    no apt install" constraint.

Usage:
    python3 capture_corpus.py --profile macos --lang en --base /tmp/steph-corpus-en

SPDX-License-Identifier: MIT
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

GIT_ENV = "git -c user.name=user -c user.email=user@example.invalid -c commit.gpgsign=false"

# Snippets a linux-low task must never contain: system-wide mutation or
# anything that is not read-only on the real machine.
FORBIDDEN_ON_LINUX_LOW = (
    "apt-get install", "apt-get remove", "apt-get purge", "apt install ",
    "yum install", "dnf install", "docker run", "docker pull", "docker rm",
    "docker rmi", "sudo ", "systemctl enable", "systemctl start", "systemctl stop",
    "systemctl restart", "mkfs", "shutdown", "reboot", "> /etc/", ">> /etc/",
)


def locale_env(lang: str, base_env: dict | None = None) -> dict:
    """Environment for one subprocess call.

    fr keeps the caller's own locale untouched (matches the original French
    capture, which never set LANG). en pins LANG/LC_ALL to an English
    locale: en_US.UTF-8 on macOS, C.utf8 on Linux (en_US.UTF-8 is not always
    generated there, C.utf8 is guaranteed and still gives UTF-8 output).
    """
    env = dict(base_env if base_env is not None else os.environ)
    if lang == "en":
        value = "en_US.UTF-8" if sys.platform == "darwin" else "C.utf8"
        env["LANG"] = value
        env["LC_ALL"] = value
    elif lang != "fr":
        raise ValueError(f"unknown lang: {lang!r}")
    return env


def add(tasks: list[dict], base: str, cmd: str, category: str,
        workdir: str | None = None, setup: str | None = None, timeout: int = 20) -> None:
    tasks.append({"cmd": cmd, "category": category, "workdir": workdir or base,
                  "setup": setup, "timeout": timeout})


def git_repo_setup(d: str) -> str:
    return f"rm -rf {d} && mkdir -p {d} && cd {d} && {GIT_ENV} init -q"


# ================= macOS =================

def _tasks_macos(base: str) -> list[dict]:
    tasks: list[dict] = []
    files = os.path.join(base, "files")
    repos = os.path.join(base, "repos")
    proj = os.path.join(base, "proj")
    tools = os.path.join(base, "tools")

    # ---- compilation ----
    clang_ok = [
        ('int main(){ printf("hello %d\\n", 3); return 0; }', "#include <stdio.h>\n"),
        ('int main(){ int a=8,b=13; printf("sum=%d\\n", a+b); return 0; }', "#include <stdio.h>\n"),
        ('int main(){ int i; for(i=0;i<3;i++) printf("%d\\n", i*i); return 0; }', "#include <stdio.h>\n"),
    ]
    for i in range(5):
        body, inc = clang_ok[i % len(clang_ok)]
        src = os.path.join(files, f"c_ok_{i}.c")
        setup = f"cat > {src} <<'EOF'\n{inc}{body}\nEOF"
        add(tasks, base, f"clang -Wall -o {files}/c_ok_{i} {files}/c_ok_{i}.c && {files}/c_ok_{i}", "compilation", setup=setup)

    clang_bad = [
        'int main(){ int x = 4 return x; }',
        'int main(){ printf("try")\n return 0; }',
        'int main(){ int y; y = ; return 0; }',
    ]
    for i in range(5):
        body = clang_bad[i % len(clang_bad)]
        src = os.path.join(files, f"c_bad_{i}.c")
        setup = f"cat > {src} <<'EOF'\n#include <stdio.h>\n{body}\nEOF"
        add(tasks, base, f"clang -Wall -o {files}/c_bad_{i} {files}/c_bad_{i}.c", "compilation", setup=setup)

    for i in range(4):
        fname = f"missing_calc_{i}"
        src = os.path.join(files, f"c_link_{i}.c")
        setup = (f"cat > {src} <<'EOF'\n#include <stdio.h>\nint {fname}(int x);\n"
                 f"int main(){{ printf(\"%d\\\\n\", {fname}(4)); return 0; }}\nEOF")
        add(tasks, base, f"clang -Wall -o {files}/c_link_{i} {files}/c_link_{i}.c", "compilation", setup=setup)

    for i in range(6):
        d = os.path.join(files, f"make_ok_{i}")
        setup = (f"mkdir -p {d} && cat > {d}/main.c <<'EOF'\n#include <stdio.h>\nint main(){{ printf(\"build {i}\\\\n\"); return 0; }}\nEOF\n"
                 f"cat > {d}/Makefile <<'EOF'\nall: prog_{i}\nprog_{i}: main.c\n\tclang -o prog_{i} main.c\nEOF")
        add(tasks, base, "make", "compilation", workdir=d, setup=setup)
    for i in range(4):
        d = os.path.join(files, f"make_sep_{i}")
        setup = (f"mkdir -p {d} && cat > {d}/main.c <<'EOF'\nint main(){{ return 0; }}\nEOF\n"
                 f"printf 'all: prog_{i}\\nprog_{i}: main.c\\n    clang -o prog_{i} main.c\\n' > {d}/Makefile")
        add(tasks, base, "make", "compilation", workdir=d, setup=setup)

    py_ok = [
        "print(sum(range(15)))",
        "d={'a':1,'b':2}\nprint(sorted(d.items()))",
        "import math\nprint(round(math.e, 3))",
        "print([n*2 for n in range(5)])",
    ]
    for i in range(5):
        body = py_ok[i % len(py_ok)]
        src = os.path.join(files, f"py_ok_{i}.py")
        setup = f"cat > {src} <<'PYEOF'\n{body}\nprint('run {i}')\nPYEOF"
        add(tasks, base, f"python3 {files}/py_ok_{i}.py", "compilation", setup=setup)

    py_bad = [
        "x = 5 / 0",
        "d={'a':1}\nprint(d['z'])",
        "print(2 + 'text')",
        "import module_missing_corpus_mac",
        "print(undefined_value)",
        "int('not_an_int')",
    ]
    for i in range(5):
        body = py_bad[i % len(py_bad)]
        src = os.path.join(files, f"py_bad_{i}.py")
        setup = f"cat > {src} <<'PYEOF'\n{body}\nPYEOF"
        add(tasks, base, f"python3 {files}/py_bad_{i}.py", "compilation", setup=setup)

    for i in range(4):
        src = os.path.join(files, f"swift_ok_{i}.swift")
        setup = f"cat > {src} <<'EOF'\nprint(\"swift ok {i} : \\\\({i}*{i})\")\nEOF"
        add(tasks, base, f"swift {files}/swift_ok_{i}.swift", "compilation", setup=setup, timeout=40)
    for i in range(4):
        src = os.path.join(files, f"swift_bad_{i}.swift")
        setup = f"cat > {src} <<'EOF'\nlet x: Int = \"not_an_int{i}\"\nprint(x)\nEOF"
        add(tasks, base, f"swift {files}/swift_bad_{i}.swift", "compilation", setup=setup, timeout=40)

    for i in range(3):
        d = os.path.join(proj, f"npm_fail_{i}")
        setup = (f"mkdir -p {d} && cat > {d}/package.json <<'EOF'\n"
                 f'{{"name":"proj{i}","version":"1.0.0","scripts":{{"build":"node build.js"}}}}\n'
                 f"EOF\ncat > {d}/build.js <<'EOF'\nrequire('module-missing-mac-{i}');\nEOF")
        add(tasks, base, "npm run build", "compilation", workdir=d, setup=setup, timeout=20)
    for i in range(2):
        d = os.path.join(proj, f"npm_ok_{i}")
        setup = (f"mkdir -p {d} && cat > {d}/package.json <<'EOF'\n"
                 f'{{"name":"proj{i}b","version":"1.0.0","scripts":{{"build":"node build.js"}}}}\n'
                 f"EOF\ncat > {d}/build.js <<'EOF'\nconsole.log('build {i} done');\nEOF")
        add(tasks, base, "npm run build", "compilation", workdir=d, setup=setup, timeout=20)

    for i in range(3):
        f = os.path.join(files, f"codesign_{i}.txt")
        setup = f"echo 'content {i}' > {f}"
        add(tasks, base, f"codesign -v {files}/codesign_{i}.txt", "compilation", setup=setup, timeout=10)

    # ---- packages (brew is read-only ; pip/npm stay local to the sandbox) ----
    for cmd in ["brew list", "brew outdated", "brew list --versions", "brew --version"]:
        add(tasks, base, cmd, "packages", timeout=25)
    for pkg in ["wget", "jq", "git", "node", "tree"]:
        add(tasks, base, f"brew info {pkg}", "packages", timeout=20)
    for pkg in ["nonexistent-brew-formula-corpus-1", "fake-formula-2"]:
        add(tasks, base, f"brew info {pkg}", "packages", timeout=20)

    add(tasks, base, f"python3 -m venv {base}/venv", "packages", timeout=30)
    for pkg in ["requests", "six", "attrs", "click"]:
        add(tasks, base, f"{base}/venv/bin/pip install {pkg}", "packages", timeout=30)
    for pkg in ["nonexistent-python-package-mac", "steph-fake-pypackage-mac"]:
        add(tasks, base, f"{base}/venv/bin/pip install {pkg}", "packages", timeout=25)
    add(tasks, base, f"{base}/venv/bin/pip install requests==999.999.999", "packages", timeout=25)

    for i, pkg in enumerate(["is-odd", "ms", "kleur"]):
        d = os.path.join(proj, f"npminst_ok_{i}")
        setup = f"mkdir -p {d} && cd {d} && npm init -y >/dev/null 2>&1"
        add(tasks, base, f"npm install {pkg}", "packages", workdir=d, setup=setup, timeout=30)
    for i, pkg in enumerate(["nonexistent-npm-package-mac-1", "this-module-does-not-exist-mac-2"]):
        d = os.path.join(proj, f"npminst_bad_{i}")
        setup = f"mkdir -p {d} && cd {d} && npm init -y >/dev/null 2>&1"
        add(tasks, base, f"npm install {pkg}", "packages", workdir=d, setup=setup, timeout=30)

    # ---- git ----
    for i in range(4):
        d = os.path.join(repos, f"repo_basic_{i}")
        setup = (f"{git_repo_setup(d)} && echo 'content {i}' > file{i}.txt && {GIT_ENV} -C {d} add file{i}.txt "
                 f"&& {GIT_ENV} -C {d} commit -q -m 'add file{i}' "
                 f"&& echo 'draft {i}' > new_{i}.txt && echo 'change {i}' >> file{i}.txt")
        add(tasks, base, f"{GIT_ENV} status", "git", workdir=d, setup=setup)
        add(tasks, base, f"{GIT_ENV} log --oneline", "git", workdir=d)

    for i in range(2):
        d = os.path.join(repos, f"repo_empty_{i}")
        setup = git_repo_setup(d)
        add(tasks, base, f"{GIT_ENV} log", "git", workdir=d, setup=setup)
        add(tasks, base, f"{GIT_ENV} commit -m 'nothing to commit'", "git", workdir=d)

    for i in range(2):
        d = os.path.join(repos, f"repo_branch_{i}")
        setup = f"{git_repo_setup(d)} && echo init > a.txt && {GIT_ENV} -C {d} add a.txt && {GIT_ENV} -C {d} commit -q -m init"
        add(tasks, base, f"{GIT_ENV} checkout nonexistent-branch-{i}", "git", workdir=d, setup=setup)

    for i in range(2):
        d = os.path.join(repos, f"repo_merge_{i}")
        setup = (f"{git_repo_setup(d)} && echo v1 > f{i}.txt && {GIT_ENV} -C {d} add f{i}.txt && {GIT_ENV} -C {d} commit -q -m v1 "
                 f"&& {GIT_ENV} -C {d} checkout -q -b branch-a-{i} && echo v2a-{i} > f{i}.txt && {GIT_ENV} -C {d} commit -q -am v2a "
                 f"&& {GIT_ENV} -C {d} checkout -q master && echo v2b-{i} > f{i}.txt && {GIT_ENV} -C {d} commit -q -am v2b")
        add(tasks, base, f"{GIT_ENV} merge branch-a-{i}", "git", workdir=d, setup=setup)

    for i in range(2):
        d = os.path.join(repos, f"repo_push_{i}")
        setup = (f"{git_repo_setup(d)} && echo x > f.txt && {GIT_ENV} -C {d} add f.txt && {GIT_ENV} -C {d} commit -q -m x "
                 f"&& {GIT_ENV} -C {d} remote add origin https://remote-mac-{i}.invalid/project.git")
        add(tasks, base, f"{GIT_ENV} push origin master", "git", workdir=d, setup=setup, timeout=15)

    for i in range(2):
        d = os.path.join(repos, f"repo_clone_{i}")
        add(tasks, base, f"{GIT_ENV} clone {base}/repos/does-not-exist-{i} {d}", "git", timeout=15)

    for i in range(2):
        d = os.path.join(repos, f"repo_diff_{i}")
        setup = (f"{git_repo_setup(d)} && printf 'line 1\\nline 2\\n' > data{i}.txt "
                 f"&& {GIT_ENV} -C {d} add data{i}.txt && {GIT_ENV} -C {d} commit -q -m init "
                 f"&& printf 'line 1\\nline changed {i}\\nline added\\n' > data{i}.txt")
        add(tasks, base, f"{GIT_ENV} diff", "git", workdir=d, setup=setup)

    for i in range(2):
        d = os.path.join(repos, f"repo_unmerged_{i}")
        setup = (f"{git_repo_setup(d)} && echo base > f.txt && {GIT_ENV} -C {d} add f.txt && {GIT_ENV} -C {d} commit -q -m base "
                 f"&& {GIT_ENV} -C {d} checkout -q -b feature-{i} && echo feature > g.txt && {GIT_ENV} -C {d} add g.txt "
                 f"&& {GIT_ENV} -C {d} commit -q -m feature && {GIT_ENV} -C {d} checkout -q master")
        add(tasks, base, f"{GIT_ENV} branch -d feature-{i}", "git", workdir=d, setup=setup)

    # ---- files (confined to the sandbox) ----
    for i in range(6):
        d = os.path.join(files, f"tree_{i}")
        n = 2 + (i % 4)
        setup = f"mkdir -p {d}/documents && " + " && ".join(f"echo doc{i}_{j} > {d}/documents/file{j}.txt" for j in range(n))
        add(tasks, base, f"ls -la {files}/tree_{i}/documents", "files", setup=setup)
    for i in range(8):
        add(tasks, base, f"ls -la {base}/missing_path_{i}", "files")
    for i in range(4):
        d = os.path.join(files, f"private_{i}")
        setup = f"mkdir -p {d} && touch {d}/secret.txt && chmod 000 {d}"
        add(tasks, base, f"ls -la {files}/private_{i}", "files", setup=setup)

    for i in range(6):
        d = os.path.join(files, f"found_{i}")
        n = 2 + (i % 3)
        setup = f"mkdir -p {d}/sub && " + " && ".join(f"echo r{i}_{j} > {d}/sub/report{j}.txt" for j in range(n))
        add(tasks, base, f"find {files}/found_{i} -name '*.txt'", "files", setup=setup)
    for i in range(4):
        add(tasks, base, f"find {base}/absent_{i} -maxdepth 2", "files")

    for i in range(3):
        d = os.path.join(files, f"size_{i}")
        setup = f"mkdir -p {d} && dd if=/dev/urandom of={d}/blob.bin bs=1024 count=1 2>/dev/null"
        add(tasks, base, f"du -sh {files}/size_{i}", "files", setup=setup)

    for i in range(8):
        d = os.path.join(files, f"cat_ok_{i}")
        setup = f"mkdir -p {d} && printf 'line one\\nline two\\nindex={i}\\n' > {d}/notes.txt"
        add(tasks, base, f"cat {files}/cat_ok_{i}/notes.txt", "files", setup=setup)
    for i in range(5):
        add(tasks, base, f"cat {files}/cat_absent_{i}.txt", "files")
    for i in range(3):
        d = os.path.join(files, f"cat_dir_{i}")
        setup = f"mkdir -p {d}"
        add(tasks, base, f"cat {files}/cat_dir_{i}", "files", setup=setup)

    for i in range(6):
        src = os.path.join(files, f"cp_src_{i}.txt")
        setup = f"echo content{i} > {src}"
        add(tasks, base, f"cp {files}/cp_src_{i}.txt {files}/cp_dst_{i}.txt", "files", setup=setup)
    for i in range(4):
        add(tasks, base, f"cp {files}/cp_src_{i}.txt {base}/missing_dir_{i}/dst.txt", "files")

    for i in range(4):
        src = os.path.join(files, f"mv_src_{i}.txt")
        setup = f"echo mv{i} > {src}"
        add(tasks, base, f"mv {files}/mv_src_{i}.txt {files}/mv_dst_{i}.txt", "files", setup=setup)
    for i in range(3):
        add(tasks, base, f"mv {files}/mv_absent_{i}.txt {files}/mv_dst2_{i}.txt", "files")

    for i in range(4):
        f = os.path.join(files, f"chmod_ok_{i}.sh")
        setup = f"echo '#!/bin/sh' > {f}"
        add(tasks, base, f"chmod +x {files}/chmod_ok_{i}.sh && ls -l {files}/chmod_ok_{i}.sh", "files", setup=setup)

    for i in range(4):
        d = os.path.join(files, f"tar_ok_{i}")
        setup = f"mkdir -p {d} && echo data{i} > {d}/a.txt"
        add(tasks, base, f"tar czf {files}/tar_ok_{i}.tgz -C {files} tar_ok_{i}", "files", setup=setup)
    for i in range(3):
        f = os.path.join(files, f"tar_bad_{i}.tgz")
        setup = f"head -c 150 /dev/urandom > {f}"
        add(tasks, base, f"tar xzf {files}/tar_bad_{i}.tgz -C {files}", "files", setup=setup)

    # macOS-specific error: Operation not permitted via chflags uchg (locally-locked file)
    for i in range(4):
        f = os.path.join(files, f"locked_{i}.txt")
        setup = f"echo locked{i} > {f} && chflags uchg {f}"
        add(tasks, base, f"rm {files}/locked_{i}.txt", "files", setup=setup, timeout=10)

    # ---- network ----
    for cmd in ["ifconfig", "ifconfig -a", "netstat -rn", "netstat -i", "networksetup -listallhardwareports"]:
        add(tasks, base, cmd, "network", timeout=15)
    for _ in range(3):
        add(tasks, base, "ping -c 2 localhost", "network", timeout=10)
    for _ in range(3):
        add(tasks, base, "ping -c 2 127.0.0.1", "network", timeout=10)
    for ip in ["10.255.255.11", "10.255.255.12", "192.168.99.199", "192.168.99.198"]:
        add(tasks, base, f"ping -c 2 -t 1 {ip}", "network", timeout=10)
    for i in range(6):
        add(tasks, base, f"curl -sS --max-time 3 http://missing-host-mac-{i}.invalid/", "network", timeout=8)
    for port in [9999, 9998, 9997]:
        add(tasks, base, f"curl -sS --max-time 3 http://127.0.0.1:{port}/", "network", timeout=8)
    for _ in range(2):
        add(tasks, base, "curl -sS --max-time 5 http://example.com/", "network", timeout=8)
    for _ in range(2):
        add(tasks, base, "dig +time=2 +tries=1 example.com", "network", timeout=8)
    for dom in [f"absent-dns-mac-{i}.invalid" for i in range(4)]:
        add(tasks, base, f"dig +time=2 +tries=1 {dom}", "network", timeout=8)

    # ---- system ----
    for cmd in ["sw_vers", "uname -a", "uname -m", "uname -r"]:
        add(tasks, base, cmd, "system")
    for cmd in ["diskutil list", "df -h", "vm_stat"]:
        add(tasks, base, cmd, "system", timeout=15)
    for cmd in ["sysctl hw.ncpu", "sysctl hw.memsize", "sysctl machdep.cpu.brand_string"]:
        add(tasks, base, cmd, "system")
    for cmd in ["top -l 1 -n 10", "ps aux | head -25", "ps -ef | head -20"]:
        add(tasks, base, cmd, "system", timeout=15)
    add(tasks, base, "pmset -g batt", "system", timeout=10)
    for cmd in ["system_profiler SPHardwareDataType", "system_profiler SPDisplaysDataType"]:
        add(tasks, base, cmd, "system", timeout=30)
    for cmd in ["launchctl list | head -30", "xcode-select -p", "clang --version", "swift --version"]:
        add(tasks, base, cmd, "system", timeout=15)
    for i in range(3):
        add(tasks, base, f"xcode-select --install-fake-{i}", "system", timeout=10)

    # ---- interactive (fails on closed stdin) ----
    prompts = ["Name", "Confirm (y/n)", "Continue", "Choice", "Path", "Server"]
    for i in range(4):
        p = prompts[i % len(prompts)]
        add(tasks, base, f"python3 -c \"x=input('{p} {i}: '); print(x)\"", "interactive", timeout=10)
    for i in range(6):
        p = prompts[i % len(prompts)]
        add(tasks, base, f"bash -c 'read -p \"{p} {i} : \" rep; echo answer=$rep'", "interactive", timeout=10)
    for i in range(2):
        d = os.path.join(repos, f"repo_edit_{i}")
        setup = git_repo_setup(d) + f" && echo x{i} > f.txt && {GIT_ENV} -C {d} add f.txt"
        add(tasks, base, f"EDITOR=false {GIT_ENV} commit", "interactive", workdir=d, setup=setup, timeout=10)
    for i in range(4):
        add(tasks, base, "python3 -c \"import sys; x=input(); sys.exit(0 if x else 1)\"", "interactive", timeout=10)

    # ---- BSD/macOS text and file tools (diversity of programs) ----
    txt = os.path.join(tools, "corpus.txt")
    txt2 = os.path.join(tools, "corpus2.txt")
    js = os.path.join(tools, "data.json")
    tools_prep = (
        f"printf 'apple 3\\nbanana 7\\napple 3\\ncherry 1\\nbanana 7\\ndate 5\\nkiwi 2\\n' > {txt} && "
        f"printf 'apple 3\\nbanana 9\\ncherry 1\\nfig 4\\n' > {txt2} && "
        f"printf '{{\"name\":\"steph\",\"version\":1,\"tags\":[\"cli\",\"voice\"]}}\\n' > {js}"
    )

    def addt(cmd: str, category: str, timeout: int = 15) -> None:
        add(tasks, base, cmd, category, workdir=tools, setup=None, timeout=timeout)

    addt(f"grep apple {txt}", "text")
    tasks[-1]["setup"] = tools_prep
    addt(f"grep -c banana {txt}", "text")
    addt("grep --invalid-option test", "text")
    addt(f"egrep 'apple|kiwi' {txt}", "text")
    addt(f"sed -n '2p' {txt}", "text")
    addt(f"sed 's/apple/pear/' {txt}", "text")
    addt(f"awk '{{print $1}}' {txt}", "text")
    addt(f"awk '{{sum+=$2}} END{{print sum}}' {txt}", "text")
    addt("awk 'BEGIN{print 1/0}'", "text")
    addt(f"cut -d' ' -f1 {txt}", "text")
    addt(f"sort {txt}", "text")
    addt(f"sort {txt} | uniq -c", "text")
    addt(f"wc -l {txt}", "text")
    addt(f"head -n 2 {txt}", "text")
    addt(f"tail -n +3 {txt}", "text")
    addt(f"diff {txt} {txt2}", "text")
    addt(f"jq . {js}", "text")
    addt(f"jq .absent {js}", "text")

    addt(f"stat {txt}", "files")
    addt(f"file {txt}", "files")
    addt(f"touch {tools}/new_touch.txt && ls -l {tools}/new_touch.txt", "files")
    addt(f"shasum -a 256 {txt}", "files")
    addt(f"md5 {txt}", "files")
    addt(f"gzip -k -c {txt} > {tools}/corpus.txt.gz", "files")
    addt(f"gzip -t {tools}/corpus.txt.gz", "files")

    addt("uname", "system")
    addt("hostname", "system")
    addt("whoami", "system")
    addt("id", "system")
    addt("date", "system")
    addt("which python3", "system")
    addt("which nonexistent-program-corpus", "system")
    addt("defaults read NSGlobalDomain AppleLocale", "system")

    addt("ps aux | grep Finder | grep -v grep", "processes")
    addt("pgrep -l Finder", "processes")
    addt("kill -0 $$", "processes")
    addt("nice -n 10 echo test", "processes")

    addt("nslookup example.com", "network", timeout=8)
    addt("host example.com", "network", timeout=8)
    addt("curl -sS -I --max-time 5 http://example.com/", "network", timeout=8)

    addt("docker ps", "containers", timeout=10)
    addt("docker images", "containers", timeout=10)

    return tasks


# ================= linux-dev (dev-host) =================

def _tasks_linux_dev(base: str) -> list[dict]:
    """Same shape as the machine that produced the French linux-dev split:
    read-only outside `base`, no sudo, no system package install, no
    container run/stop."""
    tasks: list[dict] = []
    files = os.path.join(base, "files")
    repos = os.path.join(base, "repos")
    proj = os.path.join(base, "proj")

    gcc_ok = [
        ('int main(){ printf("hello %d\\n", 42); return 0; }', "#include <stdio.h>\n"),
        ('int main(){ int a=3,b=4; printf("sum=%d\\n", a+b); return 0; }', "#include <stdio.h>\n"),
        ('int main(){ int i; for(i=0;i<5;i++) printf("i=%d\\n", i); return 0; }', "#include <stdio.h>\n"),
    ]
    for i in range(6):
        body, inc = gcc_ok[i % len(gcc_ok)]
        src = os.path.join(files, f"gcc_ok_{i}.c")
        setup = f"cat > {src} <<'EOF'\n{inc}{body}\nEOF"
        add(tasks, base, f"gcc -Wall -o {files}/gcc_ok_{i} {files}/gcc_ok_{i}.c && {files}/gcc_ok_{i}", "compilation", setup=setup)

    gcc_bad = [
        'int main(){ int x = 5 return x; }',
        'int main(){ printf("test")\n return 0; }',
        'int main(){ int y; y = ; return 0; }',
    ]
    for i in range(6):
        body = gcc_bad[i % len(gcc_bad)]
        src = os.path.join(files, f"gcc_bad_{i}.c")
        setup = f"cat > {src} <<'EOF'\n#include <stdio.h>\n{body}\nEOF"
        add(tasks, base, f"gcc -Wall -o {files}/gcc_bad_{i} {files}/gcc_bad_{i}.c", "compilation", setup=setup)

    for i in range(5):
        fname = f"missing_function_{i}"
        src = os.path.join(files, f"gcc_link_{i}.c")
        setup = f"cat > {src} <<'EOF'\n#include <stdio.h>\nint {fname}(int x);\nint main(){{ printf(\"%d\\\\n\", {fname}(i)); return 0; }}\nEOF"
        add(tasks, base, f"gcc -Wall -o {files}/gcc_link_{i} {files}/gcc_link_{i}.c", "compilation", setup=setup)

    for i in range(4):
        d = os.path.join(files, f"make_ok_{i}")
        setup = (f"mkdir -p {d} && cat > {d}/main.c <<'EOF'\n#include <stdio.h>\nint main(){{ printf(\"build {i} ok\\\\n\"); return 0; }}\nEOF\n"
                 f"cat > {d}/Makefile <<'EOF'\nall: prog\nprog: main.c\n\tgcc -o prog main.c\nEOF")
        add(tasks, base, "make", "compilation", workdir=d, setup=setup)
    for i in range(3):
        d = os.path.join(files, f"make_sep_{i}")
        setup = (f"mkdir -p {d} && cat > {d}/main.c <<'EOF'\nint main(){{ return 0; }}\nEOF\n"
                 f"printf 'all: prog\\nprog: main.c\\n    gcc -o prog main.c\\n' > {d}/Makefile")
        add(tasks, base, "make", "compilation", workdir=d, setup=setup)

    py_ok = [
        "print(sum(range(10)))",
        "d = {'a':1,'b':2}\nprint(sorted(d.items()))",
        "import math\nprint(round(math.sqrt(2), 4))",
    ]
    for i in range(6):
        body = py_ok[i % len(py_ok)]
        src = os.path.join(files, f"py_ok_{i}.py")
        setup = f"cat > {src} <<'PYEOF'\n{body}\nPYEOF"
        add(tasks, base, f"python3 {files}/py_ok_{i}.py", "compilation", setup=setup)

    py_bad = [
        "x = 1 / 0",
        "d = {'a': 1}\nprint(d['b'])",
        "print(1 + 'text')",
        "import module_that_does_not_exist",
    ]
    for i in range(6):
        body = py_bad[i % len(py_bad)]
        src = os.path.join(files, f"py_bad_{i}.py")
        setup = f"cat > {src} <<'PYEOF'\n{body}\nPYEOF"
        add(tasks, base, f"python3 {files}/py_bad_{i}.py", "compilation", setup=setup)

    for i in range(3):
        d = os.path.join(proj, f"npm_fail_{i}")
        setup = (f"mkdir -p {d} && cat > {d}/package.json <<'EOF'\n"
                 f'{{"name":"proj{i}","version":"1.0.0","scripts":{{"build":"node build.js"}}}}\n'
                 f"EOF\ncat > {d}/build.js <<'EOF'\nconst x = require('module-missing-{i}');\nEOF")
        add(tasks, base, "npm run build", "compilation", workdir=d, setup=setup, timeout=30)
    for i in range(3):
        d = os.path.join(proj, f"npm_ok_{i}")
        setup = (f"mkdir -p {d} && cat > {d}/package.json <<'EOF'\n"
                 f'{{"name":"proj{i}b","version":"1.0.0","scripts":{{"build":"node build.js"}}}}\n'
                 f"EOF\ncat > {d}/build.js <<'EOF'\nconsole.log('build {i} done');\nEOF")
        add(tasks, base, "npm run build", "compilation", workdir=d, setup=setup, timeout=30)

    # packages: local venv/npm only, no system install
    add(tasks, base, f"python3 -m venv {base}/venv", "packages", timeout=30)
    for pkg in ["is-odd", "ms", "kleur"]:
        d = os.path.join(proj, f"npminst_ok_{pkg}")
        setup = f"mkdir -p {d} && cd {d} && npm init -y >/dev/null 2>&1"
        add(tasks, base, f"npm install {pkg}", "packages", workdir=d, setup=setup, timeout=30)
    for pkg in ["nonexistent-package-abc", "this-module-does-not-exist-123"]:
        d = os.path.join(proj, f"npminst_bad_{pkg}")
        setup = f"mkdir -p {d} && cd {d} && npm init -y >/dev/null 2>&1"
        add(tasks, base, f"npm install {pkg}", "packages", workdir=d, setup=setup, timeout=30)
    for pkg in ["requests", "six", "attrs", "click"]:
        add(tasks, base, f"{base}/venv/bin/pip install {pkg}", "packages", timeout=30)
    for pkg in ["nonexistent-python-package-abc", "steph-fake-pypackage"]:
        add(tasks, base, f"{base}/venv/bin/pip install {pkg}", "packages", timeout=25)

    # git (same shape as before, in English)
    for i in range(4):
        d = os.path.join(repos, f"repo_basic_{i}")
        setup = (f"{git_repo_setup(d)} && echo 'content {i}' > file{i}.txt && {GIT_ENV} -C {d} add file{i}.txt "
                 f"&& {GIT_ENV} -C {d} commit -q -m 'add file{i}'")
        add(tasks, base, f"{GIT_ENV} status", "git", workdir=d, setup=setup)
        add(tasks, base, f"{GIT_ENV} log --oneline", "git", workdir=d)
    for i in range(3):
        d = os.path.join(repos, f"repo_empty_{i}")
        setup = git_repo_setup(d)
        add(tasks, base, f"{GIT_ENV} log", "git", workdir=d, setup=setup)
        add(tasks, base, f"{GIT_ENV} commit -m 'nothing to commit'", "git", workdir=d)
    for i in range(2):
        d = os.path.join(repos, f"repo_branch_{i}")
        setup = f"{git_repo_setup(d)} && echo init > a.txt && {GIT_ENV} -C {d} add a.txt && {GIT_ENV} -C {d} commit -q -m init"
        add(tasks, base, f"{GIT_ENV} checkout nonexistent-branch-{i}", "git", workdir=d, setup=setup)
    for i in range(2):
        d = os.path.join(repos, f"repo_merge_{i}")
        setup = (f"{git_repo_setup(d)} && echo v1 > f.txt && {GIT_ENV} -C {d} add f.txt && {GIT_ENV} -C {d} commit -q -m v1 "
                 f"&& {GIT_ENV} -C {d} checkout -q -b branch-a && echo v2a > f.txt && {GIT_ENV} -C {d} commit -q -am v2a "
                 f"&& {GIT_ENV} -C {d} checkout -q master && echo v2b > f.txt && {GIT_ENV} -C {d} commit -q -am v2b")
        add(tasks, base, f"{GIT_ENV} merge branch-a", "git", workdir=d, setup=setup)
    for i in range(2):
        d = os.path.join(repos, f"repo_diff_{i}")
        add(tasks, base, f"{GIT_ENV} diff", "git", workdir=d)
    for i in range(2):
        d = os.path.join(repos, f"repo_clone_{i}")
        add(tasks, base, f"{GIT_ENV} clone {base}/repos/does-not-exist-{i} {d}", "git", timeout=15)

    # files
    add(tasks, base, f"mkdir -p {files}/tree/a {files}/tree/b", "files")
    for _ in range(6):
        add(tasks, base, f"ls -la {files}/tree", "files")
    for i in range(6):
        add(tasks, base, f"ls -la {base}/missing_path_{i}", "files")
    for i in range(3):
        d = os.path.join(files, f"private_{i}")
        setup = f"mkdir -p {d} && touch {d}/secret.txt && chmod 000 {d}"
        add(tasks, base, f"ls -la {files}/private_{i}", "files", setup=setup)
    for sub in ["/usr/bin", "/proc/cpuinfo"]:
        add(tasks, base, f"ls -la {sub} | head -10", "files")
    for i in range(6):
        add(tasks, base, f"find {files}/tree -name '*.txt'", "files")
    for i in range(6):
        add(tasks, base, f"cat {base}/absent_cat_{i}.txt", "files")

    # network
    for cmd in ["ip a", "ip -br a", "ip route", "ip link"]:
        add(tasks, base, cmd, "network")
    for _ in range(3):
        add(tasks, base, "ping -c 2 localhost", "network", timeout=10)
    for _ in range(3):
        add(tasks, base, "ping -c 2 127.0.0.1", "network", timeout=10)
    for ip in ["10.255.255.1", "192.168.99.99"]:
        add(tasks, base, f"ping -c 2 -W 1 {ip}", "network", timeout=10)
    for dom in [f"missing-dns-dev-{i}.invalid" for i in range(4)]:
        add(tasks, base, f"curl -sS --max-time 3 http://{dom}/", "network", timeout=8)
    for _ in range(3):
        add(tasks, base, "curl -sS --max-time 5 http://example.com/", "network", timeout=8)
    for _ in range(3):
        add(tasks, base, "dig +time=2 +tries=1 example.com", "network", timeout=8)

    # system (read-only)
    for cmd in ["free -h", "free -m"]:
        add(tasks, base, cmd, "system")
    for cmd in ["uptime", "df -h", "lscpu", "lspci"]:
        add(tasks, base, cmd, "system", timeout=15)
    for svc in ["ssh", "docker", "cron"]:
        add(tasks, base, f"systemctl status {svc} --no-pager", "system", timeout=10)
    for cmd in ["journalctl -n 20 --no-pager", "journalctl -p err -n 20 --no-pager"]:
        add(tasks, base, cmd, "system", timeout=15)
    for cmd in ["ps aux | head -20", "ps -ef | head -20"]:
        add(tasks, base, cmd, "system")

    # containers: read-only only, never run/stop
    for cmd in ["docker ps", "docker ps -a", "docker images", "docker version"]:
        add(tasks, base, cmd, "containers", timeout=15)
    for i in range(3):
        add(tasks, base, f"docker inspect nonexistent-container-{i}", "containers", timeout=10)
    for i in range(2):
        add(tasks, base, f"docker logs missing-container-{i}", "containers", timeout=10)

    # interactive
    prompts = ["Name", "City", "Confirm (y/n)", "Password", "Continue", "Choice"]
    for i in range(6):
        p = prompts[i % len(prompts)]
        add(tasks, base, f"python3 -c \"x=input('{p} {i}: '); print(x)\"", "interactive", timeout=10)
    for i in range(4):
        p = prompts[i % len(prompts)]
        add(tasks, base, f"bash -c 'read -p \"{p} {i} : \" rep; echo answer=$rep'", "interactive", timeout=10)
    for i in range(2):
        d = os.path.join(repos, f"repo_edit_{i}")
        setup = git_repo_setup(d) + f" && echo x{i} > f.txt && {GIT_ENV} -C {d} add f.txt"
        add(tasks, base, f"EDITOR=false {GIT_ENV} commit", "interactive", workdir=d, setup=setup, timeout=10)

    return tasks


# ================= linux-low (remote test machine, read-only) =================

def _tasks_linux_low(base: str) -> list[dict]:
    """Targets a machine with an explicit read-only-system constraint: no apt
    install/remove, no docker run/pull, no service enable/start/stop. Package
    diversity comes from read-only inspection (apt-cache, dpkg -s) instead of
    real installs; pip/npm stay confined to a sandbox venv/project."""
    tasks: list[dict] = []
    files = os.path.join(base, "files")
    repos = os.path.join(base, "repos")
    proj = os.path.join(base, "proj")

    gcc_ok = [
        ('int main(){ printf("hello %d\\n", 7); return 0; }', "#include <stdio.h>\n"),
        ('int main(){ int a=10,b=32; printf("total=%d\\n", a+b); return 0; }', "#include <stdio.h>\n"),
        ('int main(){ int i; for(i=1;i<=4;i++) printf("%d squared = %d\\n", i, i*i); return 0; }', "#include <stdio.h>\n"),
    ]
    for i in range(6):
        body, inc = gcc_ok[i % len(gcc_ok)]
        src = os.path.join(files, f"gcc_ok_{i}.c")
        setup = f"cat > {src} <<'EOF'\n{inc}{body}\nEOF"
        add(tasks, base, f"gcc -Wall -o {files}/gcc_ok_{i} {files}/gcc_ok_{i}.c && {files}/gcc_ok_{i}", "compilation", setup=setup)

    gcc_bad = [
        'int main(){ int x = 5 return x; }',
        'int main(){ printf("try")\n return 0; }',
        'int main(){ int y; y = ; return 0; }',
    ]
    for i in range(6):
        body = gcc_bad[i % len(gcc_bad)]
        src = os.path.join(files, f"gcc_bad_{i}.c")
        setup = f"cat > {src} <<'EOF'\n#include <stdio.h>\n{body}\nEOF"
        add(tasks, base, f"gcc -Wall -o {files}/gcc_bad_{i} {files}/gcc_bad_{i}.c", "compilation", setup=setup)

    for i in range(5):
        fname = f"missing_calc_{i}"
        src = os.path.join(files, f"gcc_link_{i}.c")
        setup = f"cat > {src} <<'EOF'\n#include <stdio.h>\nint {fname}(int x);\nint main(){{ printf(\"%d\\\\n\", {fname}(5)); return 0; }}\nEOF"
        add(tasks, base, f"gcc -Wall -o {files}/gcc_link_{i} {files}/gcc_link_{i}.c", "compilation", setup=setup)

    for i in range(5):
        d = os.path.join(files, f"make_ok_{i}")
        setup = (f"mkdir -p {d} && cat > {d}/main.c <<'EOF'\n#include <stdio.h>\nint main(){{ printf(\"build {i} ready\\\\n\"); return 0; }}\nEOF\n"
                 f"cat > {d}/Makefile <<'EOF'\nall: prog_{i}\nprog_{i}: main.c\n\tgcc -o prog_{i} main.c\nEOF")
        add(tasks, base, "make", "compilation", workdir=d, setup=setup)
    for i in range(3):
        d = os.path.join(files, f"make_miss_{i}")
        setup = f"mkdir -p {d} && printf 'all: prog\\nprog: missing_{i}.c\\n\\tgcc -o prog missing_{i}.c\\n' > {d}/Makefile"
        add(tasks, base, "make", "compilation", workdir=d, setup=setup)

    py_ok = [
        "print(sum(range(20)))",
        "d = {'x':10,'y':20}\nprint(sorted(d.items()))",
        "import math\nprint(round(math.pi, 3))",
    ]
    for i in range(6):
        body = py_ok[i % len(py_ok)]
        src = os.path.join(files, f"py_ok_{i}.py")
        setup = f"cat > {src} <<'PYEOF'\n{body}\nPYEOF"
        add(tasks, base, f"python3 {files}/py_ok_{i}.py", "compilation", setup=setup)

    py_bad = [
        "x = 10 / 0",
        "d = {'a': 1}\nprint(d['z'])",
        "print(3 + 'text')",
        "import package_missing_corpus",
        "print(never_defined_variable)",
    ]
    for i in range(6):
        body = py_bad[i % len(py_bad)]
        src = os.path.join(files, f"py_bad_{i}.py")
        setup = f"cat > {src} <<'PYEOF'\n{body}\nPYEOF"
        add(tasks, base, f"python3 {files}/py_bad_{i}.py", "compilation", setup=setup)

    for i in range(3):
        d = os.path.join(proj, f"npm_fail_{i}")
        setup = (f"mkdir -p {d} && cat > {d}/package.json <<'EOF'\n"
                 f'{{"name":"proj{i}","version":"1.0.0","scripts":{{"build":"node build.js"}}}}\n'
                 f"EOF\ncat > {d}/build.js <<'EOF'\nrequire('module-missing-{i}');\nEOF")
        add(tasks, base, "npm run build", "compilation", workdir=d, setup=setup, timeout=30)
    for i in range(3):
        d = os.path.join(proj, f"npm_ok_{i}")
        setup = (f"mkdir -p {d} && cat > {d}/package.json <<'EOF'\n"
                 f'{{"name":"proj{i}b","version":"1.0.0","scripts":{{"build":"node build.js"}}}}\n'
                 f"EOF\ncat > {d}/build.js <<'EOF'\nconsole.log('build {i} finished');\nEOF")
        add(tasks, base, "npm run build", "compilation", workdir=d, setup=setup, timeout=30)

    # packages: read-only inspection instead of real installs (no apt install)
    for cmd in ["apt list --installed 2>/dev/null | head -20", "apt-cache policy git",
                "apt-cache policy python3", "dpkg -s git", "dpkg -s coreutils"]:
        add(tasks, base, cmd, "packages", timeout=20)
    for pkg in ["nonexistent-package-corpus-1", "fake-formula-corpus-2", "steph-fake-formula-3"]:
        add(tasks, base, f"apt-cache policy {pkg}", "packages", timeout=15)
        add(tasks, base, f"dpkg -s {pkg}", "packages", timeout=15)

    add(tasks, base, f"python3 -m venv {base}/venv", "packages", timeout=30)
    for pkg in ["requests", "six", "attrs", "click", "colorama"]:
        add(tasks, base, f"{base}/venv/bin/pip install {pkg}", "packages", timeout=30)
    for pkg in ["nonexistent-python-package-abc", "steph-fake-pypackage-low"]:
        add(tasks, base, f"{base}/venv/bin/pip install {pkg}", "packages", timeout=25)
    add(tasks, base, f"{base}/venv/bin/pip install requests==999.999.999", "packages", timeout=25)

    for i, pkg in enumerate(["is-odd", "ms", "kleur", "nanoid"]):
        d = os.path.join(proj, f"npminst_ok_{i}")
        setup = f"mkdir -p {d} && cd {d} && npm init -y >/dev/null 2>&1"
        add(tasks, base, f"npm install {pkg}", "packages", workdir=d, setup=setup, timeout=30)
    for i, pkg in enumerate(["nonexistent-package-totally-abc", "this-module-does-not-exist-123"]):
        d = os.path.join(proj, f"npminst_bad_{i}")
        setup = f"mkdir -p {d} && cd {d} && npm init -y >/dev/null 2>&1"
        add(tasks, base, f"npm install {pkg}", "packages", workdir=d, setup=setup, timeout=30)

    # git
    for i in range(6):
        d = os.path.join(repos, f"repo_basic_{i}")
        setup = (f"{git_repo_setup(d)} && echo 'content {i}' > file{i}.txt && {GIT_ENV} -C {d} add file{i}.txt "
                 f"&& {GIT_ENV} -C {d} commit -q -m 'add file{i}' "
                 f"&& echo 'draft {i}' > new_{i}.txt && echo 'change {i}' >> file{i}.txt")
        add(tasks, base, f"{GIT_ENV} status", "git", workdir=d, setup=setup)
        add(tasks, base, f"{GIT_ENV} log --oneline", "git", workdir=d)
        add(tasks, base, f"{GIT_ENV} show --stat HEAD", "git", workdir=d)
    for i in range(3):
        d = os.path.join(repos, f"repo_empty_{i}")
        setup = git_repo_setup(d)
        add(tasks, base, f"{GIT_ENV} log", "git", workdir=d, setup=setup)
        add(tasks, base, f"{GIT_ENV} commit -m 'nothing to commit'", "git", workdir=d)
    for i in range(3):
        d = os.path.join(repos, f"repo_branch_{i}")
        setup = f"{git_repo_setup(d)} && echo init > a.txt && {GIT_ENV} -C {d} add a.txt && {GIT_ENV} -C {d} commit -q -m init"
        add(tasks, base, f"{GIT_ENV} checkout nonexistent-branch-{i}", "git", workdir=d, setup=setup)
    for i in range(3):
        d = os.path.join(repos, f"repo_merge_{i}")
        setup = (f"{git_repo_setup(d)} && echo v1 > f{i}.txt && {GIT_ENV} -C {d} add f{i}.txt && {GIT_ENV} -C {d} commit -q -m v1 "
                 f"&& {GIT_ENV} -C {d} checkout -q -b branch-a-{i} && echo v2a-{i} > f{i}.txt && {GIT_ENV} -C {d} commit -q -am v2a "
                 f"&& {GIT_ENV} -C {d} checkout -q master && echo v2b-{i} > f{i}.txt && {GIT_ENV} -C {d} commit -q -am v2b")
        add(tasks, base, f"{GIT_ENV} merge branch-a-{i}", "git", workdir=d, setup=setup)
    for i in range(2):
        d = os.path.join(repos, f"repo_push_{i}")
        setup = (f"{git_repo_setup(d)} && echo x > f.txt && {GIT_ENV} -C {d} add f.txt && {GIT_ENV} -C {d} commit -q -m x "
                 f"&& {GIT_ENV} -C {d} remote add origin https://remote-low-{i}.invalid/project.git")
        add(tasks, base, f"{GIT_ENV} push origin master", "git", workdir=d, setup=setup, timeout=15)
    for i in range(2):
        d = os.path.join(repos, f"repo_clone_{i}")
        add(tasks, base, f"{GIT_ENV} clone {base}/repos/does-not-exist-{i} {d}", "git", timeout=15)
    for i in range(2):
        d = os.path.join(repos, f"repo_diff_{i}")
        setup = (f"{git_repo_setup(d)} && printf 'line 1\\nline 2\\nline 3\\n' > data{i}.txt "
                 f"&& {GIT_ENV} -C {d} add data{i}.txt && {GIT_ENV} -C {d} commit -q -m 'initial version' "
                 f"&& printf 'line 1\\nline changed {i}\\nline 3\\nline added {i}\\n' > data{i}.txt")
        add(tasks, base, f"{GIT_ENV} diff", "git", workdir=d, setup=setup)

    # files (confined to the sandbox and read-only elsewhere)
    for i in range(6):
        d = os.path.join(files, f"tree_{i}")
        n = 2 + (i % 4)
        setup = f"mkdir -p {d}/a {d}/b && " + " && ".join(f"echo doc{i}_{j} > {d}/a/doc{j}.txt" for j in range(n))
        add(tasks, base, f"ls -la {files}/tree_{i}/a", "files", setup=setup)
    for i in range(8):
        add(tasks, base, f"ls -la {base}/missing_path_{i}", "files")
    for i in range(4):
        d = os.path.join(files, f"private_{i}")
        setup = f"mkdir -p {d} && touch {d}/secret.txt && chmod 000 {d}"
        add(tasks, base, f"ls -la {files}/private_{i}", "files", setup=setup)
    for sub in ["/usr/bin", "/proc/cpuinfo", "/sys/class/net"]:
        for n in (10, 25):
            add(tasks, base, f"ls -la {sub} | head -{n}", "files")

    for i in range(6):
        d = os.path.join(files, f"found_{i}")
        n = 2 + (i % 3)
        setup = f"mkdir -p {d}/sub && " + " && ".join(f"echo r{i}_{j} > {d}/sub/report{j}.txt" for j in range(n))
        add(tasks, base, f"find {files}/found_{i} -name '*.txt'", "files", setup=setup)
    for i in range(6):
        add(tasks, base, f"find {base}/absent_{i} -maxdepth 2", "files")

    for i, size in enumerate(["10K", "500K", "1K"]):
        d = os.path.join(files, f"size_{i}")
        setup = f"mkdir -p {d} && dd if=/dev/urandom of={d}/blob.bin bs=1024 count=1 2>/dev/null && truncate -s {size} {d}/blob.bin"
        add(tasks, base, f"du -sh {files}/size_{i}", "files", setup=setup)

    for i in range(8):
        d = os.path.join(files, f"cat_ok_{i}")
        setup = f"mkdir -p {d} && printf 'line one\\nline two\\nindex={i}\\n' > {d}/notes.txt"
        add(tasks, base, f"cat {files}/cat_ok_{i}/notes.txt", "files", setup=setup)
    for i in range(6):
        add(tasks, base, f"cat {files}/cat_absent_{i}.txt", "files")

    for i in range(6):
        src = os.path.join(files, f"cp_src_{i}.txt")
        setup = f"echo content{i} > {src}"
        add(tasks, base, f"cp {files}/cp_src_{i}.txt {files}/cp_dst_{i}.txt", "files", setup=setup)
    for i in range(4):
        src = os.path.join(files, f"mv_src_{i}.txt")
        setup = f"echo mv{i} > {src}"
        add(tasks, base, f"mv {files}/mv_src_{i}.txt {files}/mv_dst_{i}.txt", "files", setup=setup)

    for i in range(6):
        d = os.path.join(files, f"tar_ok_{i}")
        setup = f"mkdir -p {d} && echo data{i} > {d}/a.txt && echo data{i} > {d}/b.txt"
        add(tasks, base, f"tar czf {files}/tar_ok_{i}.tgz -C {files} tar_ok_{i}", "files", setup=setup)
    for i in range(3):
        f = os.path.join(files, f"tar_bad_{i}.tgz")
        setup = f"head -c 200 /dev/urandom > {f}"
        add(tasks, base, f"tar xzf {files}/tar_bad_{i}.tgz -C {files}", "files", setup=setup)

    # network (read-only)
    for cmd in ["ip a", "ip -br a", "ip route", "ip link"]:
        add(tasks, base, cmd, "network")
    for cmd in ["ss -tulpn", "ss -s"]:
        add(tasks, base, cmd, "network", timeout=10)
    for _ in range(4):
        add(tasks, base, "ping -c 2 localhost", "network", timeout=10)
    for _ in range(4):
        add(tasks, base, "ping -c 2 127.0.0.1", "network", timeout=10)
    for ip in ["10.255.255.1", "10.255.255.2", "192.168.99.99", "192.168.99.98"]:
        add(tasks, base, f"ping -c 2 -W 1 {ip}", "network", timeout=10)
    for dom in [f"missing-host-low-{i}.invalid" for i in range(6)]:
        add(tasks, base, f"curl -sS --max-time 3 http://{dom}/", "network", timeout=8)
    for port in [9999, 9998, 9997]:
        add(tasks, base, f"curl -sS --max-time 3 http://127.0.0.1:{port}/", "network", timeout=8)
    for _ in range(3):
        add(tasks, base, "curl -sS --max-time 5 http://example.com/", "network", timeout=8)
    for _ in range(3):
        add(tasks, base, "dig +time=2 +tries=1 example.com", "network", timeout=8)
    for dom in [f"absent-dns-low-{i}.invalid" for i in range(4)]:
        add(tasks, base, f"dig +time=2 +tries=1 {dom}", "network", timeout=8)

    # system (strictly read-only)
    for cmd in ["free -h", "free -m", "free -g", "free"]:
        add(tasks, base, cmd, "system")
    for cmd in ["uptime", "uptime -p"]:
        add(tasks, base, cmd, "system")
    for cmd in ["df -h", "df -i", "df -k"]:
        add(tasks, base, cmd, "system")
    for cmd in ["lscpu", "lscpu -e"]:
        add(tasks, base, cmd, "system")
    for cmd in ["lspci", "lspci -k", "lspci -nn"]:
        add(tasks, base, cmd, "system", timeout=15)
    for svc in ["ssh", "cron", "docker", "cups", "nonexistent-service-low"]:
        add(tasks, base, f"systemctl status {svc} --no-pager", "system", timeout=10)
    for cmd in ["journalctl -n 20 --no-pager", "journalctl -p err -n 20 --no-pager", "journalctl -k -n 15 --no-pager"]:
        add(tasks, base, cmd, "system", timeout=15)
    for cmd in ["ps aux | head -20", "ps -ef | head -20", "ps aux --sort=-%mem | head -15"]:
        add(tasks, base, cmd, "system")

    # containers: read-only introspection only, never run/pull/stop
    for cmd in ["docker ps", "docker ps -a", "docker images", "docker version", "docker info | head -25"]:
        add(tasks, base, cmd, "containers", timeout=15)
    for i in range(3):
        add(tasks, base, f"docker inspect nonexistent-container-{i}", "containers", timeout=10)
    for i in range(2):
        add(tasks, base, f"docker logs missing-container-{i}", "containers", timeout=10)

    # interactive
    prompts = ["Name", "Age", "City", "Confirm (y/n)", "Password", "Continue", "Choice"]
    for i in range(8):
        p = prompts[i % len(prompts)]
        add(tasks, base, f"python3 -c \"x=input('{p} {i}: '); print(x)\"", "interactive", timeout=10)
    for i in range(6):
        p = prompts[i % len(prompts)]
        add(tasks, base, f"bash -c 'read -p \"{p} {i} : \" rep; echo answer=$rep'", "interactive", timeout=10)
    for i in range(3):
        d = os.path.join(repos, f"repo_edit_{i}")
        setup = git_repo_setup(d) + f" && echo x{i} > f.txt && {GIT_ENV} -C {d} add f.txt"
        add(tasks, base, f"EDITOR=false {GIT_ENV} commit", "interactive", workdir=d, setup=setup, timeout=10)
    for i in range(4):
        add(tasks, base, "python3 -c \"import sys; x=input(); sys.exit(0 if x else 1)\"", "interactive", timeout=10)

    return tasks


PROFILE_BUILDERS = {
    "macos": _tasks_macos,
    "linux-dev": _tasks_linux_dev,
    "linux-low": _tasks_linux_low,
}


def build_tasks(profile: str, base: str) -> list[dict]:
    try:
        builder = PROFILE_BUILDERS[profile]
    except KeyError:
        raise ValueError(f"unknown profile: {profile!r} (expected one of {sorted(PROFILE_BUILDERS)})") from None
    return builder(base)


# ================= execution =================

def run_task(task: dict, machine: str, lang: str, max_len: int = 20000) -> dict:
    cmd, workdir, setup, timeout = task["cmd"], task["workdir"], task.get("setup"), task.get("timeout", 20)
    env = locale_env(lang)
    os.makedirs(workdir, exist_ok=True)
    if setup:
        subprocess.run(setup, shell=True, cwd=workdir, executable="/bin/bash", env=env,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        stdin=subprocess.DEVNULL, timeout=120)
    start = time.perf_counter()
    try:
        p = subprocess.run(cmd, shell=True, cwd=workdir, executable="/bin/bash", env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            stdin=subprocess.DEVNULL, timeout=timeout)
        exit_code = p.returncode
        out = p.stdout.decode("utf-8", errors="replace")
    except subprocess.TimeoutExpired as e:
        exit_code = 124
        raw = e.stdout or b""
        if isinstance(raw, str):
            raw = raw.encode()
        out = raw.decode("utf-8", errors="replace") + f"\n[timeout after {timeout}s]"
    except Exception as e:  # noqa: BLE001 - one failed task must not stop the capture
        exit_code = -1
        out = f"runner error: {e}"
    duration = round(time.perf_counter() - start, 3)
    if len(out) > max_len:
        out = out[:max_len]
    return {"cmd": cmd, "exit": exit_code, "duration": duration, "output": out,
            "machine": machine, "category": task["category"]}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--profile", required=True, choices=sorted(PROFILE_BUILDERS))
    ap.add_argument("--lang", default="fr", choices=["fr", "en"])
    ap.add_argument("--base", required=True, help="sandbox directory for setup files and generated projects")
    ap.add_argument("--out", required=True, help="output jsonl (appended, resumable)")
    ap.add_argument("--machine", help="machine label written in each record (defaults to --profile)")
    args = ap.parse_args()

    base = os.path.abspath(args.base)
    for sub in ("files", "repos", "proj", "tools"):
        os.makedirs(os.path.join(base, sub), exist_ok=True)

    machine = args.machine or args.profile
    tasks = build_tasks(args.profile, base)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    done = 0
    if out_path.exists():
        with open(out_path, encoding="utf-8") as f:
            done = sum(1 for _ in f)
    print(f"{len(tasks)} tasks generated, {done} already done", file=sys.stderr)

    with open(out_path, "a", encoding="utf-8") as out:
        for i, task in enumerate(tasks):
            if i < done:
                continue
            record = run_task(task, machine, args.lang)
            out.write(json.dumps(record, ensure_ascii=False) + "\n")
            out.flush()
            if i % 25 == 0:
                print(f"{i}/{len(tasks)}", file=sys.stderr)
    print(f"done {len(tasks)}/{len(tasks)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
