#!/usr/bin/env python3
"""P20 : latence et qualité des questions (F7) par le vrai chemin de steph, sur les questions du banc v3.

Chaque question rejoue sa session dans une vraie `Session`, puis passe par `Narrator.qa_messages`,
le préchauffage `_maybe_warm` et `ControlServer._ask` (ancrage compris), contre un llama-server déjà
lancé. Le haut-parleur est factice : il note l'instant où le premier morceau lui parvient
(« premier son » avant synthèse Piper) et le texte dit.

Régimes :
  cold    slot 1 vidé, aucun préchauffage : la question lit tout l'historique (cas R2-B1).
  warm    préchauffage de l'historique terminé avant la question ; en mode outils, une question
          précédente a lu le préfixe système + outils + liste des commandes.
  replay  commandes rejouées une à une, préchauffage après chacune comme en production ; la
          question part `--delay` secondes après la fin de la dernière commande, préchauffage
          encore en cours si l'historique ajouté est long.

    python3 p20_qa_latency.py --cases bench/matrix/v3/cases/dev/history-qa.jsonl --port 8972 \\
        --regime cold --out run.json [--ids a@fr,b@en] [--delay 5] [--qa-tools] [--seed 7]

`--qa-tools` (D4) : même chemin avec le réglage `qa_tools` ; chaque ligne note les appels d'outils
et le repli sur le mode actuel. `--seed` : graine ajoutée à chaque requête (banc de qualité).

Sortie : `rows` au format de bench_run.py (`id`, `out`), lisible par score_v3.py, plus `ttft`
(question -> premier morceau de réponse) et `first_speech` (question -> premier morceau au
haut-parleur).

SPDX-License-Identifier: MIT
"""

from __future__ import annotations

import argparse
import json
import queue
import re
import sys
import threading
import time
import urllib.request
from pathlib import Path

_HERE = Path(__file__).resolve()
for _candidate in (_HERE.parents[2] / "src", _HERE.parent / "pysrc"):
    if (_candidate / "steph").is_dir():
        sys.path.insert(0, str(_candidate))
        break

from steph.config import Config  # noqa: E402
from steph.llm import LLM  # noqa: E402
from steph import narrator  # noqa: E402
from steph import server as server_mod  # noqa: E402
from steph.narrator import Narrator  # noqa: E402
from steph.server import ControlServer  # noqa: E402
from steph.session import Session  # noqa: E402

HEAD = re.compile(r"^\[(\d+)\] (.*?) \$ ", re.M)
TOOL_LOG: list[dict] = []  # un élément par question en mode outils (D4)


def instrument(seed: int | None) -> None:
    """Graine sur toutes les requêtes, et relevé des tours d'outils sans toucher au code de steph."""
    payload, chat, ask_tools = LLM._payload, LLM.chat, server_mod.ask_with_tools

    def seeded(self, *a, **k):
        p = payload(self, *a, **k)
        if seed is not None:
            p["seed"] = seed
        return p

    def logged_chat(self, messages, tools=None, **k):
        msg = chat(self, messages, tools=tools, **k)
        if TOOL_LOG:
            TOOL_LOG[-1]["rounds"] += 1
            TOOL_LOG[-1]["names"] += [tc.get("function", {}).get("name") for tc in msg.get("tool_calls") or []]
        return msg

    def logged_ask(*a, **k):
        TOOL_LOG.append({"rounds": 0, "names": []})
        t = time.time()
        res = ask_tools(*a, **k)
        TOOL_LOG[-1].update(fallback=res is None, calls=res.calls if res else None, tools_s=round(time.time() - t, 3))
        return res

    LLM._payload, LLM.chat, server_mod.ask_with_tools = seeded, logged_chat, logged_ask


class FakeSpeaker:
    """Haut-parleur sans son : consomme les flux comme Speaker et note le premier morceau."""

    def __init__(self):
        self.speaking = threading.Event()
        self._q: queue.Queue = queue.Queue()
        self.first_at: float | None = None
        self.said: list[str] = []
        self._threads: list[threading.Thread] = []

    def say(self, text, interrupt=True, on_done=None, force=False):
        self.say_stream([text], interrupt, on_done, force)

    def say_stream(self, pieces, interrupt=True, on_done=None, force=False):
        def run():
            for p in pieces:
                if self.first_at is None and p.strip():
                    self.first_at = time.time()
                self.said.append(p)
            if on_done:
                on_done(True)
        th = threading.Thread(target=run, daemon=True)
        th.start()
        self._threads.append(th)

    def join(self):
        for th in self._threads:
            th.join(timeout=300)

    def stop(self):
        pass


def history_cwds(case: dict, lang: str) -> dict[int, str]:
    user = "\n".join(m["content"] for m in case["input"][lang] if m["role"] == "user")
    return {int(m.group(1)): m.group(2) for m in HEAD.finditer(user)}


def add_command(s: Session, case: dict, i: int, cwds: dict[int, str], t0: float) -> None:
    h = case["history"][i]
    s.cwd = cwds.get(i + 1) or next(iter(cwds.values()), "")
    c = s.start(h["cmd"])
    c.feed(h["output_raw"].encode())
    c.start = t0 + 10 * i
    c.end = c.start + h["duration_s"]
    c.exit = h["exit"]


def make_narrator(port: int, lang: str, profile: str, qa_tools: bool = False) -> tuple[Narrator, FakeSpeaker]:
    cfg = Config()
    cfg.qa_tools = qa_tools
    cfg.llm_profile = profile
    cfg.language = lang
    cfg.llm_port = port
    sp = FakeSpeaker()
    nar = Narrator(cfg, Session(), sp, LLM(cfg))
    nar.llm_ready = True
    return nar, sp


def erase_slot(port: int, slot: int = 1) -> None:
    req = urllib.request.Request(f"http://127.0.0.1:{port}/slots/{slot}?action=erase", b"{}",
                                 {"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=30).read()


def warm_and_wait(nar: Narrator) -> None:
    nar._warm_pending = True
    nar.llm.last_done = 0.0
    nar._maybe_warm()
    while nar._warming or nar._warm_pending:
        time.sleep(0.05)


def ask(nar: Narrator, sp: FakeSpeaker, question: str) -> dict:
    srv = ControlServer.__new__(ControlServer)
    srv.nar = nar
    t0 = time.time()
    first: list[float] = []
    text: list[str] = []

    def send(obj):
        if "t" in obj:
            if not first:
                first.append(time.time())
            text.append(obj["t"])
        return True

    sp.first_at = None
    sp.said.clear()
    srv._ask(question, send, speak=True)
    sp.join()
    return {"out": "".join(text).strip(), "ttft": round(first[0] - t0, 3) if first else None,
            "first_speech": round(sp.first_at - t0, 3) if sp.first_at else None,
            "said": "".join(sp.said).strip()}


def run_case(case: dict, lang: str, port: int, regime: str, delay: float, profile: str,
             qa_tools: bool = False) -> dict:
    nar, sp = make_narrator(port, lang, profile, qa_tools)
    cwds = history_cwds(case, lang)
    t0 = time.time() - 100000
    erase_slot(port)
    n = len(case["history"])
    if regime == "replay":
        for i in range(n):
            add_command(nar.s, case, i, cwds, t0)
            if i < n - 1:
                warm_and_wait(nar)
        nar._warm_pending = True
        nar.llm.last_done = 0.0
        nar._maybe_warm()
        time.sleep(delay)
    else:
        for i in range(n):
            add_command(nar.s, case, i, cwds, t0)
        if regime == "warm" and qa_tools:
            # mode outils : le préfixe utile est système + outils + liste des commandes, lu par une
            # question précédente sur la même session (steph ne le préchauffe pas encore)
            server_mod.ask_with_tools(nar.llm, nar.s, "ok", nar.cfg)
        elif regime == "warm":
            warm_and_wait(nar)
    nar.s.cwd = cwds.get(n) or next(iter(cwds.values()), "")
    prompt_chars = sum(len(m["content"]) for m in nar.qa_messages())
    logged = len(TOOL_LOG)
    res = ask(nar, sp, case["question"][lang])
    if len(TOOL_LOG) > logged:
        res["tools"] = TOOL_LOG[-1]
    while nar._warming:
        time.sleep(0.05)
    res["prompt_chars"] = prompt_chars
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", required=True)
    ap.add_argument("--port", type=int, default=8972)
    ap.add_argument("--regime", choices=("cold", "warm", "replay"), required=True)
    ap.add_argument("--delay", type=float, default=5.0)
    ap.add_argument("--ids", default="")
    ap.add_argument("--out", required=True)
    ap.add_argument("--budget", type=int, default=0, help="plafond d'historique à essayer (0 : celui de steph)")
    ap.add_argument("--profile", choices=("finetuned", "generic"), default="finetuned")
    ap.add_argument("--qa-tools", action="store_true", help="D4 : réglage qa_tools activé")
    ap.add_argument("--seed", type=int, default=None)
    a = ap.parse_args()
    instrument(a.seed)
    if a.budget:
        narrator.FINETUNED_QA_BUDGET_CHARS = a.budget
    only = set(filter(None, a.ids.split(",")))
    cases = [json.loads(line) for line in open(a.cases) if line.strip()]
    rows = []
    for case in cases:
        for lang in ("fr", "en"):
            rid = f"{case['id']}@{lang}"
            if only and rid not in only:
                continue
            r = run_case(case, lang, a.port, a.regime, a.delay, a.profile, a.qa_tools)
            r["id"] = rid
            rows.append(r)
            print(rid, r["ttft"], r["first_speech"], r["prompt_chars"], flush=True)
            json.dump({"regime": a.regime, "delay": a.delay, "budget": a.budget, "profile": a.profile,
                       "qa_tools": a.qa_tools, "seed": a.seed, "rows": rows}, open(a.out, "w"),
                      ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
