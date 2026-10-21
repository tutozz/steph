"""Revalidates the invention judge (judge_lib.call_judge) before every use, both passes.

    python3 judge_validate.py A
    python3 judge_validate.py B

The 6 French control cases are the ones validated 6/6 for A7 (docs/judge-a7.md): 3 faithful,
3 with a clear invention (wrong status, wrong figure, invented line). `judge_lib`'s prompt is
kept in French; english_validate() below is K2's extra check that the same French-prompted
judge still grades English phrases correctly, since K2 judges English corpus labels with it.

SPDX-License-Identifier: MIT
"""
import sys

from judge_lib import call_judge

CTX_FX01 = """Commande : df -h
Statut : succès (code 0)
Durée : 0.0 s ; 14 lignes affichées
Sortie :
racine : 685G libres sur 953G, 29 %
boot : 284M libres sur 974M, 69 %"""

CTX_FX07 = """Commande : free -h
Statut : succès (code 0)
Durée : 0.0 s ; 3 lignes affichées
Sortie :
               total        used        free      shared  buff/cache   available
Mem:            31Gi       6,6Gi       865Mi       354Mi        25Gi        24Gi
Swap:          8,0Gi        72Ki       8,0Gi"""

CTX_FX27 = """Commande : npm run build
Statut : échec (code 1)
Durée : 12.5 s ; 9 lignes affichées
Sortie :
> app@1.0.0 build
> tsc && vite build
src/components/Header.tsx:42:17 - error TS2339: Property 'titel' does not exist on type 'Props'. Did you mean 'title'?
42     <h1>{props.titel}</h1>
                   ~~~~~
Found 1 error in src/components/Header.tsx:42"""

CONTROL_CASES = [
    {"id": "C1-fidele-disque", "context": CTX_FX01,
     "phrase": "Racine 685G libres sur 953G, 29 %. Boot 69 %.", "expected": "ok"},
    {"id": "C2-fidele-memoire", "context": CTX_FX07,
     "phrase": "31 Gi au total, 24 Gi disponibles.", "expected": "ok"},
    {"id": "C3-fidele-erreur-ligne", "context": CTX_FX27,
     "phrase": "Échec. Header.tsx ligne 42 : titel inconnu, utiliser title.", "expected": "ok"},
    {"id": "C4-invention-statut", "context": CTX_FX01,
     "phrase": "Échec. Racine pleine à 91 %, seulement 8,9G libres.", "expected": "invention"},
    {"id": "C5-invention-chiffre", "context": CTX_FX07,
     "phrase": "31 Gi au total, 16 Gi disponibles.", "expected": "invention"},
    {"id": "C6-invention-ligne", "context": CTX_FX27,
     "phrase": "Échec. Header.tsx ligne 58 : property titel manquante.", "expected": "invention"},
]

# K2 : mêmes 3 contextes, phrases et faits en anglais (fidèle, puis inventé), pour vérifier
# que le prompt français du juge grade correctement une sortie anglaise avant de l'utiliser
# sur le corpus EN.
CTX_FX01_EN = """Command: df -h
Status: success (code 0)
Duration: 0.0 s; 14 lines displayed
Output:
root: 685G free of 953G, 29%
boot: 284M free of 974M, 69%"""

CTX_FX27_EN = """Command: npm run build
Status: failed (code 1)
Duration: 12.5 s; 9 lines displayed
Output:
> app@1.0.0 build
> tsc && vite build
src/components/Header.tsx:42:17 - error TS2339: Property 'titel' does not exist on type 'Props'. Did you mean 'title'?
42     <h1>{props.titel}</h1>
                   ~~~~~
Found 1 error in src/components/Header.tsx:42"""

ENGLISH_CONTROL_CASES = [
    {"id": "E1-faithful-disk", "context": CTX_FX01_EN,
     "phrase": "Root 685G free of 953G, 29%. Boot 69%.", "expected": "ok"},
    {"id": "E2-faithful-error-line", "context": CTX_FX27_EN,
     "phrase": "Failed. Header.tsx line 42: titel unknown, use title.", "expected": "ok"},
    {"id": "E3-invented-status", "context": CTX_FX01_EN,
     "phrase": "Failed. Root full at 91%, only 8.9G free.", "expected": "invention"},
    {"id": "E4-invented-line", "context": CTX_FX27_EN,
     "phrase": "Failed. Header.tsx line 58: titel property missing.", "expected": "invention"},
]


def run(cases, pass_id):
    ok_count = 0
    for case in cases:
        result = call_judge(case["context"], case["phrase"], pass_id=pass_id)
        got = result["verdict"]
        match = "OK" if got == case["expected"] else "FAIL"
        if match == "OK":
            ok_count += 1
        print(f"[{match}] {case['id']}: attendu={case['expected']} obtenu={got} inventions={result['inventions']}")
        if result["verdict"] == "erreur":
            print(f"      RAW: {result.get('_raw')!r} ERROR: {result.get('_error')}")
    print(f"{ok_count}/{len(cases)} corrects (passe {pass_id})")
    return ok_count == len(cases)


def main():
    pass_id = sys.argv[1] if len(sys.argv) > 1 else "A"
    fr_ok = run(CONTROL_CASES, pass_id)
    print()
    en_ok = run(ENGLISH_CONTROL_CASES, pass_id)
    if not (fr_ok and en_ok):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
