"""Runs the delivered small model through the production question flow on bench sessions.

    uv run python docs/readme-charts/ask_demo.py   (one llama-server, stopped at the end)

Same path as steph.server._ask: Narrator.qa_messages (profile finetuned), temperature 0.3,
max_tokens 400, clean_llm_text, then the grounding guard. Only the seed is added, to replay.
"""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

from steph.config import Config
from steph.digest import resolve
from steph.grounding import ground_stream
from steph.llm import LLM
from steph.narrator import Narrator, clean_llm_text
from steph.session import Session

ROOT = Path(__file__).resolve().parents[2]
MODEL = ROOT / "release/hf/steph-speak-granite-4.0-h-350M-v2-GGUF/steph-speak-granite-4.0-h-350M-sft-v2.0-Q4_K_M.gguf"
CWD = "/home/alice/Projects/steph"
FIXTURES = json.load(open(ROOT / "bench/fixtures.json")) + json.load(open(ROOT / "bench/extra_fixtures.json"))
SESSIONS = {"A": [27, 24, 25, 1], "B": [28, 22, 26, 1]}
QUESTIONS = [("A", "Pourquoi le build a échoué ?"), ("A", "Combien de paquets ont été mis à jour ?"),
             ("A", "Pourquoi l'installation de nginx a échoué ?"), ("A", "Il reste combien de place sur le disque ?"),
             ("B", "Pourquoi git push a échoué ?"), ("B", "Combien de conteneurs tournent ?"),
             ("B", "Quelle version de requests a été installée ?"), ("B", "Quelle version de Python est installée ?")]


class SeededLLM(LLM):
    def _payload(self, *a, **k):
        p = super()._payload(*a, **k)
        p["seed"] = 42
        return p


def session(ids):
    s = Session()
    s.cwd = CWD
    for i in ids:
        f = FIXTURES[i]
        c = s.start(f["cmd"])
        c.feed(f["output"].replace("\n", "\r\n").encode())
        c.end, c.exit = c.start + f["duration"], f["exit"]
    return s


def main() -> None:
    cfg = Config(model=str(MODEL), llm_profile="finetuned", llm_port=8799)
    llm = SeededLLM(cfg)
    if not llm.ensure_server(120):
        sys.exit("llama-server did not start")
    rows = []
    try:
        for key, q in QUESTIONS:
            s = session(SESSIONS[key])
            nar = SimpleNamespace(cfg=cfg, s=s)
            prefix = Narrator.qa_messages(nar)
            msgs = prefix + [{"role": "user", "content": f"(dossier actuel : {s.cwd})\n{q}"}]
            history = s.context(cfg.qa_block_chars, cfg.qa_budget_chars)
            out = "".join(clean_llm_text(llm.stream(msgs, max_tokens=400, temperature=0.3, timeout=120, slot=1))).strip()
            grounded = "".join(ground_stream(iter([out]), history, is_qa=True, language="fr")).strip()
            rows.append({"session": key, "commands": [FIXTURES[i]["cmd"] for i in SESSIONS[key]], "question": q,
                         "out": out, "grounded": grounded})
            print(key, q, "|", out, "|", grounded, flush=True)
        f = FIXTURES[17]
        print("resolve fx17:", resolve(f["cmd"], f["exit"], f["output"]), "|", resolve(f["cmd"], f["exit"], f["output"], "en"))
    finally:
        llm.stop_server()
    Path("/tmp/z3s/ask.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1))


main()
