"""Net preference and controls accuracy for the control style run (same method as g3_eval.style)."""
import json
import random
import sys


def boot(vals, n=10_000, seed=20260928):
    rng = random.Random(seed)
    k = len(vals)
    means = sorted(sum(vals[rng.randrange(k)] for _ in range(k)) / k for _ in range(n))
    return round(100 * sum(vals) / k, 1), [round(100 * means[int(0.025 * n)], 1), round(100 * means[int(0.975 * n) - 1], 1)]


def controls(path):
    d = json.load(open(path))
    planted = [x for x in d if x["expected"] != "="]
    ties = [x for x in d if x["expected"] == "="]
    raws = [r["global"] for x in d for r in x["raw"] if r and r.get("global") in ("A", "B")]
    return {"planted_ok": sum(x["final"]["global"] == x["expected"] for x in planted), "planted": len(planted),
            "ties_ok": sum(x["final"]["global"] == "=" for x in ties), "ties": len(ties),
            "errors": sum(bool(x["error"]) for x in d), "position_a_pct": round(100 * raws.count("A") / len(raws), 1)}


def style(path):
    all_rows = json.load(open(path))
    rs = [r for r in all_rows if not r.get("error")]
    out = {"n": len(rs), "errors": len(all_rows) - len(rs), "unstable": sum(bool(r["unstable"]["global"]) for r in rs)}
    for lang in ("all", "fr", "en"):
        sub = [r for r in rs if lang == "all" or r["lang"] == lang]
        vals = [{"x": 1, "y": -1, "=": 0}[r["final"]["global"]] for r in sub]
        net, ci = boot(vals)
        out[lang] = {"n": len(sub), "x": vals.count(1), "y": vals.count(-1), "=": vals.count(0), "net_x": net, "ci95": ci}
    return out


if __name__ == "__main__":
    d = sys.argv[1]
    print(json.dumps({"controls_pre": controls(f"{d}/controls-pre.json"), "controls_post": controls(f"{d}/controls-post.json"),
                      "off-ple3-vs-official": style(f"{d}/style-off-ple3-vs-official.json")}, ensure_ascii=False, indent=1))
