"""L5 actif en production (commit 20cfa0d) : l'entrée des corpus d'entraînement est celle que
Narrator envoie au modèle, bloc de faits extraits en code compris.

Enregistrements synthétiques écrits d'après les formats publics des outils (bash, rsync),
jamais recopiés du corpus ni du banc v3.
"""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bench/matrix/finetune"))

import build_dataset_release  # noqa: E402
import build_feature_corpus  # noqa: E402
import compose_k3  # noqa: E402
import rebuild_p15  # noqa: E402
from label import build_messages  # noqa: E402
from steph import prompts  # noqa: E402
from steph.config import Config  # noqa: E402
from steph.digest import digest  # noqa: E402
from steph.narrator import FINETUNED_SUMMARY_CHARS, Narrator  # noqa: E402
from steph.session import Session  # noqa: E402
from steph.strings import t  # noqa: E402
from steph.textproc import compact_output  # noqa: E402

# le code ne dit pas ces sorties seul (D6 lot B) : erreur d'un fichier sourcé, rsync à blanc
RECORDS = [
    {"id": "script", "cmd": "./setup.sh", "exit": 1, "duration": 0.4,
     "output": "configure: running checks\n" * 6 + "./lib/env.sh: line 9: VERSION: unbound variable\n"},
    {"id": "rsync", "cmd": "rsync -avn src/ backup/", "exit": 0, "duration": 1.5, "output": (
        "sending incremental file list\n" + "".join(f"docs/page{i}.md\n" for i in range(12))
        + "\nsent 48,211 bytes  received 290 bytes  97,002.00 bytes/sec\n"
        + "total size is 47,020  speedup is 0.97 (DRY RUN)\n")},
    {"id": "deploy", "cmd": "bash deploy.sh", "exit": 0, "duration": 2.0, "output": (
        "Pulling latest images\n" + "layer ready\n" * 5
        + "lib/env.sh: line 12: cd: /opt/app: No such file or directory\n"
        + "Restarting service\nDone\n")},
]


class _Speaker:
    def say(self, text, interrupt=True, on_done=None):
        if on_done:
            on_done(text)

    def say_stream(self, pieces, interrupt=True, on_done=None):
        self.say("".join(pieces), interrupt, on_done)

    def stop(self):
        pass


def narrator_input(rec, lang, profile):
    n = Narrator(Config(language=lang, llm_profile=profile), Session(), _Speaker(), None)
    sent = []
    n._llm_say = lambda msgs, *a, **k: sent.append(msgs)
    c = n.s.start(rec["cmd"])
    c.start = c.enter_at = 0.0
    c.end, c.exit = rec["duration"], rec["exit"]
    c.out.lines = rec["output"].splitlines()
    c.out.total_lines = len(c.out.lines)
    n._finish(c, c.cwd, c.cwd)
    assert sent, f"{rec['id']} n'atteint pas le modèle"
    return sent[0]


def without_facts(rec, max_chars, lang):
    """Tour utilisateur d'avant L5, celui des corpus déjà étiquetés."""
    out = digest(rec["cmd"], rec["output"], max_chars, lang) or compact_output(rec["output"].splitlines(), max_chars)
    return prompts.summary_messages(rec["cmd"], rec["exit"], rec["duration"], out, len(rec["output"].splitlines()),
                                    language=lang)[1]


CASES = [(r, lang) for r in RECORDS for lang in ("fr", "en")]
IDS = [f"{r['id']}@{lang}" for r, lang in CASES]


@pytest.mark.parametrize("rec,lang", CASES, ids=IDS)
def test_every_record_carries_a_facts_block_in_production(rec, lang):
    assert t(lang, "facts.header") in narrator_input(rec, lang, "finetuned")[1]["content"]


@pytest.mark.parametrize("rec,lang", CASES, ids=IDS)
def test_label_input_is_the_generic_narrator_input(rec, lang):
    assert build_messages(rec, Config().summary_chars, lang) == narrator_input(rec, lang, "generic")


@pytest.mark.parametrize("rec,lang", CASES, ids=IDS)
def test_composed_summary_row_is_the_finetuned_narrator_input(rec, lang):
    row = compose_k3.rebuild_summary("Échec, VERSION non définie.", rec, FINETUNED_SUMMARY_CHARS, lang)
    assert row[:2] == narrator_input(rec, lang, "finetuned")


@pytest.mark.parametrize("rec", RECORDS, ids=[r["id"] for r in RECORDS])
def test_feature_corpus_summary_entry_is_the_generic_narrator_input(rec):
    assert build_feature_corpus.summary_entry(rec)["messages"] == narrator_input(rec, "fr", "generic")


@pytest.mark.parametrize("rec,lang", CASES, ids=IDS)
def test_compose_k3_matches_labeled_rows_with_or_without_facts(tmp_path, rec, lang):
    raw = tmp_path / "raw.jsonl"
    other = {**rec, "id": "other", "output": rec["output"] + "done\n"}
    raw.write_text("".join(json.dumps(r) + "\n" for r in (rec, other)))
    index = compose_k3.raw_index([raw], lang)
    old_user = without_facts(rec, 1500, lang)["content"]
    new_user = build_messages(rec, 1500, lang)[1]["content"]
    assert old_user != new_user
    assert compose_k3.match_raw(old_user, index, lang) == rec
    assert compose_k3.match_raw(new_user, index, lang) == rec


@pytest.mark.parametrize("rec,lang", CASES, ids=IDS)
def test_release_and_p15_rebuilds_match_labeled_rows_with_or_without_facts(rec, lang):
    other = {**rec, "id": "other", "output": rec["output"] + "done\n"}
    old_user = without_facts(rec, 1500, lang)["content"]
    new_user = build_messages(rec, 1500, lang)[1]["content"]
    index = build_dataset_release.index_raw([rec, other], lang)
    assert build_dataset_release.match_raw(old_user, index, lang) == rec
    assert build_dataset_release.match_raw(new_user, index, lang) == rec
    if lang == "fr":
        index = {}
        for r in (rec, other):
            index.setdefault(rebuild_p15.header_key(build_messages(r, 1500)[1]["content"]), []).append(r)
        assert rebuild_p15.match_raw(old_user, index) == rec
        assert rebuild_p15.match_raw(new_user, index) == rec
