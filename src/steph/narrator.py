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
from .llm import LLM
from .session import Command, Session
from .textproc import detect_percent, detect_stage, important_lines, looks_like_prompt, strip_ansi
from .tts import Speaker

META_COMMANDS = ("q", "steph", "clear", "reset", "exit", "logout")
SILENT_OK = {"cd", "pushd", "popd", "export", "unset", "alias", "unalias", "source", ".", "set",
             "clear", "reset", "true", "history", "fg", "bg", "jobs", "wait"}

INTERACTIVE = {"ssh", "mosh", "telnet", "ipython", "irb", "psql", "mysql", "mariadb", "sqlite3",
               "redis-cli", "mongo", "mongosh", "ftp", "sftp", "bc", "gdb", "pdb", "su", "bash", "zsh",
               "sh", "fish", "nc", "ncat", "lftp", "virsh", "iex", "ghci", "lua", "R", "guile"}
REPL_IF_NO_ARGS = {"python", "python3", "node", "deno", "bun", "php", "perl", "ruby", "julia", "sage"}


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


def fmt_duration(sec: float) -> str:
    sec = int(round(sec))
    if sec < 60:
        return f"{sec} seconde{'s' if sec > 1 else ''}"
    m, s = divmod(sec, 60)
    if m < 60:
        return f"{m} minute{'s' if m > 1 else ''}" + (f" {s}" if s else "")
    h, m = divmod(m, 60)
    return f"{h} heure{'s' if h > 1 else ''} {m}"


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


def clean_llm_text(pieces: Iterator[str]) -> Iterator[str]:
    """Filtre le markdown / les balises de raisonnement qu'un petit modèle laisse parfois passer."""
    in_think = False
    buf = ""
    for p in pieces:
        buf += p
        if "<think>" in buf:
            in_think = True
            buf = buf.split("<think>", 1)[0]
        if in_think:
            if "</think>" in p:
                in_think = False
                buf = p.split("</think>", 1)[1]
            continue
        out, buf = buf, ""
        out = out.replace("**", "").replace("`", "")
        yield out


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
        self._recovering = False
        self._last_health = 0.0
        self.tty_probe = None  # TtyProbe, posé par le proxy

    def start(self) -> None:
        self._thread.start()

    # ------------------------------------------------ mode questions
    def qa_messages(self) -> list[dict]:
        """Préfixe commun aux questions et au préchauffage du cache (slot 1)."""
        ctx = self.s.context(self.cfg.qa_block_chars, self.cfg.qa_budget_chars)
        msgs = [{"role": "system", "content": prompts.QA_SYSTEM},
                {"role": "user", "content": f"Historique de la session :\n{ctx}"},
                {"role": "assistant", "content": "Compris, j'ai l'historique."}]
        for ex in self.s.qa[-4:]:
            msgs.append({"role": "user", "content": ex["q"]})
            msgs.append({"role": "assistant", "content": ex["a"]})
        return msgs

    def warm_system_prompts(self) -> None:
        """Au démarrage : met en cache les prompts système (slot 0 et 1)."""
        try:
            self.llm.complete(prompts.summary_messages("true", 0, 0.0, "", 0), max_tokens=1, slot=0)
            self._warm_pending = True
        except Exception as e:
            self._log(f"préchauffage initial: {e!r}")

    def _maybe_warm(self) -> None:
        """GPU au repos : on pré-calcule le cache de l'historique pour que la
        prochaine question ne paie que son propre coût."""
        if not self._warm_pending or self._warming or not self.llm_ready:
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
                c.prompts_said.append(typed.strip())
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
                self.sp.stop()  # nouvelle commande : on coupe l'annonce précédente
                if c.interactive:
                    self.sp.say(f"{first_word(c.cmd) or 'shell'} interactif.")
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
            self.sp.stop()
        elif what == "repeat":
            self.sp.repeat()
        elif what == "details":
            c = self.s.current or self.s.last
            if not c:
                self.sp.say("Aucune commande pour l'instant.")
                return
            self._details(c)

    # ------------------------------------------------------ fin de commande
    def _finish(self, c: Command, old_cwd: str, cwd: str) -> None:
        if c.silent:
            return
        lines = [l for l in c.all_lines() if l.strip() and l.strip() not in ("^C", "^Z", "^\\")]
        # les questions déjà lues (et la réponse tapée derrière) ne sont pas relues
        if c.prompts_said:
            lines = [l for l in lines if not any(p and (strip_ansi(l).strip().startswith(p) or strip_ansi(l).strip().endswith(p))
                                                 for p in c.prompts_said)]
        text = "\n".join(lines).strip()
        code = c.exit
        fw = first_word(c.cmd)
        # durée « active » : sans le temps passé à attendre l'utilisateur
        active = (c.end or time.time()) - max(c.start, c.enter_at)
        long_cmd = active >= self.cfg.first_update_after
        prefix = ""
        if long_cmd:
            if code == 0:
                prefix = f"Terminé en {fmt_duration(active)}. "
            elif code == 130:
                prefix = f"Interrompu après {fmt_duration(c.duration)}. "
            else:
                prefix = f"Échec après {fmt_duration(c.duration)}. "

        def done(t: str) -> None:
            c.summary = t

        if self.cfg.verbosity == 0 and code == 0:
            return
        # session interactive (ssh, python…) : chaque réponse a déjà été lue
        if c.interactive:
            end = f"Fin de {fw}." if code in (0, 130) else f"Fin de {fw}, code {code}."
            self.sp.say(end, interrupt=False, on_done=done)
            return
        # plein écran (vim, less, htop…) : rien à résumer
        if c.used_fullscreen:
            if code not in (0, 130):
                self.sp.say(f"{fw} s'est terminé avec le code {code}.", on_done=done)
            return
        # changement de dossier
        if not text and cwd != old_cwd and code == 0:
            if self.cfg.announce_cd:
                name = os.path.basename(cwd.rstrip("/")) or "racine"
                if cwd == os.path.expanduser("~"):
                    name = "dossier personnel"
                self.sp.say(f"Dossier {name}.", on_done=done)
            return
        if code == 127 and (re.search(r"not found|introuvable|non trouvée", text) or not text):
            self.sp.say(f"Commande introuvable : {fw}.", on_done=done)
            return
        if not text:
            if code == 0:
                if fw not in SILENT_OK or long_cmd:
                    self.sp.say(prefix + ("" if prefix else "OK."), on_done=done)
            elif code == 130:
                self.sp.say(prefix or "Interrompu.", on_done=done)
            else:
                self.sp.say(prefix + f"Échec, code {code}, aucun message.", on_done=done)
            return
        words = len(text.split())
        if words <= self.cfg.read_verbatim_max_words and len(lines) <= 3:
            say = strip_ansi(text).replace("\n", ". ")
            if code not in (0, None):
                say = f"Erreur {code} : {say}"
            self.sp.say(prefix + say, on_done=done)
            return
        # sortie longue : résumé par le LLM, lu au fil de la génération
        msgs = prompts.summary_messages(c.cmd, code, c.duration, c.compact(self.cfg.summary_chars), c.out.total_lines, c.cwd)
        self._llm_say(msgs, self._fallback_summary(c, lines), prefix=prefix, on_done=done, tag=f"résumé #{c.id}")

    def _fallback_summary(self, c: Command, lines: list[str]) -> str:
        imp = important_lines(lines, 2)
        last = strip_ansi(imp[-1] if (imp and c.exit) else lines[-1]).strip()[:160]
        st = "OK" if c.exit == 0 else f"code {c.exit}"
        return f"{st}, {len(lines)} lignes. Dernière ligne : {last}"

    def _details(self, c: Command) -> None:
        msgs = prompts.summary_messages(c.cmd, c.exit, c.duration, c.compact(6000), c.out.total_lines)
        msgs[0]["content"] = msgs[0]["content"].replace(
            "UNE phrase courte en français (20 mots maximum)", "3 à 5 phrases en français")
        self._llm_say(msgs, self._fallback_summary(c, c.all_lines()) if c.all_lines() else "Aucune sortie.",
                      max_tokens=250, tag="détails")

    def _llm_ok(self) -> bool:
        if not self.llm_ready and time.time() - self._last_health > 5:
            self._last_health = time.time()
            self.llm_ready = self.llm.healthy()
            if not self.llm_ready:
                self._recover_llm()
        return self.llm_ready

    def _recover_llm(self) -> None:
        if self._recovering:
            return
        self._recovering = True

        def run():
            try:
                self._log("relance du serveur LLM")
                self.llm_ready = self.llm.ensure_server(90)
                if self.llm_ready:
                    self.warm_system_prompts()
            finally:
                self._recovering = False

        threading.Thread(target=run, daemon=True, name="llm-recover").start()

    def _llm_say(self, msgs: list[dict], fallback: str, prefix: str = "", max_tokens: int = 90,
                 on_done=None, interrupt: bool = True, tag: str = "") -> None:
        """Lit la réponse du LLM au fil de l'eau ; en cas d'échec, lit `fallback`."""
        if not self._llm_ok():
            if prefix or fallback:
                self.sp.say(prefix + fallback, interrupt=interrupt, on_done=on_done)
            return

        def gen() -> Iterator[str]:
            if prefix:
                yield prefix
            t0 = time.time()
            got = False
            try:
                for piece in clean_llm_text(self.llm.stream(msgs, max_tokens=max_tokens)):
                    if not got and tag:
                        self._log(f"{tag}: 1er token en {time.time() - t0:.2f}s")
                    got = True
                    yield piece
            except Exception as e:
                self._log(f"LLM {tag}: {e!r}")
                if isinstance(getattr(e, "reason", None), ConnectionRefusedError) or isinstance(e, ConnectionError):
                    self.llm_ready = False
                    self._recover_llm()
                if not got and fallback:
                    yield fallback

        self.sp.say_stream(gen(), interrupt=interrupt, on_done=on_done)

    # ------------------------------------------------ commande en cours
    def _tick(self) -> None:
        c = self.s.current
        if c is None or c.silent or c.used_fullscreen:
            if c is not None and c.used_fullscreen and not c.announced_start:
                c.announced_start = True
                if self.cfg.verbosity >= 1:
                    self.sp.say(f"{first_word(c.cmd)} en plein écran.")
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
            c.announced_start = True
            c.last_update_at = now
            c.lines_at_last_update = c.out.total_lines
            what = self._describe_start(c.cmd)
            prog = self._progress_text(c)
            msg = f"En cours : {what}." + (f" {prog}." if prog else "")
            if what is None:
                # description par le LLM, puis progression déterministe
                if self._llm_ok():
                    msgs = prompts.start_messages(c.cmd)
                    def gen():
                        yield "En cours : "
                        try:
                            yield self.llm.complete(msgs, max_tokens=30).replace("`", "").rstrip(" .") or first_word(c.cmd)
                        except Exception:
                            yield first_word(c.cmd)
                        yield ". "
                        if prog:
                            yield prog + "."
                    self.sp.say_stream(gen(), interrupt=False)
                    return
                msg = f"{first_word(c.cmd)} en cours." + (f" {prog}." if prog else "")
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
                self.sp.say(f"Toujours en cours, rien de nouveau depuis {fmt_duration(silent_for)}.", interrupt=False)
            return
        prog = self._progress_text(c)
        if prog and prog != c.last_spoken_update:
            c.last_spoken_update = prog
            c.updates.append(prog)
            self.sp.say(prog + ".", interrupt=False)
            return
        if new_lines > 0 and self._llm_ok() and self.cfg.verbosity >= 1:
            recent = "\n".join(l for l in c.out.tail(15) if l.strip())[-2500:]
            msgs = prompts.progress_messages(c.cmd, c.duration, recent)
            self._llm_say(msgs, "", max_tokens=30, interrupt=False,
                          on_done=lambda t: c.updates.append(t), tag="étape")

    def _prompt_check(self, c: Command, now: float) -> bool:
        partial = c.out.partial
        if not (partial and now - c.last_output_at >= self.cfg.prompt_idle and partial != c.last_prompt_said):
            return False
        if not looks_like_prompt(partial):
            # pas de forme de question, mais le programme attend peut-être quand même
            if c.interactive or self._reading() is not True:
                return False
        c.last_prompt_said = partial
        c.prompts_said.append(strip_ansi(partial).strip())
        if c.interactive:
            # invite du programme interactif (>>> , $ …) : implicite, on ne la lit pas
            if not re.search(r"mot de passe|password|passphrase|\[[OoYy]/[Nn]\]|\?\s*$", partial, re.I):
                return False
        p = strip_ansi(partial).strip()
        if re.search(r"mot de passe|password|passphrase", p, re.I):
            self.sp.say("Mot de passe demandé.")
        else:
            prev = [l.strip() for l in c.out.lines[-3:] if l.strip()]
            ctx = (prev[-1][:150].rstrip(".") + ". ") if prev and not c.interactive else ""
            self.sp.say("Question : " + ctx + p)
        c.last_update_at = now
        return True

    def _speak_reply(self, c: Command) -> None:
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
        msgs = prompts.summary_messages(f"{typed}   (dans {first_word(c.cmd)})", None, time.time() - c.enter_at,
                                        compact_output(new, self.cfg.summary_chars), len(new))
        msgs[1]["content"] = msgs[1]["content"].replace("Statut : inconnu\n", "")
        self._llm_say(msgs, f"{len(new)} lignes. Dernière : {strip_ansi(new[-1])[:150]}", tag="réponse")

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
