"""R3-T4 partie 1 : tests de onpolicy_sample.py.

    python3 -m pytest bench/matrix/finetune/loop/r3t4/test_onpolicy_sample.py -q

SPDX-License-Identifier: MIT
"""

import onpolicy_sample as s

FR_USER = ("Commande : ls -la /tmp\nStatut : échec (code 2)\nDurée : 0.3 s ; 4 lignes affichées\n"
           "Sortie :\nls: impossible d'accéder\nligne deux")
EN_USER = ("Command: make test\nStatus: success (code 0)\nDuration: 12.0 s; 40 lines displayed\n"
           "Output:\n(no output)")


def test_parse_french_turn():
    rec = s.parse_user(FR_USER, "fr")
    assert rec == {"cmd": "ls -la /tmp", "exit": 2, "duration": 0.3, "nlines": 4,
                   "output": "ls: impossible d'accéder\nligne deux", "facts": None}


def test_parse_english_turn_with_placeholder():
    rec = s.parse_user(EN_USER, "en")
    assert rec["exit"] == 0 and rec["nlines"] == 40 and rec["output"] == ""


def test_parse_unknown_status_and_signal():
    unknown = FR_USER.replace("échec (code 2)", "inconnu")
    assert s.parse_user(unknown, "fr")["exit"] is None
    ctrl_c = EN_USER.replace("success (code 0)", "interrupted by the user (Ctrl+C, code 130)")
    assert s.parse_user(ctrl_c, "en")["exit"] == 130


def test_parse_rejects_other_formats():
    assert s.parse_user("Commande : ls\nEn cours depuis 3 s\nDernières lignes :\nx", "fr") is None


def test_rebuilt_prompt_is_the_production_one():
    from steph import prompts
    rec = s.parse_user(FR_USER, "fr")
    msgs = s.production_messages(rec, "fr")
    assert msgs[0]["content"] == prompts.SUMMARY_SYSTEM_FINETUNED
    assert msgs[1]["content"].startswith("Commande : ls -la /tmp\nStatut : échec (code 2)\n")
    assert "4 lignes affichées" in msgs[1]["content"]


FACTS_FR = "Faits extraits en code :\n- Erreur : ls: impossible d'accéder\n- Projet : tmp\n"
FACTS_EN = "Facts extracted by code:\n- Tool summary: 3 passed\n"


def test_parse_keeps_the_facts_block_of_a_row_rebuilt_with_l5():
    fr = s.parse_user(FR_USER.replace("Sortie :\n", FACTS_FR + "Sortie :\n"), "fr")
    assert fr["facts"] == ["Erreur : ls: impossible d'accéder", "Projet : tmp"]
    assert fr["output"] == "ls: impossible d'accéder\nligne deux" and fr["nlines"] == 4
    en = s.parse_user(EN_USER.replace("Output:\n", FACTS_EN + "Output:\n"), "en")
    assert en["facts"] == ["Tool summary: 3 passed"] and en["output"] == ""


def test_rebuilt_prompt_carries_the_facts_block_of_the_row():
    user = FR_USER.replace("Sortie :\n", FACTS_FR + "Sortie :\n")
    assert s.production_messages(s.parse_user(user, "fr"), "fr")[1]["content"] == user
    assert s.production_messages(s.parse_user(FR_USER, "fr"), "fr")[1]["content"] == FR_USER


def _index(texts, cmds=("ls -la",)):
    cases = [{"id": f"c{i}", "cmds": [s.norm_cmd(c) for c in cmds], "reps": [s.rep(t)]} for i, t in enumerate(texts)]
    return s.BenchIndex(cases)


def test_contamination_flags_a_copied_output():
    out = "\n".join(f"fichier numero {i} avec du texte assez long" for i in range(6))
    idx = _index([out])
    assert idx.hit([f"Commande : cat x\nSortie :\n{out}"], ["cat x"])
    assert not idx.hit(["Commande : cat x\nSortie :\ntout autre chose ici\net encore"], ["cat x"])


def test_contamination_same_command_lower_threshold():
    base = [f"ligne commune {w} du texte" for w in ("alpha", "beta", "gamma", "delta")]
    case = "\n".join(base + [f"propre au cas {w}" for w in ("un", "deux", "trois")])
    entry = "\n".join(base + [f"propre au corpus {w}" for w in ("un", "deux", "trois")])
    idx = _index([case], cmds=("ls -la",))
    assert not idx.hit([entry], ["cat x"])  # Jaccard des lignes 4/10 < 0,5, pas de commande commune
    assert idx.hit([entry], ["ls -la"])  # même commande normalisée : seuil 0,3


def test_allocation_keeps_total_and_caps_english():
    eligible = {"macos": 300, "linux-low": 600, "macos.en": 250, "linux-low.en": 200}
    alloc = s.allocate(eligible, total=1500, en_cap=500)
    assert sum(alloc.values()) == 1350  # tout l'éligible : 900 FR + 450 EN
    assert alloc["macos.en"] + alloc["linux-low.en"] == 450
    assert all(alloc[k] <= eligible[k] for k in eligible)


def test_allocation_fills_to_total():
    eligible = {"a": 2000, "b": 1000, "x.en": 800}
    alloc = s.allocate(eligible, total=1500, en_cap=500)
    assert sum(alloc.values()) == 1500 and alloc["x.en"] == 500
    assert abs(alloc["a"] - 2 * alloc["b"]) <= 1


def test_reaches_uses_the_real_line_count():
    rec = s.parse_user(FR_USER, "fr")  # 5 mots sur 2 lignes affichées, mais 4 lignes réelles
    assert s.reaches(rec, "fr")
    assert not s.reaches({**rec, "nlines": 2}, "fr")  # dit tel quel en production
    assert not s.reaches({**rec, "output": ""}, "fr")
    assert not s.reaches({**rec, "exit": 127, "output": "zsh: command not found: foo"}, "fr")


def test_payload_follows_the_task():
    assert s.payload("summary") == {"temperature": 0.2, "top_p": 0.9, "max_tokens": 90}
    assert s.payload("qa") == {"temperature": 0.3, "top_p": 0.9, "max_tokens": 400}


def test_stats_counts_distinct_answers_and_lengths():
    selected = [{"id": "a", "task": "summary", "lang": "fr", "label": "un deux trois quatre"},
                {"id": "b", "task": "qa", "lang": "fr", "label": "un deux"}]
    samples = [{"id": "a", "k": 0, "text": "un deux", "finish": "stop"},
               {"id": "a", "k": 1, "text": "un deux", "finish": "stop"},
               {"id": "a", "k": 2, "text": "trois mots ici", "finish": "stop"},
               {"id": "b", "k": 0, "text": "x " * 5, "finish": "length"},
               {"id": "b", "k": 1, "text": None, "error": "URLError"}]
    st = s.stats(selected, samples)
    assert st["summary/fr"]["entries"] == 1 and st["summary/fr"]["samples"] == 3
    assert st["summary/fr"]["distinct_per_entry"] == {"2": 1}
    assert st["summary/fr"]["unique_to_judge"] == 2
    assert st["summary/fr"]["words_mean"] == round((2 + 2 + 3) / 3, 2)
    assert st["summary/fr"]["label_words_mean"] == 4.0
    assert st["qa/fr"]["errors"] == 1 and st["qa/fr"]["truncated"] == 1
    assert st["all"]["unique_to_judge"] == 3
