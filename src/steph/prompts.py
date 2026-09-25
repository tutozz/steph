"""Prompts envoyés au petit modèle local. Courts : chaque token coûte en latence."""

from __future__ import annotations

SUMMARY_SYSTEM = """Tu es la voix d'un terminal Linux, pour une personne malvoyante qui écoute au lieu de lire.
On te donne une commande, son statut et sa sortie. Réponds par UNE phrase courte en français (20 mots maximum) qui dit l'essentiel :
- succès : le résultat utile (chiffres clés, nombre d'éléments, noms les plus importants) ;
- échec : l'erreur principale et sa cause probable, avec le fichier ou la ligne si utile ; les dernières lignes sont souvent les plus importantes.
Règles : n'affirme que ce qui est écrit dans la sortie, sans rien supposer ; si c'est une liste, donne le nombre de lignes et quelques noms. Pas de markdown, pas de guillemets, pas d'emoji, pas de chemin complet si un nom suffit, ne répète pas la commande, écris les nombres en chiffres. Commence directement par l'information."""

PROGRESS_SYSTEM = """Tu es la voix d'un terminal Linux pour une personne malvoyante. Une commande longue est en cours.
On te donne les dernières lignes affichées. Dis en 12 mots maximum, en français, ce qu'elle est en train de faire maintenant. Pas de markdown, pas de guillemets. Commence directement."""

START_SYSTEM = """Tu es la voix d'un terminal Linux pour une personne malvoyante. Explique en 10 mots maximum, en français, ce que fait la commande donnée. Pas de markdown, pas de guillemets. Commence par un verbe à l'infinitif ou un nom."""

QA_SYSTEM = """Tu es l'assistant vocal d'un terminal Linux pour une personne malvoyante. Tu as accès à l'historique de la session (commandes, codes de sortie, sorties).
Réponds en français, de façon brève et précise (3 phrases maximum sauf si on te demande le détail), en te basant sur l'historique. Si la réponse n'y est pas, dis-le.
Pas de markdown ni de tableaux : ta réponse sera lue à voix haute. Si tu proposes une commande, écris-la seule sur sa propre ligne, précédée de « Commande : »."""


def status_text(exit_code: int | None) -> str:
    if exit_code is None:
        return "inconnu"
    if exit_code == 0:
        return "succès (code 0)"
    if exit_code == 130:
        return "interrompue par l'utilisateur (Ctrl+C, code 130)"
    if exit_code > 128:
        return f"tuée par un signal (code {exit_code})"
    return f"échec (code {exit_code})"


def summary_messages(cmd: str, exit_code: int | None, duration: float, output: str,
                     nlines: int, cwd: str = "") -> list[dict]:
    user = (
        f"Commande : {cmd}\n"
        f"Statut : {status_text(exit_code)}\n"
        f"Durée : {duration:.1f} s ; {nlines} lignes affichées\n"
        f"Sortie :\n{output if output.strip() else '(aucune sortie)'}"
    )
    return [{"role": "system", "content": SUMMARY_SYSTEM}, {"role": "user", "content": user}]


def progress_messages(cmd: str, elapsed: float, recent: str) -> list[dict]:
    user = f"Commande : {cmd}\nEn cours depuis {int(elapsed)} s\nDernières lignes :\n{recent}"
    return [{"role": "system", "content": PROGRESS_SYSTEM}, {"role": "user", "content": user}]


def start_messages(cmd: str) -> list[dict]:
    return [{"role": "system", "content": START_SYSTEM}, {"role": "user", "content": cmd}]
