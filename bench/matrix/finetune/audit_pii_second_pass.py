#!/usr/bin/env python3
"""Second, independent PII pass on the publishable fine-tuning release (I2).

    python3 audit_pii_second_pass.py release-v0/sft/*.jsonl [--names FICHIER] [--details]

`audit_pii.py` already scans the corpus for MAC/UUID/IP/e-mail/secret/known-name
patterns; this script is a deliberately separate second opinion, with its own patterns
and its own blind spots, on the exact files about to be published (not the labeling
intermediates). It targets what the first pass structurally cannot catch: unknown
capitalized proper nouns (the first pass only matches a fixed name list), hostnames
spelled out in a shell prompt or `hostnamectl` field, obfuscated e-mails, vendor API-key
shapes (GitHub, AWS, Slack, OpenAI, npm, JWT, SSH public keys), and serial/IMEI-style
identifiers from tools `audit_pii.py` does not special-case.

Never prints a found value, only its kind, file and line - same convention as
`audit_pii.py`. Exit code: 0 clean, 1 findings, 2 name list not found.

SPDX-License-Identifier: MIT
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import re
import sys

DEFAULT_NAMES = os.path.expanduser("~/.config/steph/pii_names.tsv")

# Command/tool/format vocabulary capitalized in normal terminal output: excluded from the
# "unknown proper noun" heuristic so it does not drown in its own false positives.
_COMMON_CAPITALIZED = {
    "Linux", "Darwin", "MacOS", "Windows", "Docker", "Python", "Git", "GitHub", "GitLab",
    "Node", "NPM", "Rust", "Cargo", "Go", "Java", "Ruby", "PHP", "SQL", "JSON", "YAML",
    "XML", "HTML", "CSS", "HTTP", "HTTPS", "TCP", "UDP", "SSH", "TLS", "SSL", "URL", "URI",
    "API", "CPU", "GPU", "RAM", "SSD", "HDD", "USB", "PCI", "PCIe", "SATA", "WiFi", "VPN",
    "LAN", "DNS", "DHCP", "IPv4", "IPv6", "OK", "ID", "UUID", "MAC", "GB", "MB", "KB", "TB",
    "Ubuntu", "Debian", "Fedora", "Arch", "Homebrew", "Xcode", "VSCode", "Vim", "Emacs",
    "Kubernetes", "Terraform", "Ansible", "Jenkins", "Postgres", "PostgreSQL", "MySQL",
    "SQLite", "Redis", "MongoDB", "Nginx", "Apache", "Systemd", "Cron", "Bash", "Zsh",
    "Makefile", "README", "LICENSE", "TODO", "FIXME", "NOTE", "WARNING", "ERROR", "INFO",
    "DEBUG", "TRACE", "FATAL", "PASS", "FAIL", "Succes", "Echec", "Commande", "Statut",
    "Duree", "Sortie", "Command", "Status", "Duration", "Output", "Historique", "Question",
    "Reponse", "Compris", "January", "February", "March", "April", "May", "June", "July",
    "August", "September", "October", "November", "December", "Monday", "Tuesday",
    "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
}

RULES = {
    # Two or three Title-Case words in a row, not sentence-initial (preceded by
    # lowercase/punctuation, never by a line start): the shape of a real proper noun the
    # fixed name list in audit_pii.py does not know about.
    "unknown_proper_noun": re.compile(r"(?<=[a-z,;:] )([A-Z][a-z]{2,}(?:[ -][A-Z][a-z]{2,}){0,2})\b"),
    # user@host / root@host style prompts baked into captured shell output.
    "shell_prompt_host": re.compile(r"\b(?:[a-z_][a-z0-9_-]*@)([a-zA-Z0-9][a-zA-Z0-9-]{1,61})(?=[:#$ ])"),
    "hostnamectl_field": re.compile(r"(?m)^\s*(?:Static|Pretty|Transient) hostname:\s*(\S+)"),
    # Obfuscated addresses ("user [at] domain [dot] com", "user(at)domain(dot)com").
    "email_obfuscated": re.compile(
        r"[A-Za-z0-9._%+-]+\s*[\[(]\s*at\s*[\])]\s*[A-Za-z0-9.-]+\s*[\[(]\s*dot\s*[\])]\s*[A-Za-z]{2,}", re.IGNORECASE),
    "github_token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,255}\b"),
    "aws_access_key": re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    "slack_token": re.compile(r"\bxox[baprs]-[0-9A-Za-z-]{10,72}\b"),
    "openai_key": re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
    "npm_token": re.compile(r"\bnpm_[A-Za-z0-9]{36}\b"),
    "jwt": re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
    "ssh_public_key": re.compile(r"\b(?:ssh-(?:rsa|ed25519|dss)|ecdsa-sha2-nistp256)\s+[A-Za-z0-9+/]{40,}={0,2}"),
    # dmidecode / lsblk / smartctl serial fields, and IMEI (15 digits, Luhn-checkable but
    # a plain length+prefix match is enough for a PII net, no false negative tolerated).
    "serial_field": re.compile(r"(?im)^\s*(?:Serial\s*(?:Number|No\.?|#)?|S/N)\s*[:=]\s*(\S+)"),
    "imei": re.compile(r"\b\d{15}\b"),
    # /home or /Users paths the first pass's narrower regex could miss inside a longer
    # path (e.g. quoted, or followed by a colon as in PATH=... or a Windows profile path).
    "home_path_broad": re.compile(r"(?:/home/|/Users/|C:\\Users\\)([A-Za-z0-9._-]+)"),
}

_SAFE_HOSTS = {"localhost", "machine", "machine-demo", "mac-demo", "host", "example.com"}


def load_names(path: str) -> set[str]:
    terms = set()
    with open(path, encoding="utf-8") as handle:
        for raw in handle:
            raw = raw.rstrip("\n")
            if not raw.strip() or raw.lstrip().startswith("#"):
                continue
            term = raw.split("\t")[0].strip()
            if term:
                terms.add(term)
    return terms


def scan_text(text: str, known_names: set[str]) -> list[str]:
    found = []

    for m in RULES["unknown_proper_noun"].finditer(text):
        phrase = m.group(1)
        words = phrase.split()
        if all(w in _COMMON_CAPITALIZED for w in words):
            continue
        if phrase in known_names or any(w in known_names for w in words):
            continue
        found.append("unknown_proper_noun")

    for m in RULES["shell_prompt_host"].finditer(text):
        host = m.group(1)
        if host.lower() in _SAFE_HOSTS or host in ("user", "root"):
            continue
        found.append("shell_prompt_host")

    for m in RULES["hostnamectl_field"].finditer(text):
        if m.group(1).lower() not in _SAFE_HOSTS:
            found.append("hostname")

    for m in RULES["home_path_broad"].finditer(text):
        if m.group(1) not in ("user", "root"):
            found.append("home_path")

    for kind in ("email_obfuscated", "github_token", "aws_access_key", "slack_token",
                "openai_key", "npm_token", "jwt", "ssh_public_key"):
        for _ in RULES[kind].finditer(text):
            found.append(kind)

    for m in RULES["serial_field"].finditer(text):
        value = m.group(1)
        if set(value) - {"0", "-", ":"}:
            found.append("serial_number")

    for m in RULES["imei"].finditer(text):
        if len(set(m.group(0))) > 1:  # exclude placeholder runs like 000000000000000
            found.append("imei_like")

    return found


def row_texts(record: dict) -> list[str]:
    texts = [v for v in record.values() if isinstance(v, str)]
    for m in record.get("messages", []):
        if isinstance(m, dict) and isinstance(m.get("content"), str):
            texts.append(m["content"])
    for m in record.get("prompt", []):
        if isinstance(m, dict) and isinstance(m.get("content"), str):
            texts.append(m["content"])
    for key in ("chosen", "rejected"):
        if isinstance(record.get(key), str):
            texts.append(record[key])
    return texts


def scan_file(path: str, known_names: set[str]) -> tuple[collections.Counter, dict[str, list[int]]]:
    per_type: collections.Counter = collections.Counter()
    locations: dict[str, list[int]] = collections.defaultdict(list)
    with open(path, encoding="utf-8") as handle:
        for lineno, raw in enumerate(handle, 1):
            if not raw.strip():
                continue
            try:
                record = json.loads(raw)
            except json.JSONDecodeError:
                per_type["invalid_json"] += 1
                locations["invalid_json"].append(lineno)
                continue
            for kind in scan_text("\n".join(row_texts(record)), known_names):
                per_type[kind] += 1
                if lineno not in locations[kind]:
                    locations[kind].append(lineno)
    return per_type, locations


def main() -> int:
    parser = argparse.ArgumentParser(description="Deuxième audit PII, indépendant de audit_pii.py (n'affiche jamais les valeurs).")
    parser.add_argument("files", nargs="+")
    parser.add_argument("--names", default=os.environ.get("STEPH_PII_NAMES", DEFAULT_NAMES))
    parser.add_argument("--details", action="store_true", help="liste fichier:ligne par type")
    args = parser.parse_args()

    if not os.path.exists(args.names):
        print(f"liste de noms introuvable : {args.names} (voir STEPH_PII_NAMES)", file=sys.stderr)
        return 2
    known_names = load_names(args.names)

    total = 0
    for path in args.files:
        per_type, locations = scan_file(path, known_names)
        count = sum(per_type.values())
        total += count
        print(f"{path} : {count} trouvaille(s)")
        for kind, n in sorted(per_type.items(), key=lambda kv: (-kv[1], kv[0])):
            lines = locations[kind]
            print(f"  {kind:<20} {n:>6}  lignes : {len(lines)}")
            if args.details:
                print("    " + ", ".join(f"{os.path.basename(path)}:{ln}" for ln in lines))
    print(f"TOTAL : {total}")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
