"""Benchmark des modèles : latence (1er token, total) + réponses, pour jugement."""
import json, sys, time, subprocess, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from steph.config import load_config
from steph.llm import LLM
from steph.prompts import summary_messages
from steph.textproc import compact_output

fx = json.load(open("fixtures.json")) + json.load(open("extra_fixtures.json"))
models = sys.argv[1:]
cfg = load_config()
res = {}
for m in models:
    cfg.model = os.path.expanduser(f"~/.local/share/steph/models/{m}")
    cfg.llm_port = 8799
    llm = LLM(cfg); llm.pidfile = llm.pidfile.with_name("bench.pid")
    t0 = time.time(); ok = llm.ensure_server(120); load = time.time() - t0
    if not ok: print("LOAD FAIL", m); llm.stop_server(); continue
    llm.complete([{"role":"user","content":"Bonjour"}], 5)  # warmup
    rows = []
    for f in fx:
        lines = f["output"].splitlines()
        msgs = summary_messages(f["cmd"], f["exit"], f["duration"], compact_output(lines, int(os.environ.get('MAXC','6000'))), len(lines))
        t = time.time(); first = None; txt = ""
        for piece in llm.stream(msgs, 80):
            if first is None: first = time.time() - t
            txt += piece
        rows.append({"cmd": f["cmd"], "ttft": round(first or 0, 3), "total": round(time.time()-t, 3), "out": txt.strip()})
    llm.stop_server(); time.sleep(2)
    res[m] = {"load": round(load,1), "rows": rows}
    tt = [r["ttft"] for r in rows]; tot = [r["total"] for r in rows]
    print(f"### {m}: load {load:.1f}s  ttft moy {sum(tt)/len(tt):.3f}s  max {max(tt):.3f}  total moy {sum(tot)/len(tot):.2f}s")
    for r in rows: print(f"  [{r['total']:.2f}s] {r['cmd'][:45]:45} -> {r['out']}")
    sys.stdout.flush()
json.dump(res, open(f"results-{int(time.time())}.json","w"), ensure_ascii=False, indent=1)
