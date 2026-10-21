# SPDX-License-Identifier: MIT

import json
import re
import urllib.request

PORT = 8931
URL = f"http://127.0.0.1:{PORT}/v1/chat/completions"

SYSTEM_PROMPT = """Tu es un juge strict qui détecte les inventions dans les réponses d'un assistant vocal de terminal.
On te donne, dans un ordre qui peut varier, le contexte envoyé à cet assistant (une commande avec son statut, son code de sortie et sa sortie ; ou un historique de commandes suivi d'une question) et la phrase que l'assistant a produite en réponse. Traite les deux blocs de la même façon, quel que soit celui qui apparaît en premier.

Méthode obligatoire, dans cet ordre :
1. Repère dans la phrase à juger CHAQUE fait vérifiable, un par un : chaque nombre (pourcentage, quantité, taille, ligne), chaque nom (fichier, paquet, interface, hôte), chaque statut (succès/échec) et chaque cause.
2. Pour chaque fait repéré à l'étape 1, cherche sa valeur exacte dans le contexte, chiffre par chiffre.
3. Si la valeur diffère de celle du contexte, même légèrement (un autre pourcentage, un autre nombre de Gi, une autre ligne), ou si le fait n'apparaît nulle part dans le contexte : c'est une invention, à ajouter à la liste. Ne t'arrête pas au premier fait vérifié : contrôle-les tous jusqu'au dernier, y compris les nombres qui se ressemblent.

Règles :
- Une reformulation, une unité convertie ou un arrondi fidèle (exemple : « environ 700 Go » pour « 685G ») n'est jamais une invention.
- Un statut « succès » ou « échec » annoncé dans la phrase et contraire au code de sortie donné dans le contexte est toujours une invention.
- Une mention « ligne N » est une invention dès que N n'apparaît pas comme numéro de ligne dans le contexte.
- Une information demandée mais correctement déclarée absente (« Pas dans l'historique. ») n'est pas une invention.

Réponds uniquement par un JSON strict, sans aucun texte autour, exactement sous cette forme :
{"inventions": ["<fait inventé 1>", "<fait inventé 2>"], "verdict": "ok"}
ou, s'il n'y a aucune invention :
{"inventions": [], "verdict": "ok"}
Le verdict est "invention" dès que la liste "inventions" contient au moins un élément, sinon "ok"."""

USER_TEMPLATE_A = """Contexte (entrée envoyée au modèle jugé) :
{context}

Phrase produite par le modèle à juger :
{phrase}

Liste les faits inventés de cette phrase par rapport au contexte ci-dessus."""

# Pass 2 : même bloc contexte en premier (l'ordre inverse dégrade la détection des chiffres,
# vérifié lors de la validation), mais reformulation complète de la consigne pour faire varier
# le texte réellement envoyé au modèle d'une passe à l'autre.
USER_TEMPLATE_B = """Voici l'entrée envoyée à un assistant de terminal :
{context}

Voici la phrase que l'assistant a répondue, à vérifier :
{phrase}

Avant de répondre, fais ceci en silence : relève un par un tous les nombres, noms, statuts et numéros de ligne présents dans la phrase à vérifier, et pour chacun, retrouve la valeur correspondante juste au-dessus dans l'entrée. Note comme invention tout élément dont la valeur ne correspond pas exactement, ou qui n'apparaît nulle part au-dessus."""


def _extract_json(text):
    text = text.strip()
    # retire d'éventuelles balises de raisonnement résiduelles
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    # retire un habillage markdown ```json ... ```
    m = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not m:
        raise ValueError(f"pas de JSON dans la réponse : {text!r}")
    return json.loads(m.group(0))


def call_judge(context, phrase, pass_id="A", timeout=120):
    template = USER_TEMPLATE_A if pass_id == "A" else USER_TEMPLATE_B
    user_content = template.format(context=context, phrase=phrase)
    payload = {
        "model": "qwen3.5-9b-judge",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    req = urllib.request.Request(
        URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    content = body["choices"][0]["message"]["content"]
    try:
        parsed = _extract_json(content)
    except Exception as e:
        return {"inventions": [], "verdict": "erreur", "_raw": content, "_error": str(e)}
    inventions = parsed.get("inventions", [])
    verdict = parsed.get("verdict", "invention" if inventions else "ok")
    return {"inventions": inventions, "verdict": verdict, "_raw": content}
