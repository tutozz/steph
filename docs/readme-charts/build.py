"""Render the README charts of the fine-tuned model from data.json, in the steph charter v1.

    python3 docs/readme-charts/build.py            # check sources, write HTML, render PNG, write alt.json
    python3 docs/readme-charts/build.py --check    # only check data.json against the bench files
    python3 docs/readme-charts/build.py --html     # write HTML only, no Chrome

Output: docs/readme-charts/src/<chart>.<lang>.html, assets/charts/<chart>.<lang>.<theme>.png
(800 CSS px wide at a device scale factor of 2, height fitted to the content) and
docs/readme-charts/alt.json (alt text and equivalent table for every image).

The charter is dark only: the light and dark files are the same image, kept under both
names so the README <picture> blocks need no change.
A value whose status is not "measured" is never drawn as a number: it becomes a hatched
bar labelled "à remplir" / "to be filled".
"""

import html
import json
import math
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SRC = HERE / "src"
OUT = ROOT / "assets" / "charts"
ALT = HERE / "alt.json"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
SCRATCH = Path(tempfile.gettempdir())
WIDTH = 800
MAX_HEIGHT = 1600
CROP_KEY = (255, 0, 255)  # page background outside the card, cropped away after the screenshot
FONTS = ("https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;700"
         "&family=JetBrains+Mono:wght@400;500;600;700&display=block")
THEMES = ("light", "dark")

sys.path.insert(0, str(ROOT / "bench" / "matrix"))
from score import score_result  # noqa: E402

DATA = json.loads((HERE / "data.json").read_text())
VALUES = DATA["values"]
MODELS = DATA["models"]


# ---------- data ----------

def check_sources() -> list[str]:
    errors = []
    for key, v in VALUES.items():
        d = v.get("derive")
        if not d or v["status"] != "measured":
            continue
        path = ROOT / d["file"]
        if "score" in d:
            split = {"quality_cleaned": "all", "holdout": "holdout", "n": "all"}[d["score"]]
            res = score_result(str(path), cleaned=True, split=split)
            got = res["n"] if d["score"] == "n" else res["quality"]
        else:
            got = json.loads(path.read_text())
            for part in d["field"].split("."):
                got = got[part]
        ok = d["contains"] in got if "contains" in d else math.isclose(float(got), float(v["value"]), abs_tol=0.05)
        if not ok:
            errors.append(f"{key}: data.json {v['value']!r}, {d['file']} gives {got!r}")
    ex = DATA["example"]["raw"]
    rows = json.loads((ROOT / ex["source"]).read_text())["rows"]
    out = next(r["out"] for r in rows if r["fixture"] == DATA["example"]["fixture"])
    if out.strip() != ex["text"]:
        errors.append(f"example.raw: data.json {ex['text']!r}, source gives {out!r}")
    return errors


def measured(key: str) -> bool:
    return VALUES[key]["status"] == "measured"


def esc(s) -> str:
    return html.escape(str(s))


class Chart:
    def __init__(self, lang: str):
        self.lang = lang
        self.alt = ""
        self.table: list[list[str]] = []

    def t(self, fr: str, en: str) -> str:
        return fr if self.lang == "fr" else en

    @property
    def todo(self) -> str:
        return self.t("à remplir", "to be filled")

    def num(self, x: float, digits: int = 1) -> str:
        s = f"{x:,.{digits}f}"
        if self.lang == "fr":
            s = s.replace(",", " ").replace(".", ",")
        return s

    def fmt(self, key: str, unit: str, digits: int = 1) -> str:
        """Formatted value, or the pending label when the value is not measured."""
        if not measured(key):
            return self.todo
        x = float(VALUES[key]["value"])
        if unit == "":
            return self.num(x, digits)
        if unit == "%":
            return self.num(x, digits) + (" %" if self.lang == "fr" else "%")
        if unit == "s":
            return self.num(x, digits) + " s"
        if unit == "MB":
            return self.num(x, 0) + self.t(" Mo", " MB")
        return self.num(x, digits)

    def label(self, model: str) -> str:
        return MODELS[model]["label"]

    def sub(self, model: str) -> str:
        m = MODELS[model]
        return m["sub_fr"] if self.lang == "fr" else m["sub_en"]


def name_html(c: Chart, model: str) -> str:
    sub = c.sub(model)
    return esc(c.label(model)) + (f" <small>{esc(sub)}</small>" if sub else "")


def bars(c: Chart, rows: list[tuple[str, str]], unit: str, scale: float, ticks: tuple[str, str, str],
         width: int = 500, digits: int = 1) -> str:
    """Horizontal bars from zero. rows: (model, value key). steph-speak is the lemon row."""
    out = []
    for model, key in rows:
        cls = "row hero" if model.startswith("steph") else "row"
        if measured(key):
            w = max(2, round(width * float(VALUES[key]["value"]) / scale))
            mark = f'<div class="bar" style="width:{w}px"></div><span class="val">{c.fmt(key, unit, digits)}</span>'
        else:
            mark = f'<div class="pending" style="width:{round(width * 0.45)}px">{c.todo}</div>'
        out.append(f'<div class="{cls}"><div class="name">{name_html(c, model)}</div><div class="track">{mark}</div></div>')
    marks = "".join(f'<span class="tk" style="left:{width * i // 2}px"><i></i><b>{t}</b></span>' for i, t in enumerate(ticks))
    return (f'<div class="rows axis">{"".join(out)}</div>'
            f'<div class="ticks" style="width:{width}px">{marks}</div>')


def model_line(c: Chart, model: str) -> str:
    sub = c.sub(model)
    return c.label(model) + (f" ({sub})" if sub else "")


# ---------- charts ----------

BENCH_NOTE_FR = "Banc v3, jeu de test caché de {n} cas, 3 graines."
BENCH_NOTE_EN = "Bench v3, hidden test set of {n} cases, 3 seeds."


def bench_note(c: Chart) -> str:
    n = c.num(VALUES["bench3.n"]["value"], 0)
    return c.t(BENCH_NOTE_FR, BENCH_NOTE_EN).format(n=n)


def hero(c: Chart) -> str:
    models = [("steph_small", "steph_small"), ("steph_base", "steph_base"), ("gemma4_e2b", "gemma4_e2b")]
    q = [(m, f"quality.{k}") for m, k in models]
    d = [(m, f"disk_mb.{k}") for m, k in models if m != "gemma4_e2b"] + [("gemma4_e2b", "disk_mb.gemma4_e2b")]
    unit = c.t("Mo", "MB")
    c.alt = c.t(
        "Les deux modèles steph-speak face à Gemma 4 E2B brut. Qualité au banc : "
        + ", ".join(f"{model_line(c, m)} {c.fmt(k, '', 1)}" for m, k in q)
        + ". Taille sur disque : " + ", ".join(f"{model_line(c, m)} {c.fmt(k, 'MB')}" for m, k in d) + ".",
        "The two steph-speak models against raw Gemma 4 E2B. Bench quality: "
        + ", ".join(f"{model_line(c, m)} {c.fmt(k, '', 1)}" for m, k in q)
        + ". Size on disk: " + ", ".join(f"{model_line(c, m)} {c.fmt(k, 'MB')}" for m, k in d) + ".")
    c.table = [[c.t("Modèle", "Model"), c.t("Qualité au banc", "Bench quality"), c.t("Taille sur disque", "Size on disk")]]
    c.table += [[model_line(c, m), c.fmt(qk, ""), c.fmt(dk, "MB")] for (m, qk), (_, dk) in zip(q, d)]
    return f"""
<span class="tag">{c.t("Les modèles steph-speak", "The steph-speak models")}</span>
<h1>{c.t("Deux modèles,<br><em>un par machine.</em>", "Two models,<br><em>one per machine.</em>")}</h1>
<div class="chart">
  <div class="group">{c.t("Qualité au banc", "Bench quality")}</div>
  <p class="sub" style="margin-top:0">{c.t("Sur 100. Plus haut, c'est mieux.", "Out of 100. Higher is better.")}</p>
  {bars(c, q, "", 100, ("0", "50", "100"))}
  <div class="sep"></div>
  <div class="group">{c.t("Taille sur disque", "Size on disk")}</div>
  <p class="sub" style="margin-top:0">{c.t(f"Fichier GGUF, en {unit}. Plus petit, c'est mieux.", f"GGUF file, in {unit}. Smaller is better.")}</p>
  {bars(c, d, "MB", 4000, ("0", c.num(2000, 0), f"{c.num(4000, 0)} {unit}"))}
</div>
<p class="foot">{bench_note(c)}</p>"""


def quality(c: Chart) -> str:
    rows = [("steph_base", "quality.steph_base"), ("gemma4_e2b", "quality.gemma4_e2b"), ("steph_small", "quality.steph_small")]
    inv = [("steph_base", "invent.steph_base"), ("gemma4_e2b", "invent.gemma4_e2b"), ("steph_small", "invent.steph_small")]
    c.alt = c.t(
        f"Qualité au banc v3, sur {c.num(VALUES['bench3.n']['value'], 0)} cas de test : "
        + ", ".join(f"{model_line(c, m)} {c.fmt(k, '')}" for m, k in rows)
        + ". Réponses avec une invention, en pourcentage : "
        + ", ".join(f"{model_line(c, m)} {c.fmt(k, '%')}" for m, k in inv) + ".",
        f"Bench v3 quality, over {c.num(VALUES['bench3.n']['value'], 0)} test cases: "
        + ", ".join(f"{model_line(c, m)} {c.fmt(k, '')}" for m, k in rows)
        + ". Answers with an invention, in percent: "
        + ", ".join(f"{model_line(c, m)} {c.fmt(k, '%')}" for m, k in inv) + ".")
    c.table = [[c.t("Modèle", "Model"), c.t("Qualité", "Quality"), c.t("Inventions", "Inventions")]]
    c.table += [[model_line(c, m), c.fmt(k, ""), c.fmt(ik, "%")] for (m, k), (_, ik) in zip(rows, inv)]
    return f"""
<span class="tag">{c.t("Qualité au banc", "Bench quality")}</span>
<h1>{c.t("Dire l'essentiel,<br><em>sans rien inventer.</em>", "Saying what matters,<br><em>inventing nothing.</em>")}</h1>
<div class="chart">
  <div class="group">{c.t("Qualité", "Quality")}</div>
  <p class="sub" style="margin-top:0">{c.t("Sur 100. Plus haut, c'est mieux.", "Out of 100. Higher is better.")}</p>
  {bars(c, rows, "", 100, ("0", "50", "100"))}
  <div class="sep"></div>
  <div class="group">{c.t("Réponses avec une invention", "Answers with an invention")}</div>
  <p class="sub" style="margin-top:0">{c.t("En %. Plus bas, c'est mieux.", "In %. Lower is better.")}</p>
  {bars(c, inv, "%", 40, ("0", "20", "40 %" if c.lang == "fr" else "40%"))}
</div>
<p class="foot">{bench_note(c)} {c.t("Inventions : juge Qwen3.5 9B.", "Inventions: Qwen3.5 9B judge.")}</p>"""


def speed(c: Chart) -> str:
    rows = [("steph_small", "ttft_p90_i5.steph_small"), ("qwen35_08b", "ttft_p90_i5.qwen35_08b"),
            ("qwen35_2b", "ttft_p90_i5.qwen35_2b"), ("smollm3_3b", "ttft_p90_i5.smollm3_3b"),
            ("ministral3_3b", "ttft_p90_i5.ministral3_3b"), ("steph_base", "ttft_p90_i5.steph_base")]
    rows.sort(key=lambda r: float(VALUES[r[1]]["value"]))
    mac = [("gemma4_e2b", "ttft_p90_mac.gemma4_e2b"), ("qwen35_9b", "ttft_p90_mac.qwen35_9b")]
    cpu, cores = VALUES["laptop.cpu"]["value"], VALUES["laptop.cores"]["value"]
    mac_txt = " · ".join(f"{esc(c.label(m))} {c.fmt(k, 's', 2)}" for m, k in mac)
    listing = ", ".join(f"{model_line(c, m)} {c.fmt(k, 's')}" for m, k in rows)
    mac_alt = ", ".join(f"{c.label(m)} {c.fmt(k, 's', 2)}" for m, k in mac)
    c.alt = c.t(
        f"Premier mot, 90e centile, en secondes, sur un portable {cpu} à {cores} cœurs, sans GPU : {listing}. "
        f"Sur Mac M3 Pro avec Metal : {mac_alt}.",
        f"First word, 90th percentile, in seconds, on a {cpu} laptop with {cores} cores, no GPU: {listing}. "
        f"On a Mac M3 Pro with Metal: {mac_alt}.")
    c.table = [[c.t("Modèle", "Model"), "i5-7200U", "Mac M3 Pro"]]
    mac_by = dict(mac)
    c.table += [[model_line(c, m), c.fmt(k, "s"), c.fmt(mac_by[m], "s", 2) if m in mac_by else ""] for m, k in rows]
    c.table += [[model_line(c, m), "", c.fmt(k, "s", 2)] for m, k in mac if m not in dict(rows)]
    return f"""
<span class="tag">{c.t("Premier mot", "First word")}</span>
<h1>{c.t("Le premier mot,<br><em>sur un portable sans GPU.</em>", "The first word,<br><em>on a laptop with no GPU.</em>")}</h1>
<div class="chart">
  <p class="sub" style="margin-top:0">{c.t(f"En secondes, 9 fois sur 10. Plus court, c'est mieux. {cpu}, {cores} cœurs, processeur seul.",
                                         f"In seconds, 9 times out of 10. Shorter is better. {cpu}, {cores} cores, CPU only.")}</p>
  <div style="margin-top:16px">{bars(c, rows, "s", 30, ("0", "15", "30 s"), digits=2)}</div>
</div>
<p class="foot">{c.t("Le petit modèle tient sur ce portable ; le modèle base est fait pour les machines plus rapides. Sur Mac M3 Pro (Metal) : ", "The small model fits this laptop; the base model is for faster machines. On a Mac M3 Pro (Metal): ")}{mac_txt}.</p>"""


def size(c: Chart) -> str:
    rows = [("steph_small", "disk_mb.steph_small"), ("steph_base", "disk_mb.steph_base"),
            ("gemma4_e2b", "disk_mb.gemma4_e2b"), ("qwen35_9b", "disk_mb.qwen35_9b")]
    where_i5 = "i5-7200U"
    ram = [("steph_small", "ram_mb.steph_small", where_i5), ("steph_base", "ram_mb.steph_base", where_i5),
           ("gemma4_e2b", "ram_mb.gemma4_e2b_i5", where_i5),
           ("qwen35_9b", "ram_mb.qwen35_9b", "Mac M3 Pro, Metal")]
    unit = c.t("Mo", "MB")
    ram_txt = " · ".join(f"{esc(model_line(c, m))} {c.fmt(k, 'MB')} ({esc(where)})" for m, k, where in ram)
    listing = ", ".join(f"{model_line(c, m)} {c.fmt(k, 'MB')}" for m, k in rows)
    ram_alt = ", ".join(f"{model_line(c, m)} {c.fmt(k, 'MB')}" for m, k, _ in ram)
    c.alt = c.t(f"Taille du fichier GGUF sur disque : {listing}. Mémoire au pic : {ram_alt}.",
                f"GGUF file size on disk: {listing}. Peak memory: {ram_alt}.")
    c.table = [[c.t("Modèle", "Model"), c.t("Taille sur disque", "Size on disk"), c.t("Mémoire au pic", "Peak memory")]]
    c.table += [[model_line(c, m), c.fmt(k, "MB"), c.fmt(rk, "MB")] for (m, k), (_, rk, _) in zip(rows, ram)]
    return f"""
<span class="tag">{c.t("Taille sur disque", "Size on disk")}</span>
<h1>{c.t("Ce que pèse le modèle<br><em>sur votre disque.</em>", "What the model weighs<br><em>on your disk.</em>")}</h1>
<div class="chart">
  <p class="sub" style="margin-top:0">{c.t(f"Fichier GGUF, en {unit}. Plus petit, c'est mieux.", f"GGUF file, in {unit}. Smaller is better.")}</p>
  <div style="margin-top:16px">{bars(c, rows, "MB", 6000, ("0", c.num(3000, 0), f"{c.num(6000, 0)} {unit}"))}</div>
</div>
<p class="foot">{c.t("Mémoire au pic : ", "Peak memory: ")}{ram_txt}</p>"""


def example(c: Chart) -> str:
    ex = DATA["example"]
    raw, ref = ex["raw"], ex["steph"]
    gloss = c.lang == "en"

    def quote(fr, en):
        q = c.t(f"« {esc(fr)} »", f"“{esc(fr)}”")
        return f'<div class="quote">{q}</div>' + (f'<div class="gloss">{esc(en)}</div>' if gloss else "")

    if not ref["text"] or not ref["text_en"]:
        raise SystemExit("data.json example.steph is empty: run the delivered model on the case first")
    c.alt = c.t(
        f"La commande {ex['command']} échoue : {ex['output']}. Qwen3.5 0.8B brut parle de Header.tsx, "
        f"un fichier absent de la sortie : « {raw['text']} » steph, par une règle écrite en code, dit : « {ref['text']} »",
        f"The command {ex['command']} fails: {ex['output_en']}. Raw Qwen3.5 0.8B talks about Header.tsx, "
        f"a file that is not in the output: “{raw['text_en']}” steph, by a rule written in code, says: “{ref['text_en']}”")
    c.table = [[c.t("Modèle", "Model"), c.t("Phrase dite", "Spoken sentence")],
               [c.t("Qwen3.5 0.8B, brut", "Qwen3.5 0.8B, raw"), raw["text"]],
               [c.t("steph, règle en code", "steph, rule in code"), ref["text"]]]
    ref_who = c.t("steph · règle écrite en code", "steph · rule written in code")
    return f"""
<span class="tag">{c.t("Avant, après", "Before, after")}</span>
<h1>{c.t("Une commande échoue.<br><em>Voici ce que vous entendez.</em>", "A command fails.<br><em>Here is what you hear.</em>")}</h1>
<div class="term">
  <div class="prompt"><span class="dollar">$ </span>{esc(ex["command"])}</div>
  <div class="dump">{esc(ex["output"])}</div>
  {f'<div class="dump gloss">{esc(ex["output_en"])}</div>' if gloss else ""}
</div>
<div class="pair">
  <div class="say raw">
    <div class="head">{c.t("Petit modèle brut", "Raw small model")} · {esc(MODELS[raw["model"]]["label"])}</div>
    {quote(raw["text"], raw["text_en"])}
    <div class="why">{c.t("Parle d'un fichier absent de la sortie.", "Talks about a file that is not in the output.")}</div>
  </div>
  <div class="say ref">
    <div class="head">{ref_who}</div>
    {quote(ref["text"], ref["text_en"])}
    <div class="why">{c.t("Nomme le fichier et la cause.", "Names the file and the cause.")}</div>
  </div>
</div>
<style>
.term {{ margin-top: 20px; padding: 16px 20px; background: var(--code-bg); border: 2px solid var(--stroke); font-family: var(--mono); }}
.prompt {{ font: 500 20px var(--mono); }}
.dollar {{ color: var(--lemon); }}
.dump {{ margin-top: 6px; font: 400 19px/1.45 var(--mono); color: var(--muted); }}
.gloss {{ margin-top: 4px; font: 400 19px/1.4 var(--sans); color: var(--muted); }}
.pair {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-top: 16px; }}
.say {{ padding: 20px; }}
.raw {{ background: var(--block); }}
.ref {{ background: var(--lemon); color: var(--black); }}
.head {{ font: 500 19px/1.35 var(--mono); }}
.raw .head, .raw .why {{ color: var(--muted); }}
.quote {{ margin-top: 10px; font: 500 24px/1.25 var(--sans); letter-spacing: -0.02em; }}
.ref .gloss, .ref .why {{ color: #2e2e2b; }}
.why {{ margin-top: 10px; font: 400 19px/1.4 var(--sans); }}
.final {{ display: flex; flex-wrap: wrap; align-items: center; gap: 8px 16px; margin-top: 16px; }}
.fh {{ font: 700 19px var(--mono); color: var(--lemon); }}
</style>"""


CHARTS = {"hero": hero, "quality": quality, "speed": speed, "size": size, "example": example}


# ---------- rendering ----------

def md_table(rows: list[list[str]]) -> str:
    head, *body = rows
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    lines += ["| " + " | ".join(r) + " |" for r in body]
    return "\n".join(lines).replace(" ", " ")


def page(body: str, lang: str, css: list[str]) -> str:
    links = "".join(f'<link rel="stylesheet" href="{h}">' for h in css)
    return f"""<!doctype html>
<html lang="{lang}"><head><meta charset="utf-8">
<link rel="stylesheet" href="{FONTS}">
{links}
<style>html, body {{ background: rgb{CROP_KEY}; }}</style>
</head><body><div class="card">{body}</div></body></html>
"""


def screenshot(html_path: Path, png_path: Path, width: int, height: int, profile: Path) -> None:
    # Chrome writes the screenshot but on this Mac its process does not always exit: wait for a stable file.
    png_path.unlink(missing_ok=True)
    proc = subprocess.Popen([CHROME, "--headless", f"--screenshot={png_path}", f"--window-size={width},{height}",
                             "--force-device-scale-factor=2", "--virtual-time-budget=15000", "--hide-scrollbars",
                             f"--user-data-dir={profile}", "--no-first-run", html_path.as_uri()],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    last, deadline = -1, time.monotonic() + 120
    try:
        while time.monotonic() < deadline:
            time.sleep(0.5)
            size = png_path.stat().st_size if png_path.exists() else -1
            if size > 0 and size == last:
                return
            if proc.poll() is not None and size <= 0:
                break
            last = size
        raise RuntimeError(f"no screenshot for {html_path.name}")
    finally:
        proc.kill()
        proc.wait()


def render(html_path: Path, png_path: Path, profile: Path) -> None:
    """Screenshot a tall window, then crop at the bottom of the card (first CROP_KEY row)."""
    screenshot(html_path, png_path, WIDTH, MAX_HEIGHT, profile)
    img = Image.open(png_path).convert("RGB")
    bottom = img.height
    for y in range(img.height):
        if img.getpixel((0, y)) == CROP_KEY:
            bottom = y
            break
    if bottom == img.height:
        raise RuntimeError(f"{html_path.name}: content taller than {MAX_HEIGHT} px")
    img.crop((0, 0, img.width, bottom)).save(png_path, optimize=True)


def write_alt(section: str, entries: dict) -> None:
    alt = json.loads(ALT.read_text()) if ALT.exists() else {}
    alt[section] = entries
    ALT.write_text(json.dumps(alt, ensure_ascii=False, indent=1) + "\n")


def main() -> int:
    errors = check_sources()
    for e in errors:
        print("MISMATCH", e)
    if errors:
        return 1
    if "--check" in sys.argv:
        print(f"data.json: {sum(measured(k) for k in VALUES)} measured, "
              f"{sum(not measured(k) for k in VALUES)} placeholder, sources match")
        return 0
    OUT.mkdir(parents=True, exist_ok=True)
    only = [a for a in sys.argv[1:] if a in CHARTS] or list(CHARTS)
    base = SCRATCH if SCRATCH.exists() else None
    profile = Path(tempfile.mkdtemp(prefix="chrome-profile-charts-", dir=base))
    alt = json.loads(ALT.read_text()).get("charts", {}) if ALT.exists() else {}
    try:
        for chart in only:
            for lang in ("fr", "en"):
                c = Chart(lang)
                body = CHARTS[chart](c)
                stem = f"{chart}.{lang}"
                html_path = SRC / f"{stem}.html"
                html_path.write_text(page(body, lang, ["charts.css"]))
                alt[stem] = {"alt": c.alt.replace(" ", " "), "table": md_table(c.table)}
                if "--html" not in sys.argv:
                    first = OUT / f"{stem}.{THEMES[0]}.png"
                    render(html_path, first, profile)
                    for theme in THEMES[1:]:
                        shutil.copyfile(first, OUT / f"{stem}.{theme}.png")
                print(stem)
    finally:
        shutil.rmtree(profile, ignore_errors=True)
    write_alt("charts", alt)
    return 0


if __name__ == "__main__":
    sys.exit(main())
