"""Synthetic container-tooling and long-listing cases for Steph Speak Bench.

Docker, podman and kubectl output stays English in both languages (these tools do not
localize); systemd does, so systemctl output is given as a genuine en/fr pair. Repetitive
filler lines use a fixed random.Random(seed) so the module stays deterministic.

SPDX-License-Identifier: MIT
"""

from __future__ import annotations

import datetime as dt
import random


def synth(**case) -> dict:
    return {"origin": "synthetic", "split": "test", "task": "summary", "forbidden": [], **case}


PS_USERS = ["root", "user", "www-data", "postgres", "redis", "syslog", "messagebus"]
PS_COMMANDS = [
    "/usr/lib/systemd/systemd-journald", "/usr/sbin/sshd -D", "nginx: worker process",
    "postgres: writer process", "redis-server *:6379", "/usr/bin/containerd",
    "python3 worker.py", "/usr/lib/udisks2/udisksd", "dockerd -H unix://",
    "/usr/bin/dbus-daemon --system", "sshd: user@pts/0", "bash", "vim notes.txt",
    "/usr/lib/snapd/snapd", "cron", "rsyslogd", "/usr/lib/policykit-1/polkitd",
    "node app.js", "gunicorn: worker", "java -jar service.jar",
]
PS_HEADER = "USER         PID  %CPU %MEM    VSZ   RSS TTY      STAT START   TIME COMMAND"
PS_TOP = "user       18422  87.3  4.2  812340 172304 ?        Rl   09:14  12:47 /usr/bin/backup-agent --full"


def _ps_aux_lines(seed: int, n: int) -> list:
    rng = random.Random(seed)
    lines, cpu = [], 14.8
    for _ in range(n):
        cpu = max(0.0, cpu - rng.uniform(0.2, 0.7))
        user, pid = rng.choice(PS_USERS), rng.randint(200, 32000)
        mem, vsz, rss = round(rng.uniform(0.1, 3.5), 1), rng.randint(10000, 900000), rng.randint(2000, 200000)
        stat = rng.choice(["S", "Sl", "Ss", "S+", "R"])
        start = f"{rng.randint(0, 23):02d}:{rng.randint(0, 59):02d}"
        elapsed = f"{rng.randint(0, 9)}:{rng.randint(0, 59):02d}"
        cmd = rng.choice(PS_COMMANDS)
        lines.append(f"{user:<12} {pid:>5} {cpu:>5.1f} {mem:>4.1f} {vsz:>7} {rss:>6} ?        "
                     f"{stat:<4} {start}   {elapsed} {cmd}")
    return lines


def _ps_aux_output() -> str:
    return "\n".join([PS_HEADER, PS_TOP] + _ps_aux_lines(20260601, 34))


SERVICE_NAMES = [
    "accounts-daemon", "avahi-daemon", "bluetooth", "chronyd", "colord", "cron",
    "cups", "dbus", "docker", "fail2ban", "gdm", "irqbalance", "kmod-static-nodes",
    "logrotate", "networkd-dispatcher", "nginx", "ntp", "polkit", "postfix",
    "postgresql", "redis-server", "rsyslog", "snapd", "ssh", "systemd-journald",
    "systemd-logind", "systemd-networkd", "systemd-resolved", "systemd-timesyncd",
    "systemd-udevd", "thermald", "udisks2", "unattended-upgrades", "upower",
    "wpa-supplicant",
]
TOTAL_UNITS = len(SERVICE_NAMES) + 1  # + the always-failed backup-sync entry


def _systemctl_units(lang: str, seed: int) -> str:
    rng = random.Random(seed)
    names = list(SERVICE_NAMES)
    rng.shuffle(names)
    fr = lang == "fr"
    header = ("UNIT                          CHARGÉ  ACTIF    SOUS                   DESCRIPTION" if fr else
              "UNIT                          LOAD   ACTIVE   SUB                    DESCRIPTION")
    running = "en cours d'exécution" if fr else "running"
    rows = [f"{name + '.service':<30}{'chargé ' if fr else 'loaded '} {'actif  ' if fr else 'active '} "
            f"{running:<22}{name.replace('-', ' ').title()} service" for name in names]
    rows.append(f"{'backup-sync.service':<30}{'chargé ' if fr else 'loaded '} "
                f"{'échoué ' if fr else 'failed '} {'échoué' if fr else 'failed':<22}Nightly backup synchronization")
    if fr:
        legend = ["", "CHARGÉ = Indique si la définition de l'unité a été correctement chargée.",
                  "ACTIF  = État d'activation de haut niveau, généralisation de SOUS.",
                  "SOUS   = État d'activation de bas niveau ; dépend du type d'unité.", "",
                  f"{TOTAL_UNITS} unités chargées énumérées."]
    else:
        legend = ["", "LOAD   = Reflects whether the unit definition was properly loaded.",
                  "ACTIVE = The high-level unit activation state.",
                  "SUB    = The low-level unit activation state.", "",
                  f"{TOTAL_UNITS} loaded units listed."]
    return "\n".join([header] + rows + legend)


PIP_PACKAGES = [
    "aiohttp", "alembic", "anyio", "attrs", "babel", "beautifulsoup4", "black",
    "boto3", "botocore", "cachetools", "certifi", "cffi", "charset-normalizer",
    "click", "colorama", "coverage", "cryptography", "cycler", "dataclasses-json",
    "Deprecated", "distlib", "Django", "docutils", "exceptiongroup", "fastapi",
    "filelock", "Flask", "fonttools", "frozenlist", "fsspec", "gitdb", "GitPython",
    "greenlet", "gunicorn", "h11", "httpcore", "httpx", "idna", "importlib-metadata",
    "iniconfig", "isort", "itsdangerous", "Jinja2", "jmespath", "joblib", "jsonschema",
    "kiwisolver", "markdown-it-py", "MarkupSafe", "matplotlib", "mccabe", "mdurl",
    "multidict", "mypy-extensions", "numpy", "oauthlib", "packaging", "pandas",
    "pathspec", "pillow", "platformdirs", "pluggy", "prompt-toolkit", "protobuf",
    "psycopg2-binary", "pyarrow", "pyasn1", "pycparser", "pydantic", "pydantic-core",
    "Pygments", "PyJWT", "pyparsing", "pytest", "python-dateutil", "python-dotenv",
    "pytz", "PyYAML", "redis", "regex", "requests", "requests-oauthlib", "rich",
    "rsa", "s3transfer", "scikit-learn", "scipy", "setuptools", "six", "smmap",
    "sniffio", "SQLAlchemy", "sqlparse", "starlette", "tenacity", "threadpoolctl",
    "tomli", "tqdm", "typing-extensions", "tzdata", "urllib3", "uvicorn", "virtualenv",
    "wcwidth", "websockets", "Werkzeug", "wrapt", "yarl", "zipp",
]


def _pip_list_output(seed: int) -> str:
    rng = random.Random(seed)
    lines = ["Package                  Version", "------------------------ -------"]
    for name in sorted(PIP_PACKAGES, key=str.lower):
        ver = f"{rng.randint(0, 4)}.{rng.randint(0, 30)}.{rng.randint(0, 20)}"
        lines.append(f"{name:<24} {ver}")
    return "\n".join(lines)


LS_BIGDIR_COUNT = 95


def _ls_bigdir_output(n: int) -> str:
    start = dt.date(2026, 1, 1)
    return "\n".join(f"backup-{(start + dt.timedelta(days=i)).isoformat()}.tar.gz" for i in range(n))


CASES = [
    # ---------------------------------------------------------------- containers
    synth(id="ctr-build-run-step", category="containers",
          cmd="docker build -t webapp:latest .", exit=1, duration=9.1,
          output="\n".join([
              "#1 [internal] load build definition from Dockerfile",
              "#1 transferring dockerfile: 356B done",
              "#1 DONE 0.0s",
              "#2 [internal] load metadata for docker.io/library/node:20-slim",
              "#2 DONE 0.4s",
              "#3 [internal] load .dockerignore",
              "#3 transferring context: 90B done",
              "#3 DONE 0.0s",
              "#4 [1/8] FROM docker.io/library/node:20-slim@sha256:9f2a1c8b7d4e",
              "#4 DONE 0.0s",
              "#5 [internal] load build context",
              "#5 transferring context: 128.4kB done",
              "#5 DONE 0.1s",
              "#6 [2/8] WORKDIR /app",
              "#6 CACHED",
              "#7 [3/8] COPY package.json package-lock.json ./",
              "#7 CACHED",
              "#8 [4/8] RUN npm ci",
              "#8 CACHED",
              "#9 [5/8] COPY . .",
              "#9 DONE 0.3s",
              "#10 [6/8] RUN npm run test",
              "#10 0.9 > webapp@1.4.0 test",
              "#10 0.9 > jest --ci",
              "#10 7.8 Tests:       1 failed, 42 passed, 43 total",
              "#10 7.8 npm ERR! Test failed.  See above for more details.",
              "#10 ERROR: process \"/bin/sh -c npm run test\" did not complete successfully: exit code 1",
              "------",
              " > [6/8] RUN npm run test:",
              "7.800 Tests:       1 failed, 42 passed, 43 total",
              "7.801 npm ERR! Test failed.  See above for more details.",
              "------",
              "Dockerfile:14",
              "--------------------",
              "  12 |     COPY . .",
              "  13 |     ",
              "  14 | >>> RUN npm run test",
              "  15 |     ",
              "--------------------",
              "ERROR: failed to solve: process \"/bin/sh -c npm run test\" did not complete successfully: exit code 1",
          ]),
          expected={"en": [r"fail|error", r"dockerfile", r"\b14\b", r"\b6\b"],
                    "fr": [r"echec|erreur", r"dockerfile", r"\b14\b", r"\b6\b"],
                    "de": [r"fehlgeschlagen|fehler", r"dockerfile", r"\b14\b", r"\b6\b"],
                    "es": [r"fallo|error", r"dockerfile", r"\b14\b", r"\b6\b"],
                    "pt": [r"falhou|erro|falha", r"dockerfile", r"\b14\b", r"\b6\b"],
                    "ru": [r"ошибк", r"dockerfile", r"\b14\b", r"\b6\b"]},
          forbidden=[r"\b5/8\b", r"\b7/8\b", r"line 12|ligne 12"],
          reference={"en": "Failed. Dockerfile line 14, step 6 of 8, npm test, exit code 1.",
                     "fr": "Échec. Dockerfile ligne 14, étape 6 sur 8, npm test, code de sortie 1.",
                     "de": "Fehlgeschlagen. Dockerfile Zeile 14, Schritt 6 von 8, npm test, Exit-Code 1.",
                     "es": "Fallo. Dockerfile línea 14, paso 6 de 8, npm test, código de salida 1.",
                     "pt": "Falhou. Dockerfile linha 14, passo 6 de 8, npm test, código de saída 1.",
                     "ru": "Ошибка. Dockerfile строка 14, шаг 6 из 8, npm test, код выхода 1."}),

    synth(id="ctr-compose-unhealthy", category="containers",
          cmd="docker compose up -d", exit=1, duration=20.5,
          output="\n".join([
              "[+] Running 4/5",
              " ✔ Network app_default        Created                                    0.1s",
              " ✔ Container app-db-1          Healthy                                    5.2s",
              " ✔ Container app-redis-1       Started                                    0.4s",
              " ⚿ Container app-api-1         Waiting                                   20.3s",
              " ✔ Container app-worker-1      Started                                    0.5s",
              "dependency failed to start: container app-api-1 is unhealthy",
          ]),
          expected={"en": [r"fail|error", r"api", r"unhealthy"],
                    "fr": [r"echec|erreur", r"api", r"malsain|unhealthy|non sain|mauvaise sante|defaillant"],
                    "de": [r"fehlgeschlagen|fehler", r"api", r"unhealthy|ungesund|fehlerhaft"],
                    "es": [r"fallo|error", r"api", r"unhealthy|no saludable|insalubre|defectuoso"],
                    "pt": [r"falhou|erro|falha", r"api", r"unhealthy|nao saudavel|insalubre|defeituoso"],
                    "ru": [r"ошибк", r"api", r"unhealthy|нездоров|неисправ"]},
          forbidden=[r"worker.{0,15}(unhealthy|fail)", r"redis.{0,15}(unhealthy|fail)"],
          reference={"en": "Failed. app-api-1 unhealthy, dependency did not start.",
                     "fr": "Échec. app-api-1 malsain, dépendance non démarrée.",
                     "de": "Fehlgeschlagen. app-api-1 ungesund, Abhängigkeit nicht gestartet.",
                     "es": "Fallo. app-api-1 no saludable, dependencia no inició.",
                     "pt": "Falhou. app-api-1 não saudável, dependência não iniciou.",
                     "ru": "Ошибка. app-api-1 нездоров, зависимость не запустилась."}),

    synth(id="ctr-crashloop", category="containers",
          cmd="kubectl get pods -n default", exit=0, duration=0.3,
          output="\n".join([
              "NAME                          READY   STATUS             RESTARTS      AGE",
              "web-7f8b9c6d4-2xk9p           1/1     Running            0             3d",
              "web-7f8b9c6d4-9mnwq           1/1     Running            0             3d",
              "worker-5d8f7b9c6-ktqvz        0/1     CrashLoopBackOff   14 (2m ago)   47m",
              "redis-6b9c7d8f5-p2xrt         1/1     Running            0             12d",
              "scheduler-84c6f9b7d-z8kjn     1/1     Running            0             12d",
          ]),
          expected={"en": [r"crashloopbackoff|crash.{0,3}loop", r"worker", r"\b14\b"],
                    "fr": [r"crashloopbackoff|crash.{0,3}loop", r"worker", r"\b14\b"],
                    "de": [r"crashloopbackoff|crash.{0,3}loop", r"worker", r"\b14\b"],
                    "es": [r"crashloopbackoff|crash.{0,3}loop", r"worker", r"\b14\b"],
                    "pt": [r"crashloopbackoff|crash.{0,3}loop", r"worker", r"\b14\b"],
                    "ru": [r"crashloopbackoff|crash.{0,3}loop", r"worker", r"\b14\b"]},
          forbidden=[r"\bweb\b.{0,20}crash", r"redis.{0,20}crash", r"\b47\b"],
          reference={"en": "worker pod CrashLoopBackOff, 14 restarts.",
                     "fr": "worker en CrashLoopBackOff, 14 redémarrages.",
                     "de": "worker pod CrashLoopBackOff, 14 Neustarts.",
                     "es": "pod worker en CrashLoopBackOff, 14 reinicios.",
                     "pt": "pod worker em CrashLoopBackOff, 14 reinícios.",
                     "ru": "под worker в CrashLoopBackOff, 14 перезапусков."}),

    synth(id="ctr-images", category="containers",
          cmd="docker images", exit=0, duration=0.2,
          output="\n".join([
              "REPOSITORY          TAG       IMAGE ID       CREATED         SIZE",
              "webapp              latest    3f2a91c8b7d4   2 hours ago     412MB",
              "webapp              v1.3.0    9d1b7e2f5a6c   3 days ago      408MB",
              "postgres            15        6c8a2f9d1e3b   2 weeks ago     379MB",
              "redis               7-alpine  1a4f7c9b2d6e   3 weeks ago     41.2MB",
              "node                20-slim   8b3e6f1a9c7d   5 weeks ago     198MB",
              "<none>              <none>    2f9c1a8b3e6d   2 months ago    120MB",
          ]),
          expected={"en": [r"webapp", r"412", r"postgres|redis|node"],
                    "fr": [r"webapp", r"412", r"postgres|redis|node"],
                    "de": [r"webapp", r"412", r"postgres|redis|node"],
                    "es": [r"webapp", r"412", r"postgres|redis|node"],
                    "pt": [r"webapp", r"412", r"postgres|redis|node"],
                    "ru": [r"webapp", r"412", r"postgres|redis|node"]},
          forbidden=[r"\b7 images\b", r"\b5 images\b", r"postgres.{0,20}(largest|biggest|plus gros|plus grande)"],
          reference={"en": "webapp latest, 412 megabytes; also postgres, redis, node.",
                     "fr": "webapp latest, 412 méga-octets ; aussi postgres, redis, node.",
                     "de": "webapp latest, 412 Megabyte; außerdem postgres, redis, node.",
                     "es": "webapp latest, 412 megabytes; también postgres, redis, node.",
                     "pt": "webapp latest, 412 megabytes; também postgres, redis, node.",
                     "ru": "webapp latest, 412 мегабайт; также postgres, redis, node."}),

    synth(id="ctr-podman-ps-exited", category="containers", split="dev",
          cmd="podman ps -a", exit=0, duration=0.1,
          output="\n".join([
              "CONTAINER ID  IMAGE                          COMMAND                CREATED         STATUS                      PORTS       NAMES",
              "a1b2c3d4e5f6  docker.io/library/nginx:1.25  \"nginx -g 'daemon of\"  2 hours ago     Up 2 hours                  80/tcp      web",
              "b2c3d4e5f6a7  docker.io/library/redis:7     \"redis-server\"         2 hours ago     Up 2 hours                  6379/tcp    cache",
              "c3d4e5f6a7b8  localhost/app:latest          \"python app.py\"        1 hour ago      Exited (1) 45 minutes ago               worker",
              "d4e5f6a7b8c9  localhost/app:latest          \"python app.py\"        50 minutes ago  Exited (1) 12 minutes ago               worker-retry",
              "e5f6a7b8c9d0  docker.io/library/postgres:15 \"docker-entrypoint.s\"  3 hours ago     Up 3 hours                  5432/tcp    db",
          ]),
          expected={"en": [r"exited|exit", r"\b2\b", r"worker"],
                    "fr": [r"exite|arret|sortie", r"\b2\b", r"worker"],
                    "de": [r"beendet|exit", r"\b2\b", r"worker"],
                    "es": [r"sali|exit", r"\b2\b", r"worker"],
                    "pt": [r"sai|exit", r"\b2\b", r"worker"],
                    "ru": [r"вышел|заверш|exit", r"\b2\b", r"worker"]},
          forbidden=[r"\b5 exited\b", r"\bweb\b.{0,20}exit", r"\bdb\b.{0,20}exit"],
          reference={"en": "2 containers exited, worker and worker-retry, exit code 1.",
                     "fr": "2 conteneurs arrêtés, worker et worker-retry, code de sortie 1.",
                     "de": "2 Container beendet, worker und worker-retry, Exit-Code 1.",
                     "es": "2 contenedores salieron, worker y worker-retry, código de salida 1.",
                     "pt": "2 contentores saíram, worker e worker-retry, código de saída 1.",
                     "ru": "2 контейнера завершились, worker и worker-retry, код выхода 1."}),

    synth(id="ctr-logs-crash", category="containers",
          cmd="docker logs webapp-api-1", exit=0, duration=0.05,
          output="\n".join([
              "> api@2.1.0 start",
              "> node server.js",
              "",
              "Server listening on port 3000",
              "[info] connected to database",
              "[info] connected to redis",
              "/app/server.js:88",
              "    throw new Error(`Missing env var: ${key}`);",
              "    ^",
              "",
              "Error: Missing env var: PAYMENT_SECRET_KEY",
              "    at loadConfig (/app/server.js:88:11)",
              "    at Object.<anonymous> (/app/server.js:12:1)",
              "    at Module._compile (node:internal/modules/cjs/loader:1254:14)",
              "    at Module.load (node:internal/modules/cjs/loader:1117:32)",
              "    at Module._load (node:internal/modules/cjs/loader:958:12)",
              "Node.js v20.11.0",
          ]),
          expected={"en": [r"fail|error|crash", r"server\.js", r"\b88\b", r"payment_secret_key|env var|missing"],
                    "fr": [r"echec|erreur|echoue|plante", r"server\.js", r"\b88\b",
                           r"payment_secret_key|variable.{0,15}manquante|env var"],
                    "de": [r"fehlgeschlagen|fehler|abgesturzt|absturz", r"server\.js", r"\b88\b",
                           r"payment_secret_key|variable.{0,15}fehlt|env var"],
                    "es": [r"fallo|error|caida|se cayo", r"server\.js", r"\b88\b",
                           r"payment_secret_key|variable.{0,15}falta|env var"],
                    "pt": [r"falhou|erro|falha|caiu", r"server\.js", r"\b88\b",
                           r"payment_secret_key|variavel.{0,15}em falta|env var"],
                    "ru": [r"ошибк|сбо|упал", r"server\.js", r"\b88\b",
                           r"payment_secret_key|перемен.{0,15}отсутств|env var"]},
          forbidden=[r"\b12\b"],
          reference={"en": "server.js line 88, missing PAYMENT_SECRET_KEY, app crashed.",
                     "fr": "server.js ligne 88, variable PAYMENT_SECRET_KEY manquante, appli plantée.",
                     "de": "server.js Zeile 88, PAYMENT_SECRET_KEY fehlt, App abgestürzt.",
                     "es": "server.js línea 88, falta PAYMENT_SECRET_KEY, app caída.",
                     "pt": "server.js linha 88, falta PAYMENT_SECRET_KEY, app caiu.",
                     "ru": "server.js строка 88, отсутствует PAYMENT_SECRET_KEY, приложение упало."}),

    synth(id="ctr-system-df", category="containers", split="dev",
          cmd="docker system df", exit=0, duration=0.15,
          output="\n".join([
              "TYPE            TOTAL     ACTIVE    SIZE      RECLAIMABLE",
              "Images          14        6         3.8GB     2.1GB (55%)",
              "Containers      6         2         412MB     380MB (92%)",
              "Local Volumes   9         3         1.7GB     1.2GB (70%)",
              "Build Cache     52        0         890MB     890MB (100%)",
          ]),
          expected={"en": [r"3[.,]8 ?gb|3[.,]8 ?go", r"2[.,]1 ?gb|2[.,]1 ?go", r"890 ?mb|890 ?mo|100 ?%"],
                    "fr": [r"3[.,]8 ?go|3[.,]8 ?gb", r"2[.,]1 ?go|2[.,]1 ?gb", r"890 ?mo|890 ?mb|100 ?%"],
                    "de": [r"3[.,]8 ?gb", r"2[.,]1 ?gb", r"890 ?mb|100 ?%"],
                    "es": [r"3[.,]8 ?gb", r"2[.,]1 ?gb", r"890 ?mb|100 ?%"],
                    "pt": [r"3[.,]8 ?gb", r"2[.,]1 ?gb", r"890 ?mb|100 ?%"],
                    "ru": [r"3[.,]8 ?gb", r"2[.,]1 ?gb", r"890 ?mb|100 ?%"]},
          forbidden=[r"images.{0,15}70 ?%", r"volumes.{0,15}55 ?%"],
          reference={"en": "Images 3.8 GB, 2.1 GB reclaimable; build cache 890 MB, fully reclaimable.",
                     "fr": "Images 3,8 Go, 2,1 Go récupérables ; cache de build 890 Mo, entièrement récupérable.",
                     "de": "Images 3,8 GB, 2,1 GB rückgewinnbar; Build-Cache 890 MB, vollständig rückgewinnbar.",
                     "es": "Imágenes 3,8 GB, 2,1 GB recuperables; caché de compilación 890 MB, totalmente recuperable.",
                     "pt": "Imagens 3,8 GB, 2,1 GB recuperáveis; cache de compilação 890 MB, totalmente recuperável.",
                     "ru": "Образы 3,8 GB, 2,1 GB можно освободить; кэш сборки 890 MB, полностью можно освободить."}),

    # ---------------------------------------------------------------- long-lists
    synth(id="list-ps-cpu", category="long-lists",
          cmd="ps aux --sort=-%cpu", exit=0, duration=0.1,
          output=_ps_aux_output(),
          expected={"en": [r"backup-agent", r"87[.,]3"],
                    "fr": [r"backup-agent", r"87[.,]3"],
                    "de": [r"backup-agent", r"87[.,]3"],
                    "es": [r"backup-agent", r"87[.,]3"],
                    "pt": [r"backup-agent", r"87[.,]3"],
                    "ru": [r"backup-agent", r"87[.,]3"]},
          forbidden=[r"\b100 ?%\b"],
          reference={"en": "backup-agent using 87.3% CPU, PID 18422.",
                     "fr": "backup-agent utilise 87,3 % CPU, PID 18422.",
                     "de": "backup-agent nutzt 87,3 % CPU, PID 18422.",
                     "es": "backup-agent usa 87,3 % CPU, PID 18422.",
                     "pt": "backup-agent usa 87,3 % CPU, PID 18422.",
                     "ru": "backup-agent использует 87,3 % CPU, PID 18422."}),

    synth(id="list-systemctl-units", category="long-lists",
          cmd="systemctl list-units --type=service --all", exit=0, duration=0.1,
          output={"en": _systemctl_units("en", 20260602), "fr": _systemctl_units("fr", 20260602)},
          expected={"en": [rf"\b{TOTAL_UNITS}\b", r"backup-sync|failed"],
                    "fr": [rf"\b{TOTAL_UNITS}\b", r"backup-sync|echoue"],
                    "de": [rf"\b{TOTAL_UNITS}\b", r"backup-sync|fehlgeschlagen"],
                    "es": [rf"\b{TOTAL_UNITS}\b", r"backup-sync|fallo|fallido"],
                    "pt": [rf"\b{TOTAL_UNITS}\b", r"backup-sync|falhou|falha"],
                    "ru": [rf"\b{TOTAL_UNITS}\b", r"backup-sync|ошибк"]},
          forbidden=[r"\b0 (failed|echoues?)\b"],
          reference={"en": f"{TOTAL_UNITS} services loaded, backup-sync failed.",
                     "fr": f"{TOTAL_UNITS} services chargés, backup-sync en échec.",
                     "de": f"{TOTAL_UNITS} Dienste geladen, backup-sync fehlgeschlagen.",
                     "es": f"{TOTAL_UNITS} servicios cargados, backup-sync con fallo.",
                     "pt": f"{TOTAL_UNITS} serviços carregados, backup-sync falhou.",
                     "ru": f"{TOTAL_UNITS} служб загружено, backup-sync завершился с ошибкой."}),

    synth(id="list-pip-list", category="long-lists",
          cmd="pip list", exit=0, duration=0.4,
          output=_pip_list_output(20260603),
          expected={"en": [r"aiohttp", r"alembic"], "fr": [r"aiohttp", r"alembic"],
                    "de": [r"aiohttp", r"alembic"], "es": [r"aiohttp", r"alembic"],
                    "pt": [r"aiohttp", r"alembic"], "ru": [r"aiohttp", r"alembic"]},
          forbidden=[r"\b100 (packages|paquets)\b"],
          reference={"en": "Packages installed, including aiohttp, alembic.",
                     "fr": "Paquets installés, dont aiohttp, alembic.",
                     "de": "Pakete installiert, darunter aiohttp, alembic.",
                     "es": "Paquetes instalados, incluyendo aiohttp, alembic.",
                     "pt": "Pacotes instalados, incluindo aiohttp, alembic.",
                     "ru": "Пакеты установлены, включая aiohttp, alembic."}),

    synth(id="list-ls-bigdir", category="long-lists",
          cmd="ls -1 /var/backups/app", exit=0, duration=0.05,
          output=_ls_bigdir_output(LS_BIGDIR_COUNT),
          expected={"en": [rf"\b{LS_BIGDIR_COUNT}\b", r"backup-2026-01-01"],
                    "fr": [rf"\b{LS_BIGDIR_COUNT}\b", r"backup-2026-01-01"],
                    "de": [rf"\b{LS_BIGDIR_COUNT}\b", r"backup-2026-01-01"],
                    "es": [rf"\b{LS_BIGDIR_COUNT}\b", r"backup-2026-01-01"],
                    "pt": [rf"\b{LS_BIGDIR_COUNT}\b", r"backup-2026-01-01"],
                    "ru": [rf"\b{LS_BIGDIR_COUNT}\b", r"backup-2026-01-01"]},
          forbidden=[r"\bjpg\b|\bpng\b", r"\b100\b"],
          notes="ls -1 prints no count line; the model sees the total in the input header (nlines).",
          reference={"en": f"{LS_BIGDIR_COUNT} files, including backup-2026-01-01.tar.gz.",
                     "fr": f"{LS_BIGDIR_COUNT} fichiers, dont backup-2026-01-01.tar.gz.",
                     "de": f"{LS_BIGDIR_COUNT} Dateien, darunter backup-2026-01-01.tar.gz.",
                     "es": f"{LS_BIGDIR_COUNT} archivos, incluyendo backup-2026-01-01.tar.gz.",
                     "pt": f"{LS_BIGDIR_COUNT} ficheiros, incluindo backup-2026-01-01.tar.gz.",
                     "ru": f"{LS_BIGDIR_COUNT} файлов, включая backup-2026-01-01.tar.gz."}),
]
