"""Tableau de fin de round (P6, docs/mission-finetune.md) : une ligne par modèle et variante testés.

    python bench/matrix/models_table.py            -> écrit docs/models-table.md

Lit tout `bench/matrix/results/` (bruts vague 1/2) plus `finetune/`, `finetune/vocab/`,
`finetune/efficiency/` et `finetune/t5/` (affinés maison, y compris flan-t5-small/base qui
n'existe qu'à cet endroit). Regroupe les fichiers d'un même modèle/variante (mêmes poids,
graines de banc -b7/-b42/-b123, rondes de mesure i5 -r2/-r3), calcule les scores avec
score.py (v1) et rescore.py (v2), lit les inventions dans les judge-*.json corrigées par
judge_audit.v2.json, et la vitesse dans les fichiers i5-*.json. Rien n'est recopié à la
main : toute valeur du tableau sort d'un calcul sur les fichiers présents.
"""

import json
import re
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from score import HOLDOUT, clean  # noqa: E402
from rescore import score_case  # noqa: E402

RESULTS = HERE / "results"
FT = RESULTS / "finetune"
MODELS_DIR = HERE / "finetune" / "models"
DOC_OUT = HERE.parent.parent / "docs" / "models-table.md"

SCAN_DIRS = [RESULTS, FT, FT / "vocab", FT / "efficiency", FT / "t5"]
JUDGE_FILES = [FT / n for n in ("judge-i5.json", "judge-judged.json", "judge-fixed.json", "judge-soup.json")]
RESOLVE_CTX = FT / "efficiency" / "judge-resolve-rawctx.json"


# ==================================================================== découverte des fichiers
def is_result_file(path: Path) -> bool:
    """Un vrai résultat de banc : JSON objet avec des lignes fixture/sortie exploitables."""
    if path.suffix != ".json" or re.match(r"^judge-", path.name) or path.name.endswith(".progress.json"):
        return False
    try:
        d = json.load(open(path))
    except Exception:
        return False
    rows = d.get("rows") if isinstance(d, dict) else None
    if not isinstance(rows, list) or not rows:
        return False
    first = rows[0]
    return isinstance(first, dict) and "fixture" in first and "out" in first


def discover_result_files(dirs) -> list:
    found = []
    for d in dirs:
        d = Path(d)
        if not d.is_dir():
            continue
        found.extend(sorted(p for p in d.glob("*.json") if is_result_file(p)))
    return found


# ==================================================================== statistiques (graines, rondes)
def average_with_range(values):
    if not values:
        raise ValueError("average_with_range: liste vide")
    return statistics.fmean(values), min(values), max(values)


def fmt_fr(x, decimals=1) -> str:
    if x is None:
        return ""
    return f"{x:.{decimals}f}".replace(".", ",")


def fmt_cell(mean, lo, hi, decimals=1) -> str:
    if mean is None:
        return ""
    if round(lo, decimals) == round(hi, decimals):
        return fmt_fr(mean, decimals)
    return f"{fmt_fr(mean, decimals)} ({fmt_fr(lo, decimals)}–{fmt_fr(hi, decimals)})"


ROUND_SUFFIX = re.compile(r"-r\d$")  # rondes i5 : r1/r2/r3 seulement (r16/r32 = rang LoRA, pas une ronde)
SEED_SUFFIX = re.compile(r"-([bs])(\d+)$")


def round_stem(name: str) -> str:
    """Regroupe les rondes de mesure i5 (-r2, -r3) avec le fichier sans suffixe (ronde 1)."""
    return ROUND_SUFFIX.sub("", Path(name).stem)


def seed_stem(name: str):
    """Regroupe les graines de banc (-b7/-b42/-b123, -s7/-s42/-s123). None si pas une graine."""
    stem = Path(name).stem
    m = SEED_SUFFIX.search(stem)
    return stem[: m.start()] if m else None


def variant_key(name: str) -> str:
    """Identité d'un fichier une fois machine/ronde/graine retirées : sert au regroupement
    ET à la classification (une fois normalisé, un nom ne porte plus que le modèle+variante)."""
    stem = Path(name).stem
    stem = re.sub(r"^i5-", "", stem)
    stem = re.sub(r"^(bench|greedy)-", "", stem)
    stem = ROUND_SUFFIX.sub("", stem)
    stem = SEED_SUFFIX.sub("", stem)
    stem = re.sub(r"^vocab-", "", stem)
    return stem.lower()


def dedup_identical_rows(paths: list) -> list:
    """Écarte les doublons (même contenu de `rows`) : évite de compter deux fois une même mesure."""
    seen = {}
    for p in paths:
        rows = json.load(open(p)).get("rows")
        key = json.dumps(rows, sort_keys=True, ensure_ascii=False)
        seen.setdefault(key, p)
    return list(seen.values())


def speed_stats(i5_files: list) -> dict:
    """Vitesse i5 : fichier unique -> ses valeurs ; plusieurs rondes -> médiane + fourchette."""
    if not i5_files:
        return {"ttft_median": None, "ttft_p90": None, "ram_mb": None}
    groups = {}
    for p in i5_files:
        groups.setdefault(round_stem(p.name), []).append(p)
    rounds = max(groups.values(), key=len)  # le groupe de rondes le plus fourni sert de mesure
    payloads = [json.load(open(p)) for p in rounds]
    medians = [d.get("ttft_median") for d in payloads if d.get("ttft_median") is not None]
    p90s = [d.get("ttft_p90") for d in payloads if d.get("ttft_p90") is not None]
    rams = [d.get("ram_peak_mb") for d in payloads if d.get("ram_peak_mb")]

    def stat(values):
        if not values:
            return None
        if len(values) == 1:
            return values[0], values[0], values[0]
        med = statistics.median(values)
        return med, min(values), max(values)

    return {
        "ttft_median": stat(medians),
        "ttft_p90": stat(p90s),
        "ram_mb": round(statistics.median(rams)) if rams else None,
    }


# ==================================================================== score (v1/v2, splits)
def load_facts(path: Path) -> dict:
    return json.load(open(path))


def filter_split(rows: list, split: str) -> list:
    if split == "tune":
        return [r for r in rows if r["fixture"] not in HOLDOUT]
    if split == "holdout":
        return [r for r in rows if r["fixture"] in HOLDOUT]
    if split == "holdout_summary":
        return [r for r in rows if r["fixture"] in HOLDOUT and r["kind"] == "summary"]
    return rows


def quality(facts: dict, rows: list, split: str = "all"):
    rows = filter_split(rows, split)
    scores = [score_case(facts, r["fixture"], r["kind"], clean(r["out"])) for r in rows if r.get("out") is not None]
    scores = [s for s in scores if s == s]  # écarte les NaN (fixture hors facts)
    return round(100 * sum(scores) / len(scores), 1) if scores else None


def score_file(path: Path, v1: dict, v2: dict) -> dict:
    rows = [r for r in json.load(open(path)).get("rows", []) if r.get("out") is not None]
    return {
        "v1": quality(v1, rows, "all"),
        "v2": quality(v2, rows, "all"),
        "v2_holdout": quality(v2, rows, "holdout"),
        "v2_holdout_summary": quality(v2, rows, "holdout_summary"),
    }


# ==================================================================== protocole (honnêteté vague 1/2 vs affiné)
_LONG_BASENAMES = {"cases.json", "cases_screen.json", "cases_g2_screen.json", "cases_p1.json", "cases_p2.json"}
_FT_MARKERS = ("cases_ft", "cases-short", "pilot_cases", "judged_cases", "fixed_cases", "full_cases",
               "steph-ft/bench/cases.json")


def classify_protocol(cases_field, filename: str) -> str:
    """steph long (prompt système complet, vague 1/2) / court affiné (prompt d'entraînement) / TermSpeak."""
    if "termspeak" in filename.lower() or (cases_field and "termspeak" in cases_field.lower()):
        return "TermSpeak"
    name = (cases_field or "").lower()
    if any(m in name for m in _FT_MARKERS):
        return "court affiné"
    if Path(name).name in _LONG_BASENAMES:
        return "steph long"
    # repli : dossier du fichier de résultat quand `cases` est absent ou inconnu
    return "court affiné" if "/finetune/" in str(filename).replace("\\", "/") else "steph long"


# ==================================================================== taille GGUF locale
_TOKEN_RE = re.compile(r"[a-z0-9]+")
_QUANT_RE = re.compile(r"^(q4|q8|f16)$")


def _tokens(name: str) -> set:
    return set(_TOKEN_RE.findall(name.lower()))


def find_local_gguf(models_dir: Path, candidate_names: list):
    """Cherche parmi les GGUF locaux celui qui correspond le mieux à un des noms distants,
    en exigeant la même quantification et les mêmes jetons numérotés (graine, ronde)."""
    local = list(Path(models_dir).glob("*.gguf")) if Path(models_dir).is_dir() else []
    if not local:
        return None
    best, best_score = None, 0.0
    for cand in candidate_names:
        ctoks = _tokens(cand)
        cquant = {t for t in ctoks if _QUANT_RE.match(t)}
        cnumbered = {t for t in ctoks if re.match(r"^[a-z]\d+$", t)}
        for lp in local:
            ltoks = _tokens(lp.stem)
            if cquant and not cquant.issubset(ltoks):
                continue
            if cnumbered and not cnumbered.issubset(ltoks):
                continue
            union = ctoks | ltoks
            score = len(ctoks & ltoks) / len(union) if union else 0.0
            if score > best_score:
                best, best_score = lp, score
    return best if best_score >= 0.4 else None


def gguf_size_mb(path: Path):
    # Mo décimal (1e6), pas Mio : convention déjà en usage dans docs/efficiency.md et `ls`.
    return round(path.stat().st_size / 1_000_000) if path else None


# ==================================================================== juge (inventions) et resolve()
def load_judge_index(judge_paths) -> dict:
    """{nom_du_fichier_de_resultat: (fichier_juge, cle_par_modele)}."""
    index = {}
    for jp in judge_paths:
        if not jp.exists():
            continue
        for model_key in json.load(open(jp)).get("par_modele", {}):
            index[model_key] = (jp, model_key)
    return index


def confirmed_invention_ids(entry: dict, overrides: dict) -> list:
    ids = [c["id"] for c in entry.get("cas_inventions", [])]
    return [i for i in ids if overrides.get(i, {}).get("v2", "confirmee") == "confirmee"]


def load_resolved_fixture_ids(path: Path) -> set:
    """Cas que `resolve()` dit en code (P4) : plus soumis au modèle, donc jamais à un juge."""
    if not path.exists():
        return set()
    return {re.sub(r"@\d+$", "", e["id"]) for e in json.load(open(path))}


# ==================================================================== regroupement des fichiers en lignes
def build_clusters(files: list) -> list:
    """Union-find : deux fichiers sont la même ligne modèle+variante si même GGUF (config.model)
    ou même identité de fichier une fois graine/ronde retirée (variant_key)."""
    parent = {p: p for p in files}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    by_variant, by_gguf = {}, {}
    for p in files:
        by_variant.setdefault(variant_key(p.name), []).append(p)
        try:
            model = json.load(open(p)).get("config", {}).get("model")
        except Exception:
            model = None
        if model:
            by_gguf.setdefault(Path(model).name.lower(), []).append(p)

    for group in list(by_variant.values()) + list(by_gguf.values()):
        for p in group[1:]:
            union(group[0], p)

    clusters = {}
    for p in files:
        clusters.setdefault(find(p), []).append(p)
    return list(clusters.values())


# ==================================================================== classification (nom, type, données, variante)
# Règles ordonnées, testées avec re.match (ancré au début) sur chaque nom normalisé par
# variant_key() : machine/graine/ronde déjà retirées, donc "full-q8" ne matche plus
# "qwen3.5-0.8b-full-q8" (qui, lui, commence par "qwen3.5-0.8b-full"). La première règle
# dont le motif matche un des candidats du groupe l'emporte.
_RULES = [
    (r"c131072", "Gemma 3 270M", "affiné", "filtrées au juge", "vocabulaire corpus c131072"),
    (r"c65536", "Gemma 3 270M", "affiné", "filtrées au juge", "vocabulaire corpus c65536"),
    (r"v20000", "Gemma 3 270M", "affiné", "filtrées au juge", "vocabulaire réduit v20000"),
    (r"v32768", "Gemma 3 270M", "affiné", "filtrées au juge", "vocabulaire réduit v32768"),
    (r"full-q[48]", "Gemma 3 270M", "affiné", "filtrées au juge", "vocabulaire plein (référence P2)"),
    (r"b32768", "Granite 4.0 H 350M", "affiné", "filtrées au juge", "vocabulaire réduit b32768 (P2b)"),
    (r"c32768", "Granite 4.0 H 350M", "affiné", "filtrées au juge", "vocabulaire corpus c32768 (P2b)"),
    (r"flan-t5-small", "flan-t5-small", "affiné", "filtrées au juge", "encodeur-décodeur (P3)"),
    (r"flan-t5-base", "flan-t5-base", "affiné", "filtrées au juge", "encodeur-décodeur (P3)"),
    (r"judged-gemma-270m-s42|judged-gemma-s42", "Gemma 3 270M", "affiné", "filtrées au juge", "graine s42"),
    (r"soup-granite-uniform", "Granite 4.0 H 350M", "affiné", "filtrées au juge", "soupe uniforme (4 graines)"),
    (r"soup-granite-greedy", "Granite 4.0 H 350M", "affiné", "filtrées au juge", "soupe gloutonne"),
    (r"soup-granite-seed42", "Granite 4.0 H 350M", "affiné", "filtrées au juge", "meilleure graine seule (s42)"),
    (r"judged-granite-350m-s42|judged-granite-s42", "Granite 4.0 H 350M", "affiné", "filtrées au juge",
     "graine s42"),
    (r"judged-granite-350m-s7|judged-granite-s7", "Granite 4.0 H 350M", "affiné", "filtrées au juge", "graine s7"),
    (r"opt-best-granite-g4|g4-q8_0", "Granite 4.0 H 350M", "affiné", "corrigées", "boucle opt G4 (données brutes)"),
    (r"opt-best-granite|g19-q8_0|a1000-granite4\.0-h-350m-ft", "Granite 4.0 H 350M", "affiné", "corrigées",
     "boucle opt G1-G19 (référence, meilleure itération)"),
    (r"granite4\.0-h-350m-base|a1000-granite4\.0-h-350m-base", "Granite 4.0 H 350M", "brut", "", "avant réglage"),
    (r"gemma3-270m-ft500", "Gemma 3 270M", "affiné", "corrigées", "entraînement 500 exemples"),
    (r"gemma3-270m-ftfull|gemma3-270m-ft-q4|a1000-gemma3-270m-ft", "Gemma 3 270M", "affiné", "corrigées",
     "entraînement complet (avant filtrage juge)"),
    (r"gemma3-270m-base|a1000-gemma3-270m-base", "Gemma 3 270M", "brut", "", "avant réglage"),
    (r"qwen3\.5-0\.8b-pilot", "Qwen3.5 0.8B", "affiné", "brutes", "LoRA pilote (A4p)"),
    (r"qwen3\.5-0\.8b-fixed-s7", "Qwen3.5 0.8B", "affiné", "corrigées", "corrigé, graine entraînement s7"),
    (r"qwen3\.5-0\.8b-fixed", "Qwen3.5 0.8B", "affiné", "corrigées", "corrigé (bug fx29), graine s42"),
    (r"qwen3\.5-0\.8b-full", "Qwen3.5 0.8B", "affiné", "corrigées", "entraînement complet"),
    (r"luth-0\.6b-ft-r16", "Luth 0.6B", "affiné", "brutes", "LoRA r16"),
    (r"luth-0\.6b-ft-r32", "Luth 0.6B", "affiné", "brutes", "LoRA r32"),
    (r"luth-0\.6b(?!.*ft)", "Luth 0.6B", "brut", "", "avant réglage"),
    # -- bruts (vague 1/2), un GGUF téléchargé = une ligne --
    (r"gemma-4-e2b", "Gemma 4 E2B", "brut", "", ""),
    (r"gemma-4-e4b", "Gemma 4 E4B", "brut", "", ""),
    (r"qwen3\.5-9b", "Qwen3.5 9B", "brut", "", ""),
    (r"qwen3\.5-4b", "Qwen3.5 4B", "brut", "", ""),
    (r"qwen3\.5-2b", "Qwen3.5 2B", "brut", "", ""),
    (r"qwen3\.5-0\.8b-q4_0", "Qwen3.5 0.8B", "brut", "", "Q4_0"),
    (r"qwen3\.5-0\.8b", "Qwen3.5 0.8B", "brut", "", ""),
    (r"qwen3-4b-instruct", "Qwen3 4B Instruct 2507", "brut", "", ""),
    (r"qwen3-0\.6b", "Qwen3 0.6B", "brut", "", ""),
    (r"granite-4\.2-3b", "Granite 4.2 3B", "brut", "", ""),
    (r"granite-4\.2-8b", "Granite 4.2 8B", "brut", "", ""),
    (r"granite-4\.0-h-1b", "Granite 4.0 H 1B", "brut", "", ""),
    (r"granite-?4\.0-h-350m|granite4h-350m", "Granite 4.0 H 350M", "brut", "", ""),
    (r"gemma3-270m-q8|google_gemma-3-270m-it", "Gemma 3 270M", "brut", "", ""),
    (r"lfm2\.5-1\.2b", "LFM2.5 1.2B", "brut", "", ""),
    (r"lfm2\.5-8b-a1b", "LFM2.5 8B-A1B", "brut", "", ""),
    (r"lfm2\.5-350m|lfm25-350m", "LFM2.5 350M", "brut", "", ""),
    (r"luth-lfm2-350m", "Luth LFM2 350M", "brut", "", ""),
    (r"luth-lfm2-700m", "Luth LFM2 700M", "brut", "", ""),
    (r"lfm2-350m", "LFM2 350M", "brut", "", ""),
    (r"lfm2-700m", "LFM2 700M", "brut", "", ""),
    (r"falcon-?h1-0\.5b", "Falcon H1 0.5B", "brut", "", ""),
    (r"ministral-?3-3b", "Ministral 3 3B", "brut", "", ""),
    (r"ministral-?3-8b", "Ministral 3 8B", "brut", "", ""),
    (r"smollm3", "SmolLM3 3B", "brut", "", ""),
    (r"smollm2-360m", "SmolLM2 360M", "brut", "", ""),
]


# Préfixes de machine que variant_key() (partagé avec le regroupement) ne retire pas : utiles
# seulement ici, pour retrouver le nom du modèle quand le chemin GGUF distant est tronqué
# (ex. "rtx3080-luth-0.6b-ft-r16.json" -> config.model = ".../ft-r16-Q4_K_M.gguf").
_HOST_PREFIX = re.compile(
    r"^(i5-7200u-cpu-|i5-g2-|homelab-cpu\d+-|homelab-rtx3060-|homelab-|mac-m3pro-metal-|mac-m3pro-cpu-|mac-pq-"
    r"|rtx3060-cpu\d+-|rtx3060-|xeon-|a1000-|rtx3080-cuda-|rtx3080-)")


def classify(cluster: list) -> dict:
    # bench/matrix/results/finetune/t5/ : "small-*"/"base-*" sans le préfixe "flan-t5-",
    # distingués par le dossier plutôt que par un motif trop générique pour être sûr.
    if any(p.parent.name == "t5" for p in cluster):
        is_small = any(variant_key(p.name).startswith("small") for p in cluster)
        return {"name": "flan-t5-small" if is_small else "flan-t5-base", "type": "affiné",
                "data": "filtrées au juge", "variant": "encodeur-décodeur (P3)"}

    candidates = set()
    for p in cluster:
        vk = variant_key(p.name)
        candidates.add(vk)
        candidates.add(_HOST_PREFIX.sub("", vk))
        try:
            m = json.load(open(p)).get("config", {}).get("model")
        except Exception:
            m = None
        if m:
            candidates.add(variant_key(Path(m).name))

    for pattern, name, type_, data, variant in _RULES:
        if any(re.match(pattern, c) for c in candidates):
            return {"name": name, "type": type_, "data": data, "variant": variant}
    # repli : aucune règle connue, nom dérivé du fichier le plus court (le plus "canonique")
    fallback = min(cluster, key=lambda p: len(p.stem)).stem
    return {"name": fallback, "type": "?", "data": "", "variant": ""}


# ==================================================================== ligne du tableau
FLOOR_INVENTIONS = 1
FLOOR_P90_S = 3.0


def canonical_quality_file(cluster: list):
    """Groupe de graines (-b/-s) si présent (moyenne+fourchette) ; sinon le fichier le plus complet.
    Le fichier i5 du même groupe (mêmes poids, cluster garanti par build_clusters) compte comme
    une graine de plus quand un groupe de graines existe déjà : c'est une mesure indépendante de
    la même sortie, pas une machine à part pour la qualité (seule la vitesse reste propre à l'i5)."""
    groups = {}
    for p in cluster:
        s = seed_stem(p.name)
        if s:
            groups.setdefault(s, []).append(p)
    seed_group = max(groups.values(), key=len) if groups else []
    if len(seed_group) >= 2:
        extra = [p for p in cluster if p.name.startswith("i5-") and p not in seed_group]
        seed_group = dedup_identical_rows(seed_group + extra)
        return seed_group
    best = max(cluster, key=lambda p: (len(json.load(open(p)).get("rows", [])), -len(p.stem)))
    return [best]


def build_row(cluster: list, v1: dict, v2: dict, judge_index: dict, audit: dict, resolved_ids: set):
    meta = classify(cluster)
    quality_files = canonical_quality_file(cluster)
    scored = [score_file(p, v1, v2) for p in quality_files]
    means = {}
    for field in ("v1", "v2", "v2_holdout", "v2_holdout_summary"):
        vals = [s[field] for s in scored if s[field] is not None]
        means[field] = average_with_range(vals) if vals else (None, None, None)

    i5_files = [p for p in cluster if p.name.startswith("i5-")]
    speed = speed_stats(i5_files)

    protocols = set()
    for p in quality_files + i5_files:
        try:
            cases = json.load(open(p)).get("config", {}).get("cases")
        except Exception:
            cases = None
        protocols.add(classify_protocol(cases, str(p)))
    protocol = sorted(protocols, key=lambda x: ["steph long", "court affiné", "TermSpeak"].index(x))[0] \
        if protocols else "steph long"

    # bench/matrix/finetune/models/ ne contient que nos propres affinages : un modèle brut n'y a
    # jamais de GGUF, inutile (et risqué, faux positifs) d'y chercher une taille pour lui.
    size_mb = None
    if meta["type"] == "affiné":
        gguf_candidates = [p.stem for p in cluster]
        for p in cluster:
            try:
                m = json.load(open(p)).get("config", {}).get("model")
            except Exception:
                m = None
            if m:
                gguf_candidates.append(Path(m).stem)
        local_gguf = find_local_gguf(MODELS_DIR, gguf_candidates)
        size_mb = gguf_size_mb(local_gguf)

    inventions, of_total, plus_resolve = None, None, None
    for p in cluster:
        key = p.name
        if key in judge_index:
            jpath, mkey = judge_index[key]
            entry = json.load(open(jpath))["par_modele"][mkey]
            overrides = audit.get(jpath.name, {}).get(mkey, {})
            kept = confirmed_invention_ids(entry, overrides)
            inventions, of_total = len(kept), entry.get("n_total", 36)
            if resolved_ids:
                remaining = [i for i in kept if re.sub(r"@\d+$", "", i) not in resolved_ids]
                plus_resolve = len(remaining)
            break

    return {
        **meta,
        "protocol": protocol,
        "size_mb": size_mb,
        "ttft_median": speed["ttft_median"],
        "ttft_p90": speed["ttft_p90"],
        "ram_mb": speed["ram_mb"],
        "v2": means["v2"],
        "v2_holdout": means["v2_holdout"],
        "v2_holdout_summary": means["v2_holdout_summary"],
        "v1": means["v1"],
        "inventions": inventions,
        "of_total": of_total,
        "plus_resolve": plus_resolve,
        "files": sorted(p.name for p in cluster),
    }


def passes_floor(row: dict) -> bool:
    if row["inventions"] is None or row["inventions"] > FLOOR_INVENTIONS:
        return False
    p90 = row["ttft_p90"]
    return p90 is not None and p90[0] < FLOOR_P90_S


# ==================================================================== rendu markdown
HEADER = ("| Modèle | Protocole | Type | Données | Variante | Taille GGUF (Mo) | Premier mot médian i5 (s) "
          "| Premier mot p90 i5 (s) | RAM i5 (Mo) | Total v2 | Contrôle v2 | Résumé seul v2 | Total v1 "
          "| Inventions /36 (juge) | + resolve() : inventions |")
SEP = "|" + "---|" * 15

LEGEND = """# Tableau de fin de round : tous les modèles testés

Généré par `bench/matrix/models_table.py`, jamais retapé à la main. Relancer après tout
nouveau résultat dans `bench/matrix/results/`.

## Légende

- **Protocole** : `steph long` (prompt système complet, bancs bruts des vagues 1 et 2, 69 cas) ;
  `court affiné` (prompt d'entraînement court, 36 cas, utilisé pour comparer les modèles affinés
  entre eux et contre leur base) ; `TermSpeak` (benchmark ouvert `benchmark/`). Les scores ne se
  comparent qu'à l'intérieur d'un même protocole.
- **Type** : `brut` (poids tels que publiés) ou `affiné` (LoRA maison sur le corpus de steph).
- **Données** : `brutes` (étiquettes non relues), `corrigées` (après P1, `facts.v2.json` et le
  nettoyage des étiquettes), `filtrées au juge` (après A11, rejet des étiquettes que le juge IA
  trouve inventées).
- **Total v2 / Contrôle v2 / Résumé seul v2** : score sur `facts.v2.json` (`rescore.py`) - total,
  jeu de contrôle (`score.HOLDOUT`, jamais utilisé pour choisir un réglage), et résumé seul
  (contrôle sans les questions). **Total v1** : même calcul avec `facts.json` (`score.py`), pour
  mesurer l'écart avant/après l'audit P1.
- **Inventions /36 (juge)** : cas confirmés par le juge IA (Qwen3.5 9B, 2 passes), après révision
  humaine dans `judge_audit.v2.json`. **+ resolve()** : inventions restantes une fois les 28 cas
  que `resolve()` dit en code (P4) retirés du calcul - seuls les cas encore envoyés au modèle
  peuvent inventer.
- Une graine de banc (`-b7/-b42/-b123` ou `-s7/-s42/-s123`) donne une moyenne et une fourchette
  `moyenne (min–max)`. Une ronde de mesure i5 (`-r2`, `-r3`) donne une médiane et une fourchette.
  Cellule vide = non mesuré, jamais estimé.

**Plancher retenu (A9) : au plus 1 invention sur 36, moins de 3 s au 90e centile sur l'i5-7200U.**
Les lignes en gras tiennent les deux à la fois.

"""


def render_markdown(rows: list) -> str:
    order = ["steph long", "court affiné", "TermSpeak"]
    rows = sorted(rows, key=lambda r: (order.index(r["protocol"]) if r["protocol"] in order else len(order),
                                        -(r["v2"][0] if r["v2"][0] is not None else -1)))
    lines = [LEGEND, HEADER, SEP]
    for r in rows:
        cells = [
            r["name"], r["protocol"], r["type"], r["data"], r["variant"],
            str(r["size_mb"]) if r["size_mb"] is not None else "",
            fmt_cell(*r["ttft_median"]) if r["ttft_median"] else "",
            fmt_cell(*r["ttft_p90"]) if r["ttft_p90"] else "",
            str(r["ram_mb"]) if r["ram_mb"] is not None else "",
            fmt_cell(*r["v2"]), fmt_cell(*r["v2_holdout"]), fmt_cell(*r["v2_holdout_summary"]), fmt_cell(*r["v1"]),
            f"{r['inventions']}" if r["inventions"] is not None else "",
            f"{r['plus_resolve']}" if r["plus_resolve"] is not None else "",
        ]
        line = "| " + " | ".join(cells) + " |"
        if passes_floor(r):
            line = "| " + " | ".join(f"**{c}**" if c else c for c in cells) + " |"
        lines.append(line)
    lines.append("")
    lines.append(f"Total : {len(rows)} lignes. Généré par `bench/matrix/models_table.py`.")
    return "\n".join(lines) + "\n"


# ==================================================================== pipeline
def main() -> int:
    v1, v2 = load_facts(HERE / "facts.json"), load_facts(HERE / "facts.v2.json")
    audit_path = HERE / "judge_audit.v2.json"
    audit = load_facts(audit_path) if audit_path.exists() else {}
    judge_index = load_judge_index(JUDGE_FILES)
    resolved_ids = load_resolved_fixture_ids(RESOLVE_CTX)

    files = discover_result_files(SCAN_DIRS)
    clusters = build_clusters(files)
    rows = [build_row(c, v1, v2, judge_index, audit, resolved_ids) for c in clusters]

    DOC_OUT.parent.mkdir(parents=True, exist_ok=True)
    DOC_OUT.write_text(render_markdown(rows), encoding="utf-8")
    print(f"{len(rows)} lignes -> {DOC_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
