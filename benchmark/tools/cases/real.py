"""Real outputs captured on the author's machines, anonymized by hand (see real_outputs/).

Anonymization: user names, host names, project names, LAN plan and VPN addresses replaced;
IPv6 link-local suffixes, LUKS identifiers and MAC addresses removed or zeroed. When the
original was captured under a French locale, the English variant is the same output under
the C locale (.en.txt), and the reverse.

de/es/pt/ru additions: most cases keep the English or French `output` unchanged
(untranslated tools stay untranslated regardless of locale, see
docs/research-terminal-languages.md) and only translate the facts a spoken answer must
contain (expected, reference, question) - that is the point being tested, not the input.
A handful of cases (git status, apt, df, du, ls) got a genuine new capture on the i5-7200U
Debian test machine, see I5_NOTE.

SPDX-License-Identifier: MIT
"""

from pathlib import Path

OUT = Path(__file__).with_name("real_outputs")
LOCALE_NOTE = "Captured under a French locale; the English output is the same run rendered under the C locale."
I5_NOTE = ("Captured live on the i5-7200U Debian test machine, LANG=fr_FR.utf8 LANGUAGE=<lang>: this selects "
           "the tool's real gettext .mo catalog without generating the full de_DE/es_ES/pt_PT/ru_RU locale, "
           "which is not installed on that machine (apt install being out of scope for this read-only capture). "
           "Only message text (LC_MESSAGES) is translated this way; date and number formatting still follow the "
           "base fr_FR locale (comma decimals, French month names).")
ALL_LANGS = ("en", "fr", "de", "es", "pt", "ru")


def read(name: str) -> str:
    return (OUT / name).read_text(encoding="utf-8")


def both(stem: str) -> dict:
    return {lang: read(f"{stem}.{lang}.txt") for lang in ALL_LANGS if (OUT / f"{stem}.{lang}.txt").exists()}


def real(**case) -> dict:
    return {"origin": "real-anonymized", "split": "dev", "task": "summary", "forbidden": [], **case}


FAIL = {"en": r"fail|error", "fr": r"echec|erreur|echoue", "de": r"fehlgeschlagen|fehler",
        "es": r"fallo|error", "pt": r"falhou|erro|falha", "ru": r"ошибк"}
NOT_IN_HISTORY = {
    "en": [r"not in (the )?history|no (information|record|version)|not (shown|found|available|listed)|unknown"],
    "fr": [r"pas dans l.historique|aucun|non disponible|pas d.info|introuvable|inconnu|absent"],
    "de": [r"nicht im verlauf|kein(?:e)? (?:information|eintrag|version)|"
           r"nicht (?:angezeigt|gefunden|verfugbar|aufgefuhrt)|unbekannt"],
    "es": [r"no esta en el historial|ning(?:un|una) (?:informacion|registro|version)|"
           r"no (?:mostrado|encontrado|disponible|listado)|desconocido"],
    "pt": [r"nao esta no historico|nenhum(?:a)? (?:informacao|registo|versao)|"
           r"nao (?:mostrado|encontrado|disponivel|listado)|desconhecido"],
    "ru": [r"нет в истории|нет (?:информации|записи|версии)|"
           r"не (?:показано|наидено|доступно|указано)|неизвестно"],
}
HISTORY = [
    {"cmd": "npm run build", "exit": 1, "output": read("npm_build.txt")},
    {"cmd": "df -h", "exit": 0, "output": read("df_hypervisor.txt")},
]

CASES = [
    real(id="build-npm-ts-property", category="build-failure", cmd="npm run build", exit=1, duration=12.5,
         output=read("npm_build.txt"),
         expected={"en": [FAIL["en"], r"header", r"\b42\b", r"titel"], "fr": [FAIL["fr"], r"header", r"\b42\b", r"titel"],
                   "de": [FAIL["de"], r"header", r"\b42\b", r"titel"], "es": [FAIL["es"], r"header", r"\b42\b", r"titel"],
                   "pt": [FAIL["pt"], r"header", r"\b42\b", r"titel"], "ru": [FAIL["ru"], r"header", r"\b42\b", r"titel"]},
         reference={"en": "Failed. Header.tsx line 42: titel does not exist, did you mean title.",
                    "fr": "Échec. Header.tsx ligne 42 : titel inexistant, utiliser title.",
                    "de": "Fehlgeschlagen. Header.tsx Zeile 42: titel existiert nicht, meintest du title.",
                    "es": "Fallo. Header.tsx línea 42: titel no existe, ¿quisiste decir title?",
                    "pt": "Falhou. Header.tsx linha 42: titel não existe, quis dizer title.",
                    "ru": "Ошибка. Header.tsx строка 42: titel не существует, возможно имелось в виду title."}),
    real(id="runtime-python-keyerror", category="runtime-error",
         cmd="python3 -c 'import json; d={}; print(d[\"key\"])'", exit=1, duration=0.05,
         output=read("python_keyerror.txt"),
         expected={"en": [r"keyerror|key ?error|missing key", r"\bkey\b"], "fr": [r"keyerror|cle", r"\bkey\b"],
                   "de": [r"keyerror|schlussel|fehlt", r"\bkey\b"], "es": [r"keyerror|clave|ausente", r"\bkey\b"],
                   "pt": [r"keyerror|chave|ausente", r"\bkey\b"], "ru": [r"keyerror|ключ|отсутств", r"\bkey\b"]},
         reference={"en": "Failed. KeyError: key missing from the dictionary, line 1.",
                    "fr": "Échec. KeyError : clé key absente du dictionnaire, ligne 1.",
                    "de": "Fehlgeschlagen. KeyError: Schlüssel key fehlt im Dictionary, Zeile 1.",
                    "es": "Fallo. KeyError: clave key ausente del diccionario, línea 1.",
                    "pt": "Falhou. KeyError: chave key ausente do dicionário, linha 1.",
                    "ru": "Ошибка. KeyError: ключ key отсутствует в словаре, строка 1."}),
    real(id="git-status-untracked", category="git", cmd="git status", exit=0, duration=0.0,
         output=both("git_status"),
         notes=LOCALE_NOTE + " " + I5_NOTE + " Portuguese git has no .mo catalog on the i5 (git.mo absent for "
               "pt): the pt case keeps the English output as a fallback; its expected facts and reference are "
               "still written in Portuguese, since the response language does not depend on the output language.",
         expected={"en": [r"master", r"untracked|not tracked"], "fr": [r"master", r"non suivis?|untracked"],
                   "de": [r"master", r"unversioniert|untracked"], "es": [r"master", r"sin seguimiento|untracked"],
                   "pt": [r"master", r"nao controlados|untracked"], "ru": [r"master", r"неотслеживаем|untracked"]},
         reference={"en": "Branch master, no commits yet, untracked: README.md, src, vendor.",
                    "fr": "Branche master, aucun commit, fichiers non suivis : README.md, src, vendor.",
                    "de": "Branch master, noch keine Commits, unversioniert: README.md, src, vendor.",
                    "es": "Rama master, sin commits todavía, sin seguimiento: README.md, src, vendor.",
                    "pt": "Ramo master, ainda sem commits, não controlados: README.md, src, vendor.",
                    "ru": "Ветка master, ещё нет коммитов, неотслеживаемые: README.md, src, vendor."}),
    real(id="git-push-rejected", category="git", cmd="git push", exit=1, duration=2.2,
         output=read("git_push.txt"),
         expected={"en": [r"reject|fail|error", r"pull|fetch|integrat|remote"],
                   "fr": [r"rejet|refus|echec|erreur", r"pull|fetch|integr|distant"],
                   "de": [r"abgelehnt|fehlgeschlagen|fehler", r"pull|fetch|remote"],
                   "es": [r"rechazad|fallo|error", r"pull|fetch|remoto"],
                   "pt": [r"rejeitad|falhou|erro", r"pull|fetch|remoto"],
                   "ru": [r"отклонен|ошибк", r"pull|fetch|удаленн"]},
         reference={"en": "Failed. Push rejected, remote has new commits: git pull first.",
                    "fr": "Échec. Push rejeté, le distant a de nouveaux commits : git pull d'abord.",
                    "de": "Fehlgeschlagen. Push abgelehnt, Remote hat neue Commits: zuerst git pull.",
                    "es": "Fallo. Push rechazado, el remoto tiene nuevos commits: primero git pull.",
                    "pt": "Falhou. Push rejeitado, o remoto tem novos commits: primeiro git pull.",
                    "ru": "Ошибка. Push отклонён, в удалённом репозитории новые коммиты: сначала git pull."}),
    real(id="pkg-apt-upgrade", category="packages", cmd="sudo apt upgrade -y", exit=0, duration=84.2,
         output=both("apt_upgrade"),
         notes=LOCALE_NOTE + " " + I5_NOTE + " cmd/exit/duration are kept identical to the historical en/fr "
               "capture for cross-language consistency; the de/es/pt/ru output actually comes from a read-only "
               "'apt-get --simulate upgrade' on the i5 (197 packages upgradable, 1 held back), not a live "
               "upgrade, since the i5 is read-only for this task.",
         expected={"en": [r"\b12\b", r"upgrad|updat"], "fr": [r"\b12\b", r"mis(es)? a jour|mise a jour|\bmaj\b"],
                   "de": [r"\b197\b", r"zuruckgehalten|linux-image"], "es": [r"\b197\b", r"retenid|linux-image"],
                   "pt": [r"\b197\b", r"retid|linux-image"], "ru": [r"\b197\b", r"не обновлен|linux-image"]},
         reference={"en": "12 packages upgraded, including curl, openssl, vim.",
                    "fr": "12 paquets mis à jour, dont curl, openssl, vim.",
                    "de": "197 aktualisiert, 1 zurückgehalten (linux-image-amd64).",
                    "es": "197 actualizados, 1 retenido (linux-image-amd64).",
                    "pt": "197 actualizados, 1 retido (linux-image-amd64).",
                    "ru": "Обновлено 197 пакетов, 1 пакет не обновлён (linux-image-amd64)."}),
    real(id="pkg-apt-lock", category="packages", cmd="sudo apt install nginx", exit=100, duration=1.3,
         output=both("apt_lock"),
         notes=LOCALE_NOTE + " Not safely reproducible read-only on the i5 (would require holding a genuine "
               "dpkg lock while another apt-get install runs): de/es/pt/ru keep the English output as a "
               "fallback; expected facts and reference are translated regardless.",
         expected={"en": [r"lock", r"4321|unattended|dpkg"], "fr": [r"verrou|lock", r"4321|unattended|dpkg"],
                   "de": [r"sperre|lock", r"4321|unattended|dpkg"], "es": [r"bloqueo|lock", r"4321|unattended|dpkg"],
                   "pt": [r"bloqueio|lock", r"4321|unattended|dpkg"],
                   "ru": [r"блокировк|lock", r"4321|unattended|dpkg"]},
         reference={"en": "Failed. dpkg lock held by process 4321, unattended-upgr.",
                    "fr": "Échec. Verrou dpkg tenu par le processus 4321, unattended-upgr.",
                    "de": "Fehlgeschlagen. dpkg-Sperre von Prozess 4321 gehalten, unattended-upgr.",
                    "es": "Fallo. Bloqueo de dpkg retenido por el proceso 4321, unattended-upgr.",
                    "pt": "Falhou. Bloqueio do dpkg retido pelo processo 4321, unattended-upgr.",
                    "ru": "Ошибка. Блокировка dpkg удерживается процессом 4321, unattended-upgr."}),
    real(id="pkg-pip-install", category="packages", cmd="pip install requests", exit=0, duration=4.1,
         output=read("pip_install.txt"),
         expected=[r"requests", r"2\.32\.3"],
         reference={"en": "requests 2.32.3 installed, with urllib3, idna, certifi.",
                    "fr": "requests 2.32.3 installé, avec urllib3, idna, certifi.",
                    "de": "requests 2.32.3 installiert, mit urllib3, idna, certifi.",
                    "es": "requests 2.32.3 instalado, con urllib3, idna, certifi.",
                    "pt": "requests 2.32.3 instalado, com urllib3, idna, certifi.",
                    "ru": "requests 2.32.3 установлен, с urllib3, idna, certifi."}),
    real(id="pkg-dnf-check-update", category="packages", cmd="dnf check-update --cacheonly 2>&1 | tail -30",
         exit=0, duration=2.28, output=read("dnf_check_update.txt"),
         expected={"en": [r"nvidia", r"update|upgrade"], "fr": [r"nvidia", r"mises? a jour|\bmaj\b|update"],
                   "de": [r"nvidia", r"update|aktualisier"], "es": [r"nvidia", r"actualiza|update"],
                   "pt": [r"nvidia", r"actualiza|update"], "ru": [r"nvidia", r"обновлен|update"]},
         reference={"en": "Updates available: nvidia driver 610.57.04, zsh, xfsprogs, yelp.",
                    "fr": "Mises à jour disponibles : pilote nvidia 610.57.04, zsh, xfsprogs, yelp.",
                    "de": "Updates verfügbar: nvidia-Treiber 610.57.04, zsh, xfsprogs, yelp.",
                    "es": "Actualizaciones disponibles: controlador nvidia 610.57.04, zsh, xfsprogs, yelp.",
                    "pt": "Actualizações disponíveis: controlador nvidia 610.57.04, zsh, xfsprogs, yelp.",
                    "ru": "Доступны обновления: драйвер nvidia 610.57.04, zsh, xfsprogs, yelp."}),
    real(id="net-ip-br-addr", category="network", cmd="ip -br addr", exit=0, duration=0.01,
         output=read("ip_br_addr.txt"),
         expected=[r"192\.168\.1\.20\b", r"10\.8\.0\.34\b", r"172\.16\.1\.2\b"],
         forbidden=[r"127\.0\.0\.1", r"fe80", r"\blo\b"],
         reference={"en": "wlp0s20f3 192.168.1.20, wg0 10.8.0.34, tun0 172.16.1.2, plus Docker bridges.",
                    "fr": "wlp0s20f3 192.168.1.20, wg0 10.8.0.34, tun0 172.16.1.2, plus des ponts Docker.",
                    "de": "wlp0s20f3 192.168.1.20, wg0 10.8.0.34, tun0 172.16.1.2, plus Docker-Bridges.",
                    "es": "wlp0s20f3 192.168.1.20, wg0 10.8.0.34, tun0 172.16.1.2, más puentes Docker.",
                    "pt": "wlp0s20f3 192.168.1.20, wg0 10.8.0.34, tun0 172.16.1.2, mais pontes Docker.",
                    "ru": "wlp0s20f3 192.168.1.20, wg0 10.8.0.34, tun0 172.16.1.2, плюс мосты Docker."}),
    real(id="net-ifconfig-macos", category="network", cmd="ifconfig", exit=0, duration=0.1,
         output=read("ifconfig_macos.txt"),
         expected=[r"192\.168\.1\.62\b", r"10\.8\.0\.46\b"],
         forbidden=[r"127\.0\.0\.1", r"\blo0\b", r"fe80"],
         reference={"en": "en0 192.168.1.62, VPN utun4 10.8.0.46.", "fr": "en0 192.168.1.62, VPN utun4 10.8.0.46."}),
    real(id="net-ip-a-hypervisor", category="network", cmd="ip a", exit=0, duration=0.1,
         output=read("ip_a_hypervisor.txt"),
         expected=[r"192\.168\.1\.200\b", r"10\.8\.0\.123\b"],
         forbidden=[r"127\.0\.0\.1", r"fe80", r"\blo\b"],
         reference={"en": "vmbr0 192.168.1.200, wg0 10.8.0.123. Plus VM taps and firewall bridges.",
                    "fr": "vmbr0 192.168.1.200, wg0 10.8.0.123. Plus interfaces tap et fw des VM.",
                    "de": "vmbr0 192.168.1.200, wg0 10.8.0.123. Plus VM-Taps und Firewall-Bridges.",
                    "es": "vmbr0 192.168.1.200, wg0 10.8.0.123. Más interfaces tap y bridges de firewall de las VM.",
                    "pt": "vmbr0 192.168.1.200, wg0 10.8.0.123. Mais interfaces tap e bridges de firewall das VM.",
                    "ru": "vmbr0 192.168.1.200, wg0 10.8.0.123. Плюс taps VM и мосты firewall."}),
    real(id="net-ping-local", category="network", cmd="ping -c 3 127.0.0.1", exit=0, duration=2.06,
         output=both("ping_local"), notes=LOCALE_NOTE,
         expected={"en": [r"\b0 ?%|no (packet )?loss|0 loss|without loss", r"\b3\b"],
                   "fr": [r"\b0 ?%|aucune perte|sans perte|0 perte", r"\b3\b"],
                   "de": [r"\b0 ?%|kein verlust|0 verlust", r"\b3\b"],
                   "es": [r"\b0 ?%|sin perdida|0 perdida", r"\b3\b"],
                   "pt": [r"\b0 ?%|sem perda|0 perda", r"\b3\b"],
                   "ru": [r"\b0 ?%|потер", r"\b3\b"]},
         reference={"en": "3 of 3 packets received, 0% loss, average 0.024 ms.",
                    "fr": "3 paquets sur 3 reçus, 0 % de perte, moyenne 0,024 ms.",
                    "de": "3 von 3 Paketen empfangen, 0 % Verlust, Durchschnitt 0,024 ms.",
                    "es": "3 de 3 paquetes recibidos, 0 % de pérdida, promedio 0,024 ms.",
                    "pt": "3 de 3 pacotes recebidos, 0 % de perda, média 0,024 ms.",
                    "ru": "Получено 3 из 3 пакетов, потери 0 %, в среднем 0,024 мс."}),
    real(id="disk-df-workstation", category="disks", cmd="df -h", exit=0, duration=0.01,
         output=both("df_workstation"),
         notes=LOCALE_NOTE + " " + I5_NOTE + " Numbers differ from the historical en/fr capture (different "
               "machine: the i5 test box, 111G root disk, 87G free).",
         expected={"en": [r"\b685", r"\b29\b"], "fr": [r"\b685", r"\b29\b"],
                   "de": [r"\b87", r"\b18\b"], "es": [r"\b87", r"\b18\b"],
                   "pt": [r"\b87", r"\b18\b"], "ru": [r"\b87", r"\b18\b"]},
         forbidden=[r"tmpfs", r"efivarfs"],
         reference={"en": "Root 685G free of 953G, 29% used. Boot 69%.",
                    "fr": "Racine 685G libres sur 953G, 29 % utilisés. Boot 69 %.",
                    "de": "Root 87G frei von 111G, 18 % belegt.",
                    "es": "Raíz 87G libres de 111G, 18 % usados.",
                    "pt": "Raiz 87G livres de 111G, 18 % usados.",
                    "ru": "Корень: свободно 87G из 111G, занято 18 %."}),
    real(id="disk-df-hypervisor", category="disks", cmd="df -h", exit=0, duration=0.01,
         output=read("df_hypervisor.txt"),
         expected=[r"8[.,]9", r"\b91\b"], forbidden=[r"tmpfs", r"efivarfs"],
         reference={"en": "Root 91% full, 8.9G free. Backup disk 134G free, 70%.",
                    "fr": "Racine pleine à 91 %, 8,9G libres. Disque backup 134G libres, 70 %."}),
    real(id="disk-du-projects", category="disks", cmd="du -sh /home/user/projects/* 2>/dev/null | sort -h | tail",
         exit=0, duration=1.03, output=both("du_projects"),
         notes=LOCALE_NOTE + " " + I5_NOTE + " Real directory /root/*/* on the i5 (not /home/user/projects like "
               "the historical en/fr capture); folder names are the machine's own project checkouts for this "
               "benchmark work, not personal data.",
         expected={"en": [r"\b12 ?g", r"old.?inventory"], "fr": [r"\b12 ?g", r"old.?inventory"],
                   "de": [r"4[.,]0 ?g", r"models"], "es": [r"4[.,]0 ?g", r"models"],
                   "pt": [r"4[.,]0 ?g", r"models"], "ru": [r"4[.,]0 ?g", r"models"]},
         reference={"en": "Largest: OLD_INVENTORY 12G, kickstart-iso 7.9G, inventory 2.4G.",
                    "fr": "Plus gros : OLD_INVENTORY 12G, kickstart-iso 7,9G, inventory 2,4G.",
                    "de": "Größte: stephbench-ft/models 4,0G, tts-venv 199M, proj 119M.",
                    "es": "Más grande: stephbench-ft/models 4,0G, tts-venv 199M, proj 119M.",
                    "pt": "Maior: stephbench-ft/models 4,0G, tts-venv 199M, proj 119M.",
                    "ru": "Самый большой: stephbench-ft/models 4,0G, tts-venv 199M, proj 119M."}),
    real(id="hw-lspci-desktop", category="hardware", cmd="lspci", exit=0, duration=0.1,
         output=read("lspci.txt"),
         expected=[r"3060|rtx", r"realtek|8111|ethernet"], forbidden=[r"ryzen", r"core i\d", r"processor|processeur"],
         reference={"en": "GPU NVIDIA RTX 3060, Realtek RTL8111 Ethernet, AMD 500 Series chipset with USB and SATA.",
                    "fr": "GPU NVIDIA RTX 3060, Ethernet Realtek RTL8111, chipset AMD 500 avec USB et SATA.",
                    "de": "GPU NVIDIA RTX 3060, Realtek RTL8111 Ethernet, AMD-500-Serie-Chipsatz mit USB und SATA.",
                    "es": "GPU NVIDIA RTX 3060, Ethernet Realtek RTL8111, chipset AMD serie 500 con USB y SATA.",
                    "pt": "GPU NVIDIA RTX 3060, Ethernet Realtek RTL8111, chipset AMD 500 com USB e SATA.",
                    "ru": "GPU NVIDIA RTX 3060, Ethernet Realtek RTL8111, чипсет AMD серии 500 с USB и SATA."}),
    real(id="ctr-docker-ps-restarting", category="containers", cmd="docker ps", exit=0, duration=0.07,
         output=read("docker_ps.txt"),
         expected={"en": [r"vault", r"restart"], "fr": [r"vault", r"redemarr|restart"],
                   "de": [r"vault", r"startet.*neu|neustart|restart"], "es": [r"vault", r"reinici|restart"],
                   "pt": [r"vault", r"reinici|restart"], "ru": [r"vault", r"перезапуск|restart"]},
         forbidden=[r"\b(7|10) (containers|conteneurs|container|contenedores|contentores|контеинеров)\b"],
         reference={"en": "9 containers, 8 up; shop_vault restarting in a loop.",
                    "fr": "9 conteneurs, 8 actifs ; shop_vault redémarre en boucle.",
                    "de": "9 Container, 8 aktiv; shop_vault startet in einer Schleife neu.",
                    "es": "9 contenedores, 8 activos; shop_vault reiniciando en bucle.",
                    "pt": "9 contentores, 8 ativos; shop_vault a reiniciar em ciclo.",
                    "ru": "9 контейнеров, 8 активны; shop_vault перезапускается в цикле."}),
    real(id="list-ls-etc", category="long-lists", cmd="ls -la /etc | head -40", exit=0, duration=0.02,
         output=both("ls_etc"),
         notes=LOCALE_NOTE + " " + I5_NOTE + " Real /etc of the i5 (Debian), a different package set than the "
               "historical en/fr capture's machine (no abrt/anaconda: Fedora-only tools).",
         expected={"en": [r"\b40\b", r"abrt|adjtime|aliases|alsa|alternatives|bashrc"],
                   "fr": [r"\b40\b", r"abrt|adjtime|aliases|alsa|alternatives|bashrc"],
                   "de": [r"\b40\b", r"adduser|adjtime|alternatives|anacrontab|apache2"],
                   "es": [r"\b40\b", r"adduser|adjtime|alternatives|anacrontab|apache2"],
                   "pt": [r"\b40\b", r"adduser|adjtime|alternatives|anacrontab|apache2"],
                   "ru": [r"\b40\b", r"adduser|adjtime|alternatives|anacrontab|apache2"]},
         reference={"en": "40 lines of /etc entries: abrt, alsa, bashrc.",
                    "fr": "40 lignes d'entrées de /etc : abrt, alsa, bashrc.",
                    "de": "40 Zeilen von /etc: adduser.conf, adjtime, alternatives.",
                    "es": "40 líneas de /etc: adduser.conf, adjtime, alternatives.",
                    "pt": "40 linhas de /etc: adduser.conf, adjtime, alternatives.",
                    "ru": "40 строк /etc: adduser.conf, adjtime, alternatives."}),
    real(id="list-find-python-docs", category="long-lists", cmd="find /usr/share/doc -maxdepth 1 -name 'py*' | head -20",
         exit=0, duration=0.01, output=read("find_doc.txt"),
         expected=[r"\b20\b", r"python"],
         reference={"en": "20 Python doc folders: python-systemd, python3-attrs, python3-click.",
                    "fr": "20 dossiers de doc Python : python-systemd, python3-attrs, python3-click.",
                    "de": "20 Python-Doku-Ordner: python-systemd, python3-attrs, python3-click.",
                    "es": "20 carpetas de documentación Python: python-systemd, python3-attrs, python3-click.",
                    "pt": "20 pastas de documentação Python: python-systemd, python3-attrs, python3-click.",
                    "ru": "20 папок документации Python: python-systemd, python3-attrs, python3-click."}),
    real(id="list-passwd-accounts", category="long-lists", cmd="sort /etc/passwd | cut -d: -f1 | head -30",
         exit=0, duration=0.01, output=read("passwd_users.txt"),
         expected=[r"\b30\b", r"abrt|\badm\b|akmods|apache|avahi"],
         reference={"en": "30 accounts: abrt, adm, akmods.", "fr": "30 comptes : abrt, adm, akmods.",
                    "de": "30 Konten: abrt, adm, akmods.", "es": "30 cuentas: abrt, adm, akmods.",
                    "pt": "30 contas: abrt, adm, akmods.", "ru": "30 учётных записей: abrt, adm, akmods."}),
    real(id="list-grep-functions", category="long-lists", cmd="grep -rn 'def ' /home/user/projects/voice-cli/src/voice/llm.py",
         exit=0, duration=0.0, output=read("grep_def.txt"),
         expected=[r"\b8\b", r"ensure_server|stream|complete|healthy|__init__"],
         reference={"en": "8 functions in llm.py: __init__, healthy, ensure_server.",
                    "fr": "8 fonctions dans llm.py : __init__, healthy, ensure_server.",
                    "de": "8 Funktionen in llm.py: __init__, healthy, ensure_server.",
                    "es": "8 funciones en llm.py: __init__, healthy, ensure_server.",
                    "pt": "8 funções em llm.py: __init__, healthy, ensure_server.",
                    "ru": "8 функций в llm.py: __init__, healthy, ensure_server."}),
    real(id="qa-real-build-cause", category="history-qa", task="qa", history=HISTORY,
         question={"en": "Why did the build fail?", "fr": "Pourquoi le build a planté ?",
                   "de": "Warum ist der Build fehlgeschlagen?", "es": "¿Por qué falló el build?",
                   "pt": "Porque é que o build falhou?", "ru": "Почему сборка не удалась?"},
         expected=[r"titel", r"title"],
         reference={"en": "Header.tsx line 42: titel does not exist, use title.",
                    "fr": "Header.tsx ligne 42 : titel n'existe pas, utiliser title.",
                    "de": "Header.tsx Zeile 42: titel existiert nicht, title verwenden.",
                    "es": "Header.tsx línea 42: titel no existe, usar title.",
                    "pt": "Header.tsx linha 42: titel não existe, usar title.",
                    "ru": "Header.tsx строка 42: titel не существует, использовать title."}),
    real(id="qa-real-disk-space", category="history-qa", task="qa", history=HISTORY,
         question={"en": "How much space is left on the disk?", "fr": "Il me reste combien de place sur le disque ?",
                   "de": "Wie viel Speicherplatz ist noch auf der Festplatte frei?",
                   "es": "¿Cuánto espacio queda en el disco?", "pt": "Quanto espaço resta no disco?",
                   "ru": "Сколько места осталось на диске?"},
         expected=[r"8[.,]9"],
         reference={"en": "Root 8.9G free, 91% used.", "fr": "Racine 8,9G libres, 91 % utilisés.",
                    "de": "Root 8,9G frei, 91 % belegt.", "es": "Raíz 8,9G libres, 91 % usados.",
                    "pt": "Raiz 8,9G livres, 91 % usados.", "ru": "Корень: свободно 8,9G, занято 91 %."}),
    real(id="qa-real-python-version", category="history-qa", task="qa", history=HISTORY,
         question={"en": "Which Python version is installed?", "fr": "Quelle version de Python est installée ?",
                   "de": "Welche Python-Version ist installiert?", "es": "¿Qué versión de Python está instalada?",
                   "pt": "Que versão de Python está instalada?", "ru": "Какая версия Python установлена?"},
         expected=NOT_IN_HISTORY, forbidden=[r"\b3\.\d+"],
         reference={"en": "Not in the history.", "fr": "Pas dans l'historique.", "de": "Nicht im Verlauf.",
                    "es": "No está en el historial.", "pt": "Não está no histórico.", "ru": "Нет в истории."}),
]
