"""Contact sheets of the model charts, social images and favicons, for a visual check against the charter.

    python3 docs/readme-charts/contact.py

Output: docs/design/impl/charts/contact-<group>.png (one tile per image, 3 per row, name under it).
Only the .dark files are tiled: the .light files are byte-identical copies (checked here).
"""

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "design" / "impl" / "charts"
GROUPS = {
    "charts-fr": sorted((ROOT / "assets" / "charts").glob("*.fr.dark.png")),
    "charts-en": sorted((ROOT / "assets" / "charts").glob("*.en.dark.png")),
    "social": [ROOT / "site" / "public" / "og.png", ROOT / "site" / "public" / "og-en.png", ROOT / "assets" / "banner.png",
               ROOT / "site" / "public" / "apple-touch-icon.png", ROOT / "site" / "public" / "favicon-32.png"],
}
TILE_W, COLS, PAD, LABEL_H = 520, 3, 24, 34
BG, INK = (38, 38, 38), (244, 244, 240)


def font(size: int):
    for path in ("/System/Library/Fonts/Supplemental/Arial.ttf", "/Library/Fonts/Arial.ttf"):
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def sheet(name: str, files: list[Path]) -> Path:
    tiles = []
    for f in files:
        img = Image.open(f).convert("RGB")
        scale = min(1.0, TILE_W / img.width)
        tiles.append((f, img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)))
    rows = [tiles[i:i + COLS] for i in range(0, len(tiles), COLS)]
    heights = [max(t.height for _, t in r) + LABEL_H for r in rows]
    out = Image.new("RGB", (PAD + COLS * (TILE_W + PAD), PAD + sum(h + PAD for h in heights)), BG)
    draw, f18, y = ImageDraw.Draw(out), font(18), PAD
    for r, h in zip(rows, heights):
        for i, (path, t) in enumerate(r):
            x = PAD + i * (TILE_W + PAD)
            out.paste(t, (x, y))
            draw.text((x, y + t.height + 8), f"{path.relative_to(ROOT)}  {Image.open(path).size[0]}x{Image.open(path).size[1]}",
                      fill=INK, font=f18)
        y += h + PAD
    OUT.mkdir(parents=True, exist_ok=True)
    dest = OUT / f"contact-{name}.png"
    out.save(dest, optimize=True)
    return dest


def main() -> int:
    bad = []
    for folder in ("charts",):
        for dark in (ROOT / "assets" / folder).glob("*.dark.png"):
            light = dark.with_name(dark.name.replace(".dark.", ".light."))
            if not light.exists() or light.read_bytes() != dark.read_bytes():
                bad.append(str(light.relative_to(ROOT)))
    for name, files in GROUPS.items():
        files = [f for f in files if f.exists()]
        if files:
            print(sheet(name, files).relative_to(ROOT), len(files))
    if bad:
        print("light differs from dark:", *bad, sep="\n  ")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
