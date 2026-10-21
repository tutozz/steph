"""B8b : téléchargement lisible au lecteur d'écran (lignes, pas de barre en \\r)."""

import hashlib
import http.server
import threading
import time

import pytest

from steph import fetch

# ------------------------------------------------------------ logique pure


def test_lines_every_ten_percent_with_remaining_time():
    p = fetch.Progress("Modèle", total=1000, start_bytes=0, language="fr", now=0.0)
    lines, spoken = p.update(95, now=10.0)
    assert lines == []
    lines, spoken = p.update(210, now=20.0)
    # 10 % puis 20 % franchis d'un coup : une seule ligne, la plus récente (débit 10,5 o/s -> 75 s)
    assert lines == ["Modèle : 20 %, reste environ 1 minute."]
    assert spoken == []


def test_speech_every_quarter_only():
    p = fetch.Progress("Modèle", total=1000, start_bytes=0, language="fr", now=0.0)
    lines, spoken = p.update(260, now=26.0)
    assert len(lines) == 1 and len(spoken) == 1 and spoken[0].startswith("Modèle : 25 %")
    lines, spoken = p.update(760, now=76.0)
    assert [s.split(" %")[0] for s in spoken] == ["Modèle : 75"]  # une seule annonce, la plus récente
    lines, spoken = p.update(1000, now=100.0)
    assert lines[-1].startswith("Modèle : 90 %") and not any("100" in s for s in lines)


def test_remaining_time_wording():
    assert fetch.remaining(3 * 60 + 20, "fr") == "3 minutes"
    assert fetch.remaining(70, "fr") == "1 minute"
    assert fetch.remaining(42, "fr") == "40 secondes"
    assert fetch.remaining(2, "fr") == "10 secondes"
    assert fetch.remaining(600, "en") == "10 minutes"


def test_resume_counts_speed_from_new_bytes_only():
    p = fetch.Progress("Modèle", total=1000, start_bytes=500, language="fr", now=0.0)
    lines, _ = p.update(600, now=10.0)
    # 100 octets en 10 s depuis la reprise : 400 restants -> 40 s
    assert lines == ["Modèle : 60 %, reste environ 40 secondes."]


def test_unknown_size_gives_a_line_every_30_seconds():
    p = fetch.Progress("Modèle", total=None, start_bytes=0, language="fr", now=0.0)
    assert p.update(5 << 20, now=10.0) == ([], [])
    lines, _ = p.update(12 << 20, now=31.0)
    assert lines == ["Modèle : 12 Mo reçus."]


def test_english_lines():
    p = fetch.Progress("Model", total=100, start_bytes=0, language="en", now=0.0)
    lines, _ = p.update(10, now=10.0)
    assert lines == ["Model: 10%, about 2 minutes left."]


# ------------------------------------------------------------ vrai téléchargement, faux serveur lent


PAYLOAD = bytes(range(256)) * 4096  # 1 Mio


class SlowHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _range_start(self):
        r = self.headers.get("Range", "")
        return int(r.split("=")[1].split("-")[0]) if r.startswith("bytes=") else 0

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-Length", str(len(PAYLOAD)))
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()

    def do_GET(self):
        start = self._range_start()
        body = PAYLOAD[start:]
        self.send_response(206 if start else 200)
        self.send_header("Content-Length", str(len(body)))
        if start:
            self.send_header("Content-Range", f"bytes {start}-{len(PAYLOAD) - 1}/{len(PAYLOAD)}")
        self.end_headers()
        step = len(PAYLOAD) // 40
        for i in range(0, len(body), step):
            self.wfile.write(body[i:i + step])
            self.wfile.flush()
            time.sleep(0.05)


@pytest.fixture
def server():
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), SlowHandler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}/model.gguf"
    httpd.shutdown()


def test_real_download_prints_plain_lines(server, tmp_path, capsys):
    dest = tmp_path / "model.gguf"
    assert fetch.main(["--label", "Modèle", "--poll", "0.05", server, str(dest)]) == 0
    assert dest.read_bytes() == PAYLOAD
    assert not (tmp_path / "model.gguf.part").exists()
    out = capsys.readouterr().out
    assert "\r" not in out
    lines = out.splitlines()
    assert sum(1 for line in lines if " %, reste environ " in line) >= 5
    assert lines[-1] == "Modèle : téléchargé."


def test_real_download_resumes_a_partial_file(server, tmp_path, capsys):
    dest = tmp_path / "model.gguf"
    (tmp_path / "model.gguf.part").write_bytes(PAYLOAD[:600_000])
    assert fetch.main(["--label", "Modèle", "--poll", "0.05", server, str(dest)]) == 0
    assert dest.read_bytes() == PAYLOAD


def test_unreachable_server_fails_with_a_clear_line(tmp_path, capsys):
    dest = tmp_path / "model.gguf"
    assert fetch.main(["--label", "Modèle", "--poll", "0.05", "--retries", "0",
                       "http://127.0.0.1:9/absent", str(dest)]) != 0
    assert not dest.exists()
    assert "reprendra" in capsys.readouterr().out


def test_fast_download_prints_no_intermediate_line(server, tmp_path, capsys, monkeypatch):
    """Un fichier reçu entre deux relevés : seulement « téléchargé », pas neuf lignes d'un coup."""
    dest = tmp_path / "model.gguf"
    assert fetch.main(["--label", "llama.cpp", "--poll", "5", server, str(dest)]) == 0
    assert capsys.readouterr().out.splitlines() == ["llama.cpp : téléchargé."]


def test_speech_is_journaled_even_when_voice_is_muted(server, tmp_path, monkeypatch, capsys):
    log = tmp_path / "speech.log"
    monkeypatch.setenv("STEPH_TTS_ENABLED", "0")
    monkeypatch.setenv("STEPH_SPEECH_LOG", str(log))
    monkeypatch.setenv("STEPH_VOICE", str(tmp_path / "absent.onnx"))
    assert fetch.main(["--label", "Modèle", "--speak", "--poll", "0.05", server, str(tmp_path / "m.gguf")]) == 0
    spoken = log.read_text()
    assert "Modèle : " in spoken and "téléchargé" in spoken


# ------------------------------------------------------------ empreinte sha256


def test_matching_sha256_keeps_the_file(server, tmp_path):
    dest = tmp_path / "model.gguf"
    digest = hashlib.sha256(PAYLOAD).hexdigest()
    assert fetch.main(["--label", "Modèle", "--poll", "5", "--sha256", digest, server, str(dest)]) == 0
    assert dest.read_bytes() == PAYLOAD


def test_wrong_sha256_fails_and_leaves_nothing(server, tmp_path, capsys):
    dest = tmp_path / "model.gguf"
    assert fetch.main(["--label", "Modèle", "--poll", "5", "--sha256", "0" * 64, server, str(dest)]) != 0
    assert not dest.exists()
    assert not (tmp_path / "model.gguf.part").exists()
    assert "empreinte" in capsys.readouterr().out
