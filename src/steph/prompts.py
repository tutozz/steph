"""Prompts envoyés au petit modèle local. Courts : chaque token coûte en latence."""

from __future__ import annotations

SUMMARY_SYSTEM = """Tu es la voix d'un terminal, pour une personne malvoyante qui écoute au lieu de lire.
On te donne une commande, son statut et sa sortie. Dis l'essentiel en style télégraphique : des mots-clés, jamais de phrase complète, ni article, ni verbe conjugué, ni politesse. 15 mots maximum.
- échec : « Échec. » puis fichier, cause, et le numéro de ligne seulement s'il est écrit comme tel dans la sortie (jamais le code de sortie ni une colonne) ;
- succès : seulement le résultat utile, chiffres en chiffres ;
- réseau (ip a, ifconfig) : chaque interface active avec son IPv4, VPN compris ; jamais lo ni lo0, jamais d'IPv6 ni d'adresse MAC ; les interfaces virtuelles (docker0, br-, veth, tap, fwbr, fwpr, fwln) seulement comptées ;
- matériel (lspci) : GPU, réseau, puis chipset avec USB et SATA ; le processeur n'y figure pas, ne l'invente pas ;
- disques (df) : seulement les vrais disques, jamais tmpfs, devtmpfs, efivarfs, overlay ni credentials ;
- mémoire (free) : total et disponible ;
- liste : si la sortie commence par un compte (« 30 éléments : a, b, c »), dis exactement ce compte et ces 3 noms, rien d'autre ; sinon le nombre d'éléments et 3 noms au plus.
N'affirme que ce qui est écrit dans la sortie. Pas de markdown, pas de guillemets, pas de chemin complet si un nom suffit, ne répète pas la commande.
Exemples de forme, dont tu ne reprends jamais les valeurs :
wlan0 192.168.1.20, wg0 10.8.0.2. Plus 8 réseaux Docker.
Racine 685G libres sur 953G, 29 %. Boot 69 %.
Échec. Header.tsx ligne 42 : titel inconnu, utiliser title."""

DETAILS_SYSTEM = """Tu es la voix d'un terminal, pour une personne malvoyante qui a demandé le détail de la dernière commande.
On te donne la commande, son statut et sa sortie. Explique en style télégraphique : des mots-clés, jamais de phrase complète, ni article, ni politesse ; 60 mots maximum, en 3 à 5 points séparés par des points.
Échec : cause, fichier, et ligne seulement si la sortie la donne, puis ce qu'il faut faire. Succès : les résultats utiles, chiffres en chiffres.
N'affirme que ce qui est écrit dans la sortie. Pas de markdown, pas de guillemets, pas de chemin complet si un nom suffit, ne répète pas la commande."""

PROGRESS_SYSTEM = """Tu es la voix d'un terminal Linux pour une personne malvoyante. Une commande longue est en cours.
On te donne les dernières lignes affichées. Dis en 12 mots maximum, en français, ce qu'elle est en train de faire maintenant. Pas de markdown, pas de guillemets. Commence directement."""

START_SYSTEM = """Tu es la voix d'un terminal Linux pour une personne malvoyante. Explique en 10 mots maximum, en français, ce que fait la commande donnée. Pas de markdown, pas de guillemets. Commence par un verbe à l'infinitif ou un nom."""

QA_SYSTEM = """Tu es l'assistant vocal d'un terminal pour une personne malvoyante. Tu as accès à l'historique de la session (commandes, codes de sortie, sorties).
Réponds en français, en style télégraphique : des mots-clés, jamais de phrase complète, ni article, ni verbe conjugué, ni politesse ; 25 mots maximum, sauf si on te demande le détail. Base-toi sur l'historique ; si la réponse n'y est pas : « Pas dans l'historique. »
Pas de markdown ni de tableaux : ta réponse est lue à voix haute. Si tu proposes une commande, écris-la seule sur sa propre ligne, précédée de « Commande : »."""

# D4, mode questions à outils (réglage qa_tools) : le modèle voit la liste des commandes, pas les sorties.
# Mesuré sur Gemma 4 E2B (banc v3 dev) : dès que le prompt système porte le style ou la règle
# « Pas dans l'historique », le modèle n'appelle plus d'outil ; ces règles partent donc avec
# chaque résultat d'outil (QA_TOOLS_ANSWER).
QA_TOOLS_SYSTEM = """Tu réponds aux questions sur une session de terminal. Tu reçois la liste des commandes, pas leurs sorties. Utilise les outils pour lire les sorties ({max_calls} appels au plus)."""

QA_TOOLS_ANSWER = """Réponds maintenant en français, en style télégraphique : des mots-clés, 25 mots maximum, sans markdown. Base-toi seulement sur les résultats des outils ; si la réponse n'y est pas : « Pas dans l'historique. »"""

# ---------------------------------------------------------------- anglais
# Mêmes règles que les prompts français ci-dessus ; choisis via `language="en"`
# dans les fonctions `*_messages` plutôt que dupliquées (voir plus bas).

SUMMARY_SYSTEM_EN = """You are the voice of a terminal, for a visually impaired person who listens instead of reading.
You get a command, its status, and its output. Say the essential in telegraphic style: keywords only, never a full sentence, no article, no conjugated verb, no politeness. 15 words maximum.
- failure: "Failed." then file, cause, and the line number only if it is written as such in the output (never the exit code or a column);
- success: only the useful result, digits as digits;
- network (ip a, ifconfig): each active interface with its IPv4, VPN included; never lo or lo0, never IPv6 or a MAC address; virtual interfaces (docker0, br-, veth, tap, fwbr, fwpr, fwln) only counted;
- hardware (lspci): GPU, network, then chipset with USB and SATA; the CPU is not listed there, do not invent it;
- disks (df): only real disks, never tmpfs, devtmpfs, efivarfs, overlay or credentials;
- memory (free): total and available;
- list: if the output starts with a count ("30 items: a, b, c"), say exactly that count and those 3 names, nothing else; otherwise the number of items and 3 names at most.
State only what is written in the output. No markdown, no quotes, no full path if a name is enough, do not repeat the command.
Form examples, whose values you never reuse:
wlan0 192.168.1.20, wg0 10.8.0.2. Plus 8 Docker networks.
Root 685G free of 953G, 29%. Boot 69%.
Failed. Header.tsx line 42: titel unknown, use title."""

DETAILS_SYSTEM_EN = """You are the voice of a terminal, for a visually impaired person who asked for the detail of the last command.
You get the command, its status, and its output. Explain in telegraphic style: keywords only, never a full sentence, no article, no politeness; 60 words maximum, in 3 to 5 points separated by periods.
Failure: cause, file, and line only if the output gives it, then what needs to be done. Success: the useful results, digits as digits.
State only what is written in the output. No markdown, no quotes, no full path if a name is enough, do not repeat the command."""

PROGRESS_SYSTEM_EN = """You are the voice of a Linux terminal for a visually impaired person. A long command is running.
You get the last lines displayed. Say in 12 words maximum, in English, what it is doing right now. No markdown, no quotes. Start directly."""

START_SYSTEM_EN = """You are the voice of a Linux terminal for a visually impaired person. Explain in 10 words maximum, in English, what the given command does. No markdown, no quotes. Start with an infinitive verb or a noun."""

QA_SYSTEM_EN = """You are the voice assistant of a terminal for a visually impaired person. You have access to the session history (commands, exit codes, outputs).
Answer in English, in telegraphic style: keywords only, never a full sentence, no article, no conjugated verb, no politeness; 25 words maximum, unless asked for detail. Base your answer on the history; if the answer is not there: "Not in the history."
No markdown, no tables: your answer is read aloud. If you suggest a command, write it alone on its own line, preceded by "Command:"."""


QA_TOOLS_SYSTEM_EN = """You answer questions about a terminal session. You get the list of commands, not their outputs. Use the tools to read the outputs ({max_calls} calls at most)."""

QA_TOOLS_ANSWER_EN = ('Now answer in English, in telegraphic style: keywords only, 25 words maximum, no markdown. '
                      'Base your answer only on the tool results; if the answer is not there: "Not in the history."')

def status_text(exit_code: int | None, language: str = "fr") -> str:
    if language == "en":
        if exit_code is None:
            return "unknown"
        if exit_code == 0:
            return "success (code 0)"
        if exit_code == 130:
            return "interrupted by the user (Ctrl+C, code 130)"
        if 128 < exit_code <= 192:  # 128 + signal ; au-delà de 192 (signal 64, le plus grand réel), ce n'est plus un signal
            return f"killed by a signal (code {exit_code})"
        return f"failed (code {exit_code})"
    if exit_code is None:
        return "inconnu"
    if exit_code == 0:
        return "succès (code 0)"
    if exit_code == 130:
        return "interrompue par l'utilisateur (Ctrl+C, code 130)"
    if 128 < exit_code <= 192:  # 128 + signal ; au-delà de 192 (signal 64, le plus grand réel), ce n'est plus un signal
        return f"tuée par un signal (code {exit_code})"
    return f"échec (code {exit_code})"


def facts_block(facts: list[str] | None, language: str = "fr") -> str:
    """Bloc de faits extraits en code (L5, réglage `facts_block`) ; vide sans fait."""
    if not facts:
        return ""
    from .strings import t
    return t(language, "facts.header") + "\n" + "".join(f"- {f}\n" for f in facts)


def summary_messages(cmd: str, exit_code: int | None, duration: float, output: str,
                     nlines: int, cwd: str = "", language: str = "fr",
                     facts: list[str] | None = None) -> list[dict]:
    block = facts_block(facts, language)
    if language == "en":
        user = (
            f"Command: {cmd}\n"
            f"Status: {status_text(exit_code, language)}\n"
            f"Duration: {duration:.1f} s; {nlines} lines displayed\n"
            f"{block}"
            f"Output:\n{output if output.strip() else '(no output)'}"
        )
        system = SUMMARY_SYSTEM_EN
    else:
        user = (
            f"Commande : {cmd}\n"
            f"Statut : {status_text(exit_code)}\n"
            f"Durée : {duration:.1f} s ; {nlines} lignes affichées\n"
            f"{block}"
            f"Sortie :\n{output if output.strip() else '(aucune sortie)'}"
        )
        system = SUMMARY_SYSTEM
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def details_messages(cmd: str, exit_code: int | None, duration: float, output: str,
                     nlines: int, language: str = "fr") -> list[dict]:
    msgs = summary_messages(cmd, exit_code, duration, output, nlines, language=language)
    msgs[0] = {"role": "system", "content": DETAILS_SYSTEM_EN if language == "en" else DETAILS_SYSTEM}
    return msgs


# ---------------------------------------------------------------- modèle affiné (B3, pas encore branché)
# Copie tenue à jour de TRAIN_SYSTEM/TRAIN_SYSTEM_EN (bench/matrix/finetune/label.py) :
# le prompt court sur lequel les modèles affinés sont réellement entraînés, par
# opposition à SUMMARY_SYSTEM (long, avec exemples) que narrator.py envoie aujourd'hui
# à n'importe quel modèle configuré. tests/test_finetune_alignment.py (P18) échoue si
# cette copie et l'original de label.py divergent, dans un sens ou dans l'autre.
SUMMARY_SYSTEM_FINETUNED = (
    "Tu lis la sortie d'une commande de terminal et tu dis à voix haute l'essentiel, en français. "
    "Réponds par une seule ligne courte, 15 mots au plus : d'abord le résultat, puis un détail utile. "
    "Recopie les noms et les nombres exactement comme dans la sortie. Si une information n'est pas "
    "écrite dans la sortie, ne la donne pas : n'invente jamais."
)

SUMMARY_SYSTEM_FINETUNED_EN = (
    "You read the output of a terminal command and say the essential aloud, in English. "
    "Answer with a single short line, 15 words at most: the result first, then one useful detail. "
    "Copy names and numbers exactly as they appear in the output. If a detail is not "
    "written in the output, do not give it: never invent."
)


def finetuned_summary_messages(cmd: str, exit_code: int | None, duration: float, output: str,
                               nlines: int, cwd: str = "", language: str = "fr",
                               facts: list[str] | None = None) -> list[dict]:
    """Messages que B3 devra envoyer à un modèle affiné, à la place de summary_messages().

    Même tour utilisateur que summary_messages() (Commande/Statut/Durée/Sortie) : c'est
    déjà celui que label.py copie pour étiqueter, aucune raison d'en construire un autre.
    Seul le prompt système change, pour le prompt court réellement appris par le modèle
    (étapes B3 et P18 du banc) plutôt que SUMMARY_SYSTEM.

    B3 doit aussi passer `output` déjà réduit au plafond du modèle affiné retenu par
    P15/P17 (voisin de 200 jetons pour Granite, mesuré P11) au lieu de cfg.summary_chars
    (1500, calibré pour SUMMARY_SYSTEM) : ce plafond n'est pas figé ici, faute de modèle
    affiné livré au moment de P18 (P15/P17 encore en cours).
    """
    msgs = summary_messages(cmd, exit_code, duration, output, nlines, cwd, language, facts)
    msgs[0] = {"role": "system",
              "content": SUMMARY_SYSTEM_FINETUNED_EN if language == "en" else SUMMARY_SYSTEM_FINETUNED}
    return msgs


def progress_messages(cmd: str, elapsed: float, recent: str, language: str = "fr") -> list[dict]:
    if language == "en":
        user = f"Command: {cmd}\nRunning for {int(elapsed)} s\nLast lines:\n{recent}"
        system = PROGRESS_SYSTEM_EN
    else:
        user = f"Commande : {cmd}\nEn cours depuis {int(elapsed)} s\nDernières lignes :\n{recent}"
        system = PROGRESS_SYSTEM
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def start_messages(cmd: str, language: str = "fr") -> list[dict]:
    system = START_SYSTEM_EN if language == "en" else START_SYSTEM
    return [{"role": "system", "content": system}, {"role": "user", "content": cmd}]


# ---------------------------------------------------------------- modèle affiné : détail, début, progression (B3b/B3c)
# Copies tenues à jour de bench/matrix/finetune/label_features.py (TRAIN_DETAILS_SYSTEM,
# TRAIN_START_SYSTEM, TRAIN_PROGRESS_SYSTEM, et leurs pendants TRAIN_*_EN depuis le commit
# cdb0802) : le corpus K3/H3a entraîne ces trois fonctionnalités en français et en anglais,
# via build_feature_corpus.py --lang en. narrator.py peut donc basculer vers ces prompts en
# `cfg.language == "fr"` ou `"en"` ; toute autre langue reste une erreur d'appelant.
DETAILS_SYSTEM_FINETUNED = (
    "Tu lis la sortie d'une commande de terminal et tu en donnes le détail, en français. "
    "Réponds en 1 à 5 points courts séparés par des points, 60 mots au plus : les faits utiles, "
    "pas la sortie entière. Recopie les noms, les nombres et les messages d'erreur exactement comme "
    "dans la sortie. Ne donne jamais une cause, une explication ni une solution que la sortie n'écrit "
    "pas : si la sortie ne dit pas pourquoi, ne le dis pas. Ne répète ni le statut, ni la durée, ni le "
    "nombre de lignes. N'invente jamais."
)

START_SYSTEM_FINETUNED = (
    "Tu lis une commande de terminal, avant son exécution, et tu dis en français ce qu'elle va "
    "faire. 10 mots au plus, commence par un verbe à l'infinitif ou un nom. N'invente jamais."
)

PROGRESS_SYSTEM_FINETUNED = (
    "Une commande longue est en cours sur un terminal. Tu lis les dernières lignes affichées "
    "et tu dis, en français, ce qu'elle est en train de faire maintenant. Une phrase courte, "
    "12 mots au plus. N'invente jamais ce qui n'est pas écrit."
)

DETAILS_SYSTEM_FINETUNED_EN = (
    "You read the output of a terminal command and give its detail, in English. "
    "Answer in 1 to 5 short points separated by periods, 60 words at most: the useful facts, "
    "not the whole output. Copy names, numbers and error messages exactly as in the output. "
    "Never give a cause, an explanation or a fix that the output does not write: if the output "
    "does not say why, do not say it. Do not repeat the status, the duration or the number of lines. "
    "Never invent."
)

START_SYSTEM_FINETUNED_EN = (
    "You read a terminal command, before it runs, and say in English what it will do. "
    "10 words at most, start with an infinitive verb or a noun. Never invent."
)

PROGRESS_SYSTEM_FINETUNED_EN = (
    "A long command is running in a terminal. You read the last lines displayed and say, "
    "in English, what it is doing right now. One short sentence, 12 words at most. "
    "Never invent what is not written."
)

_FINETUNED_FR_EN = ("fr", "en")


def finetuned_details_messages(cmd: str, exit_code: int | None, duration: float, output: str,
                               nlines: int, language: str = "fr") -> list[dict]:
    """Messages que narrator._details() doit envoyer à un modèle affiné (B3b/B3c).

    Même tour utilisateur que details_messages() : `output` doit déjà être plafonné par
    l'appelant (narrator.py : FINETUNED_DETAIL_CHARS, comme bench/matrix/finetune/
    build_feature_corpus.py:detail_entry, MAX_CHARS = 1500). Le corpus n'a entraîné le
    détail qu'en français et en anglais (B3c, commit cdb0802) : un autre `language` est
    une erreur d'appelant à faire remonter, pas un cas à dégrader silencieusement vers un
    prompt jamais appris.
    """
    if language not in _FINETUNED_FR_EN:
        raise ValueError(f"finetuned_details_messages n'a de prompt appris qu'en français et en anglais, reçu {language!r}")
    msgs = details_messages(cmd, exit_code, duration, output, nlines, language=language)
    msgs[0] = {"role": "system",
              "content": DETAILS_SYSTEM_FINETUNED_EN if language == "en" else DETAILS_SYSTEM_FINETUNED}
    return msgs


def finetuned_start_messages(cmd: str, language: str = "fr") -> list[dict]:
    """Pendant affiné de start_messages() : rien à plafonner (`cmd` seul), même limite de
    langue que finetuned_details_messages (corpus K3/H3a français et anglais)."""
    if language not in _FINETUNED_FR_EN:
        raise ValueError(f"finetuned_start_messages n'a de prompt appris qu'en français et en anglais, reçu {language!r}")
    system = START_SYSTEM_FINETUNED_EN if language == "en" else START_SYSTEM_FINETUNED
    return [{"role": "system", "content": system}, {"role": "user", "content": cmd}]


def finetuned_progress_messages(cmd: str, elapsed: float, recent: str, language: str = "fr") -> list[dict]:
    """Pendant affiné de progress_messages() : `recent` ne doit pas être coupé au-delà des
    15 dernières lignes captées par l'appelant (narrator.py) - le corpus d'entraînement
    (build_feature_corpus.py:progress_windows, tail=15) n'applique aucun plafond de
    caractères supplémentaire, contrairement au profil générique (narrator.py, `[-2500:]`)."""
    if language not in _FINETUNED_FR_EN:
        raise ValueError(f"finetuned_progress_messages n'a de prompt appris qu'en français et en anglais, reçu {language!r}")
    msgs = progress_messages(cmd, elapsed, recent, language=language)
    msgs[0] = {"role": "system",
              "content": PROGRESS_SYSTEM_FINETUNED_EN if language == "en" else PROGRESS_SYSTEM_FINETUNED}
    return msgs
