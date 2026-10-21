#!/usr/bin/env python3
"""Seconde passe d'anonymisation du corpus d'affinage steph.

Usage :  python3 clean_pii.py ENTREE.jsonl SORTIE.jsonl [--names FICHIER]

Complète le masquage d'origine sur ce qu'audit_pii.py y trouve. Les termes
connus et leurs remplacements viennent de ~/.config/steph/pii_names.tsv (hors
dépôt). Les remplacements gardent la largeur d'origine quand une colonne en
dépend. Sortie : une ligne JSON par enregistrement conservé.

SPDX-License-Identifier: MIT
"""

import argparse
import collections
import ipaddress
import json
import os
import re
import sys

from audit_pii import (
    ALLOWED_192_168_THIRD_OCTET, ALLOWED_EMAIL_DOMAINS, DEFAULT_NAMES, DOC_V4, RULES,
    UNIT_SUFFIXES, ipv6_problem, is_placeholder_hex,
)

# Le masquage d'origine a remplacé un nom de projet de 9 caractères par « app »
# sans compenser la largeur : les tableaux docker se décalaient de 6 colonnes.
APP_TOKEN = re.compile(
    r"(?<![\w.])app(?=[-_](?:api|frontend|client|bundletest|nginx|vault|admin|db|app_network|postgres_data)(?![a-z])"
    r"|/docker-compose|  +(?:restarting|running))")
APP_REPLACEMENT = "portalapp"
# Il a aussi pris le nom de chiffrement OpenSSH pour une adresse e-mail.
OVERMASKED_CIPHER = re.compile(r"cipher=user@example\.invalid( ksize=512)")
NM_CERT = re.compile(r"(/run/NetworkManager/cert/)[A-Za-z0-9]{6}\b")


def load_map(path):
    pairs = []
    with open(path, encoding="utf-8") as handle:
        for raw in handle:
            raw = raw.rstrip("\n")
            if not raw.strip() or raw.lstrip().startswith("#"):
                continue
            parts = raw.split("\t")
            term = parts[0].strip()
            repl = parts[1].strip() if len(parts) > 1 and parts[1].strip() else "redacted"
            pairs.append((term, repl))
    pairs.sort(key=lambda p: -len(p[0]))
    return [(re.compile(r"(?<![A-Za-z0-9])" + re.escape(t) + r"(?![A-Za-z0-9])", re.IGNORECASE), r) for t, r in pairs]


def match_case(original, repl):
    if original.isupper():
        return repl.upper()
    if original[:1].isupper():
        return repl[:1].upper() + repl[1:]
    return repl


def zero_like(value, counter):
    """Même forme, chiffres hexadécimaux à zéro, compteur dans les derniers."""
    tail = format(counter, "x")
    chars = [c if not c.isalnum() else "0" for c in value]
    positions = [i for i, c in enumerate(value) if c.isalnum()]
    for i, digit in zip(reversed(positions), reversed(tail)):
        chars[i] = digit
    return "".join(chars)


class Cleaner:
    def __init__(self, names, main_lan_octet):
        self.names = names
        self.main_lan_octet = main_lan_octet
        self.ids = {}
        self.stats = collections.Counter()

    def stable(self, kind, value):
        key = (kind, value)
        if key not in self.ids:
            self.ids[key] = len([k for k in self.ids if k[0] == kind]) + 1
        return self.ids[key]

    def sub(self, kind, pattern, text, fn):
        def wrapped(m):
            out = fn(m)
            if out != m.group(0):
                self.stats[kind] += 1
            return out
        return pattern.sub(wrapped, text)

    def clean(self, text):
        text = self.sub("cipher_restored", OVERMASKED_CIPHER, text, lambda m: "cipher=chacha20-poly1305@openssh.com" + m.group(1))
        for pattern, repl in self.names:
            text = self.sub("known_name", pattern, text, lambda m, r=repl: match_case(m.group(0), r))
        text = self.sub("app_realigned", APP_TOKEN, text, lambda m: APP_REPLACEMENT)
        text = text.replace(APP_REPLACEMENT + "_app_network", APP_REPLACEMENT + "_" + APP_REPLACEMENT + "_network")
        text = self.sub("nm_cert", NM_CERT, text, lambda m: m.group(1) + "cert%02d" % self.stable("nm", m.group(0)))
        text = self.sub("ssh_fingerprint", RULES["ssh_fingerprint"], text,
                        lambda m: m.group(0).split(":", 1)[0] + ":" + "A" * len(m.group(0).split(":", 1)[1]))
        text = self.sub("hex_fingerprint", RULES["hex_fingerprint"], text,
                        lambda m: m.group(0) if is_placeholder_hex(m.group(0)) else zero_like(m.group(0), 0))
        text = self.sub("uuid", RULES["uuid"], text, self._uuid)
        text = self.sub("uuid_escaped", RULES["uuid_escaped"], text,
                        lambda m: self._uuid_value(m.group(0).replace("\\x2d", "-")).replace("-", "\\x2d"))
        md5_spans = [m.span() for m in RULES["md5_output"].finditer(text)]
        text = self.sub("hex32_id", RULES["hex32_id"], text,
                        lambda m: m.group(0) if is_placeholder_hex(m.group(0)) or any(
                            a <= m.start() and m.end() <= b for a, b in md5_spans)
                        else zero_like(m.group(0), self.stable("hex32", m.group(0))))
        # Même largeur : le préfixe Tailscale devient le préfixe de documentation.
        text = self.sub("tailscale_prefix", RULES["tailscale_prefix"], text, lambda m: "2001:0db8:0000")
        text = self.sub("disk_id", RULES["partuuid"], text, lambda m: 'PARTUUID="00000000-')
        text = self.sub("hostname", RULES["hostname_header"], text, self._hostname)
        text = self.sub("serial_number", RULES["mac_serial"], text,
                        lambda m: m.group(0) if is_placeholder_hex(m.group(1))
                        else m.group(0)[:-len(m.group(1))] + zero_like(m.group(1), self.stable("serial", m.group(1))))
        text = self.sub("provisioning_udid", RULES["provisioning_udid"], text,
                        lambda m: m.group(0) if is_placeholder_hex(m.group(1))
                        else m.group(0)[:-len(m.group(1))] + zero_like(m.group(1), self.stable("udid", m.group(1))))
        text = self.sub("ipv4_short_net", RULES["ipv4_short_net"], text, self._short_net)
        text = self.sub("mac", RULES["mac"], text, lambda m: "aa:bb:cc:dd:ee:ff")
        # udev predictable-name altname (enx<mac>, wlx<mac>) : encode la MAC sans deux-points.
        text = self.sub("mac_altname", RULES["mac_altname"], text, lambda m: m.group(0)[:-12] + "aabbccddeeff")
        text = self.sub("ipv6", RULES["ipv6"], text, self._ipv6)
        text = self.sub("ipv4", RULES["ipv4"], text, self._ipv4)
        text = self.sub("home_path", RULES["home_path"], text,
                        lambda m: m.group(0) if m.group(1) in ("user", "root") else m.group(0).replace(m.group(1), "user"))
        text = self.sub("email", RULES["email"], text, self._email)
        text = self.sub("cf_ray", RULES["cf_ray"], text,
                        lambda m: m.group(0).replace(m.group(1), "0" * 16 + "-XXX"))
        return text

    def _uuid_value(self, value):
        if is_placeholder_hex(value):
            return value
        return "00000000-0000-0000-0000-%012x" % self.stable("uuid", value.lower())

    def _uuid(self, m):
        return self._uuid_value(m.group(0))

    def _ipv6(self, m):
        value = m.group(0)
        if "::" not in value and value.count(":") < 7:
            return value
        kind = ipv6_problem(value)
        if not kind and value.endswith(":"):
            trimmed = self._ipv6_value(value.rstrip(":"))
            return trimmed + value[len(value.rstrip(":")):]
        return self._ipv6_value(value)

    def _ipv6_value(self, value):
        kind = ipv6_problem(value)
        if not kind:
            return value
        n = self.stable("ipv6", value)
        if kind in ("ipv6_eui64_mac", "ipv6_linklocal"):
            return "fe80::" + zero_like(value[6:], n)
        # Même largeur que l'adresse Tailscale (25 caractères), dans le préfixe de documentation.
        return "2001:0db8:0000::0000:%04x" % n if kind == "ipv6_vpn" else "2001:db8::%x" % n

    def _ipv4(self, m):
        value = m.group(0)
        try:
            ip = ipaddress.ip_address(value)
        except ValueError:
            return value
        if any(ip in net for net in DOC_V4):
            return value
        octets = value.split(".")
        if value.startswith("192.168.") and int(octets[2]) not in ALLOWED_192_168_THIRD_OCTET:
            repl = self._subnet(int(octets[2])) + "." + octets[3]
            return self._pad_column(m, repl)
        if ip in ipaddress.ip_network("100.64.0.0/10") or ip.is_global:
            return self._pad_column(m, "203.0.113.%d" % (self.stable("ipv4", value) % 250 + 1))
        return value

    def _subnet(self, third_octet):
        # Le troisième octet réel ne doit pas survivre : il suffit à reconnaître le plan.
        if third_octet == self.main_lan_octet:
            return "192.168.1"
        return "10.8.%d" % (8 + self.stable("subnet", third_octet))

    def _short_net(self, m):
        third = int(m.group(1).split(".")[2])
        if third in ALLOWED_192_168_THIRD_OCTET:
            return m.group(0)
        repl = self._subnet(third)
        return repl + " " * max(0, len(m.group(0)) - len(repl))

    def _hostname(self, m):
        name = m.group(1) or m.group(2)
        if name in ("machine", "machine-demo", "mac-demo", "localhost"):
            return m.group(0)
        return m.group(0).replace(name, "machine", 1)

    def _pad_column(self, m, repl):
        missing = len(m.group(0)) - len(repl)
        text, start, end = m.string, m.start(), m.end()
        right_aligned = start >= 2 and text[start - 2:start] == "  " and end < len(text) and text[end] in ":%"
        if missing > 0 and right_aligned:
            return " " * missing + repl
        return repl

    def _email(self, m):
        domain = m.group(1).lower()
        if domain in ALLOWED_EMAIL_DOMAINS or domain.endswith(UNIT_SUFFIXES) or domain[0].isdigit():
            return m.group(0)
        return "user@example.invalid"


def main_lan_octet(records):
    counts = collections.Counter()
    for record in records:
        for m in re.finditer(r"default via 192\.168\.(\d+)\.", record.get("output", "")):
            counts[int(m.group(1))] += 1
    return counts.most_common(1)[0][0] if counts else None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("src")
    parser.add_argument("dst")
    parser.add_argument("--names", default=os.environ.get("STEPH_PII_NAMES", DEFAULT_NAMES))
    parser.add_argument("--drop", default="", help="numéros de lignes à supprimer, séparés par des virgules")
    args = parser.parse_args()

    if not os.path.exists(args.names):
        print(f"liste de noms introuvable : {args.names}", file=sys.stderr)
        return 2
    with open(args.src, encoding="utf-8") as handle:
        records = [json.loads(line) for line in handle]
    drop = {int(n) for n in args.drop.split(",") if n.strip()}
    cleaner = Cleaner(load_map(args.names), main_lan_octet(records))

    kept = 0
    with open(args.dst, "w", encoding="utf-8") as out:
        for lineno, record in enumerate(records, 1):
            if lineno in drop:
                continue
            cleaned = {k: cleaner.clean(v) if isinstance(v, str) else v for k, v in record.items()}
            out.write(json.dumps(cleaned, ensure_ascii=False) + "\n")
            kept += 1
    print(f"{args.src} -> {args.dst} : {kept}/{len(records)} lignes, remplacements {dict(cleaner.stats)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
