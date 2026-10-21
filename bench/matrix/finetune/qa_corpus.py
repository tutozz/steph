"""Compose synthetic QA training sessions from the existing raw corpus (P15a).

Builds sessions of 2 to 6 commands with steph's own Session and Narrator.qa_messages(),
plus the question line of server._ask (production_qa_messages) : steph itself is read-only
here, never edited. Asks the Qwen3.5 9B teacher
a question about each session, keeps the answer only if the A7 2-pass judge
(judge_lib.call_judge, same method as label.py/run_fixed.py) finds no invented
fact. About a third of the questions target a fact absent from the session : the
expected answer is then the canonical phrase steph already uses (QA_SYSTEM),
« Pas dans l'historique. ».

    python3 qa_corpus.py --corpus corpus1.jsonl corpus2.jsonl [corpus3.jsonl ...] \\
        --bench cases.json --out qa_train.jsonl --n 160 \\
        --teacher-port 8890 --judge-port 8931

Resume : question keys already written to --out are skipped, like label.py's
done_ids(). The output file contains corpus text : it stays on the machine.

SPDX-License-Identifier: MIT
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
import urllib.request
from pathlib import Path

# score.clean() lives one level up (bench/matrix/score.py), same relative
# position once this file is deployed next to label.py on a labeling machine.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from score import clean

try:
    import steph  # noqa: F401
except ImportError:
    _HERE = Path(__file__).resolve()
    for _candidate in (_HERE.parents[3] / "src", _HERE.parents[2]):
        if (_candidate / "steph").is_dir():
            sys.path.insert(0, str(_candidate))
            break

from steph.prompts import QA_SYSTEM, QA_SYSTEM_EN
from steph.strings import t as tr

CANONICAL_ABSENT = "Pas dans l'historique."
CANONICAL_ABSENT_BY_LANG = {"fr": CANONICAL_ABSENT, "en": "Not in the history."}
QA_SYSTEM_BY_LANG = {"fr": QA_SYSTEM, "en": QA_SYSTEM_EN}
MAX_WORDS = 25  # même gabarit télégraphique que label.py (QA_SYSTEM : 25 mots sauf détail)
DEFAULT_BLOCK_CHARS = 2500  # cfg.qa_block_chars
DEFAULT_BUDGET_CHARS = 8000  # plafond décidé en H2 pour ce futur corpus de questions

ABSENT_TOOLS = ("python3", "node", "ruby", "java", "go", "cargo", "docker", "psql", "mysql")

PRESENT_TEMPLATES = {
    "status": lambda c: f"La commande « {c['cmd']} » a-t-elle réussi ?",
    "exit_code": lambda c: f"Quel est le code de sortie de « {c['cmd']} » ?",
    "count_lines": lambda c: f"Combien de lignes a affichées « {c['cmd']} » ?",
    "duration": lambda c: f"Combien de temps a duré « {c['cmd']} » ?",
}
ERROR_TEMPLATE = lambda c: f"Pourquoi « {c['cmd']} » a-t-elle échoué ?"
WHICH_LAST_TEMPLATE = "Quelle a été la dernière commande exécutée ?"
WHICH_FAILED_TEMPLATE = "Quelle commande a échoué ?"

ABSENT_TEMPLATES = {
    "status": lambda c: f"La commande « {c['cmd']} » a-t-elle réussi ?",
    "count_lines": lambda c: f"Combien de lignes a affichées « {c['cmd']} » ?",
    "exit_code": lambda c: f"Quel est le code de sortie de « {c['cmd']} » ?",
}
VERSION_TEMPLATE = lambda tool: f"Quelle version de {tool} est installée ?"

PRESENT_TEMPLATES_EN = {
    "status": lambda c: f"Did the command \"{c['cmd']}\" succeed?",
    "exit_code": lambda c: f"What is the exit code of \"{c['cmd']}\"?",
    "count_lines": lambda c: f"How many lines did \"{c['cmd']}\" print?",
    "duration": lambda c: f"How long did \"{c['cmd']}\" take?",
}
TEMPLATES = {
    "fr": {"present": PRESENT_TEMPLATES, "absent": ABSENT_TEMPLATES, "error": ERROR_TEMPLATE,
           "which_last": WHICH_LAST_TEMPLATE, "which_failed": WHICH_FAILED_TEMPLATE, "version": VERSION_TEMPLATE},
    "en": {"present": PRESENT_TEMPLATES_EN,
           "absent": {k: PRESENT_TEMPLATES_EN[k] for k in ABSENT_TEMPLATES},
           "error": lambda c: f"Why did \"{c['cmd']}\" fail?",
           "which_last": "What was the last command run?", "which_failed": "Which command failed?",
           "version": lambda tool: f"What version of {tool} is installed?"},
}


# --------------------------------------------------------------------------- format historique
def qa_prefix_messages(ctx: str, lang: str = "fr") -> list[dict]:
    """Reproduit exactement Narrator.qa_messages() (narrator.py:311-323), sans historique de questions.

    Le bloc d'historique (session._block) ne dépend pas de la langue en production : seuls le
    prompt système, l'en-tête et l'accusé de réception changent.
    """
    return [
        {"role": "system", "content": QA_SYSTEM_BY_LANG[lang]},
        {"role": "user", "content": tr(lang, "qa_history_header").format(ctx=ctx)},
        {"role": "assistant", "content": tr(lang, "qa_history_ack")},
    ]


QUESTION_PREFIX = "(dossier actuel : {cwd})\n{question}"  # server._ask, en français dans les deux langues
SESSION_CWDS = ("~", "~/projet", "~/src/app", "~/Documents", "~/work/api", "/tmp")


def production_qa_messages(records: list[dict], cwd: str, question: str, lang: str = "fr",
                           block_chars: int = DEFAULT_BLOCK_CHARS) -> list[dict]:
    """Entrée exacte d'une question en production, profil affiné (P20) : la Session de steph est
    remplie commande par commande et l'historique relu après chacune, comme le préchauffage, pour
    que les blocs anciens soient coupés au fil de l'eau ; puis Narrator.qa_messages() et la
    question de server._ask. `records` : cmd, exit, duration, output, et cwd facultatif."""
    from steph.config import Config
    from steph.narrator import Narrator
    from steph.session import Session

    s = Session()
    nar = Narrator(Config(language=lang, llm_profile="finetuned", qa_block_chars=block_chars), s, None, None)
    for r in records:
        s.cwd = r.get("cwd", cwd)
        c = s.start(r["cmd"])
        if r["output"]:
            c.feed((r["output"] if r["output"].endswith("\n") else r["output"] + "\n").encode())
        c.start, c.end, c.exit = 1e9, 1e9 + r["duration"], r["exit"]
        nar.qa_messages()
    s.cwd = cwd
    return nar.qa_messages() + [{"role": "user", "content": QUESTION_PREFIX.format(cwd=cwd, question=question)}]


# --------------------------------------------------------------------------- exclusion banc
def output_lines(text: str) -> set[str]:
    """Reproduit compose_train.py:output_lines() : lignes de sortie >= 24 caractères."""
    out = text.split("Sortie :\n", 1)[-1]
    return {line.strip() for line in out.splitlines() if len(line.strip()) >= 24}


def bench_lines(bench_cases: list[dict]) -> set[str]:
    lines: set[str] = set()
    for case in bench_cases:
        lines |= output_lines(case["messages"][-1]["content"])
    return lines


def is_bench_contaminated(output: str, banned_lines: set[str]) -> bool:
    """Reproduit compose_train.py : contaminé si >= 2 lignes partagées avec le banc."""
    if not banned_lines:
        return False
    return len(output_lines("Sortie :\n" + output) & banned_lines) >= 2


# --------------------------------------------------------------------------- sessions
def pick_sessions(records: list[dict], rng: random.Random, n_sessions: int,
                   min_cmds: int = 2, max_cmds: int = 6) -> list[list[dict]]:
    sessions = []
    n = len(records)
    for _ in range(n_sessions):
        size = min(rng.randint(min_cmds, max_cmds), n)
        sessions.append(rng.sample(records, size))
    return sessions


# --------------------------------------------------------------------------- questions
def make_present_question(session: list[dict], rng: random.Random, lang: str = "fr",
                          error_weight: int = 1) -> tuple[str, str]:
    tpl = TEMPLATES[lang]
    failed = [r for r in session if r["exit"] != 0]
    categories = list(tpl["present"]) + ["which_last"]
    if failed:
        categories += ["error_cause"] * error_weight + ["which_failed"]
    category = rng.choice(categories)
    if category == "which_last":
        return category, tpl["which_last"]
    if category == "which_failed":
        return category, tpl["which_failed"]
    if category == "error_cause":
        return category, tpl["error"](rng.choice(failed))
    target = rng.choice(session)
    return category, tpl["present"][category](target)


def make_absent_question(session: list[dict], pool: list[dict], rng: random.Random,
                         lang: str = "fr") -> tuple[str, str, dict | None]:
    """pool : autres enregistrements du corpus, absents de `session` (candidats de distraction)."""
    session_cmds = {r["cmd"] for r in session}
    session_first_words = {r["cmd"].split()[0] for r in session if r["cmd"].split()}
    outside_pool = [r for r in pool if r["cmd"] not in session_cmds]
    use_distractor = outside_pool and rng.random() < 0.6
    if use_distractor:
        target = rng.choice(outside_pool)
        templates = TEMPLATES[lang]["absent"]
        category = rng.choice(list(templates))
        return "absent", templates[category](target), target
    missing_tools = [t for t in ABSENT_TOOLS if t not in session_first_words]
    tool = rng.choice(missing_tools or list(ABSENT_TOOLS))
    return "absent", TEMPLATES[lang]["version"](tool), None


# --------------------------------------------------------------------------- juge / verdict
def combine_verdicts(a: str, b: str) -> str:
    """Reproduit run_fixed.py:process_one() : accord requis sur les 2 passes pour trancher."""
    if a == "invention" and b == "invention":
        return "invention"
    if a == "invention" or b == "invention":
        return "douteux"
    return "ok"


def clean_answer(raw: str) -> tuple[str | None, str]:
    """Même gate que label.py:judge() : <think>, vide, trop long -> rejeté avant même le juge."""
    if "<think>" in raw:
        return None, "think"
    text = clean(raw)
    if not text.strip():
        return None, "vide"
    if len(text.split()) > MAX_WORDS:
        return None, "trop long"
    return text, "ok"


ABSTENTION_PREFIXES = ("pas dans l'historique", "introuvable dans l'historique", "aucune information dans l'historique",
                       "not in the history", "not found in the history", "no information in the history")


def is_abstention(text: str) -> bool:
    t = text.strip().lower()
    return any(t.startswith(p) for p in ABSTENTION_PREFIXES)


def decide_label(category: str, raw_answer: str, verdict: str, lang: str = "fr") -> str | None:
    """verdict : 'ok' (juge 2 passes, voir combine_verdicts) ; tout le reste est rejeté.

    Catégorie 'absent' : le juge à 'ok' garantit qu'aucun fait non ancré n'a été affirmé
    (le prompt du juge traite « Pas dans l'historique. » comme non-invention) ; on force
    alors la formulation canonique de steph plutôt que de garder la paraphrase du
    professeur, pour que le petit modèle apprenne une réponse unique et stable.

    Catégorie != 'absent' : le juge ne vérifie QUE les faits affirmés à tort (invention),
    jamais un refus injustifié. Un professeur qui répond « Pas dans l'historique. » à une
    question dont la réponse est bien dans le contexte envoyé passe donc son verdict 'ok'
    sans que ce soit un fait vrai à apprendre : rejeté ici, séparément du juge.
    """
    if verdict != "ok":
        return None
    if category == "absent":
        return CANONICAL_ABSENT_BY_LANG[lang]
    if is_abstention(raw_answer) or any(p in raw_answer.lower() for p in ABSTENTION_PREFIXES):
        return None
    return raw_answer


def build_example(prefix_messages: list[dict], question: str, answer: str, source: str = "qa-synth",
                  lang: str = "fr") -> dict:
    # suffixe « .en » : convention de build_dataset_release.language_for_source
    return {"source": source + (".en" if lang == "en" else ""), "messages": [*prefix_messages,
                                            {"role": "user", "content": question},
                                            {"role": "assistant", "content": answer}]}


def session_key(ctx: str, question: str) -> str:
    return hashlib.sha256((ctx + "\x00" + question).encode()).hexdigest()


# --------------------------------------------------------------------------- I/O corpus
def read_records(paths: list[Path]) -> list[dict]:
    records = []
    for p in paths:
        with p.open(encoding="utf-8") as f:
            for i, line in enumerate(f):
                if not line.strip():
                    continue
                r = json.loads(line)
                r["id"] = f"{r.get('machine', p.stem)}:{i}"
                records.append(r)
    return records


# --------------------------------------------------------------------------- réseau (teacher + juge)
def query_teacher(port: int, messages: list[dict], max_tokens: int = 100, timeout: float = 60.0,
                   presence_penalty: float = 1.0) -> str:
    """Même requête que label.py:query() : température 0, enable_thinking=false."""
    body = json.dumps({
        "messages": messages, "max_tokens": max_tokens, "temperature": 0, "top_p": 0.9,
        "presence_penalty": presence_penalty,
        "stream": False, "cache_prompt": True, "chat_template_kwargs": {"enable_thinking": False},
    }).encode()
    req = urllib.request.Request(f"http://127.0.0.1:{port}/v1/chat/completions", body,
                                  {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read())
    return data["choices"][0]["message"]["content"]


QUESTION_LABEL = {"fr": "Question : ", "en": "Question: "}


def judge_answer(call_judge, ctx: str, phrase: str, question: str, lang: str = "fr") -> str:
    """call_judge : judge_lib.call_judge (injecté, jamais importé ici pour garder ce module testable sans judge_lib).

    Le juge reçoit l'historique suivi de la question, comme le modèle : sans elle, une réponse
    fausse mais ancrée dans l'historique passait toujours (X4a).
    """
    ctx = f"{ctx}\n\n{QUESTION_LABEL[lang]}{question}"
    a = call_judge(ctx, phrase, pass_id="A")["verdict"]
    b = call_judge(ctx, phrase, pass_id="B")["verdict"]
    return combine_verdicts(a, b)


# --------------------------------------------------------------------------- CLI
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", nargs="+", required=True, type=Path)
    ap.add_argument("--bench", nargs="*", default=[], type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--n", type=int, default=160, help="exemples visés (avant rejet du juge)")
    ap.add_argument("--absent-ratio", type=float, default=1 / 3)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--teacher-port", type=int, default=8890)
    ap.add_argument("--judge-port", type=int, default=8931)  # non utilisé directement : judge_lib.PORT
    ap.add_argument("--min-cmds", type=int, default=2)
    ap.add_argument("--max-cmds", type=int, default=6)
    ap.add_argument("--block-chars", type=int, default=DEFAULT_BLOCK_CHARS)
    ap.add_argument("--parallel", type=int, default=4)
    ap.add_argument("--lang", choices=("fr", "en"), default="fr")
    ap.add_argument("--error-weight", type=int, default=1, help="poids de « pourquoi a-t-elle échoué » (banc qa0)")
    args = ap.parse_args()

    from judge_lib import call_judge  # import tardif : seule main() en a besoin

    records = read_records(args.corpus)
    bench_cases = [c for p in args.bench for c in json.loads(p.read_text())]
    banned = bench_lines(bench_cases)
    before = len(records)
    records = [r for r in records if not is_bench_contaminated(r["output"], banned)]
    print(f"{len(records)} enregistrements ({before - len(records)} écartés, contamination banc)", flush=True)

    rng = random.Random(args.seed)
    n_absent = round(args.n * args.absent_ratio)
    n_present = args.n - n_absent
    sessions_present = pick_sessions(records, rng, n_present, args.min_cmds, args.max_cmds)
    sessions_absent = pick_sessions(records, rng, n_absent, args.min_cmds, args.max_cmds)

    done = set()
    if args.out.exists():
        for line in args.out.open(encoding="utf-8"):
            if line.strip():
                done.add(json.loads(line)["_key"])

    stats = {"ok": 0, "rejet_teacher": 0, "rejet_juge": 0, "deja_fait": 0}
    with args.out.open("a", encoding="utf-8") as out:
        for kind, sessions in (("present", sessions_present), ("absent", sessions_absent)):
            for session in sessions:
                if kind == "present":
                    category, question = make_present_question(session, rng, args.lang, args.error_weight)
                else:
                    category, question, _ = make_absent_question(session, records, rng, args.lang)
                cwd = rng.choice(SESSION_CWDS)
                msgs = production_qa_messages(session, cwd, question, args.lang, args.block_chars)
                prefix, ctx = msgs[:-1], msgs[1]["content"]
                key = session_key(ctx, question)
                if key in done:
                    stats["deja_fait"] += 1
                    continue
                raw = query_teacher(args.teacher_port, msgs)
                cleaned, _reason = clean_answer(raw)
                if cleaned is None:
                    stats["rejet_teacher"] += 1
                    continue
                verdict = judge_answer(call_judge, ctx, cleaned, question, args.lang)
                label = decide_label(category, cleaned, verdict, args.lang)
                if label is None:
                    stats["rejet_juge"] += 1
                    continue
                row = build_example(prefix, msgs[-1]["content"], label, lang=args.lang)
                row["_key"] = key
                row["_category"] = category
                out.write(json.dumps(row, ensure_ascii=False) + "\n")
                out.flush()
                stats["ok"] += 1

    print(json.dumps(stats, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
