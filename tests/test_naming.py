"""Garde-fou de nommage (mission N1, voir `docs/naming.md`).

Aucun ancien nom ne doit réapparaître sur une surface publique : README, site, benchmark
public, cartes de modèle et de jeu de données, CITATION, Croissant, chaînes affichées de
`src/steph/`. Toute exception est listée et commentée ci-dessous ; rien n'est exclu en
silence.

Hors périmètre par décision explicite (voir docs/naming.md, section « Exclu du
périmètre ») : `docs/mission-*.md`, `benchmark/results/*.json`, `benchmark/data/v1/`,
`bench/matrix/`, les commentaires de code de `src/steph/`, et les champs internes
`_doc`/`quality_note` de `src/steph/data/catalog.json` (jamais lus par le code, voir
`src/steph/setup.py` qui n'affiche que `label`).
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# ---------------------------------------------------------------------------------------
# Surfaces publiques revues par N1. Ajouter un fichier ici dès qu'il devient public,
# jamais avant (un brouillon non public n'a pas à passer ce garde-fou).
# ---------------------------------------------------------------------------------------
TEXT_SURFACES = [
    ROOT / "README.md",
    ROOT / "README.fr.md",
    ROOT / "CHANGELOG.md",
    ROOT / "benchmark" / "README.md",
    ROOT / "benchmark" / "README.fr.md",
    ROOT / "benchmark" / "data" / "README.md",
    ROOT / "benchmark" / "CITATION.cff",
    ROOT / "benchmark" / "data" / "croissant.json",
    ROOT / "docs" / "model-card-draft.md",
    ROOT / "docs" / "dataset-card-draft.md",
    *sorted((ROOT / "site" / "public").rglob("*.html")),
]
TEXT_SURFACES = [p for p in TEXT_SURFACES if p.exists()]


def _lines(path: Path):
    return list(enumerate(path.read_text(encoding="utf-8").splitlines(), start=1))


# ---------------------------------------------------------------------------------------
# Ancien nom du benchmark (TermSpeak -> Steph Speak Bench, décision D-nommage de
# docs/open-source.md). Exceptions : le canari anti-contamination `termspeak-canary-v1-...`
# et l'entrée `CHANGELOG.md` qui documente le renommage lui-même (convention Keep a
# Changelog : un changelog raconte ce qui a changé, il ne cache pas l'ancien nom).
# `data/v1` est figé (docs/open-source.md, décision O2) : renommer le canari casserait des
# sommes de contrôle déjà publiées dans benchmark/results/*.json, hors périmètre ici.
# ---------------------------------------------------------------------------------------
OLD_BENCHMARK_NAME = "termspeak"


def test_no_old_benchmark_name_outside_canary_and_changelog():
    violations = []
    for path in TEXT_SURFACES:
        for line_no, line in _lines(path):
            if OLD_BENCHMARK_NAME not in line.lower():
                continue
            if "canary" in line.lower() or "canari" in line.lower():
                continue
            if path.name == "CHANGELOG.md" and "was TermSpeak" in line:
                continue
            violations.append(f"{path.relative_to(ROOT)}:{line_no}: {line.strip()!r}")
    assert not violations, "ancien nom TermSpeak trouvé hors canari/changelog :\n" + "\n".join(violations)


# ---------------------------------------------------------------------------------------
# Noms de tâches internes (P15, P17, K3, R1, A12, H3a...) :
# une lettre majuscule, 1 ou 2 chiffres, une lettre minuscule optionnelle. Ce schéma
# recoupe des tokens légitimes (touches de fonction, puces Apple, formats GGUF, artefacts
# d'encodage d'URL) : chaque faux positif observé est listé et expliqué ci-dessous plutôt
# que deviné par le test.
# ---------------------------------------------------------------------------------------
CODENAME_RE = re.compile(r"\b[A-Z][0-9]{1,2}[a-z]?\b")

CODENAME_FALSE_POSITIVES = {
    "F1", "F2", "F5", "F6", "F7", "F8", "F9", "F10",  # touches de fonction (clavier steph)
    "M3",   # puce Apple M3 (Pro), pas la tâche interne M3
    "F16",  # format de quantification GGUF (F16 = float16), pas une tâche
    "B7", "C2",  # artefact d'encodage d'URL des badges shields.io (%C2%B7 = point médian)
}


def test_no_internal_task_codename_on_public_surfaces():
    violations = []
    for path in TEXT_SURFACES:
        for line_no, line in _lines(path):
            for match in CODENAME_RE.finditer(line):
                code = match.group(0)
                if code in CODENAME_FALSE_POSITIVES:
                    continue
                violations.append(f"{path.relative_to(ROOT)}:{line_no}: {code!r} dans {line.strip()!r}")
    assert not violations, (
        "nom de tâche interne visible sur une surface publique (ajouter à "
        "CODENAME_FALSE_POSITIVES avec un commentaire si c'est un faux positif) :\n"
        + "\n".join(violations)
    )


# ---------------------------------------------------------------------------------------
# Anciens noms de modèles affinés ad hoc (avant le schéma de docs/open-source.md, section
# 2.2) : jamais un nom affiché ni un identifiant de fichier publié.
# ---------------------------------------------------------------------------------------
OLD_MODEL_NAME_RE = re.compile(r"granite[-_]soup|p17-dpo|steph[- ]universal", re.IGNORECASE)


def test_no_old_finetuned_model_names():
    violations = []
    for path in TEXT_SURFACES:
        for line_no, line in _lines(path):
            if OLD_MODEL_NAME_RE.search(line):
                violations.append(f"{path.relative_to(ROOT)}:{line_no}: {line.strip()!r}")
    assert not violations, "ancien nom de modèle affiné trouvé :\n" + "\n".join(violations)


# ---------------------------------------------------------------------------------------
# Forme du nom du produit et de la famille de modèles : toujours en minuscules avec
# tiret (`steph-speak`), jamais « steph speak » (espace) ni « Steph-Speak » (casse de
# titre) hors du nom affiché du benchmark, qui garde sa casse de titre par décision
# explicite (D-nommage, docs/open-source.md) : « Steph Speak Bench ».
# ---------------------------------------------------------------------------------------
UNHYPHENATED_RE = re.compile(r"\bsteph speak\b(?!\s+bench)", re.IGNORECASE)


def test_model_family_name_is_hyphenated():
    violations = []
    for path in TEXT_SURFACES:
        for line_no, line in _lines(path):
            if UNHYPHENATED_RE.search(line):
                violations.append(f"{path.relative_to(ROOT)}:{line_no}: {line.strip()!r}")
    assert not violations, "« steph speak » sans tiret trouvé (attendu : steph-speak) :\n" + "\n".join(violations)


# ---------------------------------------------------------------------------------------
# Catalogue des modèles : seul le champ `label` est affiché à l'utilisateur
# (src/steph/setup.py n'imprime jamais `id`, `source` ni `file`). On ne vérifie donc que
# `label` ici ; `_doc` et `quality_note` sont des notes internes non affichées et peuvent
# légitimement citer des tâches (P15, P17, R1...).
# ---------------------------------------------------------------------------------------
def test_catalog_labels_have_no_old_name():
    catalog_path = ROOT / "src" / "steph" / "data" / "catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    violations = []
    for option in catalog.get("options", []):
        label = option.get("label", "")
        if OLD_BENCHMARK_NAME in label.lower() or OLD_MODEL_NAME_RE.search(label) or CODENAME_RE.search(label):
            violations.append(f"{option.get('id')}: label={label!r}")
    assert not violations, "ancien nom dans un label affiché du catalogue :\n" + "\n".join(violations)
