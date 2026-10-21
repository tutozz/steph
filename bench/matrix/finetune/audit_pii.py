#!/usr/bin/env python3
"""Scanner d'anonymisation du corpus d'affinage steph.

Relance :  python3 audit_pii.py snapshot-1/clean/*.jsonl [--names FICHIER] [--details]

Les termes connus (noms, hôtes, projets) vivent hors dépôt, dans
~/.config/steph/pii_names.tsv ou le chemin de STEPH_PII_NAMES : les écrire ici
les publierait. Le rapport ne montre jamais une valeur trouvée, seulement le
type, le fichier et la ligne. Code de sortie : 0 propre, 1 trouvailles,
2 liste de noms introuvable.

SPDX-License-Identifier: MIT
"""

import argparse
import collections
import ipaddress
import json
import math
import os
import re
import sys

DEFAULT_NAMES = os.path.expanduser("~/.config/steph/pii_names.tsv")

PLACEHOLDER_MAC = {"aa:bb:cc:dd:ee:ff", "00:00:00:00:00:00", "ff:ff:ff:ff:ff:ff"}
ALLOWED_EMAIL_DOMAINS = {"example.invalid", "example.com", "example.org", "example.net", "openssh.com"}
UNIT_SUFFIXES = (".service", ".socket", ".target", ".mount", ".timer", ".slice", ".scope", ".path", ".device")
DOC_V4 = [ipaddress.ip_network(n) for n in ("192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24")]
CGNAT_V4 = ipaddress.ip_network("100.64.0.0/10")
DOC_V6 = ipaddress.ip_network("2001:db8::/32")
TAILSCALE_V6 = ipaddress.ip_network((0xFD7A115CA1E0 << 80, 48))  # préfixe ULA Tailscale
# Sous-réseaux privés admis tels quels : le LAN de démonstration et les cibles
# fictives injoignables des scénarios ping. Tout autre 192.168.x révèle un plan réel.
ALLOWED_192_168_THIRD_OCTET = {1, 97, 98, 99}

PUBLIC_DOMAINS = (
    "example.com", "example.org", "example.net", "iana.org", "debian.org", "debian.net",
    "docker.com", "docker.io", "npmjs.org", "npmjs.com", "pypi.org", "pythonhosted.org",
    "github.com", "githubusercontent.com", "ghcr.io", "gcr.io", "quay.io", "fedoraproject.org",
    "ntp.org", "root-servers.net", "verisign-grs.com", "rust-lang.org", "crates.io",
    "golang.org", "go.dev", "nodejs.org", "ubuntu.com", "cloudflare.com", "openssh.com",
    "freedesktop.org", "kde.org", "gnome.org", "python.org", "gnu.org", "kernel.org",
    "kitware.com", "cmake.org", "smartmontools.org", "sqlite.org", "openssl.org", "swift.org", "apple.com",
    "brew.sh", "rubygems.org", "npmjs.com", "electronjs.org", "llvm.org", "rust-lang.org",
    "kubernetes.io", "k8s.io", "terraform.io", "hashicorp.com", "badssl.com", "curl.se",
    # Only the neutral placeholder: a real tailnet name under ts.net identifies the owner.
    "device.ts.net",
)

RULES = {
    "mac": re.compile(r"(?<![0-9a-fA-F:])(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}(?![0-9a-fA-F:])"),
    "mac_altname": re.compile(r"\b(?:enx|wlx)([0-9a-f]{12})\b"),
    "hex_fingerprint": re.compile(r"(?<![0-9a-fA-F])(?:[0-9a-fA-F]{2}:){7,}[0-9a-fA-F]{2}(?![0-9a-fA-F:])"),
    "ssh_fingerprint": re.compile(r"\b(?:SHA256|SHA1|MD5):[A-Za-z0-9+/]{20,}={0,2}"),
    "uuid": re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"),
    "uuid_escaped": re.compile(r"[0-9a-fA-F]{8}\\x2d[0-9a-fA-F]{4}\\x2d[0-9a-fA-F]{4}\\x2d[0-9a-fA-F]{4}\\x2d[0-9a-fA-F]{12}"),
    "hex32_id": re.compile(r"(?<![0-9a-fA-F])[0-9a-f]{32}(?![0-9a-fA-F])"),
    "email": re.compile(r"(?<![\w.+-])[A-Za-z0-9._%+-]+@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)"),
    # Un suffixe "-3" signale une version Debian (1.2.5.1-3), pas une adresse.
    "ipv4": re.compile(r"(?<![\w.-])(?:\d{1,3}\.){3}\d{1,3}(?![\d]|\.\d|-\d)"),
    # netstat -rn on macOS prints networks without trailing zero octets ("192.168.60").
    "ipv4_short_net": re.compile(r"(?m)^(192\.168\.\d{1,3})(?=\s)"),
    "tailscale_prefix": re.compile(r"(?i)fd7a\:115c\:a1e0"),
    "partuuid": re.compile(r'PARTUUID="([0-9a-fA-F]{8})-'),
    "hostname_header": re.compile(r"(?m)^(?:Linux|Darwin) (\S+) \d|^Linux \S+ \((\S+)\)"),
    # system_profiler SPHardwareDataType : identifiants matériels uniques.
    "mac_serial": re.compile(r"(?m)^\s*Serial Number(?: \(system\))?:\s*(?!To Be Filled By O\.E\.M\.)(\S+)"),
    "provisioning_udid": re.compile(r"(?m)^\s*Provisioning UDID:\s*(\S+)"),
    # md5sum / md5 print a content hash in these exact shapes: not an identifier.
    "md5_output": re.compile(r"(?m)^[0-9a-f]{32}(?=  \S)|^MD5 \(.*\) = [0-9a-f]{32}$"),
    "ipv6": re.compile(r"(?<![0-9A-Za-z:])(?:[0-9a-fA-F]{0,4}:){2,7}[0-9a-fA-F]{0,4}(?![0-9A-Za-z.]|:[0-9A-Fa-f])"),
    "home_path": re.compile(r"/(?:home|Users)/([A-Za-z0-9._-]+)"),
    "private_key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "secret_assignment": re.compile(
        r"(?i)\b(?:password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key|auth)[\"']?\s*[=:]\s*[\"']?([^\s\"',;\[(<]{6,})"),
    "cf_ray": re.compile(r"(?i)cf-ray:\s*([0-9a-f]{16}-[A-Z]{3})"),
    # "app" volontairement absent : sur macOS, tout bundle d'appli se termine en
    # ".app" (« iTerm 2.app », « Affinity Photo 2.app »...) - faux positif
    # systématique sur ps aux/system_profiler, jamais un vrai domaine capturé.
    "domain": re.compile(r"(?<![\w@/.-])((?:[a-z0-9-]+\.)+(?:com|net|org|fr|io|dev|cloud|eu|ri|lan|local|home|internal|tech|xyz|me))(?![\w-]|\.[A-Za-z0-9])"),
    "entropy_token": re.compile(r"(?<![A-Za-z0-9+/_-])[A-Za-z0-9+/_-]{24,}={0,2}(?![A-Za-z0-9+/_-])"),
}


def shannon(text):
    counts = collections.Counter(text)
    return -sum(c / len(text) * math.log2(c / len(text)) for c in counts.values())


def is_placeholder_hex(value):
    # a token like [SERIE_SUPPRIMEE] was already redacted by an earlier cleaning pass
    if re.fullmatch(r"\[[A-Z_]+\]", value):
        return True
    digits = value.replace(":", "").replace("-", "").replace("\\x2d", "").lower()
    return set(digits) <= {"0"} or digits.lstrip("0") in ("",) or bool(re.fullmatch(r"0+[0-9a-f]{0,4}", digits))


def ipv4_problem(text):
    try:
        ip = ipaddress.ip_address(text)
    except ValueError:
        return None
    if any(ip in n for n in DOC_V4):
        return None
    if ip in CGNAT_V4:
        return "ipv4_cgnat_vpn"
    if ip.is_private:
        if text.startswith("192.168.") and int(text.split(".")[2]) not in ALLOWED_192_168_THIRD_OCTET:
            return "ipv4_private_plan"
        return None
    if ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_unspecified or ip.is_reserved:
        return None
    if text.startswith("0."):
        return None
    return "ipv4_public"


def ipv6_problem(text):
    try:
        ip = ipaddress.ip_address(text)
    except ValueError:
        return None
    if ip.version != 6 or ip.is_loopback or ip.is_unspecified or ip in DOC_V6:
        return None
    if ip.ipv4_mapped is not None:
        return ipv4_problem(str(ip.ipv4_mapped))
    if ip in TAILSCALE_V6:
        return "ipv6_vpn"
    if ip.is_link_local:
        iid = ip.packed[8:]
        if iid[3:5] == b"\xff\xfe":
            return "ipv6_eui64_mac"
        return None if int.from_bytes(iid, "big") < 0x10000 else "ipv6_linklocal"
    if ip.is_private:
        return "ipv6_ula"
    if ip.is_multicast:
        return None
    return "ipv6_global"


def domain_allowed(domain):
    domain = domain.lower()
    if domain.endswith((".invalid", ".example", ".test", ".localhost")) or domain.endswith(UNIT_SUFFIXES):
        return True
    return any(domain == d or domain.endswith("." + d) for d in PUBLIC_DOMAINS)


def load_names(path):
    terms = []
    with open(path, encoding="utf-8") as handle:
        for raw in handle:
            raw = raw.rstrip("\n")
            if not raw.strip() or raw.lstrip().startswith("#"):
                continue
            term = raw.split("\t")[0].strip()
            if term:
                terms.append(term)
    return [(t, re.compile(r"(?<![A-Za-z0-9])" + re.escape(t) + r"(?![A-Za-z0-9])", re.IGNORECASE)) for t in terms]


def scan_text(text, names):
    found = []

    def add(kind):
        found.append(kind)

    for m in RULES["mac"].finditer(text):
        if m.group(0).lower() not in PLACEHOLDER_MAC:
            add("mac")
    for m in RULES["mac_altname"].finditer(text):
        if m.group(1) != "aabbccddeeff":
            add("mac")
    for m in RULES["hex_fingerprint"].finditer(text):
        if not is_placeholder_hex(m.group(0)):
            add("hex_fingerprint")
    for m in RULES["ssh_fingerprint"].finditer(text):
        if set(m.group(0).split(":", 1)[1].rstrip("=")) - {"A", "0"}:
            add("ssh_fingerprint")
    md5_spans = [m.span() for m in RULES["md5_output"].finditer(text)]
    for kind in ("uuid", "uuid_escaped", "hex32_id"):
        for m in RULES[kind].finditer(text):
            if kind == "hex32_id" and any(a <= m.start() and m.end() <= b for a, b in md5_spans):
                continue
            if not is_placeholder_hex(m.group(0)):
                add(kind)
    for m in RULES["ipv4_short_net"].finditer(text):
        if int(m.group(1).split(".")[2]) not in ALLOWED_192_168_THIRD_OCTET:
            add("ipv4_private_plan")
    for _ in RULES["tailscale_prefix"].finditer(text):
        add("ipv6_vpn")
    for m in RULES["partuuid"].finditer(text):
        if set(m.group(1)) != {"0"}:
            add("disk_id")
    for m in RULES["hostname_header"].finditer(text):
        if (m.group(1) or m.group(2)) not in ("machine", "machine-demo", "mac-demo", "localhost"):
            add("hostname")
    for m in RULES["mac_serial"].finditer(text):
        if not is_placeholder_hex(m.group(1)):
            add("serial_number")
    for m in RULES["provisioning_udid"].finditer(text):
        if not is_placeholder_hex(m.group(1)):
            add("provisioning_udid")
    for m in RULES["email"].finditer(text):
        domain = m.group(1).lower()
        if domain in ALLOWED_EMAIL_DOMAINS or domain.endswith(UNIT_SUFFIXES) or domain[0].isdigit():
            continue
        add("email")
    for m in RULES["ipv4"].finditer(text):
        kind = ipv4_problem(m.group(0))
        if kind:
            add(kind)
    for m in RULES["ipv6"].finditer(text):
        if "::" not in m.group(0) and m.group(0).count(":") < 7:
            continue
        kind = ipv6_problem(m.group(0)) or ipv6_problem(m.group(0).rstrip(":"))
        if kind:
            add(kind)
    for m in RULES["home_path"].finditer(text):
        if m.group(1) not in ("user", "root"):
            add("home_path")
    for kind in ("private_key", "secret_assignment", "cf_ray"):
        for m in RULES[kind].finditer(text):
            if kind == "cf_ray" and m.group(1).startswith("0000000000000000"):
                continue
            add(kind)
    for m in RULES["domain"].finditer(text):
        if not domain_allowed(m.group(1)):
            add("private_domain")
    for m in RULES["entropy_token"].finditer(text):
        token = m.group(0)
        if "/" in token.strip("/") and token.count("/") > 1:
            continue
        if re.fullmatch(r"[0-9a-f]+", token) or re.fullmatch(r"[A-Za-z_-]+", token):
            continue
        classes = sum(bool(re.search(p, token)) for p in (r"[a-z]", r"[A-Z]", r"[0-9]"))
        if classes == 3 and shannon(token) >= 4.2:
            add("entropy_token")
    for term, pattern in names:
        for _ in pattern.finditer(text):
            add("known_name")
    return found


def scan_file(path, names):
    per_type = collections.Counter()
    locations = collections.defaultdict(list)
    with open(path, encoding="utf-8") as handle:
        for lineno, raw in enumerate(handle, 1):
            try:
                record = json.loads(raw)
            except json.JSONDecodeError:
                per_type["invalid_json"] += 1
                locations["invalid_json"].append(lineno)
                continue
            texts = [v for v in record.values() if isinstance(v, str)]
            texts += [m["content"] for m in record.get("messages", []) if isinstance(m.get("content"), str)]
            for kind in scan_text("\n".join(texts), names):
                per_type[kind] += 1
                if lineno not in locations[kind]:
                    locations[kind].append(lineno)
    return per_type, locations


def main():
    parser = argparse.ArgumentParser(description="Audit PII du corpus steph (n'affiche jamais les valeurs).")
    parser.add_argument("files", nargs="+")
    parser.add_argument("--names", default=os.environ.get("STEPH_PII_NAMES", DEFAULT_NAMES))
    parser.add_argument("--details", action="store_true", help="liste fichier:ligne par type")
    args = parser.parse_args()

    if not os.path.exists(args.names):
        print(f"liste de noms introuvable : {args.names} (voir STEPH_PII_NAMES)", file=sys.stderr)
        return 2
    names = load_names(args.names)

    total = 0
    for path in args.files:
        per_type, locations = scan_file(path, names)
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
