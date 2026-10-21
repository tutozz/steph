#!/usr/bin/env python3
"""G4 : courbe taille -> écart de qualité et d'inventions au Q4_0 officiel (graines communes), en SVG.

    python3 g4_chart.py <g4-eval.json> <sha256-sizes-3080.txt> <out.svg>

Deux panneaux, un axe chacun. q2_k et iq3_xxs (-23 et -17 pts) sortent du cadre et sont nommés en note.

SPDX-License-Identifier: MIT
"""

import json
import sys

BG, INK, SOFT, GRID, NEUTRAL, ACCENT = "#0b0b0b", "#e6e6e1", "#cfcfca", "#2a2a28", "#8a8a85", "#e2ff3b"
OFFICIAL_BYTES = 3349516256
RECOMMENDED = "off-ple3"
OUT_OF_FRAME = ("q2_k", "iq3_xxs")


def main():
    ev = json.load(open(sys.argv[1]))
    sizes = {ln.split()[2]: int(ln.split()[1]) for ln in open(sys.argv[2]) if ln.strip()}
    pts = [("officiel", OFFICIAL_BYTES / 1e9, 0.0, 0.0, 3)]
    for m, p in ev["vs_ref"].items():
        name = m.removeprefix("g4-")
        if name == "official" or name in OUT_OF_FRAME:
            continue
        pts.append((name, sizes[name] / 1e9, p["quality"]["diff"], p["inventions"]["diff"], len(p["seeds"])))
    W, H, pad = 760, 330, 56
    panels = [("Qualité, écart en points", 2, -7.0, 2.0), ("Inventions, écart en points de %", 3, -3.0, 7.0)]
    pw = (W - 3 * pad) / 2
    x0, x1 = 2.1, 3.5
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" font-family="Helvetica, Arial, sans-serif" role="img" '
           f'aria-label="Écart au Q4_0 officiel selon la taille du GGUF">', f'<rect width="{W}" height="{H}" fill="{BG}"/>']
    for i, (title, k, y0, y1) in enumerate(panels):
        left = pad + i * (pw + pad)
        top, bottom = 40, H - 60
        sx = lambda v: left + (v - x0) / (x1 - x0) * pw  # noqa: E731
        sy = lambda v: bottom - (v - y0) / (y1 - y0) * (bottom - top)  # noqa: E731
        out.append(f'<text x="{left}" y="24" fill="{INK}" font-size="14">{title}</text>')
        step = 1 if k == 2 else 2
        v = y0
        while v <= y1 + 1e-9:
            out.append(f'<line x1="{left}" x2="{left + pw}" y1="{sy(v):.1f}" y2="{sy(v):.1f}" stroke="{GRID}" stroke-width="1"/>')
            out.append(f'<text x="{left - 6}" y="{sy(v) + 4:.1f}" fill="{SOFT}" font-size="11" text-anchor="end">{v:+.0f}</text>')
            v += step
        out.append(f'<line x1="{left}" x2="{left + pw}" y1="{sy(0):.1f}" y2="{sy(0):.1f}" stroke="{NEUTRAL}" stroke-width="1.5"/>')
        for g in (2.2, 2.6, 3.0, 3.4):
            out.append(f'<text x="{sx(g):.1f}" y="{bottom + 18}" fill="{SOFT}" font-size="11" text-anchor="middle">{g:.1f} Go</text>')
        for name, size, dq, dinv, seeds in pts:
            val = dq if k == 2 else dinv
            col = ACCENT if name == RECOMMENDED else NEUTRAL
            r = 6 if seeds == 3 else 4.5
            fill = col if seeds == 3 else BG
            out.append(f'<circle cx="{sx(size):.1f}" cy="{sy(val):.1f}" r="{r}" fill="{fill}" stroke="{col}" stroke-width="2">'
                       f'<title>{name} : {size:.2f} Go, {val:+.2f} ({seeds} graine{"s" if seeds > 1 else ""})</title></circle>')
            if name in (RECOMMENDED, "officiel", "off-ple2", "off-ple4", "q3_k_m", "iq3_m", "q4_0"):
                out.append(f'<text x="{sx(size) + 9:.1f}" y="{sy(val) + 4:.1f}" fill="{INK}" font-size="11">{name}</text>')
    out.append(f'<text x="{pad}" y="{H - 22}" fill="{SOFT}" font-size="11">Plein : 3 graines ; creux : 1 graine (7). '
               f'Hors cadre : q2_k -22,9 et iq3_xxs -16,9 pts de qualité. Référence : Q4_0 officiel QAT, 3,35 Go.</text>')
    out.append("</svg>")
    open(sys.argv[3], "w").write("\n".join(out))


if __name__ == "__main__":
    main()
