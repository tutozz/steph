import re

from steph.proxy import overlay_off, overlay_on


def test_overlay_on_sets_window_title_to_steph_without_a_keys_list():
    seq = overlay_on()
    assert seq == b"\x1b[22;0t\x1b]0;steph\x07"
    assert b"\x1b[22;0t" in seq  # titre d'origine sauvegardé


def test_overlay_on_never_emits_a_non_empty_badge():
    seq = overlay_on()
    for m in re.finditer(rb"\x1b\]1337;SetBadgeFormat=([^\x07]*)\x07", seq):
        assert m.group(1) == b""  # échouerait si un badge (même vide au format) portait du texte


def test_overlay_off_clears_a_leftover_badge_and_restores_title():
    seq = overlay_off()
    assert b"\x1b]1337;SetBadgeFormat=\x07" in seq  # efface un badge d'une version antérieure
    assert b"\x1b[23;0t" in seq
