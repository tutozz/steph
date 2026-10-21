"""D4 prompt exploration on dev cases (not production code)."""
import json, sys, time, urllib.request
sys.path.insert(0, "/root/steph-ft/d4/pysrc")
from steph.session import Session
from steph.qa_tools import TOOLS, SessionTools
port, variant, out = int(sys.argv[1]), sys.argv[2], sys.argv[3]
idxs = [int(x) for x in sys.argv[4].split(",")]
cases = [json.loads(l) for l in open("/root/steph-ft/d4/history-qa.jsonl")]
SYS = {"fr": "Tu réponds aux questions sur une session de terminal. Tu reçois la liste des commandes, pas leurs sorties. Utilise les outils pour lire les sorties (3 appels au plus).",
       "en": "You answer questions about a terminal session. You get the list of commands, not their outputs. Use the tools to read the outputs (3 calls at most)."}
STYLE = {"fr": "Réponds maintenant en français, en style télégraphique : des mots-clés, 25 mots maximum, sans markdown. Base-toi seulement sur les résultats des outils ; si la réponse n'y est pas : « Pas dans l'historique. »",
         "en": "Now answer in English, in telegraphic style: keywords only, 25 words maximum, no markdown. Base your answer only on the tool results; if the answer is not there: \"Not in the history.\""}
HDR = {"fr": "Commandes de la session :\n", "en": "Session commands:\n"}
def post(msgs, **extra):
    body = {"messages": msgs, "tools": TOOLS, "max_tokens": 400, "temperature": 0.3, "top_p": 0.9, "stream": False, "seed": 7,
            "chat_template_kwargs": {"enable_thinking": False}, "id_slot": 1, "cache_prompt": True, **extra}
    d = json.loads(urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{port}/v1/chat/completions", json.dumps(body).encode(), {"Content-Type": "application/json"}), timeout=600).read())
    return d["choices"][0]["message"], d.get("usage", {})
rows = []
for i in idxs:
    case = cases[i]
    for lang in ("fr", "en"):
        s = Session(); s.cwd = case["cwd"]
        for h in case["history"]:
            c = s.start(h["cmd"]); c.feed(h["output_raw"].encode()); c.start, c.end, c.exit = 1e9, 1e9 + h["duration_s"], h["exit"]
        tools = SessionTools(s, lang)
        msgs = [{"role": "system", "content": SYS[lang]},
                {"role": "user", "content": HDR[lang] + tools.index() + f"\n\n(dossier actuel : {s.cwd})\n" + case["question"][lang]}]
        calls, rounds, trace, t0, usage = 0, 0, [], time.time(), []
        text = None
        while rounds < 6:
            extra = {}
            if variant in ("V2", "V3", "V4") and rounds == 0:
                extra["tool_choice"] = "required"
            m, u = post(msgs, **extra); rounds += 1; usage.append(u)
            tcs = m.get("tool_calls") or []
            if not tcs:
                text = (m.get("content") or "").strip()
                break
            if calls + len(tcs) > 3:
                text = None; break
            msgs.append({"role": "assistant", "content": m.get("content") or "", "tool_calls": tcs})
            for tc in tcs:
                args = json.loads(tc["function"]["arguments"] or "{}")
                if variant in ("V4", "V5") and tc["function"]["name"] == "get_output":
                    args["count"] = max(int(args.get("count") or 20), 20)
                res = tools.call(tc["function"]["name"], args)
                if variant in ("V1", "V4", "V5"):
                    res += "\n\n" + STYLE[lang]
                trace.append([tc["function"]["name"], args])
                msgs.append({"role": "tool", "tool_call_id": tc.get("id", ""), "name": tc["function"]["name"], "content": res})
                calls += 1
        first_text = text
        if variant == "V3" and text is not None:
            msgs.append({"role": "user", "content": STYLE[lang]})
            m, u = post(msgs, tool_choice="none"); rounds += 1; usage.append(u)
            text = (m.get("content") or "").strip()
        rows.append({"id": f"{case['id']}@{lang}", "out": text or "", "fallback": text is None, "calls": calls, "rounds": rounds,
                     "trace": trace, "first_text": first_text, "s": round(time.time() - t0, 2),
                     "prompt_n": [x.get("prompt_tokens") for x in usage], "cached": [x.get("prompt_tokens_details", {}).get("cached_tokens") for x in usage]})
        print(rows[-1]["id"], calls, rounds, rows[-1]["s"], (text or "")[:80], flush=True)
json.dump({"variant": variant, "rows": rows}, open(out, "w"), ensure_ascii=False, indent=1)
