"""R3-T4 partie 2 : tests de mask_pairs.py (empans inventés, masque par jeton, paires, cache du juge).

    python3 -m pytest bench/matrix/finetune/loop/r3t4/test_mask_pairs.py -q

SPDX-License-Identifier: MIT
"""

import mask_pairs as m


# ---------------------------------------------------------------- localisation des empans
def test_exact_fragment_is_located():
    text = "Échec, 3 erreurs dans config.yaml."
    assert m.locate_spans(text, ["3 erreurs"]) == [(7, 16)]


def test_fragment_located_case_insensitive_and_trimmed():
    text = "Build failed at line 12 of main.c."
    assert m.locate_spans(text, ["« Line 12 »"]) == [(16, 23)]


def test_paraphrased_fact_located_by_its_number():
    text = "Disque plein à 97 %, 2 Go libres."
    spans = m.locate_spans(text, ["Le pourcentage d'utilisation de 97 % n'apparaît pas dans le contexte"])
    assert spans == [(15, 17)]


def test_paraphrased_fact_located_by_identifier():
    text = "Le paquet libssl-dev est manquant."
    spans = m.locate_spans(text, ["nom du paquet libssl-dev"])
    assert spans == [(10, 20)]


def test_status_invention_located_by_status_word():
    text = "Succès, 12 fichiers copiés."
    assert m.locate_spans(text, ["statut succès alors que le code est 1"]) == [(0, 6)]
    en = "Failed, 2 tests broke."
    assert m.locate_spans(en, ["claims failure although exit code 0"]) == [(0, 6)]


def test_unlocatable_fact_gives_no_span():
    assert m.locate_spans("Tout est à jour.", ["la version 4.2 est installée"]) == []


def test_overlapping_spans_are_merged():
    text = "Erreur ligne 12 dans main.c."
    assert m.locate_spans(text, ["ligne 12", "12 dans main.c"]) == [(7, 27)]


def test_number_inside_a_longer_number_is_not_matched():
    text = "Transfert de 120 Mo terminé."
    assert m.locate_spans(text, ["12 Mo"]) == []


# ---------------------------------------------------------------- masque par jeton
def test_token_keep_marks_tokens_overlapping_a_span():
    offsets = [(0, 5), (5, 6), (6, 8), (8, 16), (16, 17)]
    assert m.token_keep(offsets, [(7, 16)], shift=0) == [False, False, True, True, False]


def test_token_keep_applies_the_answer_shift():
    offsets = [(0, 3), (3, 8), (8, 12)]
    assert m.token_keep(offsets, [(0, 4)], shift=4) == [False, True, False]


def test_token_keep_ignores_empty_offsets():
    assert m.token_keep([(0, 0), (0, 4)], [(0, 4)], shift=0) == [False, True]


# ---------------------------------------------------------------- paires
def _row(texts_verdicts, label="Échec, 2 erreurs.", eid="e1"):
    outs = [{"k": k, "text": t} for k, (t, _, _) in enumerate(texts_verdicts)]
    verdicts = {m.cache_key(eid, t): {"final": v, "inventions": inv} for t, v, inv in texts_verdicts}
    return {"id": eid, "task": "summary", "lang": "fr", "messages": [{"role": "user", "content": "x"}],
            "label": label}, outs, verdicts


def test_pair_uses_faithful_output_closest_to_label_length():
    entry, outs, verdicts = _row([
        ("Échec.", "ok", []),
        ("Échec, 2 erreurs de lien.", "ok", []),
        ("Échec, 5 erreurs de lien.", "invention", ["5 erreurs"]),
    ])
    pairs, why = m.entry_pairs(entry, outs, verdicts, max_pairs=2)
    assert why == "pairs"
    assert len(pairs) == 1
    assert pairs[0]["chosen"] == "Échec, 2 erreurs de lien."
    assert pairs[0]["rejected"] == "Échec, 5 erreurs de lien."
    assert pairs[0]["rejected_spans"] == [[7, 16]]


def test_douteux_is_neither_chosen_nor_rejected():
    entry, outs, verdicts = _row([
        ("Échec, 2 erreurs.", "douteux", []),
        ("Échec, 5 erreurs.", "invention", ["5 erreurs"]),
    ])
    pairs, why = m.entry_pairs(entry, outs, verdicts, max_pairs=2)
    assert pairs == [] and why == "no_faithful"


def test_invention_without_located_span_is_dropped():
    entry, outs, verdicts = _row([
        ("Échec, 2 erreurs.", "ok", []),
        ("Échec, cause inconnue.", "invention", ["la cause réelle est un disque plein"]),
    ])
    pairs, why = m.entry_pairs(entry, outs, verdicts, max_pairs=2)
    assert pairs == [] and why == "no_span"


def test_duplicate_rejected_texts_make_one_pair_and_cap_applies():
    entry, outs, verdicts = _row([
        ("Échec, 2 erreurs.", "ok", []),
        ("Échec, 5 erreurs.", "invention", ["5 erreurs"]),
        ("Échec, 5 erreurs.", "invention", ["5 erreurs"]),
        ("Échec, 7 erreurs.", "invention", ["7 erreurs"]),
        ("Échec, 9 erreurs.", "invention", ["9 erreurs"]),
    ])
    pairs, _ = m.entry_pairs(entry, outs, verdicts, max_pairs=2)
    assert [p["rejected"] for p in pairs] == ["Échec, 5 erreurs.", "Échec, 7 erreurs."]


def test_no_invention_gives_no_pair():
    entry, outs, verdicts = _row([("Échec, 2 erreurs.", "ok", [])])
    assert m.entry_pairs(entry, outs, verdicts, max_pairs=2) == ([], "no_invention")


# ---------------------------------------------------------------- juge : dédoublonnage et passe B
def test_cache_key_depends_on_entry_and_exact_bytes():
    assert m.cache_key("a", "x") == m.cache_key("a", "x")
    assert m.cache_key("a", "x") != m.cache_key("b", "x")
    assert m.cache_key("a", "x") != m.cache_key("a", "x ")


def test_final_verdict_matches_judge_v3():
    assert m.final_verdict("invention", "invention") == "invention"
    assert m.final_verdict("invention", "ok") == "douteux"
    assert m.final_verdict("ok", "ok") == "ok"
    assert m.final_verdict("ok", "erreur") == "erreur"


def test_pass_b_only_for_entries_with_a_pass_a_invention():
    unique = {("e1", "t1"), ("e1", "t2"), ("e2", "t3")}
    pass_a = {m.cache_key("e1", "t1"): "invention", m.cache_key("e1", "t2"): "ok", m.cache_key("e2", "t3"): "ok"}
    assert m.needs_pass_b(unique, pass_a) == {("e1", "t1"), ("e1", "t2")}


def test_shard_split_is_disjoint_and_complete():
    keys = [f"k{i}" for i in range(10)]
    parts = [m.shard(keys, i, 3) for i in range(3)]
    assert sorted(sum(parts, [])) == sorted(keys)
    assert all(not set(parts[i]) & set(parts[j]) for i in range(3) for j in range(i + 1, 3))


def test_length_balance():
    pairs = [{"chosen": "a b c d", "rejected": "a b c d e"}, {"chosen": "a b", "rejected": "a b"}]
    ratio = m.length_ratio(pairs)
    assert abs(ratio - 7 / 6) < 1e-9


def test_length_filter_drops_pairs_whose_rejected_is_too_long():
    p = lambda c, r: {"chosen": c, "rejected": r}  # noqa: E731
    pairs = [p("a b", "a b c d"), p("a b", "a b c d e"), p("a b c", "a")]
    kept = m.length_filter(pairs, 2.0)
    assert kept == [pairs[0], pairs[2]]
