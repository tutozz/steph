# SPDX-License-Identifier: MIT

"""T6: English translation of the A7 invention judge prompt (judge_lib_a7.py), same method,
rules, JSON contract and call_judge() signature; only the language of the instructions changes.
Used to test whether the French prompt biases the verdicts on English phrases.
"""

import json
import re
import urllib.request

PORT = 8931
URL = f"http://127.0.0.1:{PORT}/v1/chat/completions"

SYSTEM_PROMPT = """You are a strict judge who detects inventions in the answers of a terminal voice assistant.
You are given, in an order that may vary, the context sent to this assistant (a command with its status, its exit code and its output; or a command history followed by a question) and the sentence the assistant produced in reply. Treat both blocks the same way, whichever comes first.

Mandatory method, in this order:
1. Find in the sentence to judge EACH verifiable fact, one by one: each number (percentage, quantity, size, line), each name (file, package, interface, host), each status (success/failure) and each cause.
2. For each fact found in step 1, look for its exact value in the context, digit by digit.
3. If the value differs from the one in the context, even slightly (another percentage, another number of Gi, another line), or if the fact appears nowhere in the context: it is an invention, add it to the list. Do not stop at the first verified fact: check all of them down to the last, including numbers that look alike.

Rules:
- A rewording, a converted unit or a faithful rounding (example: "about 700 GB" for "685G") is never an invention.
- A "success" or "failure" status stated in the sentence that contradicts the exit code given in the context is always an invention.
- A "line N" mention is an invention as soon as N does not appear as a line number in the context.
- Requested information correctly declared absent ("Not in the history.") is not an invention.

Answer only with strict JSON, without any text around it, exactly in this form:
{"inventions": ["<invented fact 1>", "<invented fact 2>"], "verdict": "ok"}
or, if there is no invention:
{"inventions": [], "verdict": "ok"}
The verdict is "invention" as soon as the "inventions" list contains at least one element, otherwise "ok"."""

USER_TEMPLATE_A = """Context (input sent to the judged model):
{context}

Sentence produced by the model to judge:
{phrase}

List the invented facts of this sentence with respect to the context above."""

USER_TEMPLATE_B = """Here is the input sent to a terminal assistant:
{context}

Here is the sentence the assistant answered, to check:
{phrase}

Before answering, do this silently: pick out one by one every number, name, status and line number present in the sentence to check, and for each one, find the matching value just above in the input. Mark as an invention any element whose value does not match exactly, or that appears nowhere above."""


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
