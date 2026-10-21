"""D6, lot D : réseau, ressources, services et bases dits en code par `resolve()`.

Chaque règle suit un format documenté de l'outil ; la provenance est notée au-dessus de
chaque groupe (documentation, puis exemple du split DEV du banc v3 qui l'a montrée).
Les sorties ci-dessous sont écrites à la main dans ces formats, jamais copiées du split TEST.
"""

import pytest

from steph.digest import resolve

NBSP = "\xa0"

# ---------------------------------------------------------------- wget
# Manuel GNU Wget : bilan « Downloaded: N files, S in T (R) » après plusieurs URL,
# « ERROR NNN: Reason. » par échec, « 'f' saved [n/n] » par fichier. Traductions gettext
# à espaces insécables (« Téléchargés : 4 fichiers »). DEV : v3-network-transfer-0001,
# 0005, 0016, 0037, 0039.

WGET_FR_MULTI = (
    "--2026-09-28 07:43:35--  https://mirror.example.org/dist/v2/SUMS.txt\n"
    "Résolution de mirror.example.org (mirror.example.org)… 203.0.113.6\n"
    "requête HTTP transmise, en attente de la réponse… 200 OK\n"
    f"Taille{NBSP}: 3777 (3,7K) [text/plain]\n"
    f"Sauvegarde en{NBSP}: «{NBSP}SUMS.txt{NBSP}»\n\n"
    f"2026-09-28 07:43:35 (1,32 MB/s) — «{NBSP}SUMS.txt{NBSP}» sauvegardé [3777/3777]\n\n"
    "--2026-09-28 07:43:35--  https://mirror.example.org/dist/v1/SUMS.txt\n"
    "requête HTTP transmise, en attente de la réponse… 200 OK\n"
    f"2026-09-28 07:43:35 (2,1 MB/s) — «{NBSP}SUMS.txt.1{NBSP}» sauvegardé [3153/3153]\n\n"
    "--2026-09-28 07:43:35--  https://mirror.example.org/dist/v0/OLD.txt\n"
    "requête HTTP transmise, en attente de la réponse… 404 Not Found\n"
    f"2026-09-28 07:43:36 erreur 404{NBSP}: Not Found.\n\n"
    "Terminé — 2026-09-28 07:43:36 —\n"
    f"Temps total effectif{NBSP}: 0,5s\n"
    f"Téléchargés{NBSP}: 2{NBSP}fichiers, 6,8K en 0,003s (3,59 MB/s)\n"
)

WGET_EN_MULTI = (
    "--2026-09-28 07:43:36--  https://mirrors.example.org/gnu/a-1.0.tar.xz.sig\n"
    "HTTP request sent, awaiting response... 200 OK\n"
    "2026-09-28 07:43:37 (22.6 MB/s) - 'a-1.0.tar.xz.sig' saved [833/833]\n\n"
    "--2026-09-28 07:43:37--  https://mirrors.example.org/gnu/b-9.9.tar.xz.sig\n"
    "HTTP request sent, awaiting response... 404 Not Found\n"
    "2026-09-28 07:43:40 ERROR 404: Not Found.\n\n"
    "--2026-09-28 07:43:40--  https://mirrors.example.org/gnu/c-2.0.tar.xz.sig\n"
    "HTTP request sent, awaiting response... 404 Not Found\n"
    "2026-09-28 07:43:41 ERROR 404: Not Found.\n\n"
    "FINISHED --2026-09-28 07:43:41--\n"
    "Total wall clock time: 4.8s\n"
    "Downloaded: 1 files, 833 in 0s (19.6 MB/s)\n"
)


def test_wget_french_summary_with_non_breaking_spaces_and_http_error():
    cmd = "wget https://mirror.example.org/dist/v2/SUMS.txt https://mirror.example.org/dist/v1/SUMS.txt " \
          "https://mirror.example.org/dist/v0/OLD.txt"
    assert resolve(cmd, 8, WGET_FR_MULTI) == \
        "Échec. 2 fichiers téléchargés, 6,8K au total. Erreur HTTP 404 sur OLD.txt."
    assert resolve(cmd, 8, WGET_FR_MULTI, "en") == \
        "Failed. 2 files downloaded, 6.8K total. HTTP error 404 on OLD.txt."


def test_wget_english_summary_counts_errors_and_agrees_in_number():
    cmd = "wget -i list.txt"
    assert resolve(cmd, 8, WGET_EN_MULTI) == \
        "Échec. 1 fichier téléchargé, 833 octets au total. 2 erreurs HTTP, dont 404 sur b-9.9.tar.xz.sig."
    assert resolve(cmd, 8, WGET_EN_MULTI, "en") == \
        "Failed. 1 file downloaded, 833 bytes total. 2 HTTP errors, including 404 on b-9.9.tar.xz.sig."


def test_wget_summary_success():
    out = WGET_EN_MULTI.split("--2026-09-28 07:43:37--")[0] + \
        "FINISHED --2026-09-28 07:43:41--\nDownloaded: 3 files, 2.5K in 0s (19.6 MB/s)\n"
    assert resolve("wget a b c", 0, out) == "3 fichiers téléchargés, 2,5K au total."


def test_wget_failure_without_http_error_line_is_left_to_the_model():
    out = WGET_EN_MULTI.replace("ERROR 404: Not Found.", "Unable to establish SSL connection.")
    assert resolve("wget -i list.txt", 4, out) is None


WGET_EN_SINGLE = (
    "--2026-09-28 04:06:40--  http://127.0.0.1:8081/releases/app-2.4.1.tar.gz\n"
    "Connecting to 127.0.0.1:8081... connected.\n"
    "HTTP request sent, awaiting response... 200 OK\n"
    "Length: 3145728 (3.0M) [application/gzip]\n"
    "Saving to: ‘app.tar.gz’\n\n"
    "     0K ........ ........ ........ 100%  985M=0.003s\n\n"
    "2026-09-28 04:06:40 (985 MB/s) - ‘app.tar.gz’ saved [3145728/3145728]\n"
)


def test_wget_single_file_saved():
    cmd = "wget -O app.tar.gz http://127.0.0.1:8081/releases/app-2.4.1.tar.gz"
    assert resolve(cmd, 0, WGET_EN_SINGLE) == "app.tar.gz téléchargé, 3,0M."
    assert resolve(cmd, 0, WGET_EN_SINGLE, "en") == "app.tar.gz downloaded, 3.0M."


def test_wget_single_file_french_output():
    out = (
        "--2026-09-28 04:06:40--  http://127.0.0.1:8081/app.tar.gz\n"
        "requête HTTP transmise, en attente de la réponse… 200 OK\n"
        f"Taille{NBSP}: 3145728 (3,0M) [application/gzip]\n"
        f"Sauvegarde en{NBSP}: «{NBSP}app.tar.gz{NBSP}»\n\n"
        f"2026-09-28 04:06:40 (985 MB/s) — «{NBSP}app.tar.gz{NBSP}» sauvegardé [3145728/3145728]\n"
    )
    assert resolve("wget http://127.0.0.1:8081/app.tar.gz", 0, out, "en") == "app.tar.gz downloaded, 3.0M."


def test_wget_unknown_length_says_bytes():
    out = WGET_EN_SINGLE.replace("Length: 3145728 (3.0M) [application/gzip]", "Length: unspecified [text/html]") \
        .replace("[3145728/3145728]", "[5120]")
    assert resolve("wget http://127.0.0.1:8081/", 0, out) == "app.tar.gz téléchargé, 5120 octets."


def test_wget_partial_file_is_left_to_the_model():
    out = WGET_EN_SINGLE.replace("[3145728/3145728]", "[1048576/3145728]")
    assert resolve("wget http://127.0.0.1:8081/x", 0, out) is None


def test_wget_single_http_error_names_the_resource():
    out = (
        "--2026-09-28 04:09:19--  http://127.0.0.1:8082/api/v1/admin\n"
        "Connexion à 127.0.0.1:8082… connecté.\n"
        "requête HTTP transmise, en attente de la réponse… 401 Unauthorized\n\n"
        "Échec d’authentification par identifiant et mot de passe.\n"
    )
    assert resolve("wget http://127.0.0.1:8082/api/v1/admin", 6, out) == "Échec. HTTP 401 Unauthorized sur admin."
    assert resolve("wget http://127.0.0.1:8082/api/v1/admin", 6, out, "en") == \
        "Failed. HTTP 401 Unauthorized on admin."


def test_wget_unresolved_host_french_and_english():
    fr = ("--2026-09-28 04:06:47--  http://mirror.example.invalid/debian/\n"
          "Résolution de mirror.example.invalid (mirror.example.invalid)… échec : Nom ou service inconnu.\n"
          f"wget : impossible de résoudre l’adresse de l’hôte «{NBSP}mirror.example.invalid{NBSP}»\n")
    en = "--2026-09-28 04:06:47--  http://mirror.example.invalid/\n" \
         "Resolving mirror.example.invalid... failed: Name or service not known.\n" \
         "wget: unable to resolve host address ‘mirror.example.invalid’\n"
    assert resolve("wget http://mirror.example.invalid/debian/", 4, fr) == \
        "Échec. Hôte mirror.example.invalid introuvable."
    assert resolve("wget http://mirror.example.invalid/", 4, en, "en") == "Failed. Host mirror.example.invalid not found."


def test_wget_connection_refused():
    out = ("--2026-09-28 04:06:47--  http://localhost:8080/\n"
           "Resolving localhost (localhost)... 127.0.0.1\n"
           "Connecting to localhost (localhost)|127.0.0.1|:8080... failed: Connection refused.\n")
    assert resolve("wget http://localhost:8080/", 4, out) == "Échec. Connexion refusée : localhost port 8080."


# ---------------------------------------------------------------- curl
# Documentation curl : -i et -v montrent la ligne de statut « HTTP/x NNN Reason » (préfixée
# par « < » sous -v), la dernière est celle de la réponse finale ; barre de progression
# « % Total % Received % Xferd ». DEV : v3-network-transfer-0019, 0023, 0027.

CURL_METER = ("  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current\n"
              "                                 Dload  Upload   Total   Spent    Left  Speed\n")


def test_curl_include_says_final_status_and_resource():
    out = CURL_METER + (
        "100    70  100    70    0     0   111k      0 --:--:-- --:--:-- --:--:-- 70000\n"
        "HTTP/1.0 404 Not Found\r\nServer: api/0.9\r\nContent-Type: application/json\r\n\r\n"
        '{"error": "not_found"}\n')
    cmd = "curl -i http://localhost:18082/api/v1/orders/88412"
    assert resolve(cmd, 0, out) == "Réponse HTTP 404 Not Found de localhost, ressource 88412."
    assert resolve(cmd, 0, out, "en") == "HTTP 404 Not Found from localhost, resource 88412."


def test_curl_verbose_takes_the_last_status_and_received_size():
    out = CURL_METER + (
        "* Host example.org:443 was resolved.\n"
        "> GET / HTTP/2\r\n> Host: example.org\r\n>\r\n"
        "< HTTP/2 301 \r\n< location: https://www.example.org/\r\n<\r\n"
        "> GET / HTTP/2\r\n"
        "< HTTP/2 200 \r\n< content-length: 6153\r\n<\r\n"
        "100  6153  100  6153    0     0  75574      0 --:--:-- --:--:-- --:--:-- 75962\n"
        "* Connection #0 to host example.org left intact\n")
    cmd = "curl -vL -o /dev/null https://example.org/"
    assert resolve(cmd, 0, out) == "Réponse HTTP 200 de example.org, 6153 octets reçus."
    assert resolve(cmd, 0, out, "en") == "HTTP 200 from example.org, 6153 bytes received."


def test_curl_status_behind_a_pipe_is_left_to_the_model():
    assert resolve("curl -i https://example.org/ | head -5", 0, "HTTP/2 200\r\ncontent-type: text/html\r\n") is None


def test_curl_progress_meter_only_download():
    out = CURL_METER + "100 5120k  100 5120k    0     0   276M      0 --:--:-- --:--:-- --:--:--  277M\n"
    assert resolve("curl -O http://localhost:18080/releases/tool-1.8.0.zip", 0, out) == \
        "tool-1.8.0.zip téléchargé, 5120k."
    assert resolve("curl -o /tmp/t.zip http://localhost:18080/t", 0, out, "en") == "t.zip downloaded, 5120k."
    assert resolve("curl http://localhost:18080/t -o /dev/null", 0, out) == "Transfert complet, 5120k reçus."


def test_curl_incomplete_meter_is_left_to_the_model():
    out = CURL_METER + " 42 5120k   42 2150k    0     0   276M      0 --:--:-- --:--:-- --:--:--  277M\n"
    assert resolve("curl -O http://localhost:18080/t.zip", 0, out) is None


# ---------------------------------------------------------------- ss -l
# ss(8) : colonnes State, Recv-Q, Send-Q, Local Address:Port, Peer Address:Port, Process ;
# -p ajoute users:(("nom",pid=N,fd=N)). DEV : v3-network-0003.

SS_TLNP = (
    "State  Recv-Q Send-Q Local Address:Port Peer Address:PortProcess\n"
    'LISTEN 0      5          127.0.0.1:8081      0.0.0.0:*    users:(("python3",pid=2067804,fd=3))\n'
    'LISTEN 0      128          0.0.0.0:22        0.0.0.0:*    users:(("sshd",pid=1601,fd=6))\n'
    'LISTEN 0      512        127.0.0.1:8961      0.0.0.0:*    users:(("llama-server",pid=2069987,fd=3))\n'
    'LISTEN 0      512        127.0.0.1:8894      0.0.0.0:*    users:(("llama-server",pid=2067610,fd=30))\n'
    'LISTEN 0      5          127.0.0.1:8443      0.0.0.0:*    users:(("python3",pid=2067808,fd=3))\n'
    'LISTEN 0      128             [::]:22           [::]:*    users:(("sshd",pid=1601,fd=7))\n'
)


def test_ss_listening_groups_ports_by_process():
    assert resolve("ss -tlnp", 0, SS_TLNP) == \
        "5 ports en écoute : sshd sur 22, python3 sur 8081 et 8443, llama-server sur 8894 et 8961."
    assert resolve("sudo ss -tlnp", 0, SS_TLNP, "en") == \
        "5 listening ports: sshd on 22, python3 on 8081 and 8443, llama-server on 8894 and 8961."


def test_ss_without_process_column_and_netid():
    out = ("Netid State  Recv-Q Send-Q Local Address:Port Peer Address:Port\n"
           "udp   UNCONN 0      0          127.0.0.53%lo:53        0.0.0.0:*\n"
           "tcp   LISTEN 0      128            0.0.0.0:22        0.0.0.0:*\n"
           "tcp   LISTEN 0      244          127.0.0.1:5432      0.0.0.0:*\n")
    assert resolve("ss -tulnw", 0, out) == "3 ports en écoute : 22, 53 et 5432."


def test_ss_single_port_agrees():
    out = ("State  Recv-Q Send-Q Local Address:Port Peer Address:PortProcess\n"
           "LISTEN 0      128          0.0.0.0:22        0.0.0.0:*\n")
    assert resolve("ss -tln", 0, out, "en") == "1 listening port: 22."


def test_ss_without_listening_option_is_left_to_the_model():
    out = SS_TLNP.replace("LISTEN", "ESTAB ")
    assert resolve("ss -tnp", 0, out) is None


# ---------------------------------------------------------------- ip route
# ip-route(8) : « default via GW dev IF », drapeau « linkdown ». DEV : v3-network-0013.

IP_ROUTE = ("default via 192.0.2.254 dev wlp2s0 proto dhcp src 192.0.2.59 metric 600\n"
            "172.17.0.0/16 dev docker0 proto kernel scope link src 172.17.0.1 linkdown\n"
            "192.0.2.0/24 dev wlp2s0 proto kernel scope link src 192.0.2.59 metric 600\n")


def test_ip_route_default_gateway_and_link_down():
    assert resolve("ip route", 0, IP_ROUTE) == "Passerelle par défaut 192.0.2.254 sur wlp2s0. docker0 : sans lien."
    assert resolve("ip r show", 0, IP_ROUTE, "en") == "Default gateway 192.0.2.254 on wlp2s0. docker0: link down."


def test_ip_route_several_defaults_and_none():
    out = ("default via 10.0.0.1 dev eth0 proto dhcp metric 100\n"
           "default via 10.0.1.1 dev wlan0 proto dhcp metric 600\n"
           "10.0.0.0/24 dev eth0 proto kernel scope link src 10.0.0.5 metric 100\n")
    assert resolve("ip -4 route", 0, out) == "Passerelle par défaut 10.0.0.1 sur eth0, 2 routes par défaut en tout."
    assert resolve("ip route", 0, out.split("\n", 2)[2] + "10.0.1.0/24 dev wlan0 scope link\n") == \
        "Aucune route par défaut."


def test_ip_route_filtered_is_left_to_the_model():
    assert resolve("ip route get 198.51.100.7", 0, "198.51.100.7 via 10.0.0.1 dev eth0 src 10.0.0.5 uid 1000\n    cache\n") is None
    assert resolve("ip route show dev eth0", 0, IP_ROUTE) is None


# ---------------------------------------------------------------- nmcli
# nmcli(1) : colonnes alignées DEVICE TYPE STATE CONNECTION et NAME UUID TYPE DEVICE ;
# états traduits par gettext. DEV : v3-network-0008, 0020.

NMCLI_DEV = ("DEVICE             TYPE      STATE                  CONNECTION\n"
             "wlp0s20f3          wifi      connecté               office1\n"
             "lo                 loopback  connecté (en externe)  lo\n"
             "p2p-dev-wlp0s20f3  wifi-p2p  déconnecté             --\n")


def test_nmcli_device_status_maps_states_to_the_session_language():
    assert resolve("nmcli device status", 0, NMCLI_DEV) == \
        "wlp0s20f3 connecté à office1 et p2p-dev-wlp0s20f3 déconnecté."
    assert resolve("nmcli device status", 0, NMCLI_DEV, "en") == \
        "wlp0s20f3 connected to office1 and p2p-dev-wlp0s20f3 disconnected."


def test_nmcli_unknown_state_is_left_to_the_model():
    assert resolve("nmcli device", 0, NMCLI_DEV.replace("déconnecté ", "configuring")) is None


def test_nmcli_connection_show():
    out = ("NAME                UUID                                  TYPE      DEVICE\n"
           "homenet             00000000-0000-0000-0000-000000000001  wifi      wlp2s0\n"
           "docker0             00000000-0000-0000-0000-000000000002  bridge    docker0\n"
           "Wired connection 1  00000000-0000-0000-0000-000000000004  ethernet  --\n")
    assert resolve("nmcli connection show", 0, out) == \
        "3 connexions : homenet sur wlp2s0, docker0 sur docker0 et Wired connection 1 inactive."
    assert resolve("nmcli con show", 0, out, "en") == \
        "3 connections: homenet on wlp2s0, docker0 on docker0 and Wired connection 1 inactive."


# ---------------------------------------------------------------- top -b
# procps top(1) : en-tête « top - HH:MM:SS up …, N users, load average: a, b, c » puis
# « Tasks: N total, R running ». DEV : v3-processes-0029.

TOP = ("top - 07:22:48 up 5 days, 14:50,  5 users,  load average: 2.49, 1.78, 1.08\n"
       "Tasks: 468 total,   2 running, 466 sleeping,   0 stopped,   0 zombie\n"
       "%Cpu(s):  5.7 us,  1.0 sy,  0.0 ni, 93.3 id,  0.0 wa,  0.0 hi,  0.0 si,  0.0 st\n"
       "MiB Mem :  31743.3 total,  16375.9 free,   8221.1 used,   7893.3 buff/cache\n\n"
       "    PID USER      PR  NI    VIRT    RES    SHR S  %CPU  %MEM     TIME+ COMMAND\n"
       "2292411 root      20   0 5820084   2.4g 204532 S  60.0   7.6   0:40.80 llama-s+\n")


def test_top_batch_header():
    assert resolve("top -b -n 1 -o %MEM | head -n 75", 0, TOP) == \
        "Allumé depuis 5 jours 14 h 50, 468 tâches dont 2 en cours, charge 2,49."
    assert resolve("top -bn1", 0, TOP, "en") == "Up 5 days 14:50, 468 tasks, 2 running, load 2.49."


@pytest.mark.parametrize("up, fr", [
    ("12:09", "12 h 09"),
    ("45 min", "45 min"),
    ("1 day,  3:04", "1 jour 3 h 04"),
])
def test_top_uptime_forms(up, fr):
    out = TOP.replace("5 days, 14:50", up).replace("468 total,   2 running", "1 total,   1 running")
    assert resolve("top -b -n 1", 0, out) == f"Allumé depuis {fr}, 1 tâche dont 1 en cours, charge 2,49."


# ---------------------------------------------------------------- mémoire macOS et vmstat -s
# memory_pressure(1) : « System-wide memory free percentage: N% », « Pages free: N ».
# vmstat(8) -s : « N K total memory », traduit « N K mémoire totale ». DEV :
# v3-disk-memory-0032, 0035.

def test_memory_pressure():
    out = ("The system has 19327352832 (1179648 pages with a page size of 16384).\n\nStats: \n"
           "Pages free: 5405 \nPages purgeable: 2 \n\nSwap I/O:\nSwapins: 10951562 \n\n"
           "System-wide memory free percentage: 44%\n")
    assert resolve("memory_pressure", 0, out) == "Mémoire libre à 44 %, 5405 pages libres."
    assert resolve("memory_pressure", 0, out, "en") == "44% memory free, 5405 free pages."


def test_vmstat_s_french_and_english_output():
    fr = ("     32505148 K mémoire totale\n     22497708 K mémoire utilisée\n"
          "      1909280 K mémoire libre\n     33190908 K échange total\n")
    en = ("     16303736 K total memory\n      5012345 K used memory\n"
          "       524288 K free memory\n      2097148 K total swap\n")
    assert resolve("vmstat -s", 0, fr) == "Mémoire totale 31,0 Go, libre 1,8 Go."
    assert resolve("vmstat -s", 0, en, "en") == "Total memory 15.5 GB, free 512 MB."


# ---------------------------------------------------------------- du -c
# du(1) : ligne finale « S total » avec -c ; erreurs « du: cannot read directory 'd':
# Permission denied » (traduites). DEV : v3-disk-memory-0034.

DU_FAIL = ("du: impossible de lire le répertoire '/var/lib/NetworkManager': Permission non accordée\n"
           "4,0K\t/var/lib/NetworkManager\n8,0K\t/var/lib/dbus\n"
           "du: impossible de lire le répertoire '/var/log/audit': Permission non accordée\n"
           "4,0K\t/var/log/audit\n296M\t/var/log/journal\n315M\t/var/log\n347M\t/var/lib\n662M\ttotal\n")


def test_du_total_with_read_errors():
    cmd = "du -ch /var/lib /var/log --max-depth=1"
    assert resolve(cmd, 1, DU_FAIL) == "Échec. Total 662M, 2 erreurs, dont NetworkManager : permission refusée."
    assert resolve(cmd, 1, DU_FAIL, "en") == \
        "Failed. Total 662M, 2 errors, including NetworkManager: permission denied."


def test_du_total_success_converts_decimal_separator():
    out = "1,2G\tnode_modules\n40K\tsrc\n1,2G\ttotal\n"
    assert resolve("du -shc node_modules src", 0, out) == "Total 1,2G."
    assert resolve("du -shc node_modules src", 0, out, "en") == "Total 1.2G."


# ---------------------------------------------------------------- lsof
# lsof(8) : en-tête « COMMAND PID USER FD TYPE DEVICE SIZE/OFF NODE NAME », « (LISTEN) »
# pour un socket en écoute ; avertissements « lsof: WARNING: » en tête. DEV :
# v3-processes-0002, 0010.

def test_lsof_file_with_warning():
    out = ("lsof: WARNING: can't stat() fuse.portal file system /run/user/1000/doc\n"
           "      Output information may be incomplete.\n"
           "COMMAND   PID USER FD   TYPE DEVICE SIZE/OFF NODE NAME\n"
           "tail    38981 root 3r   REG   0,37        0  843 /tmp/app.log\n"
           "less    38990 root 4r   REG   0,37        0  843 /tmp/app.log\n")
    assert resolve("lsof /tmp/app.log", 0, out) == "app.log ouvert par tail, PID 38981 et less, PID 38990."
    assert resolve("lsof /tmp/app.log", 0, out, "en") == "app.log open by tail, PID 38981 and less, PID 38990."


def test_lsof_port_listening():
    out = ("COMMAND   PID USER FD   TYPE DEVICE SIZE/OFF NODE NAME\n"
           "python3 38928 root 3u  IPv4 458466      0t0  TCP *:8765 (LISTEN)\n"
           "python3 38928 root 4u  IPv6 458467      0t0  TCP *:8765 (LISTEN)\n")
    assert resolve("lsof -i :8765 -P -n", 0, out) == "Port 8765 : python3, PID 38928, en écoute."
    assert resolve("lsof -i:8765", 0, out, "en") == "Port 8765: python3, PID 38928, listening."


def test_lsof_other_selections_are_left_to_the_model():
    out = "COMMAND   PID USER FD   TYPE DEVICE SIZE/OFF NODE NAME\ntail 1 root 3r REG 0,37 0 843 /tmp/a\n"
    assert resolve("lsof -u root", 0, out) is None


# ---------------------------------------------------------------- disques
# diskutil(8) info : « Device / Media Name », « Disk Size », « SMART Status »,
# « Device Location », « Solid State ». smartctl(8) -H : « SMART overall-health
# self-assessment test result: PASSED », SCSI « SMART Health Status: OK ». DEV :
# v3-disk-memory-0030, 0008.

DISKUTIL = ("   Device Identifier:         disk0\n   Device Node:               /dev/disk0\n"
            "   Device / Media Name:       APPLE SSD AP0512Z\n\n"
            "   SMART Status:              Verified\n\n"
            "   Disk Size:                 500.3 GB (500277792768 Bytes) (exactly 977105064 512-Byte-Units)\n"
            "   Device Location:           Internal\n   Solid State:               Yes\n")


def test_diskutil_info():
    assert resolve("diskutil info disk0", 0, DISKUTIL) == \
        "disk0 : APPLE SSD AP0512Z, 500,3 Go, interne, SSD, SMART vérifié."
    assert resolve("diskutil info disk0", 0, DISKUTIL, "en") == \
        "disk0: APPLE SSD AP0512Z, 500.3 GB, internal, SSD, SMART verified."


def test_diskutil_info_unknown_smart_value_is_omitted():
    out = DISKUTIL.replace("Verified", "Mystery").replace("Solid State:               Yes", "Solid State: No")
    assert resolve("diskutil info disk0", 0, out) == "disk0 : APPLE SSD AP0512Z, 500,3 Go, interne."


SMART_HEAD = ("smartctl 7.4 2023-08-01 r5530 [x86_64-linux-6.12] (local build)\n"
              "Copyright (C) 2002-23, Bruce Allen, Christian Franke, www.smartmontools.org\n\n"
              "=== START OF READ SMART DATA SECTION ===\n")


def test_smartctl_health_passed_and_failed():
    assert resolve("sudo smartctl -H /dev/sda", 0, SMART_HEAD + "SMART overall-health self-assessment test result: PASSED\n") \
        == "Santé SMART de sda : test réussi."
    assert resolve("smartctl -H /dev/nvme0", 0, SMART_HEAD + "SMART Health Status: OK\n", "en") == \
        "SMART health of nvme0: passed."
    failed = SMART_HEAD + ("SMART overall-health self-assessment test result: FAILED!\n"
                           "Drive failure expected in less than 24 hours. SAVE ALL DATA.\n")
    assert resolve("smartctl -H /dev/sdb", 8, failed) == "Santé SMART de sdb : échec, défaillance annoncée."
    assert resolve("smartctl -H /dev/sdb", 8, failed, "en") == "SMART health of sdb: FAILED, drive failure predicted."


def test_smartctl_passed_with_error_bits_is_left_to_the_model():
    assert resolve("smartctl -H /dev/sda", 4, SMART_HEAD + "SMART overall-health self-assessment test result: PASSED\n") \
        is None


# ---------------------------------------------------------------- ps -u
# procps ps(1) : « error: user name does not exist », traduit « erreur: le nom
# d'utilisateur n'existe pas », suivi de l'aide. DEV : v3-processes-0019.

def test_ps_unknown_user():
    out = ("erreur: le nom d'utilisateur n'existe pas\n\nUsage:\n ps [options]\n\n"
           " Essayez 'ps --aide <simple|liste|sortie|threads|divers|tous>'\n")
    assert resolve("ps -u postgres", 1, out) == "Échec. Utilisateur postgres inexistant."
    en = "error: user name does not exist\n\nUsage:\n ps [options]\n\n Try 'ps --help <simple|list|output|threads|misc|all>'\n"
    assert resolve("ps -U postgres -o pid,cmd", 1, en, "en") == "Failed. User postgres does not exist."


# ---------------------------------------------------------------- services
# systemctl(1) list-timers : lignes triées par prochaine échéance, bilan « N timers
# listed. » ; is-enabled : un état par unité, dans l'ordre ; brew services list : colonnes
# Name Status User File. DEV : v3-services-logs-0002, 0003, v3-packages-system-0029.

TIMERS = (
    "NEXT                             LEFT LAST                               PASSED UNIT                         ACTIVATES\n"
    "Mon 2026-09-28 04:00:00 CEST     8min Mon 2026-09-28 03:50:07 CEST 1min 30s ago sysstat-collect.timer        sysstat-collect.service\n"
    "Mon 2026-09-28 06:32:11 CEST 2h 40min Sun 2026-09-27 06:12:15 CEST            - apt-daily-upgrade.timer      apt-daily-upgrade.service\n"
    "Sun 2026-10-04 03:10:20 CEST   5 days Sun 2026-09-27 03:11:08 CEST            - e2scrub_all.timer            e2scrub_all.service\n"
    "\n3 timers listed.\nPass --all to see loaded but inactive timers, too.\n")


def test_systemctl_list_timers():
    assert resolve("systemctl list-timers --no-pager", 0, TIMERS) == \
        "3 minuteries, la prochaine dans 8 min : sysstat-collect."
    assert resolve("systemctl list-timers", 0, TIMERS, "en") == "3 timers, the next in 8 min: sysstat-collect."
    later = TIMERS.replace("     8min", " 2h 40min", 1)
    assert resolve("systemctl list-timers", 0, later) == "3 minuteries, la prochaine dans 2 h 40 min : sysstat-collect."


def test_systemctl_list_timers_none():
    out = "NEXT LEFT LAST PASSED UNIT ACTIVATES\n\n0 timers listed.\nPass --all to see loaded but inactive timers, too.\n"
    assert resolve("systemctl list-timers", 0, out) == "Aucune minuterie."


def test_systemctl_is_enabled_groups_states():
    cmd = "systemctl is-enabled ssh smartd docker nginx.service"
    out = "enabled\nalias\nenabled\nnot-found\n"
    assert resolve(cmd, 0, out) == "Activés : ssh et docker. Alias : smartd. Introuvable : nginx."
    assert resolve(cmd, 0, out, "en") == "Enabled: ssh and docker. Alias: smartd. Not found: nginx."


def test_systemctl_is_enabled_mismatch_is_left_to_the_model():
    out = "enabled\nFailed to get unit file state for nginx.service: No such file or directory\n"
    assert resolve("systemctl is-enabled ssh nginx", 1, out) is None
    assert resolve("systemctl is-enabled ssh docker", 0, "enabled-runtime\nenabled\n") is None


BREW = ("Name          Status  User File\n"
        "mysql         error   256 root ~/Library/LaunchAgents/homebrew.mxcl.mysql.plist\n"
        "postgresql@14 started me   ~/Library/LaunchAgents/homebrew.mxcl.postgresql@14.plist\n"
        "redis         none\n"
        "unbound       stopped\n")


def test_brew_services_list():
    assert resolve("brew services list", 0, BREW) == \
        "4 services, 1 démarré : postgresql@14. 1 en erreur : mysql."
    assert resolve("brew services list", 0, BREW, "en") == \
        "4 services, 1 started: postgresql@14. 1 with an error: mysql."
    idle = "Name    Status User File\nredis   none\nunbound none\n"
    assert resolve("brew services", 0, idle) == "2 services, aucun démarré : redis et unbound."
    assert resolve("brew services list", 0, idle, "en") == "2 services, none started: redis and unbound."
    many = "Name Status User File\n" + "".join(f"s{i} none\n" for i in range(12))
    assert resolve("brew services list", 0, many) == \
        "12 services, aucun démarré : s0, s1, s2, s3, s4, et 7 autres."


def test_lists_past_the_cap_end_with_a_count():
    rows = "".join(f"p{i}    {100 + i} root 3r REG 0,37 0 843 /tmp/a\n" for i in range(6))
    out = "COMMAND   PID USER FD   TYPE DEVICE SIZE/OFF NODE NAME\n" + rows
    assert resolve("lsof /tmp/a", 0, out) == \
        "a ouvert par p0, PID 100 ; p1, PID 101 ; p2, PID 102 ; p3, PID 103, et 2 autres."


# ---------------------------------------------------------------- bases de données
# libpq (PostgreSQL 14+) : « psql: error: connection to server at "h" (a), port P failed:
# … », « FATAL:  database "d" does not exist » ; messages serveur « ERROR:  relation "t"
# does not exist », « syntax error at or near "x" » ; bilan « (N rows) ». sqlite3 :
# « Parse error …: near "x": syntax error », « no such table: t ». DEV : v3-data-0010,
# 0011, 0016, 0017, 0020.

def test_psql_connection_refused_on_every_address():
    out = ('psql: error: connection to server at "localhost" (::1), port 5433 failed: Connection refused\n'
           "\tIs the server running on that host and accepting TCP/IP connections?\n"
           'connection to server at "localhost" (127.0.0.1), port 5433 failed: Connection refused\n'
           "\tIs the server running on that host and accepting TCP/IP connections?\n")
    assert resolve("psql -h localhost -p 5433 -U app shop", 2, out) == "Échec. Connexion refusée : localhost port 5433."


def test_psql_missing_database_wins_over_a_refused_address():
    out = ('psql: error: connection to server at "localhost" (::1), port 5432 failed: Connection refused\n'
           "\tIs the server running on that host and accepting TCP/IP connections?\n"
           'connection to server at "localhost" (127.0.0.1), port 5432 failed: FATAL:  database "shop_prod" does not exist\n')
    assert resolve("psql -h localhost -U app shop_prod", 2, out) == "Échec. Base shop_prod inexistante sur localhost."
    assert resolve("psql -h localhost -U app shop_prod", 2, out, "en") == \
        "Failed. Database shop_prod does not exist on localhost."


def test_psql_password_and_socket():
    pw = 'psql: error: connection to server at "db.example.org" (10.0.0.4), port 5432 failed: FATAL:  password authentication failed for user "app"\n'
    assert resolve("psql -h db.example.org -U app", 2, pw) == "Échec. Mot de passe refusé pour app sur db.example.org."
    sock = ('psql: error: connection to server on socket "/var/run/postgresql/.s.PGSQL.5432" failed: '
            "No such file or directory\n\tIs the server running locally and accepting connections on that socket?\n")
    assert resolve("psql", 2, sock) == "Échec. Serveur PostgreSQL local injoignable, socket du port 5432 absent."
    assert resolve("psql", 2, sock, "en") == "Failed. Local PostgreSQL server unreachable, no socket for port 5432."


def test_psql_server_errors():
    rel = 'ERROR:  relation "ordres" does not exist\nLINE 1: SELECT * FROM ordres;\n                      ^\n'
    assert resolve("psql shop -c 'SELECT * FROM ordres;'", 1, rel) == "Échec. Table ou vue ordres introuvable."
    syn = 'ERROR:  syntax error at or near "FORM"\nLINE 1: SELECT status FORM orders;\n                      ^\n'
    assert resolve("psql shop -c 'SELECT status FORM orders;'", 1, syn, "en") == "Failed. SQL syntax error near FORM."


def test_psql_rows_are_read_for_small_tables():
    out = ("  status  | count \n----------+-------\n shipped  |  1437\n paid     |  1374\n"
           " refunded |   703\n pending  |   703\n(4 rows)\n\n")
    cmd = "psql -h localhost -U app shop -c 'SELECT status, count(*) FROM orders GROUP BY status;'"
    assert resolve(cmd, 0, out) == "4 lignes : shipped 1437, paid 1374, refunded 703, pending 703."
    assert resolve(cmd, 0, out, "en") == "4 rows: shipped 1437, paid 1374, refunded 703, pending 703."


def test_psql_rows_wide_or_empty():
    wide = (" id | name | email \n----+------+-------\n  1 | a    | x@y\n  2 | b    | z@y\n  3 | c    | w@y\n"
            "  4 | d    | v@y\n  5 | e    | u@y\n  6 | f    | t@y\n  7 | g    | s@y\n(7 rows)\n")
    assert resolve("psql shop -c 'SELECT * FROM users'", 0, wide) == "7 lignes, colonnes id, name et email."
    assert resolve("psql shop -c 'SELECT 1 WHERE false'", 0, " ?column? \n----------\n(0 rows)\n\n") == "Aucune ligne."
    one = " n \n---\n 3\n(1 row)\n"
    assert resolve("psql shop -c 'SELECT 3 AS n'", 0, one, "en") == "1 row: 3."


def test_sqlite_errors():
    syn = ('Parse error in 2nd command line argument: near "orders": syntax error\n'
           "  SELECT status, count(*) FORM orders GROUP BY status;\n                 error here ---^\n")
    assert resolve("sqlite3 data/shop.db 'SELECT status, count(*) FORM orders;'", 1, syn) == \
        "Échec. Erreur de syntaxe SQL près de orders."
    old = 'Error: near line 3: no such table: customer\nError: near line 4: no such table: customer\nx\ny\n'
    assert resolve("sqlite3 shop.db < q.sql", 1, old, "en") == "Failed. Table customer not found."


def test_sqlite_other_error_is_left_to_the_model():
    out = "Runtime error near line 2: database is locked (5)\nfoo\nbar\nbaz\n"
    assert resolve("sqlite3 shop.db < q.sql", 1, out) is None


# ---------------------------------------------------------------- garde-fous trouvés à la relecture
# Relecture des phrases changées sur les corpus d'affinage et publics (ip route à six ponts
# docker, ss à 21 ports) et passe adverse sur chaque format.

def test_ip_route_caps_link_down_interfaces():
    out = IP_ROUTE + "".join(f"172.{18 + i}.0.0/16 dev br-{i:012x} proto kernel scope link src 172.{18 + i}.0.1 linkdown\n"
                             for i in range(4))
    assert resolve("ip route", 0, out) == ("Passerelle par défaut 192.0.2.254 sur wlp2s0. "
                                           "docker0, br-000000000000, br-000000000001, et 2 autres : sans lien.")


def test_ss_caps_listed_ports():
    rows = "".join(f"LISTEN 0      128          0.0.0.0:{p}        0.0.0.0:*\n" for p in (22, 80, 443, 631, 3000, 5432, 8080))
    out = "State  Recv-Q Send-Q Local Address:Port Peer Address:PortProcess\n" + rows
    assert resolve("ss -tln", 0, out) == "7 ports en écoute : 22, 80, 443, 631, 3000 et 5432, et 1 autre."


def test_wget_failure_with_a_silent_url_is_left_to_the_model():
    out = WGET_EN_MULTI.replace(
        "--2026-09-28 07:43:40--  https://mirrors.example.org/gnu/c-2.0.tar.xz.sig\n"
        "HTTP request sent, awaiting response... 404 Not Found\n"
        "2026-09-28 07:43:41 ERROR 404: Not Found.\n",
        "--2026-09-28 07:43:40--  https://other.example.invalid/c.sig\n"
        "Resolving other.example.invalid... failed: Name or service not known.\n"
        "wget: unable to resolve host address 'other.example.invalid'\n")
    assert resolve("wget -i list.txt", 4, out) is None


def test_curl_status_with_several_urls_is_left_to_the_model():
    assert resolve("curl -i https://a.example.org/x https://b.example.org/y", 0,
                   "HTTP/2 200\r\n\r\nx\nHTTP/2 404\r\n\r\ny\n") is None


def test_lsof_plus_options_are_left_to_the_model():
    out = "COMMAND   PID USER FD   TYPE DEVICE SIZE/OFF NODE NAME\ntail 1 root 3r REG 0,37 0 843 /tmp/a\n"
    assert resolve("lsof +D /tmp", 0, out) is None


def test_diskutil_info_on_a_volume_is_left_to_the_model():
    out = DISKUTIL.replace("   Device / Media Name:       APPLE SSD AP0512Z\n",
                           "   Device / Media Name:       Data\n   Volume Name:               Data\n")
    assert resolve("diskutil info /", 0, out) is None


def test_psql_rows_next_to_an_error_are_left_to_the_model():
    out = ('psql:q.sql:1: ERROR:  relation "x" does not exist\n'
           " n \n---\n 3\n(1 row)\n")
    assert resolve("psql -f q.sql", 0, out) is None


def test_du_french_typographic_apostrophe():
    out = ("du: impossible d’accéder à 'x': Aucun fichier ou dossier de ce nom\n"
           + "".join(f"4,0K\ty/{i}\n" for i in range(5)) + "20K\ty\n20K\ttotal\n")
    assert resolve("du -ch x y", 1, out) == "Échec. Total 20K, 1 erreur sur x : fichier introuvable."


def test_curl_quoted_url_keeps_quotes_out_of_the_resource():
    out = "HTTP/1.1 204 No Content\r\nServer: x\r\n\r\n"
    assert resolve("curl -i 'https://api.example.org/v1/items/42'", 0, out) == \
        "Réponse HTTP 204 No Content de api.example.org, ressource 42."


def test_ip_route_multipath_default_is_left_to_the_model():
    out = ("default proto ra metric 1024 expires 1790sec pref medium\n"
           "\tnexthop via fe80::1 dev wlan0 weight 1\n"
           "\tnexthop via fe80::2 dev eth0 weight 1\n"
           "fe80::/64 dev wlan0 proto kernel metric 1024 pref medium\n")
    assert resolve("ip -6 route", 0, out) is None


# ---------------------------------------------------------------- curl TLS et clé d'hôte SSH
# Chaînes de vérification OpenSSL reprises par curl, et message d'OpenSSH « Host key for H
# has changed and you have requested strict checking. ». DEV : v3-network-transfer-0008,
# 0017. Un message anglais connu n'est plus lu dans une phrase française ; inconnu, la
# phrase reste celle de L1.

@pytest.mark.parametrize("msg, fr, en", [
    ("SSL certificate problem: certificate has expired", "certificat expiré", "certificate has expired"),
    ("SSL certificate problem: self-signed certificate", "certificat auto-signé", "self-signed certificate"),
    ("SSL certificate problem: self signed certificate in certificate chain",
     "certificat auto-signé dans la chaîne", "self-signed certificate in the chain"),
    ("SSL certificate problem: unable to get local issuer certificate",
     "émetteur du certificat inconnu", "unknown certificate issuer"),
    ("SSL: no alternative certificate subject name matches target host name 'wrong.host.example.org'",
     "nom d'hôte absent du certificat", "host name not in the certificate"),
])
def test_curl_tls_reasons_in_the_session_language(msg, fr, en):
    out = f"curl: (60) {msg}\nMore details here: https://curl.se/docs/sslcerts.html\n\ncurl failed to verify\n"
    cmd = "curl -sS https://wrong.host.example.org/"
    assert resolve(cmd, 60, out) == f"Échec. TLS, wrong.host.example.org : {fr}."
    assert resolve(cmd, 60, out, "en") == f"Failed. TLS, wrong.host.example.org: {en}."


def test_curl_unknown_tls_reason_keeps_the_l1_sentence():
    out = "curl: (35) OpenSSL/3.0.13: error:0A00010B:SSL routines::wrong version number\n"
    assert resolve("curl https://example.org/", 35, out) == \
        "Échec. TLS : OpenSSL/3.0.13: error:0A00010B:SSL routines::wrong version number."


def test_ssh_changed_host_key_names_the_host():
    out = ("@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@\n"
           "@    WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED!     @\n"
           "@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@\n"
           "IT IS POSSIBLE THAT SOMEONE IS DOING SOMETHING NASTY!\n"
           "Offending ED25519 key in /home/user/.ssh/known_hosts:4\n"
           "Host key for srv.example.org has changed and you have requested strict checking.\n"
           "Host key verification failed.\n")
    assert resolve("ssh srv.example.org", 255, out) == \
        "Échec. Clé d'hôte de srv.example.org changée, vérification refusée."
    assert resolve("ssh srv.example.org", 255, out, "en") == \
        "Failed. Host key for srv.example.org has changed, verification failed."
