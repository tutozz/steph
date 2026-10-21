from steph.grounding import ground, ground_stream


def test_true_number_kept():
    inp = "Sortie :\nracine : 8.9G libres sur 94G, 91 %"
    out = "Racine 8.9G libres sur 94G, 91 %."
    assert ground(inp, out) == "Racine 8.9G libres sur 94G, 91 %."


def test_invented_number_cut():
    inp = "Sortie :\nracine : 8.9G libres sur 94G, 91 %\nbackup-hdd : 134G libres sur 442G, 70 %"
    out = "Racine 8.9G libres sur 94G. Backup SSD 11M libres sur 12M."
    assert ground(inp, out) == "Racine 8.9G libres sur 94G."


def test_number_word_not_in_input_is_cut():
    inp = "Sur la branche master\nAucun commit\nFichiers non suivis:\n\t.python-version"
    out = "Succès. Un commit sur master, aucun fichier non suivi."
    assert ground(inp, out) == "Succès. aucun fichier non suivi."


def test_number_word_present_is_kept():
    inp = "Sortie :\nPing 127.0.0.1 : 3 paquets reçus"
    out = "Ping 127.0.0.1 : 3 paquets reçus."
    assert ground(inp, out) == out


def test_identifier_mismatch_cut():
    inp = "10 éléments, les plus gros : OLD_SHOPAPP 12G, installer-iso 7,9G, shopapp 2,4G"
    out = "10 éléments : OLD_SHOPAPP 12G, install-iso 7,9G, shopapp 2,4G."
    assert ground(inp, out) == "10 éléments : OLD_SHOPAPP 12G. shopapp 2,4G."


def test_identifier_match_kept():
    inp = "18 éléments : pipewire.service actif, pipewire.socket activé"
    out = "18 éléments : pipewire.service actif, pipewire.socket activé."
    assert ground(inp, out) == out


def test_proper_noun_invented_cut():
    inp = "Linux devbox 7.0.9-202.fc44.x86_64 #1 SMP PREEMPT_DYNAMIC Mon May 18 22:33:24 UTC 2026 x86_64 GNU/Linux"
    out = "Linux devbox 7.0.9-202.fc44.x86_64, CPU Xeon Scalable, GPU NVIDIA Tesla T4."
    result = ground(inp, out)
    assert "Xeon" not in result
    assert "Tesla" not in result
    assert "T4" not in result
    assert "devbox" in result


def test_digit_letter_mix_mismatch_cut():
    inp = "2b:00.0 VGA compatible controller: NVIDIA Corporation GA106 [GeForce RTX 3060 Lite Hash Rate]"
    out = "GPU GeForce RTX 3060 Lite, GBA106."
    result = ground(inp, out)
    assert "GBA106" not in result
    assert "GeForce RTX 3060 Lite" in result


def test_path_kept_when_grounded():
    inp = "rm: impossible de supprimer '/etc/hostname': Permission non accordée"
    out = "Échec. /etc/hostname : Permission non accordée."
    assert ground(inp, out) == out


def test_decimal_comma_not_split():
    inp = "10 éléments, les plus gros : installer-iso 7,9G"
    out = "installer-iso 7,9G."
    assert ground(inp, out) == out


def test_dotted_filename_not_split():
    inp = "src/components/Header.tsx:42:17 - error TS2339: Property 'titel' does not exist"
    out = "Échec. Header.tsx ligne 42 : titel inexistant."
    assert ground(inp, out) == out


def test_qa_replaced_when_fully_invented():
    inp = "Historique :\nCommande : npm run build\nStatut : échec (code 1)\nSortie :\nHeader.tsx:42"
    out = "Python 3.11 installé."
    assert ground(inp, out, is_qa=True) == "Pas dans l'historique."


def test_qa_kept_when_grounded():
    inp = "racine : 8.9G libres sur 94G, 91 %"
    out = "Racine 8.9G libres sur 94G, 91 %."
    assert ground(inp, out, is_qa=True) == out


def test_empty_output():
    assert ground("peu importe", "") == ""


def test_template_words_never_require_grounding():
    inp = "Sortie :\nMémoire : 31G total, 24G disponibles"
    out = "Mémoire 31G total, 24G disponibles."
    assert ground(inp, out) == out


def _stream(text, chunk_size):
    for i in range(0, len(text), chunk_size):
        yield text[i:i + chunk_size]


def test_ground_stream_matches_ground_single_chunk():
    inp = "10 éléments, les plus gros : OLD_SHOPAPP 12G, installer-iso 7,9G, shopapp 2,4G"
    out = "10 éléments : OLD_SHOPAPP 12G, install-iso 7,9G, shopapp 2,4G."
    assert "".join(ground_stream(iter([out]), inp)) == ground(inp, out)


def test_ground_stream_matches_ground_char_by_char():
    inp = "10 éléments, les plus gros : OLD_SHOPAPP 12G, installer-iso 7,9G, shopapp 2,4G"
    out = "10 éléments : OLD_SHOPAPP 12G, install-iso 7,9G, shopapp 2,4G."
    assert "".join(ground_stream(_stream(out, 1), inp)) == ground(inp, out)


def test_ground_stream_preserves_decimal_split_across_pieces():
    inp = "10 éléments, les plus gros : installer-iso 7,9G"
    out = "installer-iso 7,9G."
    # le "7" et le "," arrivent dans un morceau, "9G." dans le suivant : le nombre décimal
    # ne doit pas être coupé en deux propositions par erreur.
    assert "".join(ground_stream(iter(["installer-iso 7,", "9G."]), inp)) == out


def test_ground_stream_qa_not_found():
    inp = "Historique :\nCommande : npm run build\nStatut : échec (code 1)\nSortie :\nHeader.tsx:42"
    out = "Python 3.11 installé."
    assert "".join(ground_stream(iter([out]), inp, is_qa=True)) == "Pas dans l'historique."


def test_exit_code_does_not_ground_an_invented_line_number():
    inp = ("Commande : rm /etc/hostname\nStatut : échec (code 1)\nDurée : 0.0 s ; 1 lignes affichées\n"
           "Sortie :\nrm: impossible de supprimer '/etc/hostname': Permission non accordée")
    out = "Échec. /etc/hostname ligne 1 : Permission non accordée."
    assert ground(inp, out) == "Échec."


# --- L3 : faux rejets du garde-fou (exemples inspirés du dev v3 : history-qa-0010, 0041, 0054, 0056)

def test_hash_starting_with_a_digit_is_grounded_whole():
    inp = "Sortie :\n4f0e2a91c7d3b8e6  release.tar.gz"
    assert ground(inp, "4f0e2a91c7d3b8e6.") == "4f0e2a91c7d3b8e6."


def test_hash_starting_with_a_digit_absent_from_input_is_cut():
    inp = "Sortie :\n4f0e2a91c7d3b8e6  release.tar.gz"
    assert ground(inp, "Empreinte 4f0e2a91c7d3b8e7, release.tar.gz.") == "release.tar.gz."


def test_version_starting_with_a_digit_is_grounded_whole():
    inp = "Setting up linux-image-6.12.94+deb13-amd64 (6.12.94-1) ..."
    assert ground(inp, "Noyau 6.12.94-1 installé.") == "Noyau 6.12.94-1 installé."
    assert ground(inp, "Noyau 6.12.95-1 installé.") == ""


def test_number_with_unit_suffix_still_reads_as_a_number():
    inp = "Sortie :\nracine : 8.9 G libres sur 94 G"
    assert ground(inp, "8.9G libres sur 94G.") == "8.9G libres sur 94G."


def test_french_compound_number_word_is_checked_as_a_number():
    inp = "Sortie :\n36 warnings generated."
    assert ground(inp, "Trente-six avertissements.", is_qa=True) == "Trente-six avertissements."
    assert ground(inp, "Trente-sept avertissements.", is_qa=True) == "Pas dans l'historique."


def test_english_compound_number_word_is_checked_as_a_number():
    inp = "Sortie :\ncollected 45 items"
    assert ground(inp, "Forty-five tests collected.", language="en") == "Forty-five tests collected."
    assert ground(inp, "Forty-six tests collected.", language="en") == ""


def test_french_compound_numbers_above_sixty():
    inp = "Sortie :\n70 fichiers, 97 dossiers, 80 liens, 21 erreurs"
    out = "Soixante-dix fichiers, quatre-vingt-dix-sept dossiers, quatre-vingts liens, vingt-et-un erreurs."
    assert ground(inp, out) == out


def test_hyphenated_word_mixing_number_words_and_others_stays_an_identifier():
    inp = "Sortie :\nok"
    assert ground(inp, "Service deux-roues actif.") == ""


def test_period_after_a_digit_then_capital_ends_the_sentence():
    inp = "jq: error (at <stdin>:4): parse error at line 4, column 22"
    out = "Erreur jq ligne 4 colonne 22. Format JSON invalide."
    assert ground(inp, out, is_qa=True) == out


def test_period_after_a_digit_only_cuts_the_invented_sentence():
    inp = "jq: error (at <stdin>:4): parse error at line 4, column 22"
    out = "Erreur jq ligne 4 colonne 22. Fichier Zorglub corrompu."
    assert ground(inp, out) == "Erreur jq ligne 4 colonne 22."


def test_period_after_a_digit_then_lowercase_does_not_split():
    inp = "Sortie :\nversion 3 ok"
    assert ground(inp, "version 3. ok.") == "version 3. ok."


def test_ground_stream_splits_after_a_digit_char_by_char():
    inp = "jq: error (at <stdin>:4): parse error at line 4, column 22"
    out = "Erreur jq ligne 4 colonne 22. Fichier Zorglub corrompu."
    assert "".join(ground_stream(_stream(out, 1), inp)) == ground(inp, out)
