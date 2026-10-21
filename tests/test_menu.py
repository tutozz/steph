"""Menu parlé (F6) : machine à états pure, sans E/S."""

import pytest

from steph import menu
from steph.config import Config


def make_menu(tmp_path, voices=("fr_FR-siwis-medium", "fr_FR-tom-medium")):
    vdir = tmp_path / "voices"
    vdir.mkdir(exist_ok=True)
    for v in voices:
        (vdir / f"{v}.onnx").write_bytes(b"")
    cfg = Config()
    if voices:
        cfg.voice = str(vdir / f"{voices[0]}.onnx")
    return menu.Menu(cfg, help_text="F7 questions, F8 silence.", voices_dir=vdir)


# ------------------------------------------------------------ ouverture


def test_opening_announcement_names_first_item_and_count(tmp_path):
    m = make_menu(tmp_path)
    text = m.opening_announcement()
    assert text.startswith("Menu steph. Couper la parole. ")
    assert text.endswith("9 éléments.")


# ------------------------------------------------------------ navigation


def test_down_moves_and_speaks_next_label(tmp_path):
    m = make_menu(tmp_path)
    r = m.handle(menu.DOWN[0])
    assert r.say == "Répéter"
    assert not r.closed


def test_navigation_loops_at_both_ends(tmp_path):
    m = make_menu(tmp_path)
    r = m.handle(menu.UP[0])  # de l'élément 0, vers le haut : boucle sur le dernier
    assert r.say == "Fermer le menu"
    # puis vers le bas : revient au premier
    r = m.handle(menu.DOWN[0])
    assert r.say == "Couper la parole"


def test_alternate_arrow_sequences_are_accepted(tmp_path):
    m = make_menu(tmp_path)
    r = m.handle(menu.DOWN[1])  # \x1bOB
    assert r.say == "Répéter"


# ------------------------------------------------------------ actions (niveau principal)


def test_enter_on_action_returns_action_and_closes(tmp_path):
    m = make_menu(tmp_path)
    r = m.handle(menu.ENTER)
    assert r.action == "stop"
    assert r.closed


def test_all_main_actions_in_order(tmp_path):
    expected = ["stop", "repeat", "details", "ask", "first", "last"]
    for i, action in enumerate(expected):
        m = make_menu(tmp_path)
        for _ in range(i):
            m.handle(menu.DOWN[0])
        r = m.handle(menu.ENTER)
        assert r.action == action
        assert r.closed


def test_help_entry_speaks_help_text_and_does_not_close(tmp_path):
    m = make_menu(tmp_path)
    for _ in range(7):  # index 7 : Aide des touches
        m.handle(menu.DOWN[0])
    r = m.handle(menu.ENTER)
    assert r.say == "F7 questions, F8 silence."
    assert not r.closed


def test_close_entry_says_menu_closed(tmp_path):
    m = make_menu(tmp_path)
    for _ in range(8):  # index 8 : Fermer le menu
        m.handle(menu.DOWN[0])
    r = m.handle(menu.ENTER)
    assert r.say == "Menu fermé."
    assert r.closed


def test_escape_closes_from_anywhere(tmp_path):
    m = make_menu(tmp_path)
    m.handle(menu.DOWN[0])
    r = m.handle(menu.ESCAPE)
    assert r.say == "Menu fermé."
    assert r.closed


def test_f6_key_closes_the_menu(tmp_path):
    m = make_menu(tmp_path)
    r = m.handle(m.cfg.key_menu.encode())
    assert r.closed
    assert r.say == "Menu fermé."


# ------------------------------------------------------------ sous-menu réglages


def enter_settings(m):
    for _ in range(6):  # index 6 : Réglages
        m.handle(menu.DOWN[0])
    return m.handle(menu.ENTER)


def test_settings_submenu_announces_first_item(tmp_path):
    m = make_menu(tmp_path)
    r = enter_settings(m)
    assert r.say.startswith("Réglages. Voix : activée. ")
    assert r.say.endswith("6 éléments.")
    assert not r.closed


def test_backspace_returns_to_parent_and_speaks_its_item(tmp_path):
    m = make_menu(tmp_path)
    enter_settings(m)
    r = m.handle(menu.BACKSPACE)
    assert r.say == "Réglages"
    assert not r.closed


def test_back_entry_returns_to_parent(tmp_path):
    m = make_menu(tmp_path)
    enter_settings(m)
    for _ in range(5):  # index 5 : Retour
        m.handle(menu.DOWN[0])
    r = m.handle(menu.ENTER)
    assert r.say == "Réglages"
    assert not r.closed


def test_left_on_non_adjustable_entry_in_submenu_goes_back(tmp_path):
    m = make_menu(tmp_path)
    enter_settings(m)
    for _ in range(5):  # index 5 : Retour, pas de réglage
        m.handle(menu.DOWN[0])
    r = m.handle(menu.LEFT[0])
    assert r.say == "Réglages"


def test_left_at_top_level_is_a_noop(tmp_path):
    m = make_menu(tmp_path)
    r = m.handle(menu.LEFT[0])
    assert r.say is None
    assert r.action is None
    assert not r.closed


def test_backspace_at_top_level_is_a_noop(tmp_path):
    m = make_menu(tmp_path)
    r = m.handle(menu.BACKSPACE)
    assert r.say is None
    assert not r.closed


# ------------------------------------------------------------ réglage : voix (bascule)


def test_toggle_voice_enter_applies_immediately_and_returns_setting(tmp_path):
    m = make_menu(tmp_path)
    enter_settings(m)
    r = m.handle(menu.ENTER)
    assert r.say == "Voix coupée."
    assert r.setting == ("tts_enabled", False)
    assert m.cfg.tts_enabled is False


def test_toggle_voice_twice_returns_to_enabled(tmp_path):
    m = make_menu(tmp_path)
    enter_settings(m)
    m.handle(menu.ENTER)
    r = m.handle(menu.ENTER)
    assert r.say == "Voix activée."
    assert r.setting == ("tts_enabled", True)


def test_left_and_right_also_toggle_voice(tmp_path):
    m = make_menu(tmp_path)
    enter_settings(m)
    r = m.handle(menu.LEFT[0])
    assert r.setting == ("tts_enabled", False)
    r = m.handle(menu.RIGHT[0])
    assert r.setting == ("tts_enabled", True)


# ------------------------------------------------------------ réglage : débit


def goto_rate(m):
    enter_settings(m)
    m.handle(menu.DOWN[0])  # index 1 : Débit de parole


def test_rate_label_uses_french_decimal_comma(tmp_path):
    m = make_menu(tmp_path)
    m.cfg.speech_rate = 1.25
    goto_rate(m)
    r = m.handle(menu.RIGHT[0])
    assert "1,5" in r.say
    assert r.setting == ("speech_rate", 1.5)


def test_rate_is_bounded_low(tmp_path):
    m = make_menu(tmp_path)
    m.cfg.speech_rate = 0.5
    goto_rate(m)
    r = m.handle(menu.LEFT[0])
    assert r.setting == ("speech_rate", 0.5)


def test_rate_is_bounded_high(tmp_path):
    m = make_menu(tmp_path)
    m.cfg.speech_rate = 3.0
    goto_rate(m)
    r = m.handle(menu.RIGHT[0])
    assert r.setting == ("speech_rate", 3.0)


def test_rate_enter_increments_like_right(tmp_path):
    m = make_menu(tmp_path)
    m.cfg.speech_rate = 1.0
    goto_rate(m)
    r = m.handle(menu.ENTER)
    assert r.setting == ("speech_rate", 1.25)


# ------------------------------------------------------------ réglage : verbosité


def goto_verbosity(m):
    enter_settings(m)
    for _ in range(2):
        m.handle(menu.DOWN[0])  # index 2 : Verbosité


def test_verbosity_labels_and_bounds(tmp_path):
    m = make_menu(tmp_path)
    m.cfg.verbosity = 0
    goto_verbosity(m)
    r = m.handle(menu.LEFT[0])
    assert r.setting == ("verbosity", 0)
    r = m.handle(menu.RIGHT[0])
    assert r.say == "Verbosité bref."
    assert r.setting == ("verbosity", 1)
    r = m.handle(menu.RIGHT[0])
    assert r.say == "Verbosité détaillé."
    r = m.handle(menu.RIGHT[0])
    assert r.setting == ("verbosity", 2)  # plafonné


# ------------------------------------------------------------ réglage : annoncer cd


def goto_announce_cd(m):
    enter_settings(m)
    for _ in range(3):
        m.handle(menu.DOWN[0])  # index 3


def test_announce_cd_toggle(tmp_path):
    m = make_menu(tmp_path)
    m.cfg.announce_cd = True
    goto_announce_cd(m)
    r = m.handle(menu.ENTER)
    assert r.setting == ("announce_cd", False)
    assert m.cfg.announce_cd is False


# ------------------------------------------------------------ réglage : voix de synthèse


def goto_voice_choice(m):
    enter_settings(m)
    for _ in range(4):
        m.handle(menu.DOWN[0])  # index 4


def test_voice_cycle_moves_to_next_voice(tmp_path):
    m = make_menu(tmp_path)
    goto_voice_choice(m)
    r = m.handle(menu.RIGHT[0])
    assert "tom medium" in r.say
    assert r.setting[0] == "voice"
    assert "fr_FR-tom-medium.onnx" in r.setting[1]


def test_voice_cycle_wraps_around(tmp_path):
    m = make_menu(tmp_path)
    goto_voice_choice(m)
    m.handle(menu.RIGHT[0])
    r = m.handle(menu.RIGHT[0])
    assert "siwis medium" in r.say


def test_single_voice_says_only_one_installed(tmp_path):
    m = make_menu(tmp_path, voices=("fr_FR-siwis-medium",))
    goto_voice_choice(m)
    r = m.handle(menu.RIGHT[0])
    assert r.say == "Une seule voix installée."
    assert r.setting is None


def test_no_voice_says_only_one_installed(tmp_path):
    m = make_menu(tmp_path, voices=())
    goto_voice_choice(m)
    r = m.handle(menu.RIGHT[0])
    assert r.say == "Une seule voix installée."


# ------------------------------------------------------------ split_keys


def test_split_keys_separates_sequences_and_single_bytes(tmp_path):
    data = b"a" + menu.DOWN[0] + b"\r" + menu.ESCAPE
    assert menu.split_keys(data) == [b"a", menu.DOWN[0], b"\r", menu.ESCAPE]


def test_split_keys_handles_bare_escape_at_end(tmp_path):
    assert menu.split_keys(b"\x1b") == [b"\x1b"]


def test_split_keys_keeps_ss3_arrows_whole(tmp_path):
    # mode curseur applicatif (zle, vim…) : les flèches arrivent en ESC O A
    data = menu.UP[1] + menu.DOWN[1] + b"\x1bOP"
    assert menu.split_keys(data) == [menu.UP[1], menu.DOWN[1], b"\x1bOP"]


def test_split_keys_handles_f6_sequence(tmp_path):
    cfg = Config()
    assert menu.split_keys(cfg.key_menu.encode()) == [cfg.key_menu.encode()]


# ------------------------------------------------------------ rendu


def _screen(raw: bytes, rows=24, cols=80):
    import pyte

    s = pyte.Screen(cols, rows)
    pyte.ByteStream(s).feed(raw)
    return s


def _screen_feed(s, raw: bytes):
    import pyte

    pyte.ByteStream(s).feed(raw)


def _lines(s):
    return [line.rstrip() for line in s.display]


def test_render_truncates_to_width(tmp_path):
    m = make_menu(tmp_path)
    for line in _lines(_screen(m.render(24, 10), cols=10)):
        assert len(line) <= 10


def test_render_contains_title_and_help_and_reverse_video(tmp_path):
    m = make_menu(tmp_path)
    out = m.render(24, 80)
    text = _lines(_screen(out))
    assert text[0].startswith(" steph ›  Menu")
    assert text[2] == "Actions"
    assert b"naviguer" in out
    assert b"\x1b[7m" in out and b"\x1b[27m" in out
    assert b"\x1b[2J\x1b[H" in out


def test_render_moves_reverse_video_when_cursor_moves(tmp_path):
    m = make_menu(tmp_path)
    m.handle(menu.DOWN[0])
    out = m.render(24, 80)
    text = out.decode()
    idx = text.index("\x1b[7m")
    assert "Répéter" in text[idx:idx + 40]


# ------------------------------------------------------------ M5 : charte dans le menu


def _styled_menu(tmp_path, depth="truecolor"):
    from steph.term_style import Style

    m = make_menu(tmp_path)
    m.style = Style(depth)
    return m


def test_styled_render_paints_the_screen_black_before_clearing(tmp_path):
    out = _styled_menu(tmp_path).render(24, 80)
    assert out.startswith(b"\x1b[?25l\x1b[48;2;11;11;11m\x1b[2J\x1b[H")


def test_styled_render_selects_in_black_on_lemon_without_reverse_video(tmp_path):
    m = _styled_menu(tmp_path)
    m.handle(menu.DOWN[0])
    text = m.render(24, 80).decode()
    assert "\x1b[7m" not in text
    assert "\x1b[1;38;2;11;11;11;48;2;226;255;59m› 2  Répéter" in text


def test_styled_render_title_offwhite_bold_items_offwhite_help_gray(tmp_path):
    text = _styled_menu(tmp_path).render(24, 80).decode()
    assert "\x1b[38;2;11;11;11;48;2;226;255;59m steph › \x1b[0m" in text
    assert "\x1b[1;38;2;244;244;240;48;2;11;11;11m Menu" in text
    assert "\x1b[38;2;244;244;240;48;2;11;11;11m  2  Répéter" in text
    assert "\x1b[38;2;138;138;133;48;2;11;11;11mFlèches" in text


def test_styled_render_reads_exactly_like_the_plain_render(tmp_path):
    plain = _lines(_screen(make_menu(tmp_path).render(24, 80)))
    styled = _lines(_screen(_styled_menu(tmp_path).render(24, 80)))
    assert styled == plain


def test_styled_render_still_truncates_to_width(tmp_path):
    for line in _lines(_screen(_styled_menu(tmp_path, "256").render(24, 10), cols=10)):
        assert len(line) <= 10


# ------------------------------------------------------------ M6 : focus, description, rendu partiel


def test_render_leaves_the_visible_cursor_on_the_focused_item(tmp_path):
    m = make_menu(tmp_path)
    m.handle(menu.DOWN[0])
    raw = m.render(24, 80)
    s = _screen(raw)
    assert s.cursor.y == 5 and _lines(s)[5].startswith("› 2  Répéter")
    assert raw.endswith(b"\x1b[?25h")


def test_render_describes_the_focused_item(tmp_path):
    m = make_menu(tmp_path)
    assert "Arrête la phrase en cours." in "\n".join(_lines(_screen(m.render(24, 80))))


def test_update_after_a_move_rewrites_description_and_two_lines_only(tmp_path):
    m = make_menu(tmp_path)
    s = _screen(m.render(24, 80))
    before = _lines(s)
    m.handle(menu.DOWN[0])
    update = m.render_update(24, 80)
    assert b"\x1b[2J" not in update
    _screen_feed(s, update)
    after = _lines(s)
    changed = {i for i in range(24) if before[i] != after[i]}
    assert changed <= {4, 5, 19, 20, 21}
    assert "Redit la dernière annonce." in "\n".join(after)
    assert s.cursor.y == 5


def test_update_after_a_setting_rewrites_only_that_line(tmp_path):
    m = make_menu(tmp_path)
    for _ in range(6):
        m.handle(menu.DOWN[0])
    m.handle(menu.ENTER)  # Réglages : nouveau niveau, redessin complet
    assert b"\x1b[2J" in m.render_update(24, 80)
    m.handle(menu.RIGHT[0])  # voix coupée
    update = m.render_update(24, 80)
    assert b"\x1b[2J" not in update and update.count(b"\x1b[2K") == 1
    assert "Voix : coupée".encode() in update


def test_update_without_change_writes_nothing(tmp_path):
    m = make_menu(tmp_path)
    m.render(24, 80)
    m.handle(b"x")
    assert m.render_update(24, 80) == b""


def test_update_after_resize_redraws_everything(tmp_path):
    m = make_menu(tmp_path)
    m.render(24, 80)
    m.handle(menu.DOWN[0])
    assert b"\x1b[2J" in m.render_update(30, 100)


def test_settings_screen_is_titled_and_says_its_adjust_hint(tmp_path):
    m = make_menu(tmp_path)
    for _ in range(6):
        m.handle(menu.DOWN[0])
    m.handle(menu.ENTER)
    text = "\n".join(_lines(_screen(m.render(24, 80))))
    assert "Réglages" in text and "Gauche ou droite pour régler" in text


@pytest.mark.parametrize("key, index, label", [
    (b"3", 2, "Détails de la dernière commande"), (b"\t", 1, "Répéter"), (b"\x1b[Z", 8, "Fermer le menu"),
    (b"\x1b[F", 8, "Fermer le menu"), (b"9", 8, "Fermer le menu"),
])
def test_digits_tab_and_end_move_the_focus(tmp_path, key, index, label):
    m = make_menu(tmp_path)
    r = m.handle(key)
    assert m.cursor == index and r.say == label


def test_home_goes_to_the_first_item(tmp_path):
    m = make_menu(tmp_path)
    m.handle(b"5")
    assert m.handle(b"\x1b[H").say == "Couper la parole" and m.cursor == 0


def test_question_mark_says_the_key_help(tmp_path):
    m = make_menu(tmp_path)
    r = m.handle(b"?")
    assert r.say == "F7 questions, F8 silence." and not r.closed


def test_digit_beyond_the_list_does_nothing(tmp_path):
    m = make_menu(tmp_path)
    for _ in range(6):
        m.handle(menu.DOWN[0])
    m.handle(menu.ENTER)  # Réglages : 6 éléments
    assert m.handle(b"7").say is None and m.cursor == 0


# ------------------------------------------------------------ B8b : anglais, bornes partagées


def test_menu_speaks_english_when_language_is_en(tmp_path):
    m = make_menu(tmp_path)
    m.cfg.language = "en"
    assert m.opening_announcement() == "steph menu. Stop speech. 9 items."
    assert m.handle(menu.DOWN[0]).say == "Repeat"
    for _ in range(5):
        m.handle(menu.DOWN[0])
    r = m.handle(menu.ENTER)  # Réglages / Settings
    assert r.say.startswith("Settings. Voice: on.")
    m.handle(menu.DOWN[0])
    r = m.handle(menu.RIGHT[0])
    assert r.say == "Rate 1.5."
    assert b"Arrows: move" in m.render(24, 80)


def test_menu_rate_bounds_come_from_setup():
    from steph import setup

    assert (menu.RATE_MIN, menu.RATE_MAX) == (setup.RATE_MIN, setup.RATE_MAX)
    assert menu.RATE_MIN is setup.RATE_MIN and menu.RATE_MAX is setup.RATE_MAX
