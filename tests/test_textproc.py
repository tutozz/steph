from steph.textproc import (
    OutputCleaner,
    compact_output,
    compact_table,
    dedupe_lines,
    detect_percent,
    detect_stage,
    looks_like_prompt,
    strip_noise,
)
from steph.proxy import MarkerParser


def feed(*chunks):
    c = OutputCleaner()
    for ch in chunks:
        c.feed(ch.encode() if isinstance(ch, str) else ch)
    return c


def test_colors_and_cr():
    c = feed("\x1b[1;31mErreur\x1b[0m : x\r\n", "10%\r50%\r100% fini\n")
    assert c.lines == ["Erreur : x", "100% fini"]


def test_erase_line_progress():
    c = feed("Téléchargement 10%", "\r\x1b[K", "Téléchargement 90%")
    assert c.partial == "Téléchargement 90%"
    assert detect_percent(c.partial) == 90


def test_apt_status_line():
    c = feed("Dépaquetage de curl (7.88) ...\n", "\x1b7\x1b[24;0f\x1b[42m", "Progress: [ 45%]", "\x1b[49m\x1b8")
    assert c.status.startswith("Progress: [ 45%]")
    assert c.lines == ["Dépaquetage de curl (7.88) ..."]
    assert detect_percent(c.status) == 45


def test_fullscreen():
    c = feed("\x1b[?1049h", "vim stuff", "\x1b[?1049l")
    assert not c.fullscreen


def test_utf8_split():
    b = "é".encode()
    c = feed(b"caf" + b[:1], b[1:] + b"\n")
    assert c.lines == ["café"]


def test_stage():
    assert detect_stage("Paramétrage de curl (7.88.1) ...") == "configuration de curl"
    assert detect_stage("Unpacking libssl3:amd64 (3.0) over (3.0)") == "décompression de libssl3"
    assert detect_stage("Receiving objects:  45% (450/1000)") == "réception des objets"
    assert detect_stage("  Downloading requests-2.32.3-py3-none-any.whl (64 kB)").startswith("téléchargement de requests")
    assert detect_stage("[ 3/12] Installing vim-common-9.1  100%") is not None


def test_prompt():
    assert looks_like_prompt("Souhaitez-vous continuer ? [O/n] ")
    assert looks_like_prompt("[sudo] Mot de passe de luis : ")
    assert not looks_like_prompt("Compilation de foo.c")


def test_markers_split():
    p = MarkerParser()
    out = p.feed(b"abc\x1b]69") + p.feed(b"73;C;bHM=\x07def")
    assert ("marker", "C;bHM=") in out
    assert b"".join(v for k, v in out if k == "data") == b"abcdef"


def test_compact():
    lines = [f"ligne {i}" for i in range(5000)]
    lines[2500] = "error: disque plein"
    s = compact_output(lines, 3000)
    assert "disque plein" in s and len(s) <= 3100


def test_apt_get_line():
    assert detect_stage("Réception de :3 http://deb.debian.org/debian bookworm/main amd64 curl amd64 7.88.1 [315 kB]") == "téléchargement de curl"
    assert detect_stage("Get:1 http://deb.debian.org/debian bookworm InRelease [151 kB]") == "lecture des index de bookworm"


def test_macos_ps_probe():
    from steph.ttyprobe import parse_ps_wchan
    out = "  501 Ss   -\n 4242 S+   ttyin\n 4242 S+   -\n 9999 R    -\n"
    assert parse_ps_wchan(out, 4242) is True
    assert parse_ps_wchan(" 4242 S+ -\n", 4242) is None
    assert parse_ps_wchan(out, 1) is None


# ---------------------------------------------------------------- dedupe_lines

def test_dedupe_lines_collapses_consecutive_repeats():
    assert dedupe_lines(["a", "b", "b", "b", "c"]) == ["a", "b (×3)", "c"]


def test_dedupe_lines_keeps_single_occurrences():
    assert dedupe_lines(["a", "b", "c"]) == ["a", "b", "c"]


def test_dedupe_lines_does_not_merge_non_consecutive_repeats():
    assert dedupe_lines(["a", "b", "a"]) == ["a", "b", "a"]


def test_dedupe_lines_groups_same_message_with_a_changing_timestamp():
    # cas réel fx08 (journal pipewire) : même message, horodatage différent
    lines = [
        "sept. 23 09:58:56 devbox pipewire[7126]: mod.raop-sink: latence non entière",
        "sept. 23 12:05:00 devbox pipewire[7126]: mod.raop-sink: latence non entière",
    ]
    out = dedupe_lines(lines)
    assert out == ["sept. 23 09:58:56 devbox pipewire[7126]: mod.raop-sink: latence non entière (×2)"]


def test_dedupe_lines_keeps_distinct_messages_even_with_shared_date():
    lines = [f"2026-09-27 erreur n°{i} : disque {i} en panne" for i in range(3)]
    assert dedupe_lines(lines) == lines


# ---------------------------------------------------------------- strip_noise

def test_strip_noise_drops_separator_lines():
    assert strip_noise(["avant", "----------", "====", "après"]) == ["avant", "après"]


def test_strip_noise_drops_progress_bars_and_percent_only_lines():
    lines = ["Téléchargement", "[#####-----] 45%", "100 %", "fini"]
    assert strip_noise(lines) == ["Téléchargement", "fini"]


def test_strip_noise_keeps_real_content_with_punctuation():
    lines = ["Erreur : ---- config manquante ----", "a == b"]
    assert strip_noise(lines) == lines


# ---------------------------------------------------------------- compact_table

def test_compact_table_collapses_padding_between_columns():
    lines = [
        "curl.x86_64                1:8.5.0-1     updates",
        "vim.x86_64                 2:9.1-1       updates",
        "zsh.x86_64                 5.9-1         updates",
    ]
    assert compact_table(lines) == [
        "curl.x86_64 1:8.5.0-1 updates",
        "vim.x86_64 2:9.1-1 updates",
        "zsh.x86_64 5.9-1 updates",
    ]


def test_compact_table_drops_column_blank_on_every_row():
    lines = [
        "NAME    PORTS    STATUS",
        "web     8080     up",
        "db                up",
        "cache             up",
    ]
    # PORTS n'est pas vide sur toutes les lignes (web l'a) : gardée
    assert compact_table(lines)[0].split() == ["NAME", "PORTS", "STATUS"]


def test_compact_table_ignores_short_or_irregular_input():
    lines = ["une ligne", "une autre"]
    assert compact_table(lines) == lines


# ---------------------------------------------------------------- compact_output integration

def test_compact_output_applies_noise_removal_and_dedupe():
    lines = ["debut", "[#####-----] 45%", "log identique", "log identique", "fin"]
    out = compact_output(lines, 3000)
    assert out == "debut\nlog identique (×2)\nfin"


# ---------------------------------------------------------------- flux_window (journaux en continu, H1 #9)
from steph.textproc import flux_window  # noqa: E402


def test_flux_window_reports_only_new_errors_and_warnings():
    lines = [
        "2026-09-27T10:00:01 app[1]: request GET /health 200",
        "2026-09-27T10:00:02 app[1]: request GET /status 200",
        "2026-09-27T10:00:03 app[1]: ERROR connection refused to db:5432",
        "2026-09-27T10:00:04 app[1]: request GET /health 200",
        "2026-09-27T10:00:05 app[1]: WARNING slow query 812ms",
    ]
    out = flux_window(lines)
    assert out.startswith("5 nouvelles lignes, 1 erreur, 1 avertissement :")
    assert "ERROR connection refused to db:5432" in out
    assert "WARNING slow query 812ms" in out
    assert "GET /health 200" not in out


def test_flux_window_silent_when_nothing_notable():
    lines = [f"2026-09-27T10:00:0{i} app[1]: request GET /health 200" for i in range(5)]
    assert flux_window(lines) == "5 nouvelles lignes, rien de notable."


def test_flux_window_empty_window():
    assert flux_window([]) == ""


def test_flux_window_dedupes_repeated_alerts():
    lines = ["ERROR db timeout"] * 4 + ["all good"]
    out = flux_window(lines)
    assert out == "5 nouvelles lignes, 4 erreurs :\nERROR db timeout (×4)"
