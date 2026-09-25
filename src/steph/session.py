"""Historique de la session : une entrée par commande exécutée."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

from .textproc import OutputCleaner, compact_output


@dataclass
class Command:
    id: int
    cmd: str
    cwd: str
    start: float = field(default_factory=time.time)
    end: float | None = None
    exit: int | None = None
    out: OutputCleaner = field(default_factory=OutputCleaner)
    last_output_at: float = field(default_factory=time.time)
    silent: bool = False
    summary: str = ""
    updates: list[str] = field(default_factory=list)
    used_fullscreen: bool = False
    frozen: str | None = None  # bloc figé pour l'historique des questions
    # état du narrateur
    announced_start: bool = False
    last_update_at: float = 0.0
    lines_at_last_update: int = 0
    last_prompt_said: str = ""
    last_spoken_update: str = ""
    # mode interactif (ssh, python, psql…) : on lit la réponse à chaque Entrée
    interactive: bool = False
    awaiting_reply: bool = False
    enter_mark: int = 0
    enter_at: float = 0.0
    typed: str = ""
    enter_count: int = 0
    probed_partial: str = ""
    prompts_said: list[str] = field(default_factory=list)

    @property
    def running(self) -> bool:
        return self.end is None

    @property
    def duration(self) -> float:
        return (self.end or time.time()) - self.start

    def feed(self, data: bytes) -> None:
        self.out.feed(data)
        self.last_output_at = time.time()
        if self.out.fullscreen:
            self.used_fullscreen = True

    def all_lines(self) -> list[str]:
        lines = list(self.out.lines)
        if self.out.partial:
            lines.append(self.out.partial)
        return lines

    def lines_since(self, total_mark: int) -> list[str]:
        """Lignes complètes arrivées après la ligne n° total_mark (compteur absolu)."""
        offset = self.out.total_lines - len(self.out.lines)
        return self.out.lines[max(0, total_mark - offset):]

    def compact(self, max_chars: int = 6000) -> str:
        return compact_output(self.all_lines(), max_chars, self.out.dropped)


class Session:
    def __init__(self) -> None:
        self.commands: list[Command] = []
        self.lock = threading.RLock()
        self.cwd = ""
        self.qa: list[dict] = []  # échanges questions/réponses
        self.context_start = 0

    def start(self, cmd: str) -> Command:
        with self.lock:
            c = Command(id=len(self.commands) + 1, cmd=cmd, cwd=self.cwd)
            self.commands.append(c)
            return c

    @property
    def current(self) -> Command | None:
        with self.lock:
            if self.commands and self.commands[-1].running:
                return self.commands[-1]
            return None

    @property
    def last(self) -> Command | None:
        with self.lock:
            return self.commands[-1] if self.commands else None

    # ---------------------------------------------------- mode questions
    # L'historique est construit en « ajout seul » : chaque commande terminée est
    # figée en un bloc texte qui ne change plus. Le préfixe envoyé au LLM reste
    # donc identique d'une question à l'autre et llama-server réutilise son
    # cache : seule la fin (nouvelles commandes + question) est recalculée.
    def _block(self, c: Command, chars: int) -> str:
        status = "en cours" if c.running else f"code {c.exit}"
        head = f"[{c.id}] {c.cwd or '?'} $ {c.cmd}   ({status}, {c.duration:.0f} s, {c.out.total_lines} lignes)"
        body = c.compact(chars) if not c.used_fullscreen else "(application plein écran)"
        return head + "\n" + (body or "(aucune sortie)")

    def context(self, block_chars: int = 2500, budget_chars: int = 36000) -> str:
        with self.lock:
            done = [c for c in self.commands if not c.silent and not c.running]
            running = [c for c in self.commands if not c.silent and c.running]
            for c in done:
                if c.frozen is None:
                    c.frozen = self._block(c, block_chars)
            blocks = [c.frozen for c in done]
            # trop long : on coupe les plus anciennes par paquets (le cache n'est
            # invalidé qu'à ces moments-là)
            total = sum(len(b) + 2 for b in blocks)
            start = self.context_start
            while total - sum(len(b) + 2 for b in blocks[:start]) > budget_chars and start < len(blocks) - 1:
                start = min(len(blocks) - 1, start + max(1, (len(blocks) - start) // 3))
            self.context_start = start
            parts = blocks[start:]
            if start:
                parts.insert(0, f"({start} commandes plus anciennes omises)")
            for c in running:
                parts.append(self._block(c, block_chars))
        return "\n\n".join(parts) or "(aucune commande exécutée pour l'instant)"
