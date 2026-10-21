"""Axe A (prompt) : génère une variante de cas à partir de cases.json, à 800 caractères.

    python3 gen.py --sys a --shots 2 --tail short --fmt clear --out cases_x.json

Seule la formulation change : système, exemples en vrais tours de dialogue (choisis selon la
catégorie de la commande, sur des commandes absentes du banc), consigne répétée en fin de
message, présentation du message utilisateur. Les cas qa gardent le prompt de steph.
"""

import argparse
import json
import re
from pathlib import Path

HERE = Path(__file__).parent
MATRIX = HERE.parents[1]

STEPH = json.load(open(MATRIX / "cases.json"))[1]["messages"][0]["content"]

P1_BASE = ("Tu résumes la sortie d'une commande pour une personne aveugle qui écoute. "
           "Réponds en une seule ligne de 15 mots maximum, en français, en mots-clés, sans phrase. "
           "N'écris que ce qui figure dans la sortie ; n'invente rien.")

P1_RULES = {
    "echec": "La commande a échoué : commence par « Échec. », puis la cause, et le fichier et la ligne s'ils sont écrits.",
    "liste": "La sortie commence par un compte : répète exactement ce compte et les 3 noms qui le suivent.",
    "reseau": "Donne chaque interface avec son adresse IPv4, telles qu'écrites en tête de la sortie.",
    "disque": "Donne l'espace libre de chaque disque, tel qu'écrit dans la sortie.",
    "memoire": "Donne la mémoire totale et la mémoire disponible.",
    "materiel": "Donne le GPU, le contrôleur réseau et le chipset.",
    "succes": "Donne le résultat utile, avec les nombres en chiffres.",
}

# Système réécrit : rôle, gabarit de sortie, interdiction d'inventer, une règle par catégorie.
A_BASE = ("Tu lis la sortie d'une commande de terminal et tu dis à voix haute l'essentiel, en français. "
          "Format : une seule ligne, 15 mots au plus : « <résultat>. <détail>. » "
          "Recopie les noms et les nombres exactement comme dans la sortie. "
          "Si une information n'est pas écrite dans la sortie, ne la donne pas : n'invente jamais.")

A_RULES = {
    "echec": "La commande a ÉCHOUÉ. Commence par « Échec. » puis la cause exacte du message d'erreur, avec le fichier et la ligne s'ils sont écrits.",
    "liste": "La sortie commence par une ligne « N éléments : a, b, c ». Réponds exactement avec ce nombre N et ces 3 noms.",
    "reseau": "Donne chaque interface avec son adresse IPv4, dans l'ordre de la sortie, puis le nombre de réseaux virtuels s'il est écrit.",
    "disque": "Pour chaque disque : son nom, l'espace libre, la taille et le pourcentage utilisé, tels qu'écrits.",
    "memoire": "Donne la mémoire totale (colonne total) et la mémoire disponible (colonne available), avec leurs unités.",
    "materiel": "Donne la carte graphique, le contrôleur réseau et le chipset. Le processeur n'est pas dans cette sortie : ne le cite pas.",
    "succes": "Donne le résultat utile (version, nom, nombre, état), avec les nombres en chiffres.",
}

# Système B : même esprit que A, sans gabarit à chevrons (LFM le recopiait tel quel).
B_BASE = ("Tu lis la sortie d'une commande de terminal et tu dis à voix haute l'essentiel, en français. "
          "Réponds par une seule ligne courte, 15 mots au plus : d'abord le résultat, puis un détail utile. "
          "Recopie les noms et les nombres exactement comme dans la sortie. "
          "Si une information n'est pas écrite dans la sortie, ne la donne pas : n'invente jamais.")

B_RULES = {**A_RULES,
    "succes": "Donne le résultat utile : chaque version, nom, nombre ou état écrit dans la sortie, nombres en chiffres.",
}

# Système C : consignes génériques resserrées (pas de gabarit littéral, pas de « N »).
C_BASE = ("Tu es la voix d'un terminal pour une personne aveugle. On te donne une commande et sa sortie. "
          "Réponds par une seule ligne de 15 mots au plus, en français : d'abord le résultat principal, puis un détail. "
          "Reprends les noms, nombres, versions et pourcentages tels qu'ils sont écrits. Ne répète pas la commande. "
          "N'invente rien : aucun fichier, aucune ligne, aucune valeur absents de la sortie.")

C_RULES = {**A_RULES,
    "echec": "La commande a échoué : commence par « Échec. » puis la cause en quelques mots tirés du message d'erreur, avec le fichier et la ligne seulement s'ils sont écrits.",
    "liste": "La sortie commence par un compte suivi de 3 noms (par exemple « 12 éléments : x, y, z ») : répète ce compte et ces 3 noms, rien d'autre.",
    "succes": "Donne le résultat principal : versions, noms, nombres, pourcentages ou états écrits dans la sortie, nombres en chiffres.",
}

# Exemples par catégorie, sur des commandes et des valeurs absentes du banc.
SHOTS = {
    "echec": [
        ("make", 2, "0.4",
         "cc -O2 -c main.c\nmain.c: In function 'main':\nmain.c:17:5: error: 'count' undeclared (first use in this function)\nmake: *** [Makefile:4: main.o] Error 1",
         "Échec. main.c ligne 17 : count non déclaré."),
        ("node server.js", 1, "0.2",
         "node:events:497\n      throw er;\nError: listen EADDRINUSE: address already in use :::3000\n    at Server.setupListenHandle (node:net:1872:16)",
         "Échec. Port 3000 déjà utilisé."),
        ("cargo build", 101, "3.1",
         "   Compiling demo v0.1.0\nerror[E0425]: cannot find value `total` in this scope\n --> src/main.rs:9:20\nerror: could not compile `demo` due to 1 previous error",
         "Échec. main.rs ligne 9 : valeur total introuvable."),
    ],
    "liste": [
        ("ls ~/Musique", 0, "0.0",
         "14 éléments : albums, concerts, podcasts\nalbums\nconcerts\npodcasts\nradio\nsingles",
         "14 éléments : albums, concerts, podcasts."),
        ("ls /var/log | head -25", 0, "0.0",
         "25 éléments : apt, auth.log, boot.log\napt\nauth.log\nboot.log\nbtmp\ncups",
         "25 éléments : apt, auth.log, boot.log."),
        ("kubectl get pods -o name", 0, "0.6",
         "7 éléments : web-5d9f, redis-0, worker-2b1c\npod/web-5d9f\npod/redis-0\npod/worker-2b1c\npod/worker-8e4a",
         "7 éléments : web-5d9f, redis-0, worker-2b1c."),
    ],
    "reseau": [
        ("ip -4 addr show", 0, "0.0",
         "eth0 10.0.3.15\nwg0 10.8.0.2\nréseaux virtuels : 2",
         "eth0 10.0.3.15, wg0 10.8.0.2. Plus 2 réseaux virtuels."),
        ("ip address", 0, "0.0",
         "enp3s0 172.20.4.11",
         "enp3s0 172.20.4.11."),
        ("ifconfig -a", 0, "0.0",
         "eno1 10.20.30.40\nzt0 10.147.17.5\nréseaux virtuels : 5",
         "eno1 10.20.30.40, zt0 10.147.17.5. Plus 5 réseaux virtuels."),
    ],
    "disque": [
        ("df -h /srv", 0, "0.0",
         "srv : 120G libres sur 500G, 76 %",
         "srv 120G libres sur 500G, 76 %."),
        ("df -hl", 0, "0.0",
         "racine : 41G libres sur 230G, 82 %\ndata : 1,1T libres sur 3,6T, 70 %",
         "Racine 41G libres sur 230G, 82 %. Data 1,1T libres, 70 %."),
        ("df -h --local", 0, "0.0",
         "racine : 12G libres sur 60G, 80 %\nhome : 300G libres sur 400G, 25 %",
         "Racine 12G libres sur 60G, 80 %. Home 300G libres, 25 %."),
    ],
    "memoire": [
        ("free -m", 0, "0.0",
         "               total        used        free      shared  buff/cache   available\n"
         "Mem:           15890        9120        1203         410        5567        5840\n"
         "Swap:           2047           0        2047",
         "Mémoire 15890 Mo, 5840 Mo disponibles."),
        ("free -g", 0, "0.0",
         "               total        used        free      shared  buff/cache   available\n"
         "Mem:              62          18           3           1          41          43\n"
         "Swap:              4           0           4",
         "Mémoire 62 Go, 43 Go disponibles."),
        ("free --giga -h", 0, "0.0",
         "               total        used        free      shared  buff/cache   available\n"
         "Mem:           7,7Gi       5,1Gi       310Mi       120Mi       2,3Gi       2,2Gi\n"
         "Swap:          2,0Gi       1,1Gi       0,9Gi",
         "Mémoire 7,7Gi, 2,2Gi disponibles."),
    ],
    "materiel": [
        ("lspci -k", 0, "0.1",
         "00:00.0 Host bridge: Intel Corporation 8th Gen Core Processor Host Bridge\n"
         "00:02.0 VGA compatible controller: Intel Corporation CoffeeLake-S GT2 [UHD Graphics 630]\n"
         "00:14.0 USB controller: Intel Corporation Cannon Lake PCH USB 3.1 xHCI Host Controller\n"
         "00:17.0 SATA controller: Intel Corporation Cannon Lake PCH SATA AHCI Controller\n"
         "00:1f.0 ISA bridge: Intel Corporation Q370 Chipset LPC/eSPI Controller\n"
         "00:1f.6 Ethernet controller: Intel Corporation Ethernet Connection (7) I219-LM",
         "GPU Intel UHD 630, réseau Intel I219-LM, chipset Intel Q370, USB et SATA."),
        ("lspci -nn", 0, "0.1",
         "00:00.0 Host bridge [0600]: Intel Corporation Device [8086:9b61]\n"
         "01:00.0 VGA compatible controller [0300]: NVIDIA Corporation GA106 [GeForce RTX 3050] [10de:2507]\n"
         "03:00.0 Network controller [0280]: Intel Corporation Wi-Fi 6 AX200 [8086:2723]\n"
         "00:1f.0 ISA bridge [0601]: Intel Corporation B460 Chipset LPC [8086:a3c8]",
         "GPU NVIDIA RTX 3050, réseau Wi-Fi Intel AX200, chipset Intel B460."),
        ("lspci -v", 0, "0.1",
         "00:00.0 Host bridge: Advanced Micro Devices, Inc. [AMD] Renoir Root Complex\n"
         "04:00.0 VGA compatible controller: Advanced Micro Devices, Inc. [AMD/ATI] Navi 23 [Radeon RX 6600]\n"
         "05:00.0 Ethernet controller: Intel Corporation I211 Gigabit Network Connection\n"
         "06:00.0 USB controller: Advanced Micro Devices, Inc. [AMD] 500 Series Chipset USB 3.1 XHCI Controller",
         "GPU Radeon RX 6600, réseau Intel I211, chipset AMD série 500, USB."),
    ],
    "succes": [
        ("node --version", 0, "0.1", "v22.3.0", "Node 22.3.0."),
        ("wc -l ventes.csv", 0, "0.0", "1204 ventes.csv", "1204 lignes dans ventes.csv."),
        ("hostnamectl --static", 0, "0.0", "atelier-01", "Nom d'hôte atelier-01."),
    ],
}


def status_text(code: int) -> str:
    return "succès (code 0)" if code == 0 else f"échec (code {code})"


def user_orig(cmd, status, duration_line, output):
    return f"Commande : {cmd}\nStatut : {status}\n{duration_line}\nSortie :\n{output}"


def failed(status: str) -> bool:
    m = re.search(r"code (\d+)", status)
    return bool(m and int(m.group(1)) != 0)


def user_clear(cmd, status, duration_line, output):
    head = "La commande a ÉCHOUÉ." if failed(status) else "La commande a réussi."
    return (f"{head}\nCommande : {cmd}\n<<< DÉBUT DE LA SORTIE\n{output}\nFIN DE LA SORTIE >>>\n"
            "Que faut-il retenir de cette sortie ?")


def category(cmd: str, status: str, output: str) -> str:
    if failed(status):
        return "echec"
    words = cmd.split()
    prog = words[0].rsplit("/", 1)[-1] if words else ""
    if prog == "sudo" and len(words) > 1:
        prog = words[1]
    if prog in ("ip", "ifconfig"):
        return "reseau"
    if prog == "df":
        return "disque"
    if prog == "free":
        return "memoire"
    if prog == "lspci":
        return "materiel"
    if re.match(r"\d+ (éléments|conteneurs)", output):
        return "liste"
    return "succes"


TAILS = {
    "none": "",
    "short": "\n\nRéponse en une ligne :",
    "rule": "\n\n{rule} Réponse en une ligne :",
}


def build(case: dict, a) -> dict:
    if case["kind"] == "qa":
        return case
    user = case["messages"][1]["content"]
    cmd = re.search(r"Commande : (.*)", user).group(1)
    status = re.search(r"Statut : (.*)", user).group(1)
    duration_line = user.split("\n")[2]
    output = user.split("Sortie :\n", 1)[-1]
    cat = category(cmd, status, output)
    rules = C_RULES if a.sys.startswith("c") else B_RULES if a.sys.startswith("b") else A_RULES if a.sys.startswith("a") else P1_RULES
    rule = rules[cat]
    if a.sys == "steph":
        system = STEPH
    elif a.sys == "p1":
        system = P1_BASE + " " + P1_RULES[cat]
    elif a.sys == "a":
        system = A_BASE + " " + rule
    elif a.sys == "a0":  # base seule, la règle ne vit qu'en fin de message
        system = A_BASE
    elif a.sys == "b":
        system = B_BASE + " " + rule
    elif a.sys == "c":
        system = C_BASE + " " + rule
    elif a.sys == "c0":
        system = C_BASE
    elif a.sys == "b0":
        system = B_BASE
    else:
        raise SystemExit(f"système inconnu : {a.sys}")
    fmt = user_clear if a.fmt == "clear" else user_orig
    tail = TAILS[a.tail].format(rule=rule)
    msgs = [{"role": "system", "content": system}]
    pool = SHOTS[cat] if a.shotmode == "cat" else [SHOTS["echec"][0], SHOTS["succes"][1], SHOTS["liste"][0]]
    for c, code, dur, out, ans in pool[:a.shots]:
        u = fmt(c, status_text(code), f"Durée : {dur} s ; {len(out.splitlines())} lignes affichées", out)
        msgs += [{"role": "user", "content": u + tail}, {"role": "assistant", "content": ans}]
    msgs.append({"role": "user", "content": fmt(cmd, status, duration_line, output) + tail})
    return {**case, "messages": msgs, "cat": cat}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sys", default="a", help="steph | p1 | a | a0")
    ap.add_argument("--shots", type=int, default=0)
    ap.add_argument("--shotmode", default="cat", help="cat (même catégorie) | mixed")
    ap.add_argument("--tail", default="none", choices=list(TAILS))
    ap.add_argument("--fmt", default="orig", choices=["orig", "clear"])
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    cases = [c for c in json.load(open(MATRIX / "cases.json")) if c["kind"] == "qa" or c["maxc"] == 800]
    out = [build(c, a) for c in cases]
    json.dump(out, open(HERE / a.out, "w"), ensure_ascii=False, indent=0)
    print(a.out, len(out), "cas")


if __name__ == "__main__":
    main()
