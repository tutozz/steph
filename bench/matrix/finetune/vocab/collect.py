"""collect.py <port> <out.json> : renders every conversation with the model chat template and
tokenizes it through a running llama-server (/tokenize). Output: {"texts": [{"src", "ids"}]}.

SPDX-License-Identifier: MIT
"""
import json, sys, urllib.request
import jinja2

V = "/mnt/backup-hdd/stephbench-tmp/vocab"
DATA = "/mnt/backup-hdd/stephbench-tmp/ft/data/mix-judged"
port, out = sys.argv[1], sys.argv[2]


def post(path, body):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", json.dumps(body).encode(),
                                 {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=60))


def raise_exception(msg):
    raise ValueError(msg)


tmpl_src = json.load(open(f"{V}/out/chat_template.json"))
env = jinja2.Environment(trim_blocks=True, lstrip_blocks=True)
env.globals["raise_exception"] = raise_exception
tmpl = env.from_string(tmpl_src)


def render(messages, gen):
    return tmpl.render(messages=messages, bos_token="<bos>", add_generation_prompt=gen)


convs = []
for split in ("train", "val"):
    for line in open(f"{DATA}/{split}.jsonl"):
        convs.append((f"corpus-{split}", json.loads(line)["messages"], False))
for c in json.load(open(f"{V}/bench/cases_ft.json")):
    convs.append(("bench", c["messages"], True))
for c in json.load(open(f"{V}/ts_messages.json")):
    convs.append((c["src"], c["messages"], True))

checked = 0
for src, msgs, gen in convs:
    if src == "bench" and checked < 5:
        server = post("/apply-template", {"messages": msgs})["prompt"]
        assert "<bos>" + server == render(msgs, True), (src, server[:200])
        checked += 1

texts = []
for src, msgs, gen in convs:
    prompt = render(msgs, gen)
    r = post("/tokenize", {"content": prompt, "add_special": False, "parse_special": True})
    texts.append({"src": src, "ids": r["tokens"]})
json.dump({"texts": texts}, open(out, "w"))
print("texts", len(texts), "template checks", checked)
