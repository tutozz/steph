#!/usr/bin/env python3
"""Corpus capture for steph fine-tuning (H3a): multi-error builds, test runners
(including the ones digest.py does not yet resolve in code: python's stdlib
unittest, and any lint/test output whose summary line does not match), and
continuous-log snapshots (flux, H1 #9).

Same shape and safety rules as capture_corpus.py, which this module imports from
(add/run_task/locale_env/git_repo_setup): one JSON record per line (cmd, exit,
duration, output, machine, category), local sandbox only, resumable.

    python3 capture_features.py --profile macos --base /tmp/steph-features-mac --out corpus/features-macos.jsonl
    python3 capture_features.py --profile linux-low --base /tmp/steph-features-low --out corpus/features-linux-low.jsonl

linux-low : read-only system outside the sandbox, no sudo, no docker run/pull,
no apt install (same FORBIDDEN_ON_LINUX_LOW rule as capture_corpus.py) - pytest,
jest, vitest, eslint come from a local venv/npm install confined to --base, exactly
like capture_corpus.py already does for pip/npm packages.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from capture_corpus import add, run_task  # noqa: E402


# ================= erreurs multiples (H1 #2) =================

def _tasks_errors_macos(base: str) -> list[dict]:
    tasks: list[dict] = []
    f = os.path.join(base, "err")

    # clang, un fichier, 8 erreurs indépendantes dans 8 fonctions
    body = "\n".join(f"int bad{i}(void) {{ int x{i} = ; return x{i} }}" for i in range(8))
    src = os.path.join(f, "multi.c")
    setup = f"mkdir -p {f} && cat > {src} <<'EOF'\n#include <stdio.h>\n{body}\nEOF"
    add(tasks, base, f"clang -Wall -c {src} -o {f}/multi.o", "errors", setup=setup, timeout=20)

    # tsc, 6 erreurs de type
    ts_body = "\n".join(f"const n{i}: number = 'not a number {i}';" for i in range(6))
    tsrc = os.path.join(f, "types.ts")
    setup = f"mkdir -p {f} && cat > {tsrc} <<'EOF'\n{ts_body}\nEOF"
    add(tasks, base, f"tsc --noEmit {tsrc}", "errors", setup=setup, timeout=30)

    # rustc, 5 erreurs de type
    rs_body = "\n".join(f"    let x{i}: i32 = \"nope{i}\";" for i in range(5))
    rsrc = os.path.join(f, "types.rs")
    setup = f"mkdir -p {f} && cat > {rsrc} <<'EOF'\nfn main() {{\n{rs_body}\n}}\nEOF"
    add(tasks, base, f"rustc --edition 2021 -o {f}/types_bin {rsrc}", "errors", setup=setup, timeout=30)

    # go build, 5 erreurs (variables non déclarées)
    gomod = os.path.join(f, "gobuild")
    go_body = "\n".join(f"\tfmt.Println(undeclared{i})" for i in range(5))
    setup = (f"mkdir -p {gomod} && cd {gomod} && printf 'module errbuild\\n\\ngo 1.21\\n' > go.mod && "
             f"cat > main.go <<'EOF'\npackage main\n\nimport \"fmt\"\n\nfunc main() {{\n{go_body}\n}}\nEOF")
    add(tasks, base, "go build ./...", "errors", workdir=gomod, setup=setup, timeout=30)

    # eslint, 3 fichiers avec erreurs (résolu en code) + 6 fichiers à avertissements
    # seuls (résiduel : digest() doit grouper en sections, voir digest.py:_sectioned)
    eslint_dir = os.path.join(f, "eslint-errors")
    setup = (f"mkdir -p {eslint_dir}/src && cd {eslint_dir} && npm init -y >/dev/null 2>&1 && "
             f"npm install --silent eslint@9 >/dev/null 2>&1 && "
             "printf 'module.exports=[{rules:{\"no-unused-vars\":\"error\",\"no-undef\":\"error\"}}];' "
             f"> {eslint_dir}/eslint.config.cjs && " +
             " && ".join(f"printf 'function f{i}(){{ var x{i}=1; return undeclared{i} }}\\n' "
                         f"> {eslint_dir}/src/f{i}.js" for i in range(3)))
    add(tasks, base, "npx eslint src/", "errors", workdir=eslint_dir, setup=setup, timeout=40)

    warn_dir = os.path.join(f, "eslint-warnings")
    setup = (f"mkdir -p {warn_dir}/src && cd {warn_dir} && npm init -y >/dev/null 2>&1 && "
             f"npm install --silent eslint@9 >/dev/null 2>&1 && "
             "printf 'module.exports=[{rules:{\"eqeqeq\":\"warn\"}}];' "
             f"> {warn_dir}/eslint.config.cjs && " +
             " && ".join(f"printf 'function g{i}(a){{ if (a == {i}) return {i}; return 0 }}\\n' "
                         f"> {warn_dir}/src/g{i}.js" for i in range(6)))
    add(tasks, base, "npx eslint src/", "errors", workdir=warn_dir, setup=setup, timeout=40)
    return tasks


def _tasks_errors_linux_low(base: str) -> list[dict]:
    tasks: list[dict] = []
    f = os.path.join(base, "err")

    body = "\n".join(f"int bad{i}(void) {{ int x{i} = ; return x{i} }}" for i in range(8))
    src = os.path.join(f, "multi.c")
    setup = f"mkdir -p {f} && cat > {src} <<'EOF'\n#include <stdio.h>\n{body}\nEOF"
    add(tasks, base, f"gcc -Wall -c {src} -o {f}/multi.o", "errors", setup=setup, timeout=20)

    rs_body = "\n".join(f"    let x{i}: i32 = \"nope{i}\";" for i in range(5))
    rsrc = os.path.join(f, "types.rs")
    setup = f"mkdir -p {f} && cat > {rsrc} <<'EOF'\nfn main() {{\n{rs_body}\n}}\nEOF"
    add(tasks, base, f"rustc --edition 2021 -o {f}/types_bin {rsrc}", "errors", setup=setup, timeout=30)

    eslint_dir = os.path.join(f, "eslint-errors")
    setup = (f"mkdir -p {eslint_dir}/src && cd {eslint_dir} && npm init -y >/dev/null 2>&1 && "
             "printf 'module.exports=[{rules:{\"no-unused-vars\":\"error\",\"no-undef\":\"error\"}}];' "
             f"> {eslint_dir}/eslint.config.cjs && " +
             " && ".join(f"printf 'function f{i}(){{ var x{i}=1; return undeclared{i} }}\\n' "
                         f"> {eslint_dir}/src/f{i}.js" for i in range(3)))
    add(tasks, base, "npx eslint src/", "errors", workdir=eslint_dir, setup=setup, timeout=40)

    warn_dir = os.path.join(f, "eslint-warnings")
    setup = (f"mkdir -p {warn_dir}/src && cd {warn_dir} && npm init -y >/dev/null 2>&1 && "
             "printf 'module.exports=[{rules:{\"eqeqeq\":\"warn\"}}];' "
             f"> {warn_dir}/eslint.config.cjs && " +
             " && ".join(f"printf 'function g{i}(a){{ if (a == {i}) return {i}; return 0 }}\\n' "
                         f"> {warn_dir}/src/g{i}.js" for i in range(6)))
    add(tasks, base, "npx eslint src/", "errors", workdir=warn_dir, setup=setup, timeout=40)
    return tasks


# ================= résultats de tests (H1 #6) =================

def _pytest_project(d: str) -> str:
    # venv local (jamais le pytest système, absent sur linux-low) : même règle que
    # capture_corpus.py pour pip (aucune installation système).
    return (f"mkdir -p {d} && python3 -m venv {d}/venv && {d}/venv/bin/pip install -q pytest && "
            f"printf 'def test_add():\\n    assert 1 + 1 == 2\\n\\n"
            f"def test_sub():\\n    assert 5 - 2 == 3\\n\\n"
            f"def test_bad():\\n    assert 1 + 1 == 3\\n\\n"
            f"def test_mul():\\n    assert 2 * 3 == 6\\n' > {d}/test_calc.py")


def _unittest_project(d: str) -> str:
    return (f"mkdir -p {d} && cat > {d}/test_calc.py <<'EOF'\n"
            "import unittest\n\n"
            "class CalcTest(unittest.TestCase):\n"
            "    def test_add(self): self.assertEqual(1 + 1, 2)\n"
            "    def test_bad(self): self.assertEqual(1 + 1, 3)\n"
            "    def test_sub(self): self.assertEqual(5 - 2, 3)\n\n"
            "if __name__ == '__main__':\n    unittest.main()\nEOF")


def _cargo_project(d: str) -> str:
    # `d` est déjà le workdir (créé par run_task avant setup) : `cargo init`, pas `cargo new`.
    return (f"mkdir -p {d}/src && cd {d} && cargo init --quiet --lib --vcs none && cat > src/lib.rs <<'EOF'\n"
            "pub fn add(a: i32, b: i32) -> i32 { a + b }\n\n"
            "#[cfg(test)]\nmod tests {\n    use super::*;\n"
            "    #[test]\n    fn adds() { assert_eq!(add(2, 3), 5); }\n"
            "    #[test]\n    fn fails_on_purpose() { assert_eq!(add(2, 2), 5); }\n"
            "    #[test]\n    fn subtracts_like() { assert_eq!(add(-1, 1), 0); }\n}\nEOF")


def _go_test_project(d: str) -> str:
    return (f"mkdir -p {d} && printf 'module gotests\\n\\ngo 1.21\\n' > {d}/go.mod && "
            f"cat > {d}/calc_test.go <<'EOF'\npackage gotests\n\nimport \"testing\"\n\n"
            "func TestAdd(t *testing.T) { if 1+1 != 2 { t.Fatal(\"bad\") } }\n"
            "func TestFail(t *testing.T) { if 1+1 != 3 { t.Errorf(\"got %d want %d\", 2, 3) } }\nEOF")


def _vitest_project(d: str) -> str:
    return (f"mkdir -p {d}/src && cd {d} && npm init -y >/dev/null 2>&1 && npm install --silent vitest >/dev/null 2>&1 && "
            f"cat > {d}/src/calc.test.js <<'EOF'\nimport {{ test, expect }} from 'vitest'\n"
            "function sum(a, b) { return a + b }\n"
            "test('adds', () => { expect(sum(2, 3)).toBe(5) })\n"
            "test('fails on purpose', () => { expect(sum(2, 2)).toBe(5) })\n"
            "test('subtracts like', () => { expect(sum(-1, 1)).toBe(0) })\nEOF")


def _jest_project(d: str) -> str:
    return (f"mkdir -p {d}/src && cd {d} && npm init -y >/dev/null 2>&1 && npm install --silent jest >/dev/null 2>&1 && "
            f"cat > {d}/src/calc.test.js <<'EOF'\nfunction sum(a, b) {{ return a + b }}\n"
            "test('adds', () => { expect(sum(2, 3)).toBe(5) })\n"
            "test('fails on purpose', () => { expect(sum(2, 2)).toBe(5) })\nEOF")


def _tasks_tests_common(base: str, has_go: bool) -> list[dict]:
    tasks: list[dict] = []
    t = os.path.join(base, "tests")

    d = os.path.join(t, "pytest-mix")
    add(tasks, base, f"{d}/venv/bin/python -m pytest -q .", "tests", workdir=d, setup=_pytest_project(d), timeout=60)

    d = os.path.join(t, "unittest-mix")
    add(tasks, base, "python3 -m unittest -v", "tests", workdir=d, setup=_unittest_project(d), timeout=30)

    d = os.path.join(t, "cargo-mix")
    add(tasks, base, "cargo test --quiet", "tests", workdir=d, setup=_cargo_project(d), timeout=60)

    d = os.path.join(t, "vitest-mix")
    add(tasks, base, "npx vitest run", "tests", workdir=d, setup=_vitest_project(d), timeout=40)

    if has_go:
        d = os.path.join(t, "go-mix")
        add(tasks, base, "go test ./...", "tests", workdir=d, setup=_go_test_project(d), timeout=30)
        d = os.path.join(t, "go-mix-verbose")
        add(tasks, base, "go test -v ./...", "tests", workdir=d, setup=_go_test_project(d), timeout=30)

    d = os.path.join(t, "jest-mix")
    add(tasks, base, "npx jest", "tests", workdir=d, setup=_jest_project(d), timeout=40)

    return tasks


# ================= journaux en continu (H1 #9) : une seule grosse capture, =================
# ================= découpée en fenêtres glissantes par build_feature_corpus.py =================

def _tasks_flux_macos(base: str) -> list[dict]:
    tasks: list[dict] = []
    d = os.path.join(base, "flux")

    # serveur HTTP réel + vraies requêtes (succès et 404) : journal d'accès réel. Le cmd
    # commence par la commande réellement surveillée (celle que verrait le modèle),
    # le reste orchestre juste les requêtes et la capture du journal.
    port = 8098
    setup = f"mkdir -p {d}/site && echo ok > {d}/site/index.html"
    cmd = (f"python3 -m http.server {port} --directory {d}/site > {d}/server.log 2>&1 & SPID=$!; sleep 0.6; "
           f"for i in $(seq 1 12); do curl -s -o /dev/null http://127.0.0.1:{port}/index.html; "
           f"curl -s -o /dev/null http://127.0.0.1:{port}/missing-$i; sleep 0.05; done; "
           f"sleep 0.3; kill $SPID 2>/dev/null; pkill -f 'http.server {port}' 2>/dev/null; cat {d}/server.log")
    add(tasks, base, cmd, "flux", workdir=d, setup=setup, timeout=30)

    # conteneur réel (si le démon docker tourne), tick avec erreurs périodiques dans
    # les vrais logs docker ; silencieusement absent sinon (Docker Desktop non lancé)
    if _docker_available():
        setup2 = f"mkdir -p {d}"
        cmd2 = (f"docker run --rm alpine sh -c '"
                "for i in $(seq 1 40); do echo \"info: tick $i ok\"; "
                "if [ $((i % 6)) -eq 0 ]; then echo \"ERROR: tick $i failed, retrying\" >&2; fi; "
                "if [ $((i % 11)) -eq 0 ]; then echo \"WARNING: queue depth high at tick $i\"; fi; "
                "done' 2>&1")
        add(tasks, base, cmd2, "flux", workdir=d, setup=setup2, timeout=30)
    return tasks


def _docker_available() -> bool:
    try:
        return subprocess.run(["docker", "info"], stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL, timeout=5).returncode == 0
    except Exception:
        return False


def _tasks_flux_linux_low(base: str) -> list[dict]:
    tasks: list[dict] = []
    d = os.path.join(base, "flux")
    os.makedirs(d, exist_ok=True)
    # journal système réel (lecture seule) : une grosse capture, tranchée en fenêtres
    # glissantes par build_feature_corpus.py, exactement comme la progression P11.
    add(tasks, base, "journalctl -n 400 --no-pager -o short-iso", "flux", workdir=d, timeout=20)
    add(tasks, base, "journalctl -p warning -n 200 --no-pager -o short-iso", "flux", workdir=d, timeout=20)
    return tasks


PROFILE_ERRORS = {"macos": _tasks_errors_macos, "linux-low": _tasks_errors_linux_low}
PROFILE_HAS_GO = {"macos": True, "linux-low": False}
PROFILE_FLUX = {"macos": _tasks_flux_macos, "linux-low": _tasks_flux_linux_low}


def build_tasks(profile: str, base: str) -> list[dict]:
    if profile not in PROFILE_ERRORS:
        raise ValueError(f"unknown profile: {profile!r} (expected one of {sorted(PROFILE_ERRORS)})")
    tasks = PROFILE_ERRORS[profile](base)
    tasks += _tasks_tests_common(base, PROFILE_HAS_GO[profile])
    tasks += PROFILE_FLUX[profile](base)
    return tasks


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--profile", required=True, choices=sorted(PROFILE_ERRORS))
    ap.add_argument("--base", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--machine", help="défaut : --profile")
    args = ap.parse_args()

    base = os.path.abspath(args.base)
    os.makedirs(base, exist_ok=True)
    machine = args.machine or args.profile
    tasks = build_tasks(args.profile, base)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    done = 0
    if out_path.exists():
        with open(out_path, encoding="utf-8") as f:
            done = sum(1 for _ in f)
    print(f"{len(tasks)} tâches, {done} déjà faites", file=sys.stderr)

    with open(out_path, "a", encoding="utf-8") as out:
        for i, task in enumerate(tasks):
            if i < done:
                continue
            record = run_task(task, machine, "fr", max_len=40000)
            out.write(json.dumps(record, ensure_ascii=False) + "\n")
            out.flush()
            print(f"{i + 1}/{len(tasks)} {task['category']} {task['cmd'][:60]!r} exit={record['exit']}",
                  file=sys.stderr)
    print(f"terminé {len(tasks)}/{len(tasks)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
