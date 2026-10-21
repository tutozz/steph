"""Le narrateur : décide quoi dire, quand, et s'il faut passer par le LLM.

Principe : déterministe d'abord (instantané, exact), LLM seulement quand la
sortie est trop longue ou trop complexe pour être lue telle quelle.
"""

from __future__ import annotations

import os
import queue
import re
import shlex
import threading
import time
from typing import Iterator

from . import prompts
from .config import Config
from .digest import digest, extract_facts, grep_no_match, not_found_sentence, resolve
from .grounding import ground_stream
from .llm import LLM
from .session import Command, Session
from .strings import t as _t
from .textproc import detect_percent, detect_stage, important_lines, looks_like_prompt, strip_ansi, strip_symbol_runs
from .tts import Speaker

META_COMMANDS = ("q", "steph", "clear", "reset", "exit", "logout")
SILENT_OK = {"cd", "pushd", "popd", "export", "unset", "alias", "unalias", "source", ".", "set",
             "clear", "reset", "true", "history", "fg", "bg", "jobs", "wait"}

INTERACTIVE = {"ssh", "mosh", "telnet", "ipython", "irb", "psql", "mysql", "mariadb", "sqlite3",
               "redis-cli", "mongo", "mongosh", "ftp", "sftp", "bc", "gdb", "pdb", "su", "bash", "zsh",
               "sh", "fish", "nc", "ncat", "lftp", "virsh", "iex", "ghci", "lua", "R", "guile"}
REPL_IF_NO_ARGS = {"python", "python3", "node", "deno", "bun", "php", "perl", "ruby", "julia", "sage"}
RULES = ("mute", "mute-all", "verbatim", "summary")

# masquage du premier jeton (P9) : le premier jeton d'un résumé LLM = 100 % lecture du
# prompt (mesuré P7). Le temps d'attente s'estime à partir de ces deux constantes.
CHARS_PER_TOKEN = 3.2  # jetons d'entrée ≈ caractères / 3.2
BASE_SPEECH_WORDS_PER_SEC = 2.5  # débit de lecture français à speech_rate = 1.0

# profil affiné (B3) : palier retenu par P11 pour l'entrée du résumé (Granite, ~200 jetons) -
# bench/matrix/make_cases_compact.py VARIANTS["granite200"] = chars_budget("granite", 200).
# À revoir si B4/B6 retiennent un autre modèle que Granite pour le catalogue.
FINETUNED_SUMMARY_CHARS = 587
# plafond d'historique du mode questions décidé en H2 pour le corpus d'entraînement P15a
# (bench/matrix/finetune/qa_corpus.py DEFAULT_BUDGET_CHARS) ; le profil générique garde
# cfg.qa_budget_chars (36 000), jamais entraîné sur ce plafond.
FINETUNED_QA_BUDGET_CHARS = 8000
# plafond d'entrée du détail affiné (B3b, K3/H3a) : celui réellement utilisé pour construire
# le corpus détail (bench/matrix/finetune/build_feature_corpus.py MAX_CHARS = 1500), distinct
# de FINETUNED_SUMMARY_CHARS (587, propre au résumé/granite200) et du plafond générique du
# détail (6000, cfg.compact() par défaut, jamais entraîné).
FINETUNED_DETAIL_CHARS = 1500

_STATUS_ECHO = re.compile(r"^\s*(Succès|Échec|Success|Failed)\b[.,:]?\s*")


def is_interactive(cmd: str) -> bool:
    fw = first_word(cmd)
    try:
        parts = shlex.split(cmd)
    except ValueError:
        parts = cmd.split()
    if fw in INTERACTIVE:
        # ssh hôte commande : pas interactif
        if fw == "ssh":
            args = [p for p in parts[parts.index("ssh") + 1:] if p] if "ssh" in parts else []
            pos = [a for i, a in enumerate(args) if not a.startswith("-") and not (i and args[i - 1] in ("-p", "-i", "-l", "-o", "-J", "-F", "-L", "-R", "-D"))]
            return len(pos) <= 1
        return True
    if fw in REPL_IF_NO_ARGS:
        rest = parts[parts.index(fw) + 1:] if fw in parts else []
        return not rest or rest == ["-i"]
    if fw in ("docker", "podman", "kubectl") and any(a in parts for a in ("-it", "-ti", "-i")):
        return True
    if fw == "sudo" or (parts[:1] == ["sudo"] and any(a in parts for a in ("-i", "-s"))):
        return True
    return False


KNOWN_START = [
    (re.compile(r"\bapt(-get)?\s+(full-|dist-)?upgrade"), "mise à jour des paquets"),
    (re.compile(r"\bapt(-get)?\s+update"), "mise à jour de la liste des paquets"),
    (re.compile(r"\bapt(-get)?\s+install\s+(?P<x>.+)"), "installation de {x}"),
    (re.compile(r"\bapt(-get)?\s+(remove|purge)\s+(?P<x>.+)"), "suppression de {x}"),
    (re.compile(r"\bdnf\s+(upgrade|update)"), "mise à jour des paquets"),
    (re.compile(r"\bdnf\s+install\s+(?P<x>.+)"), "installation de {x}"),
    (re.compile(r"\bpip3?\s+install\s+(?P<x>.+)"), "installation Python de {x}"),
    (re.compile(r"\buv\s+(sync|add|pip install)"), "installation des dépendances Python"),
    (re.compile(r"\bnpm\s+(i|install|ci)\b"), "installation des dépendances npm"),
    (re.compile(r"\bgit\s+clone\s+\S*?(?P<x>[\w.-]+?)(\.git)?\s*$"), "clonage du dépôt {x}"),
    (re.compile(r"\bgit\s+(pull|fetch)"), "récupération depuis le dépôt distant"),
    (re.compile(r"\bgit\s+push"), "envoi vers le dépôt distant"),
    (re.compile(r"\bdocker\s+(compose\s+)?build"), "construction de l'image Docker"),
    (re.compile(r"\bdocker\s+pull\s+(?P<x>\S+)"), "téléchargement de l'image {x}"),
    (re.compile(r"\b(make|ninja|cmake --build)\b"), "compilation"),
    (re.compile(r"\bcargo\s+build"), "compilation Rust"),
    (re.compile(r"\bping\b"), "ping en cours"),
    (re.compile(r"\bansible-playbook\s+(?P<x>\S+)"), "exécution du playbook {x}"),
    (re.compile(r"\b(rsync|scp|cp)\b"), "copie de fichiers"),
    (re.compile(r"\bsleep\b"), "attente"),
]


def _plural(n: int, language: str) -> bool:
    # fr : accord dès 2 (0/1 restent au singulier, comme "0 seconde") ; en : accord dès que n != 1.
    return n != 1 if language == "en" else n > 1


def fmt_duration(sec: float, language: str = "fr") -> str:
    sec = int(round(sec))
    if sec < 60:
        key = "duration_seconds" if _plural(sec, language) else "duration_second"
        return f"{sec} {_t(language, key)}"
    m, s = divmod(sec, 60)
    if m < 60:
        key = "duration_minutes" if _plural(m, language) else "duration_minute"
        return f"{m} {_t(language, key)}" + (f" {s}" if s else "")
    h, m = divmod(m, 60)
    key = "duration_hours" if _plural(h, language) else "duration_hour"
    return f"{h} {_t(language, key)} {m}"


def first_word(cmd: str) -> str:
    try:
        parts = shlex.split(cmd)
    except ValueError:
        parts = cmd.split()
    while parts and ("=" in parts[0] and not parts[0].startswith("=")):
        parts.pop(0)
    while parts and parts[0] in ("sudo", "doas", "time", "nice", "nohup", "env", "command", "builtin", "exec"):
        parts.pop(0)
        while parts and parts[0].startswith("-"):
            parts.pop(0)
    return os.path.basename(parts[0]) if parts else ""


_THINK_TAGS = ("<think>", "</think>")


def _visible_prefix_end(s: str) -> int:
    """Jusqu'où `s` peut partir sans risquer de couper une balise <think>/</think> qui
    continuerait dans le prochain morceau du flux (au plus 7 caractères de retard)."""
    max_tail = max(len(t) for t in _THINK_TAGS) - 1
    for k in range(min(len(s), max_tail), 0, -1):
        if any(t.startswith(s[-k:]) for t in _THINK_TAGS):
            return len(s) - k
    return len(s)


def _stream_clean(pieces: Iterator[str]) -> Iterator[str]:
    """Jeton par jeton : un <think>...</think> explicite est retenu pendant sa durée, le
    reste part immédiatement. Un `</think>` isolé (sans ouvrant, Granite 4.2) est juste
    retiré du texte : ce qui précède est déjà parti, il ne peut pas être rappelé."""
    in_think = False
    pending = ""
    for p in pieces:
        pending += p
        out = ""
        while True:
            if in_think:
                end = pending.find("</think>")
                if end == -1:
                    break
                pending = pending[end + len("</think>"):]
                in_think = False
                continue
            start, close = pending.find("<think>"), pending.find("</think>")
            if start != -1 and (close == -1 or start <= close):
                out += pending[:start]
                pending = pending[start + len("<think>"):]
                in_think = True
                continue
            if close != -1:
                out += pending[:close]
                pending = pending[close + len("</think>"):]
                continue
            cut = _visible_prefix_end(pending)
            out += pending[:cut]
            pending = pending[cut:]
            break
        if out:
            yield out.replace("**", "").replace("`", "")
    if pending and not in_think:
        yield pending.replace("**", "").replace("`", "")


def _buffered_clean(pieces: Iterator[str]) -> Iterator[str]:
    """Retient tout depuis le début tant qu'aucune balise n'a tranché : seule façon de
    jeter la totalité d'un raisonnement jamais ouvert (Granite 4.2). Coûte le premier
    mot : réservé via `buffer_reasoning` aux modèles connus pour ce défaut."""
    state = "start"  # start -> in_think | pass ; in_think -> pass
    buf = ""
    for p in pieces:
        buf += p
        if state == "start":
            if "<think>" in buf:
                before, buf = buf.split("<think>", 1)
                if before:
                    yield before.replace("**", "").replace("`", "")
                state = "in_think"
            elif "</think>" in buf:
                buf = buf.split("</think>", 1)[1]
                state = "pass"
            else:
                continue
        if state == "in_think":
            if "</think>" in buf:
                buf = buf.split("</think>", 1)[1]
                state = "pass"
            else:
                continue
        if buf:
            out, buf = buf, ""
            yield out.replace("**", "").replace("`", "")
    if state == "start" and buf:
        yield buf.replace("**", "").replace("`", "")


def _estimate_first_token_seconds(msgs: list[dict], cfg: Config) -> float:
    """Estime le temps que met le modèle à lire le prompt avant son premier jeton."""
    chars = sum(len(m.get("content", "")) for m in msgs)
    tokens = chars / CHARS_PER_TOKEN
    return tokens / max(cfg.llm_prompt_tokens_per_sec, 1e-6)


def _estimate_prefix_seconds(prefix: str, cfg: Config) -> float:
    """Estime la durée audio d'un préfixe déterministe, à la vitesse de parole configurée."""
    words = len(prefix.split())
    return words / max(BASE_SPEECH_WORDS_PER_SEC * cfg.speech_rate, 1e-6)


def _line_count_fact(n: int, language: str = "fr") -> str:
    return _t(language, "narrator.line_count_one" if n == 1 else "narrator.line_count_many").format(n=n)


def _drop_leading_status(pieces: Iterator[str]) -> Iterator[str]:
    """Retire « Succès. »/« Échec. » en tête du flux LLM : un préfixe déterministe l'a
    déjà dit, mais le corpus fait commencer les résumés ainsi. Bufferise le tout début
    du flux (au moins un mot) pour trancher une seule fois, sans retenir la suite."""
    buf = ""
    checked = False
    for p in pieces:
        if checked:
            yield p
            continue
        buf += p
        if len(buf) < 12 and not buf.endswith((" ", "\n")):
            continue
        checked = True
        m = _STATUS_ECHO.match(buf)
        rest = buf[m.end():] if m else buf
        if rest:
            yield rest
    if not checked and buf:
        m = _STATUS_ECHO.match(buf)
        rest = buf[m.end():] if m else buf
        if rest:
            yield rest


_STATUS_WORDS = ("Succès", "Échec", "Success", "Failed")


def _drop_lone_status(pieces: Iterator[str]) -> Iterator[str]:
    """Retient « Succès. »/« Échec. » en tête du flux tant que rien ne le suit : seul
    rescapé de l'ancrage, il ne dit rien et le repli doit partir à sa place."""
    buf = ""
    holding = True
    for p in pieces:
        if not holding:
            yield p
            continue
        buf += p
        text = buf.strip()
        core = text.rstrip(".,:")
        if any(w.startswith(core) for w in _STATUS_WORDS) and (text == core or core in _STATUS_WORDS):
            continue
        holding = False
        yield buf
    if holding and buf.strip().rstrip(".,:") not in _STATUS_WORDS + ("",):
        yield buf


def clean_llm_text(pieces: Iterator[str], buffer_reasoning: bool = False) -> Iterator[str]:
    """Filtre le markdown / les balises de raisonnement qu'un petit modèle laisse parfois passer.

    Par défaut : flux jeton par jeton, le premier mot est la métrique n°1 de steph.
    `buffer_reasoning=True` (voir Config) : pour les modèles qui ferment un raisonnement
    jamais ouvert, au prix du premier mot.
    """
    if buffer_reasoning:
        yield from _buffered_clean(pieces)
    else:
        yield from _stream_clean(pieces)


class Narrator:
    def __init__(self, cfg: Config, session: Session, speaker: Speaker, llm: LLM):
        self.cfg = cfg
        self.s = session
        self.sp = speaker
        self.llm = llm
        self.events: queue.Queue = queue.Queue()
        self.llm_ready = False
        self._thread = threading.Thread(target=self._run, daemon=True, name="narrator")
        self._warm_pending = False
        self._warming = False
        self._qa_cached: list[dict] | None = None  # préfixe des questions déjà lu sur le slot 1
        self._recovering = False
        self._recovered = threading.Event()  # clair : aucun rechargement en cours
        self._recovered.set()
        self._last_health = 0.0
        self.tty_probe = None  # TtyProbe, posé par le proxy
        self._cursor: tuple[int, int] | None = None  # (id de commande, ligne) pour la relecture
        self.rules: dict[str, str] = {}
        rules = cfg.rules or {}
        if not isinstance(rules, dict):
            self._log("rules ignoré : une table [rules] est attendue")
            rules = {}
        for name, value in rules.items():
            if value in RULES:
                self.rules[name] = value
            else:
                self._log(f"règle ignorée pour « {name} » : valeur « {value} » inconnue ({', '.join(RULES)})")

    def rule(self, cmd: str) -> str | None:
        return self.rules.get(first_word(cmd))

    def start(self) -> None:
        self._thread.start()

    @property
    def speaker(self) -> Speaker:
        """Alias de `sp`, pour le proxy (menu F6 : parole forcée, réglages)."""
        return self.sp

    # ------------------------------------------------ mode questions
    def qa_messages(self) -> list[dict]:
        """Préfixe commun aux questions et au préchauffage du cache (slot 1)."""
        lang = self.cfg.language
        budget = FINETUNED_QA_BUDGET_CHARS if self.cfg.llm_profile == "finetuned" else self.cfg.qa_budget_chars
        ctx = self.s.context(self.cfg.qa_block_chars, budget)
        system = prompts.QA_SYSTEM_EN if lang == "en" else prompts.QA_SYSTEM
        msgs = [{"role": "system", "content": system},
                {"role": "user", "content": _t(lang, "qa_history_header").format(ctx=ctx)},
                {"role": "assistant", "content": _t(lang, "qa_history_ack")}]
        for ex in self.s.qa[-4:]:
            msgs.append({"role": "user", "content": ex["q"]})
            msgs.append({"role": "assistant", "content": ex["a"]})
        return msgs

    def qa_wait_phrase(self, prefix: list[dict], msgs: list[dict]) -> str:
        """P20 : phrase dite tout de suite quand la question devra relire tout l'historique
        (préchauffage pas fini, commande nouvelle, modèle rechargé) et que cette lecture dure
        plus que la phrase elle-même. Historique déjà lu : la réponse arrive en 0,3 s sur l'i5."""
        if prefix == self._qa_cached:
            return ""
        phrase = _t(self.cfg.language, "qa_wait")
        if _estimate_first_token_seconds(msgs, self.cfg) <= _estimate_prefix_seconds(phrase, self.cfg):
            return ""
        return phrase

    def note_qa_cached(self) -> None:
        """Après une réponse : le modèle a lu l'historique, la question suivante ne paie que
        le dernier échange."""
        self._qa_cached = self.qa_messages()

    def warm_system_prompts(self) -> None:
        """Au démarrage : met en cache les prompts système (slot 0 et 1)."""
        try:
            build = (prompts.finetuned_summary_messages if self.cfg.llm_profile == "finetuned"
                     else prompts.summary_messages)
            self.llm.complete(build("true", 0, 0.0, "", 0, language=self.cfg.language), max_tokens=1, slot=0)
            self._warm_pending = True
        except Exception as e:
            self._log(f"préchauffage initial: {e!r}")

    def _maybe_warm(self) -> None:
        """GPU au repos : on pré-calcule le cache de l'historique pour que la
        prochaine question ne paie que son propre coût."""
        if not self._warm_pending or self._warming or not self.llm_ready:
            return
        if self.cfg.qa_tools:  # D4 : les questions ne lisent pas l'historique complet
            return
        if self.s.current is not None or self.sp.speaking.is_set() or not self.sp._q.empty():
            return
        if self.llm.active or time.time() - self.llm.last_done < 0.5:
            return
        self._warm_pending = False
        self._warming = True
        msgs = self.qa_messages() + [{"role": "user", "content": "ok"}]

        def run():
            try:
                t0 = time.time()
                self.llm.complete(msgs, max_tokens=1, timeout=180, slot=1, background=True)
                self._qa_cached = msgs[:-1]
                self._log(f"préchauffage questions : {time.time() - t0:.1f}s")
            except Exception as e:
                self._warm_pending = True  # interrompu : on reprendra plus tard
                self._log(f"préchauffage interrompu: {e!r}")
            finally:
                self._warming = False

        threading.Thread(target=run, daemon=True, name="warm").start()

    # ------------------------------------------------ événements du proxy
    # Appelées depuis le thread du proxy : la création / clôture de l'entrée est
    # synchrone pour que chaque octet de sortie soit rattaché à la bonne commande.
    def on_command_start(self, cmd: str) -> None:
        cmd = cmd.strip()
        # rechargement anticipé (Q2b) : le modèle a toute la durée de la commande pour
        # redémarrer avant que le résumé de fin en ait besoin (voir _llm_say/_wait_for_llm_reload)
        if self.cfg.llm_anticipatory_reload and not self.llm_ready:
            self._recover_llm("frappe anticipée")
        c = self.s.start(cmd)
        fw = first_word(cmd)
        c.silent = (not cmd) or fw in META_COMMANDS or cmd.startswith("q ")
        c.interactive = is_interactive(cmd)
        self.events.put(("start", c))

    def on_enter(self, typed: str = "") -> None:
        """Entrée tapée pendant qu'une commande tourne : réponse à une question,
        commande dans ssh / python… ou simple frappe anticipée."""
        c = self.s.current
        if c is None or c.silent:
            return
        reading = None if c.interactive else self._reading()
        if reading is False:
            # frappe anticipée (commande suivante tapée à l'avance) : le terminal
            # en affiche l'écho, on l'écartera du résumé
            if typed.strip():
                # l'écho arrivera seul, ou collé à la ligne en cours
                c.echo_lines.append(typed.strip())
                c.echo_lines.append((strip_ansi(c.out.partial) + typed).strip())
            return
        now = time.time()
        c.typed = c.out.partial
        c.enter_mark = c.out.total_lines + 1  # la ligne tapée sera validée par l'écho
        c.enter_at = now
        c.awaiting_reply = True
        c.last_prompt_said = ""
        c.last_update_at = now
        if c.interactive:
            return
        if c.out.partial and looks_like_prompt(c.out.partial):
            return  # simple réponse à une question : le suivi normal reprend
        if reading:
            c.enter_count += 1
            if c.enter_count >= 2:  # plusieurs échanges : c'est un programme interactif
                c.interactive = True

    def _reading(self) -> bool | None:
        if self.tty_probe is None:
            return None
        try:
            return self.tty_probe.waiting_for_input()
        except Exception:
            return None

    def on_command_end(self, exit_code: int, cwd: str) -> None:
        c = self.s.current
        if c is not None:
            c.end = time.time()
            c.exit = exit_code
        self.events.put(("end", c, cwd))

    def on_cwd(self, cwd: str) -> None:
        self.events.put(("cwd", cwd))

    def on_key(self, what: str) -> None:
        self.events.put(("key", what))

    # ----------------------------------------------------------- boucle
    def _run(self) -> None:
        while True:
            try:
                ev = self.events.get(timeout=0.25)
            except queue.Empty:
                ev = None
            try:
                if ev:
                    self._handle(ev)
                self._tick()
                self._maybe_warm()
                self._maybe_unload_idle_llm()
            except Exception as e:  # le narrateur ne doit jamais tomber
                self._log(f"erreur narrateur: {e!r}")

    def _log(self, msg: str) -> None:
        try:
            from .config import RUNTIME_DIR
            with open(RUNTIME_DIR / "steph.log", "a") as f:
                f.write(time.strftime("%H:%M:%S ") + msg + "\n")
        except OSError:
            pass

    def _handle(self, ev) -> None:
        kind = ev[0]
        if kind == "start":
            c = ev[1]
            if not c.silent:
                self._cursor = None
                self.sp.stop()  # nouvelle commande : on coupe l'annonce précédente
                if c.interactive and self.rule(c.cmd) not in ("mute", "mute-all"):
                    self.sp.say(_t(self.cfg.language, "interactive_start").format(prog=first_word(c.cmd) or "shell"))
        elif kind == "end":
            _, c, cwd = ev
            old_cwd = self.s.cwd
            self.s.cwd = cwd
            if c is None:
                return
            self._warm_pending = not c.silent
            self._finish(c, old_cwd, cwd)
        elif kind == "cwd":
            self.s.cwd = ev[1]
        elif kind == "key":
            self._key(ev[1])

    def _key(self, what: str) -> None:
        if what == "stop":
            self.sp.stop_all()  # touche « silence » : la voix partagée se tait, toutes fenêtres
        elif what == "repeat":
            self.sp.repeat()
        elif what == "details":
            c = self.s.current or self.s.last
            if not c:
                self.sp.say(_t(self.cfg.language, "no_command_yet"))
                return
            self._details(c)
        elif what in ("first", "prev", "next", "last"):
            self._review(what)

    def _review(self, what: str) -> None:
        """Relecture ligne à ligne de la dernière commande terminée, comme un lecteur d'écran."""
        with self.s.lock:
            c = next((c for c in reversed(self.s.commands) if not c.running and not c.silent), None)
        if c is None:
            self.sp.say(_t(self.cfg.language, "no_command_yet"))
            return
        lines = [strip_ansi(l).strip() for l in c.all_lines()]
        lines = [l for l in lines if l and l not in ("^C", "^Z", "^\\")]
        if not lines:
            self.sp.say(_t(self.cfg.language, "no_output"))
            return
        i = self._cursor[1] if self._cursor and self._cursor[0] == c.id else None
        j = {"first": 0, "last": len(lines) - 1,
             "next": 0 if i is None else i + 1,
             "prev": len(lines) - 1 if i is None else i - 1}[what]
        if j < 0:
            self.sp.say(_t(self.cfg.language, "review_start"))
        elif j >= len(lines):
            self.sp.say(_t(self.cfg.language, "review_end"))
        else:
            self._cursor = (c.id, j)
            self.sp.say(lines[j])

    # ------------------------------------------------------ fin de commande
    def _finish(self, c: Command, old_cwd: str, cwd: str) -> None:
        if c.silent:
            return
        lang = self.cfg.language
        lines = [l for l in c.all_lines() if l.strip() and l.strip() not in ("^C", "^Z", "^\\")]
        # les questions déjà lues (et la réponse tapée derrière) ne sont pas relues
        if c.prompts_said or c.echo_lines:
            lines = [l for l in lines
                     if strip_ansi(l).strip() not in c.echo_lines
                     and not any(p and strip_ansi(l).strip().startswith(p) for p in c.prompts_said)]
        text = "\n".join(lines).strip()
        code = c.exit
        fw = first_word(c.cmd)
        rule = self.rule(c.cmd)
        # mute : Ctrl+C (130) n'est pas une erreur, c'est ainsi qu'on quitte watch ou top
        if rule == "mute-all" or (rule == "mute" and code in (0, 130, None)):
            return
        # durée « active » : sans le temps passé à attendre l'utilisateur
        active = (c.end or time.time()) - max(c.start, c.enter_at)
        long_cmd = active >= self.cfg.first_update_after
        # commande longue : le statut part en tête (comme les commandes courtes, P9), la
        # durée part en suffixe à la fin de la phrase - jamais l'inverse, pour ne pas
        # laisser l'utilisateur sans nouvelle avant que la durée soit dite en entier
        prefix = ""
        duration_suffix = ""
        if long_cmd:
            if code == 0:
                prefix = _t(lang, "narrator.status_success")
                duration_suffix = " " + _t(lang, "narrator.duration_success").format(dur=fmt_duration(active, lang))
            elif code == 130:
                prefix = _t(lang, "narrator.status_interrupted")
                duration_suffix = " " + _t(lang, "narrator.duration_after").format(dur=fmt_duration(c.duration, lang))
            else:
                prefix = _t(lang, "narrator.status_failed").format(code=code)
                duration_suffix = " " + _t(lang, "narrator.duration_after").format(dur=fmt_duration(c.duration, lang))

        def done(t: str) -> None:
            c.summary = t

        if self.cfg.verbosity == 0 and code == 0:
            return
        # session interactive (ssh, python…) : chaque réponse a déjà été lue
        if c.interactive:
            end = (_t(lang, "interactive_end_ok").format(fw=fw) if code in (0, 130)
                   else _t(lang, "interactive_end_code").format(fw=fw, code=code))
            self.sp.say(end, interrupt=False, on_done=done)
            return
        # plein écran (vim, less, htop…) : rien à résumer
        if c.used_fullscreen:
            if code not in (0, 130):
                self.sp.say(_t(lang, "fullscreen_end_code").format(fw=fw, code=code), on_done=done)
            return
        # changement de dossier
        if not text and cwd != old_cwd and code == 0:
            if self.cfg.announce_cd:
                name = os.path.basename(cwd.rstrip("/")) or _t(lang, "root_folder")
                if cwd == os.path.expanduser("~"):
                    name = _t(lang, "home_folder")
                self.sp.say(_t(lang, "cd_folder").format(name=name), on_done=done)
            return
        if code == 127 and (re.search(r"not found|introuvable|non trouvée", text) or not text):
            self.sp.say(not_found_sentence(fw, text, lang), on_done=done)
            return
        if not text:
            if no_match := grep_no_match(c.cmd, code, lang):
                self.sp.say(no_match + duration_suffix, on_done=done)
            elif code == 0:
                if long_cmd:
                    self.sp.say(_t(lang, "narrator.no_output_success_long").format(dur=fmt_duration(active, lang)),
                                on_done=done)
                elif fw not in SILENT_OK:
                    self.sp.say(_t(lang, "ok"), on_done=done)
            elif code == 130:
                if long_cmd:
                    self.sp.say(_t(lang, "narrator.no_output_interrupted_long").format(dur=fmt_duration(c.duration, lang)),
                                on_done=done)
                else:
                    self.sp.say(_t(lang, "interrupted"), on_done=done)
            else:
                if long_cmd:
                    self.sp.say(_t(lang, "narrator.no_output_failed_long").format(code=code, dur=fmt_duration(c.duration, lang)),
                                on_done=done)
                else:
                    self.sp.say(_t(lang, "failed_no_message").format(code=code), on_done=done)
            return
        words = len(text.split())
        if rule == "verbatim" or (rule != "summary" and words <= self.cfg.read_verbatim_max_words and len(lines) <= 3):
            say = strip_symbol_runs(strip_ansi(text)).replace("\n", ". ")
            if code not in (0, None):
                say = _t(lang, "error_code").format(code=code, say=say)
            self.sp.say(prefix + say + duration_suffix, on_done=done)
            return
        said = resolve(c.cmd, code, "\n".join(c.all_lines()), lang)
        if said:
            failed_word = _t(lang, "resolve.failed").rstrip(".")
            if prefix and said.startswith(failed_word):
                said = said.split(" ", 1)[1]
            self.sp.say(prefix + said + duration_suffix, on_done=done)
            return
        # sortie longue : résumé par le LLM, lu au fil de la génération
        # profil affiné (B3) : prompt court réellement appris (TRAIN_SYSTEM) au lieu de
        # SUMMARY_SYSTEM, entrée plafonnée au palier P11 (Granite ~200 jetons) au lieu de
        # cfg.summary_chars (calibré pour SUMMARY_SYSTEM, jamais appris par un modèle affiné)
        finetuned = self.cfg.llm_profile == "finetuned"
        in_chars = FINETUNED_SUMMARY_CHARS if finetuned else self.cfg.summary_chars
        build = prompts.finetuned_summary_messages if finetuned else prompts.summary_messages
        out = digest(c.cmd, "\n".join(c.all_lines()), in_chars, lang) or c.compact(in_chars)
        facts = extract_facts(c.cmd, code, "\n".join(c.all_lines()), lang) if self.cfg.facts_block else None
        msgs = build(c.cmd, code, c.duration, out, c.out.total_lines, c.cwd, language=lang, facts=facts)
        # commande courte : pas de préfixe de durée -> on dit le statut tout de suite,
        # pour ne pas rester muet jusqu'au premier jeton (le prompt est long à lire)
        llm_prefix = prefix
        if not long_cmd and code is not None:
            llm_prefix = (_t(lang, "narrator.status_success") if code == 0
                          else _t(lang, "narrator.status_failed").format(code=code))
        # le préfixe seul ne couvre pas le temps de lecture du prompt : un fait sûr
        # (jamais inventé, calculé en code) comble le silence restant
        if _estimate_first_token_seconds(msgs, self.cfg) > _estimate_prefix_seconds(llm_prefix, self.cfg):
            llm_prefix += _line_count_fact(c.out.total_lines, lang) + " "
        self._llm_say(msgs, self._fallback_summary(c, lines), prefix=llm_prefix, suffix=duration_suffix,
                      on_done=done, tag=f"résumé #{c.id}", strip_status=True)

    def _fallback_summary(self, c: Command, lines: list[str]) -> str:
        lang = self.cfg.language
        imp = important_lines(lines, 2)
        last = strip_ansi(imp[-1] if (imp and c.exit) else lines[-1]).strip()[:160]
        status = "OK" if c.exit == 0 else _t(lang, "fallback_code").format(code=c.exit)
        return _t(lang, "fallback_summary").format(status=status, n=len(lines), last=last)

    def _details(self, c: Command) -> None:
        lang = self.cfg.language
        # profil affiné (B3b/B3c) : prompt court appris (TRAIN_DETAILS_SYSTEM ou
        # TRAIN_DETAILS_SYSTEM_EN) et entrée plafonnée au palier du corpus détail
        # (FINETUNED_DETAIL_CHARS), français ou anglais (K3/H3a, commit cdb0802).
        if self.cfg.llm_profile == "finetuned" and lang in ("fr", "en"):
            out = digest(c.cmd, "\n".join(c.all_lines()), FINETUNED_DETAIL_CHARS, lang) or c.compact(FINETUNED_DETAIL_CHARS)
            msgs = prompts.finetuned_details_messages(c.cmd, c.exit, c.duration, out, c.out.total_lines, language=lang)
        else:
            msgs = prompts.details_messages(c.cmd, c.exit, c.duration, c.compact(6000), c.out.total_lines, language=lang)
        self._llm_say(msgs, self._fallback_summary(c, c.all_lines()) if c.all_lines() else _t(lang, "no_output"),
                      max_tokens=250, tag="détails")

    def _llm_ok(self) -> bool:
        if not self.llm_ready and time.time() - self._last_health > 5:
            self._last_health = time.time()
            self.llm_ready = self.llm.healthy()
            if not self.llm_ready:
                self._recover_llm()
        return self.llm_ready

    def _recover_llm(self, reason: str = "sonde de santé") -> None:
        if self._recovering:
            return
        self._recovering = True
        self._recovered.clear()

        self._qa_cached = None

        def run():
            try:
                self._log(f"relance du serveur LLM ({reason})")
                self.llm_ready = self.llm.ensure_server(90)
                if self.llm_ready:
                    self.warm_system_prompts()
            finally:
                self._recovering = False
                self._recovered.set()

        threading.Thread(target=run, daemon=True, name="llm-recover").start()

    def _wait_for_llm_reload(self, tag: str = "") -> bool:
        """Attend qu'un rechargement déjà en cours (anticipé à la frappe, ou déclenché
        par `_llm_ok` ci-dessus) aboutisse, borné par `llm_reload_grace_seconds` : au-delà,
        on abandonne et le repli déterministe part (voir `_llm_say`)."""
        if not self._recovering:
            return self.llm_ready
        self._recovered.wait(self.cfg.llm_reload_grace_seconds)
        if not self.llm_ready and tag:
            self._log(f"{tag}: modèle non prêt après {self.cfg.llm_reload_grace_seconds:g}s, repli")
        return self.llm_ready

    # ------------------------------------------------ déchargement au repos (Q2b)
    def _maybe_unload_idle_llm(self) -> None:
        """Libère la RAM de llama-server après une pause : aucune requête LLM (résumé,
        question, détail, préchauffage) nulle part depuis `llm_idle_unload_minutes`.
        Jamais pendant une génération, dans cette fenêtre (`active`, `_warming`) ou une
        autre (`LLM.try_unload_idle`, via le marqueur partagé `busy_dir`)."""
        minutes = self.cfg.llm_idle_unload_minutes
        if minutes <= 0 or not self.llm_ready:
            return
        if self.llm.active or self._warming:
            return
        if self.llm.idle_seconds() < minutes * 60:
            return
        if self.llm.try_unload_idle(minutes):
            self._log(f"llama-server déchargé après {minutes:g} min d'inactivité")
            self.llm_ready = False
            self._qa_cached = None
        elif not self.llm.healthy():
            self.llm_ready = False  # déchargé par une autre fenêtre entre-temps
            self._qa_cached = None

    def _llm_say(self, msgs: list[dict], fallback: str, prefix: str = "", max_tokens: int = 90,
                 on_done=None, interrupt: bool = True, tag: str = "", strip_status: bool = False,
                 suffix: str = "") -> None:
        """Lit la réponse du LLM au fil de l'eau ; en cas d'échec, lit `fallback`.

        `strip_status=True` : retire un « Succès. »/« Échec. » en tête du flux du modèle,
        déjà dit par `prefix` (le corpus fait commencer les résumés ainsi).
        `suffix` : dit après le flux (commande longue : la durée) - après `fallback` si
        l'ancrage a vidé toute la réponse, jamais avant : la durée ne doit pas retarder
        le premier mot.

        Modèle pas encore prêt : si un rechargement est déjà en cours (anticipé à la
        frappe, ou déclenché ici même), le préfixe part quand même tout de suite (P9) et
        l'attente du rechargement se fait dans `gen()`, sans bloquer la boucle du
        narrateur - repli déterministe seulement si `llm_reload_grace_seconds` expire.
        Aucun rechargement en cours : repli immédiat, comme avant Q2b."""
        ready = self._llm_ok()
        if not ready and not self._recovering:
            if prefix or fallback or suffix:
                self.sp.say(prefix + fallback + suffix, interrupt=interrupt, on_done=on_done)
            return

        def gen() -> Iterator[str]:
            if prefix:
                yield prefix
            if not ready and not self._wait_for_llm_reload(tag):
                if fallback:
                    yield fallback
                if suffix:
                    yield suffix
                return
            t0 = time.time()
            got = False
            try:
                stream = clean_llm_text(self.llm.stream(msgs, max_tokens=max_tokens),
                                         buffer_reasoning=self.cfg.buffer_reasoning)
                if self.cfg.ground_output:
                    # garde-fou d'ancrage : coupe toute proposition dont un nombre, un nom,
                    # un chemin ou une version est absent de l'entrée (voir grounding.py)
                    input_text = "\n".join(m["content"] for m in msgs if m["role"] == "user")
                    stream = ground_stream(stream, input_text, language=self.cfg.language)
                    if not strip_status:
                        stream = _drop_lone_status(stream)
                if strip_status:
                    stream = _drop_leading_status(stream)
                for piece in stream:
                    if not got and tag:
                        self._log(f"{tag}: 1er token en {time.time() - t0:.2f}s")
                    got = True
                    yield piece
                # the grounding guard can drop every clause: say the code-built fallback, not silence
                if not got and fallback:
                    yield fallback
            except Exception as e:
                self._log(f"LLM {tag}: {e!r}")
                if isinstance(getattr(e, "reason", None), ConnectionRefusedError) or isinstance(e, ConnectionError):
                    self.llm_ready = False
                    self._recover_llm("connexion perdue")
                if not got and fallback:
                    yield fallback
            if suffix:
                yield suffix

        self.sp.say_stream(gen(), interrupt=interrupt, on_done=on_done)

    # ------------------------------------------------ commande en cours
    def _tick(self) -> None:
        c = self.s.current
        if c is not None and self.rule(c.cmd) in ("mute", "mute-all"):
            return
        if c is None or c.silent or c.used_fullscreen:
            if c is not None and c.used_fullscreen and not c.announced_start:
                c.announced_start = True
                if self.cfg.verbosity >= 1:
                    self.sp.say(_t(self.cfg.language, "fullscreen_start").format(prog=first_word(c.cmd)))
            return
        now = time.time()
        # 0) mode interactif : lire ce qui a suivi la dernière Entrée
        if c.interactive:
            if c.awaiting_reply and now - c.last_output_at >= 0.6 and now - c.enter_at >= 0.4:
                c.awaiting_reply = False
                self._speak_reply(c)
            if not c.awaiting_reply:
                self._prompt_check(c, now)
            return
        # 1) la commande attend une réponse ?
        if self._prompt_check(c, now):
            return
        if c.last_prompt_said and c.out.partial == c.last_prompt_said:
            return  # question en attente : on ne parle pas par-dessus
        if now - max(c.start, c.enter_at) < self.cfg.first_update_after:
            return
        # 2) première annonce : ce que fait la commande
        if not c.announced_start:
            lang = self.cfg.language
            in_progress = _t(lang, "in_progress")
            c.announced_start = True
            c.last_update_at = now
            c.lines_at_last_update = c.out.total_lines
            what = self._describe_start(c.cmd)
            prog = self._progress_text(c)
            msg = f"{in_progress}{what}." + (f" {prog}." if prog else "")
            if what is None:
                # description par le LLM, puis progression déterministe
                if self._llm_ok():
                    # profil affiné (B3b/B3c) : prompt court appris (TRAIN_START_SYSTEM ou
                    # TRAIN_START_SYSTEM_EN), français ou anglais (K3/H3a, commit cdb0802).
                    msgs = (prompts.finetuned_start_messages(c.cmd, language=lang)
                            if self.cfg.llm_profile == "finetuned" and lang in ("fr", "en")
                            else prompts.start_messages(c.cmd, language=lang))
                    def gen():
                        yield in_progress
                        try:
                            yield self.llm.complete(msgs, max_tokens=30).replace("`", "").rstrip(" .") or first_word(c.cmd)
                        except Exception:
                            yield first_word(c.cmd)
                        yield ". "
                        if prog:
                            yield prog + "."
                    self.sp.say_stream(gen(), interrupt=False)
                    return
                msg = _t(lang, "running").format(prog=first_word(c.cmd)) + (f" {prog}." if prog else "")
            self.sp.say(msg, interrupt=False)
            return
        # 3) points d'étape périodiques
        if now - c.last_update_at < self.cfg.update_interval or self.sp.speaking.is_set():
            return
        c.last_update_at = now
        new_lines = c.out.total_lines - c.lines_at_last_update
        c.lines_at_last_update = c.out.total_lines
        silent_for = now - c.last_output_at
        if silent_for > self.cfg.update_interval and new_lines == 0:
            if silent_for > 3 * self.cfg.update_interval and int(silent_for) // 60 != int(silent_for - self.cfg.update_interval) // 60:
                self.sp.say(_t(self.cfg.language, "still_running").format(dur=fmt_duration(silent_for, self.cfg.language)),
                            interrupt=False)
            return
        prog = self._progress_text(c)
        if prog and prog != c.last_spoken_update:
            c.last_spoken_update = prog
            c.updates.append(prog)
            self.sp.say(prog + ".", interrupt=False)
            return
        if new_lines > 0 and self._llm_ok() and self.cfg.verbosity >= 1:
            recent = "\n".join(l for l in c.out.tail(15) if l.strip())
            # profil affiné (B3b/B3c) : prompt court appris (TRAIN_PROGRESS_SYSTEM ou
            # TRAIN_PROGRESS_SYSTEM_EN), entrée non plafonnée à 2500 caractères (le corpus
            # d'entraînement ne coupe qu'aux 15 dernières lignes, jamais aux caractères) -
            # français ou anglais (K3/H3a, commit cdb0802).
            if self.cfg.llm_profile == "finetuned" and self.cfg.language in ("fr", "en"):
                msgs = prompts.finetuned_progress_messages(c.cmd, c.duration, recent, language=self.cfg.language)
            else:
                msgs = prompts.progress_messages(c.cmd, c.duration, recent[-2500:], language=self.cfg.language)
            self._llm_say(msgs, "", max_tokens=30, interrupt=False,
                          on_done=lambda t: c.updates.append(t), tag="étape")

    def _prompt_check(self, c: Command, now: float) -> bool:
        partial = c.out.partial
        if not (partial and now - c.last_output_at >= self.cfg.prompt_idle and partial != c.last_prompt_said):
            return False
        if not looks_like_prompt(partial):
            # pas de forme de question, mais le programme attend peut-être quand
            # même : on sonde une seule fois par ligne (ps coûte cher sur macOS)
            if c.interactive or c.probed_partial == partial:
                return False
            reading = self._reading()
            if reading is None:
                # sonde muette (macOS, lecture en mode ligne) : ligne restée ouverte
                # et silence prolongé = probablement une question
                if now - c.last_output_at < 2.5 or re.search(r"\d\s*%|\.\.\.\s*$|[|/\\-]\s*$", partial):
                    return False
            c.probed_partial = partial
            if reading is False:
                return False
        c.last_prompt_said = partial
        c.prompts_said.append(strip_ansi(partial).strip())
        if c.interactive:
            # invite du programme interactif (>>> , $ …) : implicite, on ne la lit pas
            if not re.search(r"mot de passe|password|passphrase|\[[OoYy]/[Nn]\]|\?\s*$", partial, re.I):
                return False
        p = strip_ansi(partial).strip()
        pw = self.tty_probe is not None and self.tty_probe.password_mode()
        if pw or re.search(r"mot de passe|password|passphrase", p, re.I):
            self.sp.say(_t(self.cfg.language, "password_prompt"))
        else:
            prev = [l.strip() for l in c.out.lines[-3:] if l.strip()]
            ctx = (prev[-1][:150].rstrip(".") + ". ") if prev and not c.interactive else ""
            self.sp.say(_t(self.cfg.language, "question_prefix") + ctx + p)
        c.last_update_at = now
        return True

    def _speak_reply(self, c: Command) -> None:
        lang = self.cfg.language
        new = [l for l in c.lines_since(c.enter_mark) if l.strip()]
        partial = c.out.partial.strip()
        # la dernière ligne partielle est en général la nouvelle invite (>>> , user@hôte:~$)
        if partial and not looks_like_prompt(partial) and not re.search(r"[$#%>]\s*$", partial):
            new.append(partial)
        if not new:
            return
        text = "\n".join(new)
        typed = re.sub(r"^.*?[$#%>]\s+", "", strip_ansi(c.typed)).strip() or c.typed.strip()
        if len(text.split()) <= self.cfg.read_verbatim_max_words and len(new) <= 3:
            self.sp.say(strip_ansi(text).replace("\n", ". "))
            return
        from .textproc import compact_output
        in_program = _t(lang, "in_program").format(prog=first_word(c.cmd))
        msgs = prompts.summary_messages(f"{typed}{in_program}", None, time.time() - c.enter_at,
                                        compact_output(new, self.cfg.summary_chars), len(new), language=lang)
        msgs[1]["content"] = msgs[1]["content"].replace(_t(lang, "status_unknown_line"), "")
        fallback = _t(lang, "lines_last").format(n=len(new), last=strip_ansi(new[-1])[:150])
        self._llm_say(msgs, fallback, tag="réponse")

    def _describe_start(self, cmd: str) -> str | None:
        for rx, tpl in KNOWN_START:
            m = rx.search(cmd)
            if m:
                gd = {k: v.strip() for k, v in m.groupdict().items() if v}
                if "x" in gd:
                    gd["x"] = " ".join(w for w in gd["x"].split() if not w.startswith("-"))[:80]
                try:
                    return tpl.format(**gd)
                except KeyError:
                    return None
        return None

    def _progress_text(self, c: Command) -> str:
        pct = detect_percent(c.out.status, c.out.partial, *(reversed(c.out.lines[-2:])))
        stage = None
        for line in [c.out.partial] + list(reversed(c.out.lines[-8:])):
            stage = detect_stage(line)
            if stage:
                break
        parts = []
        if pct is not None:
            parts.append(f"{int(pct)} pour cent")
        if stage:
            parts.append(stage)
        return ", ".join(parts)
