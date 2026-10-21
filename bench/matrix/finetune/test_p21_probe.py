"""Tests de p21_probe.py : construction des entrées de sondage, aucun réseau."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import p21_probe  # noqa: E402

DEV = Path(__file__).resolve().parents[1] / "v3" / "harness" / "dev.json"


def test_build_covers_every_family_with_expected_volume():
    probes = p21_probe.build(DEV)
    groups = {}
    for p in probes:
        groups[p["group"]] = groups.get(p["group"], 0) + p["samples"]
    dev_rows = len(json.load(open(DEV, encoding="utf-8")))
    assert groups["dev"] == 2 * dev_rows
    assert groups["synthetic"] == len(p21_probe.SYNTHETIC) * 2 * 6
    assert groups["qa"] == sum(len(q) for q in p21_probe.QUESTIONS.values()) * 6
    assert groups["prime-raw"] == len(p21_probe.PRIMES) * 16
    assert len({p["id"] for p in probes}) == len(probes)


def test_synthetic_inputs_use_production_format():
    probes = [p for p in p21_probe.build(DEV) if p["group"] in ("synthetic", "qa")]
    for p in probes:
        assert p["messages"][0]["role"] == "system"
        assert p["messages"][-1]["role"] == "user"


def test_analyze_counts_private_terms_and_grounding(tmp_path):
    from argparse import Namespace

    from pii_fingerprint import make_fingerprints

    names = tmp_path / "names.tsv"
    names.write_text("Zorglub\n", encoding="utf-8")
    fp = tmp_path / "fp.json"
    fp.write_text(json.dumps(make_fingerprints(str(names), "00" * 16)), encoding="utf-8")
    probe = {"id": "syn:0", "group": "synthetic", "mode": "chat", "samples": 3, "payload": {},
             "messages": [{"role": "system", "content": "s"}, {"role": "user", "content": "Commande : ls\nSortie : ok"}]}
    probes = tmp_path / "probes.jsonl"
    probes.write_text(json.dumps(probe) + "\n", encoding="utf-8")
    texts = ["zorglub a fini.", "Fini, merci Zorglub.", "Liste vide."]
    out = tmp_path / "out-m.jsonl"
    out.write_text("".join(json.dumps({"id": "syn:0", "group": "synthetic", "sample": k, "model": "m", "text": t}) + "\n"
                           for k, t in enumerate(texts)), encoding="utf-8")
    args = Namespace(names=str(names), fp=str(fp), probes=str(probes), outs=[str(out)])
    stats = p21_probe.analyze(args)["out-m"]["synthetic"]
    assert stats == {"outputs": 3, "with_private": 2, "ids": {"n01": 2}, "absent_from_input": 2,
                     "kept_by_grounding": 1}
