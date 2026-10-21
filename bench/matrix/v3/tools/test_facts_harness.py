"""L5 : harnais variante avec le bloc de faits extraits en code, profils générique et affiné."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import facts_harness  # noqa: E402
import v3lib  # noqa: E402
from steph.strings import t  # noqa: E402


@pytest.fixture(scope="module")
def base():
    # harnais d'avant L5 : ceux d'après portent déjà le bloc
    pre = v3lib.V3 / "harness" / "pre-l5"
    return {"finetuned": json.load(open(pre / "dev.json")), "generic": json.load(open(pre / "dev.generic.json"))}


@pytest.mark.parametrize("profile", ["generic", "finetuned"])
def test_variant_only_adds_the_facts_block_to_summary_rows(base, profile):
    rows = facts_harness.rows(profile, "dev", base[profile])
    assert [r["id"] for r in rows] == [r["id"] for r in base[profile]]
    with_block = 0
    for new, old in zip(rows, base[profile]):
        assert {k: v for k, v in new.items() if k != "messages"} == {k: v for k, v in old.items() if k != "messages"}
        if old["kind"] != "summary":
            assert new["messages"] == old["messages"]
            continue
        assert new["messages"][0] == old["messages"][0]
        user, header = new["messages"][1]["content"], t(new["lang"], "facts.header")
        if header not in user:
            assert user == old["messages"][1]["content"]
            continue
        with_block += 1
        start = user.index(header)
        end = user.index("\nSortie :\n" if new["lang"] == "fr" else "\nOutput:\n", start) + 1
        assert user[:start] + user[end:] == old["messages"][1]["content"]
    assert with_block > 100


def test_rows_refuse_a_base_harness_that_differs_from_the_production_input(base):
    broken = [dict(r) for r in base["generic"]]
    first = next(i for i, r in enumerate(broken) if r["kind"] == "summary")
    broken[first] = {**broken[first], "messages": [broken[first]["messages"][0],
                                                   {"role": "user", "content": "autre entrée"}]}
    with pytest.raises(SystemExit):
        facts_harness.rows("generic", "dev", broken)
