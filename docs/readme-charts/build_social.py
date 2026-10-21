"""Render the social image, the repository banner and the favicons in the steph charter v1.

    python3 docs/readme-charts/build_social.py

Output:
    site/public/og.png            1280 x 640, French (landing /)
    site/public/og-en.png         1280 x 640, English (landing /en/)
    assets/banner.png             1280 x 640, English (docs/release.md, PyPI)
    site/public/favicon.svg       chevron alone, black on lemon
    site/public/favicon-32.png    32 px, black chevron on lemon
    site/public/favicon.ico       16, 32 and 48 px, same drawing
    site/public/apple-touch-icon.png  180 px, lemon chevron on black

Logo (charter, section Logotype): 3 x 3 grid, lit cells (1,1), (2,2), (1,3) in column-row
order, i.e. the shell prompt ">". Chevron pixel = 0.19 x font size here, as in the mock-ups.
"""

import json
import shutil
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

from build import screenshot

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SRC = HERE / "src" / "social"
PUBLIC = ROOT / "site" / "public"
TOKENS = json.loads((ROOT / "docs" / "design" / "tokens.json").read_text())
COLOR = TOKENS["color"]
FONTS = TOKENS["font"]["google_fonts_url"].replace("display=swap", "display=block")
LIT = [(0, 0), (1, 1), (0, 2)]  # (column, row), zero-based

TEXT = {
    "fr": {
        "eyebrow": "Lecteur vocal de terminal",
        "title": "Le terminal,<br><em>à voix haute.</em>",
        "sub": "steph écoute le shell et dit l'essentiel de chaque commande, en une phrase.",
        "foot": "Linux et macOS · 100 % local · steph.lsmdx.com",
    },
    "en": {
        "eyebrow": "Talking terminal",
        "title": "Your terminal,<br><em>out loud.</em>",
        "sub": "steph listens to your shell and says what matters in each command, in one sentence.",
        "foot": "Linux and macOS · 100% local · steph.lsmdx.com",
    },
}


def chevron_html(px: int, color: str) -> str:
    cells = "".join(f'<i style="background:{color}"></i>' if (i % 3, i // 3) in LIT else "<i></i>" for i in range(9))
    return f'<span class="chev" style="grid-template-columns:repeat(3,{px}px);grid-auto-rows:{px}px">{cells}</span>'


def fringe_script(n: int, seed: int) -> str:
    # Same generator as the landing mock-up (mulberry32, p = 0.62, empty ends).
    return f"""<script>
(() => {{
  let s = {seed} >>> 0;
  const rnd = () => {{ s = (s + 0x6D2B79F5) >>> 0; let t = s; t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }};
  const row = document.querySelector('.fringe');
  for (let i = 0; i < {n}; i++) {{
    const on = i !== 0 && i !== {n} - 1 && rnd() < 0.62;
    const c = document.createElement('i'); if (on) c.className = 'on'; row.appendChild(c);
  }}
}})();
</script>"""


def og_page(lang: str) -> str:
    t = TEXT[lang]
    return f"""<!doctype html>
<html lang="{lang}"><head><meta charset="utf-8">
<link rel="stylesheet" href="{FONTS}">
<style>
* {{ box-sizing: border-box; }}
html, body {{ margin: 0; width: 1280px; height: 640px; overflow: hidden; }}
body {{ background-color: {COLOR['black']}; color: {COLOR['offwhite']};
  background-image: linear-gradient({COLOR['grid']} 1px, transparent 1px), linear-gradient(90deg, {COLOR['grid']} 1px, transparent 1px);
  background-size: 32px 32px; font-family: "Space Grotesk", sans-serif; -webkit-font-smoothing: antialiased; }}
.b {{ position: relative; height: 640px; padding: 56px 64px 0; }}
.logo {{ display: flex; align-items: center; gap: 12px; }}
.logo b {{ font: 700 44px/1 "Space Grotesk"; letter-spacing: -0.04em; }}
.chev {{ display: grid; }}
.eyebrow {{ margin-top: 44px; font: 500 24px/1.4 "JetBrains Mono"; color: {COLOR['lemon']}; }}
h1 {{ margin: 12px 0 0; font: 500 104px/0.92 "Space Grotesk"; letter-spacing: -0.05em; }}
h1 em {{ font-style: normal; color: {COLOR['lemon']}; }}
.sub {{ margin: 26px 0 0; max-width: 880px; font: 400 28px/1.4 "Space Grotesk"; color: {COLOR['text_muted']}; }}
.foot {{ position: absolute; right: 64px; top: 64px; font: 500 22px "JetBrains Mono"; color: {COLOR['text_muted']}; }}
.fringe {{ position: absolute; left: 0; right: 0; bottom: 0; display: flex; }}
.fringe i {{ flex: 1; height: 40px; }}
.fringe i.on {{ background: {COLOR['lemon']}; }}
</style></head><body><div class="b">
<div class="logo"><b>steph</b>{chevron_html(8, COLOR['lemon'])}</div>
<div class="foot">{t['foot']}</div>
<div class="eyebrow">{t['eyebrow']}</div>
<h1>{t['title']}</h1>
<p class="sub">{t['sub']}</p>
<div class="fringe"></div>
</div>{fringe_script(32, 61)}</body></html>
"""


def favicon_svg() -> str:
    # 32-unit square on lemon, 7-unit cells as in the charter's favicon card.
    rects = "".join(f'<rect x="{5 + 7 * c}" y="{5 + 7 * r}" width="7" height="7"/>' for c, r in LIT)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
            f'<rect width="32" height="32" fill="{COLOR["lemon"]}"/><g fill="#000">{rects}</g></svg>\n')


def draw_icon(size: int, bg: str, fg: str, cell_ratio: float) -> Image.Image:
    img = Image.new("RGB", (size, size), bg)
    d = ImageDraw.Draw(img)
    cell = round(size * cell_ratio)
    origin = (size - 3 * cell) // 2
    for c, r in LIT:
        x, y = origin + c * cell, origin + r * cell
        d.rectangle((x, y, x + cell - 1, y + cell - 1), fill=fg)
    return img


def main() -> int:
    SRC.mkdir(parents=True, exist_ok=True)
    base = Path(tempfile.gettempdir())
    profile = Path(tempfile.mkdtemp(prefix="chrome-profile-social-", dir=base if base.exists() else None))
    try:
        for lang, dests in (("fr", [PUBLIC / "og.png"]), ("en", [PUBLIC / "og-en.png", ROOT / "assets" / "banner.png"])):
            html_path = SRC / f"og.{lang}.html"
            html_path.write_text(og_page(lang))
            tmp = SRC / f"og.{lang}.tmp.png"
            screenshot(html_path, tmp, 1280, 640, profile)
            img = Image.open(tmp).convert("RGB")
            if img.size != (1280, 640):
                img = img.resize((1280, 640), Image.LANCZOS)
            for d in dests:
                img.save(d, optimize=True)
                print(d.relative_to(ROOT))
            tmp.unlink()
    finally:
        shutil.rmtree(profile, ignore_errors=True)

    (PUBLIC / "favicon.svg").write_text(favicon_svg())
    small = draw_icon(32, COLOR["lemon"], "#000000", 7 / 32)
    small.save(PUBLIC / "favicon-32.png", optimize=True)
    draw_icon(48, COLOR["lemon"], "#000000", 10 / 48).save(
        PUBLIC / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])
    draw_icon(180, COLOR["black"], COLOR["lemon"], 36 / 180).save(PUBLIC / "apple-touch-icon.png", optimize=True)
    for n in ("favicon.svg", "favicon-32.png", "favicon.ico", "apple-touch-icon.png"):
        print((PUBLIC / n).relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
