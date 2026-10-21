"""D6 lot C : paquets, git, conteneurs, infra dits en code, ou gabarit pour le mode hybride.

Chaque sortie est synthétique, écrite d'après le format documenté de l'outil (provenance en
commentaire) ; aucune n'est copiée du banc. `resolve()` ne parle que quand la phrase est
complète ; sinon `skeleton()` donne le squelette exact et le modèle garde l'explication.
"""

import pytest

from steph.digest import resolve, skeleton


def both(cmd, code, out):
    return resolve(cmd, code, out, "fr"), resolve(cmd, code, out, "en")


# ---------------------------------------------------------------- npm, pnpm
# format : `npm install` (npm 10, reify-output.js), exemple dev v3-js-node-0003 et 0010

NPM_INSTALL = """npm warn deprecated inflight@1.0.6: This module is not supported, and leaks memory.

added 132 packages, and audited 133 packages in 5s

14 packages are looking for funding
  run `npm fund` for details

found 0 vulnerabilities
"""

NPM_INSTALL_VULNS = """added 1 package, removed 2 packages, changed 3 packages, and audited 400 packages in 2s

5 vulnerabilities (1 low, 2 moderate, 1 high, 1 critical)

To address all issues, run:
  npm audit fix

Run `npm audit` for details.
"""

NPM_UP_TO_DATE_ONE_SEVERITY = """up to date, audited 50 packages in 1s

8 packages are looking for funding
  run `npm fund` for details

1 high severity vulnerability

To address all issues, run:
  npm audit fix --force

Run `npm audit` for details.
"""


def test_npm_install_counts_vulnerabilities_and_deprecations():
    assert both("npm install", 0, NPM_INSTALL) == (
        "132 paquets ajoutés, aucune vulnérabilité. Déprécié : inflight.",
        "132 packages added, no vulnerabilities. Deprecated: inflight.")


def test_npm_install_counts_every_change_and_severity():
    assert both("npm i", 0, NPM_INSTALL_VULNS) == (
        "1 paquet ajouté, 2 paquets retirés, 3 paquets modifiés, 5 vulnérabilités : "
        "1 faible, 2 modérées, 1 élevée, 1 critique.",
        "1 package added, 2 packages removed, 3 packages changed, 5 vulnerabilities: "
        "1 low, 2 moderate, 1 high, 1 critical.")


def test_npm_up_to_date_with_one_severity():
    assert both("npm install", 0, NPM_UP_TO_DATE_ONE_SEVERITY) == (
        "Déjà à jour, 1 vulnérabilité élevée.",
        "Already up to date, 1 high vulnerability.")


def test_npm_unknown_warning_leaves_a_skeleton_only():
    out = "npm warn ERESOLVE overriding peer dependency\nnpm warn While resolving: app@1.0.0\n" + NPM_INSTALL
    assert resolve("npm install", 0, out) is None
    assert skeleton("npm install", 0, out) == "132 paquets ajoutés, aucune vulnérabilité. Déprécié : inflight."


def test_npm_install_script_output_is_not_said_in_code():
    out = "\n> app@1.0.0 postinstall\n> node scripts/setup.js\n\nsetup done, 3 files written\n" + NPM_INSTALL
    assert resolve("npm install", 0, out) is None


# format : `npm audit` (rapport par paquet, dépendants indentés), exemple dev v3-js-node-0011
NPM_AUDIT = """# npm audit report

lodash  <=4.17.20
Severity: critical
Prototype Pollution in lodash - https://github.com/advisories/GHSA-aaaa-bbbb-cccc
fix available via `npm audit fix`
node_modules/lodash

semver  <5.7.2
Severity: moderate
semver vulnerable to Regular Expression Denial of Service - https://github.com/advisories/GHSA-dddd-eeee-ffff
fix available via `npm audit fix`
node_modules/semver
  make-dir  2.0.0 - 3.1.0
  Depends on vulnerable versions of semver
  node_modules/make-dir

3 vulnerabilities (2 moderate, 1 critical)

To address all issues, run:
  npm audit fix
"""


def test_npm_audit_names_every_affected_package():
    assert both("npm audit", 1, NPM_AUDIT) == (
        "Échec. 3 vulnérabilités : 2 modérées, 1 critique. Paquets concernés : lodash, semver et make-dir.",
        "Failed. 3 vulnerabilities: 2 moderate, 1 critical. Packages affected: lodash, semver and make-dir.")


def test_npm_audit_fix_reports_the_changes():
    out = "\nchanged 3 packages, and audited 200 packages in 2s\n\n12 packages are looking for funding\n" \
          "  run `npm fund` for details\n\nfound 0 vulnerabilities\n"
    assert resolve("npm audit fix", 0, out) == "3 paquets modifiés, aucune vulnérabilité."


def test_npm_audit_counts_blocks_without_a_severity_line():
    # piège trouvé à la relecture dev (v3-js-node-0011) : un bloc sans ligne « Severity: » était omis
    out = NPM_AUDIT.replace("\n3 vulnerabilities (2 moderate, 1 critical)", (
        "cookie  <0.7.0\ncookie accepts cookie name, path, and domain with out of bounds characters - "
        "https://github.com/advisories/GHSA-gggg-hhhh-iiii\nfix available via `npm audit fix`\nnode_modules/cookie\n"
        "\n4 vulnerabilities (1 low, 2 moderate, 1 critical)"))
    assert resolve("npm audit", 1, out) == (
        "Échec. 4 vulnérabilités : 1 faible, 2 modérées, 1 critique. Paquets concernés : lodash, semver, make-dir "
        "et cookie.")


def test_npm_audit_without_a_matching_package_count_gives_counts_only():
    out = NPM_AUDIT.replace("3 vulnerabilities (2 moderate, 1 critical)", "4 vulnerabilities (3 moderate, 1 critical)")
    assert resolve("npm audit", 1, out) == "Échec. 4 vulnérabilités : 3 modérées, 1 critique."


# format : npm EBADENGINE (npm 10, `npm error notsup`), exemple dev v3-js-node-0013
NPM_ENGINE = """npm error code EBADENGINE
npm error engine Unsupported engine
npm error engine Not compatible with your version of node/npm: fastlib@3.1.0
npm error notsup Not compatible with your version of node/npm: fastlib@3.1.0
npm error notsup Required: {"node":">=20.0.0"}
npm error notsup Actual:   {"npm":"9.8.1","node":"v18.19.0"}
npm error A complete log of this run can be found in: /home/user/.npm/_logs/2026-01-01T00_00_00_000Z-debug-0.log"""


def test_npm_engine_requirement():
    assert both("npm install --engine-strict", 1, NPM_ENGINE) == (
        "Échec. fastlib exige Node 20.0.0 ou plus, version installée 18.19.0.",
        "Failed. fastlib requires Node 20.0.0 or later, installed version 18.19.0.")


def test_npm_engine_with_a_complex_range_stays_with_the_model():
    out = NPM_ENGINE.replace('">=20.0.0"', '"^18.20 || >=20.10"')
    assert resolve("npm install --engine-strict", 1, out) is None


# format : registre npm E404 (npm 10) et ERR_PNPM_FETCH_404 (pnpm), exemple dev v3-js-node-0026
NPM_404 = """npm error code E404
npm error 404 Not Found - GET https://registry.npmjs.org/left-padd - Not found
npm error 404
npm error 404  'left-padd@*' is not in this registry.
npm error 404
npm error 404 Note that you can also install from a
npm error 404 tarball, folder, http url, or git url.
npm error A complete log of this run can be found in: /home/user/.npm/_logs/x-debug-0.log"""

PNPM_404 = """Progress: resolved 1, reused 0, downloaded 0, added 0
[ERR_PNPM_FETCH_404] GET https://registry.npmjs.org/@scope%2Fwidget: Not Found - 404

This error happened while installing a direct dependency of /home/user/app

@scope/widget is not in the npm registry, or you have no permission to fetch it.

No authorization header was set for the request."""


@pytest.mark.parametrize("cmd, out, pkg", [("npm install left-padd", NPM_404, "left-padd"),
                                           ("pnpm add @scope/widget", PNPM_404, "@scope/widget")])
def test_registry_404(cmd, out, pkg):
    assert both(cmd, 1, out) == (f"Échec. {pkg} introuvable sur le registre npm, erreur 404.",
                                 f"Failed. {pkg} not found in the npm registry, error 404.")


# format : `npm ci` EUSAGE (lock désynchronisé), exemple dev v3-js-node-0019
NPM_CI = """npm error code EUSAGE
npm error
npm error `npm ci` can only install packages when your package.json and package-lock.json or npm-shrinkwrap.json are in sync. Please update your lock file with `npm install` before continuing.
npm error
npm error Missing: chalk@5.3.0 from lock file
npm error
npm error Clean install a project
npm error
npm error Usage:
npm error npm ci
npm error A complete log of this run can be found in: /home/user/.npm/_logs/y-debug-0.log"""


def test_npm_ci_out_of_sync():
    assert both("npm ci", 1, NPM_CI) == (
        "Échec. npm ci refusé : package.json et package-lock.json ne sont pas synchronisés, "
        "chalk 5.3.0 manque dans le lock.",
        "Failed. npm ci refused: package.json and package-lock.json are out of sync, "
        "chalk 5.3.0 is missing from the lock file.")


# format : `pnpm outdated` (tableau encadré) et `npm outdated` (colonnes), exemple dev v3-js-node-0033
PNPM_OUTDATED = """┌─────────┬─────────┬─────────┐
│ Package │ Current │ Latest  │
├─────────┼─────────┼─────────┤
│ lodash  │ 4.17.20 │ 4.17.21 │
├─────────┼─────────┼─────────┤
│ chalk   │ 4.1.2   │ 5.3.0   │
└─────────┴─────────┴─────────┘"""

NPM_OUTDATED = """Package  Current  Wanted  Latest  Location             Depended by
chalk      4.1.2   4.1.2   5.3.0  node_modules/chalk   app
lodash   4.17.20 4.17.21 4.17.21  node_modules/lodash  app"""


@pytest.mark.parametrize("cmd, out", [("pnpm outdated", PNPM_OUTDATED), ("npm outdated", NPM_OUTDATED)])
def test_js_outdated(cmd, out):
    said = both(cmd, 1, out)
    names = ("lodash vers 4.17.21", "chalk vers 5.3.0") if cmd.startswith("pnpm") else ("chalk vers 5.3.0",
                                                                                         "lodash vers 4.17.21")
    assert said[0] == f"2 paquets en retard : {names[0]} et {names[1]}."
    assert said[1] == "2 outdated packages: " + " and ".join(n.replace(" vers ", " to ") for n in names) + "."


# format : `pnpm install` (pnpm 9 et 10), exemple dev v3-js-node-0025
PNPM_INSTALL = """ WARN  deprecated request@2.88.2: request has been deprecated
Packages: +42
++++++++++++++++++++++++++++++++++++++++++
Progress: resolved 42, reused 40, downloaded 2, added 42, done

dependencies:
+ lodash 4.17.21
+ request 2.88.2 deprecated

Done in 1.2s"""


def test_pnpm_install():
    assert both("pnpm install", 0, PNPM_INSTALL) == ("42 paquets ajoutés. Déprécié : request.",
                                                     "42 packages added. Deprecated: request.")


def test_pnpm_install_added_and_removed():
    out = PNPM_INSTALL.replace("Packages: +42", "Packages: +3 -1").replace(" WARN  deprecated request@2.88.2: "
                                                                           "request has been deprecated\n", "")
    assert both("pnpm i", 0, out) == ("3 paquets ajoutés, 1 paquet retiré.", "3 packages added, 1 package removed.")


def test_pnpm_exec_is_not_an_install():
    assert resolve("pnpm exec eslint .", 0, PNPM_INSTALL) is None


# ---------------------------------------------------------------- pip, uv, poetry
# format : `pip list --outdated` (colonnes Package Version Latest Type), exemple dev v3-python-0003

PIP_OUTDATED = """Package    Version Latest Type
---------- ------- ------ -----
requests   2.31.0  2.32.3 wheel
urllib3    2.0.7   2.2.2  wheel
"""


def test_pip_list_outdated():
    assert both("pip list --outdated", 0, PIP_OUTDATED) == (
        "2 paquets en retard : requests vers 2.32.3 et urllib3 vers 2.2.2.",
        "2 outdated packages: requests to 2.32.3 and urllib3 to 2.2.2.")


def test_pip_list_outdated_with_many_packages():
    rows = "\n".join(f"pkg{i}       1.0.{i}   2.0.{i}  wheel" for i in range(6))
    out = "Package    Version Latest Type\n---------- ------- ------ -----\n" + rows
    assert resolve("pip list -o", 0, out) == "6 paquets en retard, dont pkg0 vers 2.0.0, pkg1 vers 2.0.1 et pkg2 vers 2.0.2."


# format : pip install -r (lignes « Collecting X (from -r fichier (line N)) »), exemple dev v3-python-0002
PIP_REQUIREMENTS = """Collecting django==5.0.6 (from -r requirements.txt (line 1))
  Downloading django-5.0.6-py3-none-any.whl.metadata (4.1 kB)
Collecting celery==5.4.0 (from -r requirements.txt (line 2))
  Downloading celery-5.4.0-py3-none-any.whl.metadata (21 kB)
Collecting asgiref<4,>=3.7.0 (from django==5.0.6->-r requirements.txt (line 1))
  Downloading asgiref-3.8.1-py3-none-any.whl.metadata (9.3 kB)
Collecting sqlparse>=0.3.1 (from django==5.0.6->-r requirements.txt (line 1))
  Downloading sqlparse-0.5.0-py3-none-any.whl.metadata (3.9 kB)
Collecting kombu<6.0,>=5.3.4 (from celery==5.4.0->-r requirements.txt (line 2))
  Downloading kombu-5.3.7-py3-none-any.whl.metadata (3.1 kB)
Installing collected packages: sqlparse, kombu, asgiref, django, celery
Successfully installed asgiref-3.8.1 celery-5.4.0 django-5.0.6 kombu-5.3.7 sqlparse-0.5.0
"""


def test_pip_requirements_names_the_requested_packages():
    assert both("pip install -r requirements.txt", 0, PIP_REQUIREMENTS) == (
        "5 paquets installés depuis requirements.txt, dont django et celery.",
        "5 packages installed from requirements.txt, including django and celery.")


# format : ResolutionImpossible de pip (« Cannot install a==x and b==y »), exemple dev v3-python-0014
PIP_CONFLICT = """Collecting flask==3.0.0
Collecting werkzeug==2.0.0
ERROR: Cannot install flask==3.0.0 and werkzeug==2.0.0 because these package versions have conflicting dependencies.

The conflict is caused by:
    The user requested werkzeug==2.0.0
    flask 3.0.0 depends on Werkzeug>=3.0.0

ERROR: ResolutionImpossible: for help visit https://pip.pypa.io/en/latest/topics/dependency-resolution/"""


def test_pip_conflict_names_both_sides():
    assert both("pip install flask==3.0.0 werkzeug==2.0.0", 1, PIP_CONFLICT) == (
        "Échec. Conflit de dépendances entre flask 3.0.0 et werkzeug 2.0.0.",
        "Failed. Dependency conflict between flask 3.0.0 and werkzeug 2.0.0.")


def test_pip_conflict_with_a_requirement_file_keeps_the_generic_sentence():
    out = PIP_CONFLICT.replace("Cannot install flask==3.0.0 and", "Cannot install -r requirements.txt (line 2) and")
    assert resolve("pip install -r requirements.txt", 1, out) == "Échec. Conflit de dépendances, résolution impossible."


# format : échec de construction d'une roue (pip 24 et plus), exemples dev v3-python-0015, 0016, 0034
PIP_BUILD = """Collecting lxml==4.9.0
  Downloading lxml-4.9.0.tar.gz (3.4 MB)
  Installing build dependencies: started
  Installing build dependencies: finished with status 'done'
  Getting requirements to build wheel: started
  Getting requirements to build wheel: finished with status 'error'
  error: subprocess-exited-with-error

  × Getting requirements to build wheel did not run successfully.
  │ exit code: 1
  ╰─> [3 lines of output]
      Error: Please make sure the libxml2 and libxslt development packages are installed.
      [end of output]

  note: This error originates from a subprocess, and is likely not a problem with pip.
ERROR: Failed to build 'lxml' when getting requirements to build wheel
"""


def test_pip_build_failure_is_a_skeleton_the_cause_stays_with_the_model():
    assert resolve("pip install lxml==4.9.0", 1, PIP_BUILD) is None
    assert skeleton("pip install lxml==4.9.0", 1, PIP_BUILD) == "Échec. Construction de lxml impossible."
    assert skeleton("pip install lxml==4.9.0", 1, PIP_BUILD, "en") == "Failed. lxml failed to build."


def test_pip_editable_build_failure_names_the_project_folder():
    out = PIP_BUILD.replace("'lxml' when getting requirements to build wheel",
                            "'file:///home/user/dev/shopapp' when getting requirements to build editable")
    assert skeleton("pip install -e .", 1, out) == "Échec. Construction de shopapp impossible."


# format : uv (Resolved, Prepared, Installed, lignes « + nom==version »), exemple dev v3-python-0023
UV_ADD = """Resolved 12 packages in 300ms
Prepared 3 packages in 150ms
Installed 3 packages in 10ms
 + h11==0.14.0
 + httpcore==1.0.5
 + httpx==0.27.0
"""


def test_uv_add_names_the_requested_package():
    assert both("uv add httpx", 0, UV_ADD) == ("3 paquets installés, dont httpx 0.27.0.",
                                             "3 packages installed, including httpx 0.27.0.")


def test_uv_download_lines_are_indented():
    out = ("Resolved 6 packages in 515ms\nDownloading numpy (5.2MiB)\n Downloaded numpy\nPrepared 2 packages in 374ms\n"
           "Installed 2 packages in 24ms\n + numpy==2.1.0\n + scipy==1.14.1\n")
    assert resolve("uv add scipy", 0, out) == "2 paquets installés, dont scipy 1.14.1."


def test_uv_upgrade_counts_uninstalled_packages():
    out = ("Resolved 12 packages in 300ms\nPrepared 1 package in 150ms\nUninstalled 1 package in 2ms\n"
           "Installed 1 package in 10ms\n - httpx==0.26.0\n + httpx==0.27.0\n")
    assert both("uv pip install -U httpx", 0, out) == ("httpx 0.27.0 installé ; 1 paquet désinstallé.",
                                                      "httpx 0.27.0 installed; 1 package uninstalled.")


def test_uv_nothing_to_install():
    out = "Using CPython 3.12.3\nResolved 12 packages in 3ms\nAudited 12 packages in 1ms\nBytecode compiled 40 files in 30ms"
    assert resolve("uv sync", 0, out) == "Déjà à jour, 12 paquets vérifiés."


def test_uv_warning_stays_with_the_model():
    out = "warning: `VIRTUAL_ENV=/x` does not match the project environment path `.venv`\n" + UV_ADD
    assert resolve("uv add httpx", 0, out) is None


# format : uv pip compile (Resolved puis liste épinglée), exemple dev v3-python-0025
UV_COMPILE = """Resolved 8 packages in 120ms
# This file was autogenerated by uv via the following command:
#    uv pip compile requirements.in
anyio==4.4.0
    # via httpx
certifi==2024.7.4
    # via httpx
httpx==0.27.0
    # via -r requirements.in
"""


def test_uv_pip_compile():
    assert both("uv pip compile requirements.in", 0, UV_COMPILE) == (
        "8 paquets résolus depuis requirements.in.", "8 packages resolved from requirements.in.")


# format : poetry install (« Package operations », « Installing the current project »), exemple dev v3-python-0009
POETRY = """Installing dependencies from lock file

Package operations: 5 installs, 1 update, 0 removals

  - Installing idna (3.7)
  - Installing sniffio (1.3.1)
  - Installing anyio (4.4.0)
  - Installing h11 (0.14.0)
  - Installing httpx (0.27.0)
  - Updating certifi (2024.2.2 -> 2024.7.4)

Installing the current project: shop (1.2.0)
"""


def test_poetry_install():
    assert both("poetry install", 0, POETRY) == (
        "5 paquets installés, 1 mis à jour ; projet shop 1.2.0 installé.",
        "5 packages installed, 1 updated; project shop 1.2.0 installed.")


def test_poetry_nothing_to_install():
    out = ("Installing dependencies from lock file\n\nNo dependencies to install or update\n\n"
           "Installing the current project: shop (1.2.0)\n")
    assert resolve("poetry install", 0, out) == "Dépendances déjà à jour ; projet shop 1.2.0 installé."


# ---------------------------------------------------------------- apt, dpkg, brew
# format : `apt list --upgradable` (apt 2.x, traduction gettext à espace insécable), exemple dev v3-packages-system-0065

APT_UPGRADABLE = """Listing... Done
bash/stable 5.2.15-2+b8 amd64 [upgradable from: 5.2.15-2+b7]
curl/stable-security 7.88.1-10+deb12u8 amd64 [upgradable from: 7.88.1-10+deb12u7]
libcurl4/stable-security 7.88.1-10+deb12u8 amd64 [upgradable from: 7.88.1-10+deb12u7]
tzdata/stable 2024b-0+deb12u1 all [upgradable from: 2024a-0+deb12u1]
vim/stable 2:9.0.1378-2+deb12u1 amd64 [upgradable from: 2:9.0.1378-2]
"""

APT_UPGRADABLE_FR = ("\nWARNING: apt does not have a stable CLI interface. Use with caution in scripts.\n\n"
                     "En train de lister…\n"
                     "bash/stable 5.2.15-2+b8 amd64 [pouvant être mis à jour depuis\xa0: 5.2.15-2+b7]\n"
                     "tzdata/stable 2024b-0+deb12u1 all [pouvant être mis à jour depuis\xa0: 2024a-0+deb12u1]\n")


def test_apt_list_upgradable():
    assert both("apt list --upgradable", 0, APT_UPGRADABLE) == (
        "5 paquets peuvent être mis à jour, dont bash, curl et libcurl4.",
        "5 packages can be upgraded, including bash, curl and libcurl4.")


def test_apt_list_upgradable_french_output():
    assert both("apt list --upgradable", 0, APT_UPGRADABLE_FR) == (
        "2 paquets peuvent être mis à jour : bash et tzdata.",
        "2 packages can be upgraded: bash and tzdata.")


def test_apt_list_upgradable_piped_is_not_counted():
    assert resolve("apt list --upgradable | head -3", 0, APT_UPGRADABLE) is None


# format : apt-cache policy (Installé / Candidat, table des versions de la plus récente à la plus
# ancienne), exemple dev v3-packages-system-0066
POLICY_LIBC = ("libc6:\n  Installé\xa0: 2.36-9+deb12u7\n  Candidat\xa0: 2.36-9+deb12u8\n Table de version\xa0:\n"
               "     2.36-9+deb12u8 500\n        500 http://deb.debian.org/debian bookworm/main amd64 Packages\n"
               " *** 2.36-9+deb12u7 100\n        100 /var/lib/dpkg/status\n")
POLICY_ZSH = ("zsh:\n  Installé\xa0: (aucun)\n  Candidat\xa0: 5.9-4+b5\n Table de version\xa0:\n     5.9-4+b5 500\n"
              "        500 http://deb.debian.org/debian bookworm/main amd64 Packages\n")
POLICY_GIT = ("git:\n  Installé\xa0: 1:2.39.5-0+deb12u1\n  Candidat\xa0: 1:2.39.5-0+deb12u1\n Table de version\xa0:\n"
              " *** 1:2.39.5-0+deb12u1 500\n        500 http://deb.debian.org/debian bookworm/main amd64 Packages\n"
              "        100 /var/lib/dpkg/status\n")


def test_apt_cache_policy_several_packages():
    assert both("apt-cache policy libc6 zsh git", 0, POLICY_LIBC + POLICY_ZSH + POLICY_GIT) == (
        "libc6 peut être mis à jour ; git est à jour ; zsh n'est pas installé.",
        "libc6 can be upgraded; git is up to date; zsh is not installed.")


def test_apt_cache_policy_agrees_with_several_names():
    assert resolve("apt-cache policy libc6 git bash", 0, POLICY_LIBC + POLICY_GIT + POLICY_GIT.replace("git:", "bash:")) == (
        "libc6 peut être mis à jour ; git et bash sont à jour.")


def test_apt_cache_policy_one_package():
    assert both("apt-cache policy libc6", 0, POLICY_LIBC) == (
        "libc6 : installé 2.36-9+deb12u7, candidat 2.36-9+deb12u8, mise à jour disponible.",
        "libc6: installed 2.36-9+deb12u7, candidate 2.36-9+deb12u8, upgrade available.")


def test_apt_cache_policy_pinned_older_candidate_is_not_an_upgrade():
    pinned = ("libc6:\n  Installed: 2.36-9+deb12u8\n  Candidate: 2.36-9+deb12u7\n  Version table:\n"
              " *** 2.36-9+deb12u8 100\n        100 /var/lib/dpkg/status\n"
              "     2.36-9+deb12u7 990\n        990 http://deb.debian.org/debian bookworm/main amd64 Packages\n")
    assert resolve("apt-cache policy libc6 git", 0, pinned + POLICY_GIT) is None


# format : apt-cache search (« nom - description »), exemple dev v3-packages-system-0087
APT_SEARCH = """python3-requests - elegant and simple HTTP library for Python3, built for human beings
python3-requests-oauthlib - module providing OAuthlib auth support for requests (Python 3)
python3-requests-toolbelt - Utility belt for advanced users of python3-requests
python3-requests-unixsocket - Use requests to talk HTTP via a UNIX domain socket - Python 3.x
python3-requests-mock - mock out responses from the requests package - Python 3.x
"""


def test_apt_cache_search():
    assert both("apt-cache search python3-requests", 0, APT_SEARCH) == (
        "5 paquets trouvés, dont python3-requests, python3-requests-oauthlib et python3-requests-toolbelt.",
        "5 packages found, including python3-requests, python3-requests-oauthlib and python3-requests-toolbelt.")


# format : dpkg -l (dpkg-query, colonnes souhait/état), exemples dev v3-packages-system-0008 et 0067
DPKG = """Desired=Unknown/Install/Remove/Purge/Hold
| Status=Not/Inst/Conf-files/Unpacked/halF-conf/Half-inst/trig-aWait/Trig-pend
|/ Err?=(none)/Reinst-required (Status,Err: uppercase=bad)
||/ Name              Version           Architecture Description
+++-=================-=================-============-=================================
ii  openssh-client    1:9.2p1-2+deb12u3 amd64        secure shell (SSH) client
ii  openssh-server    1:9.2p1-2+deb12u3 amd64        secure shell (SSH) server
un  openssh-sftp      <none>            <none>       (no description available)
rc  openssh-blacklist 0.4.1             all          list of default blacklisted OpenSSH keys
"""


def test_dpkg_list_counts_installed_rows():
    assert both("dpkg -l 'openssh*'", 0, DPKG) == (
        "2 paquets installés sur 4 listés : openssh-client et openssh-server.",
        "2 packages installed out of 4 listed: openssh-client and openssh-server.")


def test_dpkg_list_drops_the_architecture_suffix():
    out = DPKG.replace("openssh-client   ", "libssl3:amd64    ")
    assert resolve("dpkg -l", 0, out).endswith(": libssl3 et openssh-server.")


# format : brew outdated (verbeux « nom (installé) < dernière », casks « != »), exemple dev v3-packages-system-0022
BREW_OUTDATED = """git (2.44.0) < 2.45.1
node (21.7.1) < 22.2.0
wget (1.24.5) < 1.25.0
python@3.12 (3.12.2_1) < 3.12.3
firefox (125.0) != 126.0
"""


def test_brew_outdated():
    assert both("brew outdated", 0, BREW_OUTDATED) == (
        "5 paquets en retard, dont git vers 2.45.1, node vers 22.2.0 et wget vers 1.25.0.",
        "5 outdated packages, including git to 2.45.1, node to 22.2.0 and wget to 1.25.0.")


def test_brew_outdated_names_only():
    assert resolve("brew outdated", 0, "git\nnode\nwget\npython@3.12\nffmpeg\nopenssl@3\n") == (
        "6 paquets en retard, dont git, node et wget.")


# format : brew uses (noms en colonnes), exemple dev v3-packages-system-0026
BREW_USES = """aria2        gnupg        libssh2      php          sqlmap
bind         httpie       mariadb      postgresql@16 tmux
curl         krb5         mysql        python@3.12  unbound
ffmpeg       libevent     node         redis        wget
freetds      libpq        openvpn      ruby         yt-dlp
"""


def test_brew_uses_counts_formulae():
    assert both("brew uses --installed openssl@3", 0, BREW_USES) == (
        "25 formules installées utilisent openssl@3, dont aria2, gnupg et libssh2.",
        "25 installed formulae use openssl@3, including aria2, gnupg and libssh2.")


# format : brew doctor (blocs « Warning: »), exemple dev v3-packages-system-0027
BREW_DOCTOR = """Please note that these warnings are just used to help the Homebrew maintainers
with debugging if you file an issue. If everything you use Homebrew for is
working fine: please don't worry or file an issue; just ignore this. Thanks!

Warning: Some installed formulae are deprecated or disabled.
You should find replacements for the following formulae:
  python@3.8

Warning: Your Xcode (15.0) is outdated.
Please update to Xcode 16.0 (or delete it).
"""


def test_brew_doctor_is_a_skeleton():
    assert resolve("brew doctor", 1, BREW_DOCTOR) is None
    assert skeleton("brew doctor", 1, BREW_DOCTOR) == "brew doctor : 2 avertissements."
    assert skeleton("brew doctor", 1, BREW_DOCTOR, "en") == "brew doctor: 2 warnings."


# ---------------------------------------------------------------- git, gh
# format : git branch (« * » devant la branche courante, remotes/ avec -a, [amont: état] avec -vv),
# exemples dev v3-vcs-git-0029 et 0031

GIT_BRANCH_A = """  develop
* main
  remotes/origin/HEAD -> origin/main
  remotes/origin/develop
  remotes/origin/main
  remotes/origin/release/2.0
"""

GIT_BRANCH_VV = """  feature/a  1111111 [origin/feature/a: gone] Start a
* main       2222222 [origin/main] Release 1.0
  feature/b  3333333 [origin/feature/b: ahead 2] Tweak b
  hotfix     4444444 [origin/hotfix: behind 3] Fix c
  wip        5555555 Draft
"""


def test_git_branch_all():
    assert both("git branch -a", 0, GIT_BRANCH_A) == ("2 branches locales, courante main ; 3 distantes.",
                                                     "2 local branches, current main; 3 remote.")


def test_git_branch_vv_upstream_states():
    assert both("git branch -vv", 0, GIT_BRANCH_VV) == (
        "5 branches locales, courante main. Amont disparu : feature/a. En avance : feature/b. En retard : hotfix.",
        "5 local branches, current main. Upstream gone: feature/a. Ahead: feature/b. Behind: hotfix.")


def test_git_branch_detached_french():
    out = "* (HEAD détachée sur 1a2b3c4)\n  main\n  dev\n  feature/x\n"
    assert resolve("git branch", 0, out) == "3 branches locales, HEAD détachée sur 1a2b3c4."


def test_git_branch_delete_is_not_a_listing():
    assert resolve("git branch -d old", 0, GIT_BRANCH_A) is None


# format : message de git push sans amont (builtin/push.c), exemple dev v3-vcs-git-0015
GIT_NO_UPSTREAM = """fatal: The current branch topic/login has no upstream branch.
To push the current branch and set the remote as upstream, use

    git push --set-upstream origin topic/login

To have this happen automatically for branches without a tracking
upstream, see 'push.autoSetupRemote' in 'git help config'.
"""


def test_git_push_without_upstream():
    assert both("git push", 128, GIT_NO_UPSTREAM) == (
        "Échec. La branche topic/login n'a pas de branche amont ; lancer git push --set-upstream origin topic/login.",
        "Failed. Branch topic/login has no upstream; run git push --set-upstream origin topic/login.")


# format : git merge --ff-only (« Not possible to fast-forward », conseil « Diverging branches »),
# exemple dev v3-vcs-git-0040
GIT_FF = """hint: Diverging branches can't be fast-forwarded, you need to either:
hint:
hint: 	git merge --no-ff
hint:
hint: or:
hint:
hint: 	git rebase
hint:
hint: Disable this message with "git config advice.diverging false"
fatal: Not possible to fast-forward, aborting.
"""


def test_git_fast_forward_impossible():
    assert both("git merge --ff-only origin/main", 128, GIT_FF) == (
        "Échec. Avance rapide impossible, les branches ont divergé.",
        "Failed. Fast-forward impossible, the branches have diverged.")


# format : ssh et libcurl sous git (« Could not resolve hostname », « Could not resolve host »),
# exemple dev v3-vcs-git-0020
GIT_CLONE_DNS = """Cloning into 'tools'...
ssh: Could not resolve hostname example.org: Name or service not known
fatal: Could not read from remote repository.

Please make sure you have the correct access rights
and the repository exists.
"""


def test_git_clone_unknown_host():
    assert both("git clone git@example.org:team/tools.git", 128, GIT_CLONE_DNS) == (
        "Échec. Hôte example.org introuvable.", "Failed. Host example.org not found.")


# format : git checkout d'un commit (« detached HEAD », « HEAD is now at »), exemple dev v3-vcs-git-0024
GIT_DETACHED = """Note: switching to 'HEAD~2'.

You are in 'detached HEAD' state. You can look around, make experimental
changes and commit them, and you can discard any commits you make in this
state without impacting any branches by switching back to a branch.

If you want to create a new branch to retain commits you create, you may
do so (now or later) by using -c with the switch command. Example:

  git switch -c <new-branch-name>

Turn off this advice by setting config variable advice.detachedHead to false

HEAD is now at 3f2e1d0 Add login form
"""


def test_git_checkout_detached_head():
    assert both("git checkout HEAD~2", 0, GIT_DETACHED) == ("HEAD détachée sur 3f2e1d0, Add login form.",
                                                           "HEAD detached at 3f2e1d0, Add login form.")


# format : git status pendant un rebase (wt-status.c, anglais et français), exemples dev v3-vcs-git-0039 et 0043
GIT_REBASE = """interactive rebase in progress; onto 9ab8c7d
Last command done (1 command done):
   pick 1234567 # Add cart model
Next commands to do (2 remaining commands):
   pick 2345678 # Add cart view
   pick 3456789 # Changelog
  (use "git rebase --edit-todo" to view and edit)
You are currently rebasing branch 'feature/cart' on '9ab8c7d'.
  (fix conflicts and then run "git rebase --continue")
  (use "git rebase --skip" to skip this patch)
  (use "git rebase --abort" to check out the original branch)

Unmerged paths:
  (use "git restore --staged <file>..." to unstage)
  (use "git add <file>..." to mark resolution)
	both modified:   shop/cart.py

no changes added to commit (use "git add" and/or "git commit -a")
"""

GIT_REBASE_FR = """rebasage interactif en cours\xa0; sur 9ab8c7d
Dernière commande effectuée (1 commande effectuée)\xa0:
   pick 1234567 Add cart model
Prochaine commande à effectuer (1 commande restante)\xa0:
   pick 2345678 Add cart view
  (utilisez "git rebase --edit-todo" pour voir et éditer)
Vous êtes en train de rebaser la branche 'feature/cart' sur '9ab8c7d'.
  (réglez les conflits puis lancez "git rebase --continue")

Chemins non fusionnés\xa0:
  (utilisez "git add <fichier>..." pour marquer comme résolu)
	modifié des deux côtés\xa0:  shop/cart.py
	modifié des deux côtés\xa0:  shop/views.py

aucune modification n'a été ajoutée à la validation (utilisez "git add" ou "git commit -a")
"""


def test_git_status_during_rebase():
    assert both("git status", 0, GIT_REBASE) == (
        "Rebase interactif de feature/cart en cours sur 9ab8c7d, conflit dans cart.py, 2 commandes restantes.",
        "Interactive rebase of feature/cart in progress onto 9ab8c7d, conflict in cart.py, 2 commands remaining.")


def test_git_status_during_rebase_french_output():
    assert resolve("git status", 0, GIT_REBASE_FR) == (
        "Rebase interactif de feature/cart en cours sur 9ab8c7d, conflit dans cart.py et views.py, "
        "1 commande restante.")


# format : git log --stat (bloc commit, sujet indenté de 4 espaces, diffstat), exemple dev v3-vcs-git-0046
GIT_LOG_STAT = """commit 0123456789abcdef0123456789abcdef01234567
Author: Dev User <dev@example.invalid>
Date:   Mon Jan 5 10:00:00 2026 +0100

    Add cart page

 shop/cart.py  | 40 ++++++++++++++++++++++++++++++++++++++++
 shop/views.py |  3 ++-
 2 files changed, 42 insertions(+), 1 deletion(-)

commit 89abcdef0123456789abcdef0123456789abcdef
Author: Dev User <dev@example.invalid>
Date:   Sun Jan 4 10:00:00 2026 +0100

    Initial commit

 README.md | 1 +
 1 file changed, 1 insertion(+)
"""


def test_git_log_stat():
    assert both("git log --stat -n 2", 0, GIT_LOG_STAT) == (
        "2 commits. Dernier : Add cart page, 2 fichiers modifiés : cart.py et views.py.",
        "2 commits. Last: Add cart page, 2 files changed: cart.py and views.py.")


def test_git_log_stat_piped_is_not_counted():
    assert resolve("git log --stat | head -40", 0, GIT_LOG_STAT) is None


# format : gh sans authentification (message de GitHub CLI), exemple dev v3-infra-0014
GH_AUTH = ("To get started with GitHub CLI, please run:  gh auth login\n"
           "Alternatively, populate the GH_TOKEN environment variable with a GitHub API authentication token.\n")


def test_gh_not_logged_in():
    assert both("gh pr list", 4, GH_AUTH) == (
        "Échec. GitHub CLI non connecté : lancer gh auth login ou définir GH_TOKEN.",
        "Failed. GitHub CLI is not logged in: run gh auth login or set GH_TOKEN.")


# ---------------------------------------------------------------- docker, kubectl, helm
# format : BuildKit (« ERROR: failed to solve: », « Dockerfile:N »), exemples dev v3-containers-0011 et 0012

BUILDKIT_HEAD = """#0 building with "default" instance using docker driver

#1 [internal] load build definition from Dockerfile
#1 transferring dockerfile: 120B done
#1 DONE 0.0s
"""

DOCKER_PARSE = BUILDKIT_HEAD + """Dockerfile:5
--------------------
   3 |     COPY . .
   4 |     RUN make
   5 | >>> EXPOSES 8080
--------------------
ERROR: failed to solve: dockerfile parse error on line 5: unknown instruction: EXPOSES (did you mean EXPOSE?)
"""

DOCKER_BASE = BUILDKIT_HEAD + """
#2 [internal] load metadata for docker.io/library/python:3.99-slim
#2 ERROR: docker.io/library/python:3.99-slim: not found
------
 > [internal] load metadata for docker.io/library/python:3.99-slim:
------
Dockerfile:1
--------------------
   1 | >>> FROM python:3.99-slim
   2 |     WORKDIR /app
--------------------
ERROR: failed to solve: python:3.99-slim: failed to resolve source metadata for docker.io/library/python:3.99-slim: docker.io/library/python:3.99-slim: not found
"""

DOCKER_COPY = BUILDKIT_HEAD + """
#5 [3/4] COPY config.yaml /etc/app/
#5 ERROR: failed to calculate checksum of ref 1f2e3d::abcd: "/config.yaml": not found
------
Dockerfile:4
--------------------
   4 | >>> COPY config.yaml /etc/app/
--------------------
ERROR: failed to solve: failed to compute cache key: failed to calculate checksum of ref 1f2e3d::abcd: "/config.yaml": not found
"""

DOCKER_OTHER = BUILDKIT_HEAD + """Dockerfile:2
--------------------
   2 | >>> ARG ${
--------------------
ERROR: failed to solve: failed to process "${": missing '}' in expression
"""


def test_docker_unknown_instruction():
    assert both("docker build -t api .", 1, DOCKER_PARSE) == (
        "Échec. Dockerfile ligne 5 : instruction inconnue EXPOSES, peut-être EXPOSE.",
        "Failed. Dockerfile line 5: unknown instruction EXPOSES, did you mean EXPOSE.")


def test_docker_base_image_not_found():
    assert both("docker build .", 1, DOCKER_BASE) == (
        "Échec. Image python:3.99-slim introuvable, Dockerfile ligne 1.",
        "Failed. Image python:3.99-slim not found, Dockerfile line 1.")


def test_docker_copy_source_missing():
    assert both("docker build .", 1, DOCKER_COPY) == (
        "Échec. config.yaml introuvable dans le contexte de build, Dockerfile ligne 4.",
        "Failed. config.yaml not found in the build context, Dockerfile line 4.")


def test_docker_other_buildkit_error_is_a_skeleton():
    assert resolve("docker build .", 1, DOCKER_OTHER) is None
    assert skeleton("docker build .", 1, DOCKER_OTHER) == "Échec. Build Docker en échec, Dockerfile ligne 2."


# format : kubectl sans serveur (client-go « Unable to connect to the server », « was refused »),
# exemple dev v3-containers-0015
KUBE_TIMEOUT = "\n".join(
    ['E0101 10:00:0%d.000000 1234 memcache.go:265] "Unhandled Error" err="couldn\'t get current server API group list: '
     'Get \\"https://198.51.100.7:6443/api?timeout=5s\\": net/http: request canceled while waiting for connection"'
     % i for i in range(4)]
    + ["Unable to connect to the server: net/http: request canceled while waiting for connection "
       "(Client.Timeout exceeded while awaiting headers)"])

KUBE_REFUSED = "\n".join(
    ['E0101 10:00:0%d.000000 1234 memcache.go:265] couldn\'t get current server API group list: Get '
     '"http://localhost:8080/api?timeout=32s": dial tcp [::1]:8080: connect: connection refused' % i for i in range(4)]
    + ["The connection to the server localhost:8080 was refused - did you specify the right host or port?"])


def test_kubectl_timeout():
    assert both("kubectl get pods", 1, KUBE_TIMEOUT) == (
        "Échec. Serveur Kubernetes 198.51.100.7:6443 injoignable : délai dépassé.",
        "Failed. Kubernetes server 198.51.100.7:6443 unreachable: timed out.")


def test_kubectl_connection_refused():
    assert both("kubectl get nodes", 1, KUBE_REFUSED) == (
        "Échec. Serveur Kubernetes localhost:8080 injoignable : connexion refusée.",
        "Failed. Kubernetes server localhost:8080 unreachable: connection refused.")


# format : helm lint ([ERROR], « N chart(s) linted, M chart(s) failed »), exemple dev v3-containers-0023
HELM_LINT = """==> Linting billing
[ERROR] Chart.yaml: version is required
[INFO] Chart.yaml: icon is recommended
[ERROR] templates/: validation: chart.metadata.version is required

Error: 1 chart(s) linted, 1 chart(s) failed
"""


def test_helm_lint_failure_is_a_skeleton():
    assert resolve("helm lint billing", 1, HELM_LINT) is None
    assert skeleton("helm lint billing", 1, HELM_LINT) == "Échec. Lint du chart billing : 2 erreurs."
    assert skeleton("helm lint billing", 1, HELM_LINT, "en") == "Failed. Lint of chart billing: 2 errors."


# format : helm template (documents YAML précédés de « # Source: chart/templates/… »), exemple dev v3-containers-0024
HELM_TEMPLATE = """---
# Source: web/templates/configmap.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: demo-web
data:
  LOG_LEVEL: info
---
# Source: web/templates/service.yaml
apiVersion: v1
kind: Service
metadata:
  name: demo-web
spec:
  ports:
    - port: 80
---
# Source: web/templates/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: demo-web
spec:
  replicas: 2
"""


def test_helm_template():
    assert both("helm template demo ./web --set replicaCount=2", 0, HELM_TEMPLATE) == (
        "Chart web rendu pour la release demo, 3 manifestes : ConfigMap, Service et Deployment.",
        "Chart web rendered for release demo, 3 manifests: ConfigMap, Service and Deployment.")


def test_helm_template_release_is_said_only_when_the_chart_argument_matches():
    said = resolve("helm template ./web --kube-context staging", 0, HELM_TEMPLATE)
    assert said == "Chart web rendu, 3 manifestes : ConfigMap, Service et Deployment."


# ---------------------------------------------------------------- terraform
# format : sorties de Terraform 1.x (init, plan, apply, state list), exemples dev v3-infra-0001 à 0005

TF_INIT = """
Initializing the backend...

Initializing provider plugins...
- Finding hashicorp/aws versions matching "~> 5.0"...
- Installing hashicorp/aws v5.54.1...
- Installed hashicorp/aws v5.54.1 (signed by HashiCorp)

Terraform has created a lock file .terraform.lock.hcl to record the provider
selections it made above.

Terraform has been successfully initialized!

You may now begin working with Terraform. Try running "terraform plan" to see
any changes that are required for your infrastructure.
"""

TF_APPLY = """aws_s3_bucket.logs: Creating...
aws_s3_bucket.logs: Creation complete after 2s [id=team-logs]
aws_iam_role.app: Modifying... [id=app]
aws_iam_role.app: Modifications complete after 1s [id=app]

Apply complete! Resources: 2 added, 1 changed, 0 destroyed.

Outputs:

bucket = "team-logs"
region = "eu-west-3"
token = <sensitive>
"""

TF_PLAN = """
Terraform used the selected providers to generate the following execution
plan. Resource actions are indicated with the following symbols:
  + create
  ~ update in-place
  - destroy

Terraform will perform the following actions:

  # aws_instance.web will be created
  + resource "aws_instance" "web" {
      + ami = "ami-0123"
    }

  # aws_s3_bucket.old will be destroyed
  - resource "aws_s3_bucket" "old" {
      - bucket = "old-bucket" -> null
    }

  # aws_security_group.web will be updated in-place
  ~ resource "aws_security_group" "web" {
      ~ description = "a" -> "b"
    }

Plan: 1 to add, 1 to change, 1 to destroy.
"""

TF_NO_CHANGES = """No changes. Your infrastructure matches the configuration.

Terraform has compared your real infrastructure against your configuration and
found no differences, so no changes are needed.
"""

TF_ERROR = """╷
│ Error: Unsupported argument
│
│   on main.tf line 12, in resource "aws_instance" "web":
│   12:   instance_typo = "t3.micro"
│
│ An argument named "instance_typo" is not expected here.
╵
"""


def test_terraform_init():
    assert both("terraform init", 0, TF_INIT) == ("Terraform initialisé, hashicorp/aws 5.54.1 installé.",
                                                 "Terraform initialized, hashicorp/aws 5.54.1 installed.")


def test_terraform_apply_with_outputs():
    assert both("terraform apply -auto-approve", 0, TF_APPLY) == (
        "Application terminée : 2 ressources ajoutées, 1 modifiée. Sorties : bucket team-logs, region eu-west-3.",
        "Apply complete: 2 resources added, 1 changed. Outputs: bucket team-logs, region eu-west-3.")


def test_terraform_plan_names_resources_by_action():
    assert both("terraform plan", 0, TF_PLAN) == (
        "Plan : 1 ajout, 1 modification, 1 destruction. À créer : aws_instance.web. "
        "À modifier : aws_security_group.web. À détruire : aws_s3_bucket.old.",
        "Plan: 1 to add, 1 to change, 1 to destroy. Create: aws_instance.web. "
        "Update: aws_security_group.web. Destroy: aws_s3_bucket.old.")


def test_terraform_plan_replacement():
    out = TF_PLAN.split("Terraform will perform")[0] + (
        "Terraform will perform the following actions:\n\n  # aws_instance.web must be replaced\n"
        "-/+ resource \"aws_instance\" \"web\" {\n    }\n\nPlan: 1 to add, 0 to change, 1 to destroy.\n")
    assert both("terraform plan", 0, out) == ("Plan : 1 ajout, 1 destruction. À remplacer : aws_instance.web.",
                                             "Plan: 1 to add, 1 to destroy. Replace: aws_instance.web.")


def test_terraform_no_changes():
    assert both("terraform plan", 0, TF_NO_CHANGES) == (
        "Aucun changement, l'infrastructure correspond à la configuration.",
        "No changes, the infrastructure matches the configuration.")


def test_terraform_state_list():
    out = "\n".join(["aws_iam_role.app", "aws_instance.web", "aws_s3_bucket.logs", "aws_security_group.web",
                     "data.aws_ami.debian", 'module.net.aws_subnet.private["a"]'])
    assert both("terraform state list", 0, out) == (
        "6 ressources dans l'état, dont aws_iam_role.app, aws_instance.web et aws_s3_bucket.logs.",
        "6 resources in state, including aws_iam_role.app, aws_instance.web and aws_s3_bucket.logs.")


def test_terraform_error_is_a_skeleton():
    assert resolve("terraform plan", 1, TF_ERROR) is None
    assert skeleton("terraform plan", 1, TF_ERROR) == "Échec. Erreur Terraform, main.tf ligne 12."
    assert skeleton("terraform plan", 1, TF_ERROR, "en") == "Failed. Terraform error, main.tf line 12."


def test_skeleton_is_none_when_code_already_speaks():
    assert skeleton("terraform plan", 0, TF_NO_CHANGES) is None
