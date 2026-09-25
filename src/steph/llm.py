"""Client llama-server (API OpenAI) + gestion du processus serveur partagé."""

from __future__ import annotations

import http.client
import json
import os
import signal
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Iterator

from .config import RUNTIME_DIR, Config


class LLM:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.base = f"http://127.0.0.1:{cfg.llm_port}"
        self.pidfile = RUNTIME_DIR / "llama-server.pid"
        self.logfile = RUNTIME_DIR / "llama-server.log"
        self.active = 0  # requêtes prioritaires en cours
        self.last_done = 0.0
        self._bg_conns: set[http.client.HTTPConnection] = set()
        self._bg_lock = threading.Lock()

    # ------------------------------------------------------------ serveur
    def healthy(self) -> bool:
        try:
            with urllib.request.urlopen(self.base + "/health", timeout=0.5) as r:
                return r.status == 200
        except (urllib.error.URLError, OSError, TimeoutError):
            return False

    def ensure_server(self, wait: float = 60.0) -> bool:
        if self.healthy():
            return True
        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        if not self._pid_alive():
            exe = Path(self.cfg.llama_server)
            env = dict(os.environ)
            if exe.parent.name.startswith("llama-"):
                env["LD_LIBRARY_PATH"] = f"{exe.parent}:{env.get('LD_LIBRARY_PATH', '')}"
            args = [
                str(exe), "-m", self.cfg.model,
                "--host", "127.0.0.1", "--port", str(self.cfg.llm_port),
                "-c", str(self.cfg.llm_ctx), "-ngl", str(self.cfg.llm_gpu_layers),
                "--parallel", "2", "--no-webui", "--jinja", "-b", "512", "-ub", "512",
                "--reasoning-budget", "0",
            ]
            log = open(self.logfile, "ab")
            proc = subprocess.Popen(args, stdout=log, stderr=log, stdin=subprocess.DEVNULL,
                                    env=env, start_new_session=True)
            self.pidfile.write_text(str(proc.pid))
        deadline = time.time() + wait
        while time.time() < deadline:
            if self.healthy():
                return True
            if not self._pid_alive():
                return False
            time.sleep(0.2)
        return False

    def _pid_alive(self) -> bool:
        try:
            pid = int(self.pidfile.read_text())
            os.kill(pid, 0)
            return True
        except (OSError, ValueError):
            return False

    def stop_server(self) -> None:
        try:
            pid = int(self.pidfile.read_text())
            os.kill(pid, signal.SIGTERM)
        except (OSError, ValueError):
            pass
        self.pidfile.unlink(missing_ok=True)

    # ------------------------------------------------------------ requêtes
    def _payload(self, messages, max_tokens, temperature, stream, slot=None):
        p = {
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": 0.9,
            "stream": stream,
            "cache_prompt": True,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        if slot is not None:
            p["id_slot"] = slot
        return p

    def stream(self, messages: list[dict], max_tokens: int = 120, temperature: float = 0.2,
               timeout: float = 30.0, slot: int | None = 0, background: bool = False) -> Iterator[str]:
        """Flux de tokens. Une requête `background` (préchauffage) est coupée dès
        qu'une requête normale arrive, pour lui laisser tout le GPU."""
        body = json.dumps(self._payload(messages, max_tokens, temperature, True, slot))
        if not background:
            self.abort_background()
            self.active += 1
        conn = http.client.HTTPConnection("127.0.0.1", self.cfg.llm_port, timeout=timeout)
        if background:
            with self._bg_lock:
                self._bg_conns.add(conn)
        try:
            conn.request("POST", "/v1/chat/completions", body=body,
                         headers={"Content-Type": "application/json"})
            r = conn.getresponse()
            if r.status != 200:
                raise ConnectionError(f"llama-server HTTP {r.status}: {r.read()[:200]!r}")
            for raw in r:
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    delta = json.loads(data)["choices"][0].get("delta", {})
                except (ValueError, KeyError, IndexError):
                    continue
                piece = delta.get("content")
                if piece:
                    yield piece
        finally:
            conn.close()
            if background:
                with self._bg_lock:
                    self._bg_conns.discard(conn)
            else:
                self.active -= 1
                self.last_done = time.time()

    def abort_background(self) -> None:
        with self._bg_lock:
            conns = list(self._bg_conns)
        for c in conns:
            try:
                if c.sock:
                    c.sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    def complete(self, messages: list[dict], max_tokens: int = 120, temperature: float = 0.2,
                 timeout: float = 30.0, slot: int | None = 0, background: bool = False) -> str:
        return "".join(self.stream(messages, max_tokens, temperature, timeout, slot, background)).strip()
