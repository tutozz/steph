"""Prononciation des sigles, commandes et mots anglais pour la synthèse française.

Graphies réglées par aller-retour Whisper sur Piper fr_FR-siwis-medium, avec
contrôle croisé sur la voix macOS Thomas : voir docs/pronunciation.md.
Un mot absent des tables est laissé tel quel quand la voix le lit déjà bien.
"""

from __future__ import annotations

import re

# Mots anglais et commandes, remplacés quelle que soit la casse.
SPOKEN: dict[str, str] = {
    "lspci": "L S, P C I",
    "pci": "P C I,",  # la virgule marque la pause : sans elle, Whisper entend « PC y »
    "lsusb": "L S U S B",
    "lsblk": "L S B L K",
    "dmesg": "D M E S G",
    "apt": "A P T",
    "npm": "N P M",
    "pnpm": "P N P M",
    "ssh": "S S H",
    "chmod": "C H mod",
    "systemctl": "système C T L",
    "git": "guite",
    "github": "guite hub",
    "commit": "commite",
    "commits": "commites",
    "kernel": "keurnel",
    "firmware": "feurmouère",
    "hash": "ache",
    "lite": "laïte",
    "limit": "limite",
    "controller": "contrôleur",
    "geforce": "gé force",
    "nvme": "N V M E",
    "gpu": "G, P, U",
    "pcie": "P C I express",
    "pch": "pé cé ache",
}

# Sigles qui sont aussi des mots français en minuscules : remplacés en capitales seulement.
CAPS_ONLY: dict[str, str] = {
    "BIOS": "baïosse",
}

# Mots aussi français : remplacés seulement à côté d'un mot technique.
AMBIGUOUS: dict[str, str] = {
    "pull": "pulle",
}

# Mots anglais bien lus tels quels, mais qui signalent un contexte technique.
TECH_CONTEXT = {"request", "origin", "rebase", "merge", "branch"}

# Sigles épelés lettre par lettre, quelle que soit la casse.
SPELLED = {
    "xhci", "ehci", "hcd", "amd", "cpu", "ssd", "hdd", "hdmi", "drm", "ahci",
    "uuid", "ram",
}

# Sigles que la voix lit déjà bien : laissés tels quels, en minuscules si la
# voix lit mieux la forme minuscule (SATA en capitales est entendu « Seta »).
KEEP: dict[str, str] = {
    "usb": "USB", "rtx": "RTX", "vga": "VGA", "acpi": "ACPI", "vram": "VRAM",
    "sata": "sata", "raid": "RAID", "cuda": "CUDA", "nasa": "NASA",
    "sudo": "sudo", "push": "push",  # lus à la française, Whisper les entend mieux qu'à l'anglaise
}

# Mots français courants écrits en capitales, à ne jamais épeler.
FRENCH_CAPS = {
    "OUI", "NON", "LE", "LA", "LES", "DE", "DES", "DU", "UN", "UNE", "ET", "OU", "EST",
    "IL", "ON", "EN", "AU", "AUX", "SUR", "PAR", "POUR", "PAS", "MAX", "MIN", "FIN",
}

_VOWELS = set("AEIOUY")
# Un mot collé à un point ou deux-points (script.sh, 2b:00.0, 1.2.3) n'est jamais touché.
_TOKEN = re.compile(r"(?<![\w.:])[A-Za-z0-9]+(?![\w]|[.:]\w)")
_MODEL = re.compile(r"^([A-Z]{1,4})([0-9]+)([A-Z]{0,3})$|^([0-9]+)([A-Z]{1,3})$")


def _spell(letters: str) -> str:
    return " ".join(letters.upper())


def _is_tech(word: str) -> bool:
    low = word.lower()
    return (low in SPOKEN or low in SPELLED or low in KEEP or low in TECH_CONTEXT
            or (word.isupper() and len(word) > 1 and word not in FRENCH_CAPS))


def _caps(word: str) -> str | None:
    if not (word.isalpha() and word.isupper() and 2 <= len(word) <= 6) or word in FRENCH_CAPS:
        return None
    if len(word) <= 3 or not (_VOWELS & set(word)):
        return _spell(word)
    return None


def _model(word: str) -> str | None:
    m = _MODEL.match(word)
    if not m:
        return None
    parts = [p for p in m.groups() if p]
    return " ".join(_spell(p) if p.isalpha() and len(p) <= 3 else p for p in parts)


def _word(word: str, prev: str, nxt: str) -> str:
    low = word.lower()
    if word in CAPS_ONLY:
        return CAPS_ONLY[word]
    if low in SPOKEN:
        return SPOKEN[low]
    if low in AMBIGUOUS:
        return AMBIGUOUS[low] if _is_tech(prev) or _is_tech(nxt) else word
    if low in KEEP:
        return KEEP[low]
    if low in SPELLED:
        return _spell(word)
    return _caps(word) or _model(word) or word


def pronounce(text: str) -> str:
    matches = list(_TOKEN.finditer(text))
    words = [m.group() for m in matches]
    out, last = [], 0
    for i, m in enumerate(matches):
        prev = words[i - 1] if i else ""
        nxt = words[i + 1] if i + 1 < len(words) else ""
        spoken = _word(m.group(), prev, nxt)
        if spoken.endswith(",") and text[m.end():m.end() + 1] in ("", ".", ",", ";", ":", "!", "?", ")", "]"):
            spoken = spoken[:-1]  # la ponctuation qui suit marque déjà la pause
        out.append(text[last:m.start()])
        out.append(spoken)
        last = m.end()
    out.append(text[last:])
    return "".join(out)


# ---------------------------------------------------------------- étape anglaise (Piper)
# Les mots anglais sont phonétisés par espeak-ng en anglais, puis ramenés aux sons que
# la voix française a appris : la table IPA de la voix contient les sons anglais, mais
# le modèle ne les a jamais entendus. Le résultat est passé à Piper en phonèmes bruts
# « [[ ... ]] » : à n'utiliser que juste avant la synthèse Piper, jamais pour la voix système.

_EN_TO_FR_MULTI = [
    ("aɪ", "aj"), ("eɪ", "ɛj"), ("oʊ", "o"), ("ɔɪ", "ɔj"), ("aʊ", "aw"), ("ɜː", "œʁ"),
    ("iː", "i"), ("uː", "u"), ("ɔː", "ɔ"), ("ɚ", "œʁ"),
]
_EN_TO_FR = {
    "ɹ": "ʁ", "r": "ʁ", "ʌ": "œ", "æ": "a", "ɾ": "t", "ʊ": "u", "ɪ": "i", "ᵻ": "i", "θ": "s", "ð": "z",
    "ɑ": "ɔ", "ɒ": "ɔ", "ɐ": "a", "ɜ": "œ", "ɫ": "l", "h": "", "ː": "", "ˌ": "", "ʔ": "", "ʲ": "",
}
UNTRAINED_PHONEMES = set("ɹʌæɾʊɪᵻθðɑɒɐɜɫhːˌʔɚʲ")
# ɑː : « docker » en américain (→ ɔ), « start » en britannique (→ a).
_LONG_A = {"en-us": "ɔ", "en": "a"}

_ENGLISH_WORD = re.compile(r"(?<![\w.:])[A-Za-z]+(?!\w|[.:]\w)")
_PHONEME_BLOCK = re.compile(r"(\[\[.*?\]\])")
_CAMEL = re.compile(r"[a-z][A-Z]")
_CAMEL_PARTS = re.compile(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])")
_LEXICON_WORDS = {
    w.lower()
    for table in (SPOKEN, CAPS_ONLY, AMBIGUOUS, KEEP)
    for spoken in table.values()
    for w in re.findall(r"[A-Za-zÀ-ÿ]+", spoken)
}

_english_words: tuple[frozenset[str], frozenset[str]] | None = None
_phonemizer = None
_CONTEXT = 3  # mots de part et d'autre où chercher un indice technique
ENGLISH_VOICE = "en-us"  # voix espeak-ng qui phonétise les mots anglais
_ANY_TOKEN = re.compile(r"\[\[.*?\]\]|\S+")


def _load_english_words() -> tuple[frozenset[str], frozenset[str]]:
    """(mots anglais, mots anglais qui sont aussi de vrais mots français)."""
    global _english_words
    if _english_words is None:
        import gzip
        from importlib.resources import files

        data = files("steph").joinpath("data/english_words.txt.gz").read_bytes()
        words = gzip.decompress(data).decode().split()
        _english_words = (frozenset(w for w in words if not w.startswith("~")),
                          frozenset(w[1:] for w in words if w.startswith("~")))
    return _english_words


def _english_ipa(text: str) -> str:
    global _phonemizer
    if _phonemizer is None:
        from piper.phonemize_espeak import EspeakPhonemizer

        _phonemizer = EspeakPhonemizer()
    ipa = "".join("".join(s) for s in _phonemizer.phonemize(ENGLISH_VOICE, text)).strip()
    ipa = ipa.replace("ɑːɹ", "aʁ")  # start, part : « ar », pas « or »
    ipa = ipa.replace("ɑː", _LONG_A.get(ENGLISH_VOICE, "a"))
    for en, fr in _EN_TO_FR_MULTI:
        ipa = ipa.replace(en, fr)
    ipa = "".join(_EN_TO_FR.get(c, c) for c in ipa)
    return re.sub("ʁ+", "ʁ", ipa)  # ɚ puis ɹ : un seul r


def _is_tech_token(tok: str) -> bool:
    word = tok.strip(".,;:!?()[]\"'")
    if tok.startswith("[[") or any(c.isdigit() for c in word) or _CAMEL.search(word):
        return True
    if word.isalpha() and word.isupper():  # sigle, ou lettre d'un sigle épelé
        return True
    english, _ = _load_english_words()
    return word.lower() in english or word.lower() in _LEXICON_WORDS


def _to_english(word: str, context: list[str]) -> str | None:
    if _CAMEL.search(word):
        return " ".join(_CAMEL_PARTS.findall(word))
    low = word.lower()
    if low in _LEXICON_WORDS:
        return None
    english, ambiguous = _load_english_words()
    if low in english or (low in ambiguous and any(_is_tech_token(t) for t in context)):
        return low
    return None


def warm_up() -> None:
    """Charge la liste de mots et espeak-ng d'avance : sinon la première phrase attend 0,2 s."""
    try:
        _load_english_words()
        _english_ipa("warm")
    except Exception:
        pass  # to_piper retombera sur le texte brut


def to_piper(text: str) -> str:
    """Remplace les mots anglais par leurs phonèmes, pour la seule voix Piper.

    Une panne de cette étape (liste de mots ou espeak-ng absents) rend le texte intact :
    la voix garde l'accent français plutôt que de se taire."""
    try:
        return _to_piper(text)
    except Exception:
        return text


def _to_piper(text: str) -> str:
    tokens = [(m.start(), m.end(), m.group()) for m in _ANY_TOKEN.finditer(text)]

    def context_of(pos: int) -> list[str]:
        i = next(k for k, (a, b, _) in enumerate(tokens) if a <= pos < b)
        return [t for k, (_, _, t) in enumerate(tokens) if k != i and abs(k - i) <= _CONTEXT]

    def repl(m: re.Match, offset: int) -> str:
        word = m.group()
        if word.islower() and len(word) >= 2 and not re.search("[aeiouy]", word):
            return _spell(word)  # pwd, ls : abréviation, lettres françaises
        english = _to_english(word, context_of(offset + m.start()))
        return f"[[ {_english_ipa(english)} ]]" if english else word

    out, pos = [], 0
    for i, part in enumerate(_PHONEME_BLOCK.split(text)):  # les blocs déjà en phonèmes restent tels quels
        out.append(part if i % 2 else _ENGLISH_WORD.sub(lambda m, o=pos: repl(m, o), part))
        pos += len(part)
    return "".join(out)
