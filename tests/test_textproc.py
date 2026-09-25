from steph.textproc import OutputCleaner, detect_percent, detect_stage, looks_like_prompt, compact_output
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
    assert parse_ps_wchan(" 4242 R+ -\n", 4242) is False
    assert parse_ps_wchan(out, 1) is None
