"""Tri déterministe des sorties structurées avant le modèle.

Une sortie réseau ou disques fait souvent plus de 100 lignes : la compaction en garde le
début et la fin, et l'information utile (en0 sur Mac) tombe au milieu. Un petit modèle
suit mal un filtre décrit en mots. On extrait donc ici ce qui doit être dit ; le modèle
ne fait plus que le formuler. `None` : commande inconnue ou sortie illisible, on garde
la sortie brute.
"""

from __future__ import annotations

import os
import re
import shlex

from .strings import n as _tn
from .strings import t as _t

_VIRTUAL_NETWORK = re.compile(r"^(docker\d*|br-[0-9a-f]+|virbr\d+|fwbr\w+)$")
_VIRTUAL_PORT = re.compile(r"^(veth\w*|tap\w+|fwpr\w+|fwln\w+|vnet\d+)")
_LOOPBACK = {"lo", "lo0"}
_PSEUDO_FS_MOUNTS = ("/boot/efi", "/efi", "/System/Volumes/", "/private/var/vm")


def _program(cmd: str) -> tuple[str, list[str]]:
    words = [w for w in cmd.split() if w not in ("sudo", "npx")]
    if not words:
        return "", []
    return words[0].rsplit("/", 1)[-1], words[1:]


def digest(cmd: str, output: str, max_chars: int = 1500, language: str = "fr") -> str | None:
    prog, args = _program(cmd)
    if prog == "ifconfig" or (prog == "ip" and any(a in ("a", "addr", "address") for a in args)):
        return _network(output, language)
    if prog == "df":
        return _disks(output, language)
    if prog == "lspci":
        return _pci(output, language)
    return _list(cmd, output, max_chars, language) or _sectioned(output, max_chars, language)


# ---------------------------------------------------------------- sorties longues à blocs (H1 #17)
#
# Une sortie à plusieurs blocs (un fichier par lint, un service par journal...) perd ses
# blocs du milieu à la simple troncature tête/queue de compact_output. Un en-tête non
# indenté suivi de lignes indentées (comme la sortie par défaut d'ESLint) vaut section ;
# 4 sections ou plus justifient un sommaire structuré plutôt qu'une troncature aveugle.

def _sectioned(output: str, max_chars: int, language: str = "fr") -> str | None:
    from .textproc import compact_output

    sections: list[tuple[str, int]] = []
    header, body_lines = None, 0
    for line in output.splitlines():
        if not line.strip():
            continue
        if line[0] not in (" ", "\t"):
            if header is not None and body_lines:
                sections.append((header, body_lines))
            header, body_lines = line.strip(), 0
        else:
            body_lines += 1
    if header is not None and body_lines:
        sections.append((header, body_lines))
    if len(sections) < 4:
        return None
    names = ", ".join(_base(h)[:40] for h, _ in sections[:3])
    head = _t(language, "digest.sections.head").format(n=len(sections), names=names)
    return head + "\n" + compact_output(output.splitlines(), max_chars)


# ---------------------------------------------------------------- réseau

def _network(output: str, language: str = "fr") -> str | None:
    interfaces = _parse_ip_full(output) or _parse_ifconfig(output) or _parse_ip_brief(output)
    if not interfaces:
        return None
    lines, virtual = [], 0
    for name, up, ipv4 in interfaces:
        if name in _LOOPBACK or _VIRTUAL_PORT.match(name):
            continue
        if _VIRTUAL_NETWORK.match(name):
            virtual += 1
        elif up and ipv4:
            lines.append(f"{name} {ipv4}")
    if virtual:
        lines.append(_t(language, "digest.network.virtual").format(n=virtual))
    return "\n".join(lines) or None


def _parse_ip_full(output: str) -> list[tuple[str, bool, str]]:
    found = []
    for block in re.split(r"(?m)^(?=\d+: )", output):
        head = re.match(r"\d+: ([^:@\s]+)[^<]*<([^>]*)>", block)
        if not head:
            continue
        ipv4 = re.search(r"^\s+inet (\d+\.\d+\.\d+\.\d+)", block, re.M)
        found.append((head.group(1), "UP" in head.group(2).split(","), ipv4.group(1) if ipv4 else ""))
    return found


def _parse_ifconfig(output: str) -> list[tuple[str, bool, str]]:
    found = []
    for block in re.split(r"(?m)^(?=\S)", output):
        head = re.match(r"([^:\s]+):? .*?flags=\w+<([^>]*)>", block)
        if not head:
            continue
        ipv4 = re.search(r"^\s+inet (?:addr:)?(\d+\.\d+\.\d+\.\d+)", block, re.M)
        found.append((head.group(1), "UP" in head.group(2).split(","), ipv4.group(1) if ipv4 else ""))
    return found


def _parse_ip_brief(output: str) -> list[tuple[str, bool, str]]:
    found = []
    for line in output.splitlines():
        m = re.match(r"(\S+?)(?:@\S+)?\s+(UP|DOWN|UNKNOWN|LOWERLAYERDOWN|DORMANT)\b(.*)", line)
        if not m:
            continue
        ipv4 = re.search(r"(\d+\.\d+\.\d+\.\d+)/\d+", m.group(3))
        found.append((m.group(1), m.group(2) != "DOWN", ipv4.group(1) if ipv4 else ""))
    return found


# ---------------------------------------------------------------- disques

def _disks(output: str, language: str = "fr") -> str | None:
    """Linux (df -h, df -hT) et macOS (colonnes d'inodes après le pourcentage)."""
    rows = [line.split() for line in output.splitlines()[1:]]
    typed = "Type" in output.splitlines()[0].split() if output.strip() else False
    lines, seen = [], set()
    for r in rows:
        pct = [i for i, t in enumerate(r) if re.fullmatch(r"\d+%", t)]
        if len(r) < 5 or not pct:
            continue
        device, mount = r[0], " ".join(r[pct[-1] + 1:])
        size, avail, use = r[2 if typed else 1], r[pct[0] - 1], r[pct[0]].rstrip("%")
        if (not device.startswith("/dev/") or device.startswith(("/dev/loop", "/dev/fuse"))
                or not mount or mount.startswith(_PSEUDO_FS_MOUNTS) or device in seen):
            continue
        seen.add(device)
        name = _t(language, "digest.disks.root") if mount == "/" else mount.rstrip("/").rsplit("/", 1)[-1]
        lines.append(_t(language, "digest.disks.line").format(name=name, avail=avail, size=size, use=use))
    return "\n".join(lines) or None


# ---------------------------------------------------------------- pci (lspci)

_PCI_SLOT = re.compile(r"(?m)^(?=(?:[0-9a-fA-F]{4}:)?[0-9a-fA-F]{2}:[0-9a-fA-F]{2}\.[0-9a-fA-F]\s)")
_PCI_HEADER = re.compile(r"^\S+\s+(?P<cls>[^:\[]+?)(?:\s*\[[0-9a-fA-F]{4}\])?:\s*(?P<desc>.+)$")
_PCI_DRIVER = re.compile(r"Kernel driver in use:\s*(\S+)")
_PCI_DEVICE_ID = re.compile(r"\s*\[[0-9a-fA-F]{4}:[0-9a-fA-F]{4}\]")
_PCI_REV = re.compile(r"\s*\(rev [0-9a-fA-F]+\)\s*$")
_PCI_GPU = re.compile(r"^(VGA compatible controller|3D controller|Display controller)$")
_PCI_NETWORK = re.compile(r"^(Ethernet controller|Network controller)$")
_PCI_BRIDGE = re.compile(r"^(Host bridge|ISA bridge)$")
_PCI_USB = re.compile(r"^USB controller$")


def _clean_pci_desc(desc: str) -> str:
    desc = _PCI_DEVICE_ID.sub("", desc)
    desc = _PCI_REV.sub("", desc)
    return re.sub(r"\s{2,}", " ", desc).strip()


def _pci(output: str, language: str = "fr") -> str | None:
    """lspci / lspci -v / -k / -nn : le GPU et le réseau se noyaient dans les ponts hôte
    et les IOMMU quand la sortie brute était tronquée (cas fx29 à 800 caractères)."""
    gpus, nets, bridge, usb, other, matched = [], [], None, 0, 0, 0
    for block in _PCI_SLOT.split(output):
        if not block.strip():
            continue
        m = _PCI_HEADER.match(block.splitlines()[0])
        if not m:
            continue
        matched += 1
        cls, desc = m.group("cls").strip(), _clean_pci_desc(m.group("desc"))
        driver = _PCI_DRIVER.search(block)
        suffix = _t(language, "digest.pci.driver").format(d=driver.group(1)) if driver else ""
        if _PCI_GPU.match(cls):
            gpus.append(desc + suffix)
        elif _PCI_NETWORK.match(cls):
            nets.append(desc + suffix)
        elif _PCI_BRIDGE.match(cls):
            bridge = bridge or desc
        elif _PCI_USB.match(cls):
            usb += 1
        else:
            other += 1
    if not matched:
        return None
    lines = ([_t(language, "digest.pci.gpu").format(d=d) for d in gpus]
             + [_t(language, "digest.pci.network").format(d=d) for d in nets])
    if bridge:
        lines.append(_t(language, "digest.pci.chipset").format(d=bridge))
    if usb:
        lines.append(_t(language, "digest.pci.usb").format(n=usb))
    if other:
        lines.append(_t(language, "digest.pci.other").format(n=other))
    return "\n".join(lines) or None


# ---------------------------------------------------------------- listes

_LIST_PROGRAMS = {"ls", "find", "sort", "cut", "head", "tail", "uniq", "du", "grep", "rg", "fd", "locate"}
_LONG_LISTING = re.compile(r"^[-dlbcps][-rwxsStT]{9}[.+@]?\s")
_SIZE = re.compile(r"^([\d.,]+)([KMGTP]?)i?B?$")
_ARCH = re.compile(r"\.(x86_64|noarch|i686|aarch64|armv7hl)$")
_TRUNCATING_PIPE = re.compile(r"\|\s*(?:sudo\s+)?(?:head|tail)\b")
_DOCKER_STATUS = re.compile(r"\s(Up|Restarting|Exited|Created|Paused|Dead)\b")
_DOCKER_STATUS_VERB = {"Restarting": "digest.docker.restarting", "Exited": "digest.docker.exited",
                       "Dead": "digest.docker.exited", "Paused": "digest.docker.paused",
                       "Created": "digest.docker.created"}


def _size(text: str) -> float:
    m = _SIZE.match(text)
    if not m:
        return 0.0
    return float(m.group(1).replace(",", ".")) * 1024 ** "_KMGTP".index(m.group(2) or "_")


def _list(cmd: str, output: str, max_chars: int, language: str = "fr") -> str | None:
    """Compte les éléments d'une sortie en liste : le petit modèle compte faux.

    Le compte précède la sortie compactée, qui reste visible : un grep sur des logs
    ne doit pas perdre le contenu des lignes."""
    from .textproc import compact_output

    last = cmd.split("|")[-1]
    first, args = _program(cmd.split("|")[0])
    prog, _ = _program(last)
    if first == "systemctl" and "status" in args:
        return None
    lines = [l for l in output.splitlines() if l.strip()]
    truncated = bool(_TRUNCATING_PIPE.search(cmd))
    count_word = _t(language, "digest.list.word_truncated" if truncated else "digest.list.word")
    if first == "docker" and args[:1] == ["ps"]:
        if "-q" in args or len(lines) < 2 or not lines[0].startswith("CONTAINER"):
            return None
        rows = [(l.split()[-1], (m[1] if (m := _DOCKER_STATUS.search(l)) else "Up")) for l in lines[1:]]
        bad = [(n, s) for n, s in rows if s != "Up"]
        if bad:
            # un conteneur Restarting/Exited est l'info utile : le signaler plutôt que le
            # noyer dans les 3 premiers noms (fx22 / TermSpeak ctr-docker-ps-restarting)
            name, status = bad[0]
            active = len(rows) - len(bad)
            head = _t(language, "digest.list.containers_bad").format(
                n=len(rows), active=active, name=name, status=_t(language, _DOCKER_STATUS_VERB[status]))
        else:
            head = _t(language, "digest.list.containers").format(n=len(rows), names=", ".join(n for n, _ in rows[:3]))
        return head + "\n" + compact_output(lines, max_chars)
    if prog not in _LIST_PROGRAMS and first not in _LIST_PROGRAMS:
        return None
    if first == "du" or prog == "du":
        sized = [(l.split(None, 1)[0], l.split(None, 1)[-1].rstrip("/").rsplit("/", 1)[-1]) for l in lines]
        if len(sized) < 3:
            return None
        top = sorted(sized, key=lambda x: _size(x[0]), reverse=True)[:3]
        head = _t(language, "digest.list.largest").format(
            n=len(sized), word=count_word, names=", ".join(f"{n} {sz}" for sz, n in top))
        return head + "\n" + compact_output(lines, max_chars)
    items = []
    for l in lines:
        if l.startswith("total ") and not items:
            continue
        if first in ("dnf", "yum"):
            name = _ARCH.sub("", l.split()[0])
        else:
            name = l.split()[-1] if _LONG_LISTING.match(l) else l.strip()
        if name in (".", ".."):
            continue
        if name.startswith("/"):
            name = name.rstrip("/").rsplit("/", 1)[-1]
        items.append(re.sub(r"^\d+:\s*", "", name)[:60])
    if len(items) < 3:
        return None
    head = _t(language, "digest.list.items").format(n=len(items), word=count_word, names=", ".join(items[:3]))
    return head + "\n" + compact_output(lines, max_chars)


# ================================================================ phrases résolues en code
#
# Quand la sortie suit un format connu, la phrase entière se construit ici : aucun appel
# au modèle, donc aucune invention possible (le juge relevait surtout des « ligne 1 »
# fabriquées et des causes déformées sur ces familles). `None` : on laisse le modèle.

_QUOTES = re.compile(r"[«»'\"‘’`]")
_VIEWERS = {"cat", "bat", "less", "more", "grep", "rg", "echo", "printf", "tac", "zcat"}


def _clean(msg: str, words: int = 14) -> str:
    msg = re.sub(r"\s+", " ", _QUOTES.sub("", msg)).strip()
    return " ".join(msg.split(" ")[:words]).rstrip(".,;: ")


def _end(text: str) -> str:
    return text if text.endswith(("?", "!")) else text + "."


def _base(path: str) -> str:
    return path.strip().strip("<>").rstrip("/").rsplit("/", 1)[-1]


def _n(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


# ---------------------------------------------------------------- aides communes du lot D6-A

_MAX_WORDS = 20  # au-delà, la phrase ne se dit plus d'un souffle : on retire le détail le moins sûr
_SHORT_MSG_WORDS = 6
_SYMBOLS = re.compile(r"[=<>!{}\[\]()±+*|\\]")
# deux commandes enchaînées mêlent leurs sorties : un bilan d'outil tairait celle de la seconde
_CHAINED = re.compile(r"&&|\|\||;|\|")


def _named(names: list[str], language: str, limit: int = 3) -> str:
    if len(names) <= limit:
        return _join(names, language)
    rest = len(names) - limit
    more = _t(language, "resolve.d6a.other" if rest == 1 else "resolve.d6a.others").format(n=rest)
    return ", ".join(names[:limit]) + _t(language, "resolve.d6a.and") + more


def _num(value: str, language: str) -> str:
    if "." in value:
        value = value.rstrip("0").rstrip(".")
    return value if language == "en" else value.replace(".", ",")


def _pct(value: str, language: str) -> str:
    return f"{_num(value, language)}%" if language == "en" else f"{_num(value, language)} %"


def _where(file: str, line: str, msg: str, language: str) -> str:
    """« f ligne N : msg », ou « f ligne N » sans message."""
    return _t(language, "resolve.file_line").format(file=file, line=line, msg=msg).rstrip(" :")


def _speakable(msg: str, words: int = 14) -> str:
    """Message nettoyé sans les jetons faits de ponctuation seule (« --- » serait épelé)."""
    return " ".join(w for w in _clean(msg, words).split() if re.search(r"\w", w))


def _short_msg(msg: str) -> str:
    """Message court et lisible à l'oral, ou vide : jamais d'opérateur ni de structure lue."""
    msg = _clean(re.sub(r"^\[Errno \d+\]\s*", "", msg.strip()), 30)
    if not msg or len(msg.split()) > _SHORT_MSG_WORDS or _SYMBOLS.search(msg):
        return ""
    return msg


def _exc_said(exc_type: str, msg: str) -> str:
    name = exc_type.rsplit(".", 1)[-1]
    short = _short_msg(msg)
    return f"{name}, {short}" if short else name


def _fits(said: str) -> bool:
    return len(said.split()) <= _MAX_WORDS


def _failed_head(errors: int, warnings: int, language: str) -> str:
    """« Échec. », « Échec, 3 erreurs. » ou « Échec, 3 erreurs et 1 avertissement. »."""
    if not warnings:
        return (_t(language, "resolve.failed_n_errors").format(n=errors) if errors > 1
                else _t(language, "resolve.failed"))
    counts = (_tn(language, errors, "resolve.d6a.error", "resolve.d6a.error_many") + _t(language, "resolve.d6a.and")
              + _tn(language, warnings, "resolve.d6a.warning", "resolve.d6a.warning_many"))
    return _t(language, "resolve.d6a.failed_counts").format(counts=counts)


def _of(name: str, language: str) -> str:
    if language == "en":
        return f"of {name}"
    return f"d'{name}" if name[0].lower() in "aeiouy" else f"de {name}"


def _join(items: list[str], language: str, sep: str = ", ") -> str:
    if len(items) < 2:
        return "".join(items)
    return sep.join(items[:-1]) + _t(language, "resolve.apt.and") + items[-1]


def _names_tail(language: str, names: list[str], complete: bool, limit: int = 4) -> str:
    """« : a, b et c » quand la liste est entière et courte, sinon « , dont a, b et c »."""
    if complete and len(names) <= limit:
        return _t(language, "resolve.d6c.colon") + _join(names, language)
    return _t(language, "resolve.d6c.including") + _join(names[:3], language)


def _capped(names: list[str], language: str) -> str:
    if len(names) <= 3:
        return _join(names, language)
    rest = _tn(language, len(names) - 3, "resolve.d6c.other_one", "resolve.d6c.other_many")
    return ", ".join(names[:3]) + _t(language, "resolve.apt.and") + rest


def _outdated(items: list[str], language: str) -> str:
    head = _tn(language, len(items), "resolve.d6c.outdated_one", "resolve.d6c.outdated_many")
    return head + _names_tail(language, items, True) + "."


class Skeleton(str):
    """Squelette exact (statut, compteurs, fichier et ligne) d'une réponse que le code ne peut
    pas dire seul : la cause reste au modèle. `resolve()` ne le dit jamais."""


def _resolved(cmd: str, exit_code: int | None, output: str, language: str) -> tuple[str | None, Skeleton | None]:
    first, args = _program(cmd.split("|")[0])
    failed = exit_code not in (0, None)
    families = (_tests, _lint, _autotools, _compile, _eslint, _traceback, _apt, _pip, _npm, _brew, _git, _net,
                _services, _db, _verbose_count, _checksum, _diff_brief, _wc_total, _rsync_summary, _du, _script_error,
                _file_error, _system, _go, _hardware, _containers, _terraform, _node_error, _process)
    # un visualiseur montre la sortie d'un autre outil : seul son propre échec se résout
    if first in _VIEWERS or re.search(r"\|\s*(?:sudo\s+)?(?:grep|rg)\b", cmd):
        families = (_grep_count, _file_error)
    template = None
    for family in families:
        said = family(first, args, cmd, failed, output, language)
        if said and not isinstance(said, Skeleton):
            return said, None
        template = template or said or None
    return None, template


def resolve(cmd: str, exit_code: int | None, output: str, language: str = "fr") -> str | None:
    return _resolved(cmd, exit_code, output, language)[0]


def skeleton(cmd: str, exit_code: int | None, output: str, language: str = "fr") -> Skeleton | None:
    """Gabarit du mode hybride (D6, piste 2), seulement quand `resolve()` se tait."""
    return _resolved(cmd, exit_code, output, language)[1]


# ---------------------------------------------------------------- code 127, grep sans résultat

# bash « f: line 7: x: command not found » (ligne 7 : x : commande introuvable), dash
# « f: 7: x: not found », zsh « f:7: command not found: x »
_NOT_FOUND_AT = re.compile(
    r"^(?P<script>[^\s:][^:\n]*?):\s?(?:(?:line|ligne)\s)?(?P<line>\d+)\s?:\s?"
    r"(?:(?P<prog>[^:\n]+?)\s?:\s?(?:command not found|commande introuvable|not found)"
    r"|(?:command not found|commande introuvable)\s?:\s?(?P<prog2>\S+))\s*$", re.M)
_SHELLS = {"bash", "sh", "zsh", "dash", "ksh", "-bash", "-zsh", "-sh"}


def not_found_sentence(fw: str, output: str, language: str = "fr") -> str:
    """Code 127 : le programme manquant est celui du message, pas forcément le premier mot."""
    m = _NOT_FOUND_AT.search(output)
    if not m:
        return _t(language, "command_not_found").format(fw=fw)
    prog, script = (m["prog"] or m["prog2"]).strip(), _base(m["script"])
    if script in _SHELLS:
        return _t(language, "command_not_found").format(fw=prog)
    return _t(language, "command_not_found_at").format(fw=prog, script=script, line=m["line"])


_GREP_PROGRAMS = {"grep", "egrep", "fgrep", "zgrep", "rg"}
_GREP_VALUE_SHORT = {"grep": set("ABCDdefm"), "rg": set("ABCdEefgjMmrTt")}
_GREP_VALUE_LONG = {"--regexp", "--file", "--after-context", "--before-context", "--context",
                    "--max-count", "--devices", "--directories", "--label", "--glob", "--iglob",
                    "--type", "--type-not", "--max-depth", "--replace", "--encoding", "--threads",
                    "--max-columns", "--include", "--exclude", "--exclude-dir"}
_GREP_UNSURE = {"-v", "--invert-match", "-L", "--files-without-match", "-f", "--file", "--files",
                "--type-list"}
_GREP_MAX_PATTERN = 40


def grep_no_match(cmd: str, exit_code: int | None, language: str = "fr") -> str | None:
    """grep et rg rendent 1 sans rien écrire quand rien ne correspond (POSIX) ; None si doute."""
    if exit_code != 1 or re.search(r"[;&`]|\|\||\$\(", cmd):
        return None
    try:
        words = shlex.split(cmd.split("|")[-1])
    except ValueError:
        return None
    words = [w for w in words if w not in ("sudo", "command")]
    if not words or words[0].rsplit("/", 1)[-1] not in _GREP_PROGRAMS:
        return None
    kind = "rg" if words[0].rsplit("/", 1)[-1] == "rg" else "grep"
    patterns, positional, options = _grep_parse(words, kind)
    if options & _GREP_UNSURE:
        return None
    if not patterns and positional:
        patterns = [positional[0]]
    patterns = [p for p in patterns if p]
    if not patterns or sum(map(len, patterns)) > _GREP_MAX_PATTERN:
        return None
    return _t(language, "no_match").format(pattern=_t(language, "no_match_or").join(patterns))


def _grep_parse(words: list[str], kind: str) -> tuple[list[str], list[str], set[str]]:
    """(motifs de -e, arguments positionnels, options vues) d'une commande grep ou rg."""
    patterns, positional, options, i, options_done = [], [], set(), 1, False
    while i < len(words):
        w = words[i]
        if options_done or not w.startswith("-") or w == "-":
            positional.append(w)
        elif w == "--":
            options_done = True
        elif w.startswith("--"):
            name, eq, value = w.partition("=")
            options.add(name)
            if name == "--regexp":
                patterns.append(value if eq else (words[i + 1] if i + 1 < len(words) else ""))
            if name in _GREP_VALUE_LONG and not eq:
                i += 1
        else:
            for j, ch in enumerate(w[1:], 1):
                options.add(f"-{ch}")
                if ch in _GREP_VALUE_SHORT[kind]:
                    value = w[j + 1:]
                    if not value:
                        i += 1
                        value = words[i] if i < len(words) else ""
                    if ch == "e":
                        patterns.append(value)
                    break
        i += 1
    return patterns, positional, options


# ---------------------------------------------------------------- compilation

_CC_ERROR = re.compile(
    r"^(?P<file>[^\s:()]+?)(?::(?P<line>\d+):\d+:?| ?\((?P<line2>\d+),\d+\):)\s*(?:- )?(?:fatal )?"
    r"error(?: TS\d+)?:\s*(?P<msg>.+)$", re.M)
_RUST_ERROR = re.compile(r"^error(?:\[(?P<code>E\d+)\])?: (?P<msg>.+)\n\s*--> (?P<file>[^:\s]+):(?P<line>\d+):\d+", re.M)
_ERROR_COUNT = re.compile(r"Found (\d+) errors?|(\d+) errors? generated|due to (\d+) previous errors?")
_LD_UNDEFINED = re.compile(r"^(?P<file>[^\s:()]+):(?:\([^)]*\)|(?P<line>\d+)):\s*undefined reference to [`'](?P<sym>\w+)['`]", re.M)
_MAKE_TARGET_ERROR = re.compile(r"[Mm]ake(?:\[\d+\])?: \*\*\* \[(?P<mkfile>[^:]+):(?P<mkline>\d+):[^\]]*\] Error \d+")


_ERROR_FILES = re.compile(r"Found \d+ errors? in (\d+) files")
_RUST_WARNINGS_EMITTED = re.compile(r"due to \d+ previous errors?; (\d+) warnings? emitted")
# ld64 (macOS) : un symbole C porte un « _ » de tête sous Mach-O
_LD64_UNDEFINED = re.compile(r"^Undefined symbols for architecture \S+:\s*$", re.M)
_LD64_SYMBOL = re.compile(r'^\s+"([^"]+)", referenced from:\s*\n(?:\s+(\S+) in \S+)?', re.M)
_RUST_PANIC = re.compile(r"^thread '[^']*'(?: \(\d+\))? panicked at (?P<file>[^\s:']+):(?P<line>\d+):\d+:\s*\n"
                         r"(?P<msg>.+)$", re.M)
_RUST_PANIC_OLD = re.compile(r"^thread '[^']*'(?: \(\d+\))? panicked at '(?P<msg>.*)', "
                             r"(?P<file>[^\s:']+):(?P<line>\d+):\d+", re.M)
_RUST_UNWRAP = re.compile(r"^called `(?:Result|Option)::unwrap\(\)` on an? `(Err|None)` value(?:: (.*))?$")
_RUST_IO_MESSAGE = re.compile(r'message: "([^"]+)"')


def _compile(first, args, cmd, failed, output, language="fr"):
    if not failed:
        if _CHAINED.search(cmd):
            return None
        if first == "cargo":
            return _cargo_success(args, output, language)
        return _cc_warnings(first, output, language)
    found = [(m["file"], m["line"] or m["line2"], _clean(m["msg"])) for m in _CC_ERROR.finditer(output)]
    found += [(m["file"], m["line"], (m["code"] + ", " if m["code"] else "") + _clean(m["msg"]))
              for m in _RUST_ERROR.finditer(output)]
    if found:
        count = _ERROR_COUNT.search(output)
        n = int(next(g for g in count.groups() if g)) if count else len(found)
        file, line, msg = found[0]
        files = _ERROR_FILES.search(output)
        warned = _RUST_WARNINGS_EMITTED.search(output)
        if files and n > 1 and int(files[1]) > 1:
            head = _t(language, "resolve.d6a.n_errors_files").format(n=n, m=files[1])
        else:
            head = _failed_head(n, int(warned[1]) if warned else 0, language)
        where = _t(language, "resolve.file_line").format(file=_base(file), line=line, msg=msg)
        return _end(f"{head} {where}")
    if _LD64_UNDEFINED.search(output) and (symbols := _LD64_SYMBOL.findall(output)):
        sym, caller = (s[1:] if s.startswith("_") else s for s in symbols[0])
        if len(symbols) > 1:
            return _t(language, "resolve.d6a.ld_symbols").format(n=len(symbols), sym=sym)
        if caller:
            return _t(language, "resolve.d6a.ld_symbol").format(sym=sym, fn=caller)
        return _t(language, "resolve.d6a.ld_symbol_anon").format(sym=sym)
    # ld/collect2 : "undefined reference" n'a pas de ligne source quand seul l'offset de
    # section est connu ; on retombe alors sur la ligne du Makefile
    if m := _LD_UNDEFINED.search(output):
        file, sym = _base(m["file"]), m["sym"]
        if m["line"]:
            return _t(language, "resolve.ld_undefined_line").format(file=file, line=m["line"], sym=sym)
        if mk := _MAKE_TARGET_ERROR.search(output):
            return _t(language, "resolve.ld_undefined_makefile").format(file=file, sym=sym, mkline=mk["mkline"])
        return _t(language, "resolve.ld_undefined").format(file=file, sym=sym)
    return _rust_panic(output, language)


def _rust_panic(output: str, language: str) -> str | None:
    m = _RUST_PANIC.search(output) or _RUST_PANIC_OLD.search(output)
    if not m:
        return None
    msg = m["msg"].strip()
    if unwrap := _RUST_UNWRAP.match(msg):
        if unwrap[1] == "None":
            msg = _t(language, "resolve.d6a.unwrap_none")
        else:
            payload = unwrap[2] or ""
            io = _RUST_IO_MESSAGE.search(payload)
            detail = io[1] if io else ("" if _SYMBOLS.search(payload) else _clean(payload, 8))
            msg = _t(language, "resolve.d6a.unwrap_err") + (f", {detail}" if detail else "")
    else:
        msg = _clean(msg)
    return _t(language, "resolve.d6a.rust_panic").format(where=_where(_base(m["file"]), m["line"], msg, language))


# ---------------------------------------------------------------- cargo réussi (build, check, clippy)

_CARGO_FINISHED = re.compile(r"^\s*Finished .+ in [\d.]+m?s\s*$", re.M)
_CARGO_LOCAL_CRATE = re.compile(r"^\s*(?:Compiling|Checking) (\S+) v\S+ \((?:/|file://)", re.M)
_CARGO_GENERATED = re.compile(r"^warning: `[^`]+` \([^)]*\) generated (\d+) warnings?"
                              r"(?: \(run `[^`]*` to apply (\d+) suggestions?\))?", re.M)
_CARGO_ANY_WARNING = re.compile(r"^warning[:\[]", re.M)
_CARGO_LOCKING = re.compile(r"^\s*Locking (\d+) packages?\b", re.M)
_CARGO_SUBCOMMANDS = {"build": "build", "b": "build", "check": "check", "c": "check", "clippy": "clippy"}


def _cargo_success(args: list[str], output: str, language: str) -> str | None:
    sub = _CARGO_SUBCOMMANDS.get(args[0] if args else "")
    if not sub or not _CARGO_FINISHED.search(output):
        return None
    crates = list(dict.fromkeys(_CARGO_LOCAL_CRATE.findall(output)))
    key = f"resolve.d6a.cargo.{sub}"
    said = (_t(language, key).format(of=_of(crates[0], language)) if len(crates) == 1
            else _t(language, key + "_anon"))
    # un résumé « generated N warnings » par cible : leur somme compterait les doublons
    generated = _CARGO_GENERATED.findall(output)
    if len(generated) == 1:
        said += ", " + _tn(language, int(generated[0][0]), "resolve.d6a.warning", "resolve.d6a.warning_many")
        if fixable := int(generated[0][1] or 0):
            said += _t(language, "resolve.d6a.fixable" if fixable == 1 else "resolve.d6a.fixable_many").format(
                n=fixable)
    elif generated or _CARGO_ANY_WARNING.search(output):
        said += _t(language, "resolve.d6a.cargo.some_warnings")
    else:
        said += _t(language, "resolve.d6a.cargo.no_warning")
    if locked := _CARGO_LOCKING.search(output):
        said += ", " + _tn(language, int(locked[1]), "resolve.d6a.cargo.locked", "resolve.d6a.cargo.locked_many")
    return said + "."


# ---------------------------------------------------------------- gcc, clang réussis avec avertissements
#
# gcc n'imprime aucun total et ses lignes « warning: » ne donnent pas le compte réel (L2) :
# seul le total de clang (« N warnings generated. ») est dit.

_COMPILER = re.compile(r"(?:gcc|g\+\+|cc|c\+\+|clang|clang\+\+)(?:-\d+)?")
_CC_WARNING_LINE = re.compile(r"^(?P<file>[^\s:()]+?):(?P<line>\d+):(?:\d+:)? "
                              r"(?P<kw>warning|attention|avertissement)[ \xa0]?: (?P<msg>.+)$", re.M)
_CC_ANY_ERROR_LINE = re.compile(r"^[^\s:()]+?:\d+(?::\d+)?: (?:fatal )?(?:error|erreur)[ \xa0]?:", re.M)
_CC_FLAG = re.compile(r"\s*\[-W[^\]]*\]\s*$")
_CLANG_TOTAL = re.compile(r"^(\d+) warnings? generated\.\s*$", re.M)


def _cc_warnings(first: str, output: str, language: str) -> str | None:
    if not _COMPILER.fullmatch(first) or _CC_ANY_ERROR_LINE.search(output):
        return None
    found = [*_CC_WARNING_LINE.finditer(output)]
    if not found:
        return None
    files = list(dict.fromkeys(_base(m["file"]) for m in found))
    names = _named(files, language)
    totals = _CLANG_TOTAL.findall(output)
    if totals:
        warnings = _tn(language, sum(map(int, totals)), "resolve.d6a.warning", "resolve.d6a.warning_many")
        said = _t(language, "resolve.d6a.cc_warned_n").format(n=warnings, files=names)
    else:
        said = _t(language, "resolve.d6a.cc_warned").format(files=names)
    top = found[0]
    # sortie en français (locale fr_FR) dans une session anglaise : fichier et ligne, sans le message
    msg = "" if top["kw"] != "warning" and language == "en" else _clean(_CC_FLAG.sub("", top["msg"]))
    variants = []
    for detail in dict.fromkeys([msg, ""]):
        where = _where(_base(top["file"]), top["line"], detail, language)
        if len(files) == 1:
            where = where.removeprefix(_base(top["file"]) + " ")
        variants.append(said + _t(language, "resolve.d6a.cc_first").format(where=where))
    return next((v for v in variants if _fits(v)), variants[-1])


# ---------------------------------------------------------------- autotools : ./configure, make réussi
#
# Le modèle recopie « checking for gawk... no » ou la liste des sous-dossiers au lieu du
# résultat. Tout ce qui sort du format standard d'autoconf ou de GNU make (tableau de fin,
# bilan écrit par le projet, avertissement d'un autre outil) reste au modèle.

_CONFIGURE_ERROR = re.compile(r"configure: error: (.*)$", re.M)
_CONFIGURE_ARG = re.compile(r"-.*|\w+=.*")
_MAKE_DIR = re.compile(r"^g?make(?:\[\d+\])?\s?:\s+(?:Entering directory|Leaving directory|[Oo]n entre dans le "
                       r"répertoire|[Oo]n quitte le répertoire|Entre dans le répertoire|Quitte le répertoire)"
                       r"\s+[«'`‘]\s*(?P<dir>.+?)\s*[»'’]$")
_MAKE_IDLE = re.compile(r"^g?make(?:\[\d+\])?\s?:\s+(?:Nothing to be done|Rien à faire|.+ is up to date|.+ est à jour)"
                        r"|^Making \S+ in |^\S*make\s")
_MAKE_ARG = re.compile(r"-j\d*|--jobs(?:=\d+)?|\d+|-k|--keep-going|-s|--silent|--quiet|-w|--print-directory|"
                       r"-l[\d.]*|\w+=.*")
_MAKE_TARGETS = {(): "resolve.make.build", ("all",): "resolve.make.build", ("install",): "resolve.make.install"}
_CC_WARNING = re.compile(r"^(?P<file>[^\s:()]+?):\d+(?::\d+)?: (?:warning|avertissement|attention) ?:")
_CC_NOTE = re.compile(r"^[^\s:()]+?:\d+(?::\d+)?: note ?:")
_ANY_WARNING = re.compile(r"(?i)(?:^|[\s:])(?:warning|avertissement|attention) ?:|(?<![-\w/.])(?:ignored|ignoré|"
                          r"deprecated|obsolète)\b")
_ANY_ERROR = re.compile(r"(?i)(?:^|[\s:])(?:error|erreur|fatal) ?:|\*\*\*|\bError \d|undefined reference")
_PROJECT_VERSION = re.compile(r"(?P<name>[A-Za-z][\w.+]*?)-v?(?P<ver>\d+(?:\.\d+)+[\w.]*)")


def _autotools(first, args, cmd, failed, output, language="fr"):
    if first == "configure" and all(_CONFIGURE_ARG.fullmatch(a) for a in args):
        return _configure_failure(output, language) if failed else _configure_success(output, language)
    if first in ("make", "gmake") and not failed:
        targets = tuple(a for a in args if not _MAKE_ARG.fullmatch(a))
        if targets in _MAKE_TARGETS:
            return _make_success(_MAKE_TARGETS[targets], output, language)
    return None


def _configure_success(output: str, language: str) -> str | None:
    lines = [l.strip() for l in output.splitlines() if l.strip()]
    if (not lines or not lines[-1].startswith("config.status: ") or "config.status: creating Makefile" not in lines
            or any(l.startswith("configure: WARNING") for l in lines)):
        return None
    key = "resolve.configure.ok_config_h" if "config.status: creating config.h" in lines else "resolve.configure.ok"
    return _t(language, key)


def _configure_failure(output: str, language: str) -> str | None:
    found = [m for m in _CONFIGURE_ERROR.finditer(output) if m[1].strip() and not re.match(r"in ['`‘]", m[1])]
    if not found:
        return None
    msg = re.sub(r"\s*\((?:see|voir) [^)]*\)", "", found[-1][1]).replace("$", "").strip()
    if end := re.search(r"[.:!?](?:\s|$)", msg):
        msg = msg[:end.start()]
        if msg.count("(") > msg.count(")"):
            msg = msg[:msg.rfind("(")]
    else:
        following = output[found[-1].end():].lstrip("\n").split("\n", 1)[0].strip()
        if following and not following.startswith(("See ", "configure:", "checking ")):
            return None
    return _t(language, "resolve.configure.failed").format(msg=_clean(msg))


def _make_success(key: str, output: str, language: str) -> str | None:
    lines = [l.strip() for l in output.splitlines() if l.strip()]
    if not lines or not _MAKE_DIR.match(lines[-1]):
        return None
    if any(_ANY_ERROR.search(l) for l in lines) or all(_MAKE_DIR.match(l) or _MAKE_IDLE.match(l) for l in lines):
        return None
    warned = [m["file"] for l in lines if (m := _CC_WARNING.match(l))]
    if len(warned) != sum(bool(_ANY_WARNING.search(l)) and not _CC_NOTE.match(l) for l in lines):
        return None
    dirs = [m["dir"] for l in lines if (m := _MAKE_DIR.match(l))]
    root = os.path.commonpath(dirs) if len({d.startswith("/") for d in dirs}) == 1 else ""
    if project := _PROJECT_VERSION.fullmatch(os.path.basename(root)):
        name = f"{project['name']} {project['ver']}"
        of = f"d'{name}" if name[0].lower() in "aeiouy" else f"de {name}"
        head = _t(language, key).format(proj=name, of=of)
    else:
        head = _t(language, key + "_anon")
    if not warned:
        return _t(language, "resolve.make.clean").format(head=head)
    files = list(dict.fromkeys(_base(f) for f in warned))
    if len(files) > 1:
        return _t(language, "resolve.make.warnings_first").format(head=head, file=files[0])
    tail = "resolve.make.warning_one" if len(warned) == 1 else "resolve.make.warnings_file"
    return _t(language, tail).format(head=head, file=files[0])


# ---------------------------------------------------------------- eslint (H1 #2)

_ESLINT_SUMMARY = re.compile(r"✖ (\d+) problems? \((\d+) errors?, (\d+) warnings?\)")
_ESLINT_ISSUE = re.compile(r"^\s{2,}(\d+):(\d+)\s+(error|warning)\s+(.+?)\s{2,}\S+\s*$", re.M)


def _eslint(first, args, cmd, failed, output, language="fr"):
    if first != "eslint" or not failed:
        return None
    m = _ESLINT_SUMMARY.search(output)
    if not m:
        return None
    n_errors = int(m[2])
    if not n_errors:
        return None  # échec dû aux seuls avertissements : rien de sûr à compter ici
    file, loc, msg = None, None, None
    for line in output.splitlines():
        if im := _ESLINT_ISSUE.match(line):
            if im[3] == "error":
                loc, msg = im[1], _clean(im[4])
                break
            continue
        if line.strip() and not line.startswith((" ", "\t", "✖")):
            file = line.strip()
    if not msg:
        return None
    head = _failed_head(n_errors, int(m[3]), language)
    where = (_t(language, "resolve.file_line").format(file=_base(file), line=loc, msg=msg) if file
             else msg)
    return _end(f"{head} {where}")


# ---------------------------------------------------------------- lint et typage (D6-A)
#
# Formats documentés : ruff (« Found N errors. », « [*] N fixable »), pylint (« rated at X/10 »),
# ShellCheck (format tty), yamllint (format standard), mypy (« f:l: error: »), messages de
# configuration absente d'ESLint. Hors format, on laisse le modèle.

def _lint(first, args, cmd, failed, output, language="fr"):
    if _CHAINED.search(cmd):
        return None
    if first == "ruff":
        return _ruff(failed, output, language)
    if first == "eslint" and failed:
        return _eslint_config(output, language)
    if first == "pylint":
        return _pylint(failed, output, language)
    if first == "shellcheck" and failed:
        return _shellcheck(output, language)
    if first == "yamllint":
        return _yamllint(failed, output, language)
    if first in ("mypy", "dmypy"):
        return _mypy(failed, output, language)
    return None


_RUFF_FOUND = re.compile(r"^Found (\d+) errors?\.\s*$", re.M)
_RUFF_FIXABLE = re.compile(r"^\[\*\] (\d+) fixable with the `--fix` option", re.M)
_RUFF_CONCISE = re.compile(r"^([^\s:]+):\d+:\d+: [A-Z]+\d+ ", re.M)
_RUFF_FULL = re.compile(r"^\s*-->\s+([^\s:]+):\d+:\d+\s*$", re.M)
_RUFF_PARSE_FILE = re.compile(r"^\s*Cause: Failed to parse (\S+)", re.M)
_RUFF_TOML_LINE = re.compile(r"^\s*Cause: TOML parse error at line (\d+), column \d+\s*$", re.M)
_TOML_SNIPPET = re.compile(r"^\s|^\d+ \||^\|")


def _ruff_path(path: str) -> str:
    return "/".join(path.removeprefix("./").split("/")[-2:])


def _ruff(failed: bool, output: str, language: str) -> str | None:
    if output.lstrip().startswith("ruff failed"):
        return _ruff_config(output, language) if failed else None
    if not failed and "All checks passed!" in (l.strip() for l in output.splitlines()):
        return _t(language, "resolve.d6a.ruff_ok")
    found = _RUFF_FOUND.search(output)
    if not found:
        return None
    n = int(found[1])
    files = _RUFF_CONCISE.findall(output) + _RUFF_FULL.findall(output)
    where = ""
    # un fichier n'est nommé que si chaque erreur annoncée a sa ligne dans la sortie
    if len(files) == n:
        counts: dict[str, int] = {}
        for f in files:
            counts[f] = counts.get(f, 0) + 1
        top = max(counts, key=counts.get)
        if len(counts) == 1:
            where = _t(language, "resolve.d6a.ruff_in").format(file=_ruff_path(top))
        elif counts[top] * 2 > n:
            where = _t(language, "resolve.d6a.ruff_mostly").format(n=len(counts), file=_ruff_path(top))
        else:
            where = _t(language, "resolve.d6a.ruff_in_files").format(n=len(counts))
    fixable = ""
    if fix := _RUFF_FIXABLE.search(output):
        k = int(fix[1])
        fixable = _t(language, "resolve.d6a.fixable" if k == 1 else "resolve.d6a.fixable_many").format(n=k)
    errors = _tn(language, n, "resolve.d6a.error", "resolve.d6a.error_many")
    said = _t(language, "resolve.d6a.ruff").format(errors=errors, where=where, fixable=fixable)
    return f"{_t(language, 'resolve.failed')} {said}" if failed else said


def _ruff_config(output: str, language: str) -> str | None:
    parsed = _RUFF_PARSE_FILE.search(output)
    if not parsed:
        return None
    file = _base(parsed[1])
    where = file
    if toml := _RUFF_TOML_LINE.search(output):
        tail = [l for l in output[toml.end():].splitlines() if l.strip() and not _TOML_SNIPPET.match(l)]
        msg = _clean(tail[0].split(", expected")[0]) if tail else ""
        where = _where(file, toml[1], msg, language)
    return _t(language, "resolve.d6a.ruff_config").format(where=where)


def _eslint_config(output: str, language: str) -> str | None:
    if "ESLint couldn't find an eslint.config" in output:
        return _t(language, "resolve.d6a.eslint_no_flat_config")
    if "ESLint couldn't find a configuration file" in output:
        return _t(language, "resolve.d6a.eslint_no_config")
    return None


_PYLINT_SCORE = re.compile(r"Your code has been rated at (-?\d+(?:\.\d+)?)/10")
_PYLINT_MESSAGE = re.compile(r"^[^\s:]+:\d+:\d+: ([CRWEFI])\d{4}: ", re.M)


def _pylint(failed: bool, output: str, language: str) -> str | None:
    score = _PYLINT_SCORE.search(output)
    if not score:
        return None
    said = _t(language, "resolve.d6a.pylint").format(score=_num(score[1], language))
    kinds = _PYLINT_MESSAGE.findall(output)
    if kinds:
        said += ", " + _tn(language, len(kinds), "resolve.d6a.message", "resolve.d6a.message_many")
        if errors := sum(k in "EF" for k in kinds):
            said += _t(language, "resolve.d6a.including_errors" if errors == 1
                       else "resolve.d6a.including_errors_many").format(n=errors)
    said += "."
    return f"{_t(language, 'resolve.failed')} {said}" if failed else said


_SC_HEAD = re.compile(r"^In (\S+) line (\d+):\s*$")
_SC_ITEM = re.compile(r"^\s*\^-*\^?\s+SC(\d+) \((?:error|warning|info|style)\): (.+)$")


def _shellcheck(output: str, language: str) -> str | None:
    items, where = [], None
    for line in output.splitlines():
        if head := _SC_HEAD.match(line):
            where = (head[1], head[2])
        elif (item := _SC_ITEM.match(line)) and where:
            items.append((*where, item[1], item[2]))
    if not items:
        return None
    file, line, code, msg = items[0]
    count = _tn(language, len(items), "resolve.d6a.finding", "resolve.d6a.finding_many")
    detail = f"SC{code}, {_clean(re.split(r'\.\s', msg, maxsplit=1)[0])}"
    return (f"{_t(language, 'resolve.failed')} {_t(language, 'resolve.d6a.shellcheck').format(n=count)} "
            + _end(_where(_base(file), line, detail, language)))


_YAMLLINT_ITEM = re.compile(r"^\s+(\d+):\d+\s+(error|warning)\s+(.+?)(?:\s+\([\w-]+\))?\s*$")


def _yamllint(failed: bool, output: str, language: str) -> str | None:
    items, file = [], None
    for line in output.splitlines():
        if not line.strip():
            continue
        if not line[0].isspace():
            file = line.strip()
        elif (item := _YAMLLINT_ITEM.match(line)) and file:
            items.append((file, *item.groups()))
    errors = [i for i in items if i[2] == "error"]
    warnings = len(items) - len(errors)
    if failed and errors:
        head = _failed_head(len(errors), warnings, language)
        top = errors[0]
    elif not failed and not errors and warnings:
        counts = _tn(language, warnings, "resolve.d6a.warning", "resolve.d6a.warning_many")
        head = _t(language, "resolve.d6a.no_error_counts").format(counts=counts)
        top = items[0]
    else:
        return None
    return f"{head} " + _end(_where(_base(top[0]), top[1], _speakable(top[3]), language))


_MYPY_ERROR = re.compile(r"^(?P<file>[^\s:]+\.pyi?):(?P<line>\d+):(?:\d+:)? error: (?P<msg>.+?)"
                         r"(?:\s+\[[\w-]+\])?\s*$", re.M)
_MYPY_FOUND = re.compile(r"^Found (\d+) errors? in (\d+) files?", re.M)
_MYPY_SUCCESS = re.compile(r"^Success: no issues found in (\d+) source files?", re.M)


def _mypy(failed: bool, output: str, language: str) -> str | None:
    if not failed:
        if ok := _MYPY_SUCCESS.search(output):
            files = _tn(language, int(ok[1]), "resolve.d6a.file", "resolve.d6a.file_many")
            return _t(language, "resolve.d6a.mypy_ok").format(files=files)
        return None
    errors = [*_MYPY_ERROR.finditer(output)]
    if not errors:
        return None
    found = _MYPY_FOUND.search(output)
    n, files = (int(found[1]), int(found[2])) if found else (len(errors), 1)
    head = (_t(language, "resolve.d6a.n_errors_files").format(n=n, m=files) if n > 1 and files > 1
            else _failed_head(n, 0, language))
    top = errors[0]
    msg = _clean(re.sub(r"\s*\(.*\)\s*$", "", top["msg"]))
    return f"{head} " + _end(_where(_base(top["file"]), top["line"], msg, language))


# ---------------------------------------------------------------- go build / go test

_GO_BUILD_ERROR = re.compile(r"^\S*?(?P<file>[\w./-]+\.go):(?P<line>\d+):\d+:\s*(?P<msg>.+)$", re.M)
# go help test : « --- FAIL: nom (Xs) », indenté pour un sous-test ; en -v, le journal d'un test
# est imprimé entre son « === RUN » et son « --- FAIL », sans -v il suit le « --- FAIL », indenté
_GO_TEST_FAIL = re.compile(r"^(?P<indent>\s*)--- FAIL: (?P<name>\S+)", re.M)
_GO_TEST_RUN = re.compile(r"^\s*=== RUN\s+(\S+)\s*$")
_GO_TEST_LOG = re.compile(r"^\s+(?P<file>[\w.-]+\.go):(?P<line>\d+):\s*(?P<msg>.+)$")
_GO_TEST_PARALLEL = re.compile(r"^\s*=== (?:PAUSE|CONT)\b", re.M)
_GO_TEST_PKG_FAIL = re.compile(r"^FAIL\t(?P<pkg>\S+)\t", re.M)
_GO_PKG_LINE = re.compile(r"^(ok|FAIL|\?)\s*\t(\S+)\t(.*)$")
_GO_COVER_ONLY = re.compile(r"^\t(\S+)\t\tcoverage: [\d.]+% of statements\s*$")
_GO_COVERAGE = re.compile(r"coverage: ([\d.]+)% of statements")
# runtime Go : « panic: … » ou interblocage, puis la pile « goroutine N [état]: »
_GO_PANIC = re.compile(r"^panic: (.+?)(?: \[recovered\])?\s*$", re.M)
_GO_DEADLOCK = re.compile(r"^fatal error: all goroutines are asleep - deadlock!", re.M)
_GO_GOROUTINE = re.compile(r"^goroutine \d+ \[[^\]]*\]:\s*$", re.M)
_GO_FRAME = re.compile(r"^(?P<fn>\S[^\n]*)\([^()\n]*\)\s*\n\t(?P<file>\S+\.go):(?P<line>\d+)", re.M)


def _go_test_log(name: str, output: str) -> re.Match | None:
    """Première ligne « f.go:N: msg » du journal du test `name`, ou None si on ne peut l'attribuer."""
    lines = output.splitlines()
    if "=== RUN" in output:
        # tests parallèles : les journaux s'entremêlent, aucune attribution sûre
        if _GO_TEST_PARALLEL.search(output):
            return None
        start = next((i for i, l in enumerate(lines) if (m := _GO_TEST_RUN.match(l)) and m[1] == name), None)
        if start is None:
            return None
        for line in lines[start + 1:]:
            if re.match(r"^\s*(?:=== |--- )", line):
                return None
            if m := _GO_TEST_LOG.match(line):
                return m
        return None
    head = next(((i, m) for i, l in enumerate(lines) if (m := _GO_TEST_FAIL.match(l)) and m["name"] == name), None)
    if head is None:
        return None
    i, m = head
    for line in lines[i + 1:]:
        if len(line) - len(line.lstrip()) <= len(m["indent"]) or line.lstrip().startswith("--- "):
            return None
        if log := _GO_TEST_LOG.match(line):
            return log
    return None


def _go_test_passed(cmd: str, output: str, language: str) -> str | None:
    if "-json" in cmd.split() or _CHAINED.search(cmd):
        return None
    passed, untested = [], []
    for line in output.splitlines():
        if m := _GO_PKG_LINE.match(line):
            name = m[2].rsplit("/", 1)[-1]
            if m[1] == "FAIL" or "[no tests to run]" in m[3]:
                return None
            if m[1] == "?":
                untested.append(name)
            else:
                cover = _GO_COVERAGE.search(m[3])
                passed.append(f"{name} {_pct(cover[1], language)}" if cover else name)
        elif m := _GO_COVER_ONLY.match(line):
            untested.append(m[1].rsplit("/", 1)[-1])
    if not passed:
        return None
    head = _tn(language, len(passed), "resolve.d6a.go.pkg_passed", "resolve.d6a.go.pkg_passed_many")
    said = _t(language, "resolve.d6a.go.passed").format(head=head, names=_named(passed, language))
    if untested:
        said += _t(language, "resolve.d6a.go.no_tests").format(names=_named(untested, language))
    return said


def _go_func(fn: str) -> str:
    """« main.(*Cache).Get » -> « Cache.Get », « example.invalid/app/pkg.Run » -> « Run »."""
    _, _, rest = fn.rsplit("/", 1)[-1].partition(".")
    return re.sub(r"[()*]", "", rest) or fn


def _go_panic(output: str, language: str) -> str | None:
    panic, deadlock = _GO_PANIC.search(output), _GO_DEADLOCK.search(output)
    goroutine = _GO_GOROUTINE.search(output)
    if not (panic or deadlock) or not goroutine:
        return None
    said = (_t(language, "resolve.d6a.go.deadlock") if deadlock
            else _t(language, "resolve.d6a.go.panic").format(msg=_clean(panic[1], 12)))
    for frame in _GO_FRAME.finditer(output, goroutine.end()):
        if not frame["fn"].startswith(("runtime.", "panic(")):
            return said + _t(language, "resolve.d6a.go.in").format(
                fn=_go_func(frame["fn"]), file=_base(frame["file"]), line=frame["line"])
    return said


def _go(first, args, cmd, failed, output, language="fr"):
    # un test qui panique : le test en échec dit plus que la pile du paquet testing
    go_test = first == "go" and args[:1] == ["test"]
    if failed and not go_test and (said := _go_panic(output, language)):
        return said
    if first != "go":
        return None
    if not failed:
        return _go_test_passed(cmd, output, language) if args[:1] == ["test"] else None
    names = list(dict.fromkeys(m["name"] for m in _GO_TEST_FAIL.finditer(output)))
    if names:
        # un parent échoue avec ses sous-tests : seules les feuilles sont des échecs à compter
        leaves = [n for n in names if not any(o.startswith(n + "/") for o in names)]
        pkgs = [m["pkg"].rsplit("/", 1)[-1] for m in _GO_TEST_PKG_FAIL.finditer(output)]
        pkg_part = (_t(language, "resolve.go.package").format(pkg=pkgs[0]) if len(pkgs) == 1
                    else _t(language, "resolve.d6a.go.packages").format(pkgs=_named(pkgs, language)) if pkgs
                    else "")
        log = _go_test_log(leaves[0], output)
        detail = f", {_where(log['file'], log['line'], _clean(log['msg']), language)}" if log else ""
        count = _tn(language, len(leaves), "resolve.go.tests_failed", "resolve.go.tests_failed_many")
        head = f"{_t(language, 'resolve.failed')} {count}."
        return _end(f"{head}{pkg_part} {leaves[0].replace('/', ' ')}{detail}")
    found = [(m["file"], m["line"], _clean(m["msg"])) for m in _GO_BUILD_ERROR.finditer(output)]
    if not found:
        return None
    file, line, msg = found[0]
    n = len(found)
    head = _t(language, "resolve.failed_n_errors").format(n=n) if n > 1 else _t(language, "resolve.failed")
    where = _t(language, "resolve.file_line").format(file=_base(file), line=line, msg=msg)
    return _end(f"{head} {where}")


# ---------------------------------------------------------------- exception Python

_PY_FRAME = re.compile(r'^\s*File "([^"]+)", line (\d+)', re.M)
_PY_EXC = re.compile(r"^([A-Za-z_][\w.]*)(?::\s*(.*))?$")
_PY_CHAIN = re.compile(r"^(?:The above exception was the direct cause of the following exception:"
                       r"|During handling of the above exception, another exception occurred:)\s*$", re.M)
_CHAIN_MAX_WORDS = 20  # au-delà, la cause noie la phrase : on garde l'exception finale seule


def _traceback(first, args, cmd, failed, output, language="fr"):
    if not failed or "Traceback (most recent call last):" not in output:
        return None
    frames = _PY_FRAME.findall(output)
    exc = _PY_EXC.match([l for l in output.splitlines() if l.strip()][-1].strip())
    if not exc:
        return None
    what = " ".join(p for p in (exc[1], _clean(exc[2] or "")) if p)
    failed_word = _t(language, "resolve.failed")
    if not frames:
        return _end(f"{failed_word} {what}")
    file, line = frames[-1]
    where = _t(language, "resolve.file_line").format(file=_base(file), line=line, msg=what)
    said = _end(f"{failed_word} {where}")
    # exception chaînée : la cause d'origine est dans le premier bloc, l'exception finale
    # ne fait souvent que l'envelopper (« job aborted »)
    blocks = _PY_CHAIN.split(output)
    if len(blocks) < 2 or "Traceback (most recent call last):" not in blocks[0]:
        return said
    root_frames = _PY_FRAME.findall(blocks[0])
    root_lines = [l for l in blocks[0].splitlines() if l.strip()]
    root = _PY_EXC.match(root_lines[-1].strip()) if root_lines else None
    if not root or not root_frames:
        return said
    root_what = " ".join(p for p in (root[1], _clean(root[2] or "")) if p)
    root_file, root_line = root_frames[-1]
    root_where = _t(language, "resolve.file_line").format(file=_base(root_file), line=root_line, msg=root_what)
    chained = _end(f"{failed_word} {root_where}, {_t(language, 'resolve.traceback_then')} {what}")
    return chained if len(chained.split()) <= _CHAIN_MAX_WORDS else said


# ---------------------------------------------------------------- tests

_PYTEST_SUMMARY = re.compile(
    r"^=*\s*(\d+ (?:failed|passed|errors?|skipped|xfailed|xpassed|deselected|warnings?)(?:, \d+ \w+)*) in [\d.]+s", re.M)
_PYTEST_FIRST = re.compile(r"^(?:FAILED|ERROR) (\S+)", re.M)
_JEST_SUMMARY = re.compile(r"^Tests:\s+(.+?),\s*\d+ total", re.M)
_JEST_FIRST = re.compile(r"^\s*● (?!Console)(.+)$", re.M)
_JEST_WHERE = re.compile(r"\(([^()\s]+):(\d+):\d+\)")
_CARGO_SUMMARY = re.compile(r"^test result: (?:ok|FAILED)\. (\d+) passed; (\d+) failed", re.M)
_CARGO_FIRST = re.compile(r"^---- (\S+) stdout ----", re.M)
_CARGO_WHERE = re.compile(r"panicked at (?:'.*?', )?([^:\s']+):(\d+):\d+")
# vitest : même idée que Jest (« Tests: »), mais résumé « Tests  N failed | M passed (T) »,
# sans le deux-points, et sans position pour le premier échec (juste « FAIL  fichier > nom »).
_VITEST_SUMMARY = re.compile(r"^\s*Tests\s+(.+?)\s*\(\d+\)\s*$", re.M)
_VITEST_FIRST = re.compile(r"^\s*FAIL\s+(\S+)\s*>\s*(.+?)\s*$", re.M)


def _pytest_collect_error(path: str, output: str) -> str:
    """« fichier, cause » d'une erreur de collecte : la ligne E du bloc « ERROR collecting »."""
    block = re.search(rf"^_+ ERROR collecting {re.escape(path)} _+$(.*?)(?=^_{{3,}} |^={{3,}} |\Z)", output, re.M | re.S)
    cause = re.search(r"^E\s+(.+)$", block[1], re.M) if block else None
    return _base(path) + (", " + _clean(cause[1]) if cause else "")


# pytest : « chemin::test FAILED » de -v quand le résumé court ne liste pas les échecs (-rs) ;
# bloc « ___ test ___ » (ou « ___ ERROR at setup of test ___ ») avec « E   Type: message »,
# dernière ligne « fichier:ligne: Type » ; pytest-timeout : « Failed: Timeout (>Ns) ».
_PYTEST_VERBOSE_FIRST = re.compile(r"^(\S+?\.py::\S+) (?:FAILED|ERROR)\b", re.M)
_PYTEST_SECTION_END = re.compile(r"^(?:_{3,} |={3,})", re.M)
_PYTEST_E_EXC = re.compile(r"^E\s+([A-Za-z_][\w.]*(?:Error|Exception|Exit|Interrupt))(?::\s?(.*))?$", re.M)
_PYTEST_LAST_EXC = re.compile(r"^\S+:\d+: ([A-Za-z_]\w*(?:Error|Exception))\s*$", re.M)
_PYTEST_TIMEOUT = re.compile(r"^E\s+Failed: Timeout \(>([\d.]+)s\) from pytest-timeout", re.M)
_CARGO_BLOCK_END = re.compile(r"^(?:---- |failures:)", re.M)
_RUST_LEFT_RIGHT = re.compile(r"^assertion `left == right` failed.*\n\s*left: (.+)\n\s*right: (.+)$", re.M)
# unittest : « Ran N tests », « OK (skipped=N) », « FAILED (failures=N, errors=N) », blocs du rapport
_UT_RAN = re.compile(r"^Ran (\d+) tests? in [\d.]+s\s*$", re.M)
_UT_RESULT = re.compile(r"^(OK|FAILED)(?: \(([^)]*)\))?\s*$", re.M)
_UT_BLOCK = re.compile(r"^(FAIL|ERROR): (\w+) \(([^)]*)\)", re.M)
_UT_RULE = re.compile(r"^(?:={20,}|-{20,})\s*$", re.M)
_UT_KEYS = {"failures", "errors", "skipped"}
# deno test : « ok | N passed | N failed (Xms) », section « FAILURES » : « nom => ./f:l:c »
_DENO_SUMMARY = re.compile(r"^(?:ok|FAILED) \| (\d+) passed(?: \(\d+ steps?\))? \| (\d+) failed", re.M)
_DENO_FAILURES = re.compile(r"^\s*FAILURES\s*$", re.M)
_DENO_FAILED_AT = re.compile(r"^(.+?) => (?:\./)?(\S+?):(\d+):\d+\s*$", re.M)
_JEST_NO_TESTS = re.compile(r"^No tests found, exiting with code \d+", re.M)
_JEST_FILES_CHECKED = re.compile(r"^\s*(\d+) files? checked\.", re.M)


def _pytest_block(name: str, output: str) -> str:
    head = re.search(rf"^_+ (?:ERROR at (?:setup|teardown) of )?(?:\w+\.)?{re.escape(name)} _+\s*$", output, re.M)
    if not head:
        return ""
    end = _PYTEST_SECTION_END.search(output, head.end())
    return output[head.end():end.start() if end else len(output)]


def _pytest_causes(block: str, language: str) -> list[str]:
    """Cause du premier échec, de la plus détaillée à la plus courte ; vide si le bloc ne la dit pas."""
    if m := _PYTEST_TIMEOUT.search(block):
        return [_t(language, "resolve.d6a.timeout").format(s=_num(m[1], language))]
    if m := _PYTEST_E_EXC.search(block):
        return list(dict.fromkeys([_exc_said(m[1], m[2] or ""), m[1].rsplit(".", 1)[-1]]))
    if found := _PYTEST_LAST_EXC.findall(block):
        return [found[-1]]
    return []


def _rust_values(block: str, language: str) -> list[str]:
    m = _RUST_LEFT_RIGHT.search(block)
    if not m:
        return []
    left, right = _clean(m[1]), _clean(m[2])
    if any(not v or len(v.split()) > 4 or _SYMBOLS.search(v) for v in (left, right)):
        return []
    return [_t(language, "resolve.d6a.left_right").format(left=left, right=right)]


def _first_variants(name: str, file: str | None, line: str | None, causes: list[str], language: str) -> list[str]:
    """« nom, fichier ligne N : cause », de la variante la plus détaillée à la plus courte."""
    variants = []
    for cause in [*causes, ""]:
        if file:
            variants.append(f"{name}, {_where(file, line, cause, language)}")
        else:
            variants.append(f"{name}, {cause}" if cause else name)
    return variants


def _istanbul_lines(output: str) -> str | None:
    """Colonne « % Lines » de la ligne « All files » du tableau texte d'Istanbul (Jest, Vitest)."""
    header = re.search(r"^\s*File\s*\|(.*)$", output, re.M)
    row = re.search(r"^\s*All files\s*\|(.*)$", output, re.M)
    if not (header and row):
        return None
    cols = [c.strip() for c in header[1].split("|")]
    values = [c.strip() for c in row[1].split("|")]
    if "% Lines" not in cols or cols.index("% Lines") >= len(values):
        return None
    value = values[cols.index("% Lines")]
    return value if re.fullmatch(r"\d+(?:\.\d+)?", value) else None


def _unittest(output: str, language: str) -> str | None:
    ran = [*_UT_RAN.finditer(output)]
    result = _UT_RESULT.search(output, ran[-1].end()) if ran else None
    if not result:
        return None
    n = int(ran[-1][1])
    counts = {}
    for part in filter(None, (result[2] or "").split(", ")):
        key, _, value = part.partition("=")
        if key not in _UT_KEYS or not value.isdigit():
            return None
        counts[key] = int(value)
    skipped, bad, errors = counts.get("skipped", 0), counts.get("failures", 0), counts.get("errors", 0)
    if result[1] == "OK":
        if bad or errors or skipped > n:
            return None
        said = _tn(language, n - skipped, "resolve.tests.all_passed", "resolve.tests.all_passed_many")
        if skipped:
            said += ", " + _tn(language, skipped, "resolve.d6a.skipped", "resolve.d6a.skipped_many")
        return said + "."
    if not (bad or errors):
        return None
    block, body = _UT_BLOCK.search(output), ""
    if block:
        rules = [*_UT_RULE.finditer(output, block.end())]
        # la règle de tirets sous l'en-tête ouvre le bloc, la suivante le ferme
        body = output[rules[0].end():rules[1].start()] if len(rules) > 1 else output[block.end():]
    lines = [l.strip() for l in body.splitlines() if l.strip()]
    exc = _PY_EXC.match(lines[-1]) if lines else None
    if block and "_FailedTest" in block[3] and "Failed to import test module" in body and exc:
        return _t(language, "resolve.d6a.import_failed").format(name=block[2], exc=_exc_said(exc[1], exc[2] or ""))
    parts = []
    if bad:
        parts.append(_tn(language, bad, "resolve.d6a.failure", "resolve.d6a.failure_many"))
    if errors:
        parts.append(_tn(language, errors, "resolve.tests.error", "resolve.tests.error_many"))
    head = _t(language, "resolve.failed") + " " + _join(parts, language)
    # sous-tests (subTest) : plus d'échecs que de tests lancés, le total n'aurait plus de sens
    if bad + errors <= n:
        head += _t(language, "resolve.d6a.out_of" if n == 1 else "resolve.d6a.out_of_many").format(n=n)
    if not block:
        return head + "."
    frames = _PY_FRAME.findall(body)
    # un échec (FAIL) est toujours une assertion : seule une erreur (ERROR) dit son exception
    causes = ([_exc_said(exc[1], exc[2] or ""), exc[1].rsplit(".", 1)[-1]] if block[1] == "ERROR" and exc
              else [])
    file, line = (_base(frames[-1][0]), frames[-1][1]) if frames else (None, None)
    variants = [head + _t(language, "resolve.d6a.including").format(name=v) + "."
                for v in _first_variants(block[2], file, line, list(dict.fromkeys(causes)), language)]
    return next((v for v in variants if _fits(v)), variants[-1])


def _tests(first, args, cmd, failed, output, language="fr"):
    at_line = " {file} ligne {line}" if language != "en" else " {file} line {line}"
    counts, collect, coverage, first_fails = {}, "", None, [""]
    if m := [*_PYTEST_SUMMARY.finditer(output)]:
        counts = {w.rstrip("s"): int(n) for n, w in re.findall(r"(\d+) (\w+)", m[-1][1])}
        if f := _PYTEST_FIRST.search(output) or _PYTEST_VERBOSE_FIRST.search(output):
            path, _, name = f[1].partition("::")
            if not name:
                collect = _pytest_collect_error(path, output)
            else:
                test = name.split("::")[-1]
                where = re.search(rf"^{re.escape(path)}:(\d+): ", output, re.M)
                first_fails = _first_variants(test, _base(path) if where else None, where[1] if where else None,
                                              _pytest_causes(_pytest_block(test, output), language), language)
    elif m := _JEST_SUMMARY.search(output):
        counts = {w.rstrip("s"): int(n) for n, w in re.findall(r"(\d+) (\w+)", m[1])}
        coverage = _istanbul_lines(output)
        if f := _JEST_FIRST.search(output):
            where = _JEST_WHERE.search(output, f.end())
            first_fails = [f[1].strip().replace(" › ", ", ") + (
                "," + at_line.format(file=_base(where[1]), line=where[2]) if where else "")]
    elif m := [*_CARGO_SUMMARY.finditer(output)]:
        counts = {"passed": sum(int(x[1]) for x in m), "failed": sum(int(x[2]) for x in m)}
        if f := _CARGO_FIRST.search(output):
            where = _CARGO_WHERE.search(output, f.end())
            stop = _CARGO_BLOCK_END.search(output, f.end())
            block = output[f.end():stop.start() if stop else len(output)]
            first_fails = _first_variants(f[1].split("::")[-1], _base(where[1]) if where else None,
                                          where[2] if where else None, _rust_values(block, language), language)
    elif m := _VITEST_SUMMARY.search(output):
        counts = {w.rstrip("s"): int(n) for n, w in re.findall(r"(\d+) (\w+)", m[1])}
        coverage = _istanbul_lines(output)
        if f := _VITEST_FIRST.search(output):
            first_fails = [f"{f[2]}, {_base(f[1])}"]
    elif _CHAINED.search(cmd):
        return None
    elif m := _DENO_SUMMARY.search(output):
        counts = {"passed": int(m[1]), "failed": int(m[2])}
        if (section := _DENO_FAILURES.search(output)) and (f := _DENO_FAILED_AT.search(output, section.end())):
            first_fails = [f[1].strip() + "," + at_line.format(file=_base(f[2]), line=f[3])]
    elif _UT_RAN.search(output):
        return _unittest(output, language)
    elif _JEST_NO_TESTS.search(output):
        checked = _JEST_FILES_CHECKED.search(output)
        said = _t(language, "resolve.d6a.no_tests")
        if checked:
            key = "resolve.d6a.files_checked" if checked[1] == "1" else "resolve.d6a.files_checked_many"
            said += _t(language, key).format(n=checked[1])
        return f"{_t(language, 'resolve.failed')} {said}." if failed else f"{said}."
    else:
        return None
    bad, errors, ok = counts.get("failed", 0), counts.get("error", 0), counts.get("passed", 0)
    parts = []
    if bad:
        parts.append(_tn(language, bad, "resolve.tests.failed", "resolve.tests.failed_many"))
    if errors:
        parts.append(_tn(language, errors, "resolve.tests.error", "resolve.tests.error_many"))
    if not parts:
        if not ok:
            return None
        said = _tn(language, ok, "resolve.tests.all_passed", "resolve.tests.all_passed_many")
        if coverage:
            said += _t(language, "resolve.d6a.line_coverage").format(pct=_pct(coverage, language))
        # tous les tests passent mais la commande échoue (seuil de couverture, avertissement bloquant)
        return f"{_t(language, 'resolve.failed')} {said}." if failed else f"{said}."
    if ok:
        parts.append(_tn(language, ok, "resolve.tests.passed", "resolve.tests.passed_many"))
    said = _t(language, "resolve.failed") + " " + ", ".join(parts) + "."
    if collect:
        return said + _t(language, "resolve.tests.collect").format(name=collect)
    variants = [said + (_t(language, "resolve.tests.first").format(name=ff) if ff else "") for ff in first_fails]
    return next((v for v in variants if _fits(v)), variants[-1])


# ---------------------------------------------------------------- apt

_APT_LOCK_HOLDER = re.compile(r"(?:Could not get lock|Impossible d'obtenir le verrou) (\S+?)\.? "
                              r"(?:It is held by process|Il est tenu par le processus) (\d+) \(([^)]+)\)")
_APT_ROOT = re.compile(r"are you root|êtes-vous root|superutilisateur|Permission denied|Permission non accordée")
_APT_LOCK = re.compile(r"Could not get lock|Impossible d'obtenir le verrou|Unable to acquire the dpkg")
_APT_MISSING = re.compile(r"(?:Unable to locate package|Impossible de trouver le paquet) (\S+)")
_APT_COUNTS = re.compile(r"(\d+) (?:upgraded|mis à jour), (\d+) (?:newly installed|nouvellement installés), "
                         r"(\d+) (?:to remove|à enlever)")


def _apt(first, args, cmd, failed, output, language="fr"):
    if first == "apt-cache":
        return _apt_cache(args, cmd, failed, output, language)
    if first == "dpkg":
        return _dpkg_list(args, cmd, failed, output, language)
    if first == "apt" and args[:1] == ["list"]:
        return _apt_upgradable(args, cmd, failed, output, language)
    if first not in ("apt", "apt-get", "aptitude"):
        return None
    if failed:
        if m := _APT_LOCK_HOLDER.search(output):
            lock = "dpkg" if "dpkg" in m[1] else "apt"
            return _t(language, "resolve.apt.lock_holder").format(lock=lock, who=m[3], pid=m[2])
        if _APT_ROOT.search(output):
            return _t(language, "resolve.apt.root")
        if _APT_LOCK.search(output):
            return _t(language, "resolve.apt.lock")
        if m := _APT_MISSING.search(output):
            return _t(language, "resolve.apt.missing").format(pkg=m[1])
        return None
    m = _APT_COUNTS.search(output)
    if not m:
        return None
    done = [(int(n), one_key, many_key) for n, (one_key, many_key) in
            zip(m.groups(), (("resolve.apt.upgraded_one", "resolve.apt.upgraded_many"),
                              ("resolve.apt.installed_one", "resolve.apt.installed_many"),
                              ("resolve.apt.removed_one", "resolve.apt.removed_many"))) if int(n)]
    if not done:
        return _t(language, "resolve.apt.up_to_date")
    simulated = _apt_simulated(args)
    if simulated:
        named = _apt_simulated_named(args, output, language)
        if named:
            return _t(language, "resolve.apt.simulation").format(said=named)
    parts = [_apt_count(language, *done[0], simulated)] + [_tn(language, *d) for d in done[1:]]
    said = ", ".join(parts)
    return _t(language, "resolve.apt.simulation").format(said=said) if simulated else said + "."


# apt-get(8) : -s, --simulate, --dry-run, --just-print, --no-act, --recon ne font rien sur
# le système ; les lignes Inst, Conf et Remv décrivent ce qui serait fait.
_APT_SIMULATE_LONG = {"--simulate", "--dry-run", "--just-print", "--no-act", "--recon"}
_APT_VALUE_OPTIONS = {"-o", "-c", "-t", "-a", "--option", "--config-file", "--target-release",
                      "--default-release", "--host-architecture"}
_APT_ACTIONS = {"install": ("Inst", "resolve.apt.installed_one", "resolve.apt.installed_many"),
                "reinstall": ("Inst", "resolve.apt.installed_one", "resolve.apt.installed_many"),
                "remove": ("Remv", "resolve.apt.removed_one", "resolve.apt.removed_many"),
                "purge": ("Purg", "resolve.apt.removed_one", "resolve.apt.removed_many")}


def _apt_simulated(args: list[str]) -> bool:
    return any(a in _APT_SIMULATE_LONG or re.fullmatch(r"-[a-zA-Z]*s[a-zA-Z]*", a) for a in args)


def _apt_count(language: str, count: int, one_key: str, many_key: str, simulated: bool) -> str:
    word = _t(language, one_key if count == 1 else many_key)
    package = _t(language, "resolve.apt.package" if count == 1 else "resolve.apt.packages")
    if simulated:
        word = _t(language, "resolve.apt.would_one" if count == 1 else "resolve.apt.would_many") + " " + word
    return f"{count} {package} {word}"


def _apt_simulated_named(args: list[str], output: str, language: str) -> str | None:
    """Phrase au conditionnel qui nomme les paquets demandés, ou None (on retombe sur les comptes)."""
    words, skip = [], False
    for a in args:
        if skip:
            skip = False
        elif a in _APT_VALUE_OPTIONS:
            skip = True
        elif not a.startswith("-"):
            words.append(a)
    if not words or words[0] not in _APT_ACTIONS:
        return None
    tag, one_key, many_key = _APT_ACTIONS[words[0]]
    acted = re.findall(rf"^{tag} (\S+?)(?::\S+)? ", output, re.M)
    removed = re.findall(r"^(?:Remv|Purg) (\S+)", output, re.M)
    requested = [re.split(r"[=/]", w)[0] for w in words[1:]]
    named = [p for p in requested if p in acted]
    if not named or len(named) > 3:
        return None
    pkgs = named[0] if len(named) == 1 else ", ".join(named[:-1]) + _t(language, "resolve.apt.and") + named[-1]
    if tag != "Inst" and len(acted) > len(named):
        return (_apt_count(language, len(acted), one_key, many_key, True)
                + _t(language, "resolve.apt.sim_including").format(pkgs=pkgs))
    one = len(named) == 1
    said = _t(language, "resolve.apt.sim_named_one" if one else "resolve.apt.sim_named_many").format(
        pkgs=pkgs, word=_t(language, one_key if one else many_key))
    if len(acted) > len(named):
        said += _t(language, "resolve.apt.sim_deps_one" if one else "resolve.apt.sim_deps_many")
    if tag == "Inst" and removed:
        said += ", " + _apt_count(language, len(removed), "resolve.apt.removed_one", "resolve.apt.removed_many", True)
    return said


# ---------------------------------------------------------------- listes apt et dpkg (D6 lot C)
#
# Listes et compteurs complets seulement : un tube (head, grep, wc) tronque ou transforme la
# liste, on se tait alors, comme devant toute ligne hors format. Traductions gettext : espace
# insécable avant les deux-points.

_APT_UPGRADABLE_ROW = re.compile(
    r"^(\S+?)/\S+ \S+ \S+ \[(?:upgradable from|pouvant être mis à jour depuis)[ \xa0]?: [^\]]+\]$")
_APT_LIST_NOISE = re.compile(r"^(?:Listing\.\.\.|En train de lister|WARNING: apt does not have a stable CLI|AVERTISSEMENT)")
_APT_SEARCH_ROW = re.compile(r"^(\S+) - \S")
_POLICY_HEAD = re.compile(r"^(\S+):$")
_POLICY_INSTALLED = re.compile(r"^\s+(?:Installed|Installé)[ \xa0]?: (\S+)$")
_POLICY_CANDIDATE = re.compile(r"^\s+(?:Candidate|Candidat)[ \xa0]?: (\S+)$")
# apt-cache policy liste les versions de la plus récente à la plus ancienne
_POLICY_VERSION = re.compile(r"^ (?:\*\*\*| {3}) (\S+) -?\d+$")
_POLICY_OTHER = re.compile(r"^\s+(?:Version table|Table de version)[ \xa0]?:$|^\s+-?\d+ \S")
_POLICY_NONE = {"(none)", "(aucun)", "(aucune)"}
_POLICY_KINDS = ("upgrade", "current", "missing")
_DPKG_ROW = re.compile(r"^([uihrp][a-zA-Z])[R ]?\s+(\S+)\s+\S+\s+\S+")


def _apt_upgradable(args, cmd, failed, output, language):
    if failed or "|" in cmd or not {"--upgradable", "--upgradeable"} & set(args):
        return None
    names = []
    for line in (l.strip() for l in output.splitlines()):
        if not line or _APT_LIST_NOISE.match(line):
            continue
        if not (m := _APT_UPGRADABLE_ROW.match(line)):
            return None
        names.append(m[1])
    if not names:
        return None
    head = _tn(language, len(names), "resolve.d6c.apt.upgradable_one", "resolve.d6c.apt.upgradable_many")
    return head + _names_tail(language, names, True) + "."


def _apt_cache(args, cmd, failed, output, language):
    if failed or "|" in cmd:
        return None
    if args[:1] == ["search"]:
        names = []
        for line in (l for l in output.splitlines() if l.strip()):
            if not (m := _APT_SEARCH_ROW.match(line)):
                return None
            names.append(m[1])
        if not names:
            return None
        head = _tn(language, len(names), "resolve.d6c.apt.found_one", "resolve.d6c.apt.found_many")
        return head + _names_tail(language, names, True) + "."
    if args[:1] == ["policy"] and len(args) > 1:
        return _apt_policy(output, language)
    return None


def _apt_policy(output: str, language: str) -> str | None:
    blocks = []
    for line in (l for l in output.splitlines() if l.strip()):
        if m := _POLICY_HEAD.match(line):
            blocks.append({"name": m[1], "inst": None, "cand": None, "versions": []})
        elif not blocks:
            return None
        elif m := _POLICY_INSTALLED.match(line):
            blocks[-1]["inst"] = m[1]
        elif m := _POLICY_CANDIDATE.match(line):
            blocks[-1]["cand"] = m[1]
        elif m := _POLICY_VERSION.match(line):
            blocks[-1]["versions"].append(m[1])
        elif not _POLICY_OTHER.match(line):
            return None
    groups = {"upgrade": [], "current": [], "missing": []}
    for b in blocks:
        inst, cand, versions = b["inst"], b["cand"], b["versions"]
        if inst is None or cand is None or cand in _POLICY_NONE:
            return None
        if inst in _POLICY_NONE:
            groups["missing"].append(b)
        elif inst == cand:
            groups["current"].append(b)
        elif inst in versions and cand in versions and versions.index(cand) < versions.index(inst):
            groups["upgrade"].append(b)
        else:
            return None
    if len(blocks) == 1:
        b = blocks[0]
        kind = next(k for k in _POLICY_KINDS if groups[k])
        return _t(language, f"resolve.d6c.apt.policy_one_{kind}").format(pkg=b["name"], inst=b["inst"], cand=b["cand"])
    parts = [_t(language, f"resolve.d6c.apt.policy_{kind}_{'one' if len(groups[kind]) == 1 else 'many'}").format(
        names=_join([b["name"] for b in groups[kind]], language)) for kind in _POLICY_KINDS if groups[kind]]
    return _t(language, "resolve.d6c.semicolon").join(parts) + "." if parts else None


def _dpkg_list(args, cmd, failed, output, language):
    if failed or "|" in cmd or args[:1] not in (["-l"], ["--list"]):
        return None
    lines = output.splitlines()
    start = next((i for i, l in enumerate(lines) if l.startswith("+++-")), None)
    if start is None:
        return None
    rows = []
    for line in (l for l in lines[start + 1:] if l.strip()):
        if not (m := _DPKG_ROW.match(line)):
            return None
        rows.append((m[1], m[2].split(":")[0]))
    if not rows:
        return None
    names = [name for state, name in rows if state[1] == "i"]
    if not names:
        return (_t(language, "resolve.d6c.dpkg.none_one").format(name=rows[0][1]) if len(rows) == 1
                else _t(language, "resolve.d6c.dpkg.none_many").format(n=len(rows)))
    head = _tn(language, len(names), "resolve.pip.package_installed", "resolve.pip.packages_installed")
    if len(names) < len(rows):
        head += _t(language, "resolve.d6c.dpkg.of").format(n=len(rows))
    return head + _names_tail(language, names, True) + "."


# ---------------------------------------------------------------- pip

def _pip_name(spec: str) -> str:
    return re.split(r"[<>=!~\[;@ ]", spec)[0].lower().replace("_", "-")


_PIP_CONFLICT = re.compile(r"^ERROR: Cannot install (.+?) because these package versions have conflicting dependencies",
                           re.M)
_PIP_PINNED = re.compile(r"[A-Za-z0-9][\w.-]*(?:==[\w.+!-]+)?")
_PIP_BUILD = re.compile(r"Failed to build '([^']+)'|Failed building wheel for (\S+)|Could not build wheels for ([^\s,]+)"
                        r"|based projects \(([^)]+)\)")
_PIP_FROM_REQUIREMENTS = re.compile(r"^Collecting (\S+) \(from -r [^\n]*\(line \d+\)\)$", re.M)


def _pip(first, args, cmd, failed, output, language="fr"):
    if first == "uv":
        return _uv(args, cmd, failed, output, language)
    if first == "poetry":
        return _poetry(args, cmd, failed, output, language)
    is_pip = first in ("pip", "pip3") or (first.startswith("python") and args[:2] == ["-m", "pip"])
    if is_pip and "list" in args and {"--outdated", "-o"} & set(args):
        return _pip_outdated(cmd, failed, output, language)
    if not is_pip or "install" not in args:
        return None
    wanted = [_pip_name(a) for a in args[args.index("install") + 1:] if not a.startswith("-")]
    if "externally-managed-environment" in output:
        return _t(language, "resolve.pip.externally_managed")
    if "ResolutionImpossible" in output:
        return _pip_conflict(output, language) or _t(language, "resolve.pip.resolution_impossible")
    if m := re.search(r"Could not find a version that satisfies the requirement (\S+)", output):
        return _t(language, "resolve.pip.no_version").format(pkg=_pip_name(m[1]))
    if failed:
        if m := _PIP_BUILD.search(output):
            name = next(g for g in m.groups() if g)
            return Skeleton(_t(language, "resolve.d6c.pip.build").format(pkg=_base(name) if "/" in name else name))
        return None
    if m := re.search(r"^Successfully installed (.+)$", output, re.M):
        pkgs = [p.rsplit("-", 1) for p in m[1].split()]
        if said := _pip_requirements(args, output, pkgs, language):
            return said
        mine = [p for p in pkgs if p[0].lower().replace("_", "-") in wanted]
        if len(mine) == 1:
            deps = len(pkgs) - 1
            head = _t(language, "resolve.pip.installed_one").format(pkg=mine[0][0], ver=mine[0][1])
            if not deps:
                return head + "."
            dep_word = _tn(language, deps, "resolve.pip.dep", "resolve.pip.deps")
            sep = ", with " if language == "en" else ", avec "
            return f"{head}{sep}{dep_word}."
        noun = _tn(language, len(pkgs), "resolve.pip.package_installed", "resolve.pip.packages_installed")
        sep = ": " if language == "en" else " : "
        return f"{noun}{sep}" + ", ".join(p[0] for p in pkgs[:3]) + "."
    satisfied = {_pip_name(x) for x in re.findall(r"^Requirement already satisfied: (\S+)", output, re.M)}
    if wanted and all(w in satisfied for w in wanted):
        suffix = _t(language, "resolve.pip.already_one" if len(wanted) == 1 else "resolve.pip.already_many")
        return ", ".join(wanted) + suffix
    return None


def _pip_requirements(args, output, pkgs, language):
    """pip install -r : les paquets demandés par le fichier, pas les trois premiers par ordre alphabétique."""
    files = [args[i + 1] for i, a in enumerate(args[:-1]) if a in ("-r", "--requirement")]
    if len(files) != 1:
        return None
    installed = {p[0].lower().replace("_", "-") for p in pkgs}
    named = [n for n in dict.fromkeys(_pip_name(s) for s in _PIP_FROM_REQUIREMENTS.findall(output)) if n in installed]
    if not named:
        return None
    head = _tn(language, len(pkgs), "resolve.pip.package_installed", "resolve.pip.packages_installed")
    head += _t(language, "resolve.d6c.from").format(file=_base(files[0]))
    return head + _names_tail(language, named, len(named) == len(pkgs)) + "."


def _pip_conflict(output, language):
    m = _PIP_CONFLICT.search(output)
    specs = re.split(r", | and ", m[1]) if m else []
    if not specs or not all(_PIP_PINNED.fullmatch(s) for s in specs):
        return None
    return _t(language, "resolve.d6c.pip.conflict").format(pkgs=_join([s.replace("==", " ") for s in specs], language))


def _pip_outdated(cmd, failed, output, language):
    lines = [l for l in output.splitlines() if l.strip() and not l.startswith("[notice]")]
    if failed or "|" in cmd or len(lines) < 3 or lines[0].split()[:3] != ["Package", "Version", "Latest"]:
        return None
    if set(lines[1]) - {"-", " "}:
        return None
    items = []
    for cols in (l.split() for l in lines[2:]):
        if len(cols) < 3 or not (cols[1][:1].isdigit() and cols[2][:1].isdigit()):
            return None
        items.append(cols[0] + _t(language, "resolve.d6c.to") + cols[2])
    return _outdated(items, language)


# uv : lignes de bilan documentées ; toute autre ligne (warning, error, sortie d'un script)
# laisse la phrase au modèle
_UV_LINE = re.compile(r"^\s*(?:Using (?:CPython|Python|PyPy)|Creating virtual environment|Resolved|Prepared|Installed"
                      r"|Uninstalled|Audited|Downloading|Downloaded|Built|Building|Updated|Bytecode compiled"
                      r"|Activate with)\b|^ [+~-] \S")
_UV_PINNED = re.compile(r"^(?:\s|#|[\w.-]+(?:\[[\w,.-]+\])?==\S+)")
_UV_VALUE_OPTIONS = {"-o", "--output-file", "-c", "--constraint", "--override", "-p", "--python", "--python-version"}


def _uv_count(word: str, output: str) -> int:
    m = re.search(rf"^{word} (\d+) packages?\b", output, re.M)
    return int(m[1]) if m else 0


def _uv(args, cmd, failed, output, language):
    if failed or "|" in cmd or not args:
        return None
    lines = [l for l in output.splitlines() if l.strip()]
    if args[:2] == ["pip", "compile"]:
        resolved = _uv_count("Resolved", lines[0]) if lines else 0
        if not resolved or not all(_UV_PINNED.match(l) for l in lines[1:]):
            return None
        files, skip = [], False
        for a in args[2:]:
            if skip:
                skip = False
            elif a in _UV_VALUE_OPTIONS:
                skip = True
            elif not a.startswith("-"):
                files.append(a)
        head = _tn(language, resolved, "resolve.d6c.uv.resolved_one", "resolve.d6c.uv.resolved_many")
        return head + (_t(language, "resolve.d6c.from").format(file=_base(files[0])) if len(files) == 1 else "") + "."
    start = 1 if args[0] in ("add", "sync", "remove") else 2 if args[:2] in (["pip", "install"], ["pip", "sync"],
                                                                           ["pip", "uninstall"]) else 0
    if not start or not lines or not all(_UV_LINE.match(l) for l in lines):
        return None
    wanted = {_pip_name(a) for a in args[start:] if not a.startswith("-")}
    installed, uninstalled = _uv_count("Installed", output), _uv_count("Uninstalled", output)
    mine = [f"{n} {v}" for n, v in re.findall(r"^ \+ ([\w.-]+)==(\S+)$", output, re.M) if _pip_name(n) in wanted]
    parts = []
    if installed == 1 and len(mine) == 1:
        parts.append(_t(language, "resolve.d6c.uv.installed_one").format(pkg=mine[0]))
    elif installed:
        head = _tn(language, installed, "resolve.pip.package_installed", "resolve.pip.packages_installed")
        parts.append(head + (_t(language, "resolve.d6c.including") + _join(mine[:3], language) if mine else ""))
    if uninstalled:
        parts.append(_tn(language, uninstalled, "resolve.d6c.uv.uninstalled_one", "resolve.d6c.uv.uninstalled_many"))
    if parts:
        return _t(language, "resolve.d6c.semicolon").join(parts) + "."
    if audited := _uv_count("Audited", output):
        checked = _tn(language, audited, "resolve.d6c.uv.checked_one", "resolve.d6c.uv.checked_many")
        return f"{_t(language, 'resolve.d6c.up_to_date')}, {checked}."
    return None


_POETRY_LINE = re.compile(r"^(?:Installing dependencies from lock file|Updating dependencies|Resolving dependencies"
                          r"|Creating virtualenv|Using virtualenv|Package operations:|Writing lock file"
                          r"|No dependencies to install or update|Installing the current project:)"
                          r"|^\s+- (?:Installing|Updating|Removing|Downgrading) ")


def _poetry(args, cmd, failed, output, language):
    if failed or "|" in cmd or args[:1] not in (["install"], ["add"], ["update"]):
        return None
    lines = [l for l in output.splitlines() if l.strip()]
    if not lines or not all(_POETRY_LINE.match(l) for l in lines):
        return None
    parts = []
    if ops := re.search(r"^Package operations: (\d+) installs?, (\d+) updates?, (\d+) removals?", output, re.M):
        installs, updates, removals = map(int, ops.groups())
        if installs:
            parts.append(_tn(language, installs, "resolve.pip.package_installed", "resolve.pip.packages_installed"))
        if updates:
            parts.append(f"{updates} {_t(language, 'resolve.d6c.poetry.updated')}")
        if removals:
            parts.append(_tn(language, removals, "resolve.d6c.poetry.removed_one", "resolve.d6c.poetry.removed_many"))
    said = ", ".join(parts)
    if not said and "No dependencies to install or update" in output:
        said = _t(language, "resolve.d6c.poetry.up_to_date")
    if project := re.search(r"^Installing the current project: (\S+) \((\S+)\)", output, re.M):
        mine = _t(language, "resolve.d6c.poetry.project").format(name=project[1], ver=project[2])
        said = said + _t(language, "resolve.d6c.semicolon") + mine if said else mine[:1].upper() + mine[1:]
    return said + "." if said else None


# ---------------------------------------------------------------- npm, pnpm (D6 lot C)
#
# Code seul quand chaque ligne de la sortie est une ligne de bilan documentée (npm 10,
# pnpm 9 et 10) ; une autre ligne (script postinstall, avertissement ERESOLVE) peut porter
# le fait utile : le bilan reste un gabarit et le modèle dit le reste.

_NPM_SUMMARY = re.compile(r"^(?:(?:added|removed|changed) \d+ packages?\b|up to date\b).*$", re.M)
_NPM_CHANGE = re.compile(r"(added|removed|changed) (\d+) packages?")
_NPM_VULNS = re.compile(r"^(?:found )?(\d+) vulnerabilit(?:y|ies)(?: \(([^)]*)\))?$", re.M)
_NPM_VULNS_ONE = re.compile(r"^(\d+) (info|low|moderate|high|critical) severity vulnerabilit(?:y|ies)$", re.M)
_PNPM_VULNS = re.compile(r"^(\d+) vulnerabilit(?:y|ies) found\s*\n\s*Severity: (.+)$", re.M)
_NPM_SEVERITY = re.compile(r"(\d+) (info|low|moderate|high|critical)")
_NPM_DEPRECATED = re.compile(r"^(?:npm (?:warn|WARN)|\s*(?:\[WARN\]|WARN)) +deprecated (@?[^@\s]+)@", re.M)
# chaque bloc du rapport se termine par son chemin node_modules ; la ligne « Severity: » manque parfois
_NPM_AUDIT_PKG = re.compile(r"^\s*node_modules/(?:\S*/node_modules/)?(@[\w.-]+/[\w.-]+|[\w.-]+)$", re.M)
_NPM_INSTALL_LINE = re.compile(
    r"^(?:added|removed|changed|up to date|audited)\b|^\d+ packages? (?:is|are) looking for funding"
    r"|^\s+run `npm fund`|^(?:found )?\d+ (?:\w+ severity )?vulnerabilit|^To address |^\s+npm audit fix"
    r"|^Run `npm audit`|^npm (?:warn|WARN) deprecated |^npm notice|^Some issues need review|^a different dependency")
_PNPM_INSTALL_LINE = re.compile(
    r"^(?:Packages: |Progress: |Packages are (?:hard linked|cloned|copied|reflinked)|Done in |Already up to date"
    r"|Lockfile is up to date|Downloading |(?:dev|optional|peer)?[dD]ependencies:$|[+-] \S|[+-]+$|✓ )"
    r"|^\s+(?:Content-addressable store|Virtual store) is at|^\s*[╭│╰]|^\s*(?:\[WARN\]|WARN)\s+deprecated @?[^@\s]+@")
_NPM_INSTALL_SUBS = {"install", "i", "in", "add", "ci", "update", "up", "upgrade", "remove", "rm", "uninstall", "un"}
_NPM_ENGINE_REQUIRED = re.compile(r'notsup Required: \{"node":"([^"]+)"\}')
_NPM_ENGINE_ACTUAL = re.compile(r'notsup Actual: +\{.*"node":"v?([^"]+)"')
_NPM_ENGINE_PKG = re.compile(r"Not compatible with your version of node/npm: (@?[^@\s]+)")
_NPM_NOT_IN_REGISTRY = re.compile(r"'(@?[^@'\s]+)@[^']*' is not in this registry|^(@?\S+) is not in the npm registry", re.M)
_NPM_CI_SYNC = re.compile(r"can only install packages when your package\.json and package-lock\.json")
_NPM_CI_MISSING = re.compile(r"^npm (?:error|ERR!) Missing: (@?[^@\s]+)@(\S+) from lock file", re.M)


def _npm(first, args, cmd, failed, output, language="fr"):
    if first not in ("npm", "pnpm") or "|" in cmd:
        return None
    sub = next((a for a in args if not a.startswith("-")), "")
    if sub == "audit" and "fix" not in args:
        return _npm_audit(failed, output, language)
    if sub == "audit":
        sub = "update"
    if sub == "outdated":
        return _js_outdated(output, language)
    if sub not in _NPM_INSTALL_SUBS:
        return None
    if failed:
        return _npm_error(output, language)
    lines = [l for l in output.splitlines() if l.strip()]
    if first == "pnpm":
        said, known = _pnpm_counts(output, language), _PNPM_INSTALL_LINE
    else:
        said, known = _npm_counts(output, language), _NPM_INSTALL_LINE
    if not said:
        return None
    if deprecated := list(dict.fromkeys(_NPM_DEPRECATED.findall(output))):
        key = "resolve.d6c.npm.deprecated_one" if len(deprecated) == 1 else "resolve.d6c.npm.deprecated_many"
        said += _t(language, key).format(names=_capped(deprecated, language))
    return said if all(known.match(l) for l in lines) else Skeleton(said)


def _npm_counts(output, language):
    summary = _NPM_SUMMARY.search(output)
    if not summary:
        return None
    parts = [_tn(language, int(n), f"resolve.d6c.npm.{verb}_one", f"resolve.d6c.npm.{verb}_many")
             for verb, n in _NPM_CHANGE.findall(summary[0])]
    if not parts and summary[0].startswith("up to date"):
        parts.append(_t(language, "resolve.d6c.up_to_date"))
    if vulns := _npm_vulns(output, language):
        parts.append(vulns)
    return ", ".join(parts) + "." if parts else None


def _pnpm_counts(output, language):
    if m := re.search(r"^Packages: ([+-]\d+)(?: ([+-]\d+))?\s*$", output, re.M):
        parts = [_tn(language, int(g[1:]), *(("resolve.d6c.npm.added_one", "resolve.d6c.npm.added_many") if g[0] == "+"
                                             else ("resolve.d6c.npm.removed_one", "resolve.d6c.npm.removed_many")))
                 for g in m.groups() if g]
        return ", ".join(parts) + "."
    if re.search(r"^Already up to date", output, re.M):
        return _t(language, "resolve.d6c.up_to_date") + "."
    return None


def _severity(language: str, severity: str, n: int) -> str:
    return _t(language, f"resolve.d6c.npm.{severity}_{'one' if n == 1 else 'many'}")


def _npm_vulns(output: str, language: str) -> str | None:
    if m := _NPM_VULNS_ONE.search(output):
        n = int(m[1])
        vuln = _t(language, "resolve.d6c.npm.vuln_one" if n == 1 else "resolve.d6c.npm.vuln_many")
        return _t(language, "resolve.d6c.npm.one_severity").format(n=n, vuln=vuln, sev=_severity(language, m[2], n))
    if m := _PNPM_VULNS.search(output) or _NPM_VULNS.search(output):
        n, detail = int(m[1]), m[2] or ""
    else:
        return None
    if not n:
        return _t(language, "resolve.d6c.npm.no_vuln")
    head = _tn(language, n, "resolve.d6c.npm.vuln_one", "resolve.d6c.npm.vuln_many")
    counts = _NPM_SEVERITY.findall(detail)
    if not counts:
        return head
    return head + _t(language, "resolve.d6c.colon") + ", ".join(
        f"{c} {_severity(language, s, int(c))}" for c, s in counts)


def _npm_audit(failed, output, language):
    vulns = _npm_vulns(output, language)
    if not vulns:
        return None
    said = (_t(language, "resolve.failed") + " " if failed else "") + vulns[:1].upper() + vulns[1:] + "."
    names = list(dict.fromkeys(_NPM_AUDIT_PKG.findall(output)))
    total = _PNPM_VULNS.search(output) or _NPM_VULNS.search(output) or _NPM_VULNS_ONE.search(output)
    # npm compte un paquet vulnérable par vulnérabilité : un écart signale un bloc mal lu
    if not names or not total or len(names) != int(total[1]):
        return said
    if len(names) <= 4:
        return said + _t(language, "resolve.d6c.npm.affected_all").format(names=_join(names, language))
    return said + _t(language, "resolve.d6c.npm.affected_some").format(n=len(names), names=_join(names[:3], language))


def _npm_error(output, language):
    if m := _NPM_ENGINE_REQUIRED.search(output):
        actual, pkg = _NPM_ENGINE_ACTUAL.search(output), _NPM_ENGINE_PKG.search(output)
        if not (actual and pkg):
            return None
        if at_least := re.fullmatch(r">= ?v?(\d[\w.]*)", m[1]):
            required = _t(language, "resolve.d6c.npm.at_least").format(v=at_least[1])
        elif re.fullmatch(r"v?\d[\w.]*", m[1]):
            required = m[1].lstrip("v")
        else:
            return None
        return _t(language, "resolve.d6c.npm.engine").format(pkg=pkg[1], req=required, act=actual[1])
    if "404" in output and (m := _NPM_NOT_IN_REGISTRY.search(output)):
        return _t(language, "resolve.d6c.npm.not_in_registry").format(pkg=m[1] or m[2])
    if _NPM_CI_SYNC.search(output):
        said = _t(language, "resolve.d6c.npm.ci_sync")
        missing = _NPM_CI_MISSING.findall(output)
        if missing and not re.search(r"^npm (?:error|ERR!) Invalid: ", output, re.M):
            first = f"{missing[0][0]} {missing[0][1]}"
            said += (_t(language, "resolve.d6c.npm.ci_missing_one").format(pkg=first) if len(missing) == 1
                     else _t(language, "resolve.d6c.npm.ci_missing_many").format(n=len(missing), pkg=first))
        return said + "."
    return None


def _js_outdated(output, language):
    lines = [l for l in output.splitlines() if l.strip()]
    if not lines:
        return None
    if lines[0].lstrip().startswith("┌"):
        rows = [[c.strip() for c in l.strip().strip("│").split("│")] for l in lines if l.lstrip().startswith("│")]
    else:
        rows = [l.split() for l in lines]
    if not rows or rows[0][:2] != ["Package", "Current"] or "Latest" not in rows[0]:
        return None
    latest = rows[0].index("Latest")
    items = []
    for row in rows[1:]:
        if len(row) <= latest or not row[0] or not row[latest]:
            return None
        items.append(row[0].split()[0] + _t(language, "resolve.d6c.to") + row[latest])
    return _outdated(items, language) if items else None


# ---------------------------------------------------------------- Homebrew (D6 lot C)

_BREW_OUTDATED_ROW = re.compile(r"^(\S+) \((.+)\) (?:<|!=) (\S+)$")
_BREW_NAME = re.compile(r"^[\w@.+-]+(?:/[\w@.+-]+)*$")


def _brew(first, args, cmd, failed, output, language="fr"):
    if first != "brew" or not args or "|" in cmd:
        return None
    sub, rest = args[0], args[1:]
    lines = [l.strip() for l in output.splitlines() if l.strip()]
    if sub == "doctor" and failed:
        n = len(re.findall(r"^Warning: ", output, re.M))
        if not n:
            return None
        count = _tn(language, n, "resolve.d6c.brew.warning_one", "resolve.d6c.brew.warning_many")
        return Skeleton("brew doctor" + _t(language, "resolve.d6c.colon") + count + ".")
    if failed or not lines:
        return None
    if sub == "outdated" and not any(a.startswith("--json") for a in rest):
        rows = [_BREW_OUTDATED_ROW.match(l) for l in lines]
        if all(rows):
            return _outdated([m[1] + _t(language, "resolve.d6c.to") + m[3] for m in rows], language)
        return _outdated(lines, language) if all(_BREW_NAME.match(l) for l in lines) else None
    if sub == "uses":
        targets = [a for a in rest if not a.startswith("-")]
        names = output.split()
        if len(targets) != 1 or not all(_BREW_NAME.match(n) for n in names):
            return None
        kind = "uses_installed" if "--installed" in rest else "uses"
        head = _tn(language, len(names), f"resolve.d6c.brew.{kind}_one", f"resolve.d6c.brew.{kind}_many")
        return head.format(pkg=targets[0]) + _names_tail(language, names, True) + "."
    return None


# ---------------------------------------------------------------- git

_GIT_CONFLICT = re.compile(r"^(?:CONFLICT|CONFLIT) \([^)]*\) ?: .*?(?:Merge conflict in|Conflit de fusion dans) (.+)$", re.M)
_GIT_REJECTED = re.compile(r"\[(?:rejected|rejeté)\]\s+(\S+) -> \S+ \(([^)]+)\)")
_GIT_REMOTE_REJECTED = re.compile(r"\[remote rejected\]\s+(\S+) -> \S+ \(([^)]+)\)")
_GIT_PUSHED = re.compile(r"^\s+(?:[0-9a-f]{6,}\.\.\.?[0-9a-f]{6,}|\* \[new branch\])\s+(\S+) -> \S+", re.M)
_GIT_BEHIND_REASONS = ("fetch first", "non-fast-forward", "récupérer d'abord", "non en avance rapide")
_GIT_DIFFSTAT = re.compile(
    r"(?P<files>\d+) (?:fichiers? modifiés?|files? changed)"
    r"(?:, (?P<ins>\d+) insertions?\(\+\))?"
    r"(?:, (?P<del>\d+) (?:suppressions?|deletions?)\(-\))?")
_GIT_LOG_ONELINE_LINE = re.compile(r"^[0-9a-f]{7,40} ")
_GIT_PULL_FF = re.compile(r"Fast-forward|Avance rapide")
_GIT_CLONE_AUTH = re.compile(r"(?:Authentication failed|[Éé]chec d'authentification) (?:for|pour) '([^']+)'")
_GIT_SECTIONS = (
    (re.compile(r"^(?:Changes to be committed|Modifications qui seront validées)\s*:"),
     "resolve.git.staged", "resolve.git.staged_many"),
    (re.compile(r"^(?:Changes not staged for commit|Modifications qui ne seront pas validées)\s*:"),
     "resolve.git.modified", "resolve.git.modified_many"),
    (re.compile(r"^(?:Untracked files|Fichiers non suivis)\s*:"),
     "resolve.git.untracked", "resolve.git.untracked_many"),
    (re.compile(r"^(?:Unmerged paths|Chemins non fusionnés)\s*:"),
     "resolve.git.conflicting", "resolve.git.conflicting_many"),
)


# D6 lot C : messages de git (builtin/push.c, merge.c, wt-status.c, ref-filter.c) et de gh,
# en anglais et dans la traduction française de git (espace insécable avant les deux-points)
_GIT_HOST = re.compile(r"Could not resolve hostname (\S+?):|Could not resolve host: ([^\s'\"]+)")
_GIT_FF_IMPOSSIBLE = re.compile(r"Not possible to fast-forward|[Pp]as possible d'avancer rapidement"
                                r"|[Ii]mpossible d'avancer rapidement")
_GIT_DIVERGING = re.compile(r"Diverging branches|branches divergentes")
_GIT_NO_UPSTREAM = re.compile(r"(?:The current branch|La branche courante) (\S+) (?:has no upstream branch|n'a pas de branche amont)")
_GIT_SET_UPSTREAM = re.compile(r"^\s+(git push --set-upstream \S+ \S+)\s*$", re.M)
_GIT_DETACHED_NOTE = re.compile(r"detached HEAD|HEAD détachée")
_GIT_HEAD_AT = re.compile(r"^(?:HEAD is now at|HEAD est maintenant (?:à|sur)) ([0-9a-f]{7,40}) (.+)$", re.M)
_GIT_BRANCH_FLAGS = {"-a", "--all", "-r", "--remotes", "-v", "-vv", "--verbose", "--list", "-l", "--no-color"}
_GIT_BRANCH_LINE = re.compile(r"^([*+ ]) (\S+)")
_GIT_BRANCH_DETACHED = re.compile(r"^\* \((?:HEAD detached at|HEAD détachée sur) (\S+?)\)")
_GIT_BRANCH_TRACK = re.compile(r"^[*+ ] \S+\s+[0-9a-f]{7,40} \[([^\]]+)\]")
_GIT_TRACK_STATES = (("gone|disparue", "resolve.d6c.git.gone"), (r"ahead \d+|en avance de \d+", "resolve.d6c.git.ahead"),
                     (r"behind \d+|en retard de \d+", "resolve.d6c.git.behind"))
_GIT_REBASING = re.compile(r"You are currently rebasing branch '([^']+)' on '([^']+)'"
                           r"|Vous êtes en train de rebaser la branche '([^']+)' sur '([^']+)'")
_GIT_REBASE_INTERACTIVE = re.compile(r"^(?:interactive rebase in progress|rebasage interactif en cours)", re.M)
_GIT_REBASE_REMAINING = re.compile(r"\((\d+) (?:remaining commands?|commandes? restantes?)\)")
_GIT_UNMERGED_FILE = re.compile(
    r"^\t(?:both modified|both added|both deleted|added by us|added by them|deleted by us|deleted by them"
    r"|modifié des deux côtés|ajouté de deux côtés|ajouté des deux côtés|supprimé des deux côtés|ajouté par nous"
    r"|ajouté par eux|supprimé par nous|supprimé par eux)[ \xa0]?:\s+(.+)$", re.M)
_GIT_COMMIT = re.compile(r"^commit ([0-9a-f]{7,40})\b", re.M)
_GIT_STAT_FILE = re.compile(r"^ (\S.*?)\s+\|\s+(?:\d+|Bin\b)", re.M)


def _git_branch_list(rest, output, language):
    remote_only = bool({"-r", "--remotes"} & set(rest))
    locals_, remotes, current = [], 0, ""
    for line in (l for l in output.splitlines() if l.strip()):
        if m := _GIT_BRANCH_DETACHED.match(line):
            current = ", " + _t(language, "resolve.git.detached").format(b=m[1])
            continue
        m = _GIT_BRANCH_LINE.match(line)
        if not m or m[2].startswith("("):
            return None
        if " -> " in line:
            continue
        if remote_only or m[2].startswith("remotes/"):
            remotes += 1
            continue
        locals_.append((m[2], line))
        if m[1] == "*":
            current = _t(language, "resolve.d6c.git.current").format(b=m[2])
    if remote_only:
        return _tn(language, remotes, "resolve.d6c.git.remote_branch_one", "resolve.d6c.git.remote_branch_many") + "." \
            if remotes else None
    if not locals_:
        return None
    said = _tn(language, len(locals_), "resolve.d6c.git.local_one", "resolve.d6c.git.local_many") + current
    if remotes:
        said += _t(language, "resolve.d6c.semicolon") + _tn(language, remotes, "resolve.d6c.git.remote_one",
                                                            "resolve.d6c.git.remote_many")
    said += "."
    states = {key: [] for _, key in _GIT_TRACK_STATES}
    for name, line in locals_:
        if track := _GIT_BRANCH_TRACK.match(line):
            state = re.split(r"[ \xa0]?: ", track[1], maxsplit=1)[-1]
            for pattern, key in _GIT_TRACK_STATES:
                if re.search(rf"(?:^|, )(?:{pattern})(?:,|$)", state):
                    states[key].append(name)
    for key, names in states.items():
        if names:
            said += _t(language, key).format(names=_capped(names, language))
    return said


def _git_rebase_status(output: str, language: str) -> str | None:
    m = _GIT_REBASING.search(output)
    if not m:
        return None
    branch, onto = (m[1], m[2]) if m[1] else (m[3], m[4])
    key = "resolve.d6c.git.rebase_interactive" if _GIT_REBASE_INTERACTIVE.search(output) else "resolve.d6c.git.rebase"
    said = _t(language, key).format(b=branch, onto=onto)
    if files := list(dict.fromkeys(_base(f) for f in _GIT_UNMERGED_FILE.findall(output))):
        said += _t(language, "resolve.d6c.git.conflict_in").format(names=_capped(files, language))
    if remaining := _GIT_REBASE_REMAINING.search(output):
        said += ", " + _tn(language, int(remaining[1]), "resolve.d6c.git.remaining_one", "resolve.d6c.git.remaining_many")
    return said + "."


def _git_log_stat(output: str, language: str) -> str | None:
    commits = [*_GIT_COMMIT.finditer(output)]
    if not commits:
        return None
    block = output[commits[0].end(): commits[1].start() if len(commits) > 1 else len(output)]
    subject = re.search(r"^    (\S.*)$", block, re.M)
    if not subject:
        return None
    head = _tn(language, len(commits), "resolve.git.log_commit", "resolve.git.log_commits")
    said = _t(language, "resolve.d6c.git.log_last").format(head=head, subject=_clean(subject[1], words=10))
    stat, files = _GIT_DIFFSTAT.search(block), _GIT_STAT_FILE.findall(block)
    if stat and not any("=>" in f for f in files):
        n = int(stat["files"])
        said += ", " + _tn(language, n, "resolve.git.diffstat_file", "resolve.git.diffstat_files")
        said += _names_tail(language, [_base(f) for f in files], len(files) == n)
    return said + "."


def _git_sub(args: list[str]) -> tuple[str, list[str]]:
    i = 0
    while i < len(args):
        if args[i] in ("-C", "-c", "--git-dir", "--work-tree"):
            i += 2
        elif args[i].startswith("-"):
            i += 1
        else:
            return args[i], args[i + 1:]
    return "", []


def _git(first, args, cmd, failed, output, language="fr"):
    if first == "gh":
        if failed and "gh auth login" in output and re.search(r"To get started with GitHub CLI|not logged into any", output):
            return _t(language, "resolve.d6c.gh.login") + (_t(language, "resolve.d6c.gh.token") if "GH_TOKEN" in output
                                                           else "") + "."
        return None
    if first != "git":
        return None
    sub, rest = _git_sub(args)
    if failed and (files := list(dict.fromkeys(_base(f) for f in _GIT_CONFLICT.findall(output)))):
        if len(files) > 3:
            return _t(language, "resolve.git.conflict_many").format(n=len(files), names=", ".join(files[:3]))
        return _t(language, "resolve.git.conflict").format(names=", ".join(files))
    if failed and sub in ("clone", "fetch", "pull", "push", "ls-remote") and (m := _GIT_HOST.search(output)):
        return _t(language, "resolve.net.host_not_found").format(host=m[1] or m[2])
    if failed and sub in ("merge", "pull") and _GIT_FF_IMPOSSIBLE.search(output):
        diverged = _t(language, "resolve.d6c.git.diverged") if _GIT_DIVERGING.search(output) else ""
        return _t(language, "resolve.d6c.git.ff_impossible") + diverged + "."
    if sub == "push" and failed and (m := _GIT_NO_UPSTREAM.search(output)):
        hint = _GIT_SET_UPSTREAM.search(output)
        return (_t(language, "resolve.d6c.git.no_upstream").format(b=m[1])
                + (_t(language, "resolve.d6c.git.set_upstream").format(cmd=hint[1]) if hint else "") + ".")
    if sub in ("checkout", "switch") and not failed and _GIT_DETACHED_NOTE.search(output):
        if m := _GIT_HEAD_AT.search(output):
            return _t(language, "resolve.git.detached").format(b=m[1]) + ", " + _clean(m[2], words=10) + "."
    if sub == "branch" and not failed and "|" not in cmd and set(rest) <= _GIT_BRANCH_FLAGS:
        return _git_branch_list(rest, output, language)
    if sub == "log" and "--stat" in rest and not failed and "|" not in cmd and not {"--oneline", "-p", "--patch"} & set(rest):
        return _git_log_stat(output, language)
    if sub == "push":
        if m := _GIT_REMOTE_REJECTED.search(output):
            return _t(language, "resolve.git.push_remote_rejected").format(branch=m[1], msg=_clean(m[2]))
        if m := _GIT_REJECTED.search(output):
            if m[2] in _GIT_BEHIND_REASONS:
                return _t(language, "resolve.git.push_behind").format(branch=m[1])
            return _t(language, "resolve.git.push_rejected").format(branch=m[1], msg=_clean(m[2]))
        if failed:
            return None
        if re.search(r"Everything up-to-date|Tout est à jour", output):
            return _t(language, "resolve.git.push_up_to_date")
        if m := _GIT_PUSHED.search(output):
            return _t(language, "resolve.git.pushed").format(branch=m[1])
        return None
    if sub == "status" and not {"-s", "--short", "--porcelain", "-sb"} & set(rest):
        return _git_status(output, language)
    if sub == "diff" and {"--stat", "--shortstat"} & set(rest):
        return None if failed else _git_diffstat_sentence(output, language)
    if sub == "log" and "--oneline" in rest:
        return None if failed else _git_log_oneline_sentence(output, language)
    if sub == "pull":
        if failed:
            return None
        if _GIT_PULL_FF.search(output):
            stat = _git_diffstat_sentence(output, language)
            return (_t(language, "resolve.git.pull_ff_stat").format(stat=stat) if stat
                    else _t(language, "resolve.git.pull_ff"))
        if re.search(r"Already up[ -]to[ -]date|Déjà à jour", output):
            return _t(language, "resolve.git.pull_up_to_date")
        return None
    if sub == "clone" and failed:
        if m := _GIT_CLONE_AUTH.search(output):
            name = m[1].rstrip("/").removesuffix(".git").rsplit("/", 1)[-1]
            return _t(language, "resolve.git.clone_auth_failed").format(name=name)
        return None
    return None


def _git_diffstat_sentence(output: str, language: str = "fr") -> str | None:
    m = _GIT_DIFFSTAT.search(output)
    if not m:
        return None
    parts = [_tn(language, int(m["files"]), "resolve.git.diffstat_file", "resolve.git.diffstat_files")]
    if m["ins"]:
        parts.append(_tn(language, int(m["ins"]), "resolve.git.diffstat_insertion", "resolve.git.diffstat_insertions"))
    if m["del"]:
        parts.append(_tn(language, int(m["del"]), "resolve.git.diffstat_deletion", "resolve.git.diffstat_deletions"))
    return ", ".join(parts) + "."


def _git_log_oneline_sentence(output: str, language: str = "fr") -> str | None:
    lines = [l for l in output.splitlines() if l.strip()]
    if not lines or not all(_GIT_LOG_ONELINE_LINE.match(l) for l in lines):
        return None
    subject = _clean(lines[0].split(" ", 1)[1], words=10) if " " in lines[0] else ""
    head = _tn(language, len(lines), "resolve.git.log_commit", "resolve.git.log_commits")
    return _t(language, "resolve.git.log_last").format(head=head, subject=subject) if subject else f"{head}."


def _git_status(output: str, language: str = "fr") -> str | None:
    branch = re.search(r"^(?:On branch|Sur la branche) (\S+)", output, re.M)
    detached = re.search(r"^(?:HEAD detached at|HEAD détachée sur) (\S+)", output, re.M)
    if not (branch or detached):
        return _git_rebase_status(output, language)
    parts = [_t(language, "resolve.git.branch").format(b=branch[1]) if branch
             else _t(language, "resolve.git.detached").format(b=detached[1])]
    if re.search(r"^(?:No commits yet|Aucun commit)", output, re.M):
        parts.append(_t(language, "resolve.git.no_commits"))
    for word, key in (("ahead of|en avance sur", "resolve.git.ahead"), ("behind|en retard sur", "resolve.git.behind")):
        if m := re.search(rf"(?:{word}) '[^']+' (?:by|de) (\d+) commits?", output):
            count = int(m[1])
            parts.append(_t(language, key).format(n=count, s="" if count == 1 else "s"))
    if re.search(r"have diverged|ont divergé", output):
        parts.append(_t(language, "resolve.git.diverged"))
    counts, current = [0] * len(_GIT_SECTIONS), None
    for line in output.splitlines():
        hit = next((i for i, (rx, _, _) in enumerate(_GIT_SECTIONS) if rx.match(line)), None)
        if hit is not None:
            current = hit
        elif line.startswith("\t") and current is not None:
            counts[current] += 1
        elif line.strip() and not line.startswith(" "):
            current = None
    files = [(cnt, one_key, many_key) for cnt, (_, one_key, many_key) in zip(counts, _GIT_SECTIONS) if cnt]
    if not files:
        parts.append(_t(language, "resolve.git.nothing_to_commit"))
    for i, (cnt, one_key, many_key) in enumerate(files):
        noun = _t(language, "resolve.git.file" if cnt == 1 else "resolve.git.files") if i == 0 else ""
        word = _t(language, one_key if cnt == 1 else many_key)
        parts.append(f"{cnt} {noun}{word}")
    return ", ".join(parts) + "."


# ---------------------------------------------------------------- réseau : curl, ssh, ping

_CURL_ERROR = re.compile(r"^curl: \((\d+)\) (.+)$", re.M)
_URL_HOST = re.compile(r"https?://([^/:\s]+)")
_DNS_FAIL = re.compile(r"Name or service not known|Nom ou service inconnu|Temporary failure in name resolution|"
                       r"Échec temporaire dans la résolution du nom|Unknown host|nodename nor servname")
_PING_STATS = re.compile(r"(\d+)\s(?:packets transmitted|paquets transmis), (\d+)\s(?:packets )?(?:received|reçus)"
                         r"(?:, \+\d+\s(?:errors|erreurs))?, ([\d.,]+)%\s(?:packet loss|perte)")


def _net(first, args, cmd, failed, output, language="fr"):
    if m := [*_CURL_ERROR.finditer(output)]:
        return _curl_error(int(m[-1][1]), m[-1][2], cmd, language)
    if first == "curl" and any(a == "--head" or re.fullmatch(r"-[a-zA-Z]*I[a-zA-Z]*", a) for a in args):
        if m := [*re.finditer(r"^HTTP/[\d.]+ (\d{3})[ \t]*([^\r\n]*)$", output, re.M)]:
            return _end(_t(language, "resolve.net.http_head").format(code=m[-1][1], msg=m[-1][2]).strip())
    if first in ("ssh", "scp", "sftp") and failed:
        return _ssh_error(output, language)
    if first in ("ping", "ping6"):
        return _ping(output, language)
    if first == "wget":
        return _wget(failed, output, language)
    if first == "curl" and not failed and "|" not in cmd:
        return _curl_status(args, cmd, output, language) or _curl_meter(args, cmd, output, language)
    if first == "ss" and not failed:
        return _ss_listening(args, output, language)
    if first == "ip" and not failed:
        return _ip_route(args, output, language)
    if first == "nmcli" and not failed:
        return _nmcli(args, output, language)
    return None


# chaînes de vérification d'OpenSSL reprises par curl ; l'ordre compte (« in certificate chain »)
_TLS_REASONS = (
    (r"self[- ]signed certificate in certificate chain", "resolve.net.tls.self_signed_chain"),
    (r"self[- ]signed certificate$", "resolve.net.tls.self_signed"),
    (r"certificate has expired$", "resolve.net.tls.expired"),
    (r"certificate is not yet valid$", "resolve.net.tls.not_yet_valid"),
    (r"unable to get local issuer certificate$", "resolve.net.tls.issuer"),
    (r"no alternative certificate subject name matches target host name", "resolve.net.tls.hostname"),
)


def _curl_error(code: int, msg: str, cmd: str, language: str = "fr") -> str:
    url = _URL_HOST.search(cmd)
    if m := re.search(r"Could not resolve host: (\S+)", msg):
        return _t(language, "resolve.net.host_not_found").format(host=m[1])
    if m := re.search(r"(?:Failed to connect|Couldn't connect) to (\S+) port (\d+)", msg):
        key = "resolve.net.connection_refused" if "refused" in msg else "resolve.net.connection_failed"
        return _t(language, key).format(host=m[1], port=m[2])
    if code == 28:
        return (_t(language, "resolve.net.timeout_host").format(host=url[1]) if url
                else _t(language, "resolve.net.timeout"))
    if m := re.search(r"returned error: (\d{3})", msg):
        return _t(language, "resolve.net.http_error").format(code=m[1])
    if code in (35, 51, 58, 60, 77, 83, 90, 91):
        reason = next((key for pattern, key in _TLS_REASONS if re.search(pattern, msg)), None)
        if reason and url:
            return _t(language, "resolve.net.tls_known").format(host=url[1], reason=_t(language, reason))
        cleaned = _clean(msg.replace("SSL certificate problem: ", ""))
        return _end(_t(language, "resolve.net.tls").format(msg=cleaned))
    return _end(_t(language, "resolve.net.curl").format(msg=_clean(msg)))


def _ssh_error(output: str, language: str = "fr") -> str | None:
    if m := re.search(r"^Host key for (\S+) has changed and you have requested strict checking", output, re.M):
        return _t(language, "resolve.net.ssh_hostkey_changed").format(host=m[1])
    if "Host key verification failed" in output:
        return _t(language, "resolve.net.ssh_hostkey")
    if m := re.search(r"Could not resolve hostname (\S+?):", output):
        return _t(language, "resolve.net.host_not_found").format(host=m[1])
    if m := re.search(r"connect to host (\S+) port (\d+): (.+)", output):
        if "refused" in m[3]:
            return _t(language, "resolve.net.connection_refused").format(host=m[1], port=m[2])
        if "No route" in m[3]:
            return _t(language, "resolve.net.ssh_unreachable").format(host=m[1])
        if "timed out" in m[3]:
            return _t(language, "resolve.net.ssh_timeout").format(host=m[1], port=m[2])
    if re.search(r"Permission denied \(", output):
        return _t(language, "resolve.net.ssh_denied")
    return None


def _ping(output: str, language: str = "fr") -> str | None:
    if _DNS_FAIL.search(output) and (m := re.search(r"ping: (?:cannot resolve |unknown host )?([^\s:]+)", output)):
        return _t(language, "resolve.net.host_not_found").format(host=m[1])
    m = _PING_STATS.search(output)
    if not m:
        return None
    sent, got = int(m[1]), int(m[2])
    loss = m[3].replace(",", ".").removesuffix(".0")
    if not got:
        down = _t(language, "resolve.net.ping_unreachable") if re.search(r"Unreachable|injoignable", output) else ""
        return _t(language, "resolve.net.ping_none").format(sent=sent, loss=loss, down=down)
    avg_m = re.search(r"= [\d.]+/([\d.]+)/", output)
    avg = _t(language, "resolve.net.ping_avg").format(avg=avg_m[1]) if avg_m else ""
    return _t(language, "resolve.net.ping_some").format(got=got, s="" if got == 1 else "s", sent=sent, loss=loss, avg=avg)


# ================================================================ D6 lot B : scripts et fichiers
#
# Formats des sorties de bash, GNU coreutils, tar, diffutils, grep et rsync, en anglais et
# dans leurs traductions (catalogues fr.mo : espace insécable avant les deux-points). Chaque
# phrase compte ou reprend ce que l'outil a écrit ; au moindre doute, le modèle garde la main.

_COLON = r"[ \xa0]?:[ \xa0]"
_QUOTED = r"['‘«`][ \xa0]?(?P<p>[^'’»`]+?)[ \xa0]?['’»`]"
_SHELL_CHAINED = re.compile(r"\||;|&&|`|\$\(")
_PATH_MAX = 40


def _chained(cmd: str) -> bool:
    """Tube, enchaînement ou substitution hors des chaînes entre guillemets : la sortie n'est plus celle d'un seul outil."""
    return bool(_SHELL_CHAINED.search(re.sub(r"'[^']*'|\"[^\"]*\"", "", cmd)))


def _short_path(path: str) -> str:
    path = path.strip().strip("'\"‘’«»` \xa0")
    path = path[2:] if path.startswith("./") else path
    return path if len(path) <= _PATH_MAX else "/".join(path.rstrip("/").split("/")[-2:])


def _quote_free(msg: str, words: int = 14) -> str:
    """Comme `_clean`, sans casser les élisions (« d'ouvrir ») : seuls les guillemets autour des mots partent."""
    msg = re.sub(r"(?<!\w)['‘’`\"«»]|['‘’`\"«»](?!\w)", "", msg)
    msg = re.sub(r"\s+", " ", msg).strip()
    return " ".join(msg.split(" ")[:words]).rstrip(".,;: ")


def _and(language: str, items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + _t(language, "resolve.d6b.and") + items[-1]


def _count(language: str, count: int, key: str) -> str:
    """Compteur accordé à partir d'une clé `key` et de sa forme `key_many`."""
    return _tn(language, count, key, key + "_many")


# ---------------------------------------------------------------- dernière erreur d'un script

_SCRIPT_SHELLS = {"bash", "sh", "zsh", "dash", "ksh"}
_SCRIPT_SUFFIXES = (".sh", ".bash", ".zsh", ".ksh")
_SCRIPT_LINE = re.compile(rf"^(?P<script>[^\s:]+){_COLON}?(?:line|ligne)[ \xa0](?P<line>\d+){_COLON}?(?P<msg>.+)$")
# outils dont le message d'erreur suit le format GNU « outil: message » (coreutils, tar, rsync…)
_GNU_TOOLS = {"cp", "mv", "rm", "mkdir", "rmdir", "ln", "chmod", "chown", "chgrp", "touch", "cat", "sort", "cut",
              "head", "tail", "wc", "tar", "gzip", "gunzip", "xz", "unxz", "zip", "unzip", "ls", "stat", "install",
              "tee", "split", "shred", "find", "sed", "rsync", "du", "dd", "md5sum", "sha1sum", "sha256sum",
              "sha512sum"}
_TOOL_LINE = re.compile(rf"^(?P<tool>[a-z][\w.+-]*)(?: \(child\))?{_COLON}(?P<msg>.+)$")
# tar conclut par une ligne générique qui ne dit jamais la cause (GNU tar, src/buffer.c et src/tar.c)
_TAR_GENERIC = re.compile(r"^(?:Error is not recoverable: exiting now|Erreur non récupérable : abandon"
                          r"|Child returned status \d+|Exiting with failure status due to previous errors"
                          r"|Arrêt avec code d'échec à cause des erreurs précédentes)")
_CAUSES = (
    (r"No such file or directory|Aucun fichier ou (?:dossier|répertoire) de ce nom", "resolve.d6b.not_found"),
    (r"Permission denied|Permission non accordée", "resolve.d6b.denied"),
    (r"File exists|Le fichier existe", "resolve.d6b.exists"),
    (r"Operation not permitted|Opération non permise", "resolve.d6b.not_permitted"),
    (r"Is a directory|Est un dossier|est un répertoire", "resolve.d6b.is_dir"),
    (r"Not a directory|N'est pas un (?:dossier|répertoire)", "resolve.d6b.not_dir"),
    (r"No space left on device|(?:Plus|Aucun) d'espace disponible sur le périphérique", "resolve.d6b.no_space"),
)
_KNOWN_MESSAGES = (
    (re.compile(rf"^(?P<name>\w+){_COLON}?(?:unbound variable|variable sans liaison)$"), "resolve.d6b.unbound"),
    (re.compile(r"division (?:by|par) 0\b"), "resolve.d6b.div_zero"),
    (re.compile(r"^(?:Unexpected EOF in archive|Fin prématurée rencontrée dans l'archive"
                r"|Fin de fichier inattendue dans l'archive)"), "resolve.d6b.tar_eof"),
    (re.compile(r"^(?:This does not look like a tar archive|Ceci ne ressemble pas à une archive)"),
     "resolve.d6b.not_tar"),
    (re.compile(rf"^(?P<name>\S+){_COLON}?(?:command not found|commande introuvable)$"), "resolve.d6b.cmd_not_found"),
)
# une ligne « outil: … » n'est une erreur que si elle en a le vocabulaire (un script écrit aussi « cp: fait »)
_TOOL_ERROR_WORDS = re.compile(r"(?i)cannot|can't|impossible|failed|échec|error|erreur|invalid|non valable|denied|"
                               r"refus|not |n'est pas|unable|unexpected|inattendu|missing|manquant|no such|aucun|"
                               r"exists|existe|premature|prématurée|variable|division|non permise|introuvable")
_FRENCH = re.compile(r"(?i)[àâçéèêëîïôûùüœ«»]|\b(?:aucun|fichier|dossier|introuvable|attendu|ligne)\b")


def _script_name(first: str, args: list[str]) -> str | None:
    if first.endswith(_SCRIPT_SUFFIXES):
        return first
    if first not in _SCRIPT_SHELLS:
        return None
    for a in args:
        if a == "-c" or (a.startswith("-") and "c" in a[1:] and not a.startswith("--")):
            return None
        if not a.startswith("-") and not a.startswith("+"):
            return _base(a)
    return None


def _error_message(msg: str, language: str) -> tuple[str, str | None, str | None] | None:
    """(phrase, clé de cause, chemin) d'un message d'erreur, ou None s'il ne se dit pas sûrement."""
    msg = msg.strip()
    for pattern, key in _KNOWN_MESSAGES:
        if m := pattern.search(msg):
            return _t(language, key).format(**m.groupdict()), key, None
    for pattern, key in _CAUSES:
        m = re.search(rf"(?:^|[ \xa0]?:[ \xa0]?)(?:{pattern})\.?$", msg)
        if not m:
            continue
        prefix = msg[:m.start()].strip(" \xa0:")
        quoted = re.search(rf"(?:^|[\s:]){_QUOTED}", prefix)
        segments = [s.strip() for s in re.split(rf"{_COLON}|[ \xa0]?:$", prefix) if s.strip()]
        plain = [s for s in segments if not re.search(r"\s", s)]
        # « failed to extend /x/y » : sans segment nu, le dernier mot qui a l'allure d'un chemin
        pathlike = [w for w in prefix.split() if "/" in w]
        path = quoted["p"] if quoted else (plain[-1] if plain else (pathlike[-1] if pathlike else None))
        said = _t(language, key)
        if not path:
            return said, key, None
        # création refusée faute de chemin : parent absent ou système de fichiers qui refuse, on ne tranche pas
        if key == "resolve.d6b.not_found" and re.search(r"(?i)\bcreate\b|\bcréer\b", prefix):
            return _t(language, "resolve.d6b.cannot_create").format(path=_short_path(path)), None, path
        what = _t(language, "resolve.d6b.path_said").format(path=_short_path(path), said=said)
        # commande interne du shell nommée avant le chemin : « cd: /x: Permission denied »
        head = segments[0] if len(segments) > 1 and not quoted else ""
        if head and head != path and not re.search(r"[\s/]", head):
            what = f"{head}, {what}"
        return what, key, path
    if language == "en" and _FRENCH.search(msg):
        return None
    return _quote_free(msg), None, None


def _script_error(first, args, cmd, failed, output, language="fr"):
    """Script en échec ou outil GNU lancé seul : dernière erreur dite, et le compte s'il y en a plusieurs."""
    script = _script_name(first, args)
    direct = script is None and first in _GNU_TOOLS
    if (script is None and not direct) or (direct and not failed) or _chained(cmd):
        return None
    from .textproc import strip_ansi

    lines = [l.strip() for l in strip_ansi(output).splitlines() if l.strip()]
    errors, error_lines, fatal_tar = [], set(), False
    for i, line in enumerate(lines):
        if script and (m := _SCRIPT_LINE.match(line)) and _base(m["script"]) == script:
            errors.append(("script", m["line"], m["msg"]))
            error_lines.add(i)
        elif (m := _TOOL_LINE.match(line)) and m["tool"] in _GNU_TOOLS and (script or m["tool"] == first):
            error_lines.add(i)
            if m["tool"] == "tar" and _TAR_GENERIC.match(m["msg"]):
                fatal_tar = fatal_tar or bool(re.search(r"not recoverable|non récupérable", m["msg"]))
            # tar redit parfois la même erreur à la fermeture de l'archive
            elif ((_TOOL_ERROR_WORDS.search(m["msg"]) or any(re.search(c, m["msg"]) for c, _ in _CAUSES))
                  and (m["tool"], None, m["msg"]) not in errors):
                errors.append((m["tool"], None, m["msg"]))
    if not errors:
        return None
    # script qui rend 0 après des erreurs (pas de `set -e`) : « Terminé, mais… »
    said = _script_error_sentence(script, direct, errors, lines, "" if failed else "_ok", language)
    if not said:
        return None
    # « Error is not recoverable » ne qualifie que la dernière erreur, et seulement si elle vient de tar
    if fatal_tar and errors[-1][0] == "tar" and said.endswith("."):
        said = said[:-1] + _t(language, "resolve.d6b.tar_fatal") + "."
    if script and (last := _last_message(lines, error_lines, language)):
        said += " " + _t(language, "resolve.d6b.last_message").format(line=last)
    return said


# dernier message du script : un bilan chiffré (« 82 items synced »), jamais une ligne d'erreur
_LAST_MESSAGE_MAX_WORDS = 12


def _last_message(lines: list[str], error_lines: set[int], language: str) -> str | None:
    last = next((l for i, l in reversed(list(enumerate(lines))) if i not in error_lines), None)
    # « + commande » : trace de `set -x`, pas un message du script
    if (not last or last.startswith("+") or len(last.split()) > _LAST_MESSAGE_MAX_WORDS or not _STANDALONE_NUMBER.search(last)
            or not _TAIL_SUMMARY.search(last) or _NOT_SUMMARY.search(last) or _GENERIC_ERROR.match(last)):
        return None
    if language == "en" and _FRENCH.search(last):
        return None
    return _quote_free(last, _LAST_MESSAGE_MAX_WORDS)


def _script_error_sentence(script, direct, errors, lines, ok, language):
    rendered = []
    for source, line_no, msg in errors:
        said = _error_message(msg, language)
        if said is None:
            return None
        rendered.append((source, line_no, *said))
    source, line_no, what, key, _ = rendered[-1]
    # un outil seul, une erreur de fichier, une sortie courte : `_file_error` la dit déjà
    if direct and len(rendered) == 1 and len(lines) <= 5 and key in {k for _, k in _CAUSES}:
        return None
    where = (_t(language, "resolve.file_line").format(file=script, line=line_no, msg=what) if source == "script"
             else _t(language, "resolve.d6b.tool").format(tool=source, what=what))
    if len(rendered) == 1:
        return _end(_t(language, "resolve.d6b.one_error" + ok).format(where=where))
    # code 0 après plusieurs erreurs : la cause est souvent la première, pas la dernière ; on s'abstient
    if ok:
        return None
    n = len(rendered)
    same_tool = len({r[0] for r in rendered}) == 1 and source != "script"
    if same_tool and len({r[3] for r in rendered}) == 1 and key:
        paths = [_short_path(r[4]) for r in rendered if r[4]]
        said_many = _t(language, key + "_many") if key in _D6B_PLURAL_KEYS else _t(language, key)
        named = list(dict.fromkeys(paths))
        if len(paths) == n and len(named) <= 3:
            return _t(language, "resolve.d6b.tool_errors_paths").format(
                n=n, tool=source, paths=_and(language, named), said=said_many if len(named) > 1 else _t(language, key))
        if len(paths) == n:
            return _t(language, "resolve.d6b.tool_errors_example").format(n=n, tool=source, said=said_many,
                                                                          path=paths[0])
        if len({r[2] for r in rendered}) == 1:
            return _t(language, "resolve.d6b.tool_errors_same").format(n=n, tool=source, said=what)
    return _t(language, "resolve.d6b.n_errors").format(n=n) + " " + \
        _t(language, "resolve.d6b.last").format(where=where)


_D6B_PLURAL_KEYS = {"resolve.d6b.not_found", "resolve.d6b.exists", "resolve.d6b.is_dir", "resolve.d6b.not_dir"}


# ---------------------------------------------------------------- sorties verbeuses comptées

_RM_REMOVED = (re.compile(rf"^removed (?:directory )?{_QUOTED}$"),
               re.compile(rf"^(?:répertoire )?{_QUOTED} supprimé$"))
_MKDIR_CREATED = (re.compile(rf"^mkdir{_COLON}created directory {_QUOTED}$"),
                  re.compile(rf"^mkdir{_COLON}création du répertoire {_QUOTED}$"),
                  re.compile(rf"^mkdir{_COLON}répertoire {_QUOTED} créé$"))
_SPLIT_CREATED = (re.compile(rf"^creating file {_QUOTED}$"), re.compile(rf"^création du fichier {_QUOTED}$"))
_MODE = r"(?P<new>\d{3,4}) \([-rwxsStT]{9}\)"
_CHMOD_CHANGED = (re.compile(rf"^mode of {_QUOTED} changed from \d{{3,4}} \(\S+\) to {_MODE}$"),
                  re.compile(rf"^le mode de {_QUOTED} a été modifié de \d{{3,4}} \(\S+\) en {_MODE}$"))
_CHMOD_KEPT = (re.compile(rf"^mode of {_QUOTED} retained as \d{{3,4}} \(\S+\)$"),
               re.compile(rf"^le mode de {_QUOTED} a été conservé à \d{{3,4}} \(\S+\)$"))
_OWNER_CHANGED = (re.compile(rf"^changed ownership of {_QUOTED} from \S+ to (?P<new>\S+)$"),
                  re.compile(rf"^appartenance de {_QUOTED} modifiée de \S+ en (?P<new>\S+)$"))
_OWNER_KEPT = (re.compile(rf"^ownership of {_QUOTED} retained(?: as \S+)?$"),
               re.compile(rf"^l'appartenance de {_QUOTED} (?:a été maintenue|est maintenue à \S+)$"))
_GROUP_CHANGED = (re.compile(rf"^changed group of {_QUOTED} from \S+ to (?P<new>\S+)$"),
                  re.compile(rf"^groupe de {_QUOTED} modifié de \S+ en (?P<new>\S+)$"))
_GROUP_KEPT = (re.compile(rf"^group of {_QUOTED} retained as \S+$"),
               re.compile(rf"^le groupe de {_QUOTED} est maintenu à \S+$"))
_ARROW = r"['‘](?P<a>[^'’]+)['’] -> ['‘](?P<b>[^'’]+)['’]"
_COPIED = (re.compile(rf"^{_ARROW}$"),)
_MOVED = (re.compile(rf"^renamed {_ARROW}$"), re.compile(r"^['‘](?P<a>[^'’]+)['’] <-> ['‘](?P<b>[^'’]+)['’] renommé$"))
_SHRED_PASS = re.compile(rf"^shred{_COLON}(?P<f>.+?){_COLON}(?:pass|étape) \d+/(?P<n>\d+) \(.+?\)(?:\.\.\.|…)")
_SHRED_STEP = re.compile(rf"^shred{_COLON}.+?{_COLON}(?:removing|suppression|renamed to .+|renommé en .+)$")
_SHRED_REMOVED = re.compile(rf"^shred{_COLON}(?P<f>.+?){_COLON}(?:removed|supprimé)$")


def _all_match(lines: list[str], patterns: tuple[re.Pattern, ...]) -> list[re.Match] | None:
    found = [next((m for p in patterns if (m := p.match(l))), None) for l in lines]
    return found if found and all(found) else None


def _common_dir(paths: list[str], exclude: list[str] | None = None) -> str:
    """Dossier commun aux chemins, s'il en est un qui dit quelque chose ; sinon chaîne vide."""
    paths = [p.rstrip("/") for p in paths]
    if len({p.startswith("/") for p in paths}) != 1:
        return ""
    common = os.path.commonpath(paths)
    if common in (exclude or []) or common in ("", ".", "/"):
        return ""
    return _short_path(common)


def _verbose_count(first, args, cmd, failed, output, language="fr"):
    """rm, mkdir, split, chmod, chown, chgrp, cp, mv, ln, shred et tar en mode verbeux : le compte des lignes."""
    if failed or _chained(cmd):
        return None
    from .textproc import strip_ansi

    lines = [l.strip() for l in strip_ansi(output).splitlines() if l.strip()]
    if not lines:
        return None
    if first == "shred":
        return _shred_count(lines, language)
    if first == "tar":
        return _tar_count(args, lines, language)
    if first == "rm" and (found := _all_match(lines, _RM_REMOVED)):
        place = _common_dir([os.path.dirname(m["p"]) or "." for m in found])
        items = _count(language, len(found), "resolve.d6b.removed")
        return _t(language, "resolve.d6b.removed_in").format(items=items, dir=place) if place else items + "."
    if first == "mkdir" and (found := _all_match(lines, _MKDIR_CREATED)):
        created = [m["p"].rstrip("/") for m in found]
        place = _common_dir(created, exclude=created) if len(created) > 1 else ""
        items = _count(language, len(found), "resolve.d6b.dirs_created")
        if place:
            return _t(language, "resolve.d6b.dirs_created_in").format(items=items, dir=place)
        roots = [_short_path(d) for d in created if os.path.dirname(d) not in created]
        if roots and len(roots) < len(created) and len(roots) <= 3:
            return _t(language, "resolve.d6b.dirs_created_incl").format(items=items, roots=_and(language, roots))
        return items + "."
    if first == "split" and (found := _all_match(lines, _SPLIT_CREATED)):
        if len(found) == 1:
            return _t(language, "resolve.d6b.split_one").format(name=_short_path(found[0]["p"]))
        return _t(language, "resolve.d6b.split_many").format(
            n=len(found), first=_short_path(found[0]["p"]), last=_short_path(found[-1]["p"]))
    if first == "chmod":
        return _changed_count(lines, _CHMOD_CHANGED, _CHMOD_KEPT, "mode", language)
    if first in ("chown", "chgrp"):
        for changed, kept in ((_OWNER_CHANGED, _OWNER_KEPT), (_GROUP_CHANGED, _GROUP_KEPT)):
            if said := _changed_count(lines, changed, kept, "owner" if changed is _OWNER_CHANGED else "group",
                                      language):
                return said
        return None
    if first in ("cp", "mv") and (found := _all_match(lines, _COPIED if first == "cp" else _MOVED)):
        targets = [m["b"] for m in found]
        place = (_short_path(os.path.dirname(targets[0].rstrip("/"))) if len(targets) == 1
                 else _common_dir(targets))
        key = "resolve.d6b.copied" if first == "cp" else "resolve.d6b.moved"
        items = _count(language, len(found), key)
        return _t(language, key + "_to").format(items=items, dir=place) if place and place != "." else items + "."
    if first == "ln" and (found := _all_match(lines, _COPIED)):
        place = _common_dir([os.path.dirname(m["a"]) or "." for m in found])
        items = _count(language, len(found), "resolve.d6b.links")
        return _t(language, "resolve.d6b.links_in").format(items=items, dir=place) if place else items + "."
    return None


def _changed_count(lines, changed, kept, what, language):
    matches = _all_match(lines, changed + kept)
    if not matches:
        return None
    new = [m["new"] for m in matches if "new" in m.groupdict() and m["new"]]
    n_changed, n_kept = len(new), len(matches) - len(new)
    if not n_changed:
        return _t(language, f"resolve.d6b.{what}_kept").format(items=_count(language, n_kept, "resolve.d6b.item"))
    said = _t(language, f"resolve.d6b.{what}_changed").format(items=_count(language, n_changed, "resolve.d6b.item"))
    if len(set(new)) == 1:
        value = new[0][1:] if what == "mode" and len(new[0]) == 4 and new[0][0] == "0" else new[0]
        said += _t(language, f"resolve.d6b.{what}_now").format(value=value)
    if n_kept:
        said += ", " + _count(language, n_kept, "resolve.d6b.unchanged")
    return said + "."


def _shred_count(lines: list[str], language: str) -> str | None:
    files, passes, removed = [], set(), 0
    for line in lines:
        if m := _SHRED_PASS.match(line):
            files.append(m["f"])
            passes.add(int(m["n"]))
        elif _SHRED_REMOVED.match(line):
            removed += 1
        elif not _SHRED_STEP.match(line):
            return None
    files = list(dict.fromkeys(files))
    if not files or len(passes) != 1 or removed not in (0, len(files)):
        return None
    key = "resolve.d6b.shred_removed" if removed else "resolve.d6b.shred"
    key += "_one" if len(files) == 1 else "_many"
    return _t(language, key).format(n=len(files), first=_short_path(files[0]),
                                    passes=_count(language, passes.pop(), "resolve.d6b.pass"))


def _tar_count(args: list[str], lines: list[str], language: str) -> str | None:
    mode, verbose, archive = "", False, ""
    for i, a in enumerate(args):
        if a.startswith("--"):
            name, _, value = a.partition("=")
            mode = {"--create": "c", "--extract": "x", "--get": "x", "--list": "t"}.get(name, mode)
            verbose = verbose or name == "--verbose"
            archive = value if name == "--file" else archive
        elif a.startswith("-") or i == 0:
            flags = a.lstrip("-")
            mode = next((ch for ch in flags if ch in "cxtruA"), mode)
            verbose = verbose or "v" in flags
            if "f" in flags:
                rest = flags[flags.index("f") + 1:]
                archive = rest or (args[i + 1] if i + 1 < len(args) else "")
    if mode not in ("c", "x") or not verbose or any(l.startswith("tar:") for l in lines):
        return None
    # bsdtar (macOS) préfixe chaque membre par « a » ou « x »
    if any(re.match(r"^[ax] ", l) for l in lines) and not all(re.match(rf"^{mode if mode == 'x' else 'a'} ", l)
                                                              for l in lines):
        return None
    key = "resolve.d6b.tar_created" if mode == "c" else "resolve.d6b.tar_extracted"
    items = _count(language, len(lines), key)
    if not archive or archive == "-":
        return items + "."
    return _t(language, key + "_in").format(items=items, archive=_base(archive))


# ---------------------------------------------------------------- sommes de contrôle -c

_CHECKSUM_TOOLS = {"md5sum", "sha1sum", "sha224sum", "sha256sum", "sha384sum", "sha512sum", "b2sum", "shasum"}
_CHECK_OK = re.compile(r"^(?P<f>.+): (?:OK|Réussi)$")
_CHECK_BAD = re.compile(r"^(?P<f>.+): (?:FAILED|Échec)$")
_CHECK_UNREAD = re.compile(r"^(?P<f>.+): (?:FAILED open or read|Échec d'ouverture ou de lecture)$")
_CHECK_WARN_BAD = re.compile(rf"(?:WARNING: (?P<a>\d+) computed checksums? did NOT match"
                             rf"|Attention{_COLON}(?P<b>\d+) sommes? de contrôle ne correspond(?:ent)? pas)$")
_CHECK_WARN_UNREAD = re.compile(rf"(?:WARNING: (?P<a>\d+) listed files? could not be read"
                                rf"|Attention{_COLON}(?P<b>\d+) fichiers? de la liste n'(?:a|ont) pas pu être lus?)$")
_CHECK_MALFORMED = re.compile(r"improperly formatted|properly formatted|correctement formatée")


def _warned(pattern: re.Pattern, lines: list[str]) -> int | None:
    m = next((m for l in lines if (m := pattern.search(l))), None)
    return int(m["a"] or m["b"]) if m else None


def _checksum(first, args, cmd, failed, output, language="fr"):
    """md5sum -c, sha256sum -c… : les comptes de l'outil (avertissements finaux), puis les noms."""
    checking = any(a == "--check" or re.fullmatch(r"-[a-zA-Z]*c[a-zA-Z]*", a) for a in args)
    if first not in _CHECKSUM_TOOLS or not checking:
        return None
    from .textproc import strip_ansi

    lines = [l.strip() for l in strip_ansi(output).splitlines() if l.strip()]
    if not lines or any(_CHECK_MALFORMED.search(l) for l in lines):
        return None
    ok, bad, unread = [], [], []
    for line in lines:
        if m := _CHECK_UNREAD.match(line):
            unread.append(m["f"])
        elif m := _CHECK_BAD.match(line):
            bad.append(m["f"])
        elif m := _CHECK_OK.match(line):
            ok.append(m["f"])
        elif not (_CHECK_WARN_BAD.search(line) or _CHECK_WARN_UNREAD.search(line)
                  or re.match(rf"^{first}{_COLON}.+{_COLON}.+$", line)):
            return None
    n_bad = _warned(_CHECK_WARN_BAD, lines)
    n_unread = _warned(_CHECK_WARN_UNREAD, lines)
    n_bad = len(bad) if n_bad is None else n_bad
    n_unread = len(unread) if n_unread is None else n_unread
    if n_bad < len(bad) or n_unread < len(unread):
        return None
    partial = "|" in cmd
    if not n_bad and not n_unread:
        if partial or not ok:
            return None
        return _count(language, len(ok), "resolve.d6b.checked_all") + "."
    parts = []
    for count, names, key in ((n_bad, bad, "resolve.d6b.check_bad"), (n_unread, unread, "resolve.d6b.check_unread")):
        if not count:
            continue
        said = _count(language, count, key)
        if names and count == 1 and len(names) == 1:
            said += _t(language, "resolve.d6b.named").format(name=_short_path(names[0]))
        elif names:
            said += _t(language, "resolve.d6b.including").format(name=_short_path(names[0]))
        parts.append(said)
    if ok and not partial:
        parts.append(_count(language, len(ok), "resolve.d6b.check_ok"))
    said = ", ".join(parts) + "."
    return f"{_t(language, 'resolve.failed')} {said}" if failed else said


# ---------------------------------------------------------------- grep -r compté

_GREP_COUNT_UNSURE = {"-v", "--invert-match", "-L", "--files-without-match", "-o", "--only-matching",
                      "-A", "-B", "-C", "--after-context", "--before-context", "--context", "-Z", "--null",
                      "-z", "--null-data", "-b", "--byte-offset", "-h", "--no-filename", "-f", "--file",
                      "-q", "--quiet", "--silent", "-T", "--initial-tab", "--label", "-U", "--binary"}
_GREP_OTHER_LINE = re.compile(r"^(?:grep|egrep|fgrep)[ \xa0]?:|^Binary file |binaires? correspond")


def _grep_count(first, args, cmd, failed, output, language="fr"):
    """grep sur plusieurs fichiers (-r, -l, -c ou plusieurs chemins) : lignes et fichiers comptés."""
    if first not in ("grep", "egrep", "fgrep") or failed or _chained(cmd):
        return None
    try:
        words = [w for w in shlex.split(cmd) if w not in ("sudo", "command")]
    except ValueError:
        return None
    patterns, positional, options = _grep_parse(words, "grep")
    if options & _GREP_COUNT_UNSURE or any(re.fullmatch(r"-\d", o) for o in options):
        return None
    if not patterns:
        if not positional:
            return None
        patterns, positional = [positional[0]], positional[1:]
    recursive = options & {"-r", "-R", "--recursive", "--dereference-recursive"}
    if not (recursive or len(positional) > 1 or options & {"-H", "--with-filename"}
            or any(re.search(r"[*?\[]", p) for p in positional)):
        return None
    from .textproc import strip_ansi

    lines = [l.rstrip() for l in strip_ansi(output).splitlines() if l.strip()]
    if not lines or any(_GREP_OTHER_LINE.search(l) for l in lines):
        return None
    listing = options & {"-l", "--files-with-matches"}
    counting = options & {"-c", "--count"}
    numbered = options & {"-n", "--line-number"}
    counts: dict[str, int] = {}
    for line in lines:
        if listing:
            path, n = line, 1
        else:
            m = re.match(r"^(?P<p>.+):(?P<c>\d+)$" if counting else r"^(?P<p>.+?):\d+:" if numbered
                         else r"^(?P<p>[^:]+):", line)
            if not m:
                return None
            path, n = m["p"], int(m["c"]) if counting else 1
        counts[path] = counts.get(path, 0) + n
    roots = [p.rstrip("/") for p in positional if not re.search(r"[*?\[]", p)]
    if roots and not all(any(p == r or p.startswith(r + "/") for r in roots) for p in counts):
        return None
    pattern = patterns[0] if len(patterns) == 1 and re.fullmatch(r"[\w.@/-]{1,30}", patterns[0]) else None
    hits = {p: c for p, c in counts.items() if c}
    if not hits:
        return None
    top = max(hits, key=hits.get)
    if listing:
        return _grep_listing(language, list(hits), pattern)
    total, files = sum(hits.values()), len(hits)
    if pattern:
        head = _t(language, "resolve.d6b.grep_lines_pat" + ("_one" if total == 1 else "_many")).format(
            n=total, pattern=pattern)
    else:
        head = _t(language, "resolve.d6b.grep_lines" + ("_one" if total == 1 else "_many")).format(n=total)
    if files == 1:
        tail = _t(language, "resolve.d6b.grep_in_one" if total == 1 else "resolve.d6b.grep_all_in").format(
            file=_short_path(top))
    elif counting and len(counts) > files:
        tail = _t(language, "resolve.d6b.grep_in_files_of").format(
            k=files, m=len(counts), c=hits[top], file=_short_path(top))
    else:
        tail = _t(language, "resolve.d6b.grep_in_files").format(k=files, c=hits[top], file=_short_path(top))
    return head + tail


def _grep_listing(language: str, files: list[str], pattern: str | None) -> str:
    key = "resolve.d6b.grep_files" + ("_pat" if pattern else "") + ("_one" if len(files) == 1 else "_many")
    return _t(language, key).format(k=len(files), pattern=pattern, file=_short_path(files[0]))


# ---------------------------------------------------------------- diff -q, diff -rq

_DIFF_FILES = (re.compile(r"^(?:Binary )?[Ff]iles (?P<a>.+) and (?P<b>.+) differ$"),
               re.compile(r"^Les fichiers (?:binaires )?(?P<a>.+) et (?P<b>.+) sont différents$"))
_DIFF_ONLY = (re.compile(r"^Only in (?P<d>.+?): (?P<n>.+)$"),
              re.compile(rf"^Seulement dans (?P<d>.+?){_COLON}?(?P<n>.+)$"))
_DIFF_SAME_DIRS = re.compile(r"^Common subdirectories: .+ and .+$|^Les sous-répertoires .+ et .+ sont identiques$")


def _diff_brief(first, args, cmd, failed, output, language="fr"):
    """diff -q ou -rq : fichiers qui diffèrent, puis ce qui n'existe que d'un côté."""
    if first != "diff" or not failed or _chained(cmd):
        return None
    positional = [a for a in args if not a.startswith("-")]
    if not positional:
        return None
    root = positional[0].rstrip("/")
    differ, only = [], {}
    for line in (l.strip() for l in output.splitlines() if l.strip()):
        if m := next((m for p in _DIFF_FILES if (m := p.match(line))), None):
            a = m["a"]
            differ.append(a[len(root) + 1:] if a.startswith(root + "/") else _base(a))
        elif m := next((m for p in _DIFF_ONLY if (m := p.match(line))), None):
            only.setdefault(_short_path(m["d"]), []).append(m["n"])
        elif not _DIFF_SAME_DIRS.match(line):
            return None
    parts = []
    if len(differ) == 1:
        parts.append(_t(language, "resolve.d6b.differ_one").format(name=differ[0]))
    elif len(differ) == 2:
        parts.append(_t(language, "resolve.d6b.differ_two").format(names=_and(language, differ)))
    elif differ:
        parts.append(_t(language, "resolve.d6b.differ_many").format(n=len(differ), name=differ[0]))
    if len(only) > 2:
        d, names = next(iter(only.items()))
        parts.append(_t(language, "resolve.d6b.only_sides").format(
            n=sum(map(len, only.values())), name=names[0], dir=d))
    else:
        for d, names in only.items():
            said = (_and(language, names) if len(names) <= 2 else
                    _t(language, "resolve.d6b.only_items").format(n=len(names), name=names[0]))
            parts.append(_t(language, "resolve.d6b.only_in").format(dir=d, names=said))
    return " ".join(parts) or None


# ---------------------------------------------------------------- wc avec total

_WC_UNITS = {"-l": "lines", "--lines": "lines", "-w": "words", "--words": "words",
             "-c": "bytes", "--bytes": "bytes", "-m": "chars", "--chars": "chars"}


def _wc_total(first, args, cmd, failed, output, language="fr"):
    options = [a for a in args if a.startswith("-")]
    if first != "wc" or failed or _chained(cmd) or len(options) != 1 or options[0] not in _WC_UNITS:
        return None
    rows = [re.match(r"^\s*(\d+)\s+(.+?)\s*$", l) for l in output.splitlines() if l.strip()]
    if len(rows) < 3 or not all(rows) or rows[-1][2] not in ("total", "au total"):
        return None
    sizes = [(int(r[1]), r[2]) for r in rows[:-1]]
    total = int(rows[-1][1])
    if sum(s for s, _ in sizes) != total:
        return None
    largest, name = max(sizes, key=lambda s: s[0])
    unit = _count(language, total, "resolve.d6b.wc_" + _WC_UNITS[options[0]])
    return _t(language, "resolve.d6b.wc_total").format(total=unit, k=len(sizes), max=largest, file=_base(name))


# ---------------------------------------------------------------- bilan de rsync

_RSYNC_TOTAL = re.compile(r"^total size is (?P<size>[\d,.]+)(?P<unit>[KMGTP]?)\s+speedup is \S+\s*$", re.M)
_RSYNC_SENT = re.compile(r"^sent [\d,.]+\w? bytes\s+received [\d,.]+\w? bytes", re.M)
_RSYNC_FILES = (re.compile(r"^Number of regular files transferred: (?P<n>[\d,.]+)$", re.M),
                re.compile(r"^Transfer starting: (?P<n>\d+) files?$", re.M))


def _rsync_summary(first, args, cmd, failed, output, language="fr"):
    if first != "rsync" or failed or _chained(cmd) or "DRY RUN" in output:
        return None
    total, sent = _RSYNC_TOTAL.search(output), _RSYNC_SENT.search(output)
    if not (total and sent) or total["unit"] or not re.fullmatch(r"\d{1,3}(?:([,.])\d{3})*|\d+", total["size"]):
        return None
    size = re.sub(r"[,.]", "", total["size"])
    count = ""
    for pattern, key in zip(_RSYNC_FILES, ("resolve.d6b.rsync_transferred", "resolve.d6b.rsync_listed")):
        if m := pattern.search(output):
            n = int(re.sub(r"[,.]", "", m["n"]))
            count = _t(language, key + ("_one" if n == 1 else "_many")).format(n=n)
            break
    return _t(language, "resolve.d6b.rsync_done").format(count=count, size=size)


# ---------------------------------------------------------------- D6/D : wget, curl, ss, ip route, nmcli
#
# Formats documentés des outils (manuel GNU Wget, curl, ss(8), ip-route(8), nmcli(1)).
# Les traductions gettext mettent des espaces insécables autour des deux-points : toute
# regex française les accepte. Hors format connu, on se tait et le modèle parle.

_NB = "[ \xa0]"
_WGET_URL = re.compile(r"^(?:FINISHED )?--\d{4}-\d\d-\d\d \d\d:\d\d:\d\d--[ \xa0]+(\S+)", re.M)
_WGET_SUMMARY = re.compile(
    rf"^(?:Downloaded|Téléchargés){_NB}?:{_NB}+(\d+){_NB}+(?:files?|fichiers?),{_NB}+([\d.,]+[KMGTP]?)"
    rf"{_NB}+(?:in|en){_NB}", re.M)
_WGET_HTTP_ERROR = re.compile(rf"^\d{{4}}-\d\d-\d\d \d\d:\d\d:\d\d (?:ERROR|ERREUR|erreur){_NB}(\d{{3}}){_NB}?:", re.M)
_WGET_RESPONSE = re.compile(r"(?:awaiting response|en attente de la réponse)(?:\.\.\.|…)[ \xa0]*(\d{3})[ \xa0]*([^\r\n]*?)\s*$",
                            re.M)
_WGET_SAVED = re.compile(r"[‘'«\"][ \xa0]?([^’'»\"\n]+?)[ \xa0]?[’'»\"] (?:saved|sauvegardé) \[(\d+)(?:/(\d+))?\]")
_WGET_LENGTH = re.compile(rf"^(?:Length|Taille){_NB}?:{_NB}(\d+)(?:{_NB}\(([\d.,]+[KMGTP]?)\))?", re.M)
_WGET_UNRESOLVED = re.compile(r"(?:unable to resolve host address|impossible de résoudre l[’']adresse de l[’']hôte)"
                              r"[ \xa0][‘'«\"][ \xa0]?([^’'»\"\s]+)")
_WGET_REFUSED = re.compile(r"^(?:Connecting to|Connexion à) ([^\s|:(]+)(?: \([^)]*\))?(?:\|[^|]*\|)?:(\d+)(?:\.\.\.|…)"
                           r"[ \xa0]?(?:failed: Connection refused|échec[ \xa0]?: Connexion refusée)", re.M)


def _url_name(url: str) -> str:
    """Dernier segment non vide du chemin d'une URL ; vide pour une racine."""
    path = re.sub(r"^[a-z]+://[^/]*", "", url).split("?", 1)[0].split("#", 1)[0]
    return next((seg for seg in reversed(path.split("/")) if seg), "")


def _size_text(value: str, language: str) -> str:
    """Taille lue dans la sortie, séparateur décimal de la session ; octets nus nommés."""
    if value.isdigit():
        return _t(language, "resolve.d6d.bytes").format(n=value)
    return value.replace(".", ",") if language != "en" else value.replace(",", ".")


def _more(n: int, language: str) -> str:
    return _t(language, "resolve.d6d.more_one") if n == 1 else _t(language, "resolve.d6d.more").format(n=n)


def _failed_prefix(failed: bool, language: str) -> str:
    return _t(language, "resolve.failed") + " " if failed else ""


def _wget(failed: bool, output: str, language: str = "fr") -> str | None:
    urls = [*_WGET_URL.finditer(output)]
    errors, silent = [], 0
    for i, url in enumerate(urls):
        block = output[url.end():urls[i + 1].start() if i + 1 < len(urls) else len(output)]
        if err := _WGET_HTTP_ERROR.search(block):
            errors.append((err[1], _url_name(url[1]) or url[1]))
        elif not _WGET_SAVED.search(block):
            silent += 1
    if summary := [*_WGET_SUMMARY.finditer(output)]:
        count, size = int(summary[-1][1]), summary[-1][2]
        # une URL ni enregistrée ni en erreur HTTP (nom non résolu, TLS) : bilan incomplet
        if failed != bool(errors) or (failed and silent):
            return None
        said = _t(language, "resolve.d6d.wget_summary").format(
            files=_tn(language, count, "resolve.d6d.file_one", "resolve.d6d.file_many"), size=_size_text(size, language))
        if errors:
            code, name = errors[0]
            key = "resolve.d6d.http_error_one" if len(errors) == 1 else "resolve.d6d.http_error_many"
            said += " " + _t(language, key).format(n=len(errors), code=code, name=name)
        return _failed_prefix(failed, language) + said
    if len([u for u in urls if not u[0].startswith("FINISHED")]) > 1:
        return None
    if failed:
        if m := _WGET_UNRESOLVED.search(output):
            return _t(language, "resolve.net.host_not_found").format(host=m[1])
        if m := _WGET_REFUSED.search(output):
            return _t(language, "resolve.net.connection_refused").format(host=m[1], port=m[2])
        resp = [*_WGET_RESPONSE.finditer(output)]
        if resp and int(resp[-1][1]) >= 400 and urls:
            status = f"{resp[-1][1]} {resp[-1][2]}".strip()
            name = _url_name(urls[0][1]) or urls[0][1]
            return _t(language, "resolve.d6d.http_failed").format(status=status, name=name)
        return None
    saved = _WGET_SAVED.findall(output)
    if len(saved) != 1 or errors:
        return None
    name, got, total = saved[0]
    if total and got != total:
        return None
    length = _WGET_LENGTH.search(output)
    size = _size_text(length[2], language) if length and length[2] else _size_text(got, language)
    return _t(language, "resolve.d6d.downloaded").format(name=_base(name), size=size)


_CMD_URL = re.compile(r"https?://[^\s'\"]+")
_CURL_STATUS = re.compile(r"^(< )?HTTP/[\d.]+ (\d{3})[ \t]*([^\r\n]*?)\s*$", re.M)
_CURL_METER_HEAD = re.compile(r"^\s*% Total\s+% Received % Xferd|^\s+Dload\s+Upload\s+Total")
_CLOCK = r"(?:--:--:--|\d+:\d\d:\d\d)"
_CURL_METER_ROW = re.compile(rf"^\s*(\d{{1,3}})\s+(\S+)\s+(\d{{1,3}})\s+(\S+)\s+\d{{1,3}}\s+\S+\s+\S+\s+\S+\s+"
                             rf"{_CLOCK}\s+{_CLOCK}\s+{_CLOCK}\s+\S+")


def _short_flag(args: list[str], letter: str, *long: str) -> bool:
    return any(a in long or re.fullmatch(rf"-[a-zA-Z]*{letter}[a-zA-Z]*", a) for a in args)


def _curl_meter_received(output: str) -> str | None:
    """Octets reçus quand la barre de progression finit à 100 %, sinon None."""
    rows = [m for l in re.split(r"[\r\n]", output) if (m := _CURL_METER_ROW.match(l))]
    if not rows or rows[-1][1] != "100" or rows[-1][3] != "100":
        return None
    return rows[-1][4]


def _curl_status(args: list[str], cmd: str, output: str, language: str = "fr") -> str | None:
    verbose = _short_flag(args, "v", "--verbose")
    include = _short_flag(args, "i", "--include")
    if not (verbose or include) or len(re.findall(r"https?://", cmd)) > 1:
        return None
    lines = [m for m in _CURL_STATUS.finditer(output) if (m[1] and verbose) or (not m[1] and include)]
    if not lines:
        return None
    code, reason = lines[-1][2], lines[-1][3]
    said = _t(language, "resolve.d6d.http_status").format(status=f"{code} {reason}".strip())
    url = re.search(_CMD_URL, cmd)
    if url and (host := _URL_HOST.match(url[0])):
        said += _t(language, "resolve.d6d.http_from").format(host=host[1])
    if url and (name := _url_name(url[0])):
        said += _t(language, "resolve.d6d.http_resource").format(name=name)
    if code.startswith("2") and (got := _curl_meter_received(output)):
        said += _t(language, "resolve.d6d.received").format(size=_size_text(got, language))
    return said + "."


def _curl_output_name(args: list[str], cmd: str) -> str | None:
    """Fichier écrit par curl (-o, -O), '' pour un rejet (/dev/null, sortie standard)."""
    for i, a in enumerate(args):
        if (a in ("-o", "--output") or re.fullmatch(r"-[a-zA-Z]*o", a)) and i + 1 < len(args):
            target = args[i + 1]
            return "" if target in ("/dev/null", "-") else _base(target)
    if _short_flag(args, "O", "--remote-name"):
        url = re.search(_CMD_URL, cmd)
        return _url_name(url[0]) if url else None
    return ""


def _curl_meter(args: list[str], cmd: str, output: str, language: str = "fr") -> str | None:
    lines = [l for l in re.split(r"[\r\n]", output) if l.strip()]
    if not lines or not all(_CURL_METER_HEAD.match(l) or _CURL_METER_ROW.match(l) for l in lines):
        return None
    got = _curl_meter_received(output)
    name = _curl_output_name(args, cmd)
    if not got or name is None:
        return None
    size = _size_text(got, language)
    if name:
        return _t(language, "resolve.d6d.downloaded").format(name=name, size=size)
    return _t(language, "resolve.d6d.transfer_done").format(size=size)


_SS_HEAD = re.compile(r"^(Netid\s+)?State\s+Recv-Q\s+Send-Q\s+Local Address:Port")
_SS_NETIDS = {"tcp", "udp", "raw", "sctp", "mptcp", "dccp"}
_SS_PROC = re.compile(r'users:\(\("([^"]+)"')
_LIST_MAX = 6


def _ss_listening(args: list[str], output: str, language: str = "fr") -> str | None:
    if not _short_flag(args, "l", "--listening"):
        return None
    lines = [l for l in output.splitlines() if l.strip()]
    head = _SS_HEAD.match(lines[0]) if lines else None
    if not head:
        return None
    groups: dict[str | None, set[str]] = {}
    for line in lines[1:]:
        cols = line.split()
        if head[1]:
            if cols[0] not in _SS_NETIDS:
                continue
            cols = cols[1:]
        if len(cols) < 5 or cols[0] not in ("LISTEN", "UNCONN") or ":" not in cols[3]:
            continue
        proc = m[1] if (m := _SS_PROC.search(line)) else None
        groups.setdefault(proc, set()).add(cols[3].rsplit(":", 1)[1])
    if not groups:
        return None
    ports = {p for ps in groups.values() for p in ps}
    order = sorted(groups, key=lambda g: (g is None, min(int(p) if p.isdigit() else 1 << 20 for p in groups[g])))
    items, listed = [], 0
    for proc in order:
        shown = sorted(groups[proc], key=lambda p: (not p.isdigit(), int(p) if p.isdigit() else 0, p))
        shown = shown[:max(_LIST_MAX - listed, 0)]
        if not shown:
            break
        listed += len(shown)
        text = _join(shown, language)
        if proc is None and len(groups) == 1:
            items.append(text)
        else:
            name = proc if proc is not None else _t(language, "resolve.d6d.unknown_proc")
            items.append(_t(language, "resolve.d6d.proc_ports").format(proc=name, ports=text))
    said = ", ".join(items)
    if listed < len(ports):
        said += _more(len(ports) - listed, language)
    count = _tn(language, len(ports), "resolve.d6d.port_one", "resolve.d6d.port_many")
    return _t(language, "resolve.d6d.listening").format(ports=count, items=said)


_IP_ROUTE_WORDS = {"route", "r", "ro", "rou", "rout"}
_IP_ROUTE_LINE = re.compile(r"^(?:default|[\da-fA-F.:]+(?:/\d+)?|unreachable|blackhole|prohibit|throw|local|broadcast|"
                            r"multicast|nat|anycast)\s")
_IP_DEFAULT = re.compile(r"^default(?: via (\S+))? dev (\S+)")
_LINKDOWN_MAX = 3


def _ip_route(args: list[str], output: str, language: str = "fr") -> str | None:
    words = [a for a in args if not a.startswith("-")]
    if not words or words[0] not in _IP_ROUTE_WORDS or words[1:] not in ([], ["show"], ["list"], ["ls"]):
        return None
    lines = [l for l in output.splitlines() if l.strip()]
    if not lines or not all(_IP_ROUTE_LINE.match(l) or l[0].isspace() for l in lines):
        return None
    defaults = [m for l in lines if (m := _IP_DEFAULT.match(l))]
    # route par défaut multichemin : « default proto ra » puis des lignes « nexthop »
    if len(defaults) != sum(l.startswith("default") for l in lines):
        return None
    if not defaults:
        said = _t(language, "resolve.d6d.no_default")
    else:
        gw, dev = defaults[0][1], defaults[0][2]
        said = (_t(language, "resolve.d6d.gateway").format(gw=gw, dev=dev) if gw
                else _t(language, "resolve.d6d.default_dev").format(dev=dev))
        if len(defaults) > 1:
            said += _t(language, "resolve.d6d.defaults_count").format(n=len(defaults))
        said += "."
    down = list(dict.fromkeys(m[1] for l in lines if re.search(r"\slinkdown\b", l) and (m := re.search(r"\sdev (\S+)", l))))
    if down:
        said += " " + _t(language, "resolve.d6d.linkdown").format(devs=_capped_list(down, _LINKDOWN_MAX, language, ", "))
    return said


_NM_COLUMNS = {"DEVICE": "device", "PÉRIPHÉRIQUE": "device", "TYPE": "type", "STATE": "state", "ÉTAT": "state",
               "CONNECTION": "connection", "CONNEXION": "connection", "NAME": "name", "NOM": "name", "UUID": "uuid"}
_NM_STATES = {"connected": "connected", "connecté": "connected", "connected (externally)": "connected",
              "connecté (en externe)": "connected", "disconnected": "disconnected", "déconnecté": "disconnected",
              "unavailable": "unavailable", "indisponible": "unavailable", "unmanaged": "unmanaged",
              "non géré": "unmanaged"}
_NM_ITEMS_MAX = 6


def _nm_table(output: str) -> list[dict[str, str]] | None:
    lines = [l for l in output.splitlines() if l.strip()]
    if len(lines) < 2:
        return None
    starts = [(m.start(), _NM_COLUMNS.get(m[0])) for m in re.finditer(r"\S+", lines[0])]
    if any(name is None for _, name in starts):
        return None
    rows = []
    for line in lines[1:]:
        bounds = [s for s, _ in starts] + [len(line)]
        rows.append({name: line[bounds[i]:bounds[i + 1]].strip() for i, (_, name) in enumerate(starts)})
    return rows


def _nm_capped(items: list[str], language: str) -> str:
    return _capped_list(items, _NM_ITEMS_MAX, language)


def _nmcli(args: list[str], output: str, language: str = "fr") -> str | None:
    if args[:1] in (["device"], ["dev"], ["d"]) and args[1:] in ([], ["status"]):
        rows = _nm_table(output)
        if not rows or not all(k in rows[0] for k in ("device", "type", "state", "connection")):
            return None
        items = []
        for row in rows:
            if row["type"] == "loopback":
                continue
            state = _NM_STATES.get(row["state"])
            if state is None or (state == "connected" and row["connection"] in ("", "--")):
                return None
            items.append(_t(language, f"resolve.d6d.nm.{state}").format(dev=row["device"], conn=row["connection"]))
        return _nm_capped(items, language) + "." if items else None
    if args[:1] in (["connection"], ["con"], ["c"]) and args[1:] in ([], ["show"]):
        rows = _nm_table(output)
        if not rows or not all(k in rows[0] for k in ("name", "uuid", "device")):
            return None
        items = [_t(language, "resolve.d6d.conn_idle").format(name=r["name"]) if r["device"] in ("", "--")
                 else _t(language, "resolve.d6d.conn_on").format(name=r["name"], dev=r["device"]) for r in rows]
        count = _tn(language, len(rows), "resolve.d6d.connection_one", "resolve.d6d.connection_many")
        return _t(language, "resolve.d6d.connections").format(conns=count, items=_nm_capped(items, language))
    return None


# ---------------------------------------------------------------- fichier absent, permission

_FILE_ERRORS = (
    ("No such file or directory|Aucun fichier ou dossier de ce nom", "resolve.file.not_found"),
    ("Permission denied|Permission non accordée", "resolve.file.permission_denied"),
    ("Is a directory|Est un dossier", "resolve.file.is_a_directory"),
    ("Not a directory|N'est pas un dossier", "resolve.file.not_a_directory"),
)


def _file_error(first, args, cmd, failed, output, language="fr"):
    lines = [l for l in output.splitlines() if l.strip()]
    if not failed or len(lines) > 5 or "Traceback" in output:
        return None
    for line in lines:
        for pattern, said_key in _FILE_ERRORS:
            m = re.search(rf"^(.*?)\s*:\s*(?:\[Errno \d+\]\s*)?(?:{pattern})", line)
            if not m or ":" not in m[1]:
                continue
            segment = m[1].split(":")[1]
            quoted = re.search(r"['‘«]\s*([^'’»]+?)\s*['’»]", segment)
            path = quoted[1] if quoted else (segment.split() or [""])[-1]
            if path:
                return _t(language, "resolve.file.error").format(path=_base(path), said=_t(language, said_key))
    return None


# ---------------------------------------------------------------- état du système

_UNITS = {"K": "digest.human.K", "M": "digest.human.M", "G": "digest.human.G",
          "T": "digest.human.T", "P": "digest.human.P", "B": "digest.human.B"}
_SINCE = {"year": ("since.year", "since.years"), "month": ("since.month", "since.months"),
          "week": ("since.week", "since.weeks"), "day": ("since.day", "since.days"),
          "h": ("since.h", "since.h"), "min": ("since.min", "since.min"),
          "s": ("since.s", "since.s"), "ms": ("since.ms", "since.ms")}
_LISTING_FIRST = {"ls", "find", "sort", "cut", "du", "fd", "locate"}


def _human(value: str, language: str = "fr") -> str | None:
    m = re.fullmatch(r"([\d.,]+)([KMGTPB])i?", value)
    return f"{m[1]} {_t(language, _UNITS[m[2]])}" if m else None


def _since(text: str, language: str = "fr") -> str:
    def word(m):
        one_key, many_key = _SINCE[m[2].rstrip("s") if m[2] not in ("s", "ms") else m[2]]
        return f"{m[1]} {_t(language, one_key if m[1] == '1' else many_key)}"
    return re.sub(r"(\d+)\s*(years?|months?|weeks?|days?|h|min|ms|s)\b", word, text)


def _du(first, args, cmd, failed, output, language="fr"):
    """`du -c` passe avant la dernière erreur d'outil : son total dit aussi les erreurs."""
    if first == "du" and "|" not in cmd and _short_flag(args, "c", "--total"):
        return _du_total(failed, output, language)
    return None


def _system(first, args, cmd, failed, output, language="fr"):
    if first == "du" and "|" not in cmd and _short_flag(args, "c", "--total"):
        return _du_total(failed, output, language)
    if first == "smartctl":
        return _smart_health(args, failed, output, language)
    if failed:
        return None
    if first == "top":
        return _top_header(output, language)
    if first == "memory_pressure":
        return _memory_pressure(output, language)
    if first == "vmstat" and "-s" in args:
        return _vmstat_s(output, language)
    if first == "lsof":
        return _lsof(args, output, language)
    if first == "diskutil" and args[:1] == ["info"]:
        return _diskutil_info(output, language)
    if first == "free":
        return _free(output, language)
    if first == "systemctl" and "status" in args:
        return _service(output, language)
    if first == "df":
        disks = _disks(output, language)
        return disks.replace("\n", ". ") + "." if disks else None
    if first == "ifconfig" or (first == "ip" and any(a in ("a", "addr", "address") for a in args)):
        return _network_sentence(_network(output, language), language)
    if "|" in cmd and re.search(r"\|\s*(?:sudo\s+)?(?:grep|rg|awk|sed)\b", cmd):
        return None
    listing = (first in _LISTING_FIRST or (first == "docker" and args[:1] == ["ps"])
               or (first in ("dnf", "yum") and "check-update" in args))
    counted = _list(cmd, output, 200, language) if listing else None
    return counted.split("\n", 1)[0] + "." if counted else None


def _free(output: str, language: str = "fr") -> str | None:
    mem = re.findall(r"^(?:Mem|Mém)\.?\s*:\s+(.+)$", output, re.M)
    if not mem or not re.search(r"^\s+total.*(?:available|disponible)\s*$", output, re.M):
        return None
    cols = mem[-1].split()
    total, avail = _human(cols[0], language), _human(cols[-1], language)
    return _t(language, "resolve.system.memory").format(avail=avail, total=total) if total and avail else None


def _service(output: str, language: str = "fr") -> str | None:
    said = []
    for block in re.split(r"(?m)^(?=[●○×*] )", output):
        unit = re.match(r"[●○×*] (\S+)", block)
        state = re.search(r"^\s*Active: (\S+) \(([^)]+)\)(?: since [^;]+; (.+?) ago)?", block, re.M)
        if not (unit and state):
            continue
        name = re.sub(r"\.service$", "", unit[1])
        if state[1] == "active":
            if state[3]:
                said.append(_t(language, "resolve.system.service_active_since").format(
                    name=name, since=_since(state[3], language)))
            else:
                said.append(_t(language, "resolve.system.service_active").format(name=name))
        elif state[1] == "inactive":
            said.append(_t(language, "resolve.system.service_inactive").format(name=name))
        else:
            return None
    return ". ".join(said) + "." if said else None


def _network_sentence(digested: str | None, language: str = "fr") -> str | None:
    if not digested:
        return None
    lines = digested.splitlines()
    prefix = _t(language, "digest.network.virtual").split(":")[0]
    virtual = next((l for l in lines if l.startswith(prefix)), None)
    active = [l for l in lines if l is not virtual]
    if not active:
        return None
    said = ", ".join(active) + "."
    if virtual:
        count = int(virtual.rsplit(":", 1)[1])
        noun = _t(language, "digest.network.virtual_noun_one" if count == 1 else "digest.network.virtual_noun_many")
        said += " " + _t(language, "digest.network.virtual_sentence").format(n=count, noun=noun)
    return said


# ---------------------------------------------------------------- D6/D : du -c, top, mémoire, lsof, disques
#
# Formats documentés : du(1), procps top(1), memory_pressure(1), vmstat(8), lsof(8),
# diskutil(8), smartctl(8). Tailles recopiées telles que l'outil les écrit ; une taille en
# blocs sans unité (du sans -h) n'est jamais dite.

_DU_TOTAL = re.compile(r"^(\S+)\s+total$")
_DU_ERROR = re.compile(r"^du: (?:cannot read directory|cannot access|impossible de lire le répertoire|"
                       r"impossible d[’']accéder à) ['‘«][ \xa0]?(.+?)[ \xa0]?['’»][ \xa0]?: (.+)$")


def _du_total(failed: bool, output: str, language: str = "fr") -> str | None:
    lines = [l for l in output.splitlines() if l.strip()]
    total = _DU_TOTAL.match(lines[-1]) if lines else None
    if not total or total[1].isdigit():
        return None
    size = _size_text(total[1], language)
    errors = [l for l in lines if l.startswith("du:")]
    if failed != bool(errors):
        return None
    if not errors:
        return _t(language, "resolve.d6d.du_total").format(size=size)
    parsed = [_DU_ERROR.match(l) for l in errors]
    if not all(parsed):
        return None
    msg = parsed[0][2].strip().rstrip(".")
    cause = next((key for pattern, key in _FILE_ERRORS if re.fullmatch(pattern, msg)), None)
    if not cause:
        return None
    key = "resolve.d6d.error_one" if len(errors) == 1 else "resolve.d6d.error_many"
    said = _t(language, key).format(n=len(errors), path=_base(parsed[0][1]), cause=_t(language, cause))
    return _t(language, "resolve.d6d.du_failed").format(size=size, errors=said)


_SMART_RESULT = re.compile(r"^(?:SMART overall-health self-assessment test result|SMART Health Status): (\w+)", re.M)


def _smart_health(args: list[str], failed: bool, output: str, language: str = "fr") -> str | None:
    dev = next((a for a in reversed(args) if a.startswith("/dev/")), None)
    result = _SMART_RESULT.search(output)
    if not dev or not result or not _short_flag(args, "H", "--health"):
        return None
    # un bit d'erreur avec PASSED (attribut sous le seuil, journal d'erreurs) : le modèle détaille
    if result[1] in ("PASSED", "OK") and not failed:
        return _t(language, "resolve.d6d.smart_passed").format(dev=_base(dev))
    if result[1] == "FAILED" and failed:
        return _t(language, "resolve.d6d.smart_failed").format(dev=_base(dev))
    return None


_TOP_HEAD = re.compile(r"^top - \S+ up (?P<up>.+?),\s+\d+ users?,\s+load average: (?P<load>\d+[.,]\d+)", re.M)
_TOP_TASKS = re.compile(r"^Tasks:\s*(\d+) total,\s*(\d+) running", re.M)


def _uptime_text(up: str, language: str) -> str | None:
    parts = []
    for part in (p.strip() for p in up.split(",")):
        if m := re.fullmatch(r"(\d+) days?", part):
            parts.append(f"{m[1]} {_t(language, 'since.day' if m[1] == '1' else 'since.days')}")
        elif m := re.fullmatch(r"(\d+):(\d\d)", part):
            parts.append(_t(language, "resolve.d6d.clock").format(h=m[1], m=m[2]))
        elif m := re.fullmatch(r"(\d+) min", part):
            parts.append(f"{m[1]} {_t(language, 'since.min')}")
        else:
            return None
    return " ".join(parts) or None


def _top_header(output: str, language: str = "fr") -> str | None:
    heads, tasks = [*_TOP_HEAD.finditer(output)], _TOP_TASKS.findall(output)
    if not heads or not tasks:
        return None
    up = _uptime_text(heads[-1]["up"], language)
    if not up:
        return None
    total, running = int(tasks[-1][0]), tasks[-1][1]
    return _t(language, "resolve.d6d.top").format(
        up=up, tasks=_tn(language, total, "resolve.d6d.task_one", "resolve.d6d.task_many"), running=running,
        load=_decimal(heads[-1]["load"].replace(",", "."), language))


def _memory_pressure(output: str, language: str = "fr") -> str | None:
    pct = re.search(r"^System-wide memory free percentage: (\d+)%", output, re.M)
    if not pct:
        return None
    pages = re.search(r"^Pages free:\s*(\d+)", output, re.M)
    extra = _t(language, "resolve.d6d.free_pages").format(n=pages[1]) if pages else ""
    return _t(language, "resolve.d6d.memory_pressure").format(pct=pct[1], pages=extra)


_VMSTAT_TOTAL = re.compile(r"^\s*(\d+) K (?:total memory|mémoire totale)\s*$", re.M)
_VMSTAT_FREE = re.compile(r"^\s*(\d+) K (?:free memory|mémoire libre)\s*$", re.M)


def _kib_text(kib: int, language: str) -> str:
    for unit, div in (("G", 1 << 20), ("M", 1 << 10)):
        if kib >= div:
            value = kib / div
            number = f"{value:.0f}" if value >= 100 else f"{value:.1f}"
            return f"{_decimal(number, language)} {_t(language, _UNITS[unit])}"
    return f"{kib} {_t(language, _UNITS['K'])}"


def _vmstat_s(output: str, language: str = "fr") -> str | None:
    total, free = _VMSTAT_TOTAL.search(output), _VMSTAT_FREE.search(output)
    if not total or not free:
        return None
    return _t(language, "resolve.d6d.vmstat").format(total=_kib_text(int(total[1]), language),
                                                     free=_kib_text(int(free[1]), language))


_LSOF_PROCS_MAX = 4


def _lsof(args: list[str], output: str, language: str = "fr") -> str | None:
    spec = path = None
    i = 0
    while i < len(args):
        a = args[i]
        if a == "-i" and i + 1 < len(args):
            spec, i = args[i + 1], i + 2
        elif a.startswith("-i") and len(a) > 2:
            spec, i = a[2:], i + 1
        elif re.fullmatch(r"-[Pnlw]+", a):
            i += 1
        elif not a.startswith("-") and path is None:
            path, i = a, i + 1
        else:
            return None
    if (spec is None) == (path is None):
        return None
    port = None
    if spec is not None:
        m = re.fullmatch(r"(?:tcp|udp|TCP|UDP)?(?:@[^:]*)?:(\d+)", spec)
        if not m:
            return None
        port = m[1]
    lines = output.splitlines()
    head = next((n for n, l in enumerate(lines) if re.match(r"COMMAND\s+PID\s", l)), None)
    if head is None:
        return None
    procs: dict[tuple[str, str], bool] = {}
    for line in lines[head + 1:]:
        cols = line.split()
        if not cols:
            continue
        if len(cols) < 3 or not cols[1].isdigit():
            return None
        procs[(cols[0], cols[1])] = procs.get((cols[0], cols[1]), False) or line.rstrip().endswith("(LISTEN)")
    if not procs:
        return None
    items = [_t(language, "resolve.d6d.proc_pid").format(cmd=c, pid=p)
             + (_t(language, "resolve.d6d.proc_listening") if port and listening else "")
             for (c, p), listening in procs.items()]
    said = _capped_list(items, _LSOF_PROCS_MAX, language, " ; " if len(items) > 2 else ", ")
    if port:
        return _t(language, "resolve.d6d.lsof_port").format(port=port, procs=said)
    return _t(language, "resolve.d6d.lsof_file").format(name=_base(path), procs=said)


_DISK_FIELD = re.compile(r"^[ \t]*([^:\n]+?):[ \t]+(\S[^\n]*?)[ \t]*$", re.M)
_DISK_LOCATION = {"Internal": "resolve.d6d.disk_internal", "External": "resolve.d6d.disk_external"}
_DISK_SMART = {"Verified": "resolve.d6d.smart_verified", "Failing": "resolve.d6d.smart_failing",
               "Not Supported": "resolve.d6d.smart_unsupported"}


def _diskutil_info(output: str, language: str = "fr") -> str | None:
    fields = {m[1]: m[2] for m in _DISK_FIELD.finditer(output)}
    ident = fields.get("Device Identifier")
    # un volume : sa place libre compte plus que la taille du disque, le modèle la dit
    if fields.get("Volume Name", "Not applicable").split(" (")[0] != "Not applicable":
        return None
    size = re.match(r"([\d.]+) (B|KB|MB|GB|TB|PB)\b", fields.get("Disk Size", ""))
    if not ident or not size:
        return None
    parts = [fields["Device / Media Name"]] if fields.get("Device / Media Name") else []
    parts.append(f"{_decimal(size[1], language)} {_t(language, _UNITS[size[2][0]])}")
    if loc := _DISK_LOCATION.get(fields.get("Device Location", "")):
        parts.append(_t(language, loc))
    if fields.get("Solid State") == "Yes":
        parts.append("SSD")
    if smart := _DISK_SMART.get(fields.get("SMART Status", "")):
        parts.append(_t(language, smart))
    return _t(language, "resolve.d6d.disk").format(id=ident, parts=", ".join(parts))


# ---------------------------------------------------------------- D6/D : services (systemctl, brew services)
#
# systemctl(1) list-timers (trié par prochaine échéance, bilan « N timers listed. »),
# is-enabled (un état par unité, dans l'ordre des arguments), brew services list.

_TIMERS_COUNT = re.compile(r"^(\d+) timers? listed\.", re.M)
_TIMER_ROW = re.compile(r"^\w{3} \d{4}-\d\d-\d\d \d\d:\d\d:\d\d \S+\s+(?P<left>\d.*?)\s+"
                        r"(?:\w{3} \d{4}-\d\d-\d\d \d\d:\d\d:\d\d \S+|-|n/a)\s.*?(?P<unit>\S+)\.timer\b")
_UNIT_STATES = {"enabled", "disabled", "static", "masked", "alias", "indirect", "generated", "transient", "linked",
                "not-found"}
_BREW_HEAD = re.compile(r"^Name\s+Status\s+User\s+(?:File|Plist)\s*$")
_BREW_GROUPS = (("started", "resolve.d6d.started_one", "resolve.d6d.started_many"),
                ("error", "resolve.d6d.errored_one", "resolve.d6d.errored_many"),
                ("scheduled", "resolve.d6d.scheduled_one", "resolve.d6d.scheduled_many"))
_NAMES_MAX = 5


def _services(first, args, cmd, failed, output, language="fr"):
    if first == "systemctl":
        words = [a for a in args if not a.startswith("-")]
        if words == ["list-timers"] and not failed:
            return _timers(output, language)
        if words[:1] == ["is-enabled"] and len(words) > 1:
            return _is_enabled(words[1:], output, language)
    if first == "brew" and args[:1] == ["services"] and args[1:] in ([], ["list"]) and not failed:
        return _brew_services(output, language)
    return None


def _timers(output: str, language: str = "fr") -> str | None:
    count = _TIMERS_COUNT.search(output)
    if not count:
        return None
    n = int(count[1])
    if n == 0:
        return _t(language, "resolve.d6d.no_timers")
    timers = _tn(language, n, "resolve.d6d.timer_one", "resolve.d6d.timer_many")
    rows = [l for l in output.splitlines()[1:] if l.strip()]
    row = _TIMER_ROW.match(rows[0]) if rows else None
    if not row:
        return _t(language, "resolve.d6d.timers_count").format(timers=timers)
    return _t(language, "resolve.d6d.timers").format(timers=timers, left=_since(row["left"], language), unit=row["unit"])


def _is_enabled(units: list[str], output: str, language: str = "fr") -> str | None:
    states = [l.strip() for l in output.splitlines() if l.strip()]
    if len(states) != len(units) or any(s not in _UNIT_STATES for s in states):
        return None
    groups: dict[str, list[str]] = {}
    for unit, state in zip(units, states, strict=True):
        groups.setdefault(state, []).append(re.sub(r"\.service$", "", unit))
    return " ".join(
        _t(language, "resolve.d6d.state_group").format(
            label=_t(language, f"resolve.d6d.state.{state}.{'one' if len(names) == 1 else 'many'}"),
            units=_join(names, language))
        for state, names in groups.items())


def _capped_list(items: list[str], limit: int, language: str, sep: str = ", ") -> str:
    """Liste lue en entier jusqu'à `limit`, sinon les premiers puis « et N autres »."""
    if len(items) <= limit:
        return _join(items, language, sep)
    return sep.join(items[:limit]) + _more(len(items) - limit, language)


def _names_capped(names: list[str], language: str) -> str:
    return _capped_list(names, _NAMES_MAX, language)


def _brew_services(output: str, language: str = "fr") -> str | None:
    lines = [l for l in output.splitlines() if l.strip()]
    if not lines or not _BREW_HEAD.match(lines[0]):
        return None
    rows = [l.split()[:2] for l in lines[1:]]
    if not rows or any(len(r) < 2 or r[1] not in ("none", "started", "stopped", "error", "scheduled") for r in rows):
        return None
    services = _tn(language, len(rows), "resolve.d6d.service_one", "resolve.d6d.service_many")
    groups = {status: _t(language, "resolve.d6d.brew_group").format(
                  count=_tn(language, len(names), one, many), names=_names_capped(names, language))
              for status, one, many in _BREW_GROUPS if (names := [r[0] for r in rows if r[1] == status])}
    said = (f"{services}, {groups.pop('started')}." if "started" in groups
            else _t(language, "resolve.d6d.brew_none").format(
                services=services, names=_names_capped([r[0] for r in rows], language)))
    return " ".join([said, *(g + "." for g in groups.values())])


# ---------------------------------------------------------------- D6/D : bases (psql, sqlite3)
#
# libpq 14+ : « psql: error: connection to server at "h" (a), port P failed: … », une
# tentative par adresse ; messages du serveur « ERROR:  relation "t" does not exist » ;
# bilan « (N rows) ». sqlite3 : « Parse error …: near "x": syntax error », « no such
# table: t ». Tout autre message reste au modèle.

_PG_SERVER_ERROR = re.compile(r"^(?:psql:\S+ )?ERROR:\s+(.+)$", re.M)
_PG_CONN = re.compile(r'connection to server (?:at "(?P<host>[^"]+)" \([^)]*\), port (?P<port>\d+)|'
                      r'on socket "(?P<sock>[^"]+)") failed: (?P<msg>.+)$', re.M)
_PG_ROWS = re.compile(r"^\((\d+) (?:rows?|lignes?)\)$", re.M)
_PG_SEP = re.compile(r"^-+(?:\+-+)*$")
_SQLITE_ERROR = re.compile(r"^(?:Parse error|Runtime error|Error)(?::? near line \d+| in [^:\n]+)?: (?:in prepare, )?(.+)$",
                           re.M)
_ROWS_READ_MAX, _CELL_MAX, _COLUMNS_MAX = 6, 40, 5


def _db(first, args, cmd, failed, output, language="fr"):
    if first == "psql":
        return _psql_error(output, language) if failed else _psql_rows(output, language)
    if first in ("sqlite3", "sqlite") and failed:
        m = _SQLITE_ERROR.search(output)
        return _sql_message(m[1], language, "resolve.d6d.table") if m else None
    return None


def _sql_message(msg: str, language: str, table_key: str) -> str | None:
    if m := re.match(r'relation "([^"]+)" does not exist|no such table: (\S+)', msg):
        return _t(language, table_key).format(name=m[1] or m[2])
    if m := re.match(r'column "([^"]+)" does not exist|no such column: (\S+)', msg):
        return _t(language, "resolve.d6d.column").format(name=m[1] or m[2])
    if m := re.match(r'syntax error at or near "([^"]+)"|near "([^"]+)": syntax error', msg):
        return _t(language, "resolve.d6d.syntax").format(tok=m[1] or m[2])
    return None


def _psql_error(output: str, language: str = "fr") -> str | None:
    if err := _PG_SERVER_ERROR.search(output):
        return _sql_message(err[1], language, "resolve.d6d.relation")
    if not output.lstrip().startswith("psql: error:"):
        return None
    tries = [*_PG_CONN.finditer(output)]
    if not tries:
        if m := re.search(r'could not translate host name "([^"]+)" to address', output):
            return _t(language, "resolve.net.host_not_found").format(host=m[1])
        return None
    # le refus d'une adresse (::1) précède souvent la vraie réponse du serveur sur une autre
    if fatal := next((t for t in tries if t["msg"].startswith("FATAL:")), None):
        if not fatal["host"]:
            return None
        for pattern, key, field in ((r'database "([^"]+)" does not exist', "resolve.d6d.db_missing", "db"),
                                    (r'role "([^"]+)" does not exist', "resolve.d6d.role_missing", "role"),
                                    (r'password authentication failed for user "([^"]+)"', "resolve.d6d.auth_rejected",
                                     "user")):
            if m := re.search(pattern, fatal["msg"]):
                return _t(language, key).format(host=fatal["host"], **{field: m[1]})
        return None
    msgs, first = {t["msg"].strip() for t in tries}, tries[0]
    if msgs == {"Connection refused"} and first["host"]:
        return _t(language, "resolve.net.connection_refused").format(host=first["host"], port=first["port"])
    if msgs == {"Connection timed out"} and first["host"]:
        return _t(language, "resolve.net.ssh_timeout").format(host=first["host"], port=first["port"])
    if msgs == {"No such file or directory"} and first["sock"] and (
            port := re.search(r"\.s\.PGSQL\.(\d+)$", first["sock"])):
        return _t(language, "resolve.d6d.pg_socket").format(port=port[1])
    return None


def _psql_rows(output: str, language: str = "fr") -> str | None:
    counts = _PG_ROWS.findall(output)
    if len(counts) != 1 or _PG_SERVER_ERROR.search(output):
        return None
    n = int(counts[0])
    lines = output.splitlines()
    end = next(i for i, l in enumerate(lines) if _PG_ROWS.match(l))
    sep = next((i for i in range(end) if _PG_SEP.match(lines[i])), None)
    if not sep:
        return None
    if n == 0:
        return _t(language, "resolve.d6d.no_rows")
    cols = [c.strip() for c in lines[sep - 1].split("|")]
    cells = [[c.strip() for c in l.split("|")] for l in lines[sep + 1:end]]
    if len(cells) != n or any(len(r) != len(cols) for r in cells):
        return None
    rows = _tn(language, n, "resolve.d6d.row_one", "resolve.d6d.row_many")
    if len(cols) <= 2 and n <= _ROWS_READ_MAX and all(c and len(c) <= _CELL_MAX for r in cells for c in r):
        return _t(language, "resolve.d6d.rows_values").format(rows=rows, values=", ".join(" ".join(r) for r in cells))
    if len(cols) <= _COLUMNS_MAX and all(cols):
        return _t(language, "resolve.d6d.rows_columns").format(rows=rows, cols=_join(cols, language))
    return None


# ---------------------------------------------------------------- matériel (lspci)

def _hardware(first, args, cmd, failed, output, language="fr"):
    if first != "lspci" or failed:
        return None
    pci = _pci(output, language)
    return pci.replace("\n", ", ") + "." if pci else None


# ---------------------------------------------------------------- conteneurs (docker)

_DOCKER_STATS_ROW = re.compile(
    r"^\S+\s+(?P<name>\S+)\s+[\d.]+%\s+[\d.]+\S*\s*/\s*(?P<limit>[\d.]+\S*)\s+(?P<pct>[\d.]+)%", re.M)
_DOCKER_DF_ROW = re.compile(
    r"^(?P<type>Images|Containers|Local Volumes|Build Cache)\s+\d+\s+\d+\s+(?P<size>[\d.]+\S*)\s+"
    r"(?P<recl>[\d.]+\S*)\s*\((?P<pct>\d+)%\)", re.M)
_DOCKER_DF_LABELS = {"Images": "digest.docker.label_images", "Containers": "digest.docker.label_containers",
                     "Local Volumes": "digest.docker.label_volumes", "Build Cache": "digest.docker.label_buildcache"}
_DOCKER_IMAGES_ROW = re.compile(r"^(?P<repo>\S+)\s+(?P<tag>\S+)\s+\S+\s+(?P<created>.+)\s+(?P<size>\S+)$", re.M)
_DOCKER_BUILD_DOCKERFILE_LINE = re.compile(r"^Dockerfile:(\d+)$", re.M)
_DOCKER_BUILD_STEP = re.compile(r"^#\d+ \[(\d+)/(\d+)\] RUN (.+)$", re.M)
_DOCKER_BUILD_EXITCODE = re.compile(r"exit code (\d+)")
_DOCKER_BUILD_NAMED = re.compile(r"naming to (\S+) done")
_DOCKER_COMPOSE_UNHEALTHY = re.compile(r"dependency failed to start: container (\S+) is unhealthy")


def _decimal(value: str, language: str) -> str:
    return value if language == "en" else value.replace(".", ",")


def _docker_stats(output: str, language: str = "fr") -> str | None:
    rows = [(m["name"], m["pct"], m["limit"]) for m in _DOCKER_STATS_ROW.finditer(output)]
    if not rows:
        return None
    name, pct, limit = max(rows, key=lambda r: float(r[1]))
    if float(pct) < 90:
        return None
    return _t(language, "resolve.docker.stats_high").format(name=name, pct=_decimal(pct, language), limit=limit)


def _docker_df(output: str, language: str = "fr") -> str | None:
    rows = {m["type"]: (m["size"], m["recl"], int(m["pct"])) for m in _DOCKER_DF_ROW.finditer(output)}
    if not rows:
        return None
    parts = []
    if img := rows.get("Images"):
        size, recl, pct = img
        size, recl = _decimal(size, language), _decimal(recl, language)
        parts.append(_t(language, "resolve.docker.df_images_full").format(size=size) if pct == 100
                      else _t(language, "resolve.docker.df_images_partial").format(size=size, recl=recl))
    for t, (size, recl, pct) in rows.items():
        if t != "Images" and pct == 100:
            label = _t(language, _DOCKER_DF_LABELS[t])
            parts.append(_t(language, "resolve.docker.df_other_full").format(label=label, size=_decimal(size, language)))
            break
    return ", ".join(parts) + "." if parts else None


def _docker_images(output: str, language: str = "fr") -> str | None:
    lines = [l for l in output.splitlines() if l.strip()]
    if len(lines) < 2 or not lines[0].startswith("REPOSITORY"):
        return None
    rows = [m for l in lines[1:] if (m := _DOCKER_IMAGES_ROW.match(l))]
    if not rows:
        return None
    first_repo, first_tag, first_size = rows[0]["repo"], rows[0]["tag"], rows[0]["size"]
    others = []
    for m in rows[1:]:
        if m["repo"] not in (first_repo, "<none>") and m["repo"] not in others:
            others.append(m["repo"])
        if len(others) == 2:
            break
    head = _t(language, "resolve.docker.images_head").format(repo=first_repo, tag=first_tag, size=first_size)
    also = _t(language, "resolve.docker.images_also")
    return head + (also + ", ".join(others) + "." if others else ".")


def _docker_build(failed: bool, output: str, language: str = "fr") -> str | None:
    if failed:
        line = _DOCKER_BUILD_DOCKERFILE_LINE.search(output)
        steps = [*_DOCKER_BUILD_STEP.finditer(output)]
        if not (line and steps):
            return None
        step = steps[-1]
        code = _DOCKER_BUILD_EXITCODE.search(output)
        parts = [_t(language, "resolve.docker.build_dockerfile_line").format(line=line[1]),
                 _t(language, "resolve.docker.build_step").format(a=step[1], b=step[2]), step[3]]
        if code:
            parts.append(_t(language, "resolve.docker.build_exit_code").format(code=code[1]))
        return _t(language, "resolve.failed") + " " + ", ".join(parts) + "."
    if m := _DOCKER_BUILD_NAMED.search(output):
        image = m[1].rsplit("/", 1)[-1]
        return _t(language, "resolve.docker.build_done").format(image=image)
    return None


def _containers(first, args, cmd, failed, output, language="fr"):
    if first == "kubectl":
        return _kubectl_unreachable(output, language) if failed else None
    if first == "helm":
        return _helm(args, cmd, failed, output, language)
    if first != "docker":
        return None
    if args[:1] == ["stats"] and not failed:
        return _docker_stats(output, language)
    if args[:2] == ["system", "df"] and not failed:
        return _docker_df(output, language)
    if args[:1] == ["images"] and not failed:
        return _docker_images(output, language)
    if args[:1] == ["build"] or args[:2] == ["buildx", "build"]:
        return _docker_build(failed, output, language) or (_buildkit_error(output, language) if failed else None)
    if args[:2] == ["compose", "up"] and failed:
        if m := _DOCKER_COMPOSE_UNHEALTHY.search(output):
            return _t(language, "resolve.docker.compose_unhealthy").format(name=m[1])
        return None
    return None


# D6 lot C : BuildKit (« ERROR: failed to solve: »), client-go de kubectl, helm lint et template
_BUILDKIT_SOLVE = re.compile(r"^ERROR: failed to solve: (.+)$", re.M)
_BUILDKIT_UNKNOWN = re.compile(r"dockerfile parse error on line (\d+): unknown instruction: (\S+)"
                               r"(?: \(did you mean (\S+?)\?\))?")
_BUILDKIT_IMAGE = re.compile(r"^(\S+): failed to resolve source metadata for \S+: .*\bnot found$")
_BUILDKIT_CONTEXT = re.compile(r'failed to calculate checksum of ref \S+ "/?([^"]+)": not found')
_KUBE_REFUSED = re.compile(r"The connection to the server (\S+) was refused")
_KUBE_UNABLE = re.compile(r"^Unable to connect to the server: (.+)$", re.M)
_KUBE_SERVER = re.compile(r'https?://([^/"\\\s?]+)')
_KUBE_REASONS = ((r"Timeout|timeout|deadline exceeded|timed out", "resolve.d6c.kube.timeout"),
                 (r"connection refused", "resolve.d6c.kube.refused"), (r"no such host", "resolve.d6c.kube.no_host"))
_HELM_VALUE_OPTIONS = {"--set", "--set-string", "--set-file", "--set-json", "-f", "--values", "-n", "--namespace",
                       "--version", "--repo", "--kube-version", "--api-versions", "-a", "--output-dir", "-s",
                       "--show-only", "--name-template", "--post-renderer"}


def _buildkit_error(output: str, language: str) -> str | None:
    m = _BUILDKIT_SOLVE.search(output)
    if not m:
        return None
    line = _DOCKER_BUILD_DOCKERFILE_LINE.search(output)
    at = _t(language, "resolve.d6c.docker.at_line").format(line=line[1]) if line else ""
    if u := _BUILDKIT_UNKNOWN.search(m[1]):
        said = _t(language, "resolve.d6c.docker.unknown_instruction").format(line=u[1], instr=u[2])
        return said + (_t(language, "resolve.d6c.docker.did_you_mean").format(sugg=u[3]) if u[3] else "") + "."
    if i := _BUILDKIT_IMAGE.match(m[1]):
        return _t(language, "resolve.d6c.docker.image_not_found").format(image=i[1]) + at + "."
    if c := _BUILDKIT_CONTEXT.search(m[1]):
        return _t(language, "resolve.d6c.docker.context_missing").format(file=c[1]) + at + "."
    return Skeleton(_t(language, "resolve.d6c.docker.failed") + at + ".")


def _kubectl_unreachable(output: str, language: str) -> str | None:
    if m := _KUBE_REFUSED.search(output):
        server, reason = m[1], "resolve.d6c.kube.refused"
    elif m := _KUBE_UNABLE.search(output):
        server = _KUBE_SERVER.search(output)
        reason = next((key for pattern, key in _KUBE_REASONS if re.search(pattern, m[1])), None)
        if not server:
            return None
        server = server[1]
    else:
        return None
    said = _t(language, "resolve.d6c.kube.unreachable").format(server=server)
    return said + _t(language, reason) + "." if reason else Skeleton(said + ".")


def _helm(args, cmd, failed, output, language):
    if "|" in cmd or not args:
        return None
    if args[0] == "lint" and failed:
        summary = re.search(r"(\d+) chart\(s\) linted, (\d+) chart\(s\) failed", output)
        charts = re.findall(r"^==> Linting (\S+)", output, re.M)
        errors = len(re.findall(r"^\[ERROR\]", output, re.M))
        if not summary or not int(summary[2]):
            return None
        if len(charts) == 1 and errors:
            count = _tn(language, errors, "resolve.tests.error", "resolve.tests.error_many")
            return Skeleton(_t(language, "resolve.d6c.helm.lint_one").format(chart=_base(charts[0]), errors=count))
        return Skeleton(_t(language, "resolve.d6c.helm.lint_many").format(failed=summary[2], n=summary[1]))
    if args[0] == "template" and not failed:
        kinds = re.findall(r"^kind: (\w+)\s*$", output, re.M)
        chart = re.search(r"^# Source: ([^/\s]+)/", output, re.M)
        if not kinds or not chart:
            return None
        positional, skip = [], False
        for a in args[1:]:
            if skip:
                skip = False
            elif a in _HELM_VALUE_OPTIONS:
                skip = True
            elif not a.startswith("-"):
                positional.append(a)
        said = _t(language, "resolve.d6c.helm.rendered").format(chart=chart[1])
        # NAME CHART : le second argument doit être le chart rendu, sinon une option inconnue a décalé la lecture
        if len(positional) == 2 and _base(positional[1]) == chart[1]:
            said += _t(language, "resolve.d6c.helm.for_release").format(release=positional[0])
        counted = {k: kinds.count(k) for k in dict.fromkeys(kinds)}
        names = [k if c == 1 else f"{c} {k}" for k, c in counted.items()]
        said += ", " + _tn(language, len(kinds), "resolve.d6c.helm.manifest_one", "resolve.d6c.helm.manifest_many")
        return said + _names_tail(language, names, True) + "."
    return None


# ---------------------------------------------------------------- Terraform, OpenTofu (D6 lot C)
#
# Format des sorties de Terraform 1.x : lignes de bilan (Apply complete!, Plan:, No changes.),
# en-têtes d'action (« # adresse will be created »), cadres d'erreur « │ Error: ». Une erreur
# ou un avertissement laisse la cause au modèle.

_TF_APPLY = re.compile(r"^(Apply|Destroy) complete! Resources: (?:(\d+) added, (\d+) changed, )?(\d+) destroyed\.", re.M)
_TF_PLAN = re.compile(r"^Plan: (\d+) to add, (\d+) to change, (\d+) to destroy\.", re.M)
_TF_ACTION = re.compile(r"^\s+# (\S+) (?:is tainted, so )?(will be created|will be updated in-place|must be replaced"
                        r"|will be replaced|will be destroyed)", re.M)
_TF_ACTIONS = (("will be created", "resolve.d6c.tf.create"), ("will be updated in-place", "resolve.d6c.tf.update"),
               ("must be replaced", "resolve.d6c.tf.replace"), ("will be replaced", "resolve.d6c.tf.replace"),
               ("will be destroyed", "resolve.d6c.tf.destroy"))
_TF_ERROR = re.compile(r"^[│ ]*Error: ", re.M)
_TF_WARNING = re.compile(r"^[│ ]*Warning: ", re.M)
_TF_LOCATION = re.compile(r"^[│ ]*on (\S+) line (\d+)", re.M)
_TF_OUTPUT = re.compile(r"^([\w-]+) = (.*)$")
_TF_ADDRESS = re.compile(r"^(?:module\.[\w-]+(?:\[[^\]]+\])?\.)*(?:data\.)?[\w-]+\.[\w-]+(?:\[[^\]]+\])?$")


def _terraform(first, args, cmd, failed, output, language="fr"):
    if first not in ("terraform", "tofu") or "|" in cmd:
        return None
    if failed:
        errors = len(_TF_ERROR.findall(output))
        if not errors:
            return None
        where = _TF_LOCATION.search(output)
        if errors > 1:
            key = "resolve.d6c.tf.errors_at" if where else "resolve.d6c.tf.errors"
        else:
            key = "resolve.d6c.tf.error_at" if where else "resolve.d6c.tf.error"
        return Skeleton(_t(language, key).format(n=errors, file=_base(where[1]) if where else "",
                                                 line=where[2] if where else ""))
    words = [a for a in args if not a.startswith("-")]
    said = _tf_sentence(words, output, language)
    return Skeleton(said) if said and _TF_WARNING.search(output) else said


def _tf_sentence(words, output, language):
    if m := re.search(r"(Terraform|OpenTofu) has been successfully initialized", output):
        said = _t(language, "resolve.d6c.tf.init").format(tool=m[1])
        providers = [f"{p} {v}" for p, v in re.findall(r"^- Installed (\S+) v(\S+)", output, re.M)]
        if len(providers) == 1:
            said += _t(language, "resolve.d6c.tf.provider_one").format(names=providers[0])
        elif providers:
            said += ", " + _tn(language, len(providers), "resolve.d6c.tf.providers_one", "resolve.d6c.tf.providers_many")
            said += _names_tail(language, providers, True)
        return said + "."
    if m := _TF_APPLY.search(output):
        return _tf_apply(m, output, language)
    if m := _TF_PLAN.search(output):
        return _tf_plan(m, output, language)
    if re.search(r"^No changes\.", output, re.M):
        full = "Your infrastructure matches the configuration" in output
        return _t(language, "resolve.d6c.tf.no_changes_full" if full else "resolve.d6c.tf.no_changes")
    if words[:2] == ["state", "list"]:
        names = [l.strip() for l in output.splitlines() if l.strip()]
        if not names or not all(_TF_ADDRESS.match(n) for n in names):
            return None
        head = _tn(language, len(names), "resolve.d6c.tf.state_one", "resolve.d6c.tf.state_many")
        return head + _names_tail(language, names, True) + "."
    return None


def _tf_apply(m, output, language):
    said = _t(language, "resolve.d6c.tf.apply" if m[1] == "Apply" else "resolve.d6c.tf.destroyed")
    counts = [(int(n or 0), kind) for n, kind in zip(m.groups()[1:], ("added", "changed", "destroyed")) if int(n or 0)]
    parts = []
    for i, (n, kind) in enumerate(counts):
        noun = "res_" if i == 0 else ""
        parts.append(_tn(language, n, f"resolve.d6c.tf.{noun}{kind}_one", f"resolve.d6c.tf.{noun}{kind}_many"))
    said += _t(language, "resolve.d6c.colon") + ", ".join(parts) if parts else _t(language, "resolve.d6c.tf.nothing")
    said += "."
    if "\nOutputs:\n" not in output:
        return said
    lines = [l for l in output.split("\nOutputs:\n", 1)[1].splitlines() if l.strip()]
    outputs = [_TF_OUTPUT.match(l) for l in lines]
    if not all(outputs):
        return said
    simple = [(o[1], o[2].strip('"')) for o in outputs if o[2] != "<sensitive>"]
    if len(simple) <= 3 and all(re.fullmatch(r'"[^"]*"|[\w.:/@+-]+', o[2]) for o in outputs if o[2] != "<sensitive>"):
        return said + _t(language, "resolve.d6c.tf.outputs").format(items=", ".join(f"{k} {v}" for k, v in simple)) \
            if simple else said
    return said + " " + _tn(language, len(outputs), "resolve.d6c.tf.output_one", "resolve.d6c.tf.output_many") + "."


def _tf_plan(m, output, language):
    add, change, destroy = map(int, m.groups())
    parts = [_tn(language, n, f"resolve.d6c.tf.plan_{k}_one", f"resolve.d6c.tf.plan_{k}_many")
             for n, k in ((add, "add"), (change, "change"), (destroy, "destroy")) if n]
    if not parts:
        return None
    said = _t(language, "resolve.d6c.tf.plan") + _t(language, "resolve.d6c.colon") + ", ".join(parts) + "."
    actions = _TF_ACTION.findall(output)
    by_key = {}
    for address, action in actions:
        by_key.setdefault(dict(_TF_ACTIONS)[action], []).append(address)
    replaced = len(by_key.get("resolve.d6c.tf.replace", []))
    created, updated = len(by_key.get("resolve.d6c.tf.create", [])), len(by_key.get("resolve.d6c.tf.update", []))
    destroyed = len(by_key.get("resolve.d6c.tf.destroy", []))
    # un en-tête d'action hors format (objet déposé, lecture de données) : les compteurs suffisent
    if (created + replaced, updated, destroyed + replaced) != (add, change, destroy):
        return said
    for key in dict.fromkeys(k for _, k in _TF_ACTIONS):
        if key in by_key:
            said += _t(language, key).format(names=_capped(by_key[key], language))
    return said


# ---------------------------------------------------------------- trace Node.js
#
# Signature forte (message "Error: " suivi d'une frame "at fn (file:line:col)") : le
# programme lancé peut planter alors que la commande qui affiche son journal (docker
# logs, par exemple) rend elle-même le code 0. On ne se fie donc pas à `failed` ici.

_NODE_ERROR_MSG = re.compile(r"^Error: (.+)$", re.M)
_NODE_ERROR_FRAME = re.compile(r"at \S+ \(([^():]+):(\d+):\d+\)")


def _node_error(first, args, cmd, failed, output, language="fr"):
    msg = _NODE_ERROR_MSG.search(output)
    if not msg:
        return None
    frame = _NODE_ERROR_FRAME.search(output, msg.end())
    if not frame:
        return None
    return _t(language, "resolve.node_error").format(file=_base(frame[1]), line=frame[2], msg=_clean(msg[1]))


# ---------------------------------------------------------------- ps aux --sort

_PS_SORT = re.compile(r"--sort=-%(cpu|mem)\b")
_PS_ROW = re.compile(r"^(?P<user>\S+)\s+(?P<pid>\d+)\s+(?P<cpu>[\d.]+)\s+(?P<mem>[\d.]+)\s+(?:\S+\s+){6}(?P<cmd>.+)$", re.M)


_PS_NO_USER = re.compile(r"^(?:error|erreur)[ \xa0]?: (?:user name does not exist|le nom d'utilisateur n'existe pas)",
                         re.M)


def _ps_unknown_user(args: list[str], output: str, language: str = "fr") -> str | None:
    if not _PS_NO_USER.search(output):
        return None
    user = None
    for i, a in enumerate(args):
        if a in ("-u", "-U", "--user", "--User") and i + 1 < len(args):
            user = args[i + 1]
        elif m := re.fullmatch(r"--[uU]ser=(\S+)|-[uU](\w\S*)", a):
            user = m[1] or m[2]
    if not user or "," in user:
        return None
    return _t(language, "resolve.d6d.user_missing").format(user=user)


def _process(first, args, cmd, failed, output, language="fr"):
    if first == "ps" and failed:
        return _ps_unknown_user(args, output, language)
    if first != "ps" or failed:
        return None
    sort = _PS_SORT.search(" ".join(args))
    if not sort:
        return None
    lines = [l for l in output.splitlines() if l.strip()]
    if not lines or not lines[0].startswith("USER"):
        return None
    rows = [m for l in lines[1:] if (m := _PS_ROW.match(l))]
    if not rows:
        return None
    top = rows[0]
    name = top["cmd"].split()[0].rsplit("/", 1)[-1]
    key = sort[1]
    pct = _decimal(top["cpu"] if key == "cpu" else top["mem"], language)
    label = "CPU" if key == "cpu" else "RAM"
    return _t(language, "resolve.process").format(name=name, pct=pct, label=label, pid=top["pid"])


# ---------------------------------------------------------------- faits extraits en code (L5)
#
# Bloc de faits placé dans l'entrée du modèle quand `facts_block` est actif : le modèle
# voit déjà ces lignes dans la sortie mais ne les reprend pas (docs/deterministic-aids.md,
# L5). Chaque fait est une ligne recopiée de la sortie ou un nom lu dans un format fixe ;
# seul compte fait en code : les lignes « config.status: creating », une par fichier. Rien
# n'est déduit, pour ne jamais donner au modèle un fait faux.

_FACTS_MAX = 5
_FACT_CHARS = 200
_FACT_CONFIGURE_ERROR = re.compile(r"^configure: error: (?!in ['‘`])(.+)$", re.M)
_CONFIGURE_CREATED = re.compile(r"^config\.status: creating (\S+)$", re.M)
_MAKE_ENTERING = re.compile(r"[Mm]ake(?:\[\d+\])? ?: (?:Entering directory|on entre dans le répertoire) [«'‘`] ?(.+?) ?[»'’]$", re.M)
_FACT_CC_WARNING = re.compile(r"^(?P<file>[^\s:()]+):\d+:\d+: warning:", re.M)
_SCRIPT_LINE_ERROR = re.compile(r"^(?P<script>[^\s:]+): (?:line|ligne) (?P<line>\d+) ?: (?P<msg>.+)$", re.M)
_GENERIC_ERROR = re.compile(r"^(?:[\w./-]+: )*(?:fatal error|fatal|error|erreur|ERROR|Error|E|npm ERR!|npm error)\s?:? .+$", re.M)
_PYTEST_FIRST_ID = re.compile(r"^(?:FAILED|ERROR) (\S+::\S+)", re.M)
_UNITTEST_FIRST = re.compile(r"^(?:FAIL|ERROR): (\w+) \(", re.M)
_GO_FIRST = re.compile(r"^\s*--- FAIL: (\S+)", re.M)
_TAP_FIRST = re.compile(r"^not ok \d+ - (.+)$", re.M)
_TOOL_SUMMARY = re.compile("|".join((
    r"\d+ (?:passed|failed|errors?|skipped)\b.* in [\d.]+s",  # pytest
    r"^Ran \d+ tests? in ", r"^(?:OK|FAILED)(?: \(.+\))?$",  # unittest
    r"^Tests?:\s+.*\d+ total", r"^\s*Tests\s+.*\(\d+\)\s*$",  # jest, vitest
    r"^test result: ", r"^(?:ok|FAILED) \| \d+ passed",  # cargo, deno
    r"^# (?:tests|pass|fail) \d+$", r"^ℹ (?:tests|pass|fail) \d+$",  # node --test
    r"^Found \d+ errors?", r"^\[\*\] \d+ fixable", r"\d+ problems? \(\d+ errors?, \d+ warnings?\)",  # ruff, tsc, mypy, eslint
    r"\d+ (?:warnings?|errors?) generated", r"generated \d+ warnings?", r"rated at -?[\d.]+/10",  # clang, cargo, pylint
    r"^added \d+ packages?", r"\d+ vulnerabilit", r"^Packages: [+-]\d+",  # npm, pnpm
    r"^Successfully (?:installed|built|tagged) ", r"^(?:Resolved|Installed|Prepared) \d+ packages?",  # pip, uv
    r"^Installing \d+ packages?", r"^Writing lock file",  # poetry
    r"^(?:Apply|Destroy) complete! Resources:", r"^Plan: \d+ to add", r"has been successfully initialized",  # terraform
    r"^sent [\d,.]+ bytes", r"^total size is ", r"^Downloaded: \d+ files?", r"^FINISHED --",  # rsync, wget
    r"\d+ (?:upgraded|mis à jour), \d+ (?:newly installed|nouvellement installés)",  # apt
    r"WARNING: \d+ (?:computed checksums? did NOT match|listed files? could not be read)",  # sha*sum -c
    r"^\s*\d+\s+(?:total|au total)$", r"^\s*Finished .+ in [\d.]+", r"^\s*Locking \d+ packages?",  # wc, cargo
    r"\[100%\] Built target \S+", r"^BUILD (?:SUCCESSFUL|FAILED)", r"^\d+ files? changed",  # cmake, gradle, git
)), re.M)
_TAIL_SUMMARY = re.compile(
    r"(?i)\b(?:total|termin|done|finished|complete|réussi|success|succeeded|failed|échec|errors?|erreurs?|warnings?|"
    r"avertissements?|trait|processed|synchronis|synced|archiv|copi|bilan|summary|résumé)")
# une ligne de données ou de diagnostic n'est pas un bilan : position file:ligne:colonne,
# horodatage de journal, marqueur de make, message d'erreur ou d'avertissement
_NOT_SUMMARY = re.compile(r"\*\*\*|^\S*\d+:\d+\s|^(?:[A-Z][a-z]{2} +\d+ \d\d:\d\d|\d{4}-\d\d-\d\d)"
                          r"|(?i:\b(?:warning|error|erreur|avertissement|fatal)\s?:|^(?:error|erreur|fatal)\b)")
# renvoi vers un journal (npm, configure, pip) : jamais la cause elle-même
_LOG_POINTER = re.compile(r"(?i)log of this run|\.log\s*$|see .*\blog\b|for more details|see above")
_STANDALONE_NUMBER = re.compile(r"(?<![\w/.:-])\d+(?:[.,]\d+)?(?![\w/.:-])")
_SUMMARY_TRIM = " =-#✖✔ℹ\t"


def _shorten(text: str) -> str:
    return text if len(text) <= _FACT_CHARS else text[:_FACT_CHARS - 1].rstrip() + "…"


def _words(text: str, n: int = 18) -> str:
    return " ".join(text.split()[:n]).rstrip(".,;: ")


def _main_error(output: str, language: str, generic: bool) -> str | None:
    if found := _FACT_CONFIGURE_ERROR.findall(output):
        return _words(found[-1])
    if m := _CC_ERROR.search(output):
        return _t(language, "resolve.file_line").format(file=_base(m["file"]), line=m["line"] or m["line2"],
                                                         msg=_clean(m["msg"]))
    if m := _RUST_ERROR.search(output):
        msg = (m["code"] + ", " if m["code"] else "") + _clean(m["msg"])
        return _t(language, "resolve.file_line").format(file=_base(m["file"]), line=m["line"], msg=msg)
    if "Traceback (most recent call last):" in output:
        exc = _PY_EXC.match([l for l in output.splitlines() if l.strip()][-1].strip())
        frames = _PY_FRAME.findall(output)
        if exc and frames:
            what = " ".join(p for p in (exc[1], _clean(exc[2] or "")) if p)
            return _t(language, "resolve.file_line").format(file=_base(frames[-1][0]), line=frames[-1][1], msg=what)
    # outils en ligne de commande : la dernière ligne d'erreur porte la cause finale
    if generic and (found := [l for l in _GENERIC_ERROR.findall(output) if not _LOG_POINTER.search(l)]):
        return _words(found[-1])
    return None


def _first_failed_test(output: str) -> str | None:
    if m := _PYTEST_FIRST_ID.search(output):
        return m[1].partition("::")[2]
    for pattern in (_UNITTEST_FIRST, _CARGO_FIRST, _GO_FIRST, _TAP_FIRST):
        if m := pattern.search(output):
            return m[1].strip()
    if m := _JEST_FIRST.search(output):
        return m[1].strip().replace(" › ", ", ")
    return None


def _summary_lines(cmd: str, lines: list[str]) -> list[str]:
    picked = [i for i, l in enumerate(lines) if _TOOL_SUMMARY.search(l)]
    first, _ = _program(cmd.split("|")[0])
    # la dernière ligne d'un script ou d'un outil inconnu porte souvent son bilan ; pas celle
    # d'un visualiseur ou d'une liste, qui n'est qu'une ligne de données parmi d'autres
    viewer = first in _VIEWERS or first in _LIST_PROGRAMS or "|" in cmd
    last = len(lines) - 1
    tail = lines[last] if lines else ""
    if (not viewer and tail and last not in picked and _STANDALONE_NUMBER.search(tail)
            and _TAIL_SUMMARY.search(tail) and not _NOT_SUMMARY.search(tail)
            and not _GENERIC_ERROR.match(tail) and len(tail.split()) <= 15):
        picked.append(last)
    return [lines[i].strip(_SUMMARY_TRIM) for i in sorted(picked)[-2:]]


def extract_facts(cmd: str, exit_code: int | None, output: str, language: str = "fr") -> list[str]:
    """Faits sûrs lus en code dans la sortie, pour le bloc `facts_block` (vide : rien de sûr)."""
    from .textproc import strip_ansi

    output = strip_ansi(output)
    lines = [l for l in output.splitlines() if l.strip()]
    failed = exit_code not in (0, None)
    found: list[str] = []
    first_failed = _first_failed_test(output) if failed else None
    if failed and (error := _main_error(output, language, generic=not first_failed)):
        found.append(_t(language, "facts.error").format(msg=error))
    if m := _SCRIPT_LINE_ERROR.search(output):
        where = _t(language, "resolve.file_line").format(file=_base(m["script"]), line=m["line"],
                                                         msg=_words(m["msg"]))
        found.append(_t(language, "facts.script_error").format(msg=where))
    if first_failed:
        found.append(_t(language, "facts.first_failed").format(name=first_failed))
    warned = list(dict.fromkeys(_base(f) for f in _FACT_CC_WARNING.findall(output)))
    if warned:
        found.append(_t(language, "facts.warnings").format(files=", ".join(warned[:3])))
    created = list(dict.fromkeys(_base(f) for f in _CONFIGURE_CREATED.findall(output)))
    if created and not failed:
        total = len(_CONFIGURE_CREATED.findall(output))
        names = [n for n in ("Makefile", "config.h") if n in created] or created[:2]
        found.append(_t(language, "facts.generated").format(names=", ".join(names), n=total))
    if entered := _MAKE_ENTERING.findall(output):
        found.append(_t(language, "facts.project").format(name=_base(min(entered, key=len))))
    if summary := _summary_lines(cmd, lines):
        found.append(_t(language, "facts.summary").format(line=" ; ".join(summary)))
    return [_shorten(f) for f in dict.fromkeys(found)][:_FACTS_MAX]
