"""TermSpeak benchmark: dataset integrity, deterministic scoring, anonymization."""

import importlib.util
import json
import os
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "benchmark"
DATA = BENCH / "data" / "v1"
LANGS = ("en", "fr", "de", "es", "pt", "ru")
NEW_LANGS = ("de", "es", "pt", "ru")
CATEGORIES = {
    "build-failure", "runtime-error", "tests", "git", "packages", "network", "disks", "memory",
    "hardware", "containers", "long-lists", "long-truncated", "history-qa",
}


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


run = load("termspeak_run", BENCH / "run.py")
validate = load("termspeak_validate", BENCH / "tools" / "validate.py")
CONFIG = run.load_config(DATA)
SCHEMA = json.loads((DATA / "schema.json").read_text(encoding="utf-8"))


def cases(lang):
    return run.load_cases(DATA, lang, "all")


ALL = [(lang, c) for lang in LANGS for c in cases(lang)]
IDS = [f"{lang}:{c['id']}" for lang, c in ALL]


def test_all_languages_have_the_same_ids_and_metadata():
    by_lang = {lang: {c["id"]: c for c in cases(lang)} for lang in LANGS}
    en = by_lang["en"]
    for lang, other in by_lang.items():
        assert en.keys() == other.keys(), lang
        for cid in en:
            for key in ("split", "category", "origin", "task", "cmd", "exit"):
                assert en[cid].get(key) == other[cid].get(key), (lang, cid, key)


def test_at_least_100_cases_per_language():
    for lang in LANGS:
        assert len(cases(lang)) >= 100


def test_ids_are_unique():
    for lang in LANGS:
        ids = [c["id"] for c in cases(lang)]
        assert len(ids) == len(set(ids))


def test_categories_are_balanced_and_complete():
    counts = {}
    for c in cases("en"):
        counts[c["category"]] = counts.get(c["category"], 0) + 1
    assert set(counts) == CATEGORIES
    assert min(counts.values()) >= 7
    assert max(counts.values()) <= 2 * min(counts.values())


def test_splits_and_origins():
    en = cases("en")
    assert {c["split"] for c in en} == {"dev", "test"}
    assert {c["origin"] for c in en} == {"real-anonymized", "synthetic"}
    assert all(c["origin"] == "synthetic" for c in en if c["split"] == "test")
    for cat in CATEGORIES:
        assert any(c["split"] == "test" and c["category"] == cat for c in en), cat


@pytest.mark.parametrize("lang,case", ALL, ids=IDS)
def test_schema_validates_case(lang, case):
    assert validate.validate(case, SCHEMA) == []
    assert case["lang"] == lang


def test_schema_rejects_a_broken_case():
    case = dict(cases("en")[0])
    case["origin"] = "scraped"
    del case["expected"]
    errors = validate.validate(case, SCHEMA)
    assert any("origin" in e for e in errors)
    assert any("expected" in e for e in errors)


@pytest.mark.parametrize("lang,case", ALL, ids=IDS)
def test_output_has_5_to_400_lines(lang, case):
    assert 5 <= run.source_lines(case) <= 400


@pytest.mark.parametrize("lang,case", ALL, ids=IDS)
def test_reference_scores_100(lang, case):
    result = run.score_case(case, case["reference"], CONFIG["scoring"])
    assert result["score"] == 1.0, result


@pytest.mark.parametrize("lang,case", ALL, ids=IDS)
def test_forbidden_content_scores_zero(lang, case):
    for leak in ("<think>", "**Summary**", "3c:22:fb:12:34:56"):
        assert run.score_case(case, case["reference"] + " " + leak, CONFIG["scoring"])["score"] == 0.0


def test_case_specific_forbidden_scores_zero():
    network = [c for c in cases("en") if c["category"] == "network" and any("127" in p for p in c["forbidden"])]
    assert network
    for c in network:
        assert run.score_case(c, c["reference"] + " lo 127.0.0.1", CONFIG["scoring"])["score"] == 0.0


def test_length_penalty():
    case = cases("en")[0]
    padded = case["reference"] + " word" * (case["max_words"] + 5)
    assert run.score_case(case, padded, CONFIG["scoring"])["score"] == pytest.approx(CONFIG["scoring"]["length_penalty"])


def test_missing_fact_lowers_score():
    case = next(c for c in cases("en") if len(c["expected"]) >= 2)
    assert run.score_case(case, "", CONFIG["scoring"])["score"] == 0.0


def test_normalize_is_accent_insensitive():
    assert run.normalize("Échec : clé  ÉTRANGÈRE’s") == "echec : cle etrangere's"


@pytest.mark.parametrize("lang,case", ALL, ids=IDS)
def test_patterns_are_written_for_normalized_text(lang, case):
    for pattern in case["expected"] + case["forbidden"]:
        re.compile(pattern)
        bare = re.sub(r"\\.", "", pattern)
        assert bare == run.normalize(bare), pattern
        assert not any(ch.isupper() for ch in bare), pattern


@pytest.mark.parametrize("lang,case", ALL, ids=IDS)
def test_reference_numbers_are_in_the_model_input(lang, case):
    prompt = "\n".join(m["content"] for m in run.build_messages(case, CONFIG["prompts"]))
    for number in re.findall(r"\d+(?:[.,:]\d+)*", case["reference"]):
        assert number in prompt or number.replace(",", ".") in prompt, (case["id"], number)


def test_long_outputs_are_truncated_deterministically():
    long = [c for c in cases("en") if c["category"] == "long-truncated"]
    assert long
    for c in long:
        msgs = run.build_messages(c, CONFIG["prompts"])
        user = msgs[-1]["content"]
        assert "lines omitted" in user
        assert c["output"].rstrip().splitlines()[-1] in user
        assert msgs == run.build_messages(c, CONFIG["prompts"])


@pytest.mark.parametrize("lang", LANGS)
def test_messages_use_the_localized_command_label(lang):
    c = next(c for c in cases(lang) if c["task"] == "summary")
    user = run.build_messages(c, CONFIG["prompts"])[-1]["content"]
    label = CONFIG["prompts"][lang]["summary_user"].split("{cmd}")[0]
    assert user.startswith(label)


@pytest.mark.parametrize("lang", NEW_LANGS)
def test_most_cases_have_a_translated_reference(lang):
    """The response language is the point of L2a: expected/reference must be translated
    for (almost) every case, even when the raw tool output itself stays English (untouched
    by locale, see docs/research-terminal-languages.md). A handful of purely numeric
    references may legitimately be identical across languages."""
    en = {c["id"]: c["reference"] for c in cases("en")}
    translated = [c for c in cases(lang) if c["reference"] != en[c["id"]]]
    assert len(translated) >= 95, f"{lang}: only {len(translated)}/105 references differ from English"


@pytest.mark.parametrize("lang", NEW_LANGS)
def test_patterns_are_pre_normalized_for_the_language_script(lang):
    """German u/o/a-umlaut, Spanish/Portuguese tilde and cedilla, and Russian
    j-with-breve/e-with-diaeresis all lose their diacritic under NFKD (like French accents
    already do): a regex pattern must already be written in that stripped form, or it can
    never match a normalized answer. This is enforced generically by
    test_patterns_are_written_for_normalized_text; this test only pins the concrete
    behaviour so a change to normalize() cannot silently break Cyrillic scoring."""
    assert run.normalize("обновлён") == "обновлен"
    assert run.normalize("йод") == "иод"


def test_dataset_matches_its_generator():
    build = load("termspeak_build", BENCH / "tools" / "build_dataset.py")
    for lang in LANGS:
        for split, expected in build.render(lang).items():
            assert (DATA / lang / f"{split}.jsonl").read_text(encoding="utf-8") == expected, (lang, split)


def all_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from all_strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from all_strings(v)


def pii_scanner():
    audit = load("termspeak_audit_pii", ROOT / "bench" / "matrix" / "finetune" / "audit_pii.py")
    names_path = os.environ.get("STEPH_PII_NAMES", audit.DEFAULT_NAMES)
    names = audit.load_names(names_path) if os.path.exists(names_path) else []
    return audit, names


@pytest.mark.skipif(not (ROOT / "bench/matrix/finetune/audit_pii.py").exists(), reason="scanner absent")
def test_pii_scanner_finds_nothing():
    audit, names = pii_scanner()
    findings = {}
    for lang, case in ALL:
        found = audit.scan_text("\n".join(all_strings(case)), names)
        if found:
            findings[f"{lang}:{case['id']}"] = sorted(set(found))
    for path in list((BENCH / "tools").rglob("*.py")) + [DATA / "prompts.json", DATA / "scoring.json"]:
        found = audit.scan_text(path.read_text(encoding="utf-8"), names)
        if found:
            findings[str(path.relative_to(ROOT))] = sorted(set(found))
    assert findings == {}


def test_results_are_reproducible_from_their_rows():
    files = sorted((BENCH / "results").glob("*.json"))
    for path in files:
        result = json.loads(path.read_text(encoding="utf-8"))
        data = {c["id"]: c for c in run.load_cases(DATA, result["lang"], "all")}
        rescored = run.rescore(result, data, CONFIG["scoring"])
        assert rescored["summary"]["score"] == result["summary"]["score"], path.name


def test_croissant_checksums_match_the_data():
    meta = json.loads((BENCH / "data" / "croissant.json").read_text(encoding="utf-8"))
    files = {d["@id"]: d["sha256"] for d in meta["distribution"] if "sha256" in d}
    actual = {f"v1/{p.parent.name}/{p.name}": run.sha256(p) for p in DATA.glob("*/*.jsonl")}
    assert files == actual


CORPUS = sorted((ROOT / "bench/matrix/finetune").glob("corpus/*.jsonl"))


@pytest.mark.skipif(not CORPUS, reason="training corpus not present on this machine")
def test_test_split_is_not_in_the_training_corpus():
    tool = load("termspeak_contamination", BENCH / "tools" / "check_contamination.py")
    paths = [str(p) for p in CORPUS] + [str(p) for p in (ROOT / "bench/matrix/finetune").glob("snapshot-*/**/*.jsonl")]
    index = tool.Index(paths)
    bad = [f"{lang}:{c['id']}" for lang in LANGS for c in run.load_cases(DATA, lang, "test")
           if tool.verdict(tool.measure(tool.case_text(c), index)) == "CONTAMINATED"]
    assert bad == []
