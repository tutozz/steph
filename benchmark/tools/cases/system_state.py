"""Synthetic cases: network, disks, memory, hardware.

SPDX-License-Identifier: MIT
"""

CASES = [
    # ---------------------------------------------------------------- network
    {
        "id": "net-ping-unreachable",
        "category": "network",
        "origin": "synthetic",
        "split": "test",
        "task": "summary",
        "cmd": "ping -c 4 192.168.1.50",
        "exit": 1,
        "duration": 3.1,
        "output": {
            "en": (
                "PING 192.168.1.50 (192.168.1.50) 56(84) bytes of data.\n"
                "From 192.168.1.20 icmp_seq=1 Destination Host Unreachable\n"
                "From 192.168.1.20 icmp_seq=2 Destination Host Unreachable\n"
                "From 192.168.1.20 icmp_seq=3 Destination Host Unreachable\n"
                "From 192.168.1.20 icmp_seq=4 Destination Host Unreachable\n"
                "\n"
                "--- 192.168.1.50 ping statistics ---\n"
                "4 packets transmitted, 0 received, +4 errors, 100% packet loss, time 3062ms"
            ),
            "fr": (
                "PING 192.168.1.50 (192.168.1.50) 56(84) octets de données.\n"
                "De 192.168.1.20 icmp_seq=1 Hôte de destination injoignable\n"
                "De 192.168.1.20 icmp_seq=2 Hôte de destination injoignable\n"
                "De 192.168.1.20 icmp_seq=3 Hôte de destination injoignable\n"
                "De 192.168.1.20 icmp_seq=4 Hôte de destination injoignable\n"
                "\n"
                "--- statistiques ping de 192.168.1.50 ---\n"
                "4 paquets transmis, 0 reçus, +4 erreurs, 100% de paquets perdus, temps 3062ms"
            ),
        },
        "expected": {
            "en": [r"fail|error|could not|cannot|unable|unreachable|loss", r"unreachable", r"100 ?%"],
            "fr": [r"echec|erreur|impossible|injoignable|perte", r"injoignable|inaccessible|unreachable", r"100 ?%"],
            "de": [r"fehlgeschlagen|fehler|nicht erreichbar|unerreichbar|verlust", r"nicht erreichbar|unerreichbar", r"100 ?%"],
            "es": [r"fallo|error|inalcanzable|perdida", r"inalcanzable", r"100 ?%"],
            "pt": [r"falhou|erro|falha|inacessivel|perda", r"inacessivel", r"100 ?%"],
            "ru": [r"ошибк|недоступ|потер", r"недоступ", r"100 ?%"],
        },
        "forbidden": [r"127\.0\.0\.1", r"\blo0?\b", r"fe80", r"\b4 (received|recus)\b"],
        "reference": {
            "en": "Failed. Host unreachable, 100% packet loss.",
            "fr": "Échec. Hôte injoignable, 100% de paquets perdus.",
            "de": "Fehlgeschlagen. Host nicht erreichbar, 100% Paketverlust.",
            "es": "Fallo. Host inalcanzable, 100% de paquetes perdidos.",
            "pt": "Falhou. Host inacessível, 100% de pacotes perdidos.",
            "ru": "Ошибка. Хост недоступен, потеряно 100% пакетов.",
        },
    },
    {
        "id": "net-curl-tls-expired",
        "category": "network",
        "origin": "synthetic",
        "split": "test",
        "task": "summary",
        "cmd": "curl -v https://expired.example.com",
        "exit": 60,
        "duration": 0.4,
        "output": (
            "* Trying 203.0.113.10:443...\n"
            "* Connected to expired.example.com (203.0.113.10) port 443\n"
            "* ALPN: curl offers h2,http/1.1\n"
            "* TLSv1.3 (OUT), TLS handshake, Client hello (1):\n"
            "* TLSv1.3 (IN), TLS handshake, Server hello (2):\n"
            "* TLSv1.3 (IN), TLS handshake, Certificate (11):\n"
            "* TLSv1.3 (OUT), TLS alert, unknown CA (560):\n"
            "* SSL certificate problem: certificate has expired\n"
            "* Closing connection\n"
            "curl: (60) SSL certificate problem: certificate has expired"
        ),
        "expected": {
            "en": [r"fail|error|could not|cannot|unable", r"\bcert", r"expir"],
            "fr": [r"echec|erreur|impossible|echoue", r"\bcert", r"expir"],
            "de": [r"fehlgeschlagen|fehler", r"zertifikat", r"abgelaufen|expir"],
            "es": [r"fallo|error", r"certificado|\bcert", r"expir|caduc"],
            "pt": [r"falhou|erro|falha", r"certificado|\bcert", r"expir|caduc"],
            "ru": [r"ошибк", r"сертификат", r"истек|недеиствител"],
        },
        "forbidden": [r"refused", r"127\.0\.0\.1", r"fe80"],
        "reference": {
            "en": "Failed. Certificate expired.",
            "fr": "Échec. Certificat expiré.",
            "de": "Fehlgeschlagen. Zertifikat abgelaufen.",
            "es": "Fallo. Certificado expirado.",
            "pt": "Falhou. Certificado expirado.",
            "ru": "Ошибка. Сертификат истёк.",
        },
    },
    {
        "id": "net-dig-nxdomain",
        "category": "network",
        "origin": "synthetic",
        "split": "test",
        "task": "summary",
        "cmd": "dig missing-host.example.com",
        "exit": 0,
        "duration": 0.1,
        "output": (
            "; <<>> DiG 9.18.24-Debian <<>> missing-host.example.com\n"
            ";; global options: +cmd\n"
            ";; Got answer:\n"
            ";; ->>HEADER<<- opcode: QUERY, status: NXDOMAIN, id: 51234\n"
            ";; flags: qr rd ra; QUERY: 1, ANSWER: 0, AUTHORITY: 1, ADDITIONAL: 1\n"
            "\n"
            ";; QUESTION SECTION:\n"
            ";missing-host.example.com.\tIN\tA\n"
            "\n"
            ";; AUTHORITY SECTION:\n"
            "example.com.\t\t3600\tIN\tSOA\tns1.example.com. hostmaster.example.com. 2024031501 7200 3600 1209600 3600\n"
            "\n"
            ";; Query time: 24 msec\n"
            ";; SERVER: 192.168.1.1#53(192.168.1.1) (UDP)\n"
            ";; WHEN: Sun Sep 27 10:15:02 UTC 2026\n"
            ";; MSG SIZE  rcvd: 100"
        ),
        "expected": {
            "en": [r"fail|error|could not|cannot|unable", r"nxdomain|does not exist|non existent"],
            "fr": [r"echec|erreur|impossible|echoue", r"nxdomain|n.existe pas|inexistant"],
            "de": [r"fehlgeschlagen|fehler", r"nxdomain|existiert nicht|nicht gefunden"],
            "es": [r"fallo|error", r"nxdomain|no existe|inexistente"],
            "pt": [r"falhou|erro|falha", r"nxdomain|nao existe|inexistente"],
            "ru": [r"ошибк", r"nxdomain|не существует|не наиден"],
        },
        "forbidden": [r"127\.0\.0\.1", r"\blo0?\b", r"fe80"],
        "reference": {
            "en": "Failed. NXDOMAIN, domain not found.",
            "fr": "Échec. NXDOMAIN, domaine introuvable.",
            "de": "Fehlgeschlagen. NXDOMAIN, Domain nicht gefunden.",
            "es": "Fallo. NXDOMAIN, dominio no encontrado.",
            "pt": "Falhou. NXDOMAIN, domínio não encontrado.",
            "ru": "Ошибка. NXDOMAIN, домен не найден.",
        },
    },
    {
        "id": "net-ss-listening",
        "category": "network",
        "origin": "synthetic",
        "split": "test",
        "task": "summary",
        "cmd": "ss -tlnp",
        "exit": 0,
        "duration": 0.05,
        "output": (
            "State    Recv-Q   Send-Q     Local Address:Port      Peer Address:Port   Process\n"
            "LISTEN   0        128        127.0.0.1:3306          0.0.0.0:*           users:((\"mysqld\",pid=812,fd=23))\n"
            "LISTEN   0        511        0.0.0.0:80              0.0.0.0:*           users:((\"nginx\",pid=1190,fd=6))\n"
            "LISTEN   0        511        0.0.0.0:443             0.0.0.0:*           users:((\"nginx\",pid=1190,fd=8))\n"
            "LISTEN   0        128        127.0.0.1:6379          0.0.0.0:*           users:((\"redis-server\",pid=944,fd=6))\n"
            "LISTEN   0        4096       0.0.0.0:22              0.0.0.0:*           users:((\"sshd\",pid=701,fd=3))"
        ),
        "expected": {
            "en": [r"\bssh\b", r"\bhttp\b|\bnginx\b", r"mysql|redis"],
            "fr": [r"\bssh\b", r"\bhttp\b|\bnginx\b", r"mysql|redis"],
            "de": [r"\bssh\b", r"\bhttp\b|\bnginx\b", r"mysql|redis"],
            "es": [r"\bssh\b", r"\bhttp\b|\bnginx\b", r"mysql|redis"],
            "pt": [r"\bssh\b", r"\bhttp\b|\bnginx\b", r"mysql|redis"],
            "ru": [r"\bssh\b", r"\bhttp\b|\bnginx\b", r"mysql|redis"],
        },
        "forbidden": [r"127\.0\.0\.1", r"\blo0?\b", r"fe80"],
        "reference": {
            "en": "Listening: ssh, http, https and local mysql, redis.",
            "fr": "En écoute : ssh, http, https, et mysql, redis en local.",
            "de": "Aktiv: ssh, http, https, dazu lokal mysql, redis.",
            "es": "Escuchando: ssh, http, https y localmente mysql, redis.",
            "pt": "A escutar: ssh, http, https e localmente mysql, redis.",
            "ru": "Слушает: ssh, http, https, а также локально mysql, redis.",
        },
    },
    # ---------------------------------------------------------------- disks
    {
        "id": "disk-df-almost-full",
        "category": "disks",
        "origin": "synthetic",
        "split": "test",
        "task": "summary",
        "cmd": "df -h",
        "exit": 0,
        "duration": 0.02,
        "output": {
            "en": (
                "Filesystem      Size  Used Avail Use% Mounted on\n"
                "udev             7.8G     0  7.8G   0% /dev\n"
                "tmpfs            1.6G  1.2M  1.6G   1% /run\n"
                "/dev/sda1         49G   45G  1.6G  97% /\n"
                "tmpfs            7.8G     0  7.8G   0% /dev/shm\n"
                "tmpfs            5.0M     0  5.0M   0% /run/lock\n"
                "/dev/sdb1         20G   19G  456M  98% /var\n"
                "tmpfs            1.6G     0  1.6G   0% /run/user/1000"
            ),
            "fr": (
                "Sys. de fichiers Taille Utilisé Dispo Uti% Monté sur\n"
                "udev             7,8G     0  7,8G   0% /dev\n"
                "tmpfs            1,6G  1,2M  1,6G   1% /run\n"
                "/dev/sda1         49G   45G  1,6G  97% /\n"
                "tmpfs            7,8G     0  7,8G   0% /dev/shm\n"
                "tmpfs            5,0M     0  5,0M   0% /run/lock\n"
                "/dev/sdb1         20G   19G  456M  98% /var\n"
                "tmpfs            1,6G     0  1,6G   0% /run/user/1000"
            ),
        },
        "expected": {
            "en": [r"\bvar\b", r"\b98 ?%", r"\b456"],
            "fr": [r"\bvar\b", r"\b98 ?%", r"\b456"],
            "de": [r"\bvar\b", r"\b98 ?%", r"\b456"],
            "es": [r"\bvar\b", r"\b98 ?%", r"\b456"],
            "pt": [r"\bvar\b", r"\b98 ?%", r"\b456"],
            "ru": [r"\bvar\b", r"\b98 ?%", r"\b456"],
        },
        "forbidden": [r"tmpfs", r"overlay", r"devtmpfs", r"efivarfs"],
        "reference": {
            "en": "/var 98% full, 456M free.",
            "fr": "/var plein à 98 %, 456 Mo libres.",
            "de": "/var 98% voll, 456M frei.",
            "es": "/var lleno al 98%, 456M libres.",
            "pt": "/var cheio a 98%, 456M livres.",
            "ru": "/var заполнен на 98%, свободно 456M.",
        },
    },
    {
        "id": "disk-lsblk-3disks",
        "category": "disks",
        "origin": "synthetic",
        "split": "test",
        "task": "summary",
        "cmd": "lsblk",
        "exit": 0,
        "duration": 0.03,
        "output": (
            "NAME        MAJ:MIN RM   SIZE RO TYPE MOUNTPOINTS\n"
            "sda           8:0    0 465.8G  0 disk\n"
            "├─sda1        8:1    0   512M  0 part /boot/efi\n"
            "└─sda2        8:2    0 465.3G  0 part /\n"
            "sdb           8:16   0   1.8T  0 disk\n"
            "└─sdb1        8:17   0   1.8T  0 part /data\n"
            "nvme0n1     259:0    0 953.9G  0 disk\n"
            "├─nvme0n1p1 259:1    0   512M  0 part\n"
            "└─nvme0n1p2 259:2    0 953.4G  0 part /mnt/scratch"
        ),
        "expected": {
            "en": [r"\bsda\b", r"\bsdb\b", r"nvme0n1|nvme"],
            "fr": [r"\bsda\b", r"\bsdb\b", r"nvme0n1|nvme"],
            "de": [r"\bsda\b", r"\bsdb\b", r"nvme0n1|nvme"],
            "es": [r"\bsda\b", r"\bsdb\b", r"nvme0n1|nvme"],
            "pt": [r"\bsda\b", r"\bsdb\b", r"nvme0n1|nvme"],
            "ru": [r"\bsda\b", r"\bsdb\b", r"nvme0n1|nvme"],
        },
        "forbidden": {
            "en": [r"\b2 disks\b", r"\b4 disks\b"],
            "fr": [r"\b2 disques\b", r"\b4 disques\b"],
            "de": [r"\b2 datentrager\b", r"\b4 datentrager\b"],
            "es": [r"\b2 discos\b", r"\b4 discos\b"],
            "pt": [r"\b2 discos\b", r"\b4 discos\b"],
            "ru": [r"\b2 диска\b", r"\b4 диска\b"],
        },
        "reference": {
            "en": "Disks: sda, sdb, nvme0n1.",
            "fr": "Disques : sda, sdb, nvme0n1.",
            "de": "Datenträger: sda, sdb, nvme0n1.",
            "es": "Discos: sda, sdb, nvme0n1.",
            "pt": "Discos: sda, sdb, nvme0n1.",
            "ru": "Диски: sda, sdb, nvme0n1.",
        },
    },
    {
        "id": "disk-no-space-cp",
        "category": "disks",
        "origin": "synthetic",
        "split": "test",
        "task": "summary",
        "cmd": "cp -r build/ /var/backups/build-2026-09-27/",
        "exit": 1,
        "duration": 0.8,
        "output": {
            "en": (
                "cp: error writing '/var/backups/build-2026-09-27/dist/app.bin': No space left on device\n"
                "cp: failed to extend '/var/backups/build-2026-09-27/dist/app.bin': No space left on device\n"
                "cp: closing output file '/var/backups/build-2026-09-27/dist/app.bin': No space left on device\n"
                "cp: error writing '/var/backups/build-2026-09-27/dist/assets.tar': No space left on device\n"
                "cp: failed to extend '/var/backups/build-2026-09-27/dist/assets.tar': No space left on device"
            ),
            "fr": (
                "cp: erreur d'écriture de « /var/backups/build-2026-09-27/dist/app.bin » : "
                "Plus d'espace disponible sur le périphérique\n"
                "cp: impossible d'agrandir « /var/backups/build-2026-09-27/dist/app.bin » : "
                "Plus d'espace disponible sur le périphérique\n"
                "cp: fermeture du fichier de sortie « /var/backups/build-2026-09-27/dist/app.bin » : "
                "Plus d'espace disponible sur le périphérique\n"
                "cp: erreur d'écriture de « /var/backups/build-2026-09-27/dist/assets.tar » : "
                "Plus d'espace disponible sur le périphérique\n"
                "cp: impossible d'agrandir « /var/backups/build-2026-09-27/dist/assets.tar » : "
                "Plus d'espace disponible sur le périphérique"
            ),
        },
        "expected": {
            "en": [r"fail|error|could not|cannot|unable", r"no space|disk full|full", r"app\.bin"],
            "fr": [r"echec|erreur|impossible|echoue", r"plus d.espace|espace disponible|disque plein", r"app\.bin"],
            "de": [r"fehlgeschlagen|fehler", r"kein speicherplatz|speicherplatz voll|platz voll", r"app\.bin"],
            "es": [r"fallo|error", r"sin espacio|espacio agotado|disco lleno", r"app\.bin"],
            "pt": [r"falhou|erro|falha", r"sem espaco|espaco esgotado|disco cheio", r"app\.bin"],
            "ru": [r"ошибк", r"нет места|место закончилось|диск заполнен", r"app\.bin"],
        },
        "forbidden": [r"tmpfs", r"overlay"],
        "reference": {
            "en": "Failed. No space left, app.bin.",
            "fr": "Échec. Plus d'espace disponible, app.bin.",
            "de": "Fehlgeschlagen. Kein Speicherplatz mehr, app.bin.",
            "es": "Fallo. Sin espacio disponible, app.bin.",
            "pt": "Falhou. Sem espaço disponível, app.bin.",
            "ru": "Ошибка. Нет места на диске, app.bin.",
        },
    },
    {
        "id": "disk-du-var-log",
        "category": "disks",
        "origin": "synthetic",
        "split": "test",
        "task": "summary",
        "cmd": "du -sh * | sort -h",
        "exit": 0,
        "duration": 0.15,
        "output": {
            "en": (
                "4.0K\talternatives.log\n"
                "16K\tdpkg.log\n"
                "84K\tauth.log\n"
                "1.1M\tsyslog\n"
                "2.3M\tkern.log\n"
                "18M\tjournal\n"
                "210M\tnginx"
            ),
            "fr": (
                "4,0K\talternatives.log\n"
                "16K\tdpkg.log\n"
                "84K\tauth.log\n"
                "1,1M\tsyslog\n"
                "2,3M\tkern.log\n"
                "18M\tjournal\n"
                "210M\tnginx"
            ),
        },
        "expected": {
            "en": [r"nginx", r"\b210", r"journal"],
            "fr": [r"nginx", r"\b210", r"journal"],
            "de": [r"nginx", r"\b210", r"journal"],
            "es": [r"nginx", r"\b210", r"journal"],
            "pt": [r"nginx", r"\b210", r"journal"],
            "ru": [r"nginx", r"\b210", r"journal"],
        },
        "forbidden": [r"tmpfs", r"overlay"],
        "reference": {
            "en": "Largest: nginx 210M, then journal 18M.",
            "fr": "Plus gros : nginx 210M, puis journal 18M.",
            "de": "Größtes: nginx 210M, dann journal 18M.",
            "es": "Más grande: nginx 210M, luego journal 18M.",
            "pt": "Maior: nginx 210M, depois journal 18M.",
            "ru": "Самое большое: nginx 210M, затем journal 18M.",
        },
    },
    {
        "id": "disk-smartctl-health",
        "category": "disks",
        "origin": "synthetic",
        "split": "dev",
        "task": "summary",
        "cmd": "smartctl -H /dev/sda",
        "exit": 8,
        "duration": 0.3,
        "output": (
            "smartctl 7.4 2023-08-01 r5530 [x86_64-linux-6.1.0-13-amd64] (local build)\n"
            "\n"
            "=== START OF READ SMART DATA SECTION ===\n"
            "SMART overall-health self-assessment test result: FAILED!\n"
            "Drive failure expected in less than 24 hours. SAVE ALL DATA.\n"
            "\n"
            "SMART Attributes Data Structure revision number: 16\n"
            "Vendor Specific SMART Attributes with Thresholds:\n"
            "ID# ATTRIBUTE_NAME          FLAG     VALUE WORST THRESH TYPE      UPDATED  WHEN_FAILED RAW_VALUE\n"
            "  5 Reallocated_Sector_Ct   0x0033   001   001   036    Pre-fail  Always   FAILING_NOW  2104\n"
            "197 Current_Pending_Sector  0x0032   001   001   000    Old_age   Always   FAILING_NOW  88"
        ),
        "expected": {
            "en": [r"fail|error|could not|cannot|unable", r"replace|failing|failure|dying|imminent"],
            "fr": [r"echec|erreur|impossible|echoue", r"remplac|panne|defaillance|imminent"],
            "de": [r"fehlgeschlagen|fehler", r"ersetz|ausfall|defekt|unmittelbar bevorsteh"],
            "es": [r"fallo|error", r"reemplaz|fallando|fallo del disco|inminente"],
            "pt": [r"falhou|erro|falha", r"substitu|a falhar|falha do disco|iminente"],
            "ru": [r"ошибк", r"замен|отказ|выход из строя|неминуем"],
        },
        "forbidden": [r"tmpfs", r"overlay", r"serial"],
        "reference": {
            "en": "Failed. Drive failing, replace within 24 hours.",
            "fr": "Échec. Disque en panne, remplacer sous 24 heures.",
            "de": "Fehlgeschlagen. Laufwerk defekt, innerhalb 24 Stunden ersetzen.",
            "es": "Fallo. Disco fallando, reemplazar en 24 horas.",
            "pt": "Falhou. Disco a falhar, substituir em 24 horas.",
            "ru": "Ошибка. Диск выходит из строя, заменить в течение 24 часов.",
        },
    },
    # ---------------------------------------------------------------- memory
    {
        "id": "mem-free-h",
        "category": "memory",
        "origin": "synthetic",
        "split": "test",
        "task": "summary",
        "cmd": "free -h -t -w -s 1 -c 2",
        "exit": 0,
        "duration": 1.0,
        "output": {
            "en": (
                "               total        used        free      shared     buffers       cache   available\n"
                "Mem:            15Gi        14Gi       312Mi        412Mi       102Mi       1.8Gi       412Mi\n"
                "Swap:          2.0Gi       1.6Gi       412Mi\n"
                "Total:          17Gi        16Gi       724Mi\n"
                "\n"
                "               total        used        free      shared     buffers       cache   available\n"
                "Mem:            15Gi        14Gi       298Mi        412Mi       102Mi       1.8Gi       398Mi\n"
                "Swap:          2.0Gi       1.6Gi       412Mi\n"
                "Total:          17Gi        16Gi       710Mi"
            ),
            "fr": (
                "               total       utilisé        libre      partagé      tampons        cache   disponible\n"
                "Mem:            15Gi        14Gi       312Mi        412Mi       102Mi       1,8Gi       412Mi\n"
                "Échange:       2,0Gi       1,6Gi       412Mi\n"
                "Total:          17Gi        16Gi       724Mi\n"
                "\n"
                "               total       utilisé        libre      partagé      tampons        cache   disponible\n"
                "Mem:            15Gi        14Gi       298Mi        412Mi       102Mi       1,8Gi       398Mi\n"
                "Échange:       2,0Gi       1,6Gi       412Mi\n"
                "Total:          17Gi        16Gi       710Mi"
            ),
        },
        "expected": {
            "en": [r"\b15", r"\b412", r"1[.,]6"],
            "fr": [r"\b15", r"\b412", r"1[.,]6"],
            "de": [r"\b15", r"\b412", r"1[.,]6"],
            "es": [r"\b15", r"\b412", r"1[.,]6"],
            "pt": [r"\b15", r"\b412", r"1[.,]6"],
            "ru": [r"\b15", r"\b412", r"1[.,]6"],
        },
        "forbidden": [],
        "reference": {
            "en": "15G total, 412M available, 1.6G swap used.",
            "fr": "15G au total, 412M disponibles, 1,6G d'échange utilisés.",
            "de": "15G insgesamt, 412M verfügbar, 1,6G Swap belegt.",
            "es": "15G en total, 412M disponibles, 1,6G de intercambio usados.",
            "pt": "15G no total, 412M disponíveis, 1,6G de swap usados.",
            "ru": "15G всего, 412M доступно, 1,6G подкачки использовано.",
        },
    },
    {
        "id": "mem-vmstat",
        "category": "memory",
        "origin": "synthetic",
        "split": "dev",
        "task": "summary",
        "cmd": "vmstat 1 5",
        "exit": 0,
        "duration": 4.2,
        "output": (
            "procs -----------memory---------- ---swap-- -----io---- -system-- ------cpu-----\n"
            " r  b   swpd   free   buff  cache   si   so    bi    bo   in   cs us sy id wa st\n"
            " 2  1 1638400 319488 104448 1887436    0    0    12    45  110  210  8  3 87  2  0\n"
            " 3  1 1638400 298532 104448 1887436    0    0     0   512  145  260 12  5 79  4  0\n"
            " 4  2 1660928 275812 104448 1887436  128    0     0   768  180  310 15  6 71  8  0\n"
            " 5  3 1699840 241024 104448 1887436  256   64     0  1024  210  350 18  8 62 12  0\n"
            " 3  1 1699840 260096 104448 1887436   64    0     0   256  150  280 10  4 80  6  0"
        ),
        "expected": {
            "en": [r"swap", r"io ?wait|wait time", r"pressure|constrained|low memory|memory issue"],
            "fr": [r"echang", r"attente", r"pression|contrainte|memoire faible"],
            "de": [r"swap|auslagerung", r"wartezeit|io.?wait", r"druck|engpass|speicherknappheit|speicherproblem"],
            "es": [r"intercambio|swap", r"espera de e/s|tiempo de espera", r"presion|limitacion|poca memoria|problema de memoria"],
            "pt": [r"swap|paginacao", r"espera de e/s|tempo de espera", r"pressao|limitacao|pouca memoria|problema de memoria"],
            "ru": [r"своп|подкачк", r"время ожидания|ожидание ввода.вывода", r"давление|нагрузка|нехватка памяти|проблема с памятью"],
        },
        "forbidden": {
            "en": [r"\bhealthy\b", r"\bno issue\b"],
            "fr": [r"\bsain\b", r"\baucun probleme\b"],
            "de": [r"\bgesund\b", r"\bkein problem\b"],
            "es": [r"\bsaludable\b", r"\bsin problema\b"],
            "pt": [r"\bsaudavel\b", r"\bsem problema\b"],
            "ru": [r"\bздоровыи\b", r"\bнет проблем\b"],
        },
        "reference": {
            "en": "Swapping active, IO wait high, memory pressure.",
            "fr": "Échanges actifs, attente E/S élevée, pression mémoire.",
            "de": "Swapping aktiv, IO-Wartezeit hoch, Speicherdruck.",
            "es": "Intercambio activo, espera de E/S alta, presión de memoria.",
            "pt": "Swap ativo, espera de E/S alta, pressão de memória.",
            "ru": "Активная подкачка, высокое время ожидания ввода-вывода, давление на память.",
        },
    },
    {
        "id": "mem-top-b",
        "category": "memory",
        "origin": "synthetic",
        "split": "test",
        "task": "summary",
        "cmd": "top -b -n1 | head -20",
        "exit": 0,
        "duration": 1.1,
        "output": (
            "top - 10:15:02 up 3 days,  4:22,  1 user,  load average: 4.82, 3.10, 2.05\n"
            "Tasks: 214 total,   3 running, 211 sleeping,   0 stopped,   0 zombie\n"
            "%Cpu(s): 22.1 us,  8.4 sy,  0.0 ni, 61.2 id,  7.8 wa,  0.0 hi,  0.5 si,  0.0 st\n"
            "MiB Mem :  15872.0 total,    298.4 free,  14930.6 used,    643.0 buff/cache\n"
            "MiB Swap:   2048.0 total,   1638.2 used,    409.8 free.   1024.2 avail Mem\n"
            "\n"
            "    PID USER      PR  NI    VIRT    RES    SHR S  %CPU  %MEM     TIME+ COMMAND\n"
            "   2142 mysql     20   0 3184532 892456   9124 S  18.3  54.9   142:03 mysqld\n"
            "   1190 root      20   0  289456  45120   8320 S   4.2   2.8    38:12 nginx\n"
            "   3301 app       20   0 1245680 312048  10344 S   3.9  19.1    88:44 java\n"
            "    701 root      20   0   14224   9800   6512 S   0.3   0.6     2:10 sshd"
        ),
        "expected": {
            "en": [r"mysqld", r"54[.,]9"],
            "fr": [r"mysqld", r"54[.,]9"],
            "de": [r"mysqld", r"54[.,]9"],
            "es": [r"mysqld", r"54[.,]9"],
            "pt": [r"mysqld", r"54[.,]9"],
            "ru": [r"mysqld", r"54[.,]9"],
        },
        "forbidden": [],
        "reference": {
            "en": "Memory nearly full, mysqld using 54.9% RAM.",
            "fr": "Mémoire presque pleine, mysqld à 54,9 % RAM.",
            "de": "Speicher fast voll, mysqld nutzt 54,9 % RAM.",
            "es": "Memoria casi llena, mysqld usa 54,9 % de RAM.",
            "pt": "Memória quase cheia, mysqld a usar 54,9 % de RAM.",
            "ru": "Память почти заполнена, mysqld использует 54,9 % RAM.",
        },
    },
    {
        "id": "mem-oom-dmesg",
        "category": "memory",
        "origin": "synthetic",
        "split": "test",
        "task": "summary",
        "cmd": "dmesg -T | tail -20",
        "exit": 0,
        "duration": 0.05,
        "output": (
            "[Sun Sep 27 10:12:01 2026] java invoked oom-killer: gfp_mask=0x140dca(GFP_HIGHUSER_MOVABLE|__GFP_COMP), "
            "order=0, oom_score_adj=0\n"
            "[Sun Sep 27 10:12:01 2026] CPU: 3 PID: 3301 Comm: java Not tainted 6.1.0-13-amd64 #1 Debian\n"
            "[Sun Sep 27 10:12:01 2026] Mem-Info:\n"
            "[Sun Sep 27 10:12:01 2026] active_anon:2891234 inactive_anon:102344 isolated_anon:0\n"
            "[Sun Sep 27 10:12:01 2026]  active_file:12034 inactive_file:8821 isolated_file:0\n"
            "[Sun Sep 27 10:12:01 2026] Out of memory: Killed process 3301 (java) total-vm:4982720kB, "
            "anon-rss:3891244kB, file-rss:0kB, shmem-rss:0kB\n"
            "[Sun Sep 27 10:12:01 2026] oom_reaper: reaped process 3301 (java), now anon-rss:0kB, file-rss:0kB, "
            "shmem-rss:0kB"
        ),
        "expected": {
            "en": [r"fail|error|could not|cannot|unable", r"out of memory|oom", r"java"],
            "fr": [r"echec|erreur|impossible|echoue", r"memoire (saturee|insuffisante|pleine)|out of memory|oom", r"java"],
            "de": [r"fehlgeschlagen|fehler", r"speicher (voll|erschopft)|out of memory|oom", r"java"],
            "es": [r"fallo|error", r"memoria (saturada|agotada|llena)|out of memory|oom", r"java"],
            "pt": [r"falhou|erro|falha", r"memoria (esgotada|cheia)|out of memory|oom", r"java"],
            "ru": [r"ошибк", r"память (исчерпана|заполнена)|нехватка памяти|oom", r"java"],
        },
        "forbidden": [r"\bmysqld\b", r"\bnginx\b"],
        "reference": {
            "en": "Failed. Out of memory, java killed, pid 3301.",
            "fr": "Échec. Mémoire saturée, java tué, pid 3301.",
            "de": "Fehlgeschlagen. Speicher erschöpft, java beendet, pid 3301.",
            "es": "Fallo. Memoria agotada, java terminado, pid 3301.",
            "pt": "Falhou. Memória esgotada, java terminado, pid 3301.",
            "ru": "Ошибка. Память исчерпана, java завершён, pid 3301.",
        },
    },
    {
        "id": "mem-ps-sort",
        "category": "memory",
        "origin": "synthetic",
        "split": "test",
        "task": "summary",
        "cmd": "ps aux --sort=-%mem | head -15",
        "exit": 0,
        "duration": 0.08,
        "output": (
            "USER         PID %CPU %MEM    VSZ   RSS TTY      STAT START   TIME COMMAND\n"
            "mysql       2142 18.3 54.9 3184532 892456 ?      Sl   Sep25 142:03 /usr/sbin/mysqld\n"
            "app         3301  3.9 19.1 1245680 312048 ?      Sl   09:40  88:44 java -jar app.jar\n"
            "root        1190  4.2  2.8  289456  45120 ?      Ss   Sep25  38:12 nginx: master process\n"
            "www-data    1245  0.8  2.1  291200  34012 ?      S    Sep25  12:04 nginx: worker process\n"
            "root         701  0.3  0.6   14224   9800 ?      Ss   Sep25   2:10 /usr/sbin/sshd -D\n"
            "root           1  0.1  0.3  102344   7200 ?      Ss   Sep25   0:45 /sbin/init"
        ),
        "expected": {
            "en": [r"mysqld", r"54[.,]9", r"java|19[.,]1"],
            "fr": [r"mysqld", r"54[.,]9", r"java|19[.,]1"],
            "de": [r"mysqld", r"54[.,]9", r"java|19[.,]1"],
            "es": [r"mysqld", r"54[.,]9", r"java|19[.,]1"],
            "pt": [r"mysqld", r"54[.,]9", r"java|19[.,]1"],
            "ru": [r"mysqld", r"54[.,]9", r"java|19[.,]1"],
        },
        "forbidden": [],
        "reference": {
            "en": "Top: mysqld 54.9% RAM, then java 19.1%.",
            "fr": "Top : mysqld 54,9 % RAM, puis java 19,1 %.",
            "de": "Top: mysqld 54,9 % RAM, dann java 19,1 %.",
            "es": "Top: mysqld 54,9 % RAM, luego java 19,1 %.",
            "pt": "Top: mysqld 54,9 % RAM, depois java 19,1 %.",
            "ru": "Топ: mysqld 54,9 % RAM, затем java 19,1 %.",
        },
    },
    {
        "id": "mem-proc-meminfo",
        "category": "memory",
        "origin": "synthetic",
        "split": "test",
        "task": "summary",
        "cmd": "cat /proc/meminfo | head -20",
        "exit": 0,
        "duration": 0.01,
        "output": (
            "MemTotal:       16247892 kB\n"
            "MemFree:          305412 kB\n"
            "MemAvailable:     421308 kB\n"
            "Buffers:          104448 kB\n"
            "Cached:          1932404 kB\n"
            "SwapCached:        88320 kB\n"
            "Active:          8534212 kB\n"
            "Inactive:        6234108 kB\n"
            "SwapTotal:       2097148 kB\n"
            "SwapFree:         458392 kB\n"
            "Dirty:              5120 kB\n"
            "Writeback:              0 kB\n"
            "AnonPages:       7982340 kB\n"
            "Mapped:           412308 kB\n"
            "Shmem:            433152 kB\n"
            "Slab:             298432 kB\n"
            "SReclaimable:     168304 kB\n"
            "SUnreclaim:       130128 kB\n"
            "KernelStack:        18432 kB\n"
            "PageTables:         45056 kB"
        ),
        "expected": {
            "en": [r"16247892", r"421308"],
            "fr": [r"16247892", r"421308"],
            "de": [r"16247892", r"421308"],
            "es": [r"16247892", r"421308"],
            "pt": [r"16247892", r"421308"],
            "ru": [r"16247892", r"421308"],
        },
        "forbidden": [],
        "reference": {
            "en": "16247892 kB total, 421308 available, memory tight.",
            "fr": "16247892 ko au total, 421308 disponibles, mémoire tendue.",
            "de": "16247892 kB insgesamt, 421308 verfügbar, Speicher knapp.",
            "es": "16247892 kB en total, 421308 disponibles, memoria ajustada.",
            "pt": "16247892 kB no total, 421308 disponíveis, memória apertada.",
            "ru": "16247892 кБ всего, 421308 доступно, памяти мало.",
        },
    },
    {
        "id": "mem-vm-stat-macos",
        "category": "memory",
        "origin": "synthetic",
        "split": "test",
        "task": "summary",
        "cmd": "vm_stat",
        "exit": 0,
        "duration": 0.01,
        "output": (
            "Mach Virtual Memory Statistics: (page size of 16384 bytes)\n"
            "Pages free:                               24803.\n"
            "Pages active:                             412998.\n"
            "Pages inactive:                           388120.\n"
            "Pages speculative:                          8842.\n"
            "Pages throttled:                                0.\n"
            "Pages wired down:                         198342.\n"
            "Pages purgeable:                            32011.\n"
            "\"Translation faults\":                  289340213.\n"
            "Pages copy-on-write:                      4821223.\n"
            "Pages zero filled:                      102938442.\n"
            "Pages reactivated:                         881234.\n"
            "Pages purged:                              221044.\n"
            "File-backed pages:                         298344.\n"
            "Anonymous pages:                           510776.\n"
            "Pages stored in compressor:                892011.\n"
            "Pages occupied by compressor:               201344.\n"
            "Decompressions:                             402881.\n"
            "Compressions:                               918233.\n"
            "Pageins:                                  1029384.\n"
            "Pageouts:                                    8821.\n"
            "Swapins:                                    102934.\n"
            "Swapouts:                                   118203."
        ),
        "expected": {
            "en": [r"24803", r"swap", r"102934"],
            "fr": [r"24803", r"pagination|swap", r"102934"],
            "de": [r"24803", r"swap|auslagerung", r"102934"],
            "es": [r"24803", r"intercambio|swap", r"102934"],
            "pt": [r"24803", r"paginacao|swap", r"102934"],
            "ru": [r"24803", r"своп|подкачк", r"102934"],
        },
        "forbidden": [],
        "reference": {
            "en": "24803 pages free, heavy swapping, 102934 swap-ins.",
            "fr": "24803 pages libres, forte pagination, 102934 entrées swap.",
            "de": "24803 Seiten frei, starkes Swapping, 102934 Swap-Ins.",
            "es": "24803 páginas libres, intercambio intenso, 102934 entradas de swap.",
            "pt": "24803 páginas livres, paginação intensa, 102934 entradas de swap.",
            "ru": "24803 страницы свободно, интенсивная подкачка, 102934 переходов в своп.",
        },
    },
    {
        "id": "mem-cgroup-limit",
        "category": "memory",
        "origin": "synthetic",
        "split": "dev",
        "task": "summary",
        "cmd": "docker stats --no-stream",
        "exit": 0,
        "duration": 0.4,
        "output": (
            "CONTAINER ID   NAME         CPU %     MEM USAGE / LIMIT     MEM %     NET I/O           BLOCK I/O         PIDS\n"
            "a1b2c3d4e5f6   web          2.31%     498.2MiB / 512MiB     97.30%    1.2MB / 3.4MB     12MB / 0B         24\n"
            "b7c8d9e0f1a2   worker       88.42%    511.8MiB / 512MiB     99.96%    820kB / 640kB     4.1MB / 0B        18\n"
            "c3d4e5f6a7b8   redis        0.15%     42.1MiB / 256MiB      16.45%    102kB / 88kB      0B / 0B           6\n"
            "d9e0f1a2b3c4   nginx        0.08%     18.4MiB / 128MiB      14.38%    3.1MB / 2.8MB     0B / 0B           4"
        ),
        "expected": {
            "en": [r"worker", r"99[.,]96", r"512"],
            "fr": [r"worker", r"99[.,]96", r"512"],
            "de": [r"worker", r"99[.,]96", r"512"],
            "es": [r"worker", r"99[.,]96", r"512"],
            "pt": [r"worker", r"99[.,]96", r"512"],
            "ru": [r"worker", r"99[.,]96", r"512"],
        },
        "forbidden": [],
        "reference": {
            "en": "Worker container near limit, 99.96% of 512MiB.",
            "fr": "Conteneur worker proche de la limite, 99,96 % de 512 Mo.",
            "de": "Container worker nahe am Limit, 99,96 % von 512 MiB.",
            "es": "Contenedor worker cerca del límite, 99,96 % de 512 MiB.",
            "pt": "Contentor worker perto do limite, 99,96 % de 512 MiB.",
            "ru": "Контейнер worker близок к лимиту, 99,96 % от 512 МиБ.",
        },
    },
    # ---------------------------------------------------------------- hardware
    {
        "id": "hw-lspci-intel-laptop",
        "category": "hardware",
        "origin": "synthetic",
        "split": "test",
        "task": "summary",
        "cmd": "lspci",
        "exit": 0,
        "duration": 0.02,
        "output": (
            "00:00.0 Host bridge: Intel Corporation Device a706 (rev 01)\n"
            "00:02.0 VGA compatible controller: Intel Corporation Raptor Lake-P [Iris Xe Graphics] (rev 04)\n"
            "00:04.0 Signal processing controller: Intel Corporation Raptor Lake Dynamic Platform and Thermal "
            "Framework Processor\n"
            "00:06.0 PCI bridge: Intel Corporation Device a70d (rev 01)\n"
            "00:07.0 PCI bridge: Intel Corporation Device a70b (rev 01)\n"
            "00:14.0 USB controller: Intel Corporation Raptor Lake-P USB 3.2 Gen 2x2 XHCI Host Controller\n"
            "00:14.2 RAM memory: Intel Corporation Raptor Lake-P Shared SRAM\n"
            "00:15.0 Serial bus controller: Intel Corporation Raptor Lake-P Serial IO I2C Controller\n"
            "00:16.0 Communication controller: Intel Corporation Raptor Lake-P Management Engine Interface\n"
            "00:1f.0 ISA bridge: Intel Corporation Device a7ac\n"
            "00:1f.3 Audio device: Intel Corporation Raptor Lake-P/U/PX HD Audio Controller\n"
            "00:1f.4 SMBus: Intel Corporation Raptor Lake-P SMBus\n"
            "02:00.0 Non-Volatile memory controller: Kioxia Corporation NVMe SSD Controller\n"
            "03:00.0 Network controller: Intel Corporation Wi-Fi 6E AX211"
        ),
        "expected": {
            "en": [r"iris xe|integrated", r"wi-?fi|ax211", r"nvme"],
            "fr": [r"iris xe|integre", r"wi-?fi|ax211", r"nvme"],
            "de": [r"iris xe|integriert", r"wi-?fi|ax211", r"nvme"],
            "es": [r"iris xe|integrada|integrado", r"wi-?fi|ax211", r"nvme"],
            "pt": [r"iris xe|integrada|integrado", r"wi-?fi|ax211", r"nvme"],
            "ru": [r"iris xe|встроен", r"wi-?fi|ax211", r"nvme"],
        },
        "forbidden": [
            r"\bi7-\d", r"\bi5-\d", r"\bi9-\d", r"\bryzen\b",
            r"\bnvidia\b", r"\bgeforce\b", r"\bradeon\b",
        ],
        "reference": {
            "en": "Intel Iris Xe graphics, Wi-Fi 6E AX211, NVMe SSD, integrated only.",
            "fr": "Graphique intégré Intel Iris Xe, Wi-Fi 6E AX211, SSD NVMe, rien d'autre.",
            "de": "Intel Iris Xe Grafik, Wi-Fi 6E AX211, NVMe-SSD, nur integriert.",
            "es": "Gráficos Intel Iris Xe, Wi-Fi 6E AX211, SSD NVMe, solo integrados.",
            "pt": "Gráficos Intel Iris Xe, Wi-Fi 6E AX211, SSD NVMe, apenas integrados.",
            "ru": "Графика Intel Iris Xe, Wi-Fi 6E AX211, NVMe SSD, только встроенная.",
        },
    },
    {
        "id": "hw-lsusb",
        "category": "hardware",
        "origin": "synthetic",
        "split": "dev",
        "task": "summary",
        "cmd": "lsusb",
        "exit": 0,
        "duration": 0.03,
        "output": (
            "Bus 001 Device 001: ID 1d6b:0002 Linux Foundation 2.0 root hub\n"
            "Bus 001 Device 003: ID 046d:c52b Logitech, Inc. Unifying Receiver\n"
            "Bus 001 Device 005: ID 0781:5591 SanDisk Corp. Ultra Fit\n"
            "Bus 002 Device 001: ID 1d6b:0003 Linux Foundation 3.0 root hub\n"
            "Bus 002 Device 002: ID 8087:0033 Intel Corp. AX211 Bluetooth\n"
            "Bus 003 Device 001: ID 1d6b:0002 Linux Foundation 2.0 root hub"
        ),
        "expected": {
            "en": [r"logitech", r"sandisk", r"bluetooth"],
            "fr": [r"logitech", r"sandisk", r"bluetooth"],
            "de": [r"logitech", r"sandisk", r"bluetooth"],
            "es": [r"logitech", r"sandisk", r"bluetooth"],
            "pt": [r"logitech", r"sandisk", r"bluetooth"],
            "ru": [r"logitech", r"sandisk", r"bluetooth"],
        },
        "forbidden": [r"root hub"],
        "reference": {
            "en": "USB: Logitech receiver, SanDisk drive, Intel Bluetooth.",
            "fr": "USB : récepteur Logitech, clé SanDisk, Bluetooth Intel.",
            "de": "USB: Logitech-Empfänger, SanDisk-Laufwerk, Intel Bluetooth.",
            "es": "USB: receptor Logitech, unidad SanDisk, Bluetooth Intel.",
            "pt": "USB: receptor Logitech, unidade SanDisk, Bluetooth Intel.",
            "ru": "USB: приёмник Logitech, накопитель SanDisk, Bluetooth Intel.",
        },
    },
    {
        "id": "hw-lscpu",
        "category": "hardware",
        "origin": "synthetic",
        "split": "dev",
        "task": "summary",
        "cmd": "lscpu",
        "exit": 0,
        "duration": 0.01,
        "output": {
            "en": (
                "Architecture:            x86_64\n"
                "CPU op-mode(s):          32-bit, 64-bit\n"
                "Byte Order:              Little Endian\n"
                "CPU(s):                  20\n"
                "On-line CPU(s) list:     0-19\n"
                "Vendor ID:               GenuineIntel\n"
                "Model name:              13th Gen Intel(R) Core(TM) i7-1370P\n"
                "CPU family:              6\n"
                "Model:                   186\n"
                "Thread(s) per core:      2\n"
                "Core(s) per socket:      14\n"
                "Socket(s):               1\n"
                "CPU max MHz:             5000.0000"
            ),
            "fr": (
                "Architecture :                      x86_64\n"
                "Mode(s) opératoire(s) des CPU :     32-bit, 64-bit\n"
                "Boutisme :                          Petit boutien\n"
                "Processeur(s) :                     20\n"
                "Liste de processeur(s) en ligne :   0-19\n"
                "ID fournisseur :                    GenuineIntel\n"
                "Nom de modèle :                     13th Gen Intel(R) Core(TM) i7-1370P\n"
                "Famille de processeur :              6\n"
                "Modèle :                             186\n"
                "Thread(s) par cœur :                2\n"
                "Cœur(s) par socket :                14\n"
                "Socket(s) :                          1\n"
                "Vitesse maximale du CPU en MHz :     5000.0000"
            ),
        },
        "expected": {
            "en": [r"i7-1370p|1370p", r"\b14\b", r"\b20\b"],
            "fr": [r"i7-1370p|1370p", r"\b14\b", r"\b20\b"],
            "de": [r"i7-1370p|1370p", r"\b14\b", r"\b20\b"],
            "es": [r"i7-1370p|1370p", r"\b14\b", r"\b20\b"],
            "pt": [r"i7-1370p|1370p", r"\b14\b", r"\b20\b"],
            "ru": [r"i7-1370p|1370p", r"\b14\b", r"\b20\b"],
        },
        "forbidden": [r"\b28\b"],
        "reference": {
            "en": "Intel Core i7-1370P, 14 cores, 20 threads.",
            "fr": "Intel Core i7-1370P, 14 cœurs, 20 threads.",
            "de": "Intel Core i7-1370P, 14 Kerne, 20 Threads.",
            "es": "Intel Core i7-1370P, 14 núcleos, 20 hilos.",
            "pt": "Intel Core i7-1370P, 14 núcleos, 20 threads.",
            "ru": "Intel Core i7-1370P, 14 ядер, 20 потоков.",
        },
    },
    {
        "id": "hw-sensors-hot",
        "category": "hardware",
        "origin": "synthetic",
        "split": "test",
        "task": "summary",
        "cmd": "sensors",
        "exit": 0,
        "duration": 0.05,
        "output": (
            "coretemp-isa-0000\n"
            "Adapter: ISA adapter\n"
            "Package id 0:  +92.0°C  (high = +100.0°C, crit = +100.0°C)\n"
            "Core 0:        +78.0°C  (high = +100.0°C, crit = +100.0°C)\n"
            "Core 1:        +91.0°C  (high = +100.0°C, crit = +100.0°C)\n"
            "Core 2:        +80.0°C  (high = +100.0°C, crit = +100.0°C)\n"
            "Core 3:        +79.0°C  (high = +100.0°C, crit = +100.0°C)\n"
            "\n"
            "nvme-pci-0200\n"
            "Adapter: PCI adapter\n"
            "Composite:    +42.0°C  (low  = -0.1°C, high = +84.8°C, crit = +84.8°C)\n"
            "\n"
            "acpitz-acpi-0\n"
            "Adapter: ACPI interface\n"
            "temp1:        +45.0°C"
        ),
        "expected": {
            "en": [r"core ?1", r"\b91\b"],
            "fr": [r"c.ur ?1", r"\b91\b"],
            "de": [r"core ?1|kern ?1", r"\b91\b"],
            "es": [r"nucleo ?1|core ?1", r"\b91\b"],
            "pt": [r"nucleo ?1|core ?1", r"\b91\b"],
            "ru": [r"ядро ?1|core ?1", r"\b91\b"],
        },
        "forbidden": [],
        "reference": {
            "en": "Core 1 hot, 91°C.",
            "fr": "Cœur 1 chaud, 91°C.",
            "de": "Kern 1 heiß, 91°C.",
            "es": "Núcleo 1 caliente, 91°C.",
            "pt": "Núcleo 1 quente, 91°C.",
            "ru": "Ядро 1 горячее, 91°C.",
        },
    },
    {
        "id": "hw-nvidia-smi",
        "category": "hardware",
        "origin": "synthetic",
        "split": "dev",
        "task": "summary",
        "cmd": "nvidia-smi",
        "exit": 0,
        "duration": 0.3,
        "output": (
            "+-----------------------------------------------------------------------------------------+\n"
            "| NVIDIA-SMI 550.90.07              Driver Version: 550.90.07      CUDA Version: 12.4      |\n"
            "|-----------------------------------------+------------------------+----------------------+\n"
            "| GPU  Name                 Persistence-M | Bus-Id          Disp.A | Volatile Uncorr. ECC |\n"
            "| Fan  Temp   Perf          Pwr:Usage/Cap |           Memory-Usage | GPU-Util  Compute M. |\n"
            "|                                         |                        |               MIG M. |\n"
            "|=========================================+========================+======================|\n"
            "|   0  NVIDIA GeForce RTX 3060        Off  | 00000000:2B:00.0  On  |                  N/A |\n"
            "| 30%   62C    P2             118W / 170W |   9821MiB / 12288MiB  |     87%      Default |\n"
            "|                                         |                        |                  N/A |\n"
            "+-----------------------------------------------------------------------------------------+\n"
            "\n"
            "+-----------------------------------------------------------------------------------------+\n"
            "| Processes:                                                                               |\n"
            "|  GPU   GI   CI        PID   Type   Process name                            GPU Memory    |\n"
            "|        ID   ID                                                              Usage        |\n"
            "|===========================================================================================|\n"
            "|    0   N/A  N/A      8821      C   python3                                     9812MiB   |\n"
            "+-----------------------------------------------------------------------------------------+"
        ),
        "expected": {
            "en": [r"87 ?%", r"9821", r"\b62\b"],
            "fr": [r"87 ?%", r"9821", r"\b62\b"],
            "de": [r"87 ?%", r"9821", r"\b62\b"],
            "es": [r"87 ?%", r"9821", r"\b62\b"],
            "pt": [r"87 ?%", r"9821", r"\b62\b"],
            "ru": [r"87 ?%", r"9821", r"\b62\b"],
        },
        "forbidden": [r"4090", r"3080", r"3090", r"a100", r"h100"],
        "reference": {
            "en": "RTX 3060: 87% util, 9821MiB used, 62°C.",
            "fr": "RTX 3060 : 87 % d'utilisation, 9821 Mo utilisés, 62°C.",
            "de": "RTX 3060: 87 % Auslastung, 9821 MiB belegt, 62°C.",
            "es": "RTX 3060: 87 % de uso, 9821 MiB usados, 62°C.",
            "pt": "RTX 3060: 87 % de utilização, 9821 MiB usados, 62°C.",
            "ru": "RTX 3060: загрузка 87 %, использовано 9821 МиБ, 62°C.",
        },
    },
    {
        "id": "hw-system-profiler-macos",
        "category": "hardware",
        "origin": "synthetic",
        "split": "dev",
        "task": "summary",
        "cmd": "system_profiler SPHardwareDataType",
        "exit": 0,
        "duration": 0.5,
        "output": {
            "en": (
                "Hardware:\n"
                "\n"
                "    Hardware Overview:\n"
                "\n"
                "      Model Name: MacBook Pro\n"
                "      Model Identifier: Mac15,7\n"
                "      Chip: Apple M3 Pro\n"
                "      Total Number of Cores: 12 (6 performance and 6 efficiency)\n"
                "      Memory: 18 GB\n"
                "      System Firmware Version: 10151.101.3\n"
                "      OS Loader Version: 10151.101.3\n"
                "      Activation Lock Status: Enabled"
            ),
            "fr": (
                "Matériel :\n"
                "\n"
                "    Vue d'ensemble du matériel :\n"
                "\n"
                "      Nom du modèle : MacBook Pro\n"
                "      Identifiant du modèle : Mac15,7\n"
                "      Puce : Apple M3 Pro\n"
                "      Nombre total de cœurs : 12 (6 performants et 6 économes)\n"
                "      Mémoire : 18 Go\n"
                "      Version du micrologiciel système : 10151.101.3\n"
                "      Version du chargeur de système : 10151.101.3\n"
                "      État de verrouillage d'activation : Activé"
            ),
        },
        "expected": {
            "en": [r"m3 pro", r"\b12\b", r"\b18"],
            "fr": [r"m3 pro", r"\b12\b", r"\b18"],
            "de": [r"m3 pro", r"\b12\b", r"\b18"],
            "es": [r"m3 pro", r"\b12\b", r"\b18"],
            "pt": [r"m3 pro", r"\b12\b", r"\b18"],
            "ru": [r"m3 pro", r"\b12\b", r"\b18"],
        },
        "forbidden": [r"serial"],
        "reference": {
            "en": "MacBook Pro, Apple M3 Pro, 12 cores, 18GB memory.",
            "fr": "MacBook Pro, puce Apple M3 Pro, 12 cœurs, 18 Go de mémoire.",
            "de": "MacBook Pro, Apple M3 Pro Chip, 12 Kerne, 18 GB Speicher.",
            "es": "MacBook Pro, chip Apple M3 Pro, 12 núcleos, 18 GB de memoria.",
            "pt": "MacBook Pro, chip Apple M3 Pro, 12 núcleos, 18 GB de memória.",
            "ru": "MacBook Pro, чип Apple M3 Pro, 12 ядер, 18 ГБ памяти.",
        },
    },
    {
        "id": "hw-inxi-lshw",
        "category": "hardware",
        "origin": "synthetic",
        "split": "test",
        "task": "summary",
        "cmd": "inxi -G",
        "exit": 0,
        "duration": 0.4,
        "output": (
            "Graphics:\n"
            "  Device-1: Intel Raptor Lake-P [Iris Xe Graphics] driver: i915 v: kernel\n"
            "  Device-2: NVIDIA GA107M [GeForce RTX 3050 Mobile] driver: nvidia v: 550.90.07\n"
            "  Display: server: X.Org v: 21.1.11 driver: X: loaded: intel,nvidia\n"
            "    unloaded: fbdev,modesetting,nouveau,vesa gpu: i915,nvidia\n"
            "    resolution: 1: 1920x1080 2: 2560x1440\n"
            "  API: OpenGL v: 4.6 Mesa 24.0.5 renderer: Mesa Intel Graphics (RPL-P)"
        ),
        "expected": {
            "en": [r"iris xe|raptor lake", r"3050|ga107"],
            "fr": [r"iris xe|raptor lake", r"3050|ga107"],
            "de": [r"iris xe|raptor lake", r"3050|ga107"],
            "es": [r"iris xe|raptor lake", r"3050|ga107"],
            "pt": [r"iris xe|raptor lake", r"3050|ga107"],
            "ru": [r"iris xe|raptor lake", r"3050|ga107"],
        },
        "forbidden": [r"radeon", r"\bamd\b"],
        "reference": {
            "en": "Intel Iris Xe and NVIDIA RTX 3050.",
            "fr": "Intel Iris Xe et NVIDIA RTX 3050.",
            "de": "Intel Iris Xe und NVIDIA RTX 3050.",
            "es": "Intel Iris Xe y NVIDIA RTX 3050.",
            "pt": "Intel Iris Xe e NVIDIA RTX 3050.",
            "ru": "Intel Iris Xe и NVIDIA RTX 3050.",
        },
    },
]
