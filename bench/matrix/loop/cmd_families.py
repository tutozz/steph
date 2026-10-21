#!/usr/bin/env python3
"""Familles de commandes d'un banc ou d'un mix d'entraînement, en comptes seulement.

Aucun contenu n'est imprimé : seules les familles et leurs effectifs sortent, pour que le
script tourne là où vit le corpus personnel sans rien en déplacer.

    python3 cmd_families.py bench <cases.json>
    python3 cmd_families.py speak <benchmark/data/v1>
    python3 cmd_families.py mix <train.jsonl> [<val.jsonl> ...]
"""

import json
import re
import sys
from collections import Counter
from pathlib import Path

WRAPPERS = {"sudo", "env", "time", "nice", "ionice", "doas", "exec", "nohup", "timeout", "watch", "stdbuf"}

FAMILIES = [
    ("tests", r"^(pytest|jest|vitest|mocha|tox|nox|ctest|phpunit|rspec|bats)$"),
    ("containers", r"^(docker|docker-compose|podman|kubectl|k9s|helm|minikube|kind|crictl|nerdctl|lxc|incus)$"),
    ("systemd-logs", r"^(systemctl|journalctl|dmesg|service|loginctl|coredumpctl|rc-service)$"),
    ("git-vcs", r"^(git|gh|hg|svn|glab)$"),
    ("packages", r"^(apt|apt-get|dpkg|dnf|yum|rpm|pacman|yay|zypper|brew|snap|flatpak|pip|pip3|pipx|uv|poetry|conda|gem|composer|apk|nix|nix-env)$"),
    ("build-compile", r"^(make|cmake|ninja|gcc|g\+\+|cc|clang|clang\+\+|rustc|javac|mvn|gradle|gradlew|tsc|go|meson|bazel|dotnet|msbuild|swift|swiftc|xcodebuild|scons|webpack|vite|esbuild)$"),
    ("js-runtime", r"^(npm|pnpm|yarn|node|npx|bun|deno)$"),
    ("rust-cargo", r"^(cargo|rustup)$"),
    ("python-run", r"^(python|python2|python3|ipython)$"),
    ("disk-mem", r"^(df|du|free|lsblk|mount|findmnt|ncdu|vmstat|iostat|swapon|fdisk|parted|zpool|zfs|smartctl|btrfs)$"),
    ("net", r"^(ping|ping6|curl|wget|ip|ifconfig|ss|netstat|dig|nslookup|host|traceroute|tracepath|mtr|nmap|nc|ncat|ssh|scp|rsync|sftp|iw|iwconfig|nmcli|ethtool|tcpdump|resolvectl|arp|route|telnet|http)$"),
    ("process", r"^(ps|top|htop|btop|kill|killall|pkill|pgrep|pstree|lsof|nproc|uptime|jobs|fuser)$"),
    ("listing-find", r"^(ls|ll|la|exa|eza|tree|find|fd|locate|stat|file|realpath|readlink|basename|dirname|pwd)$"),
    ("text-tools", r"^(cat|less|more|head|tail|grep|egrep|rg|ag|ack|sort|uniq|cut|wc|sed|awk|tr|diff|cmp|jq|yq|xargs|tee|echo|printf|column|nl|bat)$"),
    ("file-ops", r"^(rm|cp|mv|mkdir|rmdir|touch|chmod|chown|chgrp|ln|install|shred|truncate)$"),
    ("archives", r"^(tar|zip|unzip|gzip|gunzip|xz|unxz|bzip2|7z|zstd|unrar)$"),
    ("sysinfo", r"^(uname|whoami|id|hostname|hostnamectl|lspci|lsusb|lscpu|lsmod|modprobe|sensors|dmidecode|inxi|neofetch|fastfetch|sw_vers|scutil|timedatectl|date|locale|groups|who|w|last|nvidia-smi|lshw|hwinfo)$"),
    ("db", r"^(psql|mysql|mariadb|sqlite3|redis-cli|mongo|mongosh|pg_dump|mysqldump)$"),
    ("infra-cloud", r"^(terraform|tofu|ansible|ansible-playbook|aws|gcloud|az|pulumi|vagrant|packer|qm|pct|virsh|proxmox-backup-client)$"),
    ("security-users", r"^(passwd|useradd|usermod|userdel|chpasswd|ufw|iptables|nft|firewall-cmd|fail2ban-client|gpg|openssl|ssh-keygen|certbot|visudo|su)$"),
    ("shell-scripts", r"^(bash|sh|zsh|fish|source|\.|\./\S+|\S+\.sh)$"),
]
COMPILED = [(name, re.compile(rx)) for name, rx in FAMILIES]
PY_MODULES = {"pytest": "tests", "unittest": "tests", "pip": "packages", "venv": "python-run", "http.server": "net"}


def primary(cmd: str) -> list:
    first = re.split(r"\|\||&&|;|\|", cmd.strip(), maxsplit=1)[0]
    toks = [t for t in first.split() if not re.match(r"^[A-Z_][A-Z0-9_]*=", t)]
    while toks and toks[0] in WRAPPERS:
        toks = toks[1:]
        while toks and toks[0].startswith("-"):
            toks = toks[1:]
    return toks


def family(cmd: str) -> str:
    toks = primary(cmd)
    if not toks:
        return "empty"
    head = toks[0].rsplit("/", 1)[-1] if not toks[0].startswith("./") else toks[0]
    sub = toks[1] if len(toks) > 1 else ""
    if head in ("python", "python3", "python2") and sub == "-m" and len(toks) > 2:
        return PY_MODULES.get(toks[2], "python-run")
    if head in ("npm", "pnpm", "yarn", "bun"):
        if sub in ("test", "t") or (sub == "run" and len(toks) > 2 and "test" in toks[2]):
            return "tests"
        if sub in ("install", "i", "add", "ci", "update", "outdated", "audit", "remove", "uninstall"):
            return "packages"
        if sub == "build" or (sub == "run" and len(toks) > 2 and "build" in toks[2]):
            return "build-compile"
        return "js-runtime"
    if head == "cargo":
        return {"test": "tests", "build": "build-compile", "check": "build-compile", "clippy": "build-compile",
                "install": "packages", "add": "packages", "update": "packages"}.get(sub, "rust-cargo")
    if head == "go":
        return {"test": "tests", "get": "packages", "mod": "packages"}.get(sub, "build-compile")
    if head in ("docker", "podman") and sub in ("compose",):
        return "containers"
    for name, rx in COMPILED:
        if rx.match(head):
            return name
    return "other"


CMD_LINE = re.compile(r"^(?:Commande|Command|Befehl|Comando|Команда)\s*:\s*(.+)$", re.M)


def from_bench(path):
    c = Counter()
    for case in json.load(open(path)):
        if case.get("kind") == "qa":
            c["qa (" + family(case.get("cmd") or _user_cmd(case)) + ")"] += 1
        else:
            c[family(case.get("cmd") or _user_cmd(case))] += 1
    return c


def _user_cmd(case):
    user = [m for m in case["messages"] if m["role"] == "user"][0]["content"]
    m = CMD_LINE.findall(user)
    return m[-1] if m else ""


def from_speak(root):
    by = {}
    for lang_dir in sorted(Path(root).iterdir()):
        if not lang_dir.is_dir():
            continue
        for split in ("dev", "test"):
            f = lang_dir / f"{split}.jsonl"
            if not f.exists():
                continue
            c = by.setdefault(f"{lang_dir.name}/{split}", Counter())
            for line in open(f):
                c[family(json.loads(line).get("cmd", ""))] += 1
    return by


def from_mix(paths):
    fam, src = Counter(), Counter()
    fam_by_src = {}
    for p in paths:
        for line in open(p):
            d = json.loads(line)
            user = [m for m in d.get("messages", []) if m["role"] == "user"]
            cmds = CMD_LINE.findall(user[0]["content"]) if user else []
            f = family(cmds[-1]) if cmds else "no-command"
            s = str(d.get("source", "?"))
            fam[f] += 1
            src[s] += 1
            fam_by_src.setdefault(s, Counter())[f] += 1
    return {"families": dict(fam.most_common()), "sources": dict(src.most_common()),
            "families_by_source": {k: dict(v.most_common()) for k, v in fam_by_src.items()}}


def main():
    mode, args = sys.argv[1], sys.argv[2:]
    if mode == "bench":
        out = dict(from_bench(args[0]).most_common())
    elif mode == "speak":
        out = {k: dict(v.most_common()) for k, v in from_speak(args[0]).items()}
    elif mode == "mix":
        out = from_mix(args)
    else:
        raise SystemExit("mode : bench, speak ou mix")
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
