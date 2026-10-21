"""Axe C (entree) : variantes de compaction de la sortie avant le modele.

Genere des fichiers de cas dans quality/entree/, jamais dans cases*.json (regle
de la boucle qualite). Prompt fixe : P1 (Qwen3.5 0.8B) ou P2 (LFM2.5 350M,
Granite 4.0 H 350M), repris tels quels de variants.py. Seule la mise en forme
de la sortie ("Sortie :") et de l'entete (Commande/Statut/Duree) change.

    python3 gen_cases.py <label> <maxc> [important=off|first|only] [noise=off|on]
                          [extract=compact|tail|head] [status=normal|removed|clear]
                          [profile=p1|p2]
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(".")
MATRIX = ROOT / "bench" / "matrix"
OUT_DIR = MATRIX / "quality" / "entree"

sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(MATRIX))

from steph.digest import digest  # noqa: E402
from steph.prompts import status_text  # noqa: E402
from steph.textproc import compact_output, important_lines  # noqa: E402

import variants as V  # noqa: E402


def load_fixtures() -> list[dict]:
    fx = json.load(open(ROOT / "bench/fixtures.json")) + json.load(open(ROOT / "bench/extra_fixtures.json"))
    for extra, cmd in (("df_proxmox.txt", "df -h"), ("ip_a_proxmox.txt", "ip a")):
        fx.append({"cmd": cmd, "exit": 0, "duration": 0.1,
                   "output": (ROOT / "tests/data" / extra).read_text(), "id": extra[:-4]})
    return fx


def strip_noise(lines: list[str]) -> list[str]:
    """Lignes vides, doublons consecutifs (barre de progression) et numeros de ligne en tete."""
    out, prev = [], None
    for l in lines:
        s = l.strip()
        if not s or s == prev:
            prev = s if s else prev
            continue
        out.append(re.sub(r"^\s*\d+[:|\t]\s?", "", l))
        prev = s
    return out


def head_extract(lines: list[str], maxc: int) -> str:
    body, total = [], 0
    for l in lines:
        if total + len(l) + 1 > maxc:
            break
        body.append(l)
        total += len(l) + 1
    return "\n".join(body)


def tail_extract(lines: list[str], maxc: int) -> str:
    body, total = [], 0
    for l in reversed(lines):
        if total + len(l) + 1 > maxc:
            break
        body.insert(0, l)
        total += len(l) + 1
    return "\n".join(body)


def promote_important(lines: list[str], maxc: int, only: bool) -> str:
    imp = important_lines(lines)
    if not imp:
        return compact_output(lines, maxc)
    imp_text = "\n".join(imp)
    if only:
        return imp_text[:maxc]
    rest_budget = max(80, maxc - len(imp_text) - 4)
    rest = compact_output(lines, rest_budget)
    combined = imp_text + ("\n" + rest if rest else "")
    return combined[:maxc]


def build_body(cmd: str, output: str, maxc: int, *, important: str, noise: str, extract: str) -> str:
    lines = output.splitlines()
    if noise == "on":
        lines = strip_noise(lines)
    dg = digest(cmd, "\n".join(lines), maxc)
    if dg is not None:
        return dg  # sortie deja structuree (reseau/disques/liste) : les leviers generiques ne s'y appliquent pas
    if important in ("first", "only"):
        return promote_important(lines, maxc, only=(important == "only"))
    if extract == "tail":
        return tail_extract(lines, maxc)
    if extract == "head":
        return head_extract(lines, maxc)
    return compact_output(lines, maxc)


def build_header(cmd: str, exit_code: int | None, duration: float, nlines: int, status_mode: str) -> str:
    if status_mode == "removed":
        return f"Commande : {cmd}\nStatut : {status_text(exit_code)}\n"
    if status_mode == "clear":
        st = "Succes" if exit_code == 0 else "Echec" if exit_code else "Statut inconnu"
        st = {"Succes": "Succès", "Echec": "Échec"}.get(st, st)
        return f"{st}, {duration:.1f} s, {nlines} lignes.\nCommande : {cmd}\n"
    return f"Commande : {cmd}\nStatut : {status_text(exit_code)}\nDurée : {duration:.1f} s ; {nlines} lignes affichées\n"


def wrap_prompt(cmd: str, exit_code: int | None, user_output: str, profile: str) -> list[dict]:
    status = status_text(exit_code)
    cat = V.category(cmd, status, user_output)
    system = V.BASE + " " + V.RULES[cat]
    msgs = [{"role": "system", "content": system}]
    if profile == "p2":
        for u, a in V.SHOTS:
            msgs += [{"role": "user", "content": u}, {"role": "assistant", "content": a}]
    return msgs


def generate(maxc: int, *, important: str = "off", noise: str = "off", extract: str = "compact",
             status_mode: str = "normal", profile: str = "p1") -> list[dict]:
    fx = load_fixtures()
    base_cases = json.load(open(MATRIX / f"cases_{profile}.json"))
    qa_cases = [c for c in base_cases if c["kind"] == "qa"]
    cases = []
    for i, f in enumerate(fx):
        cid = f.get("id") or f"fx{i:02d}"
        nlines = len(f["output"].splitlines())
        body = build_body(f["cmd"], f["output"], maxc, important=important, noise=noise, extract=extract)
        header = build_header(f["cmd"], f["exit"], f["duration"], nlines, status_mode)
        user = header + f"Sortie :\n{body if body.strip() else '(aucune sortie)'}"
        msgs = wrap_prompt(f["cmd"], f["exit"], body, profile) + [{"role": "user", "content": user}]
        cases.append({"id": f"{cid}@{maxc}", "fixture": cid, "cmd": f["cmd"], "kind": "summary",
                      "maxc": maxc, "messages": msgs})
    cases += qa_cases
    return cases


def main() -> None:
    label = sys.argv[1]
    maxc = int(sys.argv[2])
    opts = dict(arg.split("=", 1) for arg in sys.argv[3:])
    cases = generate(maxc, important=opts.get("important", "off"), noise=opts.get("noise", "off"),
                      extract=opts.get("extract", "compact"), status_mode=opts.get("status", "normal"),
                      profile=opts.get("profile", "p1"))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"cases_{label}.json"
    json.dump(cases, open(out, "w"), ensure_ascii=False, indent=0)
    print(f"{label} : {len(cases)} cas -> {out}")


if __name__ == "__main__":
    main()
