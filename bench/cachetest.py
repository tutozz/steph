import json, sys, time, os, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from steph.config import load_config
from steph.llm import LLM
from steph.textproc import compact_output
fx = json.load(open("fixtures.json")) + json.load(open("extra_fixtures.json"))
hist = "\n\n".join(f"[{i}] $ {f['cmd']} (code {f['exit']})\n{compact_output(f['output'].splitlines(), 1200)}" for i, f in enumerate(fx))
print("chars", len(hist))
cfg = load_config(); cfg.model = os.path.expanduser("~/.local/share/steph/models/" + sys.argv[1]); cfg.llm_port = 8799
llm = LLM(cfg); llm.pidfile = llm.pidfile.with_name("bench.pid"); llm.ensure_server(120)
import urllib.request
def ask(q, extra=""):
    msgs = [{"role":"system","content":"Tu es l'assistant d'un terminal. Réponds en français en 2 phrases max."},
            {"role":"user","content":"Historique :\n"+hist+extra},{"role":"assistant","content":"OK."},{"role":"user","content":q}]
    body = {"messages":msgs,"max_tokens":80,"temperature":0.2,"cache_prompt":True,"id_slot":1,"chat_template_kwargs":{"enable_thinking":False}}
    t=time.time(); r=json.load(urllib.request.urlopen(urllib.request.Request(llm.base+"/v1/chat/completions",data=json.dumps(body).encode(),headers={"Content-Type":"application/json"})))
    tm = r.get("timings",{})
    print(f"{time.time()-t:.2f}s prompt_n={tm.get('prompt_n')} cache_n={tm.get('cache_n')} | {r['choices'][0]['message']['content'][:150]}")
ask("Pourquoi git push a échoué ?")
ask("Combien de conteneurs docker tournent ?")
ask("Quelle commande a échoué en premier ?", "\n\n[99] $ echo test (code 0)\ntest")
ask("Et celle d'avant ?", "\n\n[99] $ echo test (code 0)\ntest")
llm.stop_server()
