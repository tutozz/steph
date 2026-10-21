"""Compte les jetons de chaque texte avec le tokeniseur d'un GGUF via llama-server /tokenize."""
import json, subprocess, sys, time, urllib.request, os

server, model, out = sys.argv[1], sys.argv[2], sys.argv[3]
texts = json.load(open(os.path.join(os.path.dirname(__file__), "texts.json")))
port = 8941
p = subprocess.Popen([server, "-m", model, "--port", str(port), "-t", "2", "-c", "512", "--no-webui"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(600):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1); break
        except Exception:
            time.sleep(0.2)
    def tok(t):
        body = json.dumps({"content": t, "add_special": False}).encode()
        r = urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{port}/tokenize", body, {"Content-Type": "application/json"}))
        return len(json.load(r)["tokens"])
    res = {k: [tok(t) for t in v] for k, v in texts.items() if not k.endswith("_ids")}
    res["chars"] = {k: [len(t) for t in v] for k, v in texts.items() if not k.endswith("_ids")}
    json.dump(res, open(out, "w"))
finally:
    p.terminate(); p.wait()
