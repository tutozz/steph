"""Garde-fou d'ancrage : coupe toute proposition qui porte un fait introuvable dans l'entrée.

Le petit modèle qui résume la sortie du terminal invente parfois un compte, un nom de
service ou de fichier, un chemin ou une version absents de ce qu'il a reçu. Ce module ne
réécrit jamais ce que le modèle a dit : il retire seulement la proposition (segment entre
virgules ou points) qui porte un fait non vérifiable, avant que le texte parte à la voix.

Pour les questions sur l'historique (kind qa), si plus aucune proposition ne survit, la
réponse devient « Pas dans l'historique. » plutôt qu'une phrase vide.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterator

from .strings import t as _t

NOT_FOUND = "Pas dans l'historique."

_NUMBER_WORDS = {
    "zero": "0",
    "un": "1",
    "une": "1",
    "deux": "2",
    "trois": "3",
    "quatre": "4",
    "cinq": "5",
    "six": "6",
    "sept": "7",
    "huit": "8",
    "neuf": "9",
    "dix": "10",
    "onze": "11",
    "douze": "12",
    "treize": "13",
    "quatorze": "14",
    "quinze": "15",
    "seize": "16",
    "vingt": "20",
}

# Mots des nombres composés à tiret (« trente-six », « forty-five ») : lus comme un nombre
# à ancrer, jamais comme un identifiant. Tenus à part des mots simples ci-dessus pour ne pas
# changer l'ancrage d'un « trente » ou d'un « hundred » isolé.
_COMPOUND_WORDS = {
    **{w: int(v) for w, v in _NUMBER_WORDS.items()},
    "vingts": 20, "trente": 30, "quarante": 40, "cinquante": 50, "soixante": 60,
    "cent": 100, "cents": 100, "mille": 1000,
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
    "eighty": 80, "ninety": 90, "hundred": 100, "thousand": 1000,
}
_COMPOUND_JOINERS = {"et", "and"}

# Mots de gabarit du prompt système : jamais tirés de l'entrée, jamais à ancrer.
# Les deux langues cohabitent dans un seul ensemble (inoffensif : exclure un mot anglais
# en mode fr, ou l'inverse, ne fait disparaître aucun fait réel).
_TEMPLATE_WORDS = {
    "succes", "echec", "racine", "boot", "swap", "memoire", "backup",
    "cpu", "gpu", "usb", "sata", "vpn", "ip", "docker", "reseau", "reseaux",
    "tmpfs", "devtmpfs", "efivarfs", "overlay", "vram",
    "success", "failed", "root", "memory", "network", "networks",
}

_NUMBER_RE = re.compile(r"(?<!\d)\d+(?:[.,]\d+)?(?!\d)")
_WORD_RE = re.compile(r"[A-Za-zÀ-ÿ0-9][A-Za-zÀ-ÿ0-9._/-]*")
_HYPHENATED_RE = re.compile(r"[A-Za-zÀ-ÿ]+(?:-[A-Za-zÀ-ÿ]+)+")
# Nombre suivi d'une unité (8.9G, 100ms, 91%) : le nombre s'ancre seul, l'unité n'est pas un fait.
_NUMBER_WITH_UNIT_RE = re.compile(r"\d+(?:[.,]\d+)?[A-Za-zÀ-ÿ%]*")

# Ces deux nombres de métadonnées (code de sortie, compte de lignes affichées) sont
# présents dans presque toutes les entrées : les laisser ancrer n'importe quel autre
# nombre masquerait le défaut le plus fréquent du petit modèle, « ligne 1 » inventée.
_METADATA_NUMBER_RE = re.compile(r"\bcode\s*:?\s*\d+\b|\b\d+\s*lignes?\s+affich\w*", re.IGNORECASE)


def _fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    return "".join(c for c in text if not unicodedata.combining(c)).lower()


def _norm_number(value: str) -> str:
    value = value.replace(",", ".")
    if "." in value:
        whole, frac = value.split(".", 1)
        return f"{whole.lstrip('0') or '0'}.{frac}"
    return value.lstrip("0") or "0"


def _compound_value(tok: str) -> int | None:
    """Valeur d'un nombre composé à tiret écrit en lettres, français ou anglais ; None sinon."""
    parts = _fold(tok).split("-")
    if len(parts) < 2 or parts[0] in _COMPOUND_JOINERS or parts[-1] in _COMPOUND_JOINERS:
        return None
    if not all(p in _COMPOUND_WORDS or p in _COMPOUND_JOINERS for p in parts):
        return None
    total = current = 0
    for p in parts:
        if p in _COMPOUND_JOINERS:
            continue
        value = _COMPOUND_WORDS[p]
        if value == 100:
            current = (current or 1) * 100
        elif value == 1000:
            total += (current or 1) * 1000
            current = 0
        elif p.startswith("vingt") and current % 100 == 4:
            current += 76  # quatre-vingt(s)
        else:
            current += value
    return total + current


def _numbers_in(text: str) -> set[str]:
    found = {_norm_number(m) for m in _NUMBER_RE.findall(text)}
    folded = _fold(text)
    # le composé compte pour sa valeur seule : « trente-six » n'exige pas un 6
    for m in reversed(list(_HYPHENATED_RE.finditer(folded))):
        value = _compound_value(m.group())
        if value is not None:
            found.add(str(value))
            folded = folded[:m.start()] + " " + folded[m.end():]
    for word, digit in _NUMBER_WORDS.items():
        if re.search(rf"\b{word}\b", folded):
            found.add(digit)
    return found


def _clean_token(tok: str) -> str:
    return tok.strip("._-")


def _is_identifier(tok: str) -> bool:
    """Token composite (point, tiret, tiret bas) ou mêlant lettres et chiffres : pipewire.service, GA106, install-iso."""
    has_sep = bool(re.search(r"[A-Za-z].*[._/-]|[._/-].*[A-Za-z]", tok)) and any(c in tok for c in "._/-")
    has_digit_letter_mix = bool(re.search(r"[A-Za-z]", tok)) and bool(re.search(r"\d", tok))
    return has_sep or has_digit_letter_mix


def _is_proper_noun(tok: str, is_first: bool) -> bool:
    if is_first or len(tok) < 3:
        return False
    if not tok[0].isupper():
        return False
    if _fold(tok) in _TEMPLATE_WORDS:
        return False
    return tok[1:].islower()


def _is_fact(tok: str, is_first: bool) -> bool:
    if not tok or _compound_value(tok) is not None:
        return False
    if tok[0].isdigit():
        # empreinte ou version à lettres (2cb4b14…, 3.11-slim) lue entière ; nombre à unité
        # (8.9G) ou suite de chiffres (date, adresse IP) : ses nombres suffisent, comme avant
        return bool(re.search(r"[A-Za-zÀ-ÿ]", tok)) and not _NUMBER_WITH_UNIT_RE.fullmatch(tok)
    return _is_identifier(tok) or _is_proper_noun(tok, is_first)


def _facts_of(segment: str) -> list[str]:
    tokens = [_clean_token(t) for t in _WORD_RE.findall(segment)]
    return [t for i, t in enumerate(tokens) if _is_fact(t, i == 0)]


def _split_segments(text: str) -> list[tuple[str, str]]:
    """Découpe en (proposition, séparateur) sur virgule ou point de phrase, sans casser un
    nombre décimal ni un nom pointé. Le séparateur d'origine sert à recoller sans trou."""
    segments: list[tuple[str, str]] = []
    buf: list[str] = []
    n = len(text)
    for i, c in enumerate(text):
        prev = text[i - 1] if i > 0 else ""
        nxt = text[i + 1] if i + 1 < n else ""
        if c == "," and not (prev.isdigit() and nxt.isdigit()):
            segments.append(("".join(buf), ","))
            buf = []
        elif c == "." and (nxt == "" or nxt.isspace() and (
                not prev.isdigit() or (i + 2 < n and text[i + 2].isupper()))):
            # après un chiffre, seule une capitale derrière l'espace prouve la fin de phrase ;
            # en fin de texte la coupe est sûre : en flux, la dernière proposition reste retenue
            segments.append(("".join(buf), "."))
            buf = []
        else:
            buf.append(c)
    if buf:
        segments.append(("".join(buf), ""))
    return [(t.strip(), sep) for t, sep in segments if t.strip()]


def _fact_grounded(fact: str, input_folded: str) -> bool:
    pattern = rf"(?<![A-Za-z0-9]){re.escape(_fold(fact))}(?![A-Za-z0-9])"
    return re.search(pattern, input_folded) is not None


def _is_grounded(segment: str, numbers: set[str], input_folded: str) -> bool:
    for value in _numbers_in(segment):
        if value not in numbers:
            return False
    return all(_fact_grounded(fact, input_folded) for fact in _facts_of(segment))


def _emit(segments: list[tuple[str, str]], start: int, end: int, numbers: set[str],
          input_folded: str, last_kept: int | None) -> tuple[str, int | None]:
    """Décide, pour les propositions `segments[start:end]`, lesquelles garder ; recolle
    sans trou (virgule d'origine entre deux propositions adjacentes gardées, point sinon)."""
    parts: list[str] = []
    for i in range(start, end):
        text, _sep = segments[i]
        if not _is_grounded(text, numbers, input_folded):
            continue
        if last_kept is None:
            parts.append(text)
        elif last_kept == i - 1:
            bridge = ", " if segments[last_kept][1] == "," else ". "
            parts.append(bridge + text)
        else:
            parts.append(". " + text)
        last_kept = i
    return "".join(parts), last_kept


def ground(input_text: str, output_text: str, is_qa: bool = False, language: str = "fr") -> str:
    """Retire les propositions de *output_text* dont un nombre, un nom, un chemin ou une
    version est absent de *input_text*. En mode qa, une réponse entièrement invalidée
    devient « Pas dans l'historique. » (ou son équivalent dans `language`)."""
    if not output_text.strip():
        return output_text

    numbers = _numbers_in(_METADATA_NUMBER_RE.sub(" ", input_text))
    input_folded = _fold(input_text)
    segments = _split_segments(output_text)

    result, last_kept = _emit(segments, 0, len(segments), numbers, input_folded, None)
    if last_kept is None:
        return _t(language, "grounding.not_found") if is_qa else ""
    return result + "."


def ground_stream(pieces: Iterator[str], input_text: str, is_qa: bool = False, language: str = "fr") -> Iterator[str]:
    """Version en flux de `ground` : tamponne jusqu'à la fin de chaque proposition (virgule
    ou point de phrase), la laisse partir ou la coupe, sans attendre la fin de la réponse.
    La dernière proposition reçue est toujours retenue tant que rien ne prouve qu'elle est
    complète (elle pourrait continuer, ex. un nombre décimal encore en train d'arriver)."""
    numbers = _numbers_in(_METADATA_NUMBER_RE.sub(" ", input_text))
    input_folded = _fold(input_text)
    buf = ""
    emitted = 0
    last_kept: int | None = None
    said_anything = False

    def flush(final: bool) -> str:
        nonlocal emitted, last_kept, said_anything
        segments = _split_segments(buf)
        limit = len(segments) if final else max(0, len(segments) - 1)
        chunk, last_kept = _emit(segments, emitted, limit, numbers, input_folded, last_kept)
        if chunk:
            said_anything = True
        emitted = limit
        return chunk

    for piece in pieces:
        buf += piece
        chunk = flush(final=False)
        if chunk:
            yield chunk
    chunk = flush(final=True)
    if chunk:
        yield chunk
    if said_anything:
        yield "."
    elif is_qa:
        yield _t(language, "grounding.not_found")
