"""Simule un `apt upgrade` en français, avec barre de progression d'apt."""
import sys, time
w = sys.stdout.write
def p(s, d=0.0):
    w(s + "\n"); sys.stdout.flush(); time.sleep(d)
p("Lecture des listes de paquets... Fait", 0.3)
p("Construction de l'arbre des dépendances... Fait", 0.3)
p("Calcul de la mise à jour... Fait", 0.2)
p("Les paquets suivants seront mis à jour :")
pk = ["curl", "libcurl4", "openssl", "libssl3", "linux-libc-dev", "tzdata", "vim", "vim-common", "python3.11", "libpython3.11"]
p("  " + " ".join(pk))
p(f"{len(pk)} mis à jour, 0 nouvellement installés, 0 à enlever et 0 non mis à jour.")
p("Il est nécessaire de prendre 24,3 Mo dans les archives.")
if "--ask" in sys.argv:
    w("Souhaitez-vous continuer ? [O/n] "); sys.stdout.flush()
    a = sys.stdin.readline().strip().lower()
    if a.startswith("n"):
        p("Annulation."); sys.exit(1)
for i, x in enumerate(pk, 1):
    p(f"Réception de :{i} http://deb.debian.org/debian bookworm/main amd64 {x} amd64 1.0 [315 kB]", 0.6)
p("24,3 Mo réceptionnés en 6s (4 012 ko/s)")
for i, x in enumerate(pk):
    pct = int(100 * (i + 1) / (2 * len(pk)))
    p(f"Dépaquetage de {x} (1.0) sur (0.9) ...", 0.3)
    w(f"\x1b7\x1b[24;0f\x1b[42mProgress: [{pct:3d}%]\x1b[49m [{'#'*(pct//5)}{'.'*(20-pct//5)}] \x1b8"); sys.stdout.flush(); time.sleep(1.0)
for i, x in enumerate(pk):
    pct = 50 + int(50 * (i + 1) / len(pk))
    p(f"Paramétrage de {x} (1.0) ...", 0.3)
    w(f"\x1b7\x1b[24;0f\x1b[42mProgress: [{pct:3d}%]\x1b[49m [{'#'*(pct//5)}{'.'*(20-pct//5)}] \x1b8"); sys.stdout.flush(); time.sleep(0.8)
p("Traitement des actions différées (« triggers ») pour man-db (2.11.2-2) ...", 1.0)
