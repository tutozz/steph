#!/usr/bin/env python3
"""H3a, étape 3 : étiquetage par l'enseignant (Qwen3.5 9B) des entrées construites par
build_feature_corpus.py (détail, début, progression, flux, résidu résumé). Mêmes
réglages réseau que label.py (température 0, presence_penalty 1.0, cache_prompt) - la
requête (`query`) et l'écriture reprenable (`Writer`) en sont importées directement,
pas dupliquées.

Contrairement à label.py, les messages d'entrée sont déjà construits (par
build_feature_corpus.py, avec le prompt système de PRODUCTION) : ce script ne fait que
les envoyer à l'enseignant et écrire `train_messages` avec un prompt système COURT par
mode (TRAIN_*_SYSTEM ci-dessous), sur le modèle de TRAIN_SYSTEM/SUMMARY_SYSTEM de
label.py (docstring : « aujourd'hui narrator envoie SUMMARY_SYSTEM, que les affinés
n'ont jamais vu » - B3 doit encore trancher l'alignement définitif ; H3a suit ici la
même convention que le corpus résumé existant plutôt que d'en inventer une troisième).

Usage, un fichier de features à la fois. `--out` reste À PLAT dans `labeled/`, sans
sous-dossier : sync.sh (cas « labels ») et finalize_labels.py listent `labeled/*.jsonl`
sans récursion, exactement comme pour macos.jsonl/linux-low.jsonl/linux-dev.jsonl :
    python3 label_features.py --in corpus/features/detail.jsonl --mode detail \\
        --out labeled/detail.jsonl --port 8890 --parallel 4

`--mode` doit correspondre au champ `mode` déjà présent dans chaque ligne d'entrée
(sécurité : refuse de mélanger deux tâches dans un seul fichier de sortie).
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from label import Writer, done_ids, query  # noqa: E402

sys.path.insert(0, str(Path(__file__).parent.parent))  # bench/matrix/score.py
from score import clean  # noqa: E402

# Prompts d'entraînement courts, un par mode (H2 : « 5 prompts constants, pas un
# seul ») - jamais envoyés en production (voir prompts.py pour les prompts réels) ;
# alignement définitif entraînement/production : tâche B3/P18, pas ici.
# K3 : H3a mesurait 26 % d'inventions sur le détail, surtout des causes et des remèdes que
# la sortie n'écrit pas. Le prompt de production (DETAILS_SYSTEM) demande « cause [...]
# puis ce qu'il faut faire » et impose 3 points au moins : l'enseignant comblait avec des
# explications. Ici, recopier ce qui est écrit, et moins de points plutôt qu'un point inventé.
TRAIN_DETAILS_SYSTEM = (
    "Tu lis la sortie d'une commande de terminal et tu en donnes le détail, en français. "
    "Réponds en 1 à 5 points courts séparés par des points, 60 mots au plus : les faits utiles, "
    "pas la sortie entière. Recopie les noms, les nombres et les messages d'erreur exactement comme "
    "dans la sortie. Ne donne jamais une cause, une explication ni une solution que la sortie n'écrit "
    "pas : si la sortie ne dit pas pourquoi, ne le dis pas. Ne répète ni le statut, ni la durée, ni le "
    "nombre de lignes. N'invente jamais."
)
# Envoyé à l'enseignant à la place de DETAILS_SYSTEM : même style télégraphique que la
# production, mêmes interdits que TRAIN_DETAILS_SYSTEM.
TEACHER_DETAILS_SYSTEM = (
    "Tu es la voix d'un terminal, pour une personne malvoyante qui a demandé le détail de la "
    "dernière commande.\n"
    "On te donne la commande, son statut et sa sortie. Réponds en style télégraphique : des "
    "mots-clés, jamais de phrase complète, ni article, ni politesse ; 60 mots maximum, en 1 à 5 "
    "points séparés par des points : les faits utiles, pas la sortie entière. Moins de points "
    "plutôt qu'un point qui n'est pas dans la sortie.\n"
    "Échec : le message d'erreur recopié, le fichier, et la ligne seulement si la sortie la donne. "
    "Succès : les résultats utiles, chiffres en chiffres.\n"
    "Recopie les noms, les nombres et les messages exactement comme dans la sortie. Ne donne jamais "
    "une cause, une explication ni une solution que la sortie n'écrit pas : si la sortie ne dit pas "
    "pourquoi, ne le dis pas. Ne répète ni le statut, ni la durée, ni le nombre de lignes affichées : "
    "ils sont déjà dits.\n"
    "Pas de markdown, pas de guillemets, pas de chemin complet si un nom suffit, ne répète pas la commande."
)
TRAIN_PROGRESS_SYSTEM = (
    "Une commande longue est en cours sur un terminal. Tu lis les dernières lignes affichées "
    "et tu dis, en français, ce qu'elle est en train de faire maintenant. Une phrase courte, "
    "12 mots au plus. N'invente jamais ce qui n'est pas écrit."
)
TRAIN_START_SYSTEM = (
    "Tu lis une commande de terminal, avant son exécution, et tu dis en français ce qu'elle va "
    "faire. 10 mots au plus, commence par un verbe à l'infinitif ou un nom. N'invente jamais."
)
# résidu résumé (erreurs multiples / tests non résolus en code) : même tâche, même
# corpus final que le résumé existant -> même prompt d'entraînement que label.py.
from label import TRAIN_SYSTEM as TRAIN_SUMMARY_SYSTEM  # noqa: E402

MODES = {
    # mode: (prompt d'entraînement, plafond de mots du gabarit de production)
    "detail": (TRAIN_DETAILS_SYSTEM, 60),
    "start": (TRAIN_START_SYSTEM, 10),
    "progress": (TRAIN_PROGRESS_SYSTEM, 12),
    "flux": (TRAIN_PROGRESS_SYSTEM, 12),
    "summary": (TRAIN_SUMMARY_SYSTEM, 25),
}


TEACHER_SYSTEM = {"detail": TEACHER_DETAILS_SYSTEM}

# R1 : mêmes consignes en anglais, pour les entrées anglaises de build_feature_corpus.py --lang en
# (prompts de production *_SYSTEM_EN) ; les prompts français ci-dessus restent ceux de la production.
TRAIN_DETAILS_SYSTEM_EN = (
    "You read the output of a terminal command and give its detail, in English. "
    "Answer in 1 to 5 short points separated by periods, 60 words at most: the useful facts, "
    "not the whole output. Copy names, numbers and error messages exactly as in the output. "
    "Never give a cause, an explanation or a fix that the output does not write: if the output "
    "does not say why, do not say it. Do not repeat the status, the duration or the number of lines. "
    "Never invent."
)
TEACHER_DETAILS_SYSTEM_EN = (
    "You are the voice of a terminal, for a visually impaired person who asked for the detail of "
    "the last command.\n"
    "You get the command, its status and its output. Answer in telegraphic style: keywords only, "
    "never a full sentence, no article, no politeness; 60 words maximum, in 1 to 5 points separated "
    "by periods: the useful facts, not the whole output. Fewer points rather than a point that is not "
    "in the output.\n"
    "Failure: the error message copied, the file, and the line only if the output gives it. "
    "Success: the useful results, digits as digits.\n"
    "Copy names, numbers and messages exactly as in the output. Never give a cause, an explanation "
    "or a fix that the output does not write: if the output does not say why, do not say it. Do not "
    "repeat the status, the duration or the number of lines displayed: they are already said.\n"
    "No markdown, no quotes, no full path if a name is enough, do not repeat the command."
)
TRAIN_PROGRESS_SYSTEM_EN = (
    "A long command is running in a terminal. You read the last lines displayed and say, "
    "in English, what it is doing right now. One short sentence, 12 words at most. "
    "Never invent what is not written."
)
TRAIN_START_SYSTEM_EN = (
    "You read a terminal command, before it runs, and say in English what it will do. "
    "10 words at most, start with an infinitive verb or a noun. Never invent."
)
from label import TRAIN_SYSTEM_EN as TRAIN_SUMMARY_SYSTEM_EN  # noqa: E402

MODES_EN = {
    "detail": (TRAIN_DETAILS_SYSTEM_EN, 60),
    "start": (TRAIN_START_SYSTEM_EN, 10),
    "progress": (TRAIN_PROGRESS_SYSTEM_EN, 12),
    "flux": (TRAIN_PROGRESS_SYSTEM_EN, 12),
    "summary": (TRAIN_SUMMARY_SYSTEM_EN, 25),
}
MODES_BY_LANG = {"fr": MODES, "en": MODES_EN}
TEACHER_SYSTEM_BY_LANG = {"fr": TEACHER_SYSTEM, "en": {"detail": TEACHER_DETAILS_SYSTEM_EN}}


def teacher_messages(row: dict, mode: str, lang: str = "fr") -> list[dict]:
    """Messages envoyés à l'enseignant : ceux de la ligne, système remplacé quand le mode en a un."""
    system = TEACHER_SYSTEM_BY_LANG[lang].get(mode)
    if system is None:
        return row["messages"]
    return [{"role": "system", "content": system}, *row["messages"][1:]]


def judge(raw: str, max_words: int, mode: str | None = None) -> tuple[str | None, str]:
    """Même grille de rejet que label.py:judge(), plafond de mots paramétrable par mode."""
    if "<think>" in raw:
        return None, "think"
    text = clean(raw, points=mode == "detail")
    if not text.strip():
        return None, "vide"
    if len(text.split()) > max_words:
        return None, "trop long"
    return text, "ok"


def run(args) -> None:
    lang = getattr(args, "lang", "fr")
    train_system, max_words = MODES_BY_LANG[lang][args.mode]
    rows = [json.loads(l) for l in open(args.infile, encoding="utf-8") if l.strip()]
    bad_mode = [r.get("mode") for r in rows if r.get("mode") != args.mode]
    if bad_mode:
        print(f"refus : {args.infile} contient des lignes de mode {set(bad_mode)}, "
              f"attendu {args.mode!r} partout", file=sys.stderr)
        raise SystemExit(2)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    rejects = out.with_suffix(".rejects.jsonl")
    seen = done_ids(out, rejects)
    todo = [r for r in rows if r["id"] not in seen]
    print(f"{len(rows)} entrées, {len(seen)} déjà faites, {len(todo)} à faire", flush=True)
    if not todo:
        return

    writer, rej_writer = Writer(out), Writer(rejects)
    counts = {"ok": 0, "think": 0, "vide": 0, "trop long": 0, "erreur": 0}
    import threading
    lock = threading.Lock()

    def work(row: dict) -> None:
        try:
            raw = query(args.port, teacher_messages(row, args.mode, lang), args.max_tokens, args.timeout, args.presence_penalty)
            label, reason = judge(raw, max_words, args.mode)
        except Exception as e:
            with lock:
                counts["erreur"] += 1
            rej_writer.write({"id": row["id"], "reason": f"erreur: {e!r}"})
            return
        with lock:
            counts[reason] += 1
        if label is None:
            rej_writer.write({"id": row["id"], "reason": reason, "raw": raw[:300]})
            return
        train_msgs = [{"role": "system", "content": train_system},
                      {"role": "user", "content": row["messages"][1]["content"]},
                      {"role": "assistant", "content": label}]
        writer.write({**row, "label": label, "train_messages": train_msgs})

    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.parallel) as ex:
        list(ex.map(work, todo))
    elapsed = time.time() - t0
    writer.close()
    rej_writer.close()
    rate = len(todo) / elapsed * 60 if elapsed else 0.0
    print(json.dumps({"mode": args.mode, "traites": len(todo), "elapsed_s": round(elapsed, 1),
                      "par_min": round(rate, 1), **counts}, ensure_ascii=False))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--in", dest="infile", required=True)
    ap.add_argument("--mode", required=True, choices=sorted(MODES))
    ap.add_argument("--out", required=True)
    ap.add_argument("--port", type=int, default=8890)
    ap.add_argument("--parallel", type=int, default=4)
    ap.add_argument("--max-tokens", type=int, default=120)
    ap.add_argument("--timeout", type=float, default=60.0)
    ap.add_argument("--presence-penalty", type=float, default=1.0)
    ap.add_argument("--lang", choices=("fr", "en"), default="fr", help="en : prompts d'entraînement TRAIN_*_EN")
    args = ap.parse_args()
    run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
