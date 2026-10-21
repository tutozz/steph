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


def _build_env(cfg: Config, exe: Path) -> dict:
    env = dict(os.environ)
    if exe.parent.name.startswith("llama-") or exe.parent.name == "bin":
        for var in ("LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH"):
            env[var] = f"{exe.parent}:{env.get(var, '')}"
    env.update(cfg.llm_env)
    return env


FINETUNED_CTX = 8192  # 2 slots of 4096: ~600 input tokens per summary, questions capped at 8000 chars


def _build_args(cfg: Config, exe: str) -> list[str]:
    finetuned = cfg.llm_profile == "finetuned"
    args = [
        exe, "-m", cfg.model,
        "--host", "127.0.0.1", "--port", str(cfg.llm_port),
        "-c", str(FINETUNED_CTX if finetuned else cfg.llm_ctx), "-ngl", str(cfg.llm_gpu_layers),
        "--parallel", str(cfg.llm_parallel), "--no-webui", "--jinja",
        "-b", str(cfg.llm_batch), "-ub", str(cfg.llm_ubatch),
        "--reasoning-budget", "0",
    ]
    if cfg.llm_flash_attn != "auto":
        args += ["-fa", cfg.llm_flash_attn]
    if cfg.llm_cache_type != "f16":
        args += ["-ctk", cfg.llm_cache_type, "-ctv", cfg.llm_cache_type]
    if finetuned:
        # the hybrid Mamba model copies its whole recurrent state per checkpoint: 2.3 GB for nothing (Q2c)
        args += ["--cache-ram", "0"]
    args += cfg.llm_extra_args
    return args


class LLM:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.base = f"http://127.0.0.1:{cfg.llm_port}"
        self.pidfile = RUNTIME_DIR / "llama-server.pid"
        self.logfile = RUNTIME_DIR / "llama-server.log"
        self.activity_file = RUNTIME_DIR / "llama-server.activity"  # dernière requête, toutes fenêtres
        self.busy_dir = RUNTIME_DIR / "llama-server.busy"  # une génération en cours, toutes fenêtres
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
            env = _build_env(self.cfg, exe)
            args = _build_args(self.cfg, str(exe))
            log = open(self.logfile, "ab")
            try:
                proc = subprocess.Popen(args, stdout=log, stderr=log, stdin=subprocess.DEVNULL,
                                        env=env, start_new_session=True)
            except OSError as e:  # llama-server absent
                log.write(f"lancement impossible : {e}\n".encode())
                return False
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
            # un serveur mort mais non récolté (zombie) répond encore à kill(pid, 0)
            try:
                if os.waitpid(pid, os.WNOHANG)[0] == pid:
                    return False
            except ChildProcessError:
                pass  # lancé par une autre session steph
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

    # ------------------------------------------------- déchargement au repos (Q2b)
    def touch_activity(self) -> None:
        """Marque une requête LLM réelle (résumé, question, détail, préchauffage) :
        remet à zéro l'horloge d'inactivité partagée par toutes les fenêtres."""
        try:
            RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
            self.activity_file.write_text(str(time.time()))
        except OSError:
            pass

    def idle_seconds(self) -> float:
        """Temps écoulé depuis la dernière requête LLM, toutes fenêtres confondues.
        Fichier absent (jamais touché depuis le démarrage) : 0.0, pour ne jamais
        décharger par erreur faute d'avoir vu passer une requête."""
        try:
            return time.time() - self.activity_file.stat().st_mtime
        except OSError:
            return 0.0

    def _mark_busy(self) -> Path | None:
        try:
            self.busy_dir.mkdir(parents=True, exist_ok=True)
            marker = self.busy_dir / f"{os.getpid()}-{threading.get_ident()}-{time.time_ns()}"
            marker.touch()
            return marker
        except OSError:
            return None

    def _unmark_busy(self, marker: Path | None) -> None:
        if marker is not None:
            marker.unlink(missing_ok=True)

    def _any_busy(self) -> bool:
        """Une génération est-elle en cours, dans cette fenêtre ou une autre ?"""
        try:
            return any(self.busy_dir.iterdir())
        except OSError:
            return False

    def try_unload_idle(self, idle_minutes: float) -> bool:
        """Décharge le serveur s'il est vraiment inactif partout (aucune génération
        en cours, dans cette fenêtre ou une autre). Jamais pendant une génération :
        True seulement si ce processus vient d'arrêter un serveur qui tournait
        encore (repli déterministe côté appelant sinon)."""
        if idle_minutes <= 0:
            return False
        if self.idle_seconds() < idle_minutes * 60 or self._any_busy():
            return False
        if not self.healthy():
            return False
        if self._any_busy():  # une génération a pu démarrer pendant la vérification
            return False
        self.stop_server()
        return True

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
        marker = None
        if not background:
            self.abort_background()
            self.active += 1
            marker = self._mark_busy()
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
            finished = False
            for raw in r:
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    finished = True
                    break
                try:
                    delta = json.loads(data)["choices"][0].get("delta", {})
                except (ValueError, KeyError, IndexError):
                    continue
                piece = delta.get("content")
                if piece:
                    yield piece
            if background and not finished:
                # abort_background() ferme la socket sans erreur : sans ceci, un préchauffage
                # coupé passerait pour fini et ne reprendrait jamais
                raise ConnectionError("préchauffage interrompu")
        finally:
            conn.close()
            if background:
                with self._bg_lock:
                    self._bg_conns.discard(conn)
            else:
                self.active -= 1
                self.last_done = time.time()
                self._unmark_busy(marker)
            self.touch_activity()

    def chat(self, messages: list[dict], tools: list[dict] | None = None, max_tokens: int = 400,
             temperature: float = 0.3, timeout: float = 60.0, slot: int | None = 1,
             tool_choice: str | None = None) -> dict:
        """Un tour sans flux, avec outils (D4, `qa_tools`) : renvoie le message de l'assistant,
        `tool_calls` compris, tel que llama-server le décode avec --jinja."""
        payload = self._payload(messages, max_tokens, temperature, False, slot)
        if tools:
            payload["tools"] = tools
        if tool_choice:
            payload["tool_choice"] = tool_choice
        self.abort_background()
        self.active += 1
        marker = self._mark_busy()
        conn = http.client.HTTPConnection("127.0.0.1", self.cfg.llm_port, timeout=timeout)
        try:
            conn.request("POST", "/v1/chat/completions", body=json.dumps(payload),
                         headers={"Content-Type": "application/json"})
            r = conn.getresponse()
            data = r.read()
            if r.status != 200:
                raise ConnectionError(f"llama-server HTTP {r.status}: {data[:200]!r}")
            return json.loads(data)["choices"][0]["message"]
        finally:
            conn.close()
            self.active -= 1
            self.last_done = time.time()
            self._unmark_busy(marker)
            self.touch_activity()

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
