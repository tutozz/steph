"""Détecteurs de formats documentés (couverture seulement, aucune phrase) : règle -> (lot, famille, test)."""
import re
M = lambda p: re.compile(p, re.M)
def has(p): return lambda cmd, code, out, w: bool(p.search(out))
def cmdre(c, p=None): 
    cr = re.compile(c)
    return lambda cmd, code, out, w: bool(cr.search(cmd)) and (p is None or bool(p.search(out)))
def fails(f): return lambda cmd, code, out, w: code not in (0, None) and f(cmd, code, out, w)

RULES = [
 # lot A : tests et lint/typage
 ("A", "tests", "unittest Ran/OK/FAILED", has(M(r"^Ran \d+ tests? in [\d.]+s\s*$"))),
 ("A", "tests", "go test lignes de paquet ok/FAIL/?", lambda c, e, o, w: "-json" not in c and bool(M(r"^(ok|FAIL|\?)\s+\S+\s").search(o)) and c.split()[0] in ("go",)),
 ("A", "tests", "TAP node --test / spec ℹ tests", has(M(r"^(# (tests|pass|fail) \d+|ℹ (tests|pass|fail) \d+)\s*$"))),
 ("A", "tests", "deno test ok|FAILED | N passed", has(M(r"^(ok|FAILED) \| \d+ passed"))),
 ("A", "tests", "jest No tests found", has(M(r"^No tests found"))),
 ("A", "lint-type", "ruff Found N errors / All checks passed", has(M(r"^Found \d+ errors?\.|^All checks passed!"))),
 ("A", "lint-type", "ruff/eslint erreur de configuration", fails(has(M(r"^(ruff failed|error: TOML parse error|Oops! Something went wrong|ESLint couldn't find)")))),
 ("A", "lint-type", "pylint rated at", has(M(r"Your code has been rated at -?[\d.]+/10"))),
 ("A", "lint-type", "shellcheck In f line N / SC", has(M(r"^In \S+ line \d+:"))),
 ("A", "lint-type", "yamllint N:N error|warning", lambda c, e, o, w: "yamllint" in c and bool(M(r"^\s+\d+:\d+\s+(error|warning)\s").search(o))),
 ("A", "lint-type", "tsc/mypy Found N errors in M files / Success", has(M(r"^Found \d+ errors? in \d+ files?|^Success: no issues found|^TSFILE: "))),
 ("A", "compile", "cargo Finished / generated N warnings", has(M(r"^\s*Finished .*in [\d.]+m?s\s*$|generated \d+ warnings?"))),
 ("A", "compile", "panic Rust thread panicked at f:l", has(M(r"panicked at [^:\s]+:\d+:\d+"))),
 ("A", "compile", "panic Go / deadlock", has(M(r"^panic: |^fatal error: all goroutines are asleep"))),
 ("A", "compile", "gcc/clang réussite avec avertissements (1er fichier:ligne)", lambda c, e, o, w: e == 0 and bool(M(r"^[^\s:]+\.(c|cc|cpp|h|hpp):\d+:\d+: warning:").search(o))),
 ("A", "compile", "édition de liens clang Undefined symbols", has(M(r"^Undefined symbols for architecture|undefined reference to"))),
 ("A", "runtime", "python compileall *** Error compiling", lambda c, e, o, w: "compileall" in c and "Error compiling" in o),
 # lot B : scripts shell et fichiers
 ("B", "scripts", "bash/sh f: line N: msg (dernière ou première)", has(M(r"^\S+?: (?:line|ligne) \d+ ?: "))),
 ("B", "scripts", "erreur d'outil GNU dans un script (cp:/mv:/sort: ...)", lambda c, e, o, w: e not in (0, None) and bool(M(r"^(cp|mv|rm|tar|sort|cat|mkdir|ln|chmod|rsync|scp|ssh|curl|grep): .+").search(o))),
 ("B", "files", "verbeux compté (rm -v, mkdir -v, chmod -v/-c, chown -v, cp -v, ln -sv, split --verbose, tar -v, shred -v)", lambda c, e, o, w: bool(re.search(r"^(rm|mkdir|chmod|chown|cp|ln|split|tar|shred)\b.*\s-\w*v|--verbose|chmod -\w*c", " ".join(w)))),
 ("B", "files", "sha*sum/md5sum -c : OK / FAILED / WARNING", lambda c, e, o, w: bool(re.search(r"(md5|sha\d+)sum\b.*\s-c\b", c)) and bool(M(r": (OK|FAILED|RÉUSSI|ÉCHEC)").search(o))),
 ("B", "files", "wc plusieurs fichiers ligne total", lambda c, e, o, w: w[:1] == ["wc"] and bool(M(r"^\s*\d+\s+(total|au total)$").search(o))),
 ("B", "files", "grep -r compte de lignes et fichiers (sans tube)", lambda c, e, o, w: w[:1] in (["grep"], ["rg"]) and "|" not in c and e == 0),
 ("B", "files", "diff -q/-rq : differ / Only in", lambda c, e, o, w: w[:1] == ["diff"] and bool(M(r"^(Files .+ and .+ differ|Only in |Les fichiers .+ sont différents|Seulement dans )").search(o))),
 ("B", "files", "rsync -v/--stats bilan sent/received", has(M(r"^sent [\d,.]+ bytes\s+received|^total size is"))),
 # lot C : paquets, git, conteneurs, infra
 ("C", "packages", "npm/pnpm added N packages, vulnerabilities, npm error code", has(M(r"^(added|removed|changed) \d+ packages?|\d+ vulnerabilit(y|ies)|^npm (ERR!|error) code|^Packages: \+\d+|ERR_PNPM_\w+"))),
 ("C", "packages", "apt list --upgradable compté", lambda c, e, o, w: bool(re.search(r"apt list .*--upgradable", c))),
 ("C", "packages", "dpkg -l lignes ii comptées", lambda c, e, o, w: w[:2] == ["dpkg", "-l"] and bool(M(r"^ii\s").search(o))),
 ("C", "packages", "apt-cache policy Installed/Candidate par paquet", lambda c, e, o, w: w[:2] == ["apt-cache", "policy"]),
 ("C", "packages", "apt-cache search / brew outdated|list|uses|deps / pip list compté", lambda c, e, o, w: (w[:2] in (["apt-cache", "search"], ["brew", "outdated"], ["brew", "list"], ["brew", "uses"], ["pnpm", "outdated"], ["npm", "outdated"]) or w[:3] == ["pip", "list", "--outdated"])),
 ("C", "packages", "uv Resolved/Installed N packages ; pip ERROR ; poetry", has(M(r"^(Resolved|Installed|Prepared|Audited) \d+ packages?|^ERROR: |^Installing the current project"))),
 ("C", "packages", "brew doctor Warning: comptés", lambda c, e, o, w: w[:2] == ["brew", "doctor"]),
 ("C", "git", "git fatal:/error: dernière ligne (échec)", fails(has(M(r"^(fatal|error): ")))),
 ("C", "git", "git branch liste, branche courante *", lambda c, e, o, w: w[:2] == ["git", "branch"] and e == 0),
 ("C", "git", "git HEAD is now at / rebase in progress", has(M(r"^HEAD is now at |rebase (interactif )?in progress|rebase en cours"))),
 ("C", "git", "git log --stat : dernier commit, N files changed", lambda c, e, o, w: w[:2] == ["git", "log"] and "--stat" in c),
 ("C", "git", "gh not authenticated / gh auth", has(M(r"gh auth login"))),
 ("C", "containers", "docker build ERROR: failed to solve / parse error", has(M(r"^ERROR: failed to solve|dockerfile parse error on line \d+"))),
 ("C", "containers", "kubectl Unable to connect / error:", fails(has(M(r"^(Unable to connect to the server|error: )")))),
 ("C", "containers", "helm lint N chart(s) linted / [ERROR]", has(M(r"chart\(s\) linted|^\[ERROR\]"))),
 ("C", "infra", "terraform Apply complete / Plan: / No changes / initialized", has(M(r"^Apply complete! Resources:|^Plan: \d+ to add|^No changes\.|successfully initialized"))),
 ("C", "infra", "terraform state list compté", lambda c, e, o, w: w[:3] == ["terraform", "state", "list"]),
 # lot D : réseau, ressources, services, bases
 ("D", "network", "wget Downloaded: / ERROR NNN / saved / unable to resolve", has(M(r"^(Downloaded|Téléchargés) ?: \d+ |ERROR \d{3}: |ERREUR \d{3}|saved \[|sauvegardé \[|unable to resolve host address|impossible de résoudre"))),
 ("D", "network", "curl -i/-v/-I ligne de statut HTTP", lambda c, e, o, w: w[:1] == ["curl"] and bool(re.search(r"\s-\w*[iIv]\b|--include|--head|--verbose", c)) and bool(M(r"^(< )?HTTP/[\d.]+ \d{3}").search(o))),
 ("D", "network", "curl -O barre de progression % Total", lambda c, e, o, w: w[:1] == ["curl"] and bool(M(r"^\s*% Total\s+% Received").search(o))),
 ("D", "network", "ss -l ports à l'écoute / ip route default / nmcli device", lambda c, e, o, w: (w[:1] == ["ss"] and "l" in (w[1] if len(w) > 1 else "")) or (w[:2] == ["ip", "route"] and "default via" in o) or w[:3] in (["nmcli", "device", "status"], ["nmcli", "connection", "show"]) or w[:2] in (["nmcli", "device"],)),
 ("D", "resources", "top -b en-tête Tasks/up/load", has(M(r"^top - .* up .*load average|^Tasks: \d+ total"))),
 ("D", "resources", "memory_pressure / vmstat -s / du -c total", has(M(r"System-wide memory free percentage: \d+%|^\s*\d+ K total memory|^\S+\s+total$"))),
 ("D", "resources", "lsof fichier/port : COMMAND PID", lambda c, e, o, w: w[:1] == ["lsof"] and bool(M(r"^COMMAND\s+PID").search(o))),
 ("D", "resources", "diskutil info : Media Name / Disk Size / SMART", lambda c, e, o, w: w[:2] == ["diskutil", "info"] and "Disk Size" in o),
 ("D", "resources", "ps -u utilisateur inconnu (error: user name does not exist)", has(M(r"user name does not exist|unknown user"))),
 ("D", "services", "systemctl list-timers N timers listed / is-enabled / brew services", lambda c, e, o, w: bool(M(r"^\d+ timers? listed").search(o)) or w[:2] == ["systemctl", "is-enabled"] or w[:3] == ["brew", "services", "list"]),
 ("D", "db", "psql: error connection / FATAL database does not exist / (N rows)", has(M(r"^psql: error: |FATAL:\s+database \S+ does not exist|^\(\d+ rows?\)"))),
 ("D", "db", "sqlite Parse error / Error: near", has(M(r"^(Parse error|Error: in prepare|Error: near)"))),
 ("D", "resources", "smartctl -H overall-health PASSED", has(M(r"overall-health self-assessment test result: \w+"))),
]
