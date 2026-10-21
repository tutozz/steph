# G3c : gabarit neutre du bac à sable, exécuté DANS le bac à sable (uid 1000, sans réseau).
# Tout ce qui est ici est inventé pour ce jeu (CC BY 4.0) ; noms de personnes fictifs, domaines .invalid.
set -e
cd /home/user
mkdir -p data logs config scripts py ts jsapp sql nginx/html nginx/logs cron sshd certs compose run db git

# ---------- données ----------
cat > data/commandes.csv <<'X'
id,client,montant,date,statut
1001,Lucie Ferrand,149.90,2026-09-01,payée
1002,Hugo Delmas,89.00,2026-09-01,payée
1003,Agathe Morvan,1240.50,2026-09-02,en attente
1004,Bastien Lefort,15.20,2026-09-03,annulée
1005,Lucie Ferrand,310.00,2026-09-04,payée
1006,Inès Carvalho,,2026-09-04,payée
1007,Théo Bardin,78.40,2026-09-05,remboursée
1008,Agathe Morvan,56.00,2026-09-06
1009,Hugo Delmas,420.00,2026-09-07,payée
1010,Mila Rousset,33.33,2026-09-07,payée
X
cat > data/clients.json <<'X'
[
  {"id": 1, "nom": "Lucie Ferrand", "ville": "Rennes", "email": "lucie.ferrand@example.invalid", "actif": true},
  {"id": 2, "nom": "Hugo Delmas", "ville": "Tours", "email": "hugo.delmas@example.invalid", "actif": true},
  {"id": 3, "nom": "Agathe Morvan", "ville": "Brest", "email": "agathe.morvan@example.invalid", "actif": false},
  {"id": 4, "nom": "Bastien Lefort", "ville": "Dijon", "email": "bastien.lefort@example.invalid", "actif": true},
  {"id": 5, "nom": "Inès Carvalho", "ville": "Nîmes", "email": "ines.carvalho@example.invalid", "actif": true}
]
X
printf 'capteur\ttempérature\thumidité\nserre-1\t21.4\t58\nserre-2\t23.9\t61\nserre-3\t\t55\nserre-4\t19.8\t70\n' > data/mesures.tsv
printf 'Tarifs 2026 : pâte à crêpes, 3,50 EUR\nCafé crème, 2,20 EUR\n' | iconv -f UTF-8 -t LATIN1 > data/tarifs_latin1.txt
cat > data/settings_casse.json <<'X'
{
  "port": 8080,
  "debug": false,
  "entrepots": ["Rennes", "Tours",],
  "timeout": 30
}
X
python3 - <<'X'
import random
random.seed(20261001)
chemins = ["/api/commandes", "/api/clients", "/api/stock", "/sante", "/api/factures/1003"]
niveaux = ["INFO"] * 7 + ["WARN"] * 2 + ["ERROR"]
with open("logs/api.log", "w") as f:
    for i in range(80):
        n = random.choice(niveaux)
        c = random.choice(chemins)
        code = {"INFO": random.choice([200, 200, 201, 304]), "WARN": random.choice([404, 429]), "ERROR": random.choice([500, 502, 503])}[n]
        ms = random.randint(3, 900) if n != "ERROR" else random.randint(1000, 5000)
        f.write(f"2026-09-30 {8 + i // 10:02d}:{(i * 7) % 60:02d}:{(i * 13) % 60:02d} {n} {c} {code} {ms}ms\n")
with open("logs/worker.log", "w") as f:
    for i in range(25):
        f.write(f"2026-09-30 10:{i:02d}:00 worker[{2000 + i % 3}] tâche {100 + i} {'terminée' if i % 6 else 'échouée : délai dépassé'}\n")
X
cat > config/app.yaml <<'X'
application:
  nom: suivi-stock
  port: 8080
base:
  hote: 127.0.0.1
  nom: boutique
  utilisateur: app
journalisation:
  niveau: info
X
cat > config/app.ini <<'X'
[serveur]
port = 8080
workers = 4

[base]
hote = 127.0.0.1
nom = boutique
X

# ---------- Python ----------
cat > py/facturation.py <<'X'
import csv


def charger(chemin):
    with open(chemin, newline="") as f:
        return list(csv.DictReader(f))


def total_avec_remise(ligne):
    try:
        return float(ligne["montant"]) * (1 - float(ligne["remise"]))
    except KeyError as e:
        raise ValueError(f"commande {ligne['id']} : colonne manquante") from e


if __name__ == "__main__":
    lignes = charger("data/commandes.csv")
    print(f"{len(lignes)} commandes lues")
    total = sum(total_avec_remise(l) for l in lignes)
    print(f"Total : {total:.2f} €")
X
cat > py/charger_config.py <<'X'
import json
import sys


def lire(chemin):
    try:
        with open(chemin) as f:
            return json.load(f)
    except FileNotFoundError as e:
        raise RuntimeError(f"configuration introuvable : {chemin}") from e


if __name__ == "__main__":
    chemin = sys.argv[1] if len(sys.argv) > 1 else "config/prod.json"
    conf = lire(chemin)
    print("Configuration chargée :", ", ".join(sorted(conf)))
X
cat > py/client_api.py <<'X'
import json
import urllib.request

URL = "http://127.0.0.1:8081/api/stock"

with urllib.request.urlopen(URL, timeout=3) as r:
    stock = json.load(r)
print(f"{len(stock)} articles en stock")
X
cat > py/lire_json.py <<'X'
import json
import sys

with open(sys.argv[1]) as f:
    reglages = json.load(f)
print("Port :", reglages["port"])
X
cat > py/encodage.py <<'X'
with open("data/tarifs_latin1.txt", encoding="utf-8") as f:
    for ligne in f:
        print(ligne.rstrip())
X
cat > py/stats.py <<'X'
import csv
import statistics
import sys

colonne = sys.argv[1] if len(sys.argv) > 1 else "température"
valeurs = []
with open("data/mesures.tsv", newline="") as f:
    for ligne in csv.DictReader(f, delimiter="\t"):
        valeurs.append(float(ligne[colonne]))
print(f"{colonne} : moyenne {statistics.mean(valeurs):.1f}, écart type {statistics.stdev(valeurs):.2f}")
X
cat > py/rapport.py <<'X'
import csv
from collections import defaultdict

par_client = defaultdict(float)
nb = 0
with open("data/commandes.csv", newline="") as f:
    for ligne in csv.DictReader(f):
        if ligne.get("statut") == "payée" and ligne["montant"]:
            par_client[ligne["client"]] += float(ligne["montant"])
            nb += 1
print(f"{nb} commandes payées, {len(par_client)} clients")
for client, total in sorted(par_client.items(), key=lambda kv: -kv[1]):
    print(f"  {client:<16} {total:>9.2f} €")
print(f"Chiffre d'affaires : {sum(par_client.values()):.2f} €")
X
cat > py/outil.py <<'X'
import argparse

p = argparse.ArgumentParser(prog="outil", description="Export et import des commandes")
sp = p.add_subparsers(dest="action", required=True)
e = sp.add_parser("export", help="exporte les commandes")
e.add_argument("--format", choices=["csv", "json"], required=True)
e.add_argument("--depuis", help="date de début AAAA-MM-JJ")
i = sp.add_parser("import", help="importe un fichier")
i.add_argument("fichier")
i.add_argument("--lot", type=int, default=100)
a = p.parse_args()
print(f"action {a.action} : ok")
X
cat > py/traitement.py <<'X'
import logging
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("traitement")
lots = [120, 80, 0, 45]
for n, taille in enumerate(lots, 1):
    if taille == 0:
        log.warning("lot %d vide, ignoré", n)
        continue
    log.info("lot %d : %d lignes traitées", n, taille)
    time.sleep(0.1)
log.info("terminé : %d lignes", sum(lots))
X
cat > py/typage.py <<'X'
from typing import Optional


def trouver_client(clients: dict[int, str], ident: int) -> Optional[str]:
    return clients.get(ident)


def longueur_nom(clients: dict[int, str], ident: int) -> int:
    nom = trouver_client(clients, ident)
    return len(nom)


def total(montants: list[float]) -> float:
    s = 0
    for m in montants:
        s += m
    return str(s)


def remise(prix: float, taux: float = "0.1") -> float:
    return prix * (1 - taux)


def ville_par_defaut() -> str:
    if True:
        pass


compteur: int = "zéro"
longueur_nom({1: "Lucie"}, "1")
X
cat > py/propre.py <<'X'
"""Module sans défaut, pour les outils de vérification."""


def moyenne(valeurs: list[float]) -> float:
    """Moyenne arithmétique ; lève ValueError sur une liste vide."""
    if not valeurs:
        raise ValueError("liste vide")
    return sum(valeurs) / len(valeurs)


def arrondi_prix(prix: float) -> float:
    return round(prix, 2)
X
cat > py/brouillon.py <<'X'
import os, sys
import json
from collections import *


def Calcul( a,b ):
    resultat=a+b
    if resultat == None:
        print(f"rien")
    try:
        return int(resultat)
    except:
        pass
    l = [x for x in range(10) if x%2==0]
    return undefined_total + resultat


class client:
    def __init__(self, nom, nom):
        self.nom = nom
    def affiche(self): print("Client : " + self.nom + " (inscrit depuis le premier jour de l'ouverture de la boutique en ligne)")
X

# ---------- TypeScript ----------
mkdir -p ts/src
cat > ts/package.json <<'X'
{ "name": "suivi-stock", "version": "1.2.0", "private": true, "scripts": { "build": "tsc", "check": "tsc --noEmit" } }
X
cat > ts/tsconfig.json <<'X'
{ "compilerOptions": { "target": "ES2022", "module": "commonjs", "strict": true, "outDir": "dist", "rootDir": "src", "noUnusedLocals": true }, "include": ["src"] }
X
cat > ts/src/stock.ts <<'X'
export interface Article { ref: string; libelle: string; quantite: number; entrepot?: string }

export function totalQuantite(articles: Article[]): number {
  return articles.reduce((s, a) => s + a.quantite, 0);
}

export function entrepotEnMajuscules(a: Article): string {
  return a.entrepot.toUpperCase();
}

const vis: Article = { ref: "A-101", libelle: "vis M4", quantite: "1200" };
const inutilise = 42;
totalQuantite([vis], true);
X
cat > ts/src/format.ts <<'X'
export function prix(valeur: number): string {
  return valeur.toFixed(2) + " €";
}
X

# ---------- Node ----------
cat > jsapp/package.json <<'X'
{ "name": "api-commandes", "version": "0.4.1", "private": true, "main": "index.js", "scripts": { "start": "node index.js", "test": "node --test" } }
X
cat > jsapp/index.js <<'X'
const commandes = require('./commandes.json');
const total = commandes.filter(c => c.statut === 'payée').reduce((s, c) => s + c.montant, 0);
console.log(`Total payé : ${total.toFixed(2)} €`);
console.log(`Premier client : ${commandes[0].client.nom.toUpperCase()}`);
X
cat > jsapp/commandes.json <<'X'
[{"id": 1001, "client": "Lucie Ferrand", "montant": 149.9, "statut": "payée"}, {"id": 1002, "client": "Hugo Delmas", "montant": 89, "statut": "payée"}]
X
cat > jsapp/serveur.js <<'X'
const express = require('express');
const app = express();
app.get('/sante', (req, res) => res.send('ok'));
app.listen(3000);
X
cat > jsapp/config.js <<'X'
const fs = require('fs');
const conf = JSON.parse(fs.readFileSync('../data/settings_casse.json', 'utf8'));
console.log(conf.port);
X
cat > jsapp/async.js <<'X'
async function chargerStock() {
  throw new Error('stock indisponible : délai dépassé');
}
chargerStock().then(s => console.log(s));
X
cat > jsapp/syntaxe.js <<'X'
function total(lignes) {
  return lignes.map(l => l.montant).reduce((a, b) => a + b, 0
}
console.log(total([]));
X
mkdir -p jsapp/test
cat > jsapp/test/total.test.js <<'X'
const test = require('node:test');
const assert = require('node:assert');
const arrondi = (x) => Math.round(x * 100) / 100;
test('arrondi au centime', () => { assert.strictEqual(arrondi(1.005), 1.01); });
test('somme des montants', () => { assert.strictEqual([149.9, 89].reduce((a, b) => a + b), 238.9); });
test('liste vide', () => { assert.deepStrictEqual([].map(x => x), []); });
X
cat > jsapp/eslint.config.js <<'X'
module.exports = [{ files: ['**/*.js'], languageOptions: { ecmaVersion: 2022, sourceType: 'commonjs', globals: { require: 'readonly', console: 'readonly', module: 'writable', process: 'readonly' } },
  rules: { 'no-unused-vars': 'error', 'no-undef': 'error', eqeqeq: 'warn', 'prefer-const': 'warn', semi: 'off' } }];
X
cat > jsapp/brouillon.js <<'X'
var fs = require('fs')
let port = 3000
function lire(chemin) {
  if (chemin == null) return
  const inutile = 1
  return fs.readFileSync(chemin, 'utf8')
}
console.log(lire(fichier))
X

# ---------- scripts shell ----------
cat > scripts/rotation_journaux.sh <<'X'
#!/bin/bash
set -euo pipefail
dossier=${1:-logs}
echo "Rotation des journaux dans $dossier"
for f in "$dossier"/*.log; do
  taille=$(stat -c %s "$f")
  echo "  $f : $taille octets"
  gzip -c "$f" > "$f.$(date +%Y%m%d).gz"
done
echo "Terminé"
X
cat > scripts/sante.sh <<'X'
#!/bin/bash
url=${1:-http://127.0.0.1:8080/sante}
for essai in 1 2 3; do
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 2 "$url")
  echo "Essai $essai : HTTP $code"
  [ "$code" = 200 ] && { echo "Service en bonne santé"; exit 0; }
  sleep 1
done
echo "Service injoignable après 3 essais" >&2
exit 1
X
cat > scripts/installer_deps.sh <<'X'
#!/bin/bash
set -e
echo "Installation des dépendances système"
apt-get install -y jq libpq-dev
echo "Installation des dépendances Python"
pip install -r requirements.txt
X
cat > scripts/sauvegarde_pg.sh <<'X'
#!/bin/bash
set -euo pipefail
base=${1:-boutique}
dest=sauvegardes/$base-$(date +%F).sql.gz
mkdir -p sauvegardes
echo "Sauvegarde de $base vers $dest"
pg_dump -h /home/user/run "$base" | gzip > "$dest"
ls -lh "$dest" | awk '{print "Taille :", $5}'
X
cat > scripts/verifier_certs.sh <<'X'
#!/bin/bash
code=0
for c in certs/*.pem; do
  fin=$(openssl x509 -enddate -noout -in "$c" | cut -d= -f2)
  if openssl x509 -checkend 2592000 -noout -in "$c" >/dev/null; then
    echo "OK      $c (expire le $fin)"
  else
    echo "EXPIRE  $c (fin de validité : $fin)"
    code=1
  fi
done
exit $code
X
cat > scripts/compter.sh <<'X'
#!/bin/sh
total=0
for f in logs/*.log; do
  n=$(grep -c ERROR "$f")
  total=$((total + n))
  echo "$f : $n erreurs"
done
echo "Total : $total erreurs"
X
cat > scripts/deployer.sh <<'X'
#!/bin/bash
set -eu
version=$(jq -r .version ts/package.json)
echo "Déploiement de suivi-stock $version vers $CIBLE"
rsync -a --delete ts/ "$CIBLE/"
X
cat > scripts/nettoyer.sh <<'X'
#!/bin/bash
set -e
echo "Suppression des fichiers temporaires"
find . -name '*.tmp' -print -delete
rm -r cache/
echo "Nettoyage terminé"
X
cat > scripts/archiver.sh <<'X'
#!/bin/bash
set -euo pipefail
nom=archive-$(date +%Y%m%d).tar.gz
tar czf "$nom" data logs config
echo "Archive créée : $nom"
tar tzf "$nom" | wc -l | xargs echo "Fichiers archivés :"
X
cat > scripts/attendre_base.sh <<'X'
#!/bin/bash
for i in $(seq 1 5); do
  if pg_isready -h /home/user/run -q; then echo "Base prête après $i essai(s)"; exit 0; fi
  echo "Base pas encore prête ($i/5)"
  sleep 1
done
echo "La base ne répond pas" >&2; exit 2
X
chmod +x scripts/*.sh

# ---------- SQL ----------
cat > sql/001_tables.sql <<'X'
CREATE TABLE entrepot (id serial PRIMARY KEY, ville text NOT NULL UNIQUE);
CREATE TABLE article (id serial PRIMARY KEY, ref text NOT NULL UNIQUE, libelle text NOT NULL, prix numeric(8,2) CHECK (prix >= 0));
CREATE TABLE stock (article_id int REFERENCES article(id), entrepot_id int REFERENCES entrepot(id), quantite int NOT NULL, PRIMARY KEY (article_id, entrepot_id));
X
cat > sql/002_donnees.sql <<'X'
INSERT INTO entrepot (ville) VALUES ('Rennes'), ('Tours'), ('Brest');
INSERT INTO article (ref, libelle, prix) VALUES ('A-101', 'vis M4', 0.08), ('A-102', 'écrou M4', 0.05), ('A-103', 'rondelle', 0.02), ('A-104', 'équerre', 1.90), ('A-105', 'charnière', 3.40);
INSERT INTO stock VALUES (1, 1, 1200), (1, 2, 300), (2, 1, 800), (3, 3, 0), (4, 2, 45), (5, 1, 12);
X
cat > sql/003_colonne.sql <<'X'
ALTER TABLE article ADD COLUMN seuil int DEFAULT 10;
ALTER TABLE article ADD COLUMN seuil int DEFAULT 5;
X
cat > sql/004_erreur.sql <<'X'
BEGIN;
UPDATE stock SET quantite = quantite - 50 WHERE article_id = 4;
INSERT INTO stock VALUES (9, 1, 10);
COMMIT;
X
cat > sql/rapport.sql <<'X'
SELECT e.ville, count(*) AS articles, sum(s.quantite) AS total
FROM stock s JOIN entrepot e ON e.id = s.entrepot_id
GROUP BY e.ville ORDER BY total DESC;
X

# ---------- nginx ----------
echo '<h1>Boutique de démonstration</h1>' > nginx/html/index.html
mk_nginx() {
cat > "nginx/$1" <<X
worker_processes 1;
pid /home/user/run/nginx.pid;
error_log /home/user/nginx/logs/error.log;
events { worker_connections 64; }
http {
    access_log /home/user/nginx/logs/access.log;
    client_body_temp_path /home/user/run/nginx-body;
    proxy_temp_path /home/user/run/nginx-proxy;
    fastcgi_temp_path /home/user/run/nginx-fastcgi;
    uwsgi_temp_path /home/user/run/nginx-uwsgi;
    scgi_temp_path /home/user/run/nginx-scgi;
    $2
    server {
        listen 127.0.0.1:8080;
        server_name boutique.example.invalid;
        root /home/user/nginx/html;
        $3
    }
}
X
}
mk_nginx nginx.conf "" "location /api/ { proxy_pass http://127.0.0.1:8081; }"
mk_nginx sans_point_virgule.conf "" "location / { try_files \$uri \$uri/ =404 }"
mk_nginx directive_inconnue.conf "" "location / { autoindex_localtime on; gzip_level 5; }"
mk_nginx amont_introuvable.conf "upstream api { server api-interne:8081; }" "location /api/ { proxy_pass http://api; }"
mk_nginx include_absent.conf "include /home/user/nginx/mime.types;" "location / { index index.html; }"
mk_nginx double_location.conf "" "location / { index index.html; } location / { return 404; }"
mk_nginx accolade.conf "" "location / { index index.html; "
mk_nginx port_prive.conf "" "listen 127.0.0.1:80;"

# ---------- cron, sshd, certificats ----------
cat > cron/ok.cron <<'X'
# m h dom mon dow commande
*/15 * * * * /home/user/scripts/sante.sh >> /home/user/logs/sante.log 2>&1
30 2 * * * /home/user/scripts/archiver.sh
X
cat > cron/casse.cron <<'X'
*/15 * * * /home/user/scripts/sante.sh
61 2 * * * /home/user/scripts/archiver.sh
X
ssh-keygen -q -t ed25519 -N '' -C 'machine-demo' -f sshd/cle_hote_ed25519
cat > sshd/sshd_config <<'X'
Port 2222
ListenAddress 127.0.0.1
HostKey /home/user/sshd/cle_hote_ed25519
PidFile /home/user/run/sshd.pid
PermitRootLogin no
PasswordAuthentication no
X
sed 's/^PasswordAuthentication no/PasswordAuthentification no/' sshd/sshd_config > sshd/sshd_config.faute
sed 's|^HostKey .*|HostKey /home/user/sshd/cle_absente|' sshd/sshd_config > sshd/sshd_config.cle_absente
sed 's/^PermitRootLogin no/PermitRootLogin peut-etre/' sshd/sshd_config > sshd/sshd_config.valeur
openssl req -x509 -newkey rsa:2048 -nodes -keyout certs/boutique.key -out certs/boutique.pem -days 365 -subj "/CN=boutique.example.invalid/O=Boutique Demo" 2>/dev/null
openssl req -x509 -newkey rsa:2048 -nodes -keyout certs/ancien.key -out certs/ancien.pem -subj "/CN=ancien.example.invalid" -not_before 20240101000000Z -not_after 20250101000000Z 2>/dev/null
openssl req -x509 -newkey rsa:2048 -nodes -keyout certs/bientot.key -out certs/bientot.pem -days 10 -subj "/CN=api.example.invalid" 2>/dev/null
chmod 600 certs/*.key

# ---------- docker compose (fichiers seulement) ----------
mkdir -p compose/boutique compose/indentation compose/cle_inconnue compose/env_absent compose/dependance compose/variable
cat > compose/boutique/compose.yaml <<'X'
services:
  web:
    image: nginx:1.27
    ports:
      - "8080:80"
    depends_on:
      - api
  api:
    build: ./api
    environment:
      DATABASE_URL: postgres://app:${DB_MOT_DE_PASSE}@db:5432/boutique
  db:
    image: postgres:17
    volumes:
      - donnees:/var/lib/postgresql/data
volumes:
  donnees:
X
printf 'DB_MOT_DE_PASSE=changez-moi\n' > compose/boutique/.env
cat > compose/indentation/compose.yaml <<'X'
services:
  web:
    image: nginx:1.27
     ports:
      - "8080:80"
X
cat > compose/cle_inconnue/compose.yaml <<'X'
services:
  web:
    image: nginx:1.27
    port:
      - "8080:80"
    restart_policy: always
X
cat > compose/env_absent/compose.yaml <<'X'
services:
  api:
    image: python:3.13-slim
    env_file: .env.production
X
cat > compose/dependance/compose.yaml <<'X'
services:
  web:
    image: nginx:1.27
    depends_on:
      - cache
X
cat > compose/variable/compose.yaml <<'X'
services:
  api:
    image: "registre.example.invalid/api:${VERSION}"
    ports:
      - "${PORT_API:-8081}:8081"
X

# ---------- SQLite inventé ----------
python3 - <<'X'
import sqlite3, random
random.seed(11)
c = sqlite3.connect("db/boutique.db")
c.executescript("""
CREATE TABLE client (id INTEGER PRIMARY KEY, nom TEXT NOT NULL, ville TEXT, inscrit TEXT);
CREATE TABLE commande (id INTEGER PRIMARY KEY, client_id INTEGER NOT NULL REFERENCES client(id), montant REAL CHECK (montant >= 0), statut TEXT NOT NULL, jour TEXT);
CREATE INDEX idx_commande_client ON commande(client_id);
""")
noms = [("Lucie Ferrand", "Rennes"), ("Hugo Delmas", "Tours"), ("Agathe Morvan", "Brest"), ("Bastien Lefort", "Dijon"), ("Inès Carvalho", "Nîmes"), ("Théo Bardin", "Pau")]
for i, (n, v) in enumerate(noms, 1):
    c.execute("INSERT INTO client VALUES (?, ?, ?, ?)", (i, n, v, f"2025-{i:02d}-15"))
for k in range(1, 61):
    c.execute("INSERT INTO commande (client_id, montant, statut, jour) VALUES (?, ?, ?, ?)",
              (random.randint(1, 6), round(random.uniform(5, 900), 2), random.choice(["payée"] * 4 + ["annulée", "en attente"]), f"2026-09-{random.randint(1, 30):02d}"))
c.commit()
X

# ---------- dépôts git inventés (auteurs fictifs) ----------
g() { GIT_AUTHOR_NAME="$1" GIT_AUTHOR_EMAIL="$2" GIT_COMMITTER_NAME="$1" GIT_COMMITTER_EMAIL="$2" GIT_AUTHOR_DATE="$3" GIT_COMMITTER_DATE="$3" git commit -q -m "$4"; }
CM="Camille Martin"; CME=camille.martin@example.invalid
JR="Julien Roux"; JRE=julien.roux@example.invalid
NB="Nadia Benali"; NBE=nadia.benali@example.invalid
mkdir -p git/facturation && cd git/facturation && git init -q
mkdir -p facturation tests
cp /home/user/py/facturation.py facturation/calcul.py
cp /home/user/py/rapport.py facturation/rapport.py
echo "# Facturation" > README.md
printf '__pycache__/\n*.pyc\n.venv/\n' > .gitignore
git add -A; g "$CM" $CME "2026-09-01T09:12:00+02:00" "Initialisation du projet de facturation"
printf 'def test_total():\n    assert round(149.90 + 89.00, 2) == 238.9\n' > tests/test_calcul.py
git add -A; g "$JR" $JRE "2026-09-02T14:03:00+02:00" "Ajout des premiers tests"
printf '\n## Installation\n\npip install -e .\n' >> README.md
git add -A; g "$CM" $CME "2026-09-03T10:40:00+02:00" "Documentation de l'installation"
sed -i 's/Total : {total:.2f} €/Total TTC : {total:.2f} €/' facturation/calcul.py
git add -A; g "$NB" $NBE "2026-09-05T16:22:00+02:00" "Affichage du total TTC"
git tag -a v0.1.0 -m "Version 0.1.0" 2>/dev/null || GIT_COMMITTER_NAME="$CM" GIT_COMMITTER_EMAIL=$CME git tag -a v0.1.0 -m "Version 0.1.0"
git checkout -q -b export-json
printf 'import json\n\n\ndef exporter(lignes, chemin):\n    with open(chemin, "w") as f:\n        json.dump(lignes, f, ensure_ascii=False, indent=2)\n' > facturation/export.py
git add -A; g "$JR" $JRE "2026-09-08T11:00:00+02:00" "Export JSON des factures"
sed -i 's/Total TTC : {total:.2f} €/Montant total : {total:.2f} euros/' facturation/calcul.py
git add -A; g "$JR" $JRE "2026-09-09T09:30:00+02:00" "Libellé du total en toutes lettres"
git checkout -q main
sed -i 's/Total TTC : {total:.2f} €/Total TTC (remises comprises) : {total:.2f} €/' facturation/calcul.py
git add -A; g "$NB" $NBE "2026-09-10T15:45:00+02:00" "Préciser que le total inclut les remises"
for k in 1 2 3 4 5 6; do echo "- correction $k" >> CHANGELOG.md; git add -A; g "$CM" $CME "2026-09-1${k}T08:0${k}:00+02:00" "Journal des modifications : entrée $k"; done
cd /home/user/git && git clone -q --bare facturation facturation.git && cd facturation && git remote add origin /home/user/git/facturation.git && git fetch -q origin && git branch -q -u origin/main main
git remote add miroir https://git.example.invalid/equipe/facturation.git
cd /home/user/git && mkdir -p site && cd site && git init -q && cp /home/user/nginx/html/index.html . && git add -A && g "$NB" $NBE "2026-08-20T10:00:00+02:00" "Page d'accueil" && echo "<p>Horaires : 9 h - 18 h</p>" >> index.html && git add -A && g "$NB" $NBE "2026-08-21T10:00:00+02:00" "Ajout des horaires"
cd /home/user

# ---------- PostgreSQL : grappe de démonstration ----------
initdb -D pg/pgdata -U user --locale=C.UTF-8 --encoding=UTF8 -A trust > /dev/null
pg_ctl -D pg/pgdata -o "-k /home/user/run -c listen_addresses=''" -l run/pg.log -w start > /dev/null
createuser -h /home/user/run -s postgres
createuser -h /home/user/run app
createdb -h /home/user/run chinook
createdb -h /home/user/run pagila
createdb -h /home/user/run boutique
psql -q -h /home/user/run -d chinook -f /srv/src/db/chinook-database/ChinookDatabase/DataSources/Chinook_PostgreSql.sql > /dev/null 2>&1 || true
sed -e 's/uuidv7()/gen_random_uuid()/g' -e 's/) VIRTUAL$/) STORED/' /srv/src/db/pagila/pagila-schema.sql | psql -q -h /home/user/run -d pagila 2>&1 | grep -c ERR || true
psql -q -h /home/user/run -d pagila -f /srv/src/db/pagila/pagila-data.sql 2>&1 | grep -c ERR || true
psql -q -h /home/user/run -d boutique -f sql/001_tables.sql -f sql/002_donnees.sql > /dev/null
psql -h /home/user/run -d postgres -Atc "SELECT datname FROM pg_database ORDER BY 1"
psql -h /home/user/run -d chinook -Atc "SELECT count(*) FROM track" || true
psql -h /home/user/run -d pagila -Atc "SELECT count(*) FROM film" || true
pg_ctl -D pg/pgdata -m fast -w stop > /dev/null
rm -f run/pg.log
echo GABARIT_OK
