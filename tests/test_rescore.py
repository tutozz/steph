"""Bench audit: facts.v2 corrections and rescoring of existing results."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

MATRIX = Path(__file__).resolve().parents[1] / "bench" / "matrix"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


rescore = load("bench_rescore", MATRIX / "rescore.py")
V1 = rescore.load_facts(MATRIX / "facts.json")
V2 = rescore.load_facts(MATRIX / "facts.v2.json")


def test_v2_keeps_every_v1_fixture():
    fixtures = {k for k in V1 if not k.startswith("_")}
    assert fixtures <= set(V2)


@pytest.mark.parametrize("fixture,kind,out", [
    ("fx05", "summary", "Ping 127.0.0.1 : 3 paquets envoyés, 3 reçus, temps moyen 0.024 ms."),
    ("fx01", "summary", "Racine 685G libres sur 953G, boot 284M libres sur 974M."),
    ("fx21", "summary", "Échec. tar : non existant, stat impossible."),
    ("fx28", "summary", "Échec. main -> main : travail non local."),
    ("fx29", "summary", "GPU NVIDIA GA106, Ethernet RTL8111, coprocesseur cryptographique PSPCPP."),
    ("fx12", "summary", "Six fichiers : bench, pyproject.toml, README.md."),
])
def test_v2_accepts_correct_answers_v1_refused(fixture, kind, out):
    assert rescore.score_case(V1, fixture, kind, out) < 1
    assert rescore.score_case(V2, fixture, kind, out) == 1


@pytest.mark.parametrize("fixture,kind,out", [
    ("qa2", "qa", "Échec. Header.tsx ligne 42 : Titre introuvable."),
    ("fx16", "summary", "Succès. Host key verification réussie."),
    ("fx03", "summary", "Échec. cat ligne 1 : fichier inexistant."),
    ("fx08", "summary", "18 éléments : pipewire.service désactivé, pipewire.socket connexion réussie."),
    ("fx13", "summary", "Debian Linux version 7.0.9, CPU Intel Xeon Scalable."),
    ("fx06", "summary", "Échec. main ligne 21 : expected expression before ; token."),
])
def test_v2_refuses_wrong_answers_v1_accepted(fixture, kind, out):
    assert rescore.score_case(V1, fixture, kind, out) > 0
    assert rescore.score_case(V2, fixture, kind, out) == 0


def test_rescore_file_reports_both_versions(tmp_path):
    result = {"label": "m", "rows": [
        {"fixture": "fx05", "kind": "summary", "out": "Ping : 3 paquets envoyés, 3 reçus."},
        {"fixture": "fx23", "kind": "summary", "out": "alice"},
    ]}
    path = tmp_path / "r.json"
    path.write_text(json.dumps(result))
    row = rescore.rescore_file(path, V1, V2)
    assert row["v1"] == 50.0 and row["v2"] == 100.0 and row["n"] == 2


def test_judge_inventions_after_overrides():
    model = {"invention_sur_36": 4, "cas_inventions": [{"id": "fx03@1500"}, {"id": "fx08@1500"},
                                                       {"id": "fx21@1500"}, {"id": "qa2"}]}
    overrides = {"fx08@1500": {"v2": "faux_positif"}, "fx21@1500": {"v2": "discutable"}}
    assert rescore.judge_counts(model, overrides) == {"v1": 4, "v2": 2, "v2_with_debatable": 3}
