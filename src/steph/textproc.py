"""Transformation du flux brut du terminal en texte exploitable.

`OutputCleaner` est incrémental : on lui donne des octets au fil de l'eau et il
maintient des lignes « propres » (sans séquences ANSI, retours chariot
appliqués), la ligne en cours non terminée, et une ligne de statut (texte
écrit entre sauvegarde/restauration du curseur, typiquement la barre
« Progress: [ 40%] » d'apt).
"""

from __future__ import annotations

import codecs
import re

MAX_LINES = 20000
KEEP_HEAD = 300


class OutputCleaner:
    def __init__(self) -> None:
        self._dec = codecs.getincrementaldecoder("utf-8")("replace")
        self.lines: list[str] = []
        self.dropped = 0  # lignes supprimées au milieu (sortie énorme)
        self.total_lines = 0
        self.cur: list[str] = []
        self.col = 0
        self.status = ""
        self._status_buf: list[str] | None = None
        self.fullscreen = False
        self._esc = ""  # séquence d'échappement en cours
        self.overwrites = 0  # nb de \r / effacements : indice de barre de progression

    # ---------------------------------------------------------------- API
    def feed(self, data: bytes) -> None:
        text = self._dec.decode(data)
        for ch in text:
            if self._esc:
                self._esc_char(ch)
            elif ch == "\x1b":
                self._esc = ch
            else:
                self._char(ch)

    @property
    def partial(self) -> str:
        return "".join(self.cur).rstrip()

    def text(self) -> str:
        out = list(self.lines)
        if self.partial:
            out.append(self.partial)
        return "\n".join(out)

    def tail(self, n: int) -> list[str]:
        out = self.lines[-n:]
        if self.partial:
            out = out[-(n - 1):] + [self.partial] if n > 1 else [self.partial]
        return out

    # ------------------------------------------------------------ interne
    def _target(self) -> list[str]:
        return self._status_buf if self._status_buf is not None else self.cur

    def _char(self, ch: str) -> None:
        if ch == "\n":
            if self._status_buf is not None:
                self._status_buf.clear()
                return
            self._commit()
        elif ch == "\r":
            self.col = 0
            self.overwrites += 1
        elif ch == "\b":
            self.col = max(0, self.col - 1)
        elif ch == "\t":
            self._put(" ")
        elif ch == "\x07" or (ord(ch) < 32):
            return
        else:
            self._put(ch)

    def _put(self, ch: str) -> None:
        buf = self._target()
        if self._status_buf is not None:
            buf.append(ch)
            return
        if self.col < len(buf):
            buf[self.col] = ch
        else:
            buf.extend(" " * (self.col - len(buf)))
            buf.append(ch)
        self.col += 1

    def _commit(self) -> None:
        line = "".join(self.cur).rstrip()
        self.cur = []
        self.col = 0
        self.lines.append(line)
        self.total_lines += 1
        if len(self.lines) > MAX_LINES:
            cut = len(self.lines) - MAX_LINES
            del self.lines[KEEP_HEAD:KEEP_HEAD + cut]
            self.dropped += cut

    def _esc_char(self, ch: str) -> None:
        seq = self._esc + ch
        if len(seq) == 2:
            if ch in "[]PX^_":
                self._esc = seq
                return
            if ch == "7":
                self._status_buf = []
            elif ch == "8":
                self._end_status()
            self._esc = ""
            return
        kind = seq[1]
        if kind == "[":
            if "\x40" <= ch <= "\x7e":
                self._csi(seq[2:-1], ch)
                self._esc = ""
            elif len(seq) > 64:
                self._esc = ""
            else:
                self._esc = seq
        else:  # OSC / DCS / etc. : terminé par BEL ou ST
            if ch == "\x07" or seq.endswith("\x1b\\"):
                self._esc = ""
            elif len(seq) > 4096:
                self._esc = ""
            else:
                self._esc = seq

    def _end_status(self) -> None:
        if self._status_buf is not None:
            s = "".join(self._status_buf).strip()
            if s:
                self.status = s
        self._status_buf = None

    def _csi(self, params: str, final: str) -> None:
        if final in "hl" and params.startswith("?"):
            modes = params[1:].split(";")
            if any(m in ("1049", "47", "1047") for m in modes):
                self.fullscreen = final == "h"
            return
        if final == "s":
            self._status_buf = []
        elif final == "u":
            self._end_status()
        elif final == "K":
            if self._status_buf is None:
                p = params or "0"
                if p == "0":
                    del self.cur[self.col:]
                elif p == "2":
                    self.cur = []
                self.overwrites += 1
        elif final == "G":
            try:
                self.col = max(0, int(params or "1") - 1)
            except ValueError:
                pass
        elif final == "C":
            self.col += int(params) if params.isdigit() else 1
        elif final == "D":
            self.col = max(0, self.col - (int(params) if params.isdigit() else 1))
        elif final == "A":
            # remontée de curseur : barres multiples (docker pull, pip…) ;
            # on réécrit la ligne courante plutôt que d'empiler.
            if self.cur:
                self._commit()
            self.overwrites += 1


# ------------------------------------------------------------------ helpers

ANSI_RE = re.compile(r"\x1b(\[[0-?]*[ -/]*[@-~]|\][^\x07\x1b]*(\x07|\x1b\\)|[@-Z\\-_])")


def strip_ansi(s: str) -> str:
    return ANSI_RE.sub("", s)


PROMPT_RE = re.compile(
    r"(\[[OoYy]/[nN]\]|\[[oOyY]/[Nn]\]|\([oOyY]/[nN]\)|\?\s*$|:\s*$|mot de passe|password|passphrase"
    r"|continuer|continue\s*\?|Appuyez|Press .*key|>\s*$)",
    re.IGNORECASE,
)


def looks_like_prompt(partial: str) -> bool:
    p = partial.strip()
    if not p or len(p) > 300:
        return False
    return bool(PROMPT_RE.search(p))


PCT_RE = re.compile(r"(\d{1,3}(?:[.,]\d+)?)\s?%")
FRACTION_RE = re.compile(r"\[\s*(\d+)\s*/\s*(\d+)\s*\]|\((\d+)\s*/\s*(\d+)\)")

# Étapes connues : (regex, gabarit). Le gabarit reçoit les groupes nommés.
STAGE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"^(?:Réception de|Get)\s*:\s*\d+\s+\S+\s+\S+\s+\S+\s+(?P<x>[\w.+-]+)\s+\S+\s+\S+\s+\["), "téléchargement de {x}"),
    (re.compile(r"^(?:Réception de|Get|Atteint|Hit|Ign)\s*:\s*\d+\s+\S+\s+(?P<x>\S+)"), "lecture des index de {x}"),
    (re.compile(r"^(?:Dépaquetage de|Unpacking)\s+(?P<x>[^\s:(]+)"), "décompression de {x}"),
    (re.compile(r"^(?:Paramétrage de|Setting up)\s+(?P<x>[^\s:(]+)"), "configuration de {x}"),
    (re.compile(r"^(?:Préparation du dépaquetage|Preparing to unpack)\s+\S*?(?P<x>[a-z0-9][a-z0-9+.-]+)_"), "préparation de {x}"),
    (re.compile(r"^(?:Traitement des actions différées|Processing triggers) \S+ (?P<x>\S+)"), "actions différées de {x}"),
    (re.compile(r"^Sélection du paquet|^Selecting previously"), "sélection des paquets"),
    (re.compile(r"^\s*(?:Installing|Upgrading|Installation|Mise à jour|Cleanup|Running scriptlet|Verifying|Vérification)\s*:?\s+(?P<x>[\w.+-]+)"), "{0} {x}"),
    (re.compile(r"^\s*\[\s*\d+/\s*\d+\]\s+(?P<v>\S+)\s+(?P<x>[\w.+-]+)"), "{v} {x}"),
    (re.compile(r"^Collecting (?P<x>\S+)"), "récupération de {x}"),
    (re.compile(r"^\s*Downloading (?P<x>\S+)"), "téléchargement de {x}"),
    (re.compile(r"^Installing collected packages"), "installation des paquets Python"),
    (re.compile(r"^\s*Compiling (?P<x>\S+)"), "compilation de {x}"),
    (re.compile(r"^\s*Building (?:\w+ object |target )?(?P<x>\S+)"), "compilation de {x}"),
    (re.compile(r"^(?:remote: )?(?P<v>Receiving objects|Resolving deltas|Counting objects|Compressing objects|Enumerating objects)"), "{v}"),
    (re.compile(r"^(?:remote: )?(?P<v>Réception d'objets|Résolution des deltas|Décompte des objets|Compression des objets|Énumération des objets|Mise à jour des fichiers)"), "{v}"),
    (re.compile(r"^(?P<x>[0-9a-f]{12}): (?P<v>Pulling fs layer|Downloading|Extracting|Pull complete|Waiting)"), "image docker, couche {v}"),
    (re.compile(r"^Step (?P<x>\d+/\d+)"), "étape {x} du build"),
    (re.compile(r"^#\d+ \[(?P<x>[^\]]+)\]"), "étape de build {x}"),
    (re.compile(r"^(?:TASK|PLAY) \[(?P<x>[^\]]+)\]"), "tâche {x}"),
]

STAGE_WORDS = {
    "Receiving objects": "réception des objets",
    "Réception d'objets": "réception des objets",
    "Résolution des deltas": "résolution des deltas",
    "Décompte des objets": "comptage des objets",
    "Compression des objets": "compression des objets",
    "Énumération des objets": "énumération des objets",
    "Mise à jour des fichiers": "écriture des fichiers",
    "Resolving deltas": "résolution des deltas",
    "Counting objects": "comptage des objets",
    "Compressing objects": "compression des objets",
    "Enumerating objects": "énumération des objets",
    "Pulling fs layer": "en attente",
    "Downloading": "téléchargement",
    "Extracting": "extraction",
    "Pull complete": "terminée",
    "Waiting": "en attente",
    "Installing": "installation de",
    "Upgrading": "mise à jour de",
    "Cleanup": "nettoyage de",
    "Verifying": "vérification de",
    "Running scriptlet": "script de",
}


def detect_stage(line: str) -> str | None:
    line = strip_ansi(line).strip()
    if not line:
        return None
    for rx, tpl in STAGE_PATTERNS:
        m = rx.search(line)
        if m:
            gd = {k: STAGE_WORDS.get(v, v) for k, v in m.groupdict().items() if v}
            first = line.split()[0].rstrip(":")
            try:
                return tpl.format(STAGE_WORDS.get(first, first.lower()), **gd)
            except (KeyError, IndexError):
                return None
    return None


def detect_percent(*texts: str) -> float | None:
    for t in texts:
        if not t:
            continue
        found = PCT_RE.findall(t)
        if found:
            try:
                v = float(found[-1].replace(",", "."))
            except ValueError:
                continue
            if 0 <= v <= 100:
                return v
        m = FRACTION_RE.findall(t)
        if m:
            a, b, c, d = m[-1]
            num, den = (a, b) if a else (c, d)
            if int(den) > 1:
                return 100.0 * int(num) / int(den)
    return None


ERROR_RE = re.compile(
    r"(error|erreur|échec|echec|failed|failure|fatal|traceback|exception|denied|refusé|interdit|"
    r"not found|introuvable|impossible|cannot|can't|unable|no such|aucun fichier|warning|avertissement|"
    r"^E:|^W:|panic|segmentation|killed|timed? ?out|expir)",
    re.IGNORECASE,
)


def important_lines(lines: list[str], limit: int = 40) -> list[str]:
    out = [l for l in lines if ERROR_RE.search(l)]
    # dédoublonnage en conservant l'ordre
    seen: set[str] = set()
    res = []
    for l in out:
        k = l.strip()
        if k and k not in seen:
            seen.add(k)
            res.append(l)
    return res[-limit:]


def compact_output(lines: list[str], max_chars: int = 6000, dropped: int = 0) -> str:
    """Tête + lignes importantes + queue, dans la limite de max_chars."""
    lines = [l for l in lines if l.strip()]
    # lignes tronquées seulement s'il y en a beaucoup (sinon une longue ligne
    # unique, ex. une liste Python, perdrait son contenu)
    width = max(160 if max_chars <= 3000 else 400, max_chars // max(1, len(lines)))
    lines = [l.rstrip()[:width] for l in lines]
    full = "\n".join(lines)
    if len(full) <= max_chars and not dropped:
        return full
    nh, nt = (8, 20) if max_chars <= 3000 else (25, 60)
    head = lines[:nh]
    tail = lines[-nt:]
    mid = [l for l in important_lines(lines[nh:-nt], 30 if max_chars > 3000 else 8)]
    parts = ["\n".join(head)]
    omitted = len(lines) - len(head) - len(tail) + dropped
    if mid:
        parts.append(f"[… {omitted} lignes omises ; lignes notables :]\n" + "\n".join(mid))
    else:
        parts.append(f"[… {omitted} lignes omises …]")
    parts.append("\n".join(tail))
    s = "\n".join(parts)
    if len(s) > max_chars:
        s = s[:max_chars // 3] + "\n[…]\n" + s[-(2 * max_chars // 3):]
    return s
