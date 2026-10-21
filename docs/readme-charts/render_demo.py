"""Renders assets/demo-{fr,en}.{gif,mp4}: what steph really says, with the delivered small model.

    uv run --with playwright python docs/readme-charts/render_demo.py [fr] [en]

Texts come from docs/readme-charts/answers.small.json (field `said`, production phrases) and the
apt upgrade (fx24) and failed npm build (fx27) raw fixtures of bench/fixtures.json (indexes 24 and 27). Voice: Piper at steph's default speech rate (1.25,
length_scale 0.8), no post-processing of the audio. FR uses the installed fr_FR-siwis-medium;
EN has no steph voice, so en_US-lessac-medium is downloaded to a scratch folder.
Frames: Chrome driven by Playwright (system Chrome, no browser download), page in the steph charter.
Assembly: ffmpeg (mp4 H.264 + AAC, GIF with an optimised palette).
"""

import html
import json
import re
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

from playwright.sync_api import sync_playwright

from steph.tts import normalize_for_speech, trim_leading_silence
from steph.pronounce import to_piper

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "assets"
WORK = Path(tempfile.gettempdir()) / "steph-demo-render"
W, H = 960, 600
SPEECH_RATE = 1.25
GIF_FPS = 10
VOICES = {
    "fr": Path.home() / ".local/share/steph/voices/fr_FR-siwis-medium.onnx",
    "en": WORK / "voices/en_US-lessac-medium.onnx",
}
FONTS_URL = json.loads((ROOT / "docs/design/tokens.json").read_text())["font"]["google_fonts_url"]
ANSWERS = {r["fixture"]: r for r in json.loads((ROOT / "docs/readme-charts/answers.small.json").read_text())["rows"]}
RAW = json.loads((ROOT / "bench/fixtures.json").read_text()) + json.loads((ROOT / "bench/extra_fixtures.json").read_text())
INDEX = {"fx24": 24, "fx27": 27}


def fixture(fx: str) -> tuple[str, list[str]]:
    case = RAW[INDEX[fx]]
    return case["cmd"], case["output"].splitlines()


STEPS = ("fx24", "fx27")

COPY = {
    "fr": {
        "said": {"fx24": ANSWERS["fx24"]["said"], "fx27": ANSWERS["fx27"]["said"]}, "qa": "qa_pip", "question": "Quelle version de requests a été installée ?",
        "more": "… {n} lignes de plus", "session": "session :", "lang_attr": "fr",
        "alt": "Démo : steph dit une phrase pour apt upgrade, puis pour un build en échec, puis répond à une question sur la session.",
    },
    "en": {
        "said": {"fx24": "12 packages upgraded.",
                 "fx27": "Failed. Header.tsx line 42: Property titel does not exist on type Props. Did you mean title?"}, "qa": "qa_pip_en", "question": "Which version of requests was installed?",
        "more": "… {n} more lines", "session": "session:", "lang_attr": "en",
        "alt": "Demo: steph says one sentence for apt upgrade, then for a failed build, then answers a question about the session.",
    },
}

CSS = """
* { box-sizing: border-box; }
html, body { margin: 0; width: %(w)dpx; height: %(h)dpx; overflow: hidden; }
body { background-color: #0b0b0b;
  background-image: linear-gradient(#1a1a1a 1px, transparent 1px), linear-gradient(90deg, #1a1a1a 1px, transparent 1px);
  background-size: 32px 32px; color: #f4f4f0; font-family: "Space Grotesk", system-ui, sans-serif;
  -webkit-font-smoothing: antialiased; padding: 24px; display: flex; flex-direction: column; gap: 16px; }
.term { background: #262626; padding: 20px 24px; height: 268px; font-family: "JetBrains Mono", monospace;
  font-size: 19px; line-height: 1.45; color: #cfcfca; font-feature-settings: "calt" 0, "liga" 0; overflow: hidden; }
.term .cmd { color: #f4f4f0; font-weight: 500; }
.term .out { margin-top: 8px; overflow-wrap: anywhere; }
.term .out div { margin-bottom: 4px; }
.term .more { margin-top: 10px; }
.term .sess { margin-bottom: 14px; }
.cursor { display: inline-block; width: 10px; height: 22px; background: #f4f4f0; vertical-align: -4px; margin-left: 2px; }
.steph { border: 2px solid #e2ff3b; height: 268px; padding: 18px 24px; background: #0b0b0b; }
.steph.idle { border-color: #3a3a37; }
.label { font-family: "JetBrains Mono", monospace; font-size: 19px; font-weight: 600; color: #e2ff3b; display: flex;
  align-items: center; gap: 12px; margin-bottom: 10px; }
.idle .label { color: #8a8a85; }
.bars { display: inline-flex; gap: 4px; align-items: center; height: 22px; }
.bars i { display: block; width: 5px; background: #e2ff3b; }
.say { font-size: 26px; line-height: 1.38; font-weight: 500; color: #e2ff3b; letter-spacing: -0.01em; }
""" % {"w": W, "h": H}


def segments(text: str) -> list[str]:
    """Clause-sized pieces, as steph speaks them; short pieces join the next one."""
    parts = re.split(r"(?<=[,;:])\s+", text.strip())
    out: list[str] = []
    carry = ""
    for p in parts:
        p = (carry + " " + p).strip() if carry else p
        if len(p) < 25 and p is not parts[-1]:
            carry = p
            continue
        carry = ""
        out.append(p)
    if carry:
        out.append(carry)
    return out


def load_voice(lang: str):
    from piper import PiperVoice
    path = VOICES[lang]
    if not path.exists():
        from piper.download_voices import download_voice
        path.parent.mkdir(parents=True, exist_ok=True)
        download_voice(path.stem, path.parent)
    return PiperVoice.load(str(path))


def synth(voice, lang: str, text: str) -> tuple[bytes, int]:
    from piper import SynthesisConfig
    spoken = to_piper(normalize_for_speech(text)) if lang == "fr" else text
    syn = SynthesisConfig(length_scale=1.0 / SPEECH_RATE)
    chunks = list(voice.synthesize(spoken, syn_config=syn))
    rate = chunks[0].sample_rate
    return trim_leading_silence(b"".join(c.audio_int16_bytes for c in chunks), rate), rate


def bars(level: int) -> str:
    heights = [(8, 16, 22, 12), (18, 10, 14, 22), (12, 22, 8, 16)][level % 3]
    return '<span class="bars">' + "".join(f'<i style="height:{h}px"></i>' for h in heights) + "</span>"


def term_html(lang: str, cmd: str, out_lines: list[str], extra: int, cursor: bool, session: str = "") -> str:
    c = COPY[lang]
    cur = '<span class="cursor"></span>' if cursor else ""
    body = f'<div class="sess">{html.escape(c["session"])} {html.escape(session)}</div>' if session else ""
    body += f'<div><span class="cmd">$ {html.escape(cmd)}</span>{cur}</div>'
    if out_lines:
        body += '<div class="out">' + "".join(f"<div>{html.escape(l)}</div>" for l in out_lines)
        if extra:
            body += f'<div class="more">{html.escape(c["more"].format(n=extra))}</div>'
        body += "</div>"
    return f'<div class="term">{body}</div>'


def steph_html(text: str, speaking: int | None) -> str:
    if speaking is None:
        return '<div class="steph idle"><div class="label">steph</div></div>'
    return f'<div class="steph"><div class="label">steph {bars(speaking) if speaking >= 0 else ""}</div><div class="say">{html.escape(text)}</div></div>'


def build_scenes(lang: str, voice) -> tuple[list[tuple[str, float]], bytes, int]:
    """Returns [(body_html, seconds)], the PCM track and its rate. Timing follows the real audio length."""
    c = COPY[lang]
    frames: list[tuple[str, float]] = []
    pcm = bytearray()
    rate = 22050

    def at_end_pad(seconds: float) -> None:
        pcm.extend(b"\0\0" * int(rate * seconds))

    def add(term: str, steph: str, seconds: float, silent: bool = True) -> None:
        frames.append((term + steph, seconds))
        if silent:
            at_end_pad(seconds)

    def speak(term: str, text: str) -> None:
        nonlocal rate
        shown = ""
        for i, seg in enumerate(segments(text)):
            audio, rate = synth(voice, lang, seg)
            shown = (shown + " " + seg).strip()
            frames.append((term + steph_html(shown, i), len(audio) / 2 / rate))
            pcm.extend(audio)

    for fx in STEPS:
        cmd, lines = fixture(fx)
        shown, extra = lines[:4], len(lines) - 4  # raw output, blank lines included
        said = c["said"][fx]
        add(term_html(lang, "", [], 0, True), steph_html("", None), 0.9 if fx == STEPS[0] else 0.5)
        for n in range(1, len(cmd) + 1, 2):
            add(term_html(lang, cmd[:n], [], 0, True), steph_html("", None), 0.1)
        add(term_html(lang, cmd, [], 0, False), steph_html("", None), 0.4)
        t1 = term_html(lang, cmd, shown, extra, False)
        add(t1, steph_html("", None), 0.7)
        speak(t1, said)
        add(t1, steph_html(said, -1), 1.6)

    session = ", ".join(ANSWERS[c["qa"]]["session"])
    q = "q " + c["question"]
    add(term_html(lang, "", [], 0, True, session), steph_html("", None), 0.8)
    for n in range(3, len(q) + 3, 3):
        add(term_html(lang, q[:n], [], 0, True, session), steph_html("", None), 0.12)
    add(term_html(lang, q, [], 0, False, session), steph_html("", None), 0.7)
    t2 = term_html(lang, q, [], 0, False, session)
    answer = ANSWERS[c["qa"]]["said"]
    speak(t2, answer)
    add(t2, steph_html(answer, -1), 2.2)
    return frames, bytes(pcm), rate


def render_frames(frames: list[tuple[str, float]], lang: str, out: Path) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    base = (f'<!doctype html><html lang="{lang}"><head><meta charset="utf-8"><link rel="stylesheet" href="{FONTS_URL}">'
            f"<style>{CSS}</style></head><body></body></html>")
    page_file = out / "base.html"
    page_file.write_text(base)
    paths: list[Path] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome")
        try:
            page = browser.new_page(viewport={"width": W, "height": H})
            page.goto(page_file.as_uri(), wait_until="networkidle")
            page.evaluate("document.fonts.load('26px \"Space Grotesk\"')")
            page.evaluate("document.fonts.load('19px \"JetBrains Mono\"')")
            page.evaluate("document.fonts.ready")
            for i, (body, _) in enumerate(frames):
                page.evaluate("b => { document.body.innerHTML = b; }", body)
                p = out / f"f{i:03d}.png"
                page.screenshot(path=str(p))
                paths.append(p)
        finally:
            browser.close()
    return paths


def assemble(lang: str, paths: list[Path], frames: list[tuple[str, float]], pcm: bytes, rate: int) -> None:
    d = paths[0].parent
    wav = d / "audio.wav"
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    lst = d / "list.txt"
    seq = "".join(f"file '{p.name}'\nduration {dur:.4f}\n" for p, (_, dur) in zip(paths, frames))
    lst.write_text(seq + f"file '{paths[-1].name}'\n")
    total = sum(dur for _, dur in frames)
    mp4 = ASSETS / f"demo-{lang}.mp4"
    gif = ASSETS / f"demo-{lang}.gif"
    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-i", str(wav),
         "-r", "25", "-c:v", "libx264", "-preset", "slow", "-crf", "23", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "96k",
         "-t", f"{total:.3f}", "-movflags", "+faststart", str(mp4)])
    pal = d / "palette.png"
    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-vf",
         f"fps={GIF_FPS},scale=800:-1:flags=lanczos,palettegen=max_colors=32:stats_mode=diff", "-t", f"{total:.3f}", str(pal)])
    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-i", str(pal), "-lavfi",
         f"fps={GIF_FPS},scale=800:-1:flags=lanczos[x];[x][1:v]paletteuse=dither=none:diff_mode=rectangle", "-t",
         f"{total:.3f}", "-loop", "0", str(gif)])
    print(lang, f"{total:.1f}s", mp4.stat().st_size, gif.stat().st_size)


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def main() -> int:
    langs = [a for a in sys.argv[1:] if a in COPY] or list(COPY)
    for lang in langs:
        voice = load_voice(lang)
        frames, pcm, rate = build_scenes(lang, voice)
        paths = render_frames(frames, lang, WORK / lang)
        assemble(lang, paths, frames, pcm, rate)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
