"""D6 : points de note de production perdus par famille de commandes, split dev."""
import json, re, sys, collections
from pathlib import Path
T = Path('.'); sys.path.insert(0, str(T))
import v3lib, score_v3, score_production as sp
from steph.digest import extract_facts, _program
from steph.strings import t as _t

WRAP = {"sudo", "npx", "time", "env", "nice", "nohup", "exec", "command", "doas"}
def words(cmd):
    w = cmd.split("|")[0].split("&&")[-1].split()
    out, i = [], 0
    while i < len(w):
        x = w[i]
        if x in WRAP or re.match(r"^\w+=", x): i += 1; continue
        if x == "runuser":  # runuser -u user -- cmd
            j = w.index("--") if "--" in w else i + 3
            i = j + 1; continue
        out = w[i:]; break
    return out

def fam(cmd):
    w = words(cmd)
    if not w: return "other"
    p = w[0].rsplit("/", 1)[-1]; a = w[1:]; s = " ".join(a)
    if p in ("python", "python3") and ("-m pytest" in s or "-m unittest" in s): return "tests"
    if p in ("pytest", "jest", "vitest", "nosetests", "tox", "phpunit", "rspec", "bats", "ctest"): return "tests"
    if p == "go" and a[:1] == ["test"] or p == "cargo" and a[:1] in (["test"], ["nextest"]): return "tests"
    if p in ("npm", "pnpm", "yarn", "bun") and (a[:1] == ["test"] or a[:2] in (["run", "test"],) or "test" in a[:2]): return "tests"
    if p in ("make", "gmake", "./configure", "configure", "cmake", "ninja", "meson", "autoreconf"): return "make-autotools"
    if p in ("gcc", "g++", "clang", "clang++", "cc", "c++", "rustc", "javac", "ld") or p == "go" and a[:1] in (["build"], ["vet"], ["run"], ["mod"]) \
       or p == "cargo" and a[:1] in (["build"], ["check"], ["run"], ["clippy"]): return "compile"
    if p in ("ruff", "flake8", "mypy", "pylint", "black", "isort", "eslint", "prettier", "tsc", "shellcheck", "yamllint",
             "clang-format", "clang-tidy", "golangci-lint", "hadolint", "stylelint", "markdownlint", "pyright", "biome", "rubocop") \
       or p in ("npm", "pnpm", "yarn") and ("lint" in a[:2] or "typecheck" in a[:2]): return "lint-type"
    if p == "git" or p == "gh": return "git"
    if p in ("docker", "docker-compose", "podman", "kubectl", "helm", "k3s", "minikube"): return "containers"
    if p in ("systemctl", "journalctl", "service", "launchctl", "dmesg") or p == "brew" and a[:1] == ["services"]: return "services"
    if p in ("apt", "apt-get", "apt-cache", "dpkg", "brew", "snap", "flatpak", "dnf", "yum", "pacman", "pip", "pip3", "uv", "pipx",
             "poetry", "conda", "gem", "npm", "pnpm", "yarn", "bun") or p == "cargo" and a[:1] in (["install"], ["add"], ["update"]) \
       or p in ("python", "python3") and "-m pip" in s: return "packages"
    if p in ("df", "du", "free", "top", "ps", "vm_stat", "vmstat", "uptime", "lsof", "kill", "pkill", "pgrep", "swapon",
             "ncdu", "memory_pressure", "iostat", "lsblk", "diskutil", "htop", "pidof", "sysctl"): return "resources"
    if p in ("curl", "wget", "ping", "ip", "ss", "netstat", "dig", "nslookup", "host", "nmcli", "ssh", "scp", "nc", "traceroute",
             "ifconfig", "resolvectl", "http", "telnet"): return "network"
    if p in ("psql", "sqlite3", "mysql", "redis-cli", "mongosh", "pg_dump", "mongo"): return "db"
    if p in ("bash", "sh", "zsh", "dash") or p.endswith(".sh"): return "scripts"
    if p in ("python", "python3", "node", "ruby", "perl", "deno", "php") or p.endswith(".py") or p.endswith(".js"): return "runtime"
    if p in ("terraform", "ansible-playbook", "ansible", "tofu", "pulumi"): return "infra"
    if p in ("ls", "find", "wc", "grep", "rg", "cat", "head", "tail", "diff", "cmp", "tar", "zip", "unzip", "stat", "chmod", "chown",
             "cp", "mv", "rm", "mkdir", "ln", "rsync", "cut", "awk", "sed", "sort", "uniq", "xz", "gzip", "md5sum", "sha256sum",
             "sha512sum", "shred", "split", "file", "tree", "fd", "jq", "touch", "du"): return "files"
    return "other"

def load_run(path, harness, cases):
    return sp.score_run(cases, path, harness)["per_case"]

def main():
    cases = score_v3.load_cases("dev")
    h_ft = score_v3.load_harness("dev")
    h_gen = {h["id"]: h for h in json.load(open(sys.argv[1]))}
    models = {}
    for spec in sys.argv[2:]:
        name, hk, pat = spec.split(":")
        runs = [load_run(pat.replace("SEED", str(sd)), h_gen if hk == "gen" else h_ft, cases) for sd in (7, 42, 123)]
        models[name] = runs
    N = len(next(iter(models.values()))[0])
    rows = collections.defaultdict(lambda: {"n": 0, "code": 0, "model": 0, "qa": 0, "lost": collections.Counter(),
                                              "lost_code": 0.0, "facts": 0, "proto": collections.Counter(), "proto_better": collections.Counter(),
                                              "proto_worse": collections.Counter(), "cases": set()})
    first = next(iter(models.values()))[0]
    for rid in first:
        cid, lang = score_v3.parse_row_id(rid); case = cases[cid]
        f = "qa" if case["task"] == "qa" else fam(case["cmd"])
        r = rows[f]; r["n"] += 1; r["cases"].add(cid)
        src = first[rid]["source"]
        if case["task"] == "qa": r["qa"] += 1
        elif src == "code":
            r["code"] += 1; r["lost_code"] += 1 - first[rid]["score"]
        else:
            r["model"] += 1
            facts = extract_facts(case["cmd"], case["exit"], case["output_raw"], lang)
            proto = None
            if facts:
                r["facts"] += 1
                proto = sp.status_prefix(case, lang) + ". ".join(x.rstrip(".") for x in facts) + "."
                ps = score_v3.score_answer(case, lang, proto)
        for m, runs in models.items():
            for run in runs:
                p = run[rid]
                if case["task"] != "qa" and p["source"] != "code":
                    r["lost"][m] += (1 - p["score"]) / 3
                    if proto is not None:
                        r["proto"][m] += (ps - p["score"]) / 3
                        r["proto_better"][m] += (ps > p["score"]) / 3
                        r["proto_worse"][m] += (ps < p["score"]) / 3
    tot = collections.Counter()
    out = []
    for f, r in sorted(rows.items(), key=lambda kv: -sum(kv[1]["lost"].values())):
        d = {"family": f, "cases": len(r["cases"]), "evals": r["n"], "code": r["code"], "model": r["model"], "qa": r["qa"],
             "with_facts": r["facts"], "lost_code_pts": round(100 * r["lost_code"] / N, 2)}
        for m in models:
            d[f"lost_{m}"] = round(100 * r["lost"][m] / N, 2)
            d[f"facts_proto_gain_{m}"] = round(100 * r["proto"][m] / N, 2)
            d[f"proto_better_{m}"] = round(r["proto_better"][m], 1); d[f"proto_worse_{m}"] = round(r["proto_worse"][m], 1)
            tot[m] += r["lost"][m]
        out.append(d)
    print(json.dumps({"N": N, "families": out, "total_lost": {m: round(100 * v / N, 2) for m, v in tot.items()}}, ensure_ascii=False, indent=1))

main()
