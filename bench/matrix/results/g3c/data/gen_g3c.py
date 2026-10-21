#!/usr/bin/env python3
"""G3c data: public command outputs recorded in an offline sandbox (sbx.sh), with injected faults.

    python3 gen_g3c.py G3C_DIR OUT.jsonl            # run every scenario, FR then EN locale
    python3 gen_g3c.py G3C_DIR --count              # scenario counts per family

G3C_DIR holds rootfs/, src/ (public repos at pinned commits, sources.json), tpl/ (invented template,
tpl/base, and tpl/tools/mut.py), sbx.sh. Each scenario runs with LC_ALL=fr_FR.UTF-8 and with
LC_ALL=C.UTF-8. The hidden setup (environment, services, injected fault) runs first with its output
discarded; only the visible command and its output are recorded.
"""
import collections, concurrent.futures, json, os, re, shutil, subprocess, sys, time

FR, EN = "fr_FR.UTF-8", "C.UTF-8"
G = sys.argv[1]
SRC = os.path.join(G, "src")
TPL = os.path.join(G, "tpl")
META = {m["dir"]: m for m in json.load(open(os.path.join(G, "sources.json"))) if m.get("kept")}
SYN = "synthétique (fichiers inventés pour G3c, CC BY 4.0)"
MUT = "python3 /srv/tpl/tools/mut.py"


def lic(d):
    m = META[d]
    return f"{m['source']} ({m['spdx']}) @{m['commit'][:12]}"


def S(family, cmd, setup="", needs=(), source=SYN, fault="", cwd="", timeout=60, docker="absent"):
    return {"family": family, "cmd": cmd, "setup": setup, "needs": list(needs), "source": source,
            "fault": fault, "cwd": cwd, "timeout": timeout, "docker": docker}


def exists(rel):
    return os.path.exists(os.path.join(SRC, rel))


# ---------------------------------------------------------------- Python: tests, lint, typing
PY = {  # repo: (PYTHONPATH, test dir, module to break, second module)
    "attrs": ("src", "tests", "src/attr/validators.py", "src/attr/converters.py"),
    "toolz": (".", "toolz/tests", "toolz/itertoolz.py", "toolz/dicttoolz.py"),
    "python-tabulate": (".", "test", "tabulate/__init__.py", "tabulate/__init__.py"),
    "idna": (".", "tests", "idna/core.py", "idna/codec.py"),
    "cachetools": ("src", "tests", "src/cachetools/__init__.py", "src/cachetools/keys.py"),
    "pyparsing": (".", "tests", "pyparsing/helpers.py", "pyparsing/util.py"),
    "python-sortedcontainers": ("src", "tests", "src/sortedcontainers/sortedlist.py", "src/sortedcontainers/sorteddict.py"),
    "wcwidth": (".", "tests", "wcwidth/wcwidth.py", "wcwidth/textwrap.py"),
    "iniconfig": ("src", "testing", "src/iniconfig/_parse.py", "src/iniconfig/__init__.py"),
    "marshmallow": ("src", "tests", "src/marshmallow/validate.py", "src/marshmallow/utils.py"),
}


def first_test_file(r, tdir):
    d = os.path.join(SRC, "python", r, tdir)
    fs = sorted(f for f in os.listdir(d) if f.startswith("test_") and f.endswith(".py"))
    return [f"{tdir}/{f}" for f in fs]


def python_family():
    out = []
    for r, (pp, tdir, mod, mod2) in PY.items():
        d = f"python/{r}"
        src = lic(d)
        env = f"export PYTHONPATH={pp}"
        tf = first_test_file(r, tdir)
        t1, t2 = tf[0], tf[min(1, len(tf) - 1)]
        T = lambda cmd, fault="", setup="", timeout=240: out.append(
            S("tests", cmd, env + ("\n" + setup if setup else ""), [f"py:{r}"], src, fault, f"projets/{r}", timeout))
        L = lambda fam, cmd, fault="", setup="": out.append(
            S(fam, cmd, env + ("\n" + setup if setup else ""), [f"py:{r}"], src, fault, f"projets/{r}", 120))
        T(f"python3 -m pytest -q {tdir}")
        T(f"python3 -m pytest -q {t1}")
        T(f"python3 -m pytest {t2} -v 2>&1 | tail -15")
        T(f"python3 -m pytest -q -x {tdir}", "valeur de retour neutralisée", f"{MUT} ret {mod} 2")
        T(f"python3 -m pytest -q {tdir} 2>&1 | tail -25", "comparaison inversée", f"{MUT} cmp {mod} 1")
        T(f"python3 -m pytest -q --maxfail=3 {tdir}", "valeur de retour neutralisée", f"{MUT} ret {mod2} 1")
        T(f"python3 -m pytest -q {tdir}", "erreur de syntaxe dans le module", f"{MUT} syn {mod}")
        T(f"python3 -m pytest -q {t1}", "module supprimé", f"rm {mod}")
        T(f"python3 -m pytest -q {t1}", "PYTHONPATH absent, paquet non installé", "unset PYTHONPATH")
        T(f"python3 -m pytest -q {tdir}/test_inexistant.py", "fichier de test inexistant")
        T(f"python3 -m pytest -q -k 'not slow' --co {tdir} | tail -5")
        T(f"python3 -m pytest -q --durations=5 {t1} | tail -12")
        T(f"python3 -m pytest -q -W error {t1} | tail -15")
        T(f"pytest -q {t1}", "", "")
        T(f"python3 -m pytest -q {t2}", "décalage d'une unité", f"{MUT} off {mod} 1")
        L("lint-format", "ruff check .")
        L("lint-format", f"ruff check {mod}", "variable inutilisée ajoutée", f"{MUT} unused {mod} 1")
        L("lint-format", f"ruff check {mod}", "erreur de syntaxe", f"{MUT} syn {mod}")
        L("lint-format", f"ruff format --check {os.path.dirname(mod) or '.'}")
        L("lint-format", f"flake8 --max-line-length=100 {mod}")
        L("lint-format", f"flake8 {mod} | head -20", "variable inutilisée ajoutée", f"{MUT} unused {mod} 1")
        L("lint-format", f"pylint --disable=all --enable=W,E {mod} 2>&1 | tail -20")
        L("lint-format", f"black --check {mod}")
        L("lint-format", f"black --check --diff {mod} 2>&1 | head -30", "indentation modifiée",
          f"sed -i '0,/^    return /s//    return  /' {mod}")
        L("typage", f"mypy {mod}")
        L("typage", f"mypy --strict {mod} 2>&1 | tail -12")
        L("typage", f"mypy {mod}", "valeur de retour neutralisée", f"{MUT} ret {mod} 3")
    for r, (pp, tdir, mod, mod2) in PY.items():
        for m in (mod, mod2):
            if not exists(f"python/{r}/{m}"):
                print("CIBLE ABSENTE", r, m, file=sys.stderr)
    return out


def python_scripts():
    out = []
    P = lambda cmd, fault="", setup="", fam="python": out.append(S(fam, cmd, setup, [], SYN, fault))
    P("python3 py/facturation.py", "colonne absente, exception chaînée")
    P("python3 py/charger_config.py", "fichier de configuration absent, exception chaînée")
    P("python3 py/charger_config.py data/settings_casse.json", "virgule en trop dans le JSON")
    P("python3 py/client_api.py", "service local injoignable")
    P("python3 py/client_api.py", "", "python3 -m http.server 8081 --bind 127.0.0.1 -d data >/dev/null 2>&1 & sleep 1")
    P("python3 py/lire_json.py data/settings_casse.json", "JSON invalide")
    P("python3 py/lire_json.py data/absent.json", "fichier absent")
    P("python3 py/encodage.py", "fichier en Latin-1 lu en UTF-8")
    P("python3 py/stats.py", "valeur vide dans le TSV")
    P("python3 py/stats.py humidité")
    P("python3 py/stats.py pression", "colonne inexistante")
    P("python3 py/rapport.py")
    P("python3 py/outil.py", "sous-commande manquante")
    P("python3 py/outil.py export", "option obligatoire manquante")
    P("python3 py/outil.py export --format xml", "valeur non autorisée")
    P("python3 py/outil.py import commandes.csv --lot dix", "entier attendu")
    P("python3 py/outil.py --help")
    P("python3 py/outil.py export --format csv")
    P("python3 py/traitement.py")
    P("python3 -m json.tool data/settings_casse.json", "JSON invalide")
    P("python3 -m json.tool data/clients.json | head -12")
    P("python3 -c 'import requests'", "module absent")
    P("python3 -c 'import yaml; print(yaml.safe_load(open(\"config/app.yaml\")))'", "module absent")
    P("python3 -m venv .venv && .venv/bin/python -c 'import sys; print(sys.prefix)'")
    P("python3 -m py_compile py/*.py && echo compilation ok")
    P("python3 -m py_compile py/brouillon.py", "arguments en double")
    P("python3 -m timeit -n 1000 'sum(range(1000))'")
    P("python3 -m unittest discover -s py -p 'test_*.py'", "aucun test trouvé")
    P("python3 --version && pip --version")
    P("python3 -X importtime -c 'import json' 2>&1 | tail -5")
    P("ruff check py/", fam="lint-format")
    P("ruff check py/brouillon.py --statistics", fam="lint-format")
    P("ruff check --select E,F,W,B py/brouillon.py", fam="lint-format")
    P("ruff format --diff py/brouillon.py", fam="lint-format")
    P("ruff check py/propre.py", fam="lint-format")
    P("flake8 py/", fam="lint-format")
    P("flake8 py/brouillon.py", fam="lint-format")
    P("pylint py/brouillon.py", fam="lint-format")
    P("pylint py/propre.py", fam="lint-format")
    P("black --check py/", fam="lint-format")
    P("black py/brouillon.py", fam="lint-format")
    P("mypy py/typage.py", fam="typage")
    P("mypy py/propre.py", fam="typage")
    P("mypy --strict py/", fam="typage")
    P("mypy py/typage.py --no-error-summary | wc -l", fam="typage")
    P("mypy py/brouillon.py", fam="typage")
    return out


# ---------------------------------------------------------------- Node, TypeScript
JS = ["bytes.js", "content-type", "statuses", "http-errors", "negotiator", "vary"]
JS_MAIN = {"bytes.js": "index.js", "statuses": "index.js", "http-errors": "index.js", "negotiator": "lib/mediaType.js",
           "vary": "index.js", "content-type": "src/index.ts"}


def js_family():
    out = []
    for r in JS:
        d = f"js/{r}"
        src = lic(d)
        m = JS_MAIN[r]
        T = lambda cmd, fault="", setup="", fam="tests": out.append(S(fam, cmd, setup, [f"js:{r}"], src, fault, f"projets/{r}", 180))
        if r == "content-type":
            T("npx vitest run", fam="tests")
            T("npx vitest run", "valeur de retour neutralisée", f"{MUT} ret {m} 2")
            T("npx vitest run src/parse.spec.ts", "comparaison inversée", f"{MUT} cmp {m} 1")
            T("npx tsc --noEmit", fam="typage")
            T("npx tsc --noEmit", "variable inutilisée ajoutée", f"{MUT} unused {m} 1", fam="typage")
            T("npx tsc --noEmit", "erreur de syntaxe", f"{MUT} syn {m}", fam="typage")
            T("npx tsc --noEmit -p tsconfig.json", "valeur de retour neutralisée", f"{MUT} ret {m} 1", fam="typage")
            T("npm run build", fam="build-native")
            T("npm run build", "erreur de syntaxe", f"{MUT} syn {m}", fam="build-native")
            T("npm test", "script de test sans réseau ni dépendances de contrôle")
            T("npx prettier --check src", fam="lint-format")
            T("npm ls --depth=0", fam="packages-system")
            continue
        T("npm test")
        T("npx mocha --reporter dot")
        T("npm test", "valeur de retour neutralisée", f"{MUT} ret {m} 1")
        T("npm test 2>&1 | tail -30", "comparaison inversée", f"{MUT} cmp {m} 1")
        T("npx mocha --reporter dot", "valeur de retour neutralisée", f"{MUT} ret {m} 2")
        T("npm test", "erreur de syntaxe", f"{MUT} syn {m}")
        T("npm test", "point-virgule retiré", f"{MUT} semi {m} 3")
        T("npm test", "fichier principal supprimé", f"rm {m}")
        T("npm run test-ci 2>&1 | tail -25")
        T("npm run lint", fam="lint-format")
        T("npm run lint", "variable inutilisée ajoutée", f"{MUT} unused {m} 1", fam="lint-format")
        T("npx eslint .", "comparaison inversée", f"{MUT} cmp {m} 1", fam="lint-format")
        T("npx prettier --check .", fam="lint-format")
        T("npm run nonexistent", "script absent", fam="js-node")
        T("npm ls --depth=0", fam="packages-system")
        T("npm outdated", "hors ligne", fam="packages-system")
        T("npm install left-pad", "hors ligne", fam="packages-system")
    J = lambda cmd, fault="", setup="", fam="js-node": out.append(S(fam, cmd, setup, [], SYN, fault, "jsapp", 90))
    J("node index.js", "propriété d'une chaîne lue comme un objet")
    J("node serveur.js", "module express absent")
    J("node config.js", "JSON invalide")
    J("node async.js", "promesse rejetée non gérée")
    J("node syntaxe.js", "parenthèse manquante")
    J("node --check syntaxe.js", "parenthèse manquante")
    J("node --test", fam="tests")
    J("node --test test/", "comparaison flottante", fam="tests")
    J("npm start", "propriété d'une chaîne lue comme un objet")
    J("npm test", fam="tests")
    J("npm install", "aucune dépendance déclarée", fam="packages-system")
    J("npm install express", "hors ligne", fam="packages-system")
    J("npm ci", "package-lock.json absent", fam="packages-system")
    J("npx eslint .", fam="lint-format")
    J("npx eslint brouillon.js", fam="lint-format")
    J("npx prettier --check .", fam="lint-format")
    J("node -e 'console.log(process.version, process.platform)'")
    J("node inexistant.js", "fichier absent")
    Tt = lambda cmd, fault="", setup="", fam="typage": out.append(S(fam, cmd, setup, [], SYN, fault, "ts", 90))
    Tt("tsc --noEmit", "erreurs de type")
    Tt("tsc --noEmit src/format.ts")
    Tt("tsc", "erreurs de type")
    Tt("tsc --noEmit --pretty false", "erreurs de type")
    Tt("npm run check", "erreurs de type")
    Tt("npm run build", "", "rm src/stock.ts", fam="build-native")
    Tt("tsc --noEmit", "tsconfig invalide", "echo '{ \"compilerOptions\": { \"target\": \"ES2099\" } }' > tsconfig.json")
    Tt("tsc --init", "tsconfig déjà présent")
    return out


# ---------------------------------------------------------------- Go
GO = {"mux": "mux.go", "httprouter": "router.go", "toml": "decode.go", "errors": "errors.go", "btree": "btree_generic.go"}
GOENV = ("export GOCACHE=$HOME/.cache/go-build GOMODCACHE=/srv/src/gopath/pkg/mod GOFLAGS=-mod=mod GOPROXY=off "
         "GOTOOLCHAIN=local GOTELEMETRY=off GOPATH=$HOME/go")


def go_family():
    out = []
    for r, m in GO.items():
        src = lic(f"go/{r}")
        T = lambda cmd, fault="", setup="", fam="tests": out.append(
            S(fam, cmd, GOENV + "\n[ -f go.mod ] || go mod init github.com/pkg/errors" + ("\n" + setup if setup else ""), [f"go:{r}"], src, fault, f"projets/{r}", 240))
        T("go test ./...")
        T("go test -v ./... 2>&1 | tail -20")
        T("go test -count=1 -run 'Test' ./... 2>&1 | tail -8")
        T("go test ./...", "comparaison inversée", f"{MUT} cmp {m} 1")
        T("go test ./... 2>&1 | head -30", "comparaison inversée", f"{MUT} cmp {m} 3")
        T("go test ./...", "valeur de retour modifiée", f"{MUT} off {m} 1")
        T("go test ./...", "variable inutilisée", f"{MUT} unused {m} 2")
        T("go test -cover ./...")
        T("go test -race ./...", "cgo sans compilateur C adapté ?")
        T("go build ./...", fam="rust-go")
        T("go build ./...", "accolade supprimée", f"{MUT} brace {m} 2", fam="rust-go")
        T("go build ./...", "erreur de syntaxe", f"{MUT} syn {m}", fam="rust-go")
        T("go vet ./...", fam="lint-format")
        T("go vet ./...", "variable inutilisée", f"{MUT} unused {m} 1", fam="lint-format")
        T("gofmt -l .", fam="lint-format")
        T("gofmt -d " + m + " | head -20", "indentation modifiée", f"sed -i '0,/^\\treturn /s//    return /' {m}", fam="lint-format")
        T("go mod tidy", "hors ligne", fam="packages-system")
        T("go get github.com/stretchr/testify@latest", "hors ligne", fam="packages-system")
        T("go list -m all", fam="packages-system")
        T("go version && go env GOOS GOARCH", fam="rust-go")
    return out


# ---------------------------------------------------------------- Rust
RS = {"walkdir": "src/lib.rs", "glob": "src/lib.rs", "either": "src/lib.rs", "rust-fnv": "lib.rs"}
RSENV = "export CARGO_HOME=$HOME/.cargo CARGO_NET_OFFLINE=true"


def rust_family():
    out = []
    for r, m in RS.items():
        src = lic(f"rust/{r}")
        T = lambda cmd, fault="", setup="", fam="tests": out.append(
            S(fam, cmd, RSENV + ("\n" + setup if setup else ""), [f"rs:{r}"], src, fault, f"projets/{r}", 400))
        T("cargo test --offline 2>&1 | tail -25")
        T("cargo test --offline", "comparaison inversée", f"{MUT} cmp {m} 1")
        T("cargo test --offline 2>&1 | tail -30", "valeur modifiée", f"{MUT} off {m} 1")
        T("cargo build --offline", fam="build-native")
        T("cargo build --offline", "point-virgule retiré", f"{MUT} semi {m} 2", fam="build-native")
        T("cargo build --offline", "accolade supprimée", f"{MUT} brace {m} 3", fam="build-native")
        T("cargo check --offline", "variable inutilisée", f"{MUT} unused {m} 1", fam="rust-go")
        T("cargo clippy --offline 2>&1 | tail -25", fam="lint-format")
        T("cargo fmt --check 2>&1 | head -30", fam="lint-format")
        T("cargo build --release --offline 2>&1 | tail -5", fam="build-native")
        T("cargo update", "hors ligne", fam="packages-system")
        T("cargo add serde", "hors ligne", fam="packages-system")
    return out


# ---------------------------------------------------------------- C: configure, make, cmake
def c_family():
    out = []
    READY = {"libyaml": ("src/api.c", "include/yaml.h"), "jansson": ("src/dump.c", "src/jansson.h"),
             "libuv": ("src/uv-common.c", "include/uv.h"), "expat": ("lib/xmltok.c", "lib/expat.h")}
    for r, (m, h) in READY.items():
        src = lic("c/libexpat" if r == "expat" else f"c/{r}")
        B = lambda cmd, fault="", setup="", timeout=400: out.append(
            S("build-native", cmd, setup, [f"ready:{r}"], src, fault, f"projets/{r}", timeout))
        CONF = "./configure -q >/dev/null 2>&1"
        B("./configure 2>&1 | tail -20")
        B("./configure --prefix=$HOME/.local 2>&1 | tail -8")
        B("./configure --with-inexistant --enable-truc 2>&1 | tail -6", "options inconnues")
        B("./configure CC=clang", "compilateur absent")
        B("./configure CFLAGS='-O2 -march=nehalem-inexistant' 2>&1 | tail -12", "option de compilation invalide")
        B("make", "configure non lancé")
        B("make -j4 2>&1 | tail -15", "", CONF)
        B("make -s -j4", "", CONF)
        B("make -j4 2>&1 | grep -iE 'error|erreur' | head", "point-virgule retiré", CONF + f"\n{MUT} semi {m} 5")
        B("make 2>&1 | tail -20", "point-virgule retiré", CONF + f"\n{MUT} semi {m} 5")
        B("make 2>&1 | tail -20", "variable inutilisée, -Werror", CONF + f"\n{MUT} unused {m} 1\nexport CFLAGS='-Wall -Werror'")
        B("make CFLAGS='-Wall -Wextra -Werror' 2>&1 | tail -15", "avertissements traités en erreurs", CONF)
        B("make 2>&1 | tail -12", "en-tête supprimé", CONF + f"\nrm {h}")
        B("make install", "préfixe système non inscriptible", CONF + "\nmake -s -j4 >/dev/null 2>&1")
        B("make install 2>&1 | tail -6", "", "./configure -q --prefix=$HOME/.local >/dev/null 2>&1\nmake -s -j4 >/dev/null 2>&1")
        B("make check 2>&1 | tail -25", "", CONF + "\nmake -s -j4 >/dev/null 2>&1", 600)
        B("make distclean && ls", "", CONF)
        B("make clean", "configure non lancé")
        B("make instal", "cible mal orthographiée", CONF)
        B("make -n | head -10", "", CONF)
        B("mkdir -p build && cd build && cmake .. 2>&1 | tail -12")
        B("cmake -S . -B build -DCMAKE_BUILD_TYPE=Release 2>&1 | tail -8")
        B("cmake --build build -j4 2>&1 | tail -10", "", "cmake -S . -B build >/dev/null 2>&1")
        B("cmake --build build 2>&1 | tail -15", "point-virgule retiré", f"cmake -S . -B build >/dev/null 2>&1\n{MUT} semi {m} 5")
        B("cmake --build build", "répertoire de build absent")
        B("cmake -S . -B build -G Ninja", "générateur absent")
        B("cd build && ctest 2>&1 | tail -15", "", "cmake -S . -B build >/dev/null 2>&1 && cmake --build build -j4 >/dev/null 2>&1", 600)
    for r in ["libyaml", "jansson", "libuv"]:
        src = lic(f"c/{r}")
        B = lambda cmd, fault="", setup="": out.append(S("build-native", cmd, setup, [f"c:{r}"], src, fault, f"projets/{r}", 300))
        B("./configure", "script configure pas encore généré")
        B("autoreconf -fi 2>&1 | tail -8")
        B("ls && make", "ni configure ni Makefile")
    z = lic("c/zlib")
    Z = lambda cmd, fault="", setup="", timeout=300: out.append(S("build-native", cmd, setup, ["c:zlib"], z, fault, "projets/zlib", timeout))
    Z("./configure")
    Z("./configure --prefix=/opt/zlib && make -j4 2>&1 | tail -6")
    Z("make -j4", "configure non lancé")
    Z("make test 2>&1 | tail -15", "", "./configure >/dev/null 2>&1")
    Z("make 2>&1 | tail -10", "point-virgule retiré", "./configure >/dev/null 2>&1\n" + f"{MUT} semi deflate.c 7")
    Z("make install", "préfixe système non inscriptible", "./configure >/dev/null 2>&1 && make -s -j4 >/dev/null 2>&1")
    Z("./configure --static --64 && make -s -j4 && ls -l libz.a")
    Z("cmake -B build 2>&1 | tail -8")
    Z("make -f Makefile.in", "Makefile modèle utilisé tel quel")
    Z("./configure CC=gcc-9", "compilateur absent")
    return out


# ---------------------------------------------------------------- Databases
PGSTART = ('pg_ctl -D pg/pgdata -o "-k /home/user/run -c listen_addresses=localhost -c lc_messages=$LC_ALL" '
           "-l run/pg.log -w start\nexport PGHOST=/home/user/run")
VKSTART = ("valkey-server --port 6379 --bind 127.0.0.1 --daemonize yes --dir /home/user/run --save '' "
           "--logfile /home/user/run/valkey.log\nsleep 0.5")


def db_family():
    out = []
    ch = lic("db/chinook-database")
    pa = lic("db/pagila")
    Q = lambda cmd, src=SYN, fault="", setup="", start=True: out.append(
        S("bases", cmd, (PGSTART + "\n" if start else "") + setup, ["pg"], src, fault, "", 90))
    Q("psql -l")
    Q("psql -d chinook -c '\\dt'", ch)
    Q("psql chinook -c '\\d invoice'", ch)
    Q("psql chinook -c 'SELECT count(*) FROM track'", ch)
    Q("psql chinook -c 'SELECT name, milliseconds / 60000 AS minutes FROM track ORDER BY milliseconds DESC LIMIT 5'", ch)
    Q("psql chinook -c 'SELECT billing_country, round(sum(total), 2) AS ca FROM invoice GROUP BY 1 ORDER BY 2 DESC LIMIT 5'", ch)
    Q("psql chinook -c 'SELECT * FROM tracks LIMIT 3'", ch, "table mal nommée")
    Q("psql chinook -c 'SELECT title, nom FROM album LIMIT 3'", ch, "colonne inexistante")
    Q("psql chinook -c 'SELEC * FROM album LIMIT 2'", ch, "mot-clé mal écrit")
    Q("psql chinook -c \"INSERT INTO genre (genre_id, name) VALUES (1, 'Jazz')\"", ch, "clé primaire en double")
    Q("psql chinook -c 'DELETE FROM artist WHERE artist_id = 1'", ch, "clé étrangère")
    Q("psql chinook -c \"INSERT INTO track (name) VALUES ('Essai')\"", ch, "colonne NOT NULL")
    Q("psql chinook -c 'SELECT count(*) FROM invoice WHERE total > 10' -At", ch)
    Q("psql chinook -c 'EXPLAIN SELECT * FROM track WHERE composer = $$AC/DC$$'", ch)
    Q("psql chinook -c 'SELECT 1/0'", ch, "division par zéro")
    Q("psql chinook -c \"SELECT '2026-02-30'::date\"", ch, "date invalide")
    Q("psql pagila -c '\\dt'", pa)
    Q("psql pagila -c 'SELECT rating, count(*) FROM film GROUP BY rating ORDER BY 2 DESC'", pa)
    Q("psql pagila -c 'SELECT count(*) FROM rental WHERE return_date IS NULL'", pa)
    Q("psql pagila -x -c 'SELECT * FROM customer LIMIT 1'", pa)
    Q("psql pagila -c 'SELECT title FROM film WHERE fulltext @@ to_tsquery($$dog & cat$$) LIMIT 5'", pa)
    Q("psql pagila -c 'SELECT * FROM film_embedding LIMIT 1'", pa, "table absente (extension manquante au chargement)")
    Q("psql pagila -c 'SELECT count(*) FROM payment'", pa)
    Q("psql pagila -c '\\di' | head -15", pa)
    Q("psql boutique -f sql/rapport.sql")
    Q("psql boutique -f sql/003_colonne.sql", fault="colonne ajoutée deux fois")
    Q("psql boutique -v ON_ERROR_STOP=1 -f sql/004_erreur.sql", fault="clé étrangère dans une transaction")
    Q("psql boutique -c 'SELECT * FROM stock WHERE quantite = 0'")
    Q("psql boutique -c \"INSERT INTO article (ref, libelle, prix) VALUES ('A-106', 'goupille', -1)\"", fault="contrainte CHECK")
    Q("psql boutique -c \"INSERT INTO entrepot (ville) VALUES ('Rennes')\"", fault="valeur unique en double")
    Q("psql -d inexistante", fault="base inexistante")
    Q("psql -U admin boutique", fault="rôle inexistant")
    Q("psql -h localhost -U app boutique -c 'SELECT count(*) FROM article'", fault="droits insuffisants sur la table")
    Q("psql -h localhost -p 5433 boutique", fault="mauvais port")
    Q("psql boutique", fault="serveur arrêté", start=False, setup="export PGHOST=/home/user/run")
    Q("psql -h 127.0.0.1 boutique", fault="serveur arrêté", start=False)
    Q("pg_isready")
    Q("pg_isready -h /home/user/run", fault="serveur arrêté", start=False)
    Q("pg_dump boutique | head -30")
    Q("pg_dump -t article boutique | grep -c INSERT")
    Q("pg_dump chinook | gzip > chinook.sql.gz && ls -lh chinook.sql.gz", ch)
    Q("pg_dump -Fc boutique -f /sauvegardes/boutique.dump", fault="dossier absent")
    Q("./scripts/sauvegarde_pg.sh")
    Q("./scripts/sauvegarde_pg.sh inexistante", fault="base inexistante")
    Q("./scripts/attendre_base.sh")
    Q("./scripts/attendre_base.sh", fault="serveur arrêté", start=False)
    Q("createdb boutique", fault="base déjà existante")
    Q("createdb essai && psql -l | grep essai")
    Q("dropdb inexistante", fault="base inexistante")
    Q("psql boutique -c 'VACUUM ANALYZE' && psql boutique -c 'SELECT relname, n_live_tup FROM pg_stat_user_tables'")
    Q("psql boutique -c 'SELECT pg_size_pretty(pg_database_size(current_database()))'")
    Q("psql -c 'SELECT version()'")
    Q("psql chinook -c 'SELECT pid, state, query FROM pg_stat_activity WHERE datname IS NOT NULL'", ch)
    Q("pg_ctl -D pg/pgdata status")
    Q("pg_ctl -D pg/pgdata start", fault="serveur déjà lancé")
    Q("pg_ctl -D pg/pgdata -l run/pg.log start", fault="droits du répertoire de données trop ouverts", start=False, setup="chmod 755 pg/pgdata")
    Q("pg_ctl -D pg/absent start", fault="répertoire de données absent", start=False)
    Q("tail -5 run/pg.log", fault="", setup="psql boutique -c 'SELECT * FROM absent' >/dev/null 2>&1")
    Q("psql boutique -c 'BEGIN; LOCK TABLE stock; SELECT pg_sleep(3)' & sleep 1; psql boutique -c 'SET lock_timeout = 1000; UPDATE stock SET quantite = 1'",
      fault="verrou tenu par une autre session")
    V = lambda cmd, fault="", setup="", start=True: out.append(
        S("bases", cmd, (VKSTART + "\n" if start else "") + setup, [], SYN, fault, "", 60))
    seed = "valkey-cli set panier:42 3 >/dev/null; valkey-cli rpush file:emails a b c >/dev/null; valkey-cli hset client:7 nom 'Lucie Ferrand' ville Rennes >/dev/null"
    V("valkey-cli ping")
    V("valkey-cli info server | head -12")
    V("valkey-cli keys '*'", setup=seed)
    V("valkey-cli lrange file:emails 0 -1", setup=seed)
    V("valkey-cli hgetall client:7", setup=seed)
    V("valkey-cli incr panier:42", setup=seed)
    V("valkey-cli lpush panier:42 x", "mauvais type", seed)
    V("valkey-cli dbsize", setup=seed)
    V("valkey-cli info memory | head -8")
    V("valkey-cli ping", "serveur arrêté", start=False)
    V("valkey-cli -p 6380 ping", "mauvais port")
    V("valkey-cli config get maxmemory")
    V("valkey-cli set cle", "arguments manquants")
    V("valkey-cli flushall && valkey-cli dbsize", setup=seed)
    V("valkey-server --port 6379 --bind 127.0.0.1", "port déjà utilisé")
    V("valkey-server --maxmemory beaucoup", "valeur invalide", start=False)
    sq = lambda cmd, fault="": out.append(S("bases", cmd, "", [], SYN, fault, "", 60))
    sq("sqlite3 db/boutique.db .tables")
    sq("sqlite3 -header -column db/boutique.db 'SELECT statut, count(*), round(sum(montant), 2) FROM commande GROUP BY statut'")
    sq("sqlite3 db/boutique.db 'SELECT c.nom, count(*) FROM commande o JOIN client c ON c.id = o.client_id GROUP BY 1 ORDER BY 2 DESC'")
    sq("sqlite3 db/boutique.db 'SELECT * FROM commandes LIMIT 3'", "table mal nommée")
    sq("sqlite3 db/boutique.db \"INSERT INTO commande (client_id, montant, statut) VALUES (1, -5, 'payée')\"", "contrainte CHECK")
    sq("sqlite3 db/boutique.db 'PRAGMA integrity_check'")
    sq("sqlite3 -json db/boutique.db 'SELECT * FROM client WHERE ville = \"Rennes\"'")
    sq("sqlite3 db/boutique.db '.schema commande'")
    return out


# ---------------------------------------------------------------- Docker (client seul, sans démon)
def docker_family():
    out = []
    ac = "compose/awesome-compose"
    samples = ["flask", "nginx-golang-postgres", "react-express-mysql", "prometheus-grafana", "wordpress-mysql",
               "nginx-flask-mongo", "django", "gitea-postgres", "spring-postgres", "traefik-golang"]
    for smp in samples:
        if not exists(f"{ac}/{smp}"):
            continue
        src = lic(ac)
        D = lambda cmd, mode="absent", fault="": out.append(S("docker", cmd, "", [f"compose:{smp}"], src, fault, f"projets/{smp}", 60, mode))
        D("docker compose config", "denied")
        D("docker compose config --services", "denied")
        D("docker compose up -d", "absent", "démon absent")
        D("docker compose up -d", "denied", "socket refusée, utilisateur hors du groupe docker")
        D("docker compose ps", "absent", "démon absent")
        D("docker compose build", "absent", "démon absent")
    O = lambda cmd, mode, fault="", cwd="": out.append(S("docker", cmd, "", [], SYN, fault, cwd, 60, mode))
    for c in ["boutique", "indentation", "cle_inconnue", "env_absent", "dependance", "variable"]:
        O("docker compose config", "absent", "" if c == "boutique" else "fichier compose invalide", f"compose/{c}")
    O("docker compose config -q && echo valide", "absent", "", "compose/boutique")
    O("docker compose up -d", "absent", "démon absent", "compose/boutique")
    O("docker compose -f docker-compose.yml up", "absent", "fichier compose mal nommé", "compose/boutique")
    O("docker compose up -d", "absent", "variable non définie", "compose/variable")
    O("VERSION=2.1 docker compose config", "absent", "", "compose/variable")
    for cmd in ["docker ps", "docker images", "docker version", "docker info", "docker context ls", "docker system df",
                "docker run --rm hello-world", "docker pull alpine:3.20", "docker logs api", "docker exec -it api sh",
                "docker network ls", "docker volume ls", "docker build -t boutique:1.0 .", "docker login registre.example.invalid"]:
        O(cmd, "absent", "démon absent")
    for cmd in ["docker ps -a", "docker images", "docker version", "docker info | tail -12", "docker compose ls",
                "docker stats --no-stream", "docker inspect api"]:
        O(cmd, "denied", "socket refusée, utilisateur hors du groupe docker")
    O("docker buildx version", "absent", "extension absente")
    O("docker compose version", "absent")
    O("docker --version && docker compose version", "absent")
    O("id -nG && ls -l /var/run/docker.sock", "denied", "utilisateur hors du groupe docker")
    O("podman ps", "absent", "podman non installé")
    O("docker-compose up -d", "absent", "ancienne commande absente")
    return out


# ---------------------------------------------------------------- Network (hors ligne, boucle locale)
SRV = {"http": "python3 -m http.server 8080 --bind 127.0.0.1 -d nginx/html >/dev/null 2>&1 &\nsleep 1",
       "nginx": "nginx -p /home/user/nginx -c nginx.conf -e /home/user/nginx/logs/error.log\nsleep 0.5",
       "tls": "openssl s_server -accept 8443 -cert certs/boutique.pem -key certs/boutique.key -www -quiet >/dev/null 2>&1 &\nsleep 1",
       "tls_old": "openssl s_server -accept 8444 -cert certs/ancien.pem -key certs/ancien.key -www -quiet >/dev/null 2>&1 &\nsleep 1",
       "api": "python3 -c \"import http.server as h\nclass R(h.BaseHTTPRequestHandler):\n  def do_GET(s):\n    c = 500 if 'factures' in s.path else (404 if 'absent' in s.path else 200)\n    s.send_response(c); s.send_header('Content-Type','application/json'); s.end_headers(); s.wfile.write(b'{\\\"statut\\\": \\\"ok\\\", \\\"articles\\\": 5}' if c == 200 else b'{\\\"erreur\\\": \\\"interne\\\"}')\n  def log_message(s, *a): pass\nh.HTTPServer(('127.0.0.1', 8081), R).serve_forever()\" &\nsleep 1",
       "slow": "python3 -c \"import socket,time; s=socket.socket(); s.bind(('127.0.0.1',8090)); s.listen(); c,_=s.accept(); time.sleep(30)\" &\nsleep 0.5"}


def net_family():
    out = []
    N = lambda cmd, srv=(), fault="", fam="network-transfer", setup="": out.append(
        S(fam, cmd, "\n".join(SRV[x] for x in srv) + ("\n" + setup if setup else ""), [], SYN, fault, "", 60))
    N("curl -sS http://127.0.0.1:8080/", ["http"])
    N("curl -I http://127.0.0.1:8080/", ["http"])
    N("curl -sS -o /dev/null -w '%{http_code} %{time_total}s\\n' http://127.0.0.1:8080/absent.html", ["http"], "page absente")
    N("curl -v http://127.0.0.1:8080/ 2>&1 | head -20", ["http"])
    N("curl -sS http://127.0.0.1:8080/", [], "connexion refusée")
    N("curl -sS http://127.0.0.1:8081/api/stock", ["api"])
    N("curl -sS -i http://127.0.0.1:8081/api/factures/1003", ["api"], "erreur 500")
    N("curl -fsS http://127.0.0.1:8081/api/factures/1003", ["api"], "erreur 500 avec -f")
    N("curl -fsS http://127.0.0.1:8081/api/absent", ["api"], "erreur 404 avec -f")
    N("curl -sS http://127.0.0.1:8081/api/stock | python3 -m json.tool", ["api"])
    N("curl -sS --max-time 3 http://127.0.0.1:8090/", ["slow"], "délai dépassé")
    N("curl -sS https://registre.example.invalid/v2/", [], "nom introuvable")
    N("curl -sS https://deb.debian.org/debian/", [], "pas de réseau")
    N("curl -sS http://10.20.30.40:8080/", [], "réseau injoignable")
    N("curl -sS https://127.0.0.1:8443/", ["tls"], "certificat autosigné")
    N("curl -sSk https://127.0.0.1:8443/ | head -5", ["tls"])
    N("curl -sS --cacert certs/boutique.pem https://127.0.0.1:8443/", ["tls"], "nom du certificat différent")
    N("curl -sSk -o /dev/null -w '%{http_code}\\n' https://127.0.0.1:8444/", ["tls_old"])
    N("curl -sS --cacert certs/ancien.pem https://127.0.0.1:8444/", ["tls_old"], "certificat expiré")
    N("wget http://127.0.0.1:8080/index.html", ["http"])
    N("wget -q -O - http://127.0.0.1:8080/", ["http"])
    N("wget http://127.0.0.1:8080/archive.tar.gz", ["http"], "fichier absent")
    N("wget http://127.0.0.1:8080/", [], "connexion refusée")
    N("wget https://miroir.example.invalid/paquet.deb", [], "nom introuvable")
    N("wget --tries=2 --timeout=2 http://127.0.0.1:8090/", ["slow"], "délai dépassé")
    N("openssl s_client -connect 127.0.0.1:8443 -brief < /dev/null", ["tls"])
    N("openssl s_client -connect 127.0.0.1:8444 < /dev/null 2>&1 | grep -iE 'verify|subject|issuer|expired'", ["tls_old"], "certificat expiré")
    N("openssl s_client -connect 127.0.0.1:9443 < /dev/null", [], "connexion refusée")
    N("openssl x509 -in certs/boutique.pem -noout -subject -dates")
    N("openssl x509 -in certs/ancien.pem -noout -checkend 0", fault="certificat expiré")
    N("openssl verify certs/boutique.pem", fault="certificat autosigné")
    N("./scripts/verifier_certs.sh", fault="un certificat expiré, un proche de l'expiration")
    N("./scripts/sante.sh", ["api"], setup="", fault="")
    N("./scripts/sante.sh http://127.0.0.1:8081/api/stock", ["api"])
    N("./scripts/sante.sh", [], "service injoignable")
    N("ss -tln", ["http", "api"], fam="network")
    N("ss -tlnp", ["nginx", "api"], fam="network")
    N("ss -s", ["http"], fam="network")
    N("ss -tan", ["http", "slow"], fam="network", setup="curl -s -m 1 http://127.0.0.1:8090/ >/dev/null 2>&1 &\nsleep 0.3")
    N("netstat -tlnp", ["http", "tls"], fam="network")
    N("ip addr", fam="network")
    N("ip -br link", fam="network")
    N("ip route", fam="network")
    N("ip route get 1.1.1.1", fault="aucune route", fam="network")
    N("ping -c 2 127.0.0.1", fault="ping sans capacité réseau", fam="network")
    N("ping -c 2 serveur-interne.example.invalid", fault="ping sans capacité réseau", fam="network")
    N("nc -zv 127.0.0.1 8080", ["http"], fam="network")
    N("nc -zv 127.0.0.1 5432", [], "port fermé", fam="network")
    N("nc -zv -w 2 127.0.0.1 8079-8082", ["http", "api"], fam="network")
    N("dig example.invalid", fault="aucun serveur DNS", fam="network")
    N("dig +short @127.0.0.1 boutique.example.invalid", fault="aucun serveur DNS", fam="network")
    N("host registre.example.invalid", fault="aucun serveur DNS", fam="network")
    N("nslookup api.example.invalid", fault="aucun serveur DNS", fam="network")
    N("getent hosts machine-demo localhost", fam="network")
    N("cat /etc/hosts /etc/resolv.conf", fam="network")
    N("ssh -p 2222 user@127.0.0.1", [], "connexion refusée")
    N("ssh -o BatchMode=yes -o ConnectTimeout=3 deploiement@serveur.example.invalid", [], "nom introuvable")
    N("scp data/commandes.csv user@serveur.example.invalid:/tmp/", [], "nom introuvable")
    N("rsync -av data/ sauvegarde/", [])
    N("rsync -av --dry-run --delete data/ logs/", [])
    N("rsync -av data/ user@serveur.example.invalid:/srv/data/", [], "nom introuvable")
    N("rsync -a data/ /srv/sauvegarde/", [], "destination non inscriptible")
    return out


# ---------------------------------------------------------------- Services (sans systemd)
def svc_family():
    out = []
    V = lambda cmd, fault="", setup="", fam="services-logs": out.append(S(fam, cmd, setup, [], SYN, fault, "", 60))
    for conf, fault in [("nginx.conf", ""), ("sans_point_virgule.conf", "point-virgule manquant"),
                        ("directive_inconnue.conf", "directive inconnue"), ("amont_introuvable.conf", "hôte amont introuvable"),
                        ("include_absent.conf", "fichier inclus absent"), ("double_location.conf", "location en double"),
                        ("accolade.conf", "accolade manquante"), ("port_prive.conf", "port privilégié")]:
        V(f"nginx -t -p /home/user/nginx -c {conf} -e /home/user/nginx/logs/error.log", fault)
    V("nginx -t", "configuration système sans droits")
    V("nginx -p /home/user/nginx -c port_prive.conf -e /home/user/nginx/logs/error.log", "port privilégié")
    V("nginx -p /home/user/nginx -c nginx.conf -e /home/user/nginx/logs/error.log", "port déjà utilisé", SRV["http"])
    V("nginx -p /home/user/nginx -c nginx.conf -e /home/user/nginx/logs/error.log -s reload", "aucun processus maître")
    V("nginx -p /home/user/nginx -c nginx.conf -e /home/user/nginx/logs/error.log -s reload && echo rechargé", "", SRV["nginx"])
    V("curl -sS http://127.0.0.1:8080/api/stock", "amont arrêté (502)", SRV["nginx"])
    V("curl -sS http://127.0.0.1:8080/api/stock", "", SRV["nginx"] + "\n" + SRV["api"])
    V("tail -3 nginx/logs/error.log", "amont arrêté", SRV["nginx"] + "\ncurl -s http://127.0.0.1:8080/api/stock >/dev/null")
    V("tail -4 nginx/logs/access.log", "", SRV["nginx"] + "\nfor p in / /absent /api/x; do curl -s http://127.0.0.1:8080$p >/dev/null; done")
    V("ps aux | grep [n]ginx", "", SRV["nginx"], fam="processes")
    V("nginx -V 2>&1 | head -3")
    V("systemctl status nginx", "pas de systemd")
    V("systemctl restart nginx", "pas de systemd")
    V("systemctl list-units --failed", "pas de systemd")
    V("journalctl -u nginx -n 20", "aucun journal")
    V("service nginx status", "script d'init sans droits")
    V("service valkey-server status")
    V("service ssh status")
    V("/usr/sbin/sshd -t -f sshd/sshd_config")
    V("/usr/sbin/sshd -t -f sshd/sshd_config.faute", "mot-clé mal orthographié")
    V("/usr/sbin/sshd -t -f sshd/sshd_config.cle_absente", "clé d'hôte absente")
    V("/usr/sbin/sshd -t -f sshd/sshd_config.valeur", "valeur invalide")
    V("/usr/sbin/sshd -t", "configuration système sans droits")
    V("/usr/sbin/sshd -f sshd/sshd_config -D -e", "privilèges requis")
    V("crontab -l", "aucune crontab")
    V("crontab cron/casse.cron", "champ horaire invalide")
    V("crontab cron/ok.cron && crontab -l", "démon cron absent, crontab refusée ?")
    V("valkey-server --port 6379 --bind 127.0.0.1 --maxmemory-policy nimporte", "valeur invalide")
    V("valkey-cli shutdown && valkey-cli ping", "", VKSTART)
    V("pg_ctl -D pg/pgdata stop -m fast", "", PGSTART, fam="bases")
    V("tail -8 run/pg.log", "", PGSTART + "\npg_ctl -D pg/pgdata stop -m fast >/dev/null", fam="bases")
    V("timeout 5 python3 -m http.server 8080 --bind 127.0.0.1", "port déjà utilisé", SRV["http"])
    V("python3 -m http.server 80", "port privilégié")
    V("./scripts/sante.sh http://127.0.0.1:8080/", "", SRV["nginx"])
    return [s if s["family"] != "bases" or "pg" in s["needs"] else {**s, "needs": ["pg"]} for s in out]


# ---------------------------------------------------------------- Packages
def pkg_family():
    out = []
    K = lambda cmd, fault="", setup="": out.append(S("packages-system", cmd, setup, [], SYN, fault, "", 120))
    for p in ["jq", "nginx-light", "postgresql-17", "python3-requests", "golang-go", "htop", "neovim", "paquet-inexistant"]:
        K(f"apt-cache policy {p}", "paquet inconnu" if p == "paquet-inexistant" else "")
    for p in ["htop", "python3-requests", "neovim", "jq", "paquet-inexistant", "libssl-dev"]:
        K(f"apt-get install -s {p} | tail -6", "paquet inconnu" if p == "paquet-inexistant" else "")
    K("apt-get install htop", "droits administrateur requis")
    K("apt-get update", "droits administrateur requis")
    K("apt-get remove jq", "droits administrateur requis")
    K("apt install python3-flask", "droits administrateur requis")
    K("apt-get -s upgrade | tail -5")
    K("apt list --upgradable 2>/dev/null | head")
    K("apt list --installed 2>/dev/null | wc -l")
    K("apt-cache show jq | head -15")
    K("apt-cache depends nginx-light")
    K("apt-cache rdepends --installed libpq5 | head")
    K("apt-cache search --names-only '^python3-pytest' | head")
    K("apt show valkey-server 2>/dev/null | head -12")
    K("dpkg -l | grep -E '^ii +(nginx|valkey|postgresql)' ")
    K("dpkg -L jq")
    K("dpkg -S /usr/bin/psql")
    K("dpkg -S /usr/bin/htop", "fichier d'aucun paquet")
    K("dpkg -s nginx-light | head -8")
    K("dpkg -i paquet.deb", "fichier absent")
    K("dpkg --audit")
    K("pip install requests", "environnement géré par le système")
    K("pip install --user flask", "environnement géré par le système")
    K("pip list 2>/dev/null | head -15")
    K("pip show pytest")
    K("pip show inexistant", "paquet non installé")
    K("pip check")
    K("pip freeze | wc -l")
    K("python3 -m venv .venv && .venv/bin/pip install flask", "hors ligne")
    K("python3 -m venv .venv && .venv/bin/pip install -r requirements.txt", "fichier absent")
    K(".venv/bin/pip install flask", "environnement virtuel absent")
    K("python3 -m venv .venv && .venv/bin/pip list")
    K("pipx install ruff", "pipx absent")
    K("npm install -g yarn", "droits insuffisants et hors ligne")
    K("npm ls -g --depth=0")
    K("npm view express version", "hors ligne")
    K("npm init -y && cat package.json", "")
    K("npm audit", "aucun package.json")
    K("gem install rails", "ruby absent")
    K("snap install code", "snap absent")
    K("flatpak list", "flatpak absent")
    K("brew install jq", "brew absent")
    K("which psql pg_dump nginx node go cargo rustc gcc make cmake")
    K("go version; node --version; cargo --version; rustc --version")
    K("cat /etc/os-release")
    K("uname -srm")
    K("ls /etc/apt/sources.list.d/ && cat /etc/apt/sources.list.d/*")
    K("apt-mark showmanual | head")
    K("update-alternatives --display editor", "alternative absente")
    return out


# ---------------------------------------------------------------- Shell scripts
def sh_family():
    out = []
    X = lambda cmd, fault="", setup="", needs=(), src=SYN, cwd="", fam="shell-scripts": out.append(S(fam, cmd, setup, needs, src, fault, cwd, 60))
    X("./scripts/rotation_journaux.sh")
    X("./scripts/rotation_journaux.sh journaux", "dossier absent, glob non développé")
    X("./scripts/installer_deps.sh", "droits administrateur requis")
    X("./scripts/verifier_certs.sh", "un certificat expiré")
    X("./scripts/compter.sh")
    X("./scripts/deployer.sh", "variable CIBLE non définie avec set -u")
    X("CIBLE=/srv/app ./scripts/deployer.sh", "destination non inscriptible")
    X("CIBLE=$HOME/deploiement ./scripts/deployer.sh && ls deploiement")
    X("./scripts/nettoyer.sh", "dossier cache absent")
    X("./scripts/nettoyer.sh", "", "mkdir -p cache && touch cache/a.tmp b.tmp data/c.tmp")
    X("./scripts/archiver.sh")
    X("./scripts/archiver.sh", "fichier illisible", "chmod 000 config/app.ini")
    X("bash -x scripts/compter.sh 2>&1 | head -15")
    X("sh -n scripts/rotation_journaux.sh && echo ok")
    X("shellcheck scripts/*.sh", fam="lint-format")
    X("shellcheck scripts/compter.sh scripts/nettoyer.sh", fam="lint-format")
    X("shellcheck -S warning scripts/*.sh", fam="lint-format")
    X("shellcheck -f gcc scripts/deployer.sh scripts/sante.sh", fam="lint-format")
    X("shellcheck scripts/archiver.sh && echo aucun problème", fam="lint-format")
    X("bats --version")
    for name, body, fault in [
        ("ok", "@test \"addition\" {\n  result=$((2 + 2))\n  [ \"$result\" -eq 4 ]\n}\n@test \"fichier de config présent\" {\n  [ -f config/app.ini ]\n}\n", ""),
        ("echec", "@test \"total des commandes\" {\n  run python3 py/rapport.py\n  [ \"$status\" -eq 0 ]\n  [[ \"$output\" == *\"8 commandes payées\"* ]]\n}\n@test \"script de santé\" {\n  run ./scripts/sante.sh\n  [ \"$status\" -eq 0 ]\n}\n", "attente fausse, service arrêté"),
        ("syntaxe", "@test \"cassé\" {\n  run ls\n  [ \"$status\" -eq 0 \n}\n", "crochet non fermé"),
    ]:
        X(f"bats tests_{name}.bats", fault, f"cat > tests_{name}.bats <<'EOF'\n{body}EOF", fam="tests")
    bs = "shell/Bash-Snippets"
    if exists(bs):
        src = lic(bs)
        for t in ["weather/weather", "stocks/stocks", "todo/todo", "short/short", "crypt/crypt", "newton/newton", "cheat/cheat", "qrify/qrify"]:
            X(f"shellcheck {t} | head -30", "", "", ["sh:Bash-Snippets"], src, "projets/Bash-Snippets", "lint-format")
        X("bash weather/weather Rennes", "hors ligne", "", ["sh:Bash-Snippets"], src, "projets/Bash-Snippets")
        X("bash todo/todo -h", "", "", ["sh:Bash-Snippets"], src, "projets/Bash-Snippets")
        X("./install.sh todo", "droits insuffisants", "", ["sh:Bash-Snippets"], src, "projets/Bash-Snippets")
        X("bats tests/todo.bats", "", "", ["sh:Bash-Snippets"], src, "projets/Bash-Snippets", "tests")
        X("bats tests/", "hors ligne", "", ["sh:Bash-Snippets"], src, "projets/Bash-Snippets", "tests")
    gf = "shell/gitflow"
    if exists(gf):
        src = lic(gf)
        for t in ["git-flow", "git-flow-feature", "git-flow-release", "git-flow-init", "gitflow-common"]:
            X(f"shellcheck -s sh {t} | tail -20", "", "", ["sh:gitflow"], src, "projets/gitflow", "lint-format")
        X("make install", "préfixe non inscriptible", "", ["sh:gitflow"], src, "projets/gitflow", "build-native")
    fz = "shell/fzf"
    if exists(fz):
        src = lic(fz)
        X("./install --help", "", "", ["sh:fzf"], src, "projets/fzf")
        X("./install --bin", "hors ligne, binaire à télécharger", "", ["sh:fzf"], src, "projets/fzf")
        X("shellcheck install | tail -25", "", "", ["sh:fzf"], src, "projets/fzf", "lint-format")
        X("shellcheck bin/fzf-tmux | head -20", "", "", ["sh:fzf"], src, "projets/fzf", "lint-format")
    return out


# ---------------------------------------------------------------- Files
def files_family():
    out = []
    trees = [("python/attrs", "attrs"), ("go/mux", "mux"), ("c/libuv", "libuv"), ("js/vary", "vary"), ("rust/walkdir", "walkdir"),
             ("compose/awesome-compose", "awesome-compose"), ("c/libexpat", "libexpat")]
    for d, name in trees:
        kind = d.split("/")[0]
        need = {"python": "py", "go": "go", "c": "c", "js": "js", "rust": "rs", "compose": "compose-all"}[kind] + ":" + name
        src = lic(d)
        F = lambda cmd, fault="", setup="": out.append(S("files", cmd, setup, [need], src, fault, f"projets/{name}", 60))
        F("ls -la")
        F("ls -lhS | head -10")
        F("du -sh * | sort -h | tail -8")
        F("du -h --max-depth=1 . | sort -h")
        F("find . -type f | wc -l")
        F("find . -name '*.md' | head -15")
        F("find . -type f -size +100k -exec ls -lh {} + | awk '{print $5, $9}' | head")
        F("find . -type d -empty")
        F("find . -newer README.md -type f | head", "README absent ?")
        F("grep -rn TODO --include='*.*' . | head -12")
        F("grep -rc 'func\\|def \\|function' . 2>/dev/null | grep -v ':0' | sort -t: -k2 -n | tail -6")
        F("grep -rl 'Copyright' . | wc -l")
        F("wc -l $(git ls-files 2>/dev/null || find . -maxdepth 1 -type f) 2>&1 | tail -5")
        F("tree -L 2 | tail -20")
        F("tree -d -L 2")
        F("file * | head -15")
        F("stat LICENSE* COPYING* 2>&1 | head -12")
        F("tar czf ../archive.tgz . && ls -lh ../archive.tgz")
        F("tar czf /opt/archive.tgz .", "destination non inscriptible")
        F("tar tzf ../absent.tgz", "archive absente")
        F("zip -qr ../sources.zip . && unzip -l ../sources.zip | tail -3")
        F("cp -r . /usr/local/src/copie", "destination non inscriptible")
        F("mv README.md docs/", "dossier de destination absent")
        F("rm fichier-absent.txt", "fichier absent")
        F("rm -r .", "suppression du dossier courant refusée")
        F("chmod 644 /etc/hosts", "fichier d'un autre utilisateur")
        F("cat .", "dossier lu comme un fichier")
        F("head -c 300 LICENSE* COPYING* 2>/dev/null")
        F("sha256sum * 2>/dev/null | head -5")
        F("sha256sum -c sommes.txt", "somme de contrôle modifiée", "sha256sum $(find . -maxdepth 1 -type f | head -4) > sommes.txt && echo x >> $(find . -maxdepth 1 -type f ! -name sommes.txt | head -1)")
        F("diff -rq . /srv/src/" + d + " | head", "fichiers modifiés", "echo '# note locale' >> $(find . -maxdepth 1 -type f -name '*.md' | head -1)")
        F("ln -s LICENSE lien && ls -l lien && ln -s LICENSE lien", "lien déjà existant")
        F("mkdir src", "dossier déjà existant")
        F("touch /srv/src/test", "système de fichiers en lecture seule")
        F("ls -la --time-style=long-iso | sort -k6,7 | tail -5")
    G = lambda cmd, fault="", setup="": out.append(S("files", cmd, setup, [], SYN, fault, "", 60))
    G("wc -l logs/*.log data/*.csv")
    G("grep -c ERROR logs/api.log")
    G("grep ERROR logs/api.log | awk '{print $4}' | sort | uniq -c | sort -rn")
    G("awk '$6+0 > 1000 {print $3, $4, $5, $6}' logs/api.log | head")
    G("cut -d, -f2 data/commandes.csv | sort | uniq -c | sort -rn")
    G("sort -t, -k3 -n -r data/commandes.csv | head -4")
    G("column -s, -t data/commandes.csv")
    G("diff config/app.ini config/app.yaml | head -20")
    G("diff -u data/commandes.csv data/commandes.old.csv", "fichier absent")
    G("diff -u data/commandes.csv data/commandes.old.csv", "", "sed '3d; 5s/310.00/301.00/' data/commandes.csv > data/commandes.old.csv")
    G("cmp data/commandes.csv data/commandes.bak", "", "cp data/commandes.csv data/commandes.bak && sed -i 's/Mila/Milla/' data/commandes.bak")
    G("iconv -f utf-8 -t ascii data/commandes.csv", "caractères non convertibles")
    G("file data/*")
    G("jq '.[] | select(.actif) | .nom' data/clients.json")
    G("jq length data/clients.json")
    G("jq '.port' data/settings_casse.json", "JSON invalide")
    G("jq '.[0].adresse.rue' data/clients.json")
    G("jq -r '.[] | \"\\(.nom) (\\(.ville))\"' data/clients.json")
    G("find . -name '*.log' -mmin -60")
    G("find / -name pg_hba.conf 2>/dev/null | head -3")
    G("find /etc -maxdepth 1 -name '*.conf' | head", "")
    G("ls -la /root", "permission refusée")
    G("cat /etc/shadow", "permission refusée")
    G("sudo cat /etc/shadow", "sudo absent")
    G("touch /etc/app.conf", "système de fichiers en lecture seule")
    G("chmod +x data/commandes.csv && ls -l data/commandes.csv")
    G("chown root data/commandes.csv", "opération non permise")
    G("umask; touch nouveau && ls -l nouveau")
    G("id; groups")
    G("ls -l scripts/ | head")
    G("tar czf sauvegarde.tgz data logs && tar tvzf sauvegarde.tgz")
    G("gzip -k logs/api.log && ls -l logs/")
    G("gunzip logs/api.log.gz", "archive absente")
    G("tail -n 5 logs/worker.log")
    G("head -3 data/commandes.csv; tail -2 data/commandes.csv")
    G("grep -n 'échouée' logs/worker.log")
    G("sed -n '10,14p' logs/api.log")
    G("xargs -a /dev/null echo vide")
    G("stat -c '%n %s octets %y' data/*")
    G("split -l 4 data/commandes.csv part_ && wc -l part_*")
    return out


# ---------------------------------------------------------------- Git
def git_family():
    out = []
    R = lambda cmd, fault="", setup="", cwd="git/facturation": out.append(S("vcs-git", cmd, setup, [], SYN, fault, cwd, 60))
    idt = "export GIT_AUTHOR_NAME='Camille Martin' GIT_AUTHOR_EMAIL=camille.martin@example.invalid GIT_COMMITTER_NAME='Camille Martin' GIT_COMMITTER_EMAIL=camille.martin@example.invalid"
    R("git status")
    R("git status", "fichier modifié et fichier non suivi", "echo '# brouillon' >> README.md; touch notes.txt")
    R("git status -s", "", "echo x >> README.md; git add README.md; echo y >> facturation/rapport.py; touch tmp.log")
    R("git log --oneline | head -12")
    R("git log --oneline --graph --all | head -20")
    R("git log -3 --stat")
    R("git log --since=2026-09-10 --format='%h %an %s'")
    R("git shortlog -sn")
    R("git branch -a")
    R("git branch -vv")
    R("git tag -n")
    R("git describe --tags")
    R("git show --stat HEAD~6")
    R("git diff HEAD~1 --stat")
    R("git diff main export-json -- facturation/calcul.py")
    R("git blame -L 20,25 facturation/calcul.py")
    R("git remote -v")
    R("git merge export-json", "conflit de fusion", idt)
    R("git merge export-json; git status", "conflit de fusion", idt)
    R("git diff", "conflit de fusion", idt + "\ngit merge export-json")
    R("git merge --abort && git status -s", "", idt + "\ngit merge export-json")
    R("git rebase main", "conflit de rebase", idt + "\ngit checkout -q export-json")
    R("git cherry-pick export-json", "conflit de cherry-pick", idt)
    R("git checkout develop", "branche inexistante")
    R("git switch -c correctif && git branch")
    R("git checkout export-json", "modifications locales écrasées", "sed -i 's/Total TTC/Total/' facturation/calcul.py")
    R("git stash && git stash list", "", idt + "\necho '# essai' >> README.md")
    R("git stash pop", "conflit au retour du remisage", idt + "\nsed -i 's/remises comprises/avec remises/' facturation/calcul.py\ngit stash -q\nsed -i 's/remises comprises/hors remises/' facturation/calcul.py\ngit commit -qam 'Autre libellé'")
    R("git commit -m 'Correction'", "rien à valider", idt)
    R("git commit -am 'Mise à jour du README'", "", idt + "\necho '- nouvelle entrée' >> README.md")
    R("git commit -m 'Sans identité'", "identité absente", "echo x >> README.md; git add README.md")
    R("git push", "", idt + "\necho '- entrée' >> CHANGELOG.md\ngit commit -qam 'Nouvelle entrée'")
    R("git push", "branche distante en avance", idt + "\ncd /home/user/git && git clone -q facturation.git autre && cd autre && echo z >> README.md && git commit -qam 'Changement distant' && git push -q && cd ../facturation\necho '- local' >> CHANGELOG.md\ngit commit -qam 'Changement local'")
    R("git pull", "divergence sans stratégie de fusion", idt + "\ncd /home/user/git && git clone -q facturation.git autre && cd autre && echo z >> README.md && git commit -qam 'Changement distant' && git push -q && cd ../facturation\necho '- local' >> CHANGELOG.md\ngit commit -qam 'Changement local'")
    R("git pull --rebase", "", idt + "\ncd /home/user/git && git clone -q facturation.git autre && cd autre && echo z >> README.md && git commit -qam 'Changement distant' && git push -q && cd ../facturation")
    R("git fetch miroir", "hôte distant introuvable")
    R("git push miroir main", "hôte distant introuvable")
    R("git clone https://git.example.invalid/equipe/outil.git", "hôte distant introuvable", "", "git")
    R("git clone facturation.git copie && ls copie", "", "", "git")
    R("git status", "pas un dépôt git", "", "data")
    R("git log", "dépôt sans commit", "", "run")
    R("git init projet && cd projet && git status", "", "", "")
    R("git reset --hard HEAD~2 && git log --oneline | head -3")
    R("git revert --no-edit HEAD", "", idt)
    R("git bisect start HEAD v0.1.0 && git bisect run grep -q 'remises comprises' facturation/calcul.py", "", idt)
    R("git clean -n", "", "touch a.tmp b.log; mkdir -p build")
    R("git rm facturation/absent.py", "fichier non suivi")
    R("git add inexistant.txt", "chemin absent")
    R("git mv README.md docs/README.md", "dossier absent")
    R("git fsck")
    R("git count-objects -vH")
    R("git config --list --show-origin | head")
    R("git log --oneline main..export-json")
    R("git diff --check", "espaces en fin de ligne", "printf 'def f():  \\n    return 1   \\n' >> facturation/rapport.py")
    R("git checkout v0.1.0", "tête détachée")
    R("git tag v0.1.0", "étiquette déjà existante")
    R("git branch -d export-json", "branche non fusionnée")
    R("git log --oneline -3", "", "", "git/site")
    R("git status", "", "rm index.html", "git/site")
    return out


def scenarios():
    return (python_family() + python_scripts() + js_family() + go_family() + rust_family() + c_family() + db_family()
            + docker_family() + net_family() + svc_family() + pkg_family() + sh_family() + files_family() + git_family())


# ---------------------------------------------------------------- runner
WS_ROOT = "/dev/shm/g3c-ws"


def assemble(ws, needs):
    shutil.copytree(os.path.join(TPL, "base"), ws, symlinks=True, ignore=shutil.ignore_patterns("pg"))
    for n in needs:
        kind, _, name = n.partition(":")
        dst = os.path.join(ws, "projets", name)
        if kind == "py":
            shutil.copytree(os.path.join(SRC, "python", name), dst, symlinks=True)
        elif kind == "js":
            shutil.copytree(os.path.join(SRC, "js", name), dst, symlinks=True, ignore=shutil.ignore_patterns("node_modules"))
            os.symlink(f"/srv/src/js/{name}/node_modules", os.path.join(dst, "node_modules"))
        elif kind == "go":
            shutil.copytree(os.path.join(SRC, "go", name), dst, symlinks=True)
            shutil.copytree(os.path.join(SRC, "gocache"), os.path.join(ws, ".cache", "go-build"))
        elif kind == "rs":
            shutil.copytree(os.path.join(SRC, "rust", name), dst, symlinks=True)
            os.makedirs(os.path.join(ws, ".cargo"), exist_ok=True)
            os.symlink("/srv/src/cargo-home/registry", os.path.join(ws, ".cargo", "registry"))
        elif kind == "c":
            shutil.copytree(os.path.join(SRC, "c", name), dst, symlinks=True)
        elif kind == "ready":
            shutil.copytree(os.path.join(SRC, "ready", name), dst, symlinks=True)
        elif kind == "sh":
            shutil.copytree(os.path.join(SRC, "shell", name), dst, symlinks=True)
        elif kind == "compose":
            shutil.copytree(os.path.join(SRC, "compose", "awesome-compose", name), dst, symlinks=True)
        elif kind == "compose-all":
            shutil.copytree(os.path.join(SRC, "compose", name), dst, symlinks=True)
        elif kind == "pg":
            shutil.copytree(os.path.join(TPL, "base", "pg"), os.path.join(ws, "pg"), symlinks=True)


RUNNER_PREFIX = re.compile(r"^/bin/bash ?: (?:ligne|line) \d+ ?: ", re.M)


def run_one(idx, sc, lang):
    ws = os.path.join(WS_ROOT, f"{idx}-{lang[:2]}")
    shutil.rmtree(ws, ignore_errors=True)
    assemble(ws, sc["needs"])
    subprocess.run(["chown", "-R", "1000:1000", ws], check=True)
    body = "cd /home/user\n"
    if sc["cwd"]:
        body += f"cd {sc['cwd']}\n"
    if sc["setup"]:
        body += f"{{\n{sc['setup']}\n}} </dev/null >/dev/null 2>&1\n"
    body += f"{{ {sc['cmd']} ; }} </dev/null\n"
    env = dict(os.environ, G3C_SRC=SRC, G3C_TPL=TPL)
    t0 = time.time()
    try:
        p = subprocess.run(["timeout", "-k", "5", str(sc["timeout"]), os.path.join(G, "sbx.sh"), os.path.join(G, "rootfs"), ws, lang, sc["docker"]],
                           input=body.encode(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=sc["timeout"] + 20, env=env)
        code, raw = p.returncode, p.stdout
    except subprocess.TimeoutExpired as e:
        code, raw = 124, e.stdout or b""
    dur = time.time() - t0
    shutil.rmtree(ws, ignore_errors=True)
    out = RUNNER_PREFIX.sub("bash: ", raw.decode("utf-8", errors="replace"))
    lines = out.splitlines()
    if len(lines) > 400:
        out = "\n".join(lines[:200] + lines[-200:])
    out = out[:20000]
    return {"cmd": sc["cmd"], "family": sc["family"], "source": sc["source"], "fault": sc["fault"], "cwd": sc["cwd"],
            "docker_mode": sc["docker"] if sc["family"] == "docker" else "", "scenario": idx,
            "lang": "fr" if lang == FR else "en", "locale": lang, "exit": code, "duration": round(dur, 2), "output": out}


def main(out_path):
    scs = scenarios()
    print(f"{len(scs)} scénarios", flush=True)
    os.makedirs(WS_ROOT, exist_ok=True)
    only = os.environ.get("G3C_ONLY")
    keep = {int(x) for x in only.split(",")} if only else None
    done = set()
    if os.path.exists(out_path):
        for l in open(out_path):
            d = json.loads(l)
            done.add((d["scenario"], d["lang"]))
    jobs = [(i, s, lang) for i, s in enumerate(scs) for lang in (FR, EN)
            if (keep is None or i in keep) and (i, "fr" if lang == FR else "en") not in done]
    workers = int(os.environ.get("G3C_WORKERS", "5"))
    with open(out_path, "a", encoding="utf-8") as f, concurrent.futures.ThreadPoolExecutor(workers) as ex:
        for res in ex.map(lambda j: run_one(*j), jobs):
            f.write(json.dumps(res, ensure_ascii=False) + "\n")
            f.flush()
    print(f"{len(jobs)} exécutions ajoutées à {out_path}", flush=True)


if __name__ == "__main__":
    if sys.argv[2] == "--count":
        scs = scenarios()
        print(collections.Counter(s["family"] for s in scs), len(scs))
        print(len({s["cmd"] for s in scs}), "commandes distinctes")
    elif sys.argv[2] == "--list":
        for i, s in enumerate(scenarios()):
            print(i, s["family"], s["cmd"][:90], "|", s["fault"])
    else:
        main(sys.argv[2])
