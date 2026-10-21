"""Mesure complémentaire à p14a_harness.py : coût du tampon d'ancrage (P13) isolé de la
synthèse Piper. Sur les mêmes messages (TRAIN_SYSTEM + digest, comme le harnais principal),
un seul passage de génération réelle est chronométré à deux points de la même chaîne (pas de
second appel : la température 0.2 rendrait deux générations non comparables) :
  - t_clean  : premier morceau après `clean_llm_text` (~ premier jeton brut du modèle) ;
  - t_final  : premier morceau après la chaîne réelle de `_llm_say`
               (clean_llm_text -> ground_stream si ground_output -> _drop_leading_status).
Le delta t_final - t_clean est le coût combiné du garde-fou d'ancrage P13 et du retrait du
statut P9 sur le premier mot effectivement parlé (P13 est le terme dominant : le tampon P9
porte sur ~12 caractères, celui de P13 sur une proposition entière).
"""
from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, "/root/p14a-work")
os.environ.setdefault("PULSE_SERVER", "unix:/run/user/1000/pulse/native")

from steph.config import Config
from steph.llm import LLM
from steph.narrator import clean_llm_text, _drop_leading_status
from steph.grounding import ground_stream
import steph.prompts as prompts_mod
import steph.digest as digest_mod

TRAIN_SYSTEM = (
    "Tu lis la sortie d'une commande de terminal et tu dis à voix haute l'essentiel, en français. "
    "Réponds par une seule ligne courte, 15 mots au plus : d'abord le résultat, puis un détail utile. "
    "Recopie les noms et les nombres exactement comme dans la sortie. Si une information n'est pas "
    "écrite dans la sortie, ne la donne pas : n'invente jamais."
)
_orig_summary_messages = prompts_mod.summary_messages


def _train_summary_messages(cmd, exit_code, duration, output, nlines, cwd="", language="fr"):
    msgs = _orig_summary_messages(cmd, exit_code, duration, output, nlines, cwd, language=language)
    msgs[0] = {"role": "system", "content": TRAIN_SYSTEM}
    return msgs


prompts_mod.summary_messages = _train_summary_messages


def build_fixture_table(fixtures_dir: str) -> list[dict]:
    fx = json.load(open(os.path.join(fixtures_dir, "fixtures.json"), encoding="utf-8"))
    fx += json.load(open(os.path.join(fixtures_dir, "extra_fixtures.json"), encoding="utf-8"))
    byid = {}
    for i, f in enumerate(fx):
        cid = f.get("id") or f"fx{i:02d}"
        byid[cid] = f
    df = open(os.path.join(fixtures_dir, "df_proxmox.txt"), encoding="utf-8").read()
    ipa = open(os.path.join(fixtures_dir, "ip_a_proxmox.txt"), encoding="utf-8").read()
    byid["df_proxmox"] = {"cmd": "df -h", "exit": 0, "duration": 0.1, "output": df}
    byid["ip_a_proxmox"] = {"cmd": "ip a", "exit": 0, "duration": 0.1, "output": ipa}
    ids = [f"fx{i:02d}" for i in range(31)] + ["df_proxmox", "ip_a_proxmox"]
    return [{"id": cid, **byid[cid]} for cid in ids]


def main() -> int:
    cfg = Config()
    cfg.model = "/root/stephbench-ft/models/granite-soup-Q4_K_M.gguf"
    cfg.llama_server = "/root/stephbench-g2/bin/llama-b11205/llama-server"
    cfg.llm_port = 8972
    cfg.llm_ctx = 4096
    cfg.llm_extra_args = ["-t", "4"]

    llm = LLM(cfg)
    print("lancement llama-server...", file=sys.stderr)
    if not llm.ensure_server(90):
        print("échec démarrage serveur", file=sys.stderr)
        return 1
    print("prêt.", file=sys.stderr)

    fixtures = build_fixture_table("/root/p14a-work/fixtures")
    # chauffe cache slot 0 (hors mesure)
    llm.complete(_train_summary_messages("true", 0, 0.0, "", 0), max_tokens=1, slot=0)

    results = []
    for fx in fixtures:
        cmd, exit_code, duration, raw = fx["cmd"], fx["exit"], fx["duration"], fx["output"]
        lines = raw.splitlines()
        out = digest_mod.digest(cmd, raw, cfg.summary_chars, cfg.language)
        if out is None:
            from steph.textproc import compact_output
            out = compact_output(lines, cfg.summary_chars)
        msgs = prompts_mod.summary_messages(cmd, exit_code, duration, out, len(lines), language=cfg.language)
        input_text = msgs[1]["content"]

        box = {}
        t0 = time.time()

        def timed(gen, key):
            first = True
            for p in gen:
                if first:
                    box[key] = time.time()
                    first = False
                yield p

        raw_stream = llm.stream(msgs, max_tokens=90)
        cleaned = clean_llm_text(raw_stream, buffer_reasoning=cfg.buffer_reasoning)
        cleaned_timed = timed(cleaned, "t_clean")
        grounded = ground_stream(cleaned_timed, input_text, language=cfg.language) if cfg.ground_output else cleaned_timed
        final_stream = _drop_leading_status(grounded)
        pieces = []
        for i, p in enumerate(final_stream):
            if i == 0:
                box["t_final"] = time.time()
            pieces.append(p)
        text = "".join(pieces)

        t_clean = box.get("t_clean")
        t_final = box.get("t_final")
        rec = {
            "id": fx["id"],
            "t_clean_s": round(t_clean - t0, 4) if t_clean else None,
            "t_final_s": round(t_final - t0, 4) if t_final else None,
            "ground_cost_s": round(t_final - t_clean, 4) if (t_clean and t_final) else None,
            "output_text": text,
        }
        results.append(rec)
        print(f"{fx['id']:14s} t_clean={rec['t_clean_s']} t_final={rec['t_final_s']} "
              f"cout_tampon={rec['ground_cost_s']}", file=sys.stderr)

    out_path = "/root/p14a-work/out/p14a-ground-cost.json"
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    json.dump({"results": results}, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    costs = [r["ground_cost_s"] for r in results if r["ground_cost_s"] is not None]
    import statistics
    if costs:
        print(json.dumps({
            "n": len(costs), "median": round(statistics.median(costs), 4),
            "min": round(min(costs), 4), "max": round(max(costs), 4),
        }, ensure_ascii=False))

    llm.stop_server()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
