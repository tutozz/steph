"""Questions « à outils » (D4) : le modèle reçoit la liste des commandes et lit l'historique par outils.

Invariant de sécurité et de vie privée : chaque outil lit seulement ce que steph a déjà capturé
dans la `Session` qu'on lui donne. Aucun accès au système de fichiers, au réseau, à l'exécution
de commandes ni à une autre session ; tests/test_qa_tools.py échoue si ce module importe ou
appelle de quoi en sortir. Tout plafond atteint (appels, temps) ou toute erreur du serveur rend
None : l'appelant repasse au mode actuel (historique complet).
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass

from . import prompts
from .session import Command, Session
from .strings import t as _t


def _function(name: str, description: str, properties: dict, required: list[str]) -> dict:
    return {"type": "function", "function": {
        "name": name, "description": description,
        "parameters": {"type": "object", "properties": properties, "required": required}}}


_ID = {"type": "integer", "description": "command number, as in the list"}
_PATTERN = {"type": "string", "description": "plain text to look for, case-insensitive (not a regex)"}

TOOLS = [
    _function("search_history", "Lines of the captured outputs that contain the text, with command number and line number.",
              {"pattern": _PATTERN, "command_id": _ID}, ["pattern"]),
    _function("get_output", "Lines of one command's captured output, numbered from 1.",
              {"command_id": _ID, "start": {"type": "integer", "description": "first line, from 1"},
               "count": {"type": "integer", "description": "number of lines"}}, ["command_id"]),
    _function("command_info", "Command text, folder, exit code, duration and line count of one command.",
              {"command_id": _ID}, ["command_id"]),
    _function("count_matches", "Number of output lines containing the text, per command.",
              {"pattern": _PATTERN, "command_id": _ID}, ["pattern"]),
]

_WORDS = {
    "fr": {"lines": "lignes", "running": "en cours", "none": "aucune ligne trouvée", "error": "erreur :",
           "more": "(+{n} lignes)", "fullscreen": "(application plein écran)", "empty": "(aucune sortie)",
           "nothing": "(aucune commande exécutée pour l'instant)"},
    "en": {"lines": "lines", "running": "running", "none": "no matching line", "error": "error:",
           "more": "(+{n} lines)", "fullscreen": "(full-screen application)", "empty": "(no output)",
           "nothing": "(no command run yet)"},
}
_LINE_CHARS = 300
# « [3] 22: » et « 22: » : numérotation ajoutée par les outils, pas un fait de la sortie ; l'ancrage
# ne doit pas y trouver les nombres qu'il vérifie
_NUMBERING = re.compile(r"^(?:\[\d+\] )?\d+: ", re.M)
# Gemma 4 E2B demande souvent count=1 puis conclut à l'absence (banc v3 dev) : une fenêtre plus
# petite que ceci devient la sortie entière depuis `start`, tête et queue gardées si elle déborde
_MIN_COUNT = 20


class SessionTools:
    """Les quatre outils, liés à une seule session ; `call` n'exécute que ceux de TOOLS."""

    def __init__(self, session: Session, language: str = "fr", result_chars: int = 1500) -> None:
        self._session = session
        self._w = _WORDS["en" if language == "en" else "fr"]
        self._result_chars = result_chars
        self._handlers = {
            "search_history": self._search_history,
            "get_output": self._get_output,
            "command_info": self._command_info,
            "count_matches": self._count_matches,
        }

    # ------------------------------------------------------------ vues
    def _commands(self) -> list[Command]:
        with self._session.lock:
            return [c for c in self._session.commands if not c.silent]

    def _lines(self, c: Command) -> list[str]:
        return [] if c.used_fullscreen else c.all_lines()

    def _head(self, c: Command) -> str:
        status = self._w["running"] if c.running else f"code {c.exit}"
        return f"[{c.id}] {c.cwd or '?'} $ {c.cmd}   ({status}, {c.duration:.0f} s, {c.out.total_lines} {self._w['lines']})"

    def index(self) -> str:
        return "\n".join(self._head(c) for c in self._commands()) or self._w["nothing"]

    def _error(self, what: str) -> str:
        return f"{self._w['error']} {what}"

    def _command(self, args: dict) -> Command | str:
        cid = args.get("command_id")
        if isinstance(cid, str) and cid.strip().isdigit():
            cid = int(cid)
        if not isinstance(cid, int) or isinstance(cid, bool):
            return self._error("command_id")
        for c in self._commands():
            if c.id == cid:
                return c
        return self._error(f"command_id {cid}")

    def _capped(self, lines: list[str]) -> str:
        out: list[str] = []
        size = 0
        for i, line in enumerate(lines):
            line = line[:_LINE_CHARS]
            if out and size + len(line) + 1 > self._result_chars:
                out.append(self._w["more"].format(n=len(lines) - i))
                break
            out.append(line)
            size += len(line) + 1
        return "\n".join(out)

    def _head_tail(self, lines: list[str]) -> str:
        lines = [line[:_LINE_CHARS] for line in lines]
        if sum(len(line) + 1 for line in lines) <= self._result_chars:
            return "\n".join(lines)
        head: list[str] = []
        size = 0
        for line in lines:
            if size + len(line) + 1 > self._result_chars // 3:
                break
            head.append(line)
            size += len(line) + 1
        tail: list[str] = []
        for line in reversed(lines[len(head):]):
            if size + len(line) + 1 > self._result_chars:
                break
            tail.insert(0, line)
            size += len(line) + 1
        gap = len(lines) - len(head) - len(tail)
        return "\n".join(head + [self._w["more"].format(n=gap)] + tail)

    def _matching(self, args: dict) -> tuple[list[Command], str] | str:
        pattern = args.get("pattern")
        if not isinstance(pattern, str) or not pattern.strip():
            return self._error("pattern")
        if "command_id" in args and args["command_id"] is not None:
            c = self._command(args)
            if isinstance(c, str):
                return c
            return [c], pattern.lower()
        return self._commands(), pattern.lower()

    # ------------------------------------------------------------ outils
    def _search_history(self, args: dict) -> str:
        found = self._matching(args)
        if isinstance(found, str):
            return found
        cmds, needle = found
        hits = [f"[{c.id}] {n}: {line}" for c in cmds
                for n, line in enumerate(self._lines(c), 1) if needle in line.lower()]
        return self._capped(hits) if hits else self._w["none"]

    def _get_output(self, args: dict) -> str:
        c = self._command(args)
        if isinstance(c, str):
            return c
        if c.used_fullscreen:
            return self._w["fullscreen"]
        lines = self._lines(c)
        if not lines:
            return self._w["empty"]
        start = args.get("start", 1)
        count = args.get("count")
        start = start if isinstance(start, int) and not isinstance(start, bool) and start > 0 else 1
        if not isinstance(count, int) or isinstance(count, bool) or count < _MIN_COUNT:
            count = len(lines)
        window = lines[start - 1:start - 1 + count]
        return self._head_tail([f"{n}: {line}" for n, line in enumerate(window, start)]) or self._w["none"]

    def _command_info(self, args: dict) -> str:
        c = self._command(args)
        if isinstance(c, str):
            return c
        return json.dumps({"id": c.id, "command": c.cmd, "folder": c.cwd or "?", "exit_code": c.exit,
                           "duration_s": round(c.duration), "lines": c.out.total_lines, "running": c.running},
                          ensure_ascii=False)

    def _count_matches(self, args: dict) -> str:
        found = self._matching(args)
        if isinstance(found, str):
            return found
        cmds, needle = found
        counts = {str(c.id): sum(needle in line.lower() for line in self._lines(c)) for c in cmds}
        counts = {k: v for k, v in counts.items() if v}
        counts["total"] = sum(counts.values())
        return json.dumps(counts)

    def call(self, name: str, args: dict) -> str:
        handler = self._handlers.get(name)
        if handler is None:
            return self._error(f"unknown tool {name}")
        if not isinstance(args, dict):
            return self._error("arguments")
        return handler(args)


# ---------------------------------------------------------------- boucle
@dataclass
class ToolAnswer:
    text: str
    calls: int
    evidence: str  # liste des commandes et résultats d'outils : ce que le modèle a vu, pour l'ancrage


def tool_messages(session: Session, question: str, language: str, max_calls: int, index: str) -> list[dict]:
    system = (prompts.QA_TOOLS_SYSTEM_EN if language == "en" else prompts.QA_TOOLS_SYSTEM).format(max_calls=max_calls)
    msgs = [{"role": "system", "content": system}]
    for ex in session.qa[-4:]:
        msgs.append({"role": "user", "content": ex["q"]})
        msgs.append({"role": "assistant", "content": ex["a"]})
    user = _t(language, "qa_tools_index_header").format(index=index)
    msgs.append({"role": "user", "content": f"{user}\n\n(dossier actuel : {session.cwd})\n{question}"})
    return msgs


def _arguments(raw) -> dict | None:
    if isinstance(raw, dict):
        return raw
    try:
        args = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return None
    return args if isinstance(args, dict) else None


def ask_with_tools(llm, session: Session, question: str, cfg) -> ToolAnswer | None:
    """Répond par appels d'outils ; None au premier plafond atteint ou à la première erreur."""
    deadline = time.monotonic() + cfg.qa_tools_timeout_seconds
    tools = SessionTools(session, cfg.language, cfg.qa_tools_result_chars)
    rules = prompts.QA_TOOLS_ANSWER_EN if cfg.language == "en" else prompts.QA_TOOLS_ANSWER
    index = tools.index()
    msgs = tool_messages(session, question, cfg.language, cfg.qa_tools_max_calls, index)
    evidence = [index]
    calls = 0
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        try:
            # 1er tour : un appel imposé, sinon Gemma répond de mémoire sans lire (banc v3 dev)
            msg = llm.chat(msgs, tools=TOOLS, max_tokens=400, temperature=0.3, timeout=remaining, slot=1,
                           tool_choice=None if calls else "required")
        except Exception:
            return None
        if time.monotonic() > deadline:
            return None
        tool_calls = msg.get("tool_calls") or []
        if not tool_calls:
            # aucun appel malgré le 1er tour imposé : modèle ou gabarit sans outils (v1.0), mode actuel
            text = (msg.get("content") or "").strip()
            return ToolAnswer(text, calls, "\n".join(evidence)) if text and calls else None
        if calls + len(tool_calls) > cfg.qa_tools_max_calls:
            return None
        msgs.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": tool_calls})
        for tc in tool_calls:
            fn = tc.get("function") or {}
            name = fn.get("name", "")
            args = _arguments(fn.get("arguments"))
            result = tools.call(name, args) if args is not None else tools._error("arguments")
            evidence.append(_NUMBERING.sub("", result))
            msgs.append({"role": "tool", "tool_call_id": tc.get("id", ""), "name": name,
                         "content": f"{result}\n\n{rules}"})
            calls += 1
