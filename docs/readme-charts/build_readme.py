"""Render one image per README section, in the steph charte v1 (docs/design/tokens.json).

    python3 docs/readme-charts/build_readme.py            # write HTML, render every PNG
    python3 docs/readme-charts/build_readme.py keys ask   # only these images
    python3 docs/readme-charts/build_readme.py --html     # write HTML only, no Chrome

Output: docs/readme-charts/src/readme/<name>.<lang>.html and
assets/readme/<name>.<lang>.<theme>.png, styles in src/readme-brand.css (1600 px wide, height of the content, same pipeline as build.py).
The charte is dark only and forbids lemon on a light background, so the light PNG is a copy of the
dark one: the README keeps its <picture> markup and shows the same dark image in both GitHub themes.

Every sentence shown as spoken by steph is read from a bench result file at build time
(REAL below), so an image cannot drift from what the model actually said.
"""

import html
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from PIL import Image

# Self-contained on purpose: build.py (model charts) evolves separately.
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SCRATCH = Path(tempfile.gettempdir())
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
WIDTH = 800
SRC = HERE / "src" / "readme"
OUT = ROOT / "assets" / "readme"
TOKENS = json.loads((ROOT / "docs/design/tokens.json").read_text())
FONTS = TOKENS["font"]["google_fonts_url"].replace("display=swap", "display=block")

# What steph says in production (field said of docs/readme-charts/answers.small.json, see its settings field).
RESULT = "docs/readme-charts/answers.small.json"
GLOSS = {
    "fx27": "Failed. Header.tsx line 42: Property titel does not exist on type Props. Did you mean title?",
    "fx24": "12 packages upgraded.",
    "fx25": "Failed. dpkg lock held by unattended-upgr, process 4321.",
    "fx29": "GPU: NVIDIA Corporation GA106 [GeForce RTX 3060 Lite Hash Rate], network: Realtek Semiconductor Co., Ltd. RTL8111/8168/8411 PCI Express Gigabit Ethernet Controller, chipset: Advanced Micro Devices, Inc. [AMD] Starship/Matisse Root Complex, USB: 2, other devices: 14.",
    "qa_pip": "requests-2.32.3.",
    "qa_py": "Not in the history.",
}
REAL = {r["fixture"]: r["said"].strip() for r in json.loads((ROOT / RESULT).read_text())["rows"]}
CASES = {c["id"]: c for c in json.loads((ROOT / "bench/matrix/cases.json").read_text())}

# The body under the card is this key colour; the PNG is cropped at its first row, so each image
# takes the height of its content.
CROP_KEY = (255, 0, 254)
MAX_HEIGHT = 1400


def esc(s) -> str:
    return html.escape(str(s))


def render(html_path: Path, png_path: Path, height: int, profile: Path) -> None:
    # Chrome writes the screenshot but on this Mac its process does not always exit: wait for a stable file.
    png_path.unlink(missing_ok=True)
    proc = subprocess.Popen([CHROME, "--headless", f"--screenshot={png_path}", f"--window-size={WIDTH},{height}",
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


def render_cropped(html_path: Path, png_path: Path, profile: Path) -> None:
    render(html_path, png_path, MAX_HEIGHT, profile)
    img = Image.open(png_path).convert("RGB")
    bottom = next((y for y in range(img.height) if img.getpixel((0, y)) == CROP_KEY), None)
    if bottom is None:
        raise RuntimeError(f"{html_path.name}: content taller than {MAX_HEIGHT} px")
    img.crop((0, 0, img.width, bottom)).save(png_path, optimize=True)


def shown_lines(fixture: str) -> int:
    user = CASES[f"{fixture}@1500"]["messages"][1]["content"]
    return int(re.search(r"(\d+) lignes affichées", user).group(1))


class Img:
    def __init__(self, lang: str):
        self.lang = lang

    def t(self, fr: str, en: str) -> str:
        return typo(fr) if self.lang == "fr" else en

    def quote(self, text: str) -> str:
        return typo(f"« {esc(text)} »") if self.lang == "fr" else f"“{esc(text)}”"

    def said(self, fixture: str, size: int = 21) -> str:
        """steph's real sentence, French as spoken; English images add a translation."""
        gloss = f'<div class="gl">{esc(GLOSS[fixture])}</div>' if self.lang == "en" else ""
        return f'<div class="q" style="font-size:{size}px">{self.quote(REAL[fixture])}</div>{gloss}'


def typo(s: str) -> str:
    """French typography: no-break space before : % and inside guillemets, narrow one before ; ? !."""
    s = re.sub(r" ([:%»])", " \\1", s)
    s = re.sub(r" ([;?!])", " \\1", s)
    return s.replace("« ", "« ")


def chevron(px: int, color: str = "var(--lemon)") -> str:
    """The logo chevron: 3 x 3 grid, cells (1,1), (2,2), (1,3) lit."""
    lit = {0, 4, 6}
    cells = "".join(f'<i style="background:{color if k in lit else "transparent"}"></i>' for k in range(9))
    return f'<span class="chev" style="grid-template-columns:repeat(3,{px}px);grid-auto-rows:{px}px">{cells}</span>'


ARROW = '<svg class="ico arrow" width="28" height="28" viewBox="0 0 24 24"><path d="M3 12h16"/><path d="M13 6l6 6-6 6"/></svg>'


def who(img: Img, text_fr: str = "steph dit", text_en: str = "steph says") -> str:
    return f'<div class="who"><span class="sq"></span>{img.t(text_fr, text_en)}</div>'


COMMON = """<style>
.chev { display: inline-grid; }
.chev i { display: block; }
.who .sq { width: 14px; height: 14px; background: var(--black); flex: none; }
.arrow { color: var(--neutral); }
</style>"""


# ---------- images ----------

def banner(img: Img) -> str:
    acro = img.t("<b>S</b>hell <b>T</b>raduit <b>E</b>n <b>P</b>arole <b>H</b>umaine",
                 "<b>S</b>peaking <b>T</b>erminal, <b>E</b>verything <b>P</b>rivately <b>H</b>osted")
    chips = [img.t("Linux et macOS", "Linux and macOS"), img.t("100 % local", "100% local"),
             img.t("Gratuit pour les particuliers", "Free for individuals")]
    bars = "".join(f'<i style="width:{w}%"></i>' for w in (72, 88, 54, 80, 66, 90, 48))
    return f"""
<div class="logo"><span>steph</span>{chevron(9)}</div>
<div class="bn">
  <div>
    <h1>{img.t("Le terminal,<br><em>à voix haute.</em>", "Your terminal,<br><em>out loud.</em>")}</h1>
    <p class="sub">{img.t("steph écoute tout ce qui passe dans le shell et dit l'essentiel, en une phrase. Conçu et testé avec des personnes malvoyantes.",
                        "steph listens to everything in your shell and says what matters, in one sentence. Designed and tested with people with low vision.")}</p>
    <p class="acro">{acro}</p>
    <div class="chips">{"".join(f"<span>{c}</span>" for c in chips)}</div>
  </div>
  <div class="art">
    <div class="term win"><div class="lines">{bars}</div></div>
    <div class="say wave">{chevron(14, "var(--black)")}</div>
  </div>
</div>
<style>
.logo {{ display: flex; align-items: center; gap: 12px; font-size: 40px; font-weight: 700; line-height: 1; letter-spacing: -0.03em; }}
.bn {{ display: grid; grid-template-columns: 1fr 200px; gap: 32px; align-items: end; margin-top: 20px; }}
.bn h1 {{ margin-top: 0; font-size: 64px; line-height: 0.92; letter-spacing: -0.05em; }}
.bn .sub {{ margin-top: 18px; }}
.acro {{ margin: 12px 0 0; font-family: var(--mono); font-size: 19px; line-height: 1.4; color: var(--muted); }}
.acro b {{ color: var(--lemon); font-weight: 600; }}
.chips {{ display: flex; flex-wrap: wrap; gap: 10px; margin-top: 16px; }}
.chips span {{ font-family: var(--mono); font-size: 19px; font-weight: 500; line-height: 1; padding: 9px 12px; border: 2px solid var(--stroke); }}
.art {{ position: relative; height: 290px; }}
.win {{ position: absolute; left: 0; top: 0; width: 200px; height: 200px; }}
.lines {{ display: grid; gap: 12px; padding: 24px 20px; }}
.lines i {{ display: block; height: 8px; background: var(--neutral); }}
.wave {{ position: absolute; right: 0; bottom: 0; width: 120px; height: 104px; display: grid; place-items: center; }}
</style>"""


def problem(img: Img) -> str:
    n = shown_lines("fx29")
    bars = "".join(f'<i style="width:{w}%"></i>' for w in
                   [(37 * k * k + 11 * k) % 45 + 50 for k in range(n)])
    return f"""
<span class="tag">{img.t("Le problème", "The problem")}</span>
<h1>{img.t(f"Un lecteur d'écran lit {n} lignes.<br><em>steph dit une phrase.</em>", f"A screen reader reads {n} lines.<br><em>steph says one sentence.</em>")}</h1>
<div class="pb">
  <div>
    <div class="label">{img.t(f"Lecteur d'écran · {n} lignes", f"Screen reader · {n} lines")}</div>
    <div class="term wall"><div class="cmd">lspci</div><div class="rows35">{bars}</div></div>
  </div>
  {ARROW}
  <div>
    <div class="label">{img.t("steph · une phrase", "steph · one sentence")}</div>
    <div class="say one">{who(img)}{img.said("fx29", 23 if img.lang == "fr" else 21)}</div>
  </div>
</div>
<style>
.pb {{ display: grid; grid-template-columns: 312px 28px 1fr; gap: 18px; align-items: center; margin-top: 28px; }}
.pb .label {{ margin-bottom: 10px; }}
.wall {{ padding: 14px 18px 16px; }}
.rows35 {{ display: grid; gap: 3px; margin-top: 10px; }}
.rows35 i {{ display: block; height: 3px; background: var(--neutral); }}
.one {{ padding: 22px 24px 24px; }}
.one .q {{ margin-top: 12px; }}
</style>"""


def says(img: Img) -> str:
    rows = [("npm run build", "fx27"), ("sudo apt upgrade -y", "fx24"), ("sudo apt install nginx", "fx25")]
    out = []
    for cmd, fx in rows:
        n = shown_lines(fx)
        out.append(f'<div class="srow"><div class="term c"><div class="cmd">{esc(cmd)}</div>'
                   f'<div class="dim n">{img.t(f"{n} lignes affichées", f"{n} lines printed")}</div></div>'
                   f'{ARROW}<div class="say s">{img.said(fx, 20)}</div></div>')
    return f"""
<span class="tag">{img.t("Ce que vous entendez", "What you hear")}</span>
<h1>{img.t("Chaque commande.<br><em>Une phrase.</em>", "Every command.<br><em>One sentence.</em>")}</h1>
<div class="srows">{"".join(out)}</div>
<p class="foot">{img.t("Phrases dites en production : règles écrites en code pour ces trois sorties, sans appel au modèle (docs/readme-charts/answers.small.json).",
                       "What steph says in production: code rules for these three outputs, no model call (docs/readme-charts/answers.small.json). steph speaks French; translation below.")}</p>
<style>
.srows {{ display: grid; gap: 14px; margin-top: 28px; }}
.srow {{ display: grid; grid-template-columns: 300px 28px 1fr; gap: 12px; align-items: center; }}
.c {{ padding: 12px 16px; white-space: nowrap; }}
.c .n {{ margin-top: 2px; }}
.s {{ padding: 12px 18px 14px; }}
</style>"""


def ask(img: Img) -> str:
    qs = [("q quelle version de requests a été installée ?", "which version of requests was installed?", "qa_pip",
           img.t("Lue dans la sortie de pip install.", "Read from the pip install output.")),
          ("q quelle version de Python est installée ?", "which Python version is installed?", "qa_py",
           img.t("Pas dans la session : il ne l'invente pas.", "Not in the session: it does not make it up."))]
    out = []
    for q_fr, q_en, fx, note in qs:
        gloss = f'<span class="qg">{esc(q_en)}</span>' if img.lang == "en" else ""
        note_html = f'<div class="nt">{note}</div>' if note else ""
        out.append(f'<div class="qa"><div class="term qq"><div class="cmd">{esc(q_fr)}</div>{gloss}</div>'
                   f'<div class="say a">{img.said(fx, 20)}</div>{note_html}</div>')
    return f"""
<span class="tag">{img.t("Questions", "Questions")}</span>
<h1>{img.t("Posez la question.<br><em>Il a tout entendu.</em>", "Just ask.<br><em>It heard it all.</em>")}</h1>
<p class="sub">{img.t("Les questions portent sur tout l'historique de la session : commandes, codes de retour, sorties. Sur un portable i5 sans carte graphique, réponse en 2,2 s en médiane.",
                    "Questions cover the whole session history: commands, exit codes, output. On an i5 laptop with no graphics card, answered in 2.2 s (median).")}</p>
<div class="qas">{"".join(out)}</div>
<p class="foot">{img.t("Session du banc : git push (échec), docker ps, pip install requests, puis df -h. Réponses du petit modèle steph-speak après le garde-fou d’ancrage.",
                     "Bench session: git push (failed), docker ps, pip install requests, then df -h. Answers of the small steph-speak model after the grounding guard.")}</p>
<style>
.qas {{ display: grid; grid-template-columns: 1fr 1fr; gap: 24px; margin-top: 26px; align-items: start; }}
.qq {{ padding: 12px 16px; }}
.qg {{ display: block; margin-top: 2px; color: var(--muted); }}
.a {{ margin-top: 10px; padding: 12px 18px 14px; }}
.nt {{ margin-top: 10px; font-size: 20px; font-weight: 700; line-height: 1.35; color: var(--lemon); }}
</style>"""


def install(img: Img) -> str:
    stats = [(img.t("223 Mo", "223 MB"), img.t("le petit modèle ; 2,4 Go pour le modèle base", "the small model; 2.4 GB for the base model")),
             ("0", img.t("droit administrateur requis", "admin rights needed")),
             ("2", img.t("systèmes : Linux et macOS", "systems: Linux and macOS")),
             (img.t("9,9 s", "9.9 s"), img.t("avant la première phrase, dès le lancement", "before the first spoken word, from launch")),
             (img.t("1,6 Go", "1.6 GB"), img.t("libérés par steph uninstall en 1,6 s", "freed by steph uninstall in 1.6 s"))]
    cells = "".join(f'<div class="st"><div class="num">{a}</div><div class="cap">{b}</div></div>' for a, b in stats)
    return f"""
<span class="tag">{img.t("Installation", "Install")}</span>
<h1>{img.t("Une ligne.<br><em>Sans droits administrateur.</em>", "One line.<br><em>No admin rights.</em>")}</h1>
<div class="inst"><div class="c1">curl -fsSL https://steph.lsmdx.com/install | sh</div><div class="c1">steph</div></div>
<div class="stats">{cells}</div>
<p class="foot">{img.t("Mesuré sur macOS, compte vierge : 55 s et environ 1 Go sur le disque avec le petit modèle, cache de téléchargement compris.",
                       "Measured on macOS, fresh account: 55 s and about 1 GB on disk with the small model, download cache included.")}</p>
<style>
.inst {{ margin-top: 28px; padding: 20px 26px; background: var(--lemon); color: var(--black); clip-path: var(--notch-card);
  font-family: var(--mono); font-feature-settings: "calt" 0, "liga" 0; font-size: 21px; font-weight: 500; line-height: 1.55; }}
.c1::before {{ content: "$ "; }}
.stats {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-top: 16px; }}
.st {{ padding: 20px 22px; background: var(--block); }}
.st .num {{ font-size: 60px; font-weight: 500; line-height: 0.9; letter-spacing: -0.05em; }}
.st .cap {{ margin-top: 12px; font-size: 19px; line-height: 1.35; color: var(--soft); }}
.foot {{ margin-top: 20px; }}
</style>"""


def keys(img: Img) -> str:
    ks = [("F6", img.t("menu parlé", "spoken menu")), ("F7", img.t("questions", "questions")),
          ("F8", img.t("silence immédiat", "instant silence")), ("F9", img.t("répéter", "repeat")),
          ("F10", img.t("en détail", "in detail"))]
    caps = "".join(f'<div class="k"><kbd>{k}</kbd><div class="kl">{lab}</div></div>' for k, lab in ks)
    return f"""
<span class="tag">{img.t("Au clavier", "Keyboard")}</span>
<h1>{img.t("Cinq touches.<br><em>Les mains restent sur le clavier.</em>", "Five keys.<br><em>Hands stay on the keyboard.</em>")}</h1>
<div class="keys">{caps}</div>
<p class="foot">{img.t("Relecture ligne par ligne : Maj+F5 à Maj+F8. Sur Mac, maintenir fn. Touches modifiables dans config.toml.",
                       "Line by line review: Shift+F5 to Shift+F8. On a Mac, hold fn. Keys can be changed in config.toml.")}</p>
<style>
.keys {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 16px; margin-top: 32px; }}
.k kbd {{ display: grid; place-items: center; height: 104px; font-size: 40px; font-weight: 600; background: var(--lemon); color: var(--black);
  clip-path: var(--notch-btn); }}
.k .kl {{ margin-top: 12px; text-align: center; font-size: 20px; font-weight: 500; line-height: 1.3; }}
.foot {{ margin-top: 28px; }}
</style>"""


def how(img: Img) -> str:
    fork = ('<svg class="link" viewBox="0 0 24 100" preserveAspectRatio="none">'
            '<path d="M0 50H8V25H24M8 50V75H24" vector-effect="non-scaling-stroke"/></svg>')
    join = ('<svg class="link" viewBox="0 0 24 100" preserveAspectRatio="none">'
            '<path d="M0 25H16V75H0M16 50H24" vector-effect="non-scaling-stroke"/></svg>')
    line = ('<svg class="link" viewBox="0 0 24 100" preserveAspectRatio="none">'
            '<path d="M0 50H24" vector-effect="non-scaling-stroke"/></svg>')
    return f"""
<span class="tag">{img.t("Comment ça marche", "How it works")}</span>
<h1>{img.t("Des règles d'abord.<br><em>Le modèle seulement si besoin.</em>", "Rules first.<br><em>The model only when needed.</em>")}</h1>
<div class="flow">
  <div class="nd panel"><b>{img.t("Votre shell", "Your shell")}</b><span>zsh, bash</span></div>
  {line}
  <div class="nd panel"><b>{img.t("Nettoyeur", "Cleaner")}</b><span>{img.t("ANSI, barres de progression", "ANSI, progress bars")}</span></div>
  {fork}
  <div class="mid">
    <div class="nd rules"><b>{img.t("Règles · instantané", "Rules · instant")}</b>
      <span>{img.t("vide → « OK »<br>code 127 → « Commande introuvable »", "empty → “OK”<br>code 127 → “Command not found”")}</span></div>
    <div class="nd panel"><b>{img.t("LLM local", "Local LLM")}</b><span>{img.t("sorties longues, erreurs, questions", "long output, errors, questions")}</span></div>
  </div>
  {join}
  <div class="nd say voice"><b>Piper</b><span>{img.t("la voix, phrase par phrase", "the voice, sentence by sentence")}</span></div>
</div>
<style>
.flow {{ display: grid; grid-template-columns: 132px 16px 140px 24px 1fr 24px 150px; align-items: center; margin-top: 30px; }}
.link {{ align-self: stretch; width: 100%; height: 100%; fill: none; stroke: var(--neutral); stroke-width: 2; }}
.mid {{ display: grid; gap: 16px; }}
.nd {{ padding: 12px 12px 14px; }}
.nd b {{ display: block; font-size: 20px; font-weight: 700; line-height: 1.2; }}
.nd span {{ display: block; margin-top: 6px; font-size: 19px; line-height: 1.3; color: var(--soft); }}
.rules {{ background: var(--surface); border: 2px solid var(--offwhite); }}
.voice span {{ color: var(--black); }}
</style>"""


def voice(img: Img) -> str:
    words = [("lspci", "L S, P C I"), ("GA106", "G A 106"), ("xHCI", "X H C I"), ("lsusb", "L S U S B")]
    rows = "".join(f'<div class="w"><code>{esc(a)}</code>{ARROW}<span class="sp">{img.quote(b)}</span></div>'
                   for a, b in words)
    return f"""
<span class="tag">{img.t("Voix et prononciation", "Voice and pronunciation")}</span>
<h1>{img.t("Les mots techniques,<br><em>enfin prononcés.</em>", "Tech words,<br><em>pronounced right.</em>")}</h1>
<div class="vc">
  <div class="term words"><div class="wl">{img.t("écrit → dit", "written → spoken")}</div>{rows}</div>
  <div class="score">
    <div class="label">{img.t("Mots reconnus par Whisper", "Words recognized by Whisper")}</div>
    <div class="nums"><span class="before">45</span>{ARROW}<span class="big after">68</span><span class="of">/94</span></div>
    <p class="cap">{img.t("Voix Piper siwis, française, sur 35 phrases de terminal. Aucun mot français de contrôle dégradé.",
                        "Piper siwis voice, French, over 35 terminal sentences. No French control word got worse.")}</p>
  </div>
</div>
<p class="foot">{img.t("Mesure par aller-retour Whisper sur MacBook Pro M3 Pro : un indicateur, pas une écoute humaine. docs/pronunciation.fr.md",
                       "Measured by a Whisper round trip on a MacBook Pro M3 Pro: a proxy, not a human listening test. docs/pronunciation.md")}</p>
<style>
.vc {{ display: grid; grid-template-columns: 340px 1fr; gap: 32px; align-items: center; margin-top: 26px; }}
.words {{ padding: 16px 20px; }}
.wl {{ margin-bottom: 6px; }}
.w {{ display: grid; grid-template-columns: 80px 28px 1fr; gap: 12px; align-items: center; padding: 5px 0; }}
.w code {{ color: var(--offwhite); }}
.w .sp {{ font-family: var(--sans); font-size: 21px; font-weight: 500; color: var(--lemon); white-space: nowrap; }}
.nums {{ display: flex; align-items: baseline; gap: 14px; margin-top: 12px; }}
.nums svg {{ align-self: center; }}
.before {{ font-size: 60px; font-weight: 500; letter-spacing: -0.05em; color: var(--muted); }}
.after {{ font-size: 112px; }}
.of {{ font-family: var(--mono); font-size: 28px; font-weight: 600; color: var(--muted); }}
.score .cap {{ margin: 12px 0 0; font-size: 19px; line-height: 1.4; color: var(--soft); }}
</style>"""


def local(img: Img) -> str:
    parts = [(img.t("Votre shell", "Your shell"), "zsh, bash"),
             (img.t("Modèle", "Model"), "steph-speak"),
             (img.t("Voix", "Voice"), "Piper"),
             (img.t("Historique", "History"), img.t("la session", "the session"))]
    tiles = "".join(f'<div class="tile"><b>{a}</b><span>{b}</span></div>' for a, b in parts)
    return f"""
<span class="tag">{img.t("Confidentialité", "Privacy")}</span>
<h1>{img.t("Rien ne sort<br><em>de la machine.</em>", "Nothing leaves<br><em>your machine.</em>")}</h1>
<div class="lc">
  <div class="box">
    <div class="label bl">{img.t("Votre ordinateur", "Your computer")}</div>
    <div class="tiles">{tiles}</div>
    <div class="lo">{img.t("modèle servi sur", "model served on")} <code>127.0.0.1</code></div>
  </div>
  <div class="side">
    <p class="sub">{img.t("Le modèle et la voix tournent sur votre ordinateur. Aucun cloud, aucune donnée envoyée.",
                        "The model and the voice run on your computer. No cloud, no data sent anywhere.")}</p>
    <div class="cloud">{img.t("Aucun cloud", "No cloud")}</div>
  </div>
</div>
<style>
.lc {{ display: grid; grid-template-columns: 1fr 250px; gap: 28px; align-items: center; margin-top: 26px; }}
.box {{ padding: 22px; background: var(--surface); border: 2px solid var(--lemon); }}
.bl {{ color: var(--lemon); margin-bottom: 14px; }}
.tiles {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }}
.tile {{ padding: 12px 14px; background: var(--block); }}
.tile b {{ display: block; font-size: 20px; font-weight: 700; line-height: 1.2; }}
.tile span {{ display: block; margin-top: 4px; font-family: var(--mono); font-size: 19px; color: var(--muted); }}
.lo {{ margin-top: 14px; font-size: 19px; color: var(--soft); }}
.lo code {{ font-weight: 600; color: var(--offwhite); }}
.side .sub {{ margin: 0; }}
.cloud {{ display: inline-block; margin-top: 20px; padding: 10px 14px; border: 2px dashed var(--stroke); font-family: var(--mono);
  font-size: 19px; font-weight: 500; color: var(--muted); }}
</style>"""


def hardware(img: Img) -> str:
    def chain(items):
        out = []
        for i, (a, b, hot) in enumerate(items):
            if i:
                out.append(f'<span class="or">{img.t("sinon", "else")}</span>')
            out.append(f'<div class="hw{" say" if hot else " panel"}"><b>{a}</b><span>{b}</span></div>')
        return "".join(out)
    linux = chain([("NVIDIA", img.t("4 Go suffisent", "4 GB is enough"), True), ("Vulkan", img.t("autres GPU", "other GPUs"), False),
                   ("CPU", img.t("sans GPU", "no GPU"), False)])
    mac = chain([("Metal", "Apple Silicon, Intel", True)])
    machines = [(img.t("2,33 s", "2.33 s"), img.t("i5-7200U, CPU seul, premier mot p90, petit modèle steph-speak (~0,56 Go de RAM)",
                                  "i5-7200U, CPU only, first word p90, small steph-speak model (~0.56 GB RAM)")),
                (img.t("0,68 s", "0.68 s"), img.t("Mac M3 Pro, Metal, premier mot p90, Gemma 4 E2B brut (RAM 3,4 à 3,7 Go)",
                                  "Mac M3 Pro, Metal, first word p90, raw Gemma 4 E2B (RAM 3.4 to 3.7 GB)")),
                (img.t("1,5 s", "1.5 s"), img.t("NVIDIA T600, 4 Go, résumé moyen, Gemma 4 E2B brut",
                                 "NVIDIA T600, 4 GB, mean summary, raw Gemma 4 E2B"))]
    mcells = "".join(f'<div class="st"><div class="num">{a}</div><div class="cap">{b}</div></div>' for a, b in machines)
    return f"""
<span class="tag">{img.t("Matériel", "Hardware")}</span>
<h1>{img.t("4 Go de mémoire vidéo<br><em>suffisent.</em>", "4 GB of video memory<br><em>is enough.</em>")}</h1>
<div class="lanes">
  <div class="lane"><div class="os">Linux</div><div class="ch">{linux}</div></div>
  <div class="lane"><div class="os">macOS</div><div class="ch">{mac}</div></div>
</div>
<div class="prof"><div class="term pc"><div class="cmd">steph profile</div></div>
  <span>{img.t("affiche le matériel détecté et la commande llama&#8209;server qui sera lancée. Réglages adaptés au GPU, automatiquement.",
               "shows the detected hardware and the llama&#8209;server command it will launch. Settings adapt to the GPU, automatically.")}</span></div>
<div class="stats">{mcells}</div>
<p class="foot">{img.t("i5-7200U : petit modèle steph-speak. Mac et NVIDIA T600 : Gemma 4 E2B brut, mesuré avant l'affinage.",
                       "i5-7200U: small steph-speak model. Mac and NVIDIA T600: raw Gemma 4 E2B, measured before fine-tuning.")}</p>
<style>
.lanes {{ display: grid; gap: 14px; margin-top: 28px; }}
.lane {{ display: grid; grid-template-columns: 76px 1fr; align-items: center; gap: 12px; }}
.os {{ font-family: var(--mono); font-size: 19px; font-weight: 600; color: var(--muted); }}
.ch {{ display: flex; align-items: center; gap: 10px; }}
.hw {{ padding: 10px 14px 12px; }}
.hw b {{ display: block; font-size: 22px; font-weight: 700; line-height: 1.2; }}
.hw span {{ display: block; margin-top: 2px; font-size: 19px; line-height: 1.3; white-space: nowrap; }}
.hw.panel span {{ color: var(--soft); }}
.or {{ font-family: var(--mono); font-size: 19px; font-weight: 500; color: var(--muted); }}
.prof {{ display: grid; grid-template-columns: auto 1fr; gap: 18px; align-items: center; margin-top: 28px; }}
.pc {{ padding: 12px 16px; }}
.prof span {{ font-size: 19px; line-height: 1.4; color: var(--soft); }}
.stats {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-top: 20px; }}
.st {{ padding: 18px 20px; background: var(--block); }}
.st .num {{ font-family: var(--mono); font-size: 38px; font-weight: 600; line-height: 1; letter-spacing: -0.03em; color: var(--lemon); }}
.st .cap {{ margin-top: 10px; font-size: 19px; line-height: 1.3; color: var(--soft); }}
.foot {{ margin-top: 18px; }}
</style>"""


def bench(img: Img) -> str:
    # README "Model choice" table, NVIDIA T600 4 GB, mean summary latency.
    rows = [("Qwen3.5 0.8B", 0.6, img.t("invente trop", "makes things up")),
            ("LFM2.5 1.2B", 1.1, img.t("style télégraphique, peu utile", "telegraphic, not very useful")),
            ("Qwen3.5 2B", 1.1, img.t("correct, quelques erreurs", "fair, a few mistakes")),
            ("Gemma 4 E2B", 1.5, img.t("factuel, meilleur en Q&amp;R", "factual, best at Q&amp;A")),
            ("granite 4.2 3B", 2.8, img.t("précis, laisse fuiter &lt;/think&gt;", "precise, leaks &lt;/think&gt;")),
            ("Qwen3.5 4B", 3.2, img.t("le meilleur, trop lent", "the best, too slow"))]
    scale = 4.0

    def num(x: float) -> str:
        return f"{x:.1f}".replace(".", ",") if img.lang == "fr" else f"{x:.1f}"

    out = []
    for name, s, q in rows:
        hot = name == "Gemma 4 E2B"
        tag = ""
        out.append(f'<div class="br{" hot" if hot else ""}"><div class="nm"><b>{name}</b>{tag}<span class="ql"> · {q}</span></div>'
                   f'<div class="tr"><i class="bar" style="width:{s / scale * 100:.2f}%"></i><span class="sv">{num(s)} s</span></div></div>')
    ticks = "".join(f'<span style="left:{v / scale * 100}%">{t}</span>' for v, t in ((0, "0"), (2, "2"), (4, "4 s")))
    return f"""
<span class="tag">{img.t("Choix du modèle", "Model choice")}</span>
<h1 class="bh">{img.t("Six modèles, chronométrés.<br><em>Le plus juste l'emporte.</em>", "Six models, timed.<br><em>The most factual wins.</em>")}</h1>
<p class="sub">{img.t("Latence moyenne du résumé, en secondes. Plus court, c'est mieux ; la justesse décide.",
                    "Mean summary latency, in seconds. Shorter is better; accuracy decides.")}</p>
<div class="plot"><div class="brs">{"".join(out)}</div><div class="ticks">{ticks}</div></div>
<p class="foot">{img.t("NVIDIA T600, 4 Go. Banc reproductible : bench/bench.py, fixtures réelles.",
                       "NVIDIA T600, 4 GB. Reproducible bench: bench/bench.py, real fixtures.")}</p>
<style>
.plot {{ margin-top: 22px; padding: 20px 24px 14px; background: var(--surface); border: 2px solid var(--deco); }}
.brs {{ display: grid; gap: 12px; margin-right: 80px; border-left: 2px solid var(--neutral); }}
.nm {{ padding-left: 10px; font-size: 19px; line-height: 1.3; white-space: nowrap; }}
.nm b {{ font-weight: 500; }}
.ql {{ color: var(--muted); }}
.tr {{ position: relative; display: flex; align-items: center; gap: 10px; margin-top: 4px; height: 28px; }}
.bar {{ display: block; height: 28px; background: var(--neutral); flex: none; }}
.sv {{ font-family: var(--mono); font-size: 19px; font-weight: 600; white-space: nowrap; }}
.br.hot .nm b, .br.hot .def {{ font-family: var(--mono); font-weight: 700; color: var(--lemon); }}
.br.hot .bar {{ background: var(--lemon); }}
.br.hot .sv {{ color: var(--lemon); }}
.ticks {{ position: relative; height: 30px; margin: 6px 80px 0 0; font-family: var(--mono); font-size: 19px; color: var(--muted); }}
.ticks span {{ position: absolute; top: 0; transform: translateX(-50%); white-space: nowrap; }}
.ticks span:first-child {{ transform: none; }}
.bh {{ font-size: 44px; }}
</style>"""


def license_(img: Img) -> str:
    cards = [(img.t("Gratuit", "Free"), img.t("Particuliers, études, loisirs", "Individuals, study, hobby projects"), False),
             (img.t("Gratuit", "Free"), img.t("Associations, écoles, recherche publique, administrations", "Nonprofits, schools, public research, government"), False),
             (img.t("Sur devis", "On request"), img.t("Entreprises, prestataires, intégration dans un produit", "Companies, contractors, embedding in a product"), True)]
    html_cards = "".join(f'<div class="lic{" hot" if hot else " panel"}"><div class="pr">{p}</div><div class="who2">{w}</div>'
                         f'<div class="ln2">{"Licence commerciale" if hot and img.lang == "fr" else "Commercial license" if hot else "PolyForm Noncommercial 1.0.0"}</div></div>'
                         for p, w, hot in cards)
    return f"""
<span class="tag">{img.t("Licence", "License")}</span>
<h1>{img.t("Gratuit pour vous.<br><em>Sous licence pour les entreprises.</em>", "Free for you.<br><em>Licensed for companies.</em>")}</h1>
<div class="lics">{html_cards}</div>
<div class="contact"><span>luis@lsmdx.com</span><span>github.com/tutozz/steph</span><span>steph.lsmdx.com</span></div>
<style>
.lics {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-top: 28px; }}
.lic {{ display: flex; flex-direction: column; padding: 20px 20px 18px; }}
.pr {{ font-size: 34px; font-weight: 500; line-height: 1; letter-spacing: -0.03em; }}
.who2 {{ flex: 1; margin-top: 12px; font-size: 19px; line-height: 1.35; color: var(--soft); }}
.ln2 {{ margin-top: 16px; font-family: var(--mono); font-size: 19px; font-weight: 500; line-height: 1.3; color: var(--muted); }}
.lic.hot {{ background: var(--offwhite); color: var(--black); clip-path: var(--notch-card); }}
.lic.hot .who2 {{ color: #2e2e2b; }}
.lic.hot .ln2 {{ color: var(--black); font-weight: 600; }}
.contact {{ display: flex; flex-wrap: wrap; gap: 8px 28px; margin-top: 26px; font-family: var(--mono); font-size: 20px; font-weight: 500; }}
.contact span:first-child {{ color: var(--lemon); }}
</style>"""


IMAGES = {"banner": banner, "problem": problem, "says": says, "install": install, "keys": keys, "ask": ask,
          "how": how, "voice": voice, "local": local, "hardware": hardware, "bench": bench, "license": license_}


def page(name: str, lang: str) -> str:
    body = IMAGES[name](Img(lang))
    return f"""<!doctype html>
<html lang="{lang}"><head><meta charset="utf-8">
<link rel="stylesheet" href="{FONTS}">
<link rel="stylesheet" href="../readme-brand.css">
<style>body {{ background: rgb{CROP_KEY}; }}</style>{COMMON}
</head><body><div class="card">{body}</div></body></html>
"""


def main() -> int:
    missing = [k for k in GLOSS if k not in REAL]
    if missing:
        print("missing in", RESULT, missing)
        return 1
    SRC.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    only = [a for a in sys.argv[1:] if a in IMAGES] or list(IMAGES)
    base = SCRATCH if SCRATCH.exists() else None
    profile = Path(tempfile.mkdtemp(prefix="chrome-profile-readme-", dir=base))
    try:
        for name in only:
            for lang in ("fr", "en"):
                stem = f"{name}.{lang}"
                html_path = SRC / f"{stem}.html"
                html_path.write_text(page(name, lang))
                if "--html" not in sys.argv:
                    render_cropped(html_path, OUT / f"{stem}.dark.png", profile)
                    shutil.copyfile(OUT / f"{stem}.dark.png", OUT / f"{stem}.light.png")
                print(stem)
    finally:
        shutil.rmtree(profile, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
