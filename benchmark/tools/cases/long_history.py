"""Synthetic long-output ("long-truncated") and session-history QA cases for Steph Speak Bench.

Repetitive middles are generated with a fixed random.Random(seed) so the module stays
deterministic across runs.

SPDX-License-Identifier: MIT
"""

from __future__ import annotations

import random

SUBSYSTEMS = ["core", "net", "io", "gui", "math", "parser", "utils", "cache",
              "auth", "render", "codec", "proto", "disk", "sched"]
WORD_STEMS = ["core", "dev", "common", "utils", "base", "extra", "doc", "bin",
              "tools", "client", "server", "gtk", "qt", "json", "xml", "http",
              "crypto", "media", "video", "audio", "data", "net", "test", "log"]
PKG_PREFIXES = ["lib", "python3-", "gir1.2-", "fonts-", "gnome-", "php-",
                "ruby-", "nodejs-", "perl-", "golang-", "rust-"]


# ---------------------------------------------------------------- filler generators

def _make_build_log() -> str:
    rng = random.Random(20260501)
    lines = []
    for i in range(1, 289):
        sub = rng.choice(SUBSYSTEMS)
        lines.append(f"cc -std=c11 -O2 -Wall -c -o build/{sub}/mod_{i:03d}.o src/{sub}/mod_{i:03d}.c")
    lines += [
        "cc -std=c11 -O2 -Wall -c -o build/net/socket_bridge.o src/net/socket_bridge.c",
        "cc -o dist/engine build/*/*.o -lpthread -lm",
        "build/net/socket_bridge.o: in function `net_connect':",
        "net/socket_bridge.c:88: undefined reference to `socket_configure'",
        "collect2: error: ld returned 1 exit status",
        "make: *** [Makefile:42: dist/engine] Error 1",
    ]
    return "\n".join(lines)


def _pytest_log() -> str:
    rng = random.Random(20260502)
    modules = ["test_auth", "test_models", "test_billing", "test_api",
               "test_utils", "test_views", "test_cache", "test_search"]
    total = 239
    lines = []
    for i in range(total):
        mod = rng.choice(modules)
        pct = int((i + 1) / (total + 1) * 100)
        lines.append(f"tests/{mod}.py::test_case_{i:03d} PASSED [{pct:3d}%]")
    lines += [
        "tests/test_billing.py::test_refund_amount FAILED [100%]",
        "",
        "=================================== FAILURES ===================================",
        "________________________________ test_refund_amount ________________________________",
        "",
        "    def test_refund_amount():",
        ">       assert compute_refund(order) == 29.99",
        "E       assert 19.99 == 29.99",
        "",
        "tests/test_billing.py:142: AssertionError",
        "=========================== short test summary info ============================",
        "FAILED tests/test_billing.py::test_refund_amount - AssertionError: assert 19.99 == 29.99",
        "===================== 1 failed, 239 passed in 18.42s =====================",
    ]
    return "\n".join(lines)


def _rsync_log() -> str:
    rng = random.Random(20260503)
    dirs = ["src", "docs", "tests", "assets", "scripts", "config", "public", "lib"]
    exts = ["py", "md", "json", "png", "js", "ts", "yaml", "txt"]
    lines = ["sending incremental file list"]
    for i in range(210):
        d, ext = rng.choice(dirs), rng.choice(exts)
        lines.append(f"projects/{d}/file_{i:04d}.{ext}")
    lines += [
        "",
        "sent 42,318,204 bytes  received 3,912 bytes  512,394.11 bytes/sec",
        "total size is 42,300,000  speedup is 1.00",
    ]
    return "\n".join(lines)


def _apt_names(rng: random.Random, n: int) -> list:
    return [f"{rng.choice(PKG_PREFIXES)}{rng.choice(WORD_STEMS)}-{i % 41}" for i in range(n)]


def _apt_log(lang: str) -> str:
    rng = random.Random(20260504)
    names = _apt_names(rng, 214)
    removed = ["linux-image-6.1.0-9-amd64", "linux-headers-6.1.0-9-amd64",
               "linux-headers-6.1.0-9-common"]
    if lang == "fr":
        head = ["Lecture des listes de paquets... Fait",
                "Construction de l'arbre des dépendances... Fait",
                "Lecture des informations d'état... Fait",
                "Calcul de la mise à niveau... Fait",
                "Les paquets suivants seront enlevés :"]
        mid = ["Les paquets suivants seront mis à niveau :"]
        tail = "214 mis à jour, 0 nouvellement installés, 3 à enlever et 0 non mis à jour."
    else:
        head = ["Reading package lists... Done",
                "Building dependency tree... Done",
                "Reading state information... Done",
                "Calculating upgrade... Done",
                "The following packages will be REMOVED:"]
        mid = ["The following packages will be upgraded:"]
        tail = "214 upgraded, 0 newly installed, 3 to remove and 0 not upgraded."
    lines = head + [f"  {p}" for p in removed] + mid + [f"  {n}" for n in names] + [tail]
    return "\n".join(lines)


def _journalctl_log(lang: str) -> str:
    rng = random.Random(20260505)
    host = "web01"
    lines = []
    for _ in range(66):
        hh, mm, ss = rng.randint(0, 23), rng.randint(0, 59), rng.randint(0, 59)
        pid = rng.randint(1000, 9999)
        ts = f"Sep {rng.randint(1, 26):02d} {hh:02d}:{mm:02d}:{ss:02d}"
        if lang == "fr":
            lines += [
                f"{ts} {host} systemd[1] : Rechargement de nginx - high performance web server...",
                f"{ts} {host} nginx[{pid}]: configuration file /etc/nginx/nginx.conf test is successful",
                f"{ts} {host} systemd[1] : Rechargement de nginx - high performance web server terminé.",
            ]
        else:
            lines += [
                f"{ts} {host} systemd[1]: Reloading nginx - high performance web server...",
                f"{ts} {host} nginx[{pid}]: configuration file /etc/nginx/nginx.conf test is successful",
                f"{ts} {host} systemd[1]: Reloaded nginx - high performance web server.",
            ]
    if lang == "fr":
        lines += [
            "Sep 27 03:14:02 web01 systemd[1] : Rechargement de nginx - high performance web server...",
            "Sep 27 03:14:02 web01 nginx[2044]: nginx: [emerg] invalid number of arguments in \"listen\" directive in /etc/nginx/sites-enabled/default:12",
            "Sep 27 03:14:02 web01 nginx[2044]: nginx: configuration file /etc/nginx/nginx.conf test failed",
            "Sep 27 03:14:02 web01 systemd[1] : nginx.service : le processus de contrôle a quitté avec le code d'erreur, état=1/FAILURE",
            "Sep 27 03:14:02 web01 systemd[1] : nginx.service : échec, résultat « exit-code ».",
            "Sep 27 03:14:02 web01 systemd[1] : Échec du rechargement de nginx - high performance web server.",
        ]
    else:
        lines += [
            "Sep 27 03:14:02 web01 systemd[1]: Reloading nginx - high performance web server...",
            "Sep 27 03:14:02 web01 nginx[2044]: nginx: [emerg] invalid number of arguments in \"listen\" directive in /etc/nginx/sites-enabled/default:12",
            "Sep 27 03:14:02 web01 nginx[2044]: nginx: configuration file /etc/nginx/nginx.conf test failed",
            "Sep 27 03:14:02 web01 systemd[1]: nginx.service: Control process exited, code=exited, status=1/FAILURE",
            "Sep 27 03:14:02 web01 systemd[1]: nginx.service: Failed with result 'exit-code'.",
            "Sep 27 03:14:02 web01 systemd[1]: Reload failed for nginx - high performance web server.",
        ]
    return "\n".join(lines)


def _docker_build_log() -> str:
    rng = random.Random(20260506)
    lines = [
        "#1 [internal] load build definition from Dockerfile",
        "#1 transferring dockerfile: 512B done",
        "#1 DONE 0.1s",
        "#2 [internal] load .dockerignore",
        "#2 transferring context: 84B done",
        "#2 DONE 0.1s",
        "#3 [internal] load metadata for docker.io/library/node:20-slim",
        "#3 DONE 0.6s",
        "#4 [1/6] FROM docker.io/library/node:20-slim",
        "#4 DONE 0.0s",
        "#5 [2/6] WORKDIR /app",
        "#5 DONE 0.1s",
        "#6 [3/6] COPY package.json package-lock.json ./",
        "#6 DONE 0.1s",
        "#7 [4/6] RUN npm ci",
    ]
    t = 1.0
    for _ in range(180):
        pkg = f"{rng.choice(WORD_STEMS)}-{rng.choice(WORD_STEMS)}"
        t += 0.4
        lines.append(f"#7 {t:.1f} npm http fetch GET 200 https://registry.npmjs.org/{pkg} {rng.randint(20, 400)}ms (cache miss)")
    lines += [
        "#7 78.3 added 842 packages in 77s",
        "#7 DONE 78.4s",
        "#8 [5/6] COPY . .",
        "#8 DONE 0.3s",
        "#9 [6/6] RUN npm run build",
        "#9 6.1 webapp@1.4.0 build",
        "#9 6.1 vite build",
        "#9 8.9 built in 8.72s",
        "#9 DONE 8.9s",
        "#10 exporting to image",
        "#10 exporting layers 0.4s done",
        "#10 writing image sha256:3f2a91c8b7d4 done",
        "#10 naming to registry.example.com/webapp:latest done",
        "#10 DONE 0.5s",
    ]
    return "\n".join(lines)


def _find_log(lang: str) -> str:
    rng = random.Random(20260507)
    dirs = ["/var/log", "/opt/app/logs", "/home/user/logs", "/srv/app/log",
            "/var/lib/app/logs", "/usr/local/var/log"]
    names = ["access", "error", "worker", "cron", "audit", "sync", "app", "debug"]
    lines = [f"{rng.choice(dirs)}/{rng.choice(names)}_{i:04d}.log" for i in range(225)]
    if lang == "fr":
        lines.append("find : « /var/lib/docker/overlay2/a1b2c3d4e5f6/diff » : Permission non accordée")
    else:
        lines.append("find: '/var/lib/docker/overlay2/a1b2c3d4e5f6/diff': Permission denied")
    return "\n".join(lines)


def _tar_log(lang: str) -> str:
    rng = random.Random(20260508)
    dirs = ["etc", "var/log/app", "usr/local/bin", "home/user/data", "opt/app"]
    names = ["config", "worker", "session", "cache", "report", "index"]
    lines = ["backup-2026-09/"]
    for i in range(255):
        d, n = rng.choice(dirs), rng.choice(names)
        lines.append(f"backup-2026-09/{d}/{n}_{i:04d}.dat")
    if lang == "fr":
        lines += ["tar : Fin de fichier inattendue dans l'archive",
                  "tar : Erreur non récupérable : abandon"]
    else:
        lines += ["tar: Unexpected EOF in archive",
                  "tar: Error is not recoverable: exiting now"]
    return "\n".join(lines)


# ---------------------------------------------------------------- long-truncated cases

CASES = [
    {
        "id": "long-make-linker-error",
        "category": "long-truncated",
        "origin": "synthetic",
        "split": "test",
        "task": "summary",
        "cmd": "make",
        "exit": 2,
        "duration": 51.3,
        "output": _make_build_log(),
        "expected": {
            "en": [r"fail|error|could not|cannot", r"undefined reference|socket_configure", r"socket_bridge", r"\b88\b"],
            "fr": [r"echec|erreur|echoue|impossible", r"reference indefinie|socket_configure", r"socket_bridge", r"\b88\b"],
            "de": [r"fehlgeschlagen|fehler|konnte nicht|kann nicht", r"undefinierter verweis|socket_configure", r"socket_bridge", r"\b88\b"],
            "es": [r"fallo|error|no se pudo|no pudo", r"referencia indefinida|socket_configure", r"socket_bridge", r"\b88\b"],
            "pt": [r"falhou|erro|nao foi possivel|nao consegue", r"referencia indefinida|socket_configure", r"socket_bridge", r"\b88\b"],
            "ru": [r"ошибк|не удалось|невозможно", r"неопределенная ссылка|socket_configure", r"socket_bridge", r"\b88\b"],
        },
        "forbidden": {
            "en": [r"\bsyntax error\b", r"\bline 42\b"],
            "fr": [r"erreur de syntaxe", r"\bligne 42\b"],
            "de": [r"syntaxfehler", r"\bzeile 42\b"],
            "es": [r"error de sintaxis", r"\blinea 42\b"],
            "pt": [r"erro de sintaxe", r"\blinha 42\b"],
            "ru": [r"синтаксическая ошибка", r"\bстрока 42\b"],
        },
        "reference": {
            "en": "Failed. Undefined reference to socket_configure, socket_bridge.c line 88.",
            "fr": "Échec. Référence indéfinie à socket_configure, socket_bridge.c ligne 88.",
            "de": "Fehlgeschlagen. Undefinierter Verweis auf socket_configure, socket_bridge.c Zeile 88.",
            "es": "Fallo. Referencia indefinida a socket_configure, socket_bridge.c línea 88.",
            "pt": "Falhou. Referência indefinida a socket_configure, socket_bridge.c linha 88.",
            "ru": "Ошибка. Неопределённая ссылка на socket_configure, socket_bridge.c строка 88.",
        },
        "notes": "289 compile lines then a link-time failure; the decisive fact sits in the last 6 lines.",
    },
    {
        "id": "long-pytest-summary",
        "category": "long-truncated",
        "origin": "synthetic",
        "split": "test",
        "task": "summary",
        "cmd": "pytest -v",
        "exit": 1,
        "duration": 18.42,
        "output": _pytest_log(),
        "expected": {
            "en": [r"test_refund_amount", r"\b1\b", r"\b239\b"],
            "fr": [r"test_refund_amount", r"\b1\b", r"\b239\b"],
            "de": [r"test_refund_amount", r"\b1\b", r"\b239\b"],
            "es": [r"test_refund_amount", r"\b1\b", r"\b239\b"],
            "pt": [r"test_refund_amount", r"\b1\b", r"\b239\b"],
            "ru": [r"test_refund_amount", r"\b1\b", r"\b239\b"],
        },
        "forbidden": {
            "en": [r"\b0 failed\b", r"\bimport ?error\b", r"\b240 passed\b"],
            "fr": [r"\b0 echecs?\b", r"\berreur d.import\b", r"\b240 reussites\b"],
            "de": [r"\b0 fehlgeschlagen\b", r"importfehler", r"\b240 bestanden\b"],
            "es": [r"\b0 fallos?\b", r"error de importacion", r"\b240 aprobadas?\b"],
            "pt": [r"\b0 falhas?\b", r"erro de importacao", r"\b240 aprovados?\b"],
            "ru": [r"\b0 ошибок\b", r"ошибка импорта", r"\b240 проидено\b"],
        },
        "reference": {
            "en": "Failed. test_refund_amount assertion error, 1 failed, 239 passed.",
            "fr": "Échec. test_refund_amount, erreur d'assertion, 1 échec, 239 réussites.",
            "de": "Fehlgeschlagen. test_refund_amount, Assertion-Fehler, 1 fehlgeschlagen, 239 bestanden.",
            "es": "Fallo. test_refund_amount, error de aserción, 1 fallo, 239 aprobadas.",
            "pt": "Falhou. test_refund_amount, erro de asserção, 1 falha, 239 aprovados.",
            "ru": "Ошибка. test_refund_amount, ошибка утверждения, 1 не пройден, 239 пройдено.",
        },
        "notes": "239 PASSED lines then one FAILURE block; the summary line is the very last line.",
    },
    {
        "id": "long-rsync-transfer",
        "category": "long-truncated",
        "origin": "synthetic",
        "split": "dev",
        "task": "summary",
        "cmd": "rsync -av /data/projects/ backup:/mnt/backup/projects/",
        "exit": 0,
        "duration": 142.7,
        "output": _rsync_log(),
        "expected": {
            "en": [r"42[ .,]?318[ .,]?204", r"42[ .,]?300[ .,]?000"],
            "fr": [r"42[ .,]?318[ .,]?204", r"42[ .,]?300[ .,]?000"],
            "de": [r"42[ .,]?318[ .,]?204", r"42[ .,]?300[ .,]?000"],
            "es": [r"42[ .,]?318[ .,]?204", r"42[ .,]?300[ .,]?000"],
            "pt": [r"42[ .,]?318[ .,]?204", r"42[ .,]?300[ .,]?000"],
            "ru": [r"42[ .,]?318[ .,]?204", r"42[ .,]?300[ .,]?000"],
        },
        "forbidden": {
            "en": [r"\bfail(?:ed)?\b"],
            "fr": [r"\bechec\b"],
            "de": [r"fehlgeschlagen"],
            "es": [r"\bfallo\b"],
            "pt": [r"\bfalhou\b"],
            "ru": [r"ошибк"],
        },
        "reference": {
            "en": "Done. Sent 42,318,204 bytes, total size 42,300,000.",
            "fr": "Terminé. Envoyé 42 318 204 octets, taille totale 42 300 000.",
            "de": "Fertig. Gesendet 42 318 204 Bytes, Gesamtgröße 42 300 000.",
            "es": "Listo. Enviados 42 318 204 bytes, tamaño total 42 300 000.",
            "pt": "Concluído. Enviados 42 318 204 bytes, tamanho total 42 300 000.",
            "ru": "Готово. Отправлено 42 318 204 байт, общий размер 42 300 000.",
        },
        "notes": "210 transferred file names then the two rsync stat lines at the very end.",
    },
    {
        "id": "long-apt-fullupgrade-count",
        "category": "long-truncated",
        "origin": "synthetic",
        "split": "test",
        "task": "summary",
        "cmd": "apt-get -s full-upgrade",
        "exit": 0,
        "duration": 3.8,
        "output": {"en": _apt_log("en"), "fr": _apt_log("fr")},
        "expected": {
            "en": [r"\b214\b", r"upgrad", r"\b3\b", r"remov"],
            "fr": [r"\b214\b", r"mis(es)? a jour|mise a jour|\bmaj\b|actualis", r"\b3\b", r"supprim"],
            "de": [r"\b214\b", r"aktualisiert|upgrad", r"\b3\b", r"entfernt"],
            "es": [r"\b214\b", r"actualizad|upgrad", r"\b3\b", r"eliminad|desinstalad"],
            "pt": [r"\b214\b", r"atualizad|upgrad", r"\b3\b", r"removid"],
            "ru": [r"\b214\b", r"обновлен|upgrad", r"\b3\b", r"удален"],
        },
        "forbidden": {
            "en": [r"\b0 removed?\b", r"\b217\b"],
            "fr": [r"\b0 supprim", r"\b217\b"],
            "de": [r"\b0 entfernt\b", r"\b217\b"],
            "es": [r"\b0 eliminad", r"\b217\b"],
            "pt": [r"\b0 removid", r"\b217\b"],
            "ru": [r"\b0 удален", r"\b217\b"],
        },
        "reference": {
            "en": "214 upgraded, 3 removed.",
            "fr": "214 mis à jour, 3 supprimés.",
            "de": "214 aktualisiert, 3 entfernt.",
            "es": "214 actualizados, 3 eliminados.",
            "pt": "214 atualizados, 3 removidos.",
            "ru": "214 обновлено, 3 удалено.",
        },
        "notes": "Simulate mode (-s): 214 package names one per line, ending with the counts line, no download.",
    },
    {
        "id": "long-journalctl-failure",
        "category": "long-truncated",
        "origin": "synthetic",
        "split": "test",
        "task": "summary",
        "cmd": "journalctl -u nginx.service --no-pager",
        "exit": 0,
        "duration": 0.4,
        "output": {"en": _journalctl_log("en"), "fr": _journalctl_log("fr")},
        "expected": {
            "en": [r"fail|error|could not|cannot", r"listen directive|invalid number of arguments", r"sites-enabled.default|\bdefault\b", r"\b12\b"],
            "fr": [r"echec|erreur|echoue|impossible", r"argument invalide|listen", r"sites-enabled.default|\bdefault\b", r"\b12\b"],
            "de": [r"fehlgeschlagen|fehler|konnte nicht|kann nicht", r"ungultige anzahl (von )?argumenten|listen", r"sites-enabled.default|\bdefault\b", r"\b12\b"],
            "es": [r"fallo|error|no se pudo|no pudo", r"numero invalido de argumentos|listen", r"sites-enabled.default|\bdefault\b", r"\b12\b"],
            "pt": [r"falhou|erro|nao foi possivel|nao consegue", r"numero invalido de argumentos|listen", r"sites-enabled.default|\bdefault\b", r"\b12\b"],
            "ru": [r"ошибк|не удалось|невозможно", r"неверное число аргументов|listen", r"sites-enabled.default|\bdefault\b", r"\b12\b"],
        },
        "forbidden": {
            "en": [r"\bpermission denied\b", r"\bout of memory\b"],
            "fr": [r"permission refusee", r"a court de memoire"],
            "de": [r"zugriff verweigert", r"kein speicher mehr|speicher voll"],
            "es": [r"permiso denegado", r"sin memoria|memoria agotada"],
            "pt": [r"permissao negada", r"sem memoria|memoria esgotada"],
            "ru": [r"доступ запрещен", r"нехватка памяти|недостаточно памяти"],
        },
        "reference": {
            "en": "Failed. Nginx reload, invalid listen directive, sites-enabled/default line 12.",
            "fr": "Échec. Rechargement nginx, argument invalide, listen, sites-enabled/default ligne 12.",
            "de": "Fehlgeschlagen. Nginx-Neuladen, ungültige listen-Direktive, sites-enabled/default Zeile 12.",
            "es": "Fallo. Recarga de nginx, directiva listen inválida, sites-enabled/default línea 12.",
            "pt": "Falhou. Recarregamento do nginx, diretiva listen inválida, sites-enabled/default linha 12.",
            "ru": "Ошибка. Перезагрузка nginx, неверный аргумент директивы listen, sites-enabled/default строка 12.",
        },
        "notes": "journalctl itself exits 0; the failure is in the log content, in the last reload cycle.",
    },
    {
        "id": "long-docker-build-naming",
        "category": "long-truncated",
        "origin": "synthetic",
        "split": "test",
        "task": "summary",
        "cmd": "docker build -t registry.example.com/webapp:latest .",
        "exit": 0,
        "duration": 87.3,
        "output": _docker_build_log(),
        "expected": {
            "en": [r"done|built|success|\bok\b|finished", r"webapp"],
            "fr": [r"termine|construit|reussi|succes|\bok\b", r"webapp"],
            "de": [r"fertig|erstellt|erfolgreich|\bok\b|abgeschlossen", r"webapp"],
            "es": [r"listo|construido|exito|\bok\b|finalizado", r"webapp"],
            "pt": [r"concluido|construido|sucesso|\bok\b|finalizado", r"webapp"],
            "ru": [r"готово|собрано|успешно|\bok\b|завершено", r"webapp"],
        },
        "forbidden": {
            "en": [r"\bfail(?:ed)?\b"],
            "fr": [r"\bechec\b"],
            "de": [r"fehlgeschlagen"],
            "es": [r"\bfallo\b"],
            "pt": [r"\bfalhou\b"],
            "ru": [r"ошибк"],
        },
        "reference": {
            "en": "Done. Built and tagged webapp:latest.",
            "fr": "Terminé. Image webapp:latest construite et taguée.",
            "de": "Fertig. webapp:latest erstellt und getaggt.",
            "es": "Listo. webapp:latest construido y etiquetado.",
            "pt": "Concluído. webapp:latest construído e etiquetado.",
            "ru": "Готово. webapp:latest собран и помечен тегом.",
        },
        "notes": "BuildKit npm fetch spam in the middle; the naming/DONE lines are the last of the log.",
    },
    {
        "id": "long-find-permission-denied",
        "category": "long-truncated",
        "origin": "synthetic",
        "split": "dev",
        "task": "summary",
        "cmd": "find / -name '*.log'",
        "exit": 1,
        "duration": 4.1,
        "output": {"en": _find_log("en"), "fr": _find_log("fr")},
        "expected": {
            "en": [r"fail|error|could not|cannot", r"permission denied", r"overlay"],
            "fr": [r"echec|erreur|echoue|impossible", r"acces refuse|permission (non accordee|refusee)|permission denied", r"overlay"],
            "de": [r"fehlgeschlagen|fehler|konnte nicht|kann nicht", r"zugriff verweigert|permission denied", r"overlay"],
            "es": [r"fallo|error|no se pudo|no pudo", r"permiso denegado|permission denied", r"overlay"],
            "pt": [r"falhou|erro|nao foi possivel|nao consegue", r"permissao negada|permission denied", r"overlay"],
            "ru": [r"ошибк|не удалось|невозможно", r"доступ запрещен|permission denied", r"overlay"],
        },
        "forbidden": {
            "en": [r"\bnot found\b", r"\bno such file\b"],
            "fr": [r"introuvable", r"aucun fichier"],
            "de": [r"nicht gefunden", r"keine solche datei"],
            "es": [r"no encontrado", r"no existe (el|tal) archivo"],
            "pt": [r"nao encontrado", r"nenhum arquivo (assim|desse tipo)"],
            "ru": [r"не наиден", r"нет такого фаила"],
        },
        "reference": {
            "en": "Failed. Permission denied on a docker overlay path.",
            "fr": "Échec. Accès refusé sur un chemin overlay docker.",
            "de": "Fehlgeschlagen. Zugriff verweigert auf einen Docker-Overlay-Pfad.",
            "es": "Fallo. Permiso denegado en una ruta overlay de docker.",
            "pt": "Falhou. Permissão negada num caminho overlay do docker.",
            "ru": "Ошибка. Доступ запрещён к overlay-пути docker.",
        },
        "notes": "225 matched log paths then one stderr permission error as the last line.",
    },
    {
        "id": "long-tar-unexpected-eof",
        "category": "long-truncated",
        "origin": "synthetic",
        "split": "test",
        "task": "summary",
        "cmd": "tar -xvf backup-2026-09.tar.gz",
        "exit": 2,
        "duration": 33.6,
        "output": {"en": _tar_log("en"), "fr": _tar_log("fr")},
        "expected": {
            "en": [r"fail|error|could not|cannot", r"unexpected eof|eof|end of file"],
            "fr": [r"echec|erreur|echoue|impossible", r"fin de fichier|eof|archive (tronquee|incomplete)"],
            "de": [r"fehlgeschlagen|fehler|konnte nicht|kann nicht", r"unerwartetes dateiende|eof|archiv (unvollstandig|abgeschnitten)"],
            "es": [r"fallo|error|no se pudo|no pudo", r"fin de archivo inesperado|eof|archivo (truncado|incompleto)"],
            "pt": [r"falhou|erro|nao foi possivel|nao consegue", r"fim de arquivo inesperado|eof|arquivo (truncado|incompleto)"],
            "ru": [r"ошибк|не удалось|невозможно", r"неожиданныи конец фаила|eof|архив (обрезан|неполныи)"],
        },
        "forbidden": {
            "en": [r"\bdisk full\b", r"\bpermission denied\b"],
            "fr": [r"disque plein", r"acces refuse"],
            "de": [r"festplatte voll", r"zugriff verweigert"],
            "es": [r"disco lleno", r"permiso denegado"],
            "pt": [r"disco cheio", r"permissao negada"],
            "ru": [r"диск полон|нет места на диске", r"доступ запрещен"],
        },
        "reference": {
            "en": "Failed. Unexpected EOF in archive, extraction incomplete.",
            "fr": "Échec. Fin de fichier inattendue, extraction incomplète.",
            "de": "Fehlgeschlagen. Unerwartetes Dateiende im Archiv, Extraktion unvollständig.",
            "es": "Fallo. Fin de archivo inesperado en el archivo, extracción incompleta.",
            "pt": "Falhou. Fim de arquivo inesperado no arquivo, extração incompleta.",
            "ru": "Ошибка. Неожиданный конец файла в архиве, извлечение не завершено.",
        },
        "notes": "255 extracted member names then a truncated-archive error as the last two lines.",
    },

    # ---------------------------------------------------------------- history-qa cases

    {
        "id": "qa-failed-test",
        "category": "history-qa",
        "origin": "synthetic",
        "split": "test",
        "task": "qa",
        "history": {
            "en": [
                {"cmd": "pytest -q", "exit": 1, "output": (
                    "..F..                                                            [100%]\n"
                    "=================================== FAILURES ===================================\n"
                    "_________________________________ test_login __________________________________\n"
                    "tests/test_auth.py:34: AssertionError: assert False\n"
                    "=========================== short test summary info ============================\n"
                    "FAILED tests/test_auth.py::test_login - AssertionError: assert False\n"
                    "1 failed, 4 passed in 0.42s"
                )},
                {"cmd": "git status", "exit": 0, "output": "On branch main\nnothing to commit, working tree clean"},
            ],
            "fr": [
                {"cmd": "pytest -q", "exit": 1, "output": (
                    "..F..                                                            [100%]\n"
                    "=================================== FAILURES ===================================\n"
                    "_________________________________ test_login __________________________________\n"
                    "tests/test_auth.py:34: AssertionError: assert False\n"
                    "=========================== short test summary info ============================\n"
                    "FAILED tests/test_auth.py::test_login - AssertionError: assert False\n"
                    "1 failed, 4 passed in 0.42s"
                )},
                {"cmd": "git status", "exit": 0, "output": "Sur la branche main\nrien à valider, la copie de travail est propre"},
            ],
        },
        "question": {
            "en": "Which test failed?", "fr": "Quel test a échoué ?",
            "de": "Welcher Test ist fehlgeschlagen?", "es": "¿Qué prueba falló?",
            "pt": "Que teste falhou?", "ru": "Какой тест не прошёл?",
        },
        "expected": {
            "en": [r"test_login"],
            "fr": [r"test_login"],
            "de": [r"test_login"],
            "es": [r"test_login"],
            "pt": [r"test_login"],
            "ru": [r"test_login"],
        },
        "forbidden": {
            "en": [r"\ball (tests )?passed\b"],
            "fr": [r"tous les tests ont reussi|tout est passe"],
            "de": [r"alle tests (sind )?bestanden|alles bestanden"],
            "es": [r"todas las pruebas (pasaron|tuvieron exito)|todo paso"],
            "pt": [r"todos os testes passaram|tudo passou"],
            "ru": [r"все тесты проидены|все прошло успешно"],
        },
        "reference": {
            "en": "test_login failed.",
            "fr": "test_login a échoué.",
            "de": "test_login fehlgeschlagen.",
            "es": "test_login falló.",
            "pt": "test_login falhou.",
            "ru": "test_login не прошёл.",
        },
    },
    {
        "id": "qa-server-port",
        "category": "history-qa",
        "origin": "synthetic",
        "split": "test",
        "task": "qa",
        "history": [
            {"cmd": "cat app/config.yaml", "exit": 0, "output": (
                "server:\n  host: 0.0.0.0\n  port: 8443\n  workers: 4\n"
                "database:\n  url: postgres://db:5432/app"
            )},
            {"cmd": "curl -s http://localhost:8443/health", "exit": 0, "output": '{"status":"ok"}'},
        ],
        "question": {
            "en": "What port does the server listen on?", "fr": "Sur quel port écoute le serveur ?",
            "de": "Auf welchem Port lauscht der Server?", "es": "¿En qué puerto escucha el servidor?",
            "pt": "Em que porta o servidor escuta?", "ru": "На каком порту слушает сервер?",
        },
        "expected": {
            "en": [r"\b8443\b"],
            "fr": [r"\b8443\b"],
            "de": [r"\b8443\b"],
            "es": [r"\b8443\b"],
            "pt": [r"\b8443\b"],
            "ru": [r"\b8443\b"],
        },
        "forbidden": {
            "en": [r"\b5432\b"],
            "fr": [r"\b5432\b"],
            "de": [r"\b5432\b"],
            "es": [r"\b5432\b"],
            "pt": [r"\b5432\b"],
            "ru": [r"\b5432\b"],
        },
        "reference": {
            "en": "Port 8443.",
            "fr": "Port 8443.",
            "de": "Port 8443.",
            "es": "Puerto 8443.",
            "pt": "Porta 8443.",
            "ru": "Порт 8443.",
        },
    },
    {
        "id": "qa-ram-free",
        "category": "history-qa",
        "origin": "synthetic",
        "split": "test",
        "task": "qa",
        "history": {
            "en": [
                {"cmd": "free -h", "exit": 0, "output": (
                    "               total        used        free      shared  buff/cache   available\n"
                    "Mem:            15Gi       6.2Gi       3.1Gi       412Mi       6.0Gi        8.4Gi\n"
                    "Swap:          2.0Gi          0B       2.0Gi"
                )},
                {"cmd": "df -h", "exit": 0, "output": (
                    "Filesystem      Size  Used Avail Use% Mounted on\n"
                    "/dev/sda1        50G   22G   26G  46% /\n"
                    "/dev/sda2       500M  120M  350M  26% /boot"
                )},
            ],
            "fr": [
                {"cmd": "free -h", "exit": 0, "output": (
                    "               total       utilisé      libre     partagé  tamp/cache  disponible\n"
                    "Mem:            15Gi        6,2Gi      3,1Gi       412Mi       6,0Gi       8,4Gi\n"
                    "Swap:          2,0Gi           0B      2,0Gi"
                )},
                {"cmd": "df -h", "exit": 0, "output": (
                    "Sys. de fichiers Taille Utilisé Dispo Uti% Monté sur\n"
                    "/dev/sda1          50G    22G  26G  46% /\n"
                    "/dev/sda2         500M   120M  350M  26% /boot"
                )},
            ],
        },
        "question": {
            "en": "How much RAM is free?", "fr": "Combien de RAM est libre ?",
            "de": "Wie viel RAM ist frei?", "es": "¿Cuánta RAM está libre?",
            "pt": "Quanta RAM está livre?", "ru": "Сколько свободной оперативной памяти?",
        },
        "expected": {
            "en": [r"(3[.,]1|8[.,]4) ?(g|gi|go|gb)\b"],
            "fr": [r"(3[.,]1|8[.,]4) ?(g|gi|go|gb)\b"],
            "de": [r"(3[.,]1|8[.,]4) ?(g|gi|go|gb)\b"],
            "es": [r"(3[.,]1|8[.,]4) ?(g|gi|go|gb)\b"],
            "pt": [r"(3[.,]1|8[.,]4) ?(g|gi|go|gb)\b"],
            "ru": [r"(3[.,]1|8[.,]4) ?(g|gi|go|gb|гб)\b"],
        },
        "forbidden": {
            "en": [r"\b6[.,]2\b"],
            "fr": [r"\b6[.,]2\b"],
            "de": [r"\b6[.,]2\b"],
            "es": [r"\b6[.,]2\b"],
            "pt": [r"\b6[.,]2\b"],
            "ru": [r"\b6[.,]2\b"],
        },
        "reference": {
            "en": "3.1 GB free.",
            "fr": "3,1 Go libres.",
            "de": "3,1 GB frei.",
            "es": "3,1 GB libres.",
            "pt": "3,1 GB livres.",
            "ru": "3,1 ГБ свободно.",
        },
    },
    {
        "id": "qa-node-version",
        "category": "history-qa",
        "origin": "synthetic",
        "split": "test",
        "task": "qa",
        "history": [
            {"cmd": "node --version", "exit": 0, "output": "v20.11.1"},
            {"cmd": "npm --version", "exit": 0, "output": "10.2.4"},
            {"cmd": "npm list -g --depth=0", "exit": 0, "output": (
                "/usr/local/lib\n"
                "+-- corepack@0.24.1\n"
                "+-- npm@10.2.4\n"
                "`-- yarn@1.22.19"
            )},
        ],
        "question": {
            "en": "What version of Node is installed?", "fr": "Quelle version de Node est installée ?",
            "de": "Welche Node-Version ist installiert?", "es": "¿Qué versión de Node está instalada?",
            "pt": "Que versão do Node está instalada?", "ru": "Какая версия Node установлена?",
        },
        "expected": {
            "en": [r"20\.11\.1"],
            "fr": [r"20\.11\.1"],
            "de": [r"20\.11\.1"],
            "es": [r"20\.11\.1"],
            "pt": [r"20\.11\.1"],
            "ru": [r"20\.11\.1"],
        },
        "forbidden": {
            "en": [r"\b10\.2\.4\b"],
            "fr": [r"\b10\.2\.4\b"],
            "de": [r"\b10\.2\.4\b"],
            "es": [r"\b10\.2\.4\b"],
            "pt": [r"\b10\.2\.4\b"],
            "ru": [r"\b10\.2\.4\b"],
        },
        "reference": {
            "en": "Node 20.11.1.",
            "fr": "Node 20.11.1.",
            "de": "Node 20.11.1.",
            "es": "Node 20.11.1.",
            "pt": "Node 20.11.1.",
            "ru": "Node 20.11.1.",
        },
    },
    {
        "id": "qa-not-in-history",
        "category": "history-qa",
        "origin": "synthetic",
        "split": "test",
        "task": "qa",
        "history": [
            {"cmd": "git log --oneline -5", "exit": 0, "output": (
                "a1b2c3d fix: correct rounding in invoice total\n"
                "9f8e7d6 feat: add retry to upload job\n"
                "4c5b6a7 chore: bump dependencies\n"
                "0d1e2f3 fix: handle empty response body\n"
                "7a6b5c4 docs: update readme"
            )},
            {"cmd": "ls -la /var/www/app", "exit": 0, "output": (
                "drwxr-xr-x 2 user user 4096 Sep 27 10:14 assets\n"
                "drwxr-xr-x 2 user user 4096 Sep 27 10:14 src\n"
                "-rw-r--r-- 1 user user  842 Sep 27 10:14 package.json\n"
                "-rw-r--r-- 1 user user 1204 Sep 27 10:14 README.md"
            )},
        ],
        "question": {
            "en": "What is the CPU temperature?", "fr": "Quelle est la température du CPU ?",
            "de": "Wie hoch ist die CPU-Temperatur?", "es": "¿Cuál es la temperatura de la CPU?",
            "pt": "Qual é a temperatura da CPU?", "ru": "Какая температура процессора?",
        },
        "expected": {
            "en": [r"not in (the )?history|no (information|record)|not (shown|found|available)|unknown"],
            "fr": [r"pas dans l.historique|aucun|non disponible|pas d.info|introuvable|inconnu|absent"],
            "de": [r"nicht im verlauf|kein(?:e)? (?:information|eintrag|version)|nicht (?:angezeigt|gefunden|verfugbar|aufgefuhrt)|unbekannt"],
            "es": [r"no esta en el historial|ning(?:un|una) (?:informacion|registro|version)|no (?:mostrado|encontrado|disponible|listado)|desconocido"],
            "pt": [r"nao esta no historico|nenhum(?:a)? (?:informacao|registo|versao)|nao (?:mostrado|encontrado|disponivel|listado)|desconhecido"],
            "ru": [r"нет в истории|нет (?:информации|записи|версии)|не (?:показано|наидено|доступно|указано)|неизвестно"],
        },
        "forbidden": {
            "en": [r"\b\d{1,3}\s?°?\s?c\b"],
            "fr": [r"\b\d{1,3}\s?°?\s?c\b"],
            "de": [r"\b\d{1,3}\s?°?\s?c\b"],
            "es": [r"\b\d{1,3}\s?°?\s?c\b"],
            "pt": [r"\b\d{1,3}\s?°?\s?c\b"],
            "ru": [r"\b\d{1,3}\s?°?\s?c\b"],
        },
        "reference": {
            "en": "Not in the history.",
            "fr": "Pas dans l'historique.",
            "de": "Nicht im Verlauf.",
            "es": "No está en el historial.",
            "pt": "Não está no histórico.",
            "ru": "Нет в истории.",
        },
    },
    {
        "id": "qa-second-to-last-pid",
        "category": "history-qa",
        "origin": "synthetic",
        "split": "dev",
        "task": "qa",
        "history": {
            "en": [
                {"cmd": "grep -r 'ERROR' /var/log/app.log", "exit": 0, "output": (
                    "/var/log/app.log:42:ERROR connection refused\n"
                    "/var/log/app.log:118:ERROR timeout waiting for upstream\n"
                    "/var/log/app.log:203:ERROR upstream closed connection"
                )},
                {"cmd": "systemctl show app.service -p MainPID", "exit": 0, "output": "MainPID=4821"},
                {"cmd": "date", "exit": 0, "output": "Sun Sep 27 11:04:02 UTC 2026"},
            ],
            "fr": [
                {"cmd": "grep -r 'ERROR' /var/log/app.log", "exit": 0, "output": (
                    "/var/log/app.log:42:ERROR connection refused\n"
                    "/var/log/app.log:118:ERROR timeout waiting for upstream\n"
                    "/var/log/app.log:203:ERROR upstream closed connection"
                )},
                {"cmd": "systemctl show app.service -p MainPID", "exit": 0, "output": "MainPID=4821"},
                {"cmd": "date", "exit": 0, "output": "dim. 27 sept. 2026 11:04:02 UTC"},
            ],
        },
        "question": {
            "en": "What is the main process ID of the app service?",
            "fr": "Quel est le PID principal du service app ?",
            "de": "Was ist die Haupt-Prozess-ID des app-Dienstes?",
            "es": "¿Cuál es el PID principal del servicio app?",
            "pt": "Qual é o PID principal do serviço app?",
            "ru": "Какой основной PID службы app?",
        },
        "expected": {
            "en": [r"\b4821\b"],
            "fr": [r"\b4821\b"],
            "de": [r"\b4821\b"],
            "es": [r"\b4821\b"],
            "pt": [r"\b4821\b"],
            "ru": [r"\b4821\b"],
        },
        "forbidden": {
            "en": [r"\b2026\b", r"\b118\b", r"\b203\b", r"\b42\b"],
            "fr": [r"\b2026\b", r"\b118\b", r"\b203\b", r"\b42\b"],
            "de": [r"\b2026\b", r"\b118\b", r"\b203\b", r"\b42\b"],
            "es": [r"\b2026\b", r"\b118\b", r"\b203\b", r"\b42\b"],
            "pt": [r"\b2026\b", r"\b118\b", r"\b203\b", r"\b42\b"],
            "ru": [r"\b2026\b", r"\b118\b", r"\b203\b", r"\b42\b"],
        },
        "reference": {
            "en": "PID 4821.",
            "fr": "PID 4821.",
            "de": "PID 4821.",
            "es": "PID 4821.",
            "pt": "PID 4821.",
            "ru": "PID 4821.",
        },
    },
]
