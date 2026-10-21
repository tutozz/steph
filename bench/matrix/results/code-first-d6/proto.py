"""Prototypes jetables de gabarits D6 (RIGUEUR: brouillon) : phrase FR et EN, ou None si doute."""
import re
M = lambda p: re.compile(p, re.M)
def base(p): return p.strip("'\"‘’«» ").rstrip("/").rsplit("/", 1)[-1]
def plural(n, one, many): return f"{n} {one if n == 1 else many}"

# ---- A. tests
UT_RAN = M(r"^Ran (\d+) tests? in [\d.]+s\s*$"); UT_END = M(r"^(OK|FAILED)(?: \((.*)\))?\s*$")
UT_FIRST = M(r"^(?:FAIL|ERROR): (\w+) \(")
def unittest(cmd, code, out, w):
    ran, end = UT_RAN.search(out), UT_END.findall(out)
    if not ran or not end: return None
    kv = dict(p.split("=") for p in end[-1][1].split(", ") if "=" in p)
    n, f, e, s = int(ran[1]), int(kv.get("failures", 0)), int(kv.get("errors", 0)), int(kv.get("skipped", 0))
    first = UT_FIRST.search(out)
    if end[-1][0] == "OK":
        return (f"{plural(n, 'test réussi', 'tests réussis')}" + (f", {s} ignorés" if s else "") + ".",
                f"{n} tests passed" + (f", {s} skipped" if s else "") + ".")
    fr = f"{n} tests : {plural(f, 'échec', 'échecs')}" + (f", {plural(e, 'erreur', 'erreurs')}" if e else "") + "."
    en = f"{n} tests: {f} failed" + (f", {e} errors" if e else "") + "."
    if first: fr += f" Premier : {first[1]}."; en += f" First: {first[1]}."
    return fr, en

TAP = {k: M(rf"^(?:#|ℹ) {k} (\d+)\s*$") for k in ("tests", "pass", "fail")}
TAP_FIRST = M(r"^(?:not ok \d+ - |✖ )(.+?)(?: \([\d.]+m?s\))?\s*$")
def node_test(cmd, code, out, w):
    got = {k: p.findall(out) for k, p in TAP.items()}
    if not all(got.values()):
        return None
    n, p, f = (int(got[k][-1]) for k in ("tests", "pass", "fail"))
    first = TAP_FIRST.search(out)
    if f == 0: return f"{n} tests réussis.", f"{n} tests passed."
    fr, en = f"{f} échecs sur {n} tests.", f"{f} of {n} tests failed."
    if first: fr += f" Premier : {first[1]}."; en += f" First: {first[1]}."
    return fr, en

GO_PKG = M(r"^(ok|FAIL|\?)\s+(\S+)\s")
def go_pkgs(cmd, code, out, w):
    if w[:2] != ["go", "test"] or "-json" in cmd: return None
    got = GO_PKG.findall(out)
    if not got: return None
    groups = {"ok": [], "FAIL": [], "?": []}
    for k, pkg in got: groups[k].append(base(pkg))
    fr, en = [], []
    if groups["FAIL"]: fr.append("en échec : " + ", ".join(groups["FAIL"][:3])); en.append("failing: " + ", ".join(groups["FAIL"][:3]))
    if groups["ok"]: fr.append("réussis : " + ", ".join(groups["ok"][:3])); en.append("passing: " + ", ".join(groups["ok"][:3]))
    if groups["?"]: fr.append("sans tests : " + ", ".join(groups["?"][:3])); en.append("no tests: " + ", ".join(groups["?"][:3]))
    return "Paquets " + " ; ".join(fr) + ".", "Packages " + "; ".join(en) + "."

# ---- A. lint et compilation
RUFF_FOUND = M(r"^Found (\d+) errors?\."); RUFF_FIX = M(r"\[\*\] (\d+) fixable"); RUFF_LINE = M(r"^([^\s:]+\.py):\d+:\d+: [A-Z]+\d+")
def ruff(cmd, code, out, w):
    if w[:1] != ["ruff"]: return None
    if "All checks passed!" in out: return "Aucun problème.", "All checks passed."
    f = RUFF_FOUND.search(out)
    if not f: return None
    files = RUFF_LINE.findall(out)
    top = max(set(files), key=files.count) if files else None
    fix = RUFF_FIX.search(out)
    fr = f"Ruff : {f[1]} erreurs" + (f", surtout dans {top}" if top else "") + "."
    en = f"Ruff: {f[1]} errors" + (f", mostly in {top}" if top else "") + "."
    if fix: fr += f" {fix[1]} corrigeables avec --fix."; en += f" {fix[1]} fixable with --fix."
    return fr, en

PYLINT = M(r"Your code has been rated at (-?[\d.]+)/10")
def pylint(cmd, code, out, w):
    m = PYLINT.search(out)
    return (f"Note pylint : {m[1].replace('.', ',')} sur 10.", f"pylint score: {m[1]} out of 10.") if m else None

CARGO_FIN = M(r"^\s*Finished .* in ([\d.]+)(m?s)\s*$"); CARGO_WARN = M(r"^warning: `([\w-]+)` \([^)]*\) generated (\d+) warnings?")
def cargo(cmd, code, out, w):
    if w[:1] != ["cargo"] or code != 0: return None
    fin, warn = CARGO_FIN.search(out), CARGO_WARN.search(out)
    if not fin: return None
    t = fin[1] + (" ms" if fin[2] == "ms" else " s")
    fr, en = f"Compilation réussie en {t.replace('.', ',')}.", f"Build finished in {t}."
    if warn: fr += f" {warn[2]} avertissements dans {warn[1]}."; en += f" {warn[2]} warnings in {warn[1]}."
    return fr, en

RUST_PANIC = M(r"panicked at ([^:\s]+):(\d+):\d+:?\s*\n?(.*)")
def rust_panic(cmd, code, out, w):
    m = RUST_PANIC.search(out)
    if not m or code == 0: return None
    msg = m[3].strip()[:80]
    return f"Panique dans {base(m[1])} ligne {m[2]} : {msg}.", f"Panic in {base(m[1])} line {m[2]}: {msg}."

# ---- B. scripts et fichiers
SCRIPT_ERR = M(r"^(\S+?): (?:line|ligne) (\d+) ?: (.+)$")
TOOL_ERR = M(r"^(cp|mv|rm|tar|sort|cat|mkdir|ln|chmod|rsync|grep|touch|head|tail|cut|wc|find) ?: (.+)$")
def script(cmd, code, out, w):
    p = w[0] if w else ""
    if not (p in ("bash", "sh", "zsh", "dash") or p.endswith(".sh")): return None
    errs = [(m.start(), "s", m) for m in SCRIPT_ERR.finditer(out)] + [(m.start(), "t", m) for m in TOOL_ERR.finditer(out)]
    if not errs or code in (0, None): return None
    _, kind, m = max(errs, key=lambda x: x[0])
    if kind == "s":
        return (f"{base(m[1])} ligne {m[2]} : {m[3].strip()}.", f"{base(m[1])} line {m[2]}: {m[3].strip()}.")
    return (f"Erreur de {m[1]} : {m[2].strip()}.", f"{m[1]} error: {m[2].strip()}.")

VERBOSE = {
 "rm": (M(r"^(?:removed (?:directory )?'.+'|'.+' supprimé|répertoire '.+' supprimé)$"), "élément supprimé", "éléments supprimés", "item removed", "items removed"),
 "mkdir": (M(r"^mkdir ?: (?:created directory|création du répertoire) '.+'$"), "dossier créé", "dossiers créés", "directory created", "directories created"),
 "split": (M(r"^(?:creating file|création du fichier) '.+'$"), "fichier créé", "fichiers créés", "file created", "files created"),
 "chmod": (M(r"^(?:mode of '.+' (?:changed|retained)|le mode de '.+' a été (?:modifié|conservé)).*$"), "élément traité", "éléments traités", "item processed", "items processed"),
 "chown": (M(r"^(?:changed ownership of|ownership of|le propriétaire de|la propriété de) '.+'.*$"), "élément traité", "éléments traités", "item processed", "items processed"),
}
def verbose(cmd, code, out, w):
    p = w[0] if w else ""
    if p not in VERBOSE or "|" in cmd or code != 0: return None
    pat, fo, fm, eo, em = VERBOSE[p]
    lines = [l for l in out.splitlines() if l.strip()]
    if not lines or any(not pat.match(l) for l in lines): return None
    n = len(lines)
    return f"{n} {fo if n == 1 else fm}.", f"{n} {eo if n == 1 else em}."

SHRED = M(r"^shred: (.+?) ?: (?:removed|supprimé)$")
def shred(cmd, code, out, w):
    if w[:1] != ["shred"] or code != 0: return None
    n = len(SHRED.findall(out))
    if not n: return None
    return f"{n} fichiers écrasés et supprimés.", f"{n} files shredded and removed."

CHECK = M(r"^(.+?): (OK|FAILED|RÉUSSI|ÉCHEC|FAILED open or read|ÉCHEC d'ouverture ou de lecture)$")
def checksum(cmd, code, out, w):
    if not re.search(r"(md5|sha\d+)sum\b.*\s-c\b", cmd) or "|" in cmd: return None
    got = CHECK.findall(out)
    if not got: return None
    ok = sum(s in ("OK", "RÉUSSI") for _, s in got); bad = [f for f, s in got if s in ("FAILED", "ÉCHEC")]
    unread = [f for f, s in got if "open" in s or "ouverture" in s]
    fr = f"{ok} fichiers conformes, {len(bad)} différents" + (f", {len(unread)} illisibles" if unread else "") + "."
    en = f"{ok} files OK, {len(bad)} mismatched" + (f", {len(unread)} unreadable" if unread else "") + "."
    if bad: fr += f" Premier : {base(bad[0])}."; en += f" First: {base(bad[0])}."
    return fr, en

# ---- C. paquets, infra, git
NPM_ADDED = M(r"^added (\d+) packages?"); NPM_VULN = M(r"^(?:found )?(\d+) vulnerabilit(?:y|ies)(?: \((.+)\))?"); NPM_CODE = M(r"^npm (?:ERR!|error) code (\S+)")
def npm(cmd, code, out, w):
    if w[:1] not in (["npm"], ["pnpm"]): return None
    a, v, c = NPM_ADDED.search(out), NPM_VULN.search(out), NPM_CODE.search(out)
    if c or not (a or v): return None
    fr, en = [], []
    if a: fr.append(f"{a[1]} paquets ajoutés"); en.append(f"{a[1]} packages added")
    if v:
        detail = (v[2] or "").replace("low", "faibles").replace("moderate", "moyennes").replace("high", "élevées").replace("critical", "critiques")
        fr.append(f"{v[1]} vulnérabilités" + (f" ({detail})" if detail else "")); en.append(f"{v[1]} vulnerabilities" + (f" ({v[2]})" if v[2] else ""))
    return ", ".join(fr) + ".", ", ".join(en) + "."

TF = [(M(r"^Apply complete! Resources: (\d+) added, (\d+) changed, (\d+) destroyed"), "Application terminée : {0} ajoutées, {1} modifiées, {2} détruites.", "Apply complete: {0} added, {1} changed, {2} destroyed."),
      (M(r"^Plan: (\d+) to add, (\d+) to change, (\d+) to destroy"), "Plan : {0} à ajouter, {1} à modifier, {2} à détruire.", "Plan: {0} to add, {1} to change, {2} to destroy."),
      (M(r"^No changes\."), "Aucun changement.", "No changes."),
      (M(r"Terraform has been successfully initialized"), "Terraform initialisé.", "Terraform initialized.")]
def terraform(cmd, code, out, w):
    if w[:1] != ["terraform"]: return None
    for p, fr, en in TF:
        if m := p.search(out): return fr.format(*m.groups()), en.format(*m.groups())
    return None

# ---- D. réseau
WGET_DL = M(r"^(?:Downloaded|Téléchargés)[ \xa0]?:[ \xa0](\d+)[ \xa0]fichiers?, ([\d.,]+\w?)|^(?:Downloaded|Téléchargés)[ \xa0]?:[ \xa0](\d+)[ \xa0]files?, ([\d.,]+\w?)")
WGET_ERR = M(r"ERR(?:OR|EUR)[ \xa0](\d{3})[ \xa0]?:[ \xa0]?(.+?)\.?$")
def wget(cmd, code, out, w):
    if w[:1] != ["wget"]: return None
    d, errs = WGET_DL.search(out), WGET_ERR.findall(out)
    if not d: return None
    n, size = (d[1], d[2]) if d[1] else (d[3], d[4])
    fr, en = f"{n} fichiers téléchargés, {size} au total.", f"{n} files downloaded, {size} total."
    if errs: fr += f" {len(errs)} en erreur, dont {errs[0][0]}."; en += f" {len(errs)} failed, including {errs[0][0]}."
    return fr, en

HTTP = M(r"^(?:< )?HTTP/[\d.]+ (\d{3})(?: (.*))?$")
def curl_status(cmd, code, out, w):
    if w[:1] != ["curl"] or not re.search(r"\s-\w*[iIv]\b|--include|--head|--verbose", cmd): return None
    got = HTTP.findall(out)
    if not got: return None
    st, reason = got[-1]
    return f"Réponse HTTP {st}{(' ' + reason.strip()) if reason.strip() else ''}.", f"HTTP {st}{(' ' + reason.strip()) if reason.strip() else ''}."

BUILDERS = {"A": [unittest, node_test, go_pkgs, ruff, pylint, cargo, rust_panic],
            "B": [script, verbose, shred, checksum],
            "C": [npm, terraform],
            "D": [wget, curl_status]}
