"""D6, lot B : scripts et fichiers dits en code (docs/code-first-d6.md, section 4).

Provenance des formats : sorties réelles de GNU coreutils 9.x, bash 5.2, GNU tar 1.35,
diffutils, grep et rsync 3.4.1, capturées en LANG=C et LANG=fr_FR.UTF-8 sur une machine du
labo (bench/matrix/results/code-first-d6/lot-b/real-*.txt), et catalogues fr.mo de ces outils
(espaces insécables des traductions compris). Aucun cas du split test n'a servi.
"""

import pytest

from steph.digest import resolve

NB = "\xa0"


# ---------------------------------------------------------------- _script_error
# format « script: line N: msg » de bash (fr : « ligne N : »), erreurs d'outil GNU « outil: msg »

def test_script_unbound_variable_fr_and_en():
    out = "start\nunbound.sh: line 4: UNDEF_VAR: unbound variable"
    assert resolve("bash unbound.sh", 1, out) == "Échec. unbound.sh ligne 4 : variable UNDEF_VAR non définie."
    assert resolve("bash unbound.sh", 1, out, "en") == "Failed. unbound.sh line 4: unbound variable UNDEF_VAR."
    fr = "start\n./rotation.sh: ligne 7: DUREE_RETENTION : variable sans liaison"
    assert resolve("./rotation.sh", 1, fr) == "Échec. rotation.sh ligne 7 : variable DUREE_RETENTION non définie."
    assert resolve("./rotation.sh", 1, fr, "en") == "Failed. rotation.sh line 7: unbound variable DUREE_RETENTION."


def test_script_division_by_zero_is_translated():
    en = 'div.sh: line 2: 1 / 0: division by 0 (error token is "0")'
    fr = f"div.sh: ligne 2: 1 / 0 : division par 0 (le symbole erroné est «{NB}0{NB}»)"
    assert resolve("bash div.sh", 1, en) == "Échec. div.sh ligne 2 : division par zéro."
    assert resolve("bash div.sh", 1, fr, "en") == "Failed. div.sh line 2: division by zero."


def test_script_last_error_wins_and_errors_are_counted():
    out = ("start\nerrs.sh: line 3: cd: /nonexistent/dir: No such file or directory\n"
           "cp: cannot stat 'nope.csv': No such file or directory")
    assert resolve("bash errs.sh", 3, out) == "Échec, 2 erreurs. Dernière : cp, nope.csv : introuvable."
    assert resolve("bash errs.sh", 3, out, "en") == "Failed, 2 errors. Last: cp, nope.csv: not found."


def test_script_tool_error_alone():
    out = ("Bilan : 75 lignes traitées, total 3460\n"
           "mv: impossible d'évaluer 'export_pointage.csv': Aucun fichier ou dossier de ce nom")
    assert resolve("./pointage.sh", 1, out) == \
        "Échec. mv, export_pointage.csv : introuvable. Dernier message : Bilan : 75 lignes traitées, total 3460."
    sort = "sort: impossible de lire: suivi_transporteur.txt: Aucun fichier ou dossier de ce nom"
    assert resolve("./colis.sh", 2, "x\n" + sort) == "Échec. sort, suivi_transporteur.txt : introuvable."
    bsd = "82 items synced\ncp: /nonexistent/reports: No such file or directory"
    assert resolve("./sync.sh", 1, bsd, "en") == \
        "Failed. cp, /nonexistent/reports: not found. Last message: 82 items synced."


def test_script_same_tool_failing_several_times_names_them():
    # piège D6 : deux cp en échec, un seul était dit
    out = ("copied export-01.csv\n"
           "cp: impossible d'évaluer 'data/export-04.csv': Aucun fichier ou dossier de ce nom\n"
           "copied export-05.csv\n"
           "cp: impossible d'évaluer 'data/export-09.csv': Aucun fichier ou dossier de ce nom\n"
           "done: 8 copied, 2 failed")
    assert resolve("bash collect.sh", 1, out) == \
        "Échec, 2 erreurs de cp : data/export-04.csv et data/export-09.csv, introuvables. " \
        "Dernier message : done: 8 copied, 2 failed."
    assert resolve("bash collect.sh", 1, out, "en") == \
        "Failed, 2 cp errors: data/export-04.csv and data/export-09.csv, not found. " \
        "Last message: done: 8 copied, 2 failed."


def test_script_same_tool_many_failures_gives_count_and_example():
    lines = [f"rm: cannot remove 'tmp/cache_{i}.tmp': No such file or directory" for i in range(2, 12, 2)]
    out = "Cleaning\n" + "\n".join(lines)
    assert resolve("bash clean.sh", 1, out) == "Échec, 5 erreurs de rm, introuvables, dont tmp/cache_2.tmp."


def test_script_tar_generic_last_line_keeps_the_real_cause():
    # piège D6 : « Error is not recoverable » ne dit pas la cause
    fr = ("Archivage des factures de septembre\n"
          "tar (child): backups/factures-2026-09.tar.gz : open impossible: Aucun fichier ou dossier de ce nom\n"
          "tar (child): Error is not recoverable: exiting now\n"
          "tar: Child returned status 2\n"
          "tar: Error is not recoverable: exiting now")
    assert resolve("bash archive.sh", 2, fr) == \
        "Échec. tar, backups/factures-2026-09.tar.gz : introuvable, erreur non récupérable."
    en = "tar: missing.tar: Cannot open: No such file or directory\ntar: Error is not recoverable: exiting now"
    assert resolve("sh unpack.sh", 2, en, "en") == "Failed. tar, missing.tar: not found, unrecoverable error."


def test_tar_truncated_archive_is_translated():
    fr = ("releves/\nreleves/mai/\ntar: Fin prématurée rencontrée dans l'archive.\n"
          "tar: Fin prématurée rencontrée dans l'archive.\ntar: Error is not recoverable: exiting now")
    # tar redit la même fin prématurée : une seule erreur
    assert resolve("bash restore.sh", 2, fr) == "Échec. tar, archive tronquée, erreur non récupérable."
    en = "tar: Unexpected EOF in archive\ntar: Error is not recoverable: exiting now"
    assert resolve("bash restore.sh", 2, en, "en") == "Failed. tar, truncated archive, unrecoverable error."


def test_tool_run_directly_says_its_own_errors_after_a_verbose_listing():
    tar = "releves/\nreleves/mai/\nreleves/mai/a.csv\ntar: Unexpected EOF in archive\n" \
          "tar: Error is not recoverable: exiting now"
    assert resolve("tar -xvf releves.tar", 2, tar, "en") == "Failed. tar, truncated archive, unrecoverable error."
    ls = ("ls: impossible d'accéder à 'devi_17.txt': Aucun fichier ou dossier de ce nom\n"
          "ls: impossible d'accéder à 'devi_20.txt': Aucun fichier ou dossier de ce nom\n"
          "-rw-r----- 1 root root 160 28 sept. 07:13 devi_08.txt\n"
          "-rw-r----- 1 root root 221 28 sept. 07:13 devi_11.txt\n"
          "-rw-r----- 1 root root  48 28 sept. 07:13 devi_01.txt\n"
          "-rw-r----- 1 root root  96 28 sept. 07:13 devi_04.txt")
    assert resolve("ls -l devi_08.txt devi_17.txt devi_20.txt devi_11.txt devi_01.txt devi_04.txt", 2, ls) == \
        "Échec, 2 erreurs de ls : devi_17.txt et devi_20.txt, introuvables."
    mk = "\n".join(f"mkdir: created directory 'p/m_{i:02}'" for i in range(8)) + \
        "\nmkdir: cannot create directory ‘p/m_07’: File exists"
    assert resolve("mkdir -v p/m_00 p/m_01 p/m_07", 1, mk, "en") == "Failed. mkdir, p/m_07: already exists."


@pytest.mark.parametrize("cmd, code, out", [
    ("make", 2, "a\ncp: cannot stat 'x': No such file or directory"),  # pas un script
    ("bash -c 'cp x b'", 1, "cp: cannot stat 'x': No such file or directory"),
    ("rm -v a x", 1, "removed 'a'\nrm: cannot remove 'x': No such file or directory"),
    ("diff -rq a x", 2, "diff: x: No such file or directory"),
    ("wc -l a x", 1, "wc: x: No such file or directory\n 3 a\n 3 total"),
])
def test_short_single_tool_error_keeps_the_existing_file_sentence(cmd, code, out):
    assert resolve(cmd, code, out) == "Échec. x : fichier introuvable."


def test_script_that_returns_zero_after_one_error_says_so():
    # sans `set -e`, bash continue après une erreur et le script peut finir par « ok »
    one = "a\nx.sh: line 4: [: 3: unary operator expected\nBilan : 7 lignes traitées"
    assert resolve("./x.sh", 0, one) == \
        "Terminé, mais une erreur : x.sh ligne 4 : [: 3: unary operator expected. Dernier message : Bilan : 7 lignes traitées."
    out = "+ rsync_x a b\nsave.sh: line 10: rsync_x: command not found\n+ echo done\ndone"
    assert resolve("./save.sh", 0, out, "en") == "Finished, but one error: save.sh line 10: command rsync_x not found."


@pytest.mark.parametrize("cmd, out", [
    # plusieurs erreurs sous un code 0 : la première est souvent la cause, la dernière sa suite
    ("bash backup.sh data", "backup.sh: line 7: cd: /var/backups/shop: Permission denied\n"
                            "cp: /var/backups/shop/a.csv: Permission denied\nok"),
    ("./clean.sh", "rm: cannot remove 'a': No such file or directory\nrm: cannot remove 'b': No such file or directory"),
    ("rm -f a b", "rm: cannot remove 'a': Permission denied\nrm: cannot remove 'b': Permission denied\nx"),
])
def test_zero_exit_with_several_errors_is_left_to_the_model(cmd, out):
    assert resolve(cmd, 0, out) is None


def test_creating_in_a_missing_place_keeps_the_system_message():
    # ENOENT sur mkdir : composant absent, ou système de fichiers qui refuse (/proc) ; on ne devine pas
    out = "a\nmkdir: cannot create directory ‘/proc/release’: Aucun fichier ou dossier de ce nom"
    assert resolve("./deploy.sh", 1, out) == \
        "Échec. mkdir, création de /proc/release impossible, aucun fichier ou dossier de ce nom."
    ln = "a\nln: failed to create symbolic link 'x/l': No such file or directory"
    assert resolve("bash links.sh", 1, ln, "en") == "Failed. ln, cannot create x/l, no such file or directory."


def test_last_message_is_quoted_only_when_it_is_a_count_in_the_session_language():
    fr_line = "Bilan : 69 lignes traitées, total 3306"
    err = "./x.sh: line 3: X: unbound variable"
    assert resolve("./x.sh", 1, fr_line + "\n" + err, "en") == "Failed. x.sh line 3: unbound variable X."
    assert resolve("./x.sh", 1, "Starting\n" + err, "en") == "Failed. x.sh line 3: unbound variable X."
    # une ligne d'erreur n'est pas un bilan
    assert resolve("./x.sh", 1, "error: 3 retries left\n" + err, "en") == "Failed. x.sh line 3: unbound variable X."


def test_older_french_tar_catalog():
    # traduction de GNU tar plus ancienne (corpus public Steph Speak Bench v1)
    out = "\n".join(f"b/etc/f_{i}.dat" for i in range(6)) + \
        "\ntar : Fin de fichier inattendue dans l'archive\ntar : Erreur non récupérable : abandon"
    assert resolve("tar -xvf b.tar.gz", 2, out) == "Échec. tar, archive tronquée, erreur non récupérable."


def test_no_space_left_names_each_file_once():
    en = ("cp: error writing '/var/backups/b/dist/app.bin': No space left on device\n"
          "cp: failed to extend '/var/backups/b/dist/app.bin': No space left on device\n"
          "cp: closing output file '/var/backups/b/dist/app.bin': No space left on device\n"
          "cp: error writing '/var/backups/b/dist/assets.tar': No space left on device")
    assert resolve("cp -r build/ /var/backups/b/", 1, en, "en") == \
        "Failed, 4 cp errors: /var/backups/b/dist/app.bin and /var/backups/b/dist/assets.tar, no space left on device."
    fr = ("cp: impossible d'agrandir «\xa0/var/backups/b/dist/app.bin\xa0» : Plus d'espace disponible sur le périphérique\n"
          "cp: erreur d'écriture de «\xa0/var/backups/b/dist/app.bin\xa0» : Plus d'espace disponible sur le périphérique")
    assert resolve("cp -r build/ /var/backups/b/", 1, fr) == \
        "Échec, 2 erreurs de cp : /var/backups/b/dist/app.bin, plus d'espace sur le disque."


def test_tar_fatal_suffix_belongs_to_tar_only():
    out = ("tar: Unexpected EOF in archive\ntar: Error is not recoverable: exiting now\n"
           "cp: cannot stat 'out/a.csv': No such file or directory")
    assert resolve("bash restore.sh", 1, out, "en") == "Failed, 2 errors. Last: cp, out/a.csv: not found."


def test_last_message_is_never_an_xtrace_line():
    out = "+ echo 'copied 3 files'\n./x.sh: line 5: Y: unbound variable"
    assert resolve("./x.sh", 1, out, "en") == "Failed. x.sh line 5: unbound variable Y."


def test_french_elisions_survive_in_quoted_messages():
    out = "a\nx.sh: ligne 3: impossible d'ouvrir le fichier de config"
    assert resolve("bash x.sh", 1, out) == "Échec. x.sh ligne 3 : impossible d'ouvrir le fichier de config."


def test_script_long_path_keeps_its_last_two_parts():
    out = "cp: cannot stat '/very/long/path/to/some/deeply/nested/folder/report.csv': No such file or directory"
    assert resolve("bash x.sh", 1, "a\n" + out, "en") == "Failed. cp, folder/report.csv: not found."


def test_script_permission_and_existing_directory():
    out = f"a\nmkdir: impossible de créer le répertoire «{NB}out{NB}»: Le fichier existe"
    assert resolve("bash mk.sh", 1, out) == "Échec. mkdir, out : existe déjà."
    out = "a\nbackup.sh: line 7: cd: /var/backups/shop: Permission denied"
    assert resolve("bash backup.sh", 1, out, "en") == "Failed. backup.sh line 7: cd, /var/backups/shop: permission denied."


def test_script_raw_message_is_quoted_cut_on_words():
    out = "a\nunary.sh: line 2: [: 3: unary operator expected"
    assert resolve("bash unary.sh", 2, out, "en") == "Failed. unary.sh line 2: [: 3: unary operator expected."
    fr = f"a\nunary.sh: ligne 2{NB}: [: 3 : opérateur unaire attendu"
    assert resolve("bash unary.sh", 2, fr) == "Échec. unary.sh ligne 2 : [: 3 : opérateur unaire attendu."


def test_script_french_message_is_not_read_in_an_english_sentence():
    # piège D6 : sortie en locale fr_FR, session anglaise ; le modèle garde le message
    out = "a\n./planning.sh: ligne 11 : [: 3 : opérateur unaire attendu"
    assert resolve("./planning.sh", 2, out, "en") is None


@pytest.mark.parametrize("cmd, code, out", [
    ("bash ok.sh", 0, "backup.sh: line 7: cd: /x: Permission denied\nok"),  # succès : au modèle
    ("bash run.sh", 4, "48 réservations traitées, total 2287"),  # aucune erreur lisible
    ("bash run.sh | tee log", 1, "a\nrun.sh: line 3: X: unbound variable"),  # tube
    # une autre source que le script lancé (fichier sourcé) : doute
    ("bash main.sh", 1, "a\nlib.sh: line 3: X: unbound variable"),
    ("bash x.sh", 1, "a\ngrep: warning: stray \\ before -"),  # outil hors de la liste
])
def test_script_error_stays_silent_when_unsure(cmd, code, out):
    assert resolve(cmd, code, out) is None


# ---------------------------------------------------------------- _verbose_count

def test_rm_verbose_counts_and_names_the_common_folder():
    en = "\n".join(f"removed 'cache/obj_{i:03}.cache'" for i in range(70))
    fr = "\n".join(f"'cache/obj_{i:03}.cache' supprimé" for i in range(70))
    assert resolve("rm -v cache/*", 0, en, "en") == "70 items removed in cache."
    assert resolve("rm -v cache/*", 0, fr) == "70 éléments supprimés dans cache."
    mixed = "removed 'f1'\nremoved 'f2'\nremoved directory 'd1'"
    assert resolve("rm -rv f1 f2 d1", 0, mixed, "en") == "3 items removed."
    assert resolve("rm -v f1", 0, "'f1' supprimé\n'f2' supprimé\nrépertoire 'd1' supprimé") == \
        "3 éléments supprimés."


def test_mkdir_verbose_old_and_new_french_forms():
    en = "\n".join(f"mkdir: created directory 'p/src/m_{i}'" for i in range(3))
    assert resolve("mkdir -pv p/src/m_0 p/src/m_1 p/src/m_2", 0, en, "en") == "3 directories created in p/src."
    old = "mkdir: création du répertoire '2024'\nmkdir: création du répertoire '2024/janvier'\n" \
          "mkdir: création du répertoire '2025'"
    assert resolve("mkdir -pv 2024/janvier 2025", 0, old) == "3 dossiers créés, dont 2024 et 2025."
    new = "mkdir: répertoire 'a' créé\nmkdir: répertoire 'a/b' créé\nmkdir: répertoire 'a/c' créé"
    assert resolve("mkdir -pv a/b a/c", 0, new) == "3 dossiers créés, dont a."


def test_split_verbose_names_first_and_last():
    fr = "\n".join(f"création du fichier 'partie_{i:02}'" for i in range(40))
    assert resolve("split -n 40 -d --verbose lignes.txt partie_", 0, fr) == \
        "40 fichiers créés, de partie_00 à partie_39."
    en = "creating file 'part_00'"
    assert resolve("split --verbose -n 1 a part_", 0, en, "en") == "1 file created: part_00."


def test_chmod_verbose_says_count_and_single_new_mode():
    fr = "\n".join(f"le mode de 'b/f{i}' a été modifié de 0644 (rw-r--r--) en 0640 (rw-r-----)" for i in range(39))
    assert resolve("chmod -Rv 640 b", 0, fr) == "Droits modifiés sur 39 éléments, mode 640."
    en = ("mode of 'out' changed from 0755 (rwxr-xr-x) to 0750 (rwxr-x---)\n"
          "mode of 'out/a' changed from 0600 (rw-------) to 0640 (rw-r-----)\n"
          "mode of 'out/b' retained as 0640 (rw-r-----)")
    assert resolve("chmod -Rv u=rwX,g=rX,o= out", 0, en, "en") == "Mode changed on 2 items, 1 unchanged."
    kept = "le mode de 'a' a été conservé à 0640 (rw-r-----)"
    assert resolve("chmod -v 640 a", 0, kept + "\n" + kept.replace("'a'", "'b'")) == \
        "Droits inchangés sur 2 éléments."


def test_chown_and_chgrp_verbose():
    fr = "\n".join(f"appartenance de 'r/f{i}' modifiée de root:root en nobody:nogroup" for i in range(27))
    assert resolve("chown -Rv nobody:nogroup r", 0, fr) == "Propriétaire changé sur 27 éléments, désormais nobody:nogroup."
    en = "changed ownership of 'a' from root:root to nobody:nogroup\nchanged ownership of 'b' from root:root to nobody:nogroup"
    assert resolve("chown -c nobody:nogroup a b", 0, en, "en") == "Owner changed on 2 items, now nobody:nogroup."
    grp = "changed group of 'a' from root to staff\ngroup of 'b' retained as staff"
    assert resolve("chgrp -v staff a b", 0, grp, "en") == "Group changed on 1 item, now staff, 1 unchanged."
    assert resolve("chgrp -v nogroup a", 0, "le groupe de 'a' est maintenu à nogroup") == "Groupe inchangé sur 1 élément."


def test_cp_ln_mv_verbose():
    cp = "'part_00' -> 'out/part_00'\n'part_01' -> 'out/part_01'"
    assert resolve("cp -v part_00 part_01 out/", 0, cp) == "2 éléments copiés vers out."
    tree = ("'src' -> 'out/copie'\n'src/sub' -> 'out/copie/sub'\n'src/sub/b.py' -> 'out/copie/sub/b.py'\n"
            "'src/a.py' -> 'out/copie/a.py'")
    assert resolve("cp -rv src out/copie", 0, tree, "en") == "4 items copied to out/copie."
    ln = "\n".join(f"'./c_{i:02}.txt' -> '../docs/c_{i:02}.txt'" for i in range(60))
    assert resolve("ln -sv ../docs/c_*.txt .", 0, ln) == "60 liens créés."
    assert resolve("mv -v part_02 out/", 0, "renamed 'part_02' -> 'out/part_02'", "en") == "1 item moved to out."
    assert resolve("mv -v part_02 out/", 0, "'part_02' <-> 'out/part_02' renommé") == "1 élément déplacé vers out."


def test_shred_verbose_counts_files_and_passes():
    fr = "\n".join(f"shred: cache_{i}.tmp{NB}: étape {p}/2 (random)…" for i in range(13) for p in (1, 2))
    assert resolve("shred -v -n 2 cache_*.tmp", 0, fr) == "13 fichiers écrasés, dont cache_0.tmp, 2 passes chacun."
    en = ("shred: s2: pass 1/2 (random)...\nshred: s2: pass 2/2 (000000)...\nshred: s2: removing\n"
          "shred: s2: renamed to 00\nshred: 00: renamed to 0\nshred: s2: removed\n"
          "shred: s3: pass 1/2 (random)...\nshred: s3: pass 2/2 (000000)...\nshred: s3: removing\n"
          "shred: s3: removed")
    assert resolve("shred -vzu -n 1 s2 s3", 0, en, "en") == \
        "2 files shredded and removed, including s2, 2 passes each."


def test_tar_verbose_create_and_extract():
    gnu = "src/\nsrc/c.py\nsrc/a.py\nsrc/sub/\nsrc/sub/b.py"
    assert resolve("tar -czvf ../tree.tgz src", 0, gnu) == "5 éléments archivés dans tree.tgz."
    assert resolve("tar -xzvf ../tree.tgz -C out", 0, gnu, "en") == "5 items extracted from tree.tgz."
    bsd = "a .\na ./tests\na ./tests/file_01.py"
    assert resolve("tar -czvf ../tree.tgz .", 0, bsd, "en") == "3 items archived in tree.tgz."
    assert resolve("tar --create --verbose --file=b.tar src", 0, gnu) == "5 éléments archivés dans b.tar."


@pytest.mark.parametrize("cmd, code, out", [
    ("rm -v a b | tee log", 0, "removed 'a'\nremoved 'b'"),  # tube
    ("rm -v a b && ls", 0, "removed 'a'\nremoved 'b'\nc"),  # chaîne
    ("rm -v a b", 0, "a\nb"),  # rm -v de macOS : chemin seul, rien de sûr
    ("mkdir -v a", 0, "a"),
    ("chmod -v 640 a", 0, "mode of 'a' changed from 0644 (rw-r--r--) to 0640 (rw-r-----)\nwarning: x"),
    ("tar -tvf a.tar", 0, "src/\nsrc/a.py"),  # liste : pas une création
    ("tar -czvf a.tgz /src", 0, "tar: Removing leading `/' from member names\n/src/\n/src/a.py"),
    ("cp -v a b", 0, "'a' -> 'b'\nremoved 'b~'"),
])
def test_verbose_count_stays_silent_when_unsure(cmd, code, out):
    assert resolve(cmd, code, out) is None


# ---------------------------------------------------------------- _checksum

def test_checksum_all_ok():
    out = "\n".join(f"f{i}: OK" for i in range(12))
    assert resolve("sha256sum -c SUMS", 0, out, "en") == "12 files checked, all OK."
    fr = "\n".join(f"f{i}: Réussi" for i in range(12))
    assert resolve("sha256sum --check SUMS", 0, fr) == "12 fichiers vérifiés, tous conformes."


def test_checksum_failures_use_the_tool_counts_and_names():
    fr = ("c1: Réussi\nc2: Échec\nsha256sum: c3: Aucun fichier ou dossier de ce nom\n"
          "c3: Échec d'ouverture ou de lecture\n"
          f"sha256sum: Attention{NB}: 1 fichier de la liste n'a pas pu être lu\n"
          f"sha256sum: Attention{NB}: 1 somme de contrôle ne correspond pas")
    assert resolve("sha256sum -c sums", 1, fr) == \
        "Échec. 1 somme de contrôle ne correspond pas : c2, 1 fichier illisible : c3, 1 fichier conforme."
    en = ("c1: OK\nc2: FAILED\nsha256sum: c3: No such file or directory\nc3: FAILED open or read\n"
          "sha256sum: WARNING: 1 listed file could not be read\nsha256sum: WARNING: 1 computed checksum did NOT match")
    assert resolve("sha256sum -c sums", 1, en, "en") == \
        "Failed. 1 checksum did not match: c2, 1 file could not be read: c3, 1 file OK."


def test_checksum_counts_come_from_the_warning_when_lines_are_cut():
    # sortie coupée par tail : seuls les avertissements donnent les comptes
    out = ("site/index.html: Échec\nsite/p1.html: Réussi\n"
           "sha512sum: Attention : 3 sommes de contrôle ne correspondent pas")
    assert resolve("sha512sum -c SUMS 2>&1 | tail -n 70", 0, out) == \
        "3 sommes de contrôle ne correspondent pas, dont site/index.html."
    warn = ("a: Réussi\nmd5sum: Attention : 2 fichiers de la liste n'ont pas pu être lus\n"
            "md5sum: Attention : 1 somme de contrôle ne correspond pas")
    assert resolve("md5sum -c controle.md5", 1, warn) == \
        "Échec. 1 somme de contrôle ne correspond pas, 2 fichiers illisibles, 1 fichier conforme."


@pytest.mark.parametrize("cmd, code, out", [
    ("md5sum -c sums", 1, "md5sum: sums: no properly formatted checksum lines found"),
    ("sha256sum a b", 0, "e3b0  a\n1234  b"),  # calcul, pas vérification
    ("sha256sum -c s", 1, "a: OK\nsha256sum: WARNING: 1 line is improperly formatted"),
])
def test_checksum_stays_silent_when_unsure(cmd, code, out):
    assert resolve(cmd, code, out) is None


# ---------------------------------------------------------------- _grep_count

def test_grep_recursive_counts_lines_and_files():
    out = "src/a.py:1:a TODO x\nsrc/a.py:3:TODO y\nsrc/sub/b.py:1:TODO z"
    assert resolve("grep -rn TODO src", 0, out) == "3 lignes contiennent TODO, dans 2 fichiers, dont 2 dans src/a.py."
    assert resolve("grep -r TODO src", 0, out.replace(":1:", ":").replace(":3:", ":"), "en") == \
        "3 lines match TODO, in 2 files, 2 in src/a.py."
    one = "src/a.py:1:a TODO x\nsrc/a.py:3:TODO y"
    assert resolve("grep -rn TODO src", 0, one) == "2 lignes contiennent TODO, toutes dans src/a.py."


def test_grep_count_and_list_modes():
    counts = "src/c.py:0\nsrc/a.py:2\nsrc/sub/b.py:1"
    assert resolve("grep -rc TODO src", 0, counts) == \
        "3 lignes contiennent TODO, dans 2 fichiers sur 3, dont 2 dans src/a.py."
    assert resolve("grep -rl TODO src", 0, "src/a.py\nsrc/sub/b.py", "en") == "2 files match TODO, including src/a.py."


def test_grep_regex_pattern_is_not_read_aloud():
    out = "src/a.py:1:TODO\nsrc/b.py:2:FIXME"
    assert resolve("grep -rnE 'TODO|FIXME' src", 0, out) == "2 lignes trouvées, dans 2 fichiers, dont 1 dans src/a.py."


@pytest.mark.parametrize("cmd, out", [
    ("grep -n TODO src/a.py", "1:a TODO x\n3:TODO y\n4:TODO"),  # un seul fichier : le contenu compte
    ("grep -rn TODO src | head", "src/a.py:1:x\nsrc/a.py:2:y\nsrc/b.py:1:z"),
    ("grep -rvn TODO src", "src/a.py:2:b\nsrc/a.py:4:c\nsrc/b.py:1:z"),
    ("grep -rno TODO src", "src/a.py:1:TODO\nsrc/a.py:1:TODO\nsrc/b.py:1:TODO"),
    ("grep -rn -C1 TODO src", "src/a.py-1-x\nsrc/a.py:2:TODO\nsrc/a.py-3-y"),
    ("grep -rn TODO src", "src/a.py:1:x\nBinary file src/b.bin matches\nsrc/c.py:1:y"),
    ("grep -rn TODO src", "src/a.py:1:x\ngrep: src/d: Permission denied\nsrc/c.py:1:y"),
    ("grep -rhn TODO src", "1:x\n2:y\n3:z"),
])
def test_grep_count_stays_silent_when_unsure(cmd, out):
    assert resolve(cmd, 0, out) is None


# ---------------------------------------------------------------- _diff_brief

def test_diff_brief_fr_and_en():
    fr = ("Seulement dans release-1.3: CHANGELOG.md\n"
          "Les fichiers release-1.3/firmware.bin et release-1.4/firmware.bin sont différents\n"
          "Seulement dans release-1.4: migrations\n"
          "Les fichiers release-1.3/src/routes.py et release-1.4/src/routes.py sont différents\n"
          "Les fichiers release-1.3/src/stock.py et release-1.4/src/stock.py sont différents")
    assert resolve("diff -rq release-1.3 release-1.4", 1, fr) == \
        ("3 fichiers diffèrent, dont firmware.bin. Seulement dans release-1.3 : CHANGELOG.md. "
         "Seulement dans release-1.4 : migrations.")
    en = "Only in r2: new\nOnly in r1: only\nFiles r1/src/s and r2/src/s differ\nFiles r1/x and r2/x differ"
    assert resolve("diff -rq r1 r2", 1, en, "en") == \
        "2 files differ: src/s and x. Only in r2: new. Only in r1: only."
    assert resolve("diff -q a/x b/x", 1, "Files a/x and b/x differ", "en") == "1 file differs: x."


def test_diff_brief_many_only_in_one_side():
    out = "\n".join(f"Only in new: f{i}" for i in range(5)) + "\nBinary files old/logo.png and new/logo.png differ"
    assert resolve("diff -rq old new", 1, out, "en") == "1 file differs: logo.png. Only in new: 5 items, including f0."


@pytest.mark.parametrize("cmd, code, out", [
    ("diff -u a b", 1, "--- a\n+++ b\n@@ -1 +1 @@\n-x\n+y"),
    ("diff -rq a b", 1, "Files a/x and b/x differ\nsomething else"),
])
def test_diff_brief_stays_silent_when_unsure(cmd, code, out):
    assert resolve(cmd, code, out) is None


# ---------------------------------------------------------------- _wc_total

def test_wc_total_with_largest_file():
    out = "   413 data/sales.csv\n  1289 data/stock.csv\n     5 data/suppliers.csv\n  1707 total"
    assert resolve("wc -l data/*.csv", 0, out) == "1707 lignes au total dans 3 fichiers, dont 1289 dans stock.csv."
    assert resolve("wc -w a b", 0, "100 a\n  6 b\n106 total", "en") == "106 words in 2 files, 100 in a."


@pytest.mark.parametrize("cmd, code, out", [
    ("wc a b", 0, " 1 2 3 a\n 1 2 3 b\n 2 4 6 total"),  # trois colonnes
    ("wc -l a b | sort -n", 0, " 3 a\n 5 b\n 8 total"),
])
def test_wc_total_stays_silent_when_unsure(cmd, code, out):
    assert resolve(cmd, code, out) is None


# ---------------------------------------------------------------- _rsync_summary

def test_rsync_summary_gnu_stats_and_openrsync():
    stats = ("\nNumber of files: 5 (reg: 3, dir: 2)\nNumber of regular files transferred: 3\n"
             "Total file size: 30 bytes\n\nsent 309 bytes  received 88 bytes  794.00 bytes/sec\n"
             "total size is 30  speedup is 0.08")
    assert resolve("rsync -a --stats src/ dst/", 0, stats) == \
        "Synchronisation terminée, 3 fichiers transférés, taille totale 30 octets."
    mac = ("Transfer starting: 77 files\n./\nassets/\n\nsent 29829 bytes  received 1634 bytes  2231418 bytes/sec\n"
           "total size is 23380  speedup is 0.74")
    assert resolve("rsync -av --delete ./ ../mirror/", 0, mac, "en") == \
        "Sync finished, 77 files in the transfer, total size 23380 bytes."
    plain = "sending incremental file list\na.py\n\nsent 306 bytes  received 85 bytes  782.00 bytes/sec\n" \
            "total size is 1,234,567  speedup is 0.08"
    assert resolve("rsync -av src/ dst/", 0, plain) == "Synchronisation terminée, taille totale 1234567 octets."


def test_rsync_summary_stays_silent_on_failure_or_human_sizes():
    out = "sent 30 bytes  received 8 bytes  7.00 bytes/sec\ntotal size is 23.38K  speedup is 0.74"
    assert resolve("rsync -avh a/ b/", 0, out) is None
    assert resolve("rsync -av a/ b/", 23, "sent 30 bytes  received 8 bytes\ntotal size is 30  speedup is 1") is None
