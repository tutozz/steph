# SPDX-License-Identifier: MIT
import random
import re

import inject_pairs as ip

FR_SYS = {"role": "system", "content": "Tu lis la sortie d'une commande."}
EN_SYS = {"role": "system", "content": "You read the output of a terminal command."}


def row(sys, ctx, label):
    return [sys, {"role": "user", "content": ctx}, {"role": "assistant", "content": label}]


CTX_FR = "Commande : pytest\nStatut : échec (code 1)\nSortie :\n3 failed, 12 passed in tests/test_api.py"
CTX_EN = "Command: pytest\nStatus: failure (code 1)\nOutput:\n3 failed, 12 passed in tests/test_api.py"


def test_number_changed_to_value_absent_from_context():
    rng = random.Random(1)
    out = ip.alter_number(rng, "3 tests échoués sur 15.", CTX_FR + " 15")
    assert out and out != "3 tests échoués sur 15."
    new = set(re.findall(r"\d+", out)) - {"3", "15"}
    assert new and all(ip.absent_in(n, CTX_FR + " 15") for n in new)


def test_file_renamed_to_absent_name():
    out = ip.alter_file(random.Random(2), "Échec dans test_api.py.", CTX_FR)
    assert out and "test_api.py" not in out and re.search(r"\w+\.py", out).group(0) not in CTX_FR


def test_status_flip_fr_and_en():
    assert ip.flip_status(None, "Échec, 3 tests.", CTX_FR, "fr") == "Succès, 3 tests."
    assert ip.flip_status(None, "Failed: 3 tests.", CTX_EN, "en") == "Succeeded: 3 tests."


def test_extrinsic_adds_fact_absent_from_context():
    rng = random.Random(3)
    for _ in range(20):
        out = ip.extrinsic(rng, "3 tests échoués.", CTX_FR, "fr")
        if out:
            assert out.startswith("3 tests échoués, ") and out.endswith(".")


def test_absent_answer_becomes_invented_answer():
    out = ip.extrinsic(random.Random(4), "Pas dans l'historique.", CTX_FR, "fr")
    assert out.startswith("C'était ") and "code" in out


def test_build_respects_language_quota_and_one_pair_per_prompt():
    rows = [row(FR_SYS, CTX_FR + f"\n{i}", "Échec, 3 tests sur 15.") for i in range(30)]
    rows += [row(EN_SYS, CTX_EN + f"\n{i}", "Failed, 3 tests of 15.") for i in range(30)]
    pairs = ip.build(rows, 12, 2 / 3, random.Random(5), 0.4)
    langs = [p["lang"] for p in pairs]
    assert langs.count("fr") == 8 and langs.count("en") == 4
    assert all(p["rejected"] != p["chosen"] for p in pairs)
    assert len({p["prompt"][1]["content"] for p in pairs}) == len(pairs)


def test_intrinsic_request_never_falls_back_to_extrinsic():
    msgs = row(FR_SYS, "Commande : ls\nStatut : succès (code 0)\nSortie :\nrien", "Rien à afficher.")
    assert ip.inject(random.Random(6), msgs, want_extrinsic=False) == (None, None)


def test_addresses_are_never_altered():
    ctx = "Commande : ip a\nSortie :\nwlp2s0 192.0.2.10/24 2001:db8::1:2 3 interfaces"
    for seed in range(20):
        out = ip.alter_number(random.Random(seed), "wlp2s0 192.0.2.10, 2001:db8::1:2, 3 interfaces.", ctx)
        assert out and "192.0.2.10" in out and "2001:db8::1:2" in out
