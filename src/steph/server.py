"""Socket de contrôle de la session : questions, stop, répéter…

Protocole : une requête JSON par connexion (une ligne), réponses en lignes
JSON : {"t": "morceau"}…, puis {"done": true}.
"""

from __future__ import annotations

import json
import os
import queue
import socket
import threading
import time

from .grounding import ground_stream
from .narrator import clean_llm_text
from .qa_tools import ask_with_tools
from .strings import t as _t


class _QueueIter:
    def __init__(self):
        self.q: queue.Queue = queue.Queue()

    def put(self, x):
        self.q.put(x)

    def __iter__(self):
        while True:
            x = self.q.get()
            if x is None:
                return
            yield x


class ControlServer:
    def __init__(self, path: str, narrator):
        self.path = path
        self.nar = narrator
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass
        self.sock.bind(path)
        os.chmod(path, 0o600)
        self.sock.listen(8)
        threading.Thread(target=self._accept, daemon=True, name="ctl").start()

    def close(self) -> None:
        try:
            self.sock.close()
            os.unlink(self.path)
        except OSError:
            pass

    def _accept(self) -> None:
        while True:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            threading.Thread(target=self._serve, args=(conn,), daemon=True).start()

    def _serve(self, conn: socket.socket) -> None:
        f = conn.makefile("rwb", buffering=0)

        def send(obj) -> bool:
            try:
                f.write((json.dumps(obj, ensure_ascii=False) + "\n").encode())
                return True
            except OSError:
                return False

        try:
            line = f.readline()
            req = json.loads(line or b"{}")
            op = req.get("op")
            if op == "ask":
                self._ask(req.get("q", ""), send, speak=req.get("speak", True))
            elif op in ("stop", "repeat", "details", "prev", "next", "first", "last"):
                self.nar.on_key(op)
            elif op == "say":
                self.nar.sp.say(req.get("text", ""))
            elif op == "history":
                send({"t": self.nar.s.context(self.nar.cfg.qa_block_chars, self.nar.cfg.qa_budget_chars)})
            elif op == "status":
                c = self.nar.s.current
                send({"t": json.dumps({"running": c.cmd if c else None,
                                       "commands": len(self.nar.s.commands),
                                       "llm": self.nar.llm.healthy()}, ensure_ascii=False)})
            send({"done": True})
        except Exception as e:
            send({"error": repr(e)})
        finally:
            try:
                conn.close()
            except OSError:
                pass

    def _ask(self, question: str, send, speak: bool = True) -> None:
        question = question.strip()
        if not question:
            return
        s = self.nar.s
        if not self.nar._llm_ok():
            msg = "Le modèle local n'est pas encore prêt, réessaie dans quelques secondes."
            send({"t": msg})
            if speak:
                self.nar.sp.say(msg)
            return
        prefix = self.nar.qa_messages()
        msgs = prefix + [{"role": "user", "content": f"(dossier actuel : {s.cwd})\n{question}"}]
        tee = _QueueIter()
        if speak:
            self.nar.sp.say_stream(tee)
            # P20 : dite seulement, jamais envoyée à la fenêtre ni gardée dans s.qa
            # D4 : plusieurs tours du modèle avant la réponse, la phrase part toujours
            wait = _t(self.nar.cfg.language, "qa_wait") if self.nar.cfg.qa_tools else self.nar.qa_wait_phrase(prefix, msgs)
            if wait:
                tee.put(wait + " ")
        answer = ""
        failed = False
        tool_answer = None
        t0 = time.time()
        try:
            if self.nar.cfg.qa_tools:
                tool_answer = ask_with_tools(self.nar.llm, s, question, self.nar.cfg)
            if tool_answer is not None:
                # le slot 1 porte maintenant l'échange à outils, plus l'historique préchauffé
                self.nar._qa_cached = None
                cleaned = clean_llm_text(iter([tool_answer.text]), buffer_reasoning=self.nar.cfg.buffer_reasoning)
                evidence = tool_answer.evidence
            else:
                cleaned = clean_llm_text(self.nar.llm.stream(msgs, max_tokens=400, temperature=0.3, timeout=120, slot=1),
                                          buffer_reasoning=self.nar.cfg.buffer_reasoning)
                evidence = None
            if self.nar.cfg.ground_output:
                # P13 - garde-fou d'ancrage : un fait absent de l'historique fourni ->
                # « Pas dans l'historique. » plutôt qu'une réponse inventée. Mode à outils :
                # ancré sur ce que le modèle a lu (liste des commandes et résultats d'outils).
                history = evidence if evidence is not None else s.context(self.nar.cfg.qa_block_chars,
                                                                          self.nar.cfg.qa_budget_chars)
                cleaned = ground_stream(cleaned, history, is_qa=True, language=self.nar.cfg.language)
            for piece in cleaned:
                answer += piece
                tee.put(piece)
                if not send({"t": piece}):
                    break
        except Exception as e:
            err = f" (erreur du modèle : {e})"
            answer += err
            failed = True
            send({"t": err})
        finally:
            tee.put(None)
        s.qa.append({"q": question, "a": answer.strip(), "t": time.time() - t0})
        if not failed and tool_answer is None:
            self.nar.note_qa_cached()
