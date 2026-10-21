#!/usr/bin/env python3
"""T6 (loop round 1): is the A7 invention judge as accurate on English phrases as on French ones?

    python3 judge_validate_en.py build <cases.json>                 # on the Mac, public data only
    PYTHONPATH=<judge_lib dir> python3 judge_validate_en.py run <cases.json> <out.json>

12 paired cases, each in English and in its French mirror (same context, same phrase meaning):
6 faithful phrases (paraphrases, spelled-out numbers, unit conversion, hedged inference taken
from the benchmark's own reference answer) and 6 planted inventions (one wrong number or one
fact absent from the context). Contexts come from 4 Steph Speak Bench dev cases (native EN and
FR versions) and 2 bench fixtures (fx05, qa2) with a hand translation to English. Both judge
passes (A, B) run on every case; the final verdict follows judge_bench.py (invention if both
passes agree, douteux if one does).

SPDX-License-Identifier: MIT
"""

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]

FX05_FR = """Commande : ping -c 3 127.0.0.1
Statut : succès (code 0)
Durée : 2.1 s ; 8 lignes affichées
Sortie :
PING 127.0.0.1 (127.0.0.1) 56(84) octets de données.
64 octets de 127.0.0.1 : icmp_seq=1 ttl=64 temps=0.020 ms
64 octets de 127.0.0.1 : icmp_seq=2 ttl=64 temps=0.017 ms
64 octets de 127.0.0.1 : icmp_seq=3 ttl=64 temps=0.036 ms
--- statistiques ping 127.0.0.1 ---
3 paquets transmis, 3 reçus, 0% packet loss, time 2059ms
rtt min/avg/max/mdev = 0.017/0.024/0.036/0.008 ms"""

FX05_EN = """Command: ping -c 3 127.0.0.1
Status: success (exit 0)
Duration: 2.1 s; 8 lines printed
Output:
PING 127.0.0.1 (127.0.0.1) 56(84) bytes of data.
64 bytes from 127.0.0.1: icmp_seq=1 ttl=64 time=0.020 ms
64 bytes from 127.0.0.1: icmp_seq=2 ttl=64 time=0.017 ms
64 bytes from 127.0.0.1: icmp_seq=3 ttl=64 time=0.036 ms
--- 127.0.0.1 ping statistics ---
3 packets transmitted, 3 received, 0% packet loss, time 2059ms
rtt min/avg/max/mdev = 0.017/0.024/0.036/0.008 ms"""

QA2_FR = """Historique :
Commande : npm run build
Statut : échec (code 1)
Sortie :
src/components/Header.tsx:42:17 - error TS2339: Property 'titel' does not exist on type 'Props'. Did you mean 'title'?

Commande : df -h
Statut : succès
Sortie :
racine : 8.9G libres sur 94G, 91 %
backup-hdd : 134G libres sur 442G, 70 %

Question : Quelle version de Python est installée ?"""

QA2_EN = """History:
Command: npm run build
Status: failure (exit 1)
Output:
src/components/Header.tsx:42:17 - error TS2339: Property 'titel' does not exist on type 'Props'. Did you mean 'title'?

Command: df -h
Status: success
Output:
root: 8.9G free of 94G, 91%
backup-hdd: 134G free of 442G, 70%

Question: Which Python version is installed?"""

# (id, context source, expected, English phrase, French phrase)
PHRASES = [
    ("V01-faithful-ping", "fx05", "ok",
     "Local ping fine: three packets sent, all three came back, about 0.02 milliseconds on average.",
     "Ping local correct : trois paquets envoyés, les trois reçus, environ 0,02 milliseconde en moyenne."),
    ("V02-invented-ping-loss", "fx05", "invention",
     "Ping OK: 3 packets sent, 1 lost, average 0.024 ms.",
     "Ping correct : 3 paquets envoyés, 1 perdu, moyenne 0,024 ms."),
    ("V03-faithful-qa-absent", "qa2", "ok",
     "Not in the history.",
     "Pas dans l'historique."),
    ("V04-invented-qa-python", "qa2", "invention",
     "Python 3.12 is installed.",
     "Python 3.12 est installé."),
    ("V05-faithful-cmake-line", "build-cmake-missing-package", "ok",
     "CMake configuration failed: it could not find the OpenSSL package, called from CMakeLists.txt line 23.",
     "La configuration CMake a échoué : paquet OpenSSL introuvable, appelé depuis CMakeLists.txt ligne 23."),
    ("V06-invented-cmake-line", "build-cmake-missing-package", "invention",
     "CMake failed: OpenSSL not found, CMakeLists.txt line 32.",
     "Échec CMake : OpenSSL introuvable, CMakeLists.txt ligne 32."),
    ("V07-faithful-oom-inference", "runtime-oom-killed", "ok",
     "Training was killed during epoch 4 with exit code 137, most likely out of memory.",
     "L'entraînement a été tué pendant l'époque 4, code 137, probablement par manque de mémoire."),
    ("V08-invented-oom-epoch", "runtime-oom-killed", "invention",
     "Training killed at epoch 40 of 50, exit 137.",
     "Entraînement tué à l'époque 40 sur 50, code 137."),
    ("V09-faithful-vitest-paraphrase", "tests-mocha-vitest", "ok",
     "One of seven tests failed: applies discount in pricing.test.ts got 81 instead of 90.",
     "Un test sur sept a échoué : applies discount dans pricing.test.ts donne 81 au lieu de 90."),
    ("V10-invented-vitest-count", "tests-mocha-vitest", "invention",
     "Two of seven tests failed, both in pricing.test.ts.",
     "Deux tests sur sept ont échoué, tous dans pricing.test.ts."),
    ("V11-faithful-lscpu-units", "hw-lscpu", "ok",
     "Intel Core i7-1370P, fourteen cores and twenty threads, up to 5 GHz.",
     "Intel Core i7-1370P, quatorze cœurs et vingt threads, jusqu'à 5 GHz."),
    ("V12-invented-lscpu-threads", "hw-lscpu", "invention",
     "Intel Core i7-1370P, 14 cores, 28 threads.",
     "Intel Core i7-1370P, 14 cœurs, 28 threads."),
]


def speak_context(case_id, lang):
    sys.path.insert(0, str(REPO / "benchmark"))
    import run as speak

    data = REPO / "benchmark/data/v1"
    prompts = speak.load_config(data)["prompts"]
    case = {c["id"]: c for c in speak.load_cases(data, lang, "dev")}[case_id]
    return speak.build_messages(case, prompts)[1]["content"]


def build(out):
    fixed = {("fx05", "en"): FX05_EN, ("fx05", "fr"): FX05_FR, ("qa2", "en"): QA2_EN, ("qa2", "fr"): QA2_FR}
    cases = []
    for cid, src, expected, en, fr in PHRASES:
        for lang, phrase in (("en", en), ("fr", fr)):
            ctx = fixed.get((src, lang)) or speak_context(src, lang)
            cases.append({"id": cid, "lang": lang, "source": src, "expected": expected, "context": ctx, "phrase": phrase})
    json.dump(cases, open(out, "w"), ensure_ascii=False, indent=1)
    print(f"{len(cases)} cases written to {out}")


def run(cases_path, out):
    from judge_lib import call_judge

    cases = json.load(open(cases_path))
    rows = []
    for c in cases:
        passes = {}
        for pass_id in ("A", "B"):
            r = call_judge(c["context"], c["phrase"], pass_id=pass_id)
            passes[pass_id] = {"verdict": r["verdict"], "inventions": r["inventions"]}
        va, vb = passes["A"]["verdict"], passes["B"]["verdict"]
        final = "invention" if va == vb == "invention" else ("douteux" if "invention" in (va, vb) else "ok")
        rows.append({**{k: c[k] for k in ("id", "lang", "expected", "phrase")}, "passes": passes, "final": final})
        print(f"{c['lang']} {c['id']}: attendu={c['expected']} A={va} B={vb} final={final} {passes['A']['inventions']}")
    summary = {}
    for lang in ("en", "fr"):
        rs = [r for r in rows if r["lang"] == lang]
        summary[lang] = {
            "n": len(rs),
            "pass_A_correct": sum(r["passes"]["A"]["verdict"] == r["expected"] for r in rs),
            "pass_B_correct": sum(r["passes"]["B"]["verdict"] == r["expected"] for r in rs),
            "final_correct": sum(r["final"] == r["expected"] for r in rs),
            "false_inventions_final": sum(r["expected"] == "ok" and r["final"] != "ok" for r in rs),
            "missed_inventions_final": sum(r["expected"] == "invention" and r["final"] != "invention" for r in rs),
        }
    print(json.dumps(summary, ensure_ascii=False))
    json.dump({"summary": summary, "rows": rows}, open(out, "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    if sys.argv[1] == "build":
        build(sys.argv[2])
    else:
        run(sys.argv[2], sys.argv[3])
