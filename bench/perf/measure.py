#!/usr/bin/env python3
"""Mesure "temps et poids" de steph en usage reel (mission Q1, base pour Q2/Q3).

Rejouable, stdlib seul (aucune dependance lourde : pas de psutil, pas de pexpect).
Pilote une vraie session `steph run` dans un pty (comme un vrai terminal), envoie
de vraies commandes, et observe le processus audio reellement lance par la voix
(afplay/play/paplay/aplay) pour dater "premier son" et "fin de parole" - pas une
approximation par journal seul.

Isolation : XDG_CONFIG_HOME et XDG_RUNTIME_DIR (donc le port du serveur LLM et
les sockets) sont deplaces dans un dossier temporaire propre a chaque run, pour
ne jamais toucher la config reelle de l'utilisateur ni une session en cours.
XDG_DATA_HOME n'est PAS deplace : le modele et la voix deja installes sont
reutilises tels quels (installation reelle, pas de nouveau telechargement).

Q2a : la voix peut être jouée par le service vocal partagé (voice_service) et non
plus par la session elle-même. Une session « parle » alors quand le service dit la
jouer (`status`, champ playing_pid) ET qu'un lecteur audio enfant du service tourne.
Le chevauchement compte les lecteurs audio réels (sessions + service) : deux
lecteurs en même temps = deux voix superposées, quelle que soit l'architecture.

Usage :
    python3 bench/perf/measure.py --out bench/perf/results/mac.json
    python3 bench/perf/measure.py --out out.json --skip-idle --windows 1,2
    python3 bench/perf/measure.py --out out.json --steph-cmd "/chemin/.venv/bin/python -m steph.cli"
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import signal
import socket as socketlib
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
STEPH_BIN = shutil.which("steph") or str(Path.home() / ".local/bin/steph")
STEPH_CMD = [STEPH_BIN]  # remplacé par --steph-cmd (ex. l'interpréteur d'un autre arbre)
AUDIO_PLAYERS = {"afplay", "play", "paplay", "pw-play", "aplay"}
TEST_PORT = 18765  # different du port par defaut (8765) : isolation totale d'une vraie session

COMMANDS = {
    "courte": "pwd",
    "longue": "sleep 6 && echo fini",
    "erreur": "ls /chemin/totalement/inexistant/xyz",
    "resolue_code": "git status",
    "modele": "find /Applications -maxdepth 1 -type d | head -40",
}

# Q2b : commande dediee au scenario dechargement/rechargement - assez longue (sleep 6)
# pour laisser au rechargement anticipe le temps d'aboutir avant la fin de commande, ET
# sortie non resolue (passe par le resume LLM, contrairement a "longue" ci-dessus dont
# la sortie "fini" est lue telle quelle, verbatim, sans jamais toucher au modele).
IDLE_RELOAD_COMMAND = "sleep 6 && find /Applications -maxdepth 1 -type d | head -40"


# --------------------------------------------------------------- outils systeme

def ps_table() -> list[dict]:
    """Snapshot de la table des processus (macOS et Linux : memes colonnes -o)."""
    out = subprocess.run(
        ["ps", "-eo", "pid=,ppid=,pcpu=,rss=,comm="],
        capture_output=True, text=True, check=False,
    ).stdout
    rows = []
    for line in out.splitlines():
        parts = line.split(None, 4)
        if len(parts) < 5:
            continue
        try:
            rows.append({
                "pid": int(parts[0]), "ppid": int(parts[1]),
                "cpu": float(parts[2]), "rss_kb": int(parts[3]), "comm": parts[4],
            })
        except ValueError:
            continue
    return rows


def proc_stats(table: list[dict], pid: int) -> dict | None:
    for r in table:
        if r["pid"] == pid:
            return r
    return None


def audio_children(table: list[dict], ppid: int) -> list[dict]:
    return [r for r in table if r["ppid"] == ppid and os.path.basename(r["comm"]) in AUDIO_PLAYERS]


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def wait_until(fn, timeout: float, interval: float = 0.05):
    """Repete fn() jusqu'a une valeur vraie ; retourne l'HORODATAGE de la
    detection (pas la valeur de fn()), None si rien avant l'expiration."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if fn():
            return time.time()
        time.sleep(interval)
    return None


def mem_free_mb() -> float | None:
    if sys.platform == "darwin":
        out = subprocess.run(["vm_stat"], capture_output=True, text=True).stdout
        page = 4096
        for line in out.splitlines():
            if line.startswith("Pages free:"):
                pages = int(line.split(":")[1].strip().rstrip("."))
                return pages * page / 1024 / 1024
        return None
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) / 1024
    except OSError:
        return None
    return None


def disk_free_gb(path: str = "/") -> float:
    u = shutil.disk_usage(path)
    return u.free / 1024**3


def du_mb(path: Path) -> float | None:
    if not path.exists():
        return None
    out = subprocess.run(["du", "-sk", str(path)], capture_output=True, text=True).stdout
    try:
        return int(out.split()[0]) / 1024
    except (ValueError, IndexError):
        return None


# --------------------------------------------------------------- socket de controle

def ctl_request(sock_path: str, op: str, timeout: float = 2.0) -> dict | None:
    try:
        with socketlib.socket(socketlib.AF_UNIX, socketlib.SOCK_STREAM) as s:
            s.settimeout(timeout)
            s.connect(sock_path)
            s.sendall((json.dumps({"op": op}) + "\n").encode())
            f = s.makefile("rb")
            line = f.readline()
            return json.loads(line) if line else None
    except (OSError, ValueError):
        return None


def ctl_status(sock_path: str) -> dict:
    r = ctl_request(sock_path, "status")
    if not r or "t" not in r:
        return {}
    try:
        return json.loads(r["t"])
    except (ValueError, TypeError):
        return {}


# --------------------------------------------------------------- session pty

class PtySession:
    """Pilote une vraie session `steph run` : pty exterieur, lecture continue en
    tache de fond (sinon le tampon du pty se remplit et bloque l'enfant)."""

    def __init__(self, env: dict, cwd: Path):
        master, slave = os.openpty()
        pid = os.fork()
        if pid == 0:
            try:
                os.close(master)
                os.chdir(cwd)
                os.setsid()
                os.dup2(slave, 0)
                os.dup2(slave, 1)
                os.dup2(slave, 2)
                os.close(slave)
                import fcntl
                import termios
                fcntl.ioctl(0, termios.TIOCSCTTY, 0)
                os.execvpe(STEPH_CMD[0], STEPH_CMD + ["run"], env)
            finally:
                os._exit(127)
        os.close(slave)
        self.pid = pid
        self.master = master
        self._buf = bytearray()
        self._alive = True
        import threading
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._reader, daemon=True)
        self._thread.start()

    def _reader(self) -> None:
        import select
        while self._alive:
            try:
                r, _, _ = select.select([self.master], [], [], 0.2)
            except OSError:
                return
            if self.master in r:
                try:
                    data = os.read(self.master, 65536)
                except OSError:
                    self._alive = False
                    return
                if not data:
                    self._alive = False
                    return
                with self._lock:
                    self._buf += data
                    del self._buf[:-8192]  # ne garde qu'une fenetre recente

    def send(self, text: str) -> None:
        os.write(self.master, text.encode())

    def close(self, timeout: float = 8.0) -> None:
        """Fermeture propre (comme fermer un vrai terminal) : declenche le
        `finally` de cmd_run (arret du serveur si derniere session)."""
        if pid_alive(self.pid):
            try:
                self.send("exit\r")
            except OSError:
                pass
            deadline = time.time() + timeout
            while time.time() < deadline and pid_alive(self.pid):
                try:
                    r, _ = os.waitpid(self.pid, os.WNOHANG)
                    if r == self.pid:
                        break
                except ChildProcessError:
                    break
                time.sleep(0.1)
            if pid_alive(self.pid):
                try:
                    os.kill(self.pid, signal.SIGTERM)
                    os.waitpid(self.pid, 0)
                except (OSError, ChildProcessError):
                    pass
        self._alive = False
        try:
            os.close(self.master)
        except OSError:
            pass


# --------------------------------------------------------------- scenarios

def make_env(runtime_dir: Path, config_dir: Path, port: int | None = None) -> dict:
    port = port or TEST_PORT
    env = dict(os.environ)
    env["XDG_RUNTIME_DIR"] = str(runtime_dir)
    env["XDG_CONFIG_HOME"] = str(config_dir)
    env["STEPH_LLM_PORT"] = str(port)
    env.pop("STEPH_ACTIVE", None)
    env.pop("STEPH_SOCKET", None)
    return env


def runtime_socket(runtime_dir: Path, pid: int) -> str:
    return str(runtime_dir / "steph" / f"session-{pid}.sock")


# --------------------------------------------------------------- voix partagée (Q2a)

def voice_status(runtime_dir: Path) -> dict:
    """État du service vocal partagé ; {} s'il n'existe pas (architecture d'avant Q2a)."""
    path = runtime_dir / "steph" / "voice.sock"
    if not path.exists():
        return {}
    try:
        with socketlib.socket(socketlib.AF_UNIX, socketlib.SOCK_STREAM) as s:
            s.settimeout(1.0)
            s.connect(str(path))
            s.sendall(b'{"op": "status"}\n')
            line = s.makefile("rb").readline()
            return json.loads(line) if line else {}
    except (OSError, ValueError):
        return {}


def voice_pid(runtime_dir: Path) -> int | None:
    try:
        pid = int((runtime_dir / "steph" / "voice.pid").read_text())
        return pid if pid_alive(pid) else None
    except (OSError, ValueError):
        return None


def heard_sessions(table: list[dict], session_pids: list[int], runtime_dir: Path) -> set[int]:
    """Sessions entendues à cet instant : lecteur audio enfant de la session (avant Q2a)
    ou lecteur du service vocal jouant une annonce de cette session (après Q2a)."""
    heard = {p for p in session_pids if audio_children(table, p)}
    st = voice_status(runtime_dir)
    if st.get("playing_pid") in session_pids and audio_children(table, st.get("pid", -1)):
        heard.add(st["playing_pid"])
    return heard


def audio_players(table: list[dict], owner_pids: list[int]) -> int:
    """Lecteurs audio réels lancés par les sessions ou le service : 2 = deux voix à la fois."""
    return sum(len(audio_children(table, p)) for p in owner_pids)


def stop_voice_service(runtime_dir: Path, timeout: float = 5.0) -> bool | None:
    """Après la fermeture des sessions, le service doit s'arrêter seul. Vrai s'il l'a
    fait, faux s'il a fallu le tuer, None s'il n'y en avait pas."""
    pid = voice_pid(runtime_dir)
    if pid is None:
        return None
    if wait_until(lambda: not pid_alive(pid), timeout):
        return True
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        pass
    return False


def wait_boot_sound(sess: PtySession, runtime_dir: Path, timeout: float = 90.0) -> dict:
    """Attend le premier son (annonce d'ouverture), puis sa fin."""
    t_launch = time.time()

    def heard() -> bool:
        return sess.pid in heard_sessions(ps_table(), [sess.pid], runtime_dir)

    t_first = wait_until(heard, timeout)
    t_end = None
    if t_first:
        t_end = wait_until(lambda: not heard(), 30.0)
        if t_end is None:
            t_end = time.time()
    return {"t_launch": t_launch, "t_first_sound": t_first, "t_speech_end": t_end,
            "latency_launch_to_sound": (t_first - t_launch) if t_first else None,
            "latency_sound_duration": (t_end - t_first) if (t_first and t_end) else None}


def measure_command(sess: PtySession, sock_path: str, cmd_text: str, runtime_dir: Path,
                    timeout: float = 90.0, interval: float = 0.03) -> dict:
    """Une seule boucle de sondage continue, du send() a la fin de la parole :
    une commande courte (ex. `pwd`) peut demarrer ET finir de parler en moins
    d'une seconde - deux boucles separees (fin de commande, PUIS audio) rateraient
    la fenetre. `commands` (compteur du socket) leve l'ambiguite sur le debut,
    puisque `running` peut deja valoir None avant meme l'envoi (etat precedent)."""
    commands_before = ctl_status(sock_path).get("commands", 0)
    t_send = time.time()
    sess.send(cmd_text + "\r")
    t_started = t_cmd_end = t_first = t_speech_end = None
    deadline = time.time() + timeout
    while time.time() < deadline:
        st = ctl_status(sock_path)
        if t_started is None and st.get("commands", 0) > commands_before:
            t_started = time.time()
        if t_started is not None and t_cmd_end is None and st.get("running") is None:
            t_cmd_end = time.time()
        if t_cmd_end is not None:
            kids = sess.pid in heard_sessions(ps_table(), [sess.pid], runtime_dir)
            if t_first is None and kids:
                t_first = time.time()
            elif t_first is not None and not kids:
                t_speech_end = time.time()
                break
        time.sleep(interval)
    return {
        "cmd": cmd_text, "t_send": t_send, "t_cmd_end": t_cmd_end,
        "t_first_sound": t_first, "t_speech_end": t_speech_end,
        "latency_cmdend_to_sound_s": (t_first - t_cmd_end) if (t_first and t_cmd_end) else None,
        "latency_sound_duration_s": (t_speech_end - t_first) if (t_first and t_speech_end) else None,
    }


def sample_weights(sess_pid: int, llama_pid: int | None, duration: float, interval: float = 0.5) -> dict:
    """Echantillonne CPU/RAM pendant `duration` secondes, retourne pic + moyenne."""
    steph_cpu, steph_rss, llama_cpu, llama_rss = [], [], [], []
    deadline = time.time() + duration
    while time.time() < deadline:
        t = ps_table()
        s = proc_stats(t, sess_pid)
        if s:
            steph_cpu.append(s["cpu"])
            steph_rss.append(s["rss_kb"])
        if llama_pid:
            l = proc_stats(t, llama_pid)
            if l:
                llama_cpu.append(l["cpu"])
                llama_rss.append(l["rss_kb"])
        time.sleep(interval)

    def agg(vals, div=1):
        return {"peak": max(vals) / div, "avg": statistics.mean(vals) / div} if vals else None

    return {
        "steph_cpu_pct": agg(steph_cpu), "steph_rss_mb": agg(steph_rss, 1024),
        "llama_cpu_pct": agg(llama_cpu), "llama_rss_mb": agg(llama_rss, 1024),
    }


def find_llama_pid(runtime_dir: Path) -> int | None:
    pidfile = runtime_dir / "steph" / "llama-server.pid"
    try:
        pid = int(pidfile.read_text())
        return pid if pid_alive(pid) else None
    except (OSError, ValueError):
        return None


def run_scenario(name: str, prewarm: bool) -> dict:
    tmp = Path(tempfile.mkdtemp(prefix="sp-", dir="/tmp"))
    runtime_dir, config_dir = tmp / "rt", tmp / "cf"
    runtime_dir.mkdir(parents=True)
    config_dir.mkdir(parents=True)
    env = make_env(runtime_dir, config_dir)
    result: dict = {"scenario": name, "prewarm": prewarm, "commands": {}}
    sess = None
    try:
        if prewarm:
            t0 = time.time()
            subprocess.run(STEPH_CMD + ["server", "start"], env=env, cwd=REPO,
                            capture_output=True, text=True, timeout=180)
            result["prewarm_wait_s"] = time.time() - t0
        sess = PtySession(env, REPO)
        result["boot"] = wait_boot_sound(sess, runtime_dir)
        result["boot"]["llm_healthy_after_s"] = None
        t_boot = time.time()
        t_ready = wait_until(lambda: ctl_status(runtime_socket(runtime_dir, sess.pid)).get("llm") is True, 180.0, 0.5)
        if t_ready:
            result["boot"]["llm_healthy_after_s"] = t_ready - t_boot
        sock_path = runtime_socket(runtime_dir, sess.pid)
        for label, cmd_text in COMMANDS.items():
            result["commands"][label] = measure_command(sess, sock_path, cmd_text, runtime_dir)
        llama_pid = find_llama_pid(runtime_dir)
        result["weights_after_commands"] = sample_weights(sess.pid, llama_pid, duration=2.0)
        result["_sess"] = sess
        result["_runtime_dir"] = runtime_dir
        result["_llama_pid"] = llama_pid
        result["_env"] = env
        result["_tmp"] = tmp
    except Exception as e:
        result["error"] = repr(e)
        # meme en echec : jamais laisser le serveur LLM ou la session orphelins
        if sess is not None:
            sess.close()
        shutil.rmtree(tmp, ignore_errors=True)
    return result


def teardown_scenario(result: dict) -> None:
    sess = result.pop("_sess", None)
    tmp = result.pop("_tmp", None)
    result.pop("_env", None)
    result.pop("_llama_pid", None)
    result.pop("_runtime_dir", None)
    if sess:
        sess.close()
    if tmp:
        result["voice_service_exited_cleanly"] = stop_voice_service(tmp / "rt")
        shutil.rmtree(tmp, ignore_errors=True)


def idle_measurement(minutes: float) -> dict:
    """Repos : relance une session seule (prechauffee), attend `minutes`, mesure avant/apres."""
    tmp = Path(tempfile.mkdtemp(prefix="sp-idle-", dir="/tmp"))
    runtime_dir, config_dir = tmp / "rt", tmp / "cf"
    runtime_dir.mkdir(parents=True)
    config_dir.mkdir(parents=True)
    env = make_env(runtime_dir, config_dir)
    out = {"minutes": minutes}
    sess = None
    try:
        subprocess.run(STEPH_CMD + ["server", "start"], env=env, cwd=REPO,
                        capture_output=True, text=True, timeout=180)
        sess = PtySession(env, REPO)
        wait_boot_sound(sess, runtime_dir, timeout=90)
        llama_pid = find_llama_pid(runtime_dir)
        time.sleep(2)  # laisse retomber le pic de demarrage avant la ligne de base
        t = ps_table()
        before_steph = proc_stats(t, sess.pid)
        before_llama = proc_stats(t, llama_pid) if llama_pid else None
        out["before"] = {
            "steph_rss_mb": before_steph["rss_kb"] / 1024 if before_steph else None,
            "llama_rss_mb": before_llama["rss_kb"] / 1024 if before_llama else None,
        }
        weights = sample_weights(sess.pid, llama_pid, duration=minutes * 60, interval=5.0)
        out["during"] = weights
        t = ps_table()
        after_steph = proc_stats(t, sess.pid)
        after_llama = proc_stats(t, llama_pid) if llama_pid else None
        out["after"] = {
            "steph_rss_mb": after_steph["rss_kb"] / 1024 if after_steph else None,
            "llama_rss_mb": after_llama["rss_kb"] / 1024 if after_llama else None,
        }
        vpid = voice_pid(runtime_dir)
        if vpid:
            v = proc_stats(ps_table(), vpid)
            out["after"]["voice_rss_mb"] = v["rss_kb"] / 1024 if v else None
        sess.close()
        sess = None
    except Exception as e:
        out["error"] = repr(e)
    finally:
        if sess is not None:
            sess.close()
        stop_voice_service(runtime_dir)
        shutil.rmtree(tmp, ignore_errors=True)
    return out


def idle_unload_measurement(idle_unload_minutes: float, anticipate: bool) -> dict:
    """Q2b : RAM avant/apres dechargement, temps de dechargement observe, puis latence
    de la premiere commande apres la pause - avec et sans rechargement anticipe
    (STEPH_LLM_ANTICIPATORY_RELOAD), meme reglage court d'inactivite pour les deux."""
    tmp = Path(tempfile.mkdtemp(prefix="sp-idleunload-", dir="/tmp"))
    runtime_dir, config_dir = tmp / "rt", tmp / "cf"
    runtime_dir.mkdir(parents=True)
    config_dir.mkdir(parents=True)
    env = make_env(runtime_dir, config_dir)
    env["STEPH_LLM_IDLE_UNLOAD_MINUTES"] = str(idle_unload_minutes)
    env["STEPH_LLM_ANTICIPATORY_RELOAD"] = "true" if anticipate else "false"
    out: dict = {"idle_unload_minutes": idle_unload_minutes, "anticipate": anticipate}
    sess = None
    try:
        subprocess.run([STEPH_BIN, "server", "start"], env=env, cwd=REPO,
                        capture_output=True, text=True, timeout=180)
        sess = PtySession(env, REPO)
        wait_boot_sound(sess, runtime_dir, timeout=90)
        llama_pid = find_llama_pid(runtime_dir)
        t = ps_table()
        before = proc_stats(t, llama_pid) if llama_pid else None
        out["ram_before_mb"] = before["rss_kb"] / 1024 if before else None

        t_wait = time.time()
        gone = wait_until(lambda: find_llama_pid(runtime_dir) is None, idle_unload_minutes * 60 + 30, 1.0)
        out["unloaded"] = gone is not None
        out["unload_observed_after_s"] = (gone - t_wait) if gone else None
        out["ram_after_unload_mb"] = 0.0 if gone else None

        sock_path = runtime_socket(runtime_dir, sess.pid)
        # sonde en parallele "llm pret" (endpoint /ctl status) pendant l'execution de la
        # commande : timing direct du rechargement, independant du son (le prefixe P9 est
        # synthetise et joue immediatement dans les deux cas - voir docs/perf-baseline.md)
        llm_ready_at: dict = {}
        stop_poll = threading.Event()

        def poll_llm_ready():
            while not stop_poll.is_set():
                if ctl_status(sock_path).get("llm"):
                    llm_ready_at["t"] = time.time()
                    return
                time.sleep(0.1)

        poll_thread = threading.Thread(target=poll_llm_ready, daemon=True)
        poll_thread.start()
        cmd_result = measure_command(sess, sock_path, IDLE_RELOAD_COMMAND, runtime_dir, timeout=120)
        stop_poll.set()
        poll_thread.join(timeout=1.0)
        out["first_command_after_pause"] = cmd_result
        out["llm_ready_relative_to_send_s"] = (
            llm_ready_at["t"] - cmd_result["t_send"] if "t" in llm_ready_at else None
        )
        out["llm_ready_before_cmd_end"] = (
            llm_ready_at["t"] <= cmd_result["t_cmd_end"]
            if ("t" in llm_ready_at and cmd_result.get("t_cmd_end")) else None
        )

        llama_pid2 = find_llama_pid(runtime_dir)
        out["reloaded"] = llama_pid2 is not None
        after = proc_stats(ps_table(), llama_pid2) if llama_pid2 else None
        out["ram_after_reload_mb"] = after["rss_kb"] / 1024 if after else None
    except Exception as e:
        out["error"] = repr(e)
    finally:
        if sess is not None:
            sess.close()
        shutil.rmtree(tmp, ignore_errors=True)
    return out


def multiwindow_measurement(counts: list[int], cmd_text: str) -> dict:
    """N sessions steph partageant le même serveur LLM isolé, même commande envoyée à
    toutes : latence, contention, chevauchement audio.

    La commande part d'abord vers les N-1 premières fenêtres, puis vers la dernière : c'est
    là que l'on a tapé en dernier, donc la fenêtre active (Q2a). Son délai fin de commande ->
    premier son est rapporté à part ; celui des autres inclut, après Q2a, l'attente en file."""
    out = {}
    for n in counts:
        tmp = Path(tempfile.mkdtemp(prefix=f"sp-mw{n}-", dir="/tmp"))
        runtime_dir, config_dir = tmp / "rt", tmp / "cf"
        runtime_dir.mkdir(parents=True)
        config_dir.mkdir(parents=True)
        env = make_env(runtime_dir, config_dir)
        row: dict = {"n": n}
        sessions: list[PtySession] = []
        try:
            subprocess.run(STEPH_CMD + ["server", "start"], env=env, cwd=REPO,
                           capture_output=True, text=True, timeout=180)
            for _ in range(n):
                s = PtySession(env, REPO)
                sessions.append(s)
                wait_boot_sound(s, runtime_dir, timeout=90)
            llama_pid = find_llama_pid(runtime_dir)
            pids = [s.pid for s in sessions]
            sockets = [runtime_socket(runtime_dir, p) for p in pids]
            commands_before = [ctl_status(st).get("commands", 0) for st in sockets]
            # la dernière fenêtre reçoit la commande 0,5 s après les autres : c'est là que l'on
            # a tapé en dernier, donc la fenêtre active. Sans cet écart, les frappes de toutes
            # les fenêtres arrivent dans la même milliseconde et l'ordre n'a plus de sens.
            for s in sessions[:-1]:
                s.send(cmd_text + "\r")
            if n > 1:
                time.sleep(0.5)
            sessions[-1].send(cmd_text + "\r")
            t_cmd_end = [None] * n
            t_first = [None] * n
            t_last_heard = [None] * n
            overlap_ticks = speech_ticks = total_ticks = 0
            cpu_total, rss_total = [], []
            t_silence = None
            t_loop0 = time.time()
            deadline = time.time() + 180
            while time.time() < deadline:
                table = ps_table()
                vpid = voice_pid(runtime_dir)
                owners = pids + ([vpid] if vpid else [])
                now = time.time()
                for i in range(n):
                    if t_cmd_end[i] is None:
                        st = ctl_status(sockets[i])
                        if st.get("commands", 0) > commands_before[i] and st.get("running") is None:
                            t_cmd_end[i] = now
                heard = heard_sessions(table, pids, runtime_dir)
                for i, p in enumerate(pids):
                    if p in heard and t_cmd_end[i] is not None:
                        t_first[i] = t_first[i] or now
                        t_last_heard[i] = now
                players = audio_players(table, owners)
                total_ticks += 1
                speech_ticks += players >= 1
                overlap_ticks += players >= 2
                rows = [r for r in table if r["pid"] in owners]
                cpu_total.append(sum(r["cpu"] for r in rows))
                rss_total.append(sum(r["rss_kb"] for r in rows) / 1024)
                # fin : toutes les fenêtres ont parlé, puis 1,5 s sans aucun lecteur
                # (une annonce lue segment par segment laisse de courts blancs entre deux)
                if all(t_first) and players == 0:
                    t_silence = t_silence or now
                    if now - t_silence >= 1.5:
                        break
                else:
                    t_silence = None
                time.sleep(0.05)
            lat = [(f - e) if (e and f) else None for e, f in zip(t_cmd_end, t_first)]
            row["latency_cmdend_to_sound_s"] = [x for x in lat if x is not None]
            row["latency_by_window_s"] = lat
            row["active_window_latency_s"] = lat[-1]
            row["windows_heard"] = sum(1 for x in t_first if x)
            row["speech_span_s"] = ((max(x for x in t_last_heard if x) - min(x for x in t_first if x))
                                    if any(t_first) else None)
            # résolution des délais : un tour de sondage (ps + sockets de toutes les fenêtres)
            row["tick_s_avg"] = ((time.time() - t_loop0) / total_ticks) if total_ticks else None
            row["overlap_fraction"] = (overlap_ticks / total_ticks) if total_ticks else None
            row["overlap_of_speech_fraction"] = (overlap_ticks / speech_ticks) if speech_ticks else None
            row["cpu_total_pct"] = {"peak": max(cpu_total), "avg": statistics.mean(cpu_total)} if cpu_total else None
            row["rss_total_mb_peak"] = max(rss_total) if rss_total else None
            row["weights"] = sample_weights(sessions[0].pid, llama_pid, duration=2.0)
            table = ps_table()
            row["llama_rss_mb_total"] = (proc_stats(table, llama_pid) or {}).get("rss_kb", 0) / 1024 if llama_pid else None
            row["steph_rss_mb_sum"] = sum((proc_stats(table, p) or {}).get("rss_kb", 0) for p in pids) / 1024
            vpid = voice_pid(runtime_dir)
            row["voice_rss_mb"] = (proc_stats(table, vpid) or {}).get("rss_kb", 0) / 1024 if vpid else 0.0
            row["steph_plus_voice_rss_mb"] = row["steph_rss_mb_sum"] + row["voice_rss_mb"]
        except Exception as e:
            row["error"] = repr(e)
        finally:
            for s in sessions:
                s.close()
            row["voice_service_exited_cleanly"] = stop_voice_service(runtime_dir)
            shutil.rmtree(tmp, ignore_errors=True)
        out[str(n)] = row
    return out


def disk_report() -> dict:
    data_home = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
    return {
        "install_uv_tool_mb": du_mb(Path.home() / ".local/share/uv/tools/steph"),
        "models_mb": du_mb(data_home / "steph/models"),
        "voices_mb": du_mb(data_home / "steph/voices"),
        "config_kb": (du_mb(Path.home() / ".config/steph") or 0) * 1024,
        "disk_free_gb": disk_free_gb("/"),
    }


def log_growth_report() -> dict:
    import datetime as dt
    out = {}
    real_runtime = Path(os.environ.get("XDG_RUNTIME_DIR", f"/tmp/steph-{os.getuid()}")) / "steph"
    for name in ("steph.log", "llama-server.log"):
        p = real_runtime / name
        if not p.exists():
            out[name] = None
            continue
        st = p.stat()
        try:
            birth = st.st_birthtime
        except AttributeError:
            birth = st.st_mtime
        span_h = max((st.st_mtime - birth) / 3600, 1 / 60)
        out[name] = {
            "size_bytes": st.st_size,
            "span_hours_observed": round(span_h, 2),
            "avg_bytes_per_hour": round(st.st_size / span_h, 1),
            "note": "moyenne sur l'historique du fichier, pas une mesure controlee sur 1h",
        }
    return out


def clean_stray_test_server(port: int | None = None) -> None:
    """Un run precedent tue brutalement (SIGKILL, debogage) peut laisser un
    llama-server orphelin sur le port de test : `ensure_server()` le reutiliserait
    en silence et fausserait la mesure "froid" (le serveur semblerait deja chaud).
    Uniquement le port dedie au test, jamais le port reel (8765) d'une session."""
    port = port or TEST_PORT
    try:
        out = subprocess.run(["lsof", "-ti", f":{port}"], capture_output=True, text=True).stdout
    except FileNotFoundError:
        return
    for line in out.split():
        pid = int(line)
        row = next((r for r in ps_table() if r["pid"] == pid), None)
        if row and os.path.basename(row["comm"]) == "llama-server":
            print(f"nettoyage : llama-server orphelin (pid {pid}) sur le port de test {port}", file=sys.stderr)
            try:
                os.kill(pid, signal.SIGTERM)
                time.sleep(1)
            except OSError:
                pass


def main() -> int:
    global TEST_PORT
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--skip-idle", action="store_true")
    ap.add_argument("--skip-multiwindow", action="store_true")
    ap.add_argument("--skip-idle-unload", action="store_true")
    ap.add_argument("--idle-minutes", type=float, default=5.0)
    ap.add_argument("--idle-unload-minutes", type=float, default=0.2,
                     help="reglage court de llm_idle_unload_minutes pour le scenario Q2b (defaut 12 s)")
    ap.add_argument("--windows", default="1,2,4,8")
    ap.add_argument("--steph-cmd", default=STEPH_BIN,
                    help="commande qui lance steph (ex. « .venv/bin/python -m steph.cli » d'un autre arbre)")
    ap.add_argument("--skip-single", action="store_true", help="sauter les scénarios froid et chaud")
    ap.add_argument("--port", type=int, default=TEST_PORT,
                    help="port du serveur LLM de test : un autre banc lancé en parallèle ne doit pas le partager")
    args = ap.parse_args()
    TEST_PORT = args.port
    STEPH_CMD[:] = shlex.split(args.steph_cmd)

    if not shutil.which(STEPH_CMD[0]):
        print(f"steph introuvable ({STEPH_CMD[0]})", file=sys.stderr)
        return 1

    clean_stray_test_server()

    report: dict = {"host": os.uname()._asdict() if hasattr(os.uname(), "_asdict") else list(os.uname()),
                     "started_at": time.time()}

    report["steph_cmd"] = STEPH_CMD
    if not args.skip_single:
        print("[1/6] scenario froid (llama-server pas encore lance)", file=sys.stderr)
        cold = run_scenario("froid", prewarm=False)
        teardown_scenario(cold)
        report["cold"] = cold
        clean_stray_test_server()  # verifie que la fermeture propre a bien arrete le serveur partage

        print("[2/6] scenario chaud (llama-server prechauffe avant le lancement)", file=sys.stderr)
        warm = run_scenario("chaud", prewarm=True)
        teardown_scenario(warm)
        report["warm"] = warm
        clean_stray_test_server()

    if not args.skip_idle:
        print(f"[3/6] repos ({args.idle_minutes} min sans commande)", file=sys.stderr)
        report["idle"] = idle_measurement(args.idle_minutes)
        clean_stray_test_server()
    else:
        report["idle"] = {"skipped": True}

    if not args.skip_idle_unload:
        print(f"[4/6] Q2b dechargement au repos + rechargement anticipe "
              f"(idle_unload={args.idle_unload_minutes} min)", file=sys.stderr)
        with_anticipation = idle_unload_measurement(args.idle_unload_minutes, anticipate=True)
        clean_stray_test_server()  # meme TEST_PORT que la mesure suivante : jamais de serveur partage entre les deux
        without_anticipation = idle_unload_measurement(args.idle_unload_minutes, anticipate=False)
        clean_stray_test_server()
        report["idle_unload"] = {"with_anticipation": with_anticipation, "without_anticipation": without_anticipation}
    else:
        report["idle_unload"] = {"skipped": True}

    if not args.skip_multiwindow:
        counts = [int(x) for x in args.windows.split(",") if x.strip()]
        print(f"[5/6] multi-fenetre {counts}", file=sys.stderr)
        report["multiwindow"] = multiwindow_measurement(counts, COMMANDS["modele"])
        clean_stray_test_server()
    else:
        report["multiwindow"] = {"skipped": True}

    print("[6/6] disque", file=sys.stderr)
    report["disk"] = disk_report()
    report["log_growth"] = log_growth_report()
    report["mem_free_mb_end"] = mem_free_mb()
    report["finished_at"] = time.time()

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"ecrit : {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
