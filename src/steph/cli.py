"""Point d'entrée : `steph` (terminal parlant), `steph ask`, `steph ctl …`, `steph server …`."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
from pathlib import Path

from .config import RUNTIME_DIR, load_config

HELP_KEYS = "F7 questions, F8 silence, F9 répéter, F10 détails."


# ------------------------------------------------------------------ client
def find_socket(explicit: str | None = None) -> str | None:
    if explicit:
        return explicit
    env = os.environ.get("STEPH_SOCKET")
    if env and os.path.exists(env):
        return env
    socks = sorted(RUNTIME_DIR.glob("session-*.sock"), key=lambda p: p.stat().st_mtime, reverse=True)
    for s in socks:
        if _alive(str(s)):
            return str(s)
    return None


def _alive(path: str) -> bool:
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(0.3)
            s.connect(path)
        return True
    except OSError:
        return False


def request(path: str, req: dict, on_piece=None, timeout: float = 90) -> str:
    out = []
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        s.connect(path)
        s.sendall((json.dumps(req, ensure_ascii=False) + "\n").encode())
        f = s.makefile("rb")
        for line in f:
            msg = json.loads(line)
            if "t" in msg:
                out.append(msg["t"])
                if on_piece:
                    on_piece(msg["t"])
            if msg.get("error"):
                raise RuntimeError(msg["error"])
            if msg.get("done"):
                break
    return "".join(out)


def cmd_ask(args) -> int:
    path = find_socket(args.socket)
    if not path:
        print("Aucune session steph active.", file=sys.stderr)
        return 1

    def ask(q: str) -> None:
        request(path, {"op": "ask", "q": q, "speak": not args.mute},
                on_piece=lambda t: (sys.stdout.write(t), sys.stdout.flush()))
        print()

    if args.question:
        ask(" ".join(args.question))
        return 0
    try:
        import readline  # noqa: F401  (historique / édition de ligne)
    except ImportError:
        pass
    # `q` seul : la question est lue ici et non par le shell, qui
    # interpréterait apostrophes et guillemets
    if args.once:
        try:
            q = input("? ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if q:
            ask(q)
        return 0
    # fenêtre interactive
    print("Questions sur la session. Entrée vide ou Ctrl+D pour quitter.")
    print("Commandes : /stop (silence), /repeter, /details, /historique")
    request(path, {"op": "say", "text": "Fenêtre de questions ouverte."})
    while True:
        try:
            q = input("\n? ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not q:
            return 0
        if q in ("/stop", "/silence"):
            request(path, {"op": "stop"})
        elif q in ("/repeter", "/répéter", "/repeat"):
            request(path, {"op": "repeat"})
        elif q == "/details":
            request(path, {"op": "details"})
        elif q in ("/historique", "/history"):
            print(request(path, {"op": "history"}))
        else:
            try:
                ask(q)
            except (OSError, RuntimeError) as e:
                print(f"[erreur : {e}]")


def cmd_ctl(args) -> int:
    path = find_socket(args.socket)
    if not path:
        print("Aucune session steph active.", file=sys.stderr)
        return 1
    req = {"op": args.action}
    if args.action == "say":
        req["text"] = " ".join(args.text)
    print(request(path, req), end="")
    return 0


def open_ask_window(socket_path: str, cfg) -> None:
    exe = shutil.which("steph") or sys.argv[0]
    inner = [exe, "ask", "--socket", socket_path]
    if sys.platform == "darwin" and not cfg.terminal_cmd:
        import shlex
        line = shlex.join(inner).replace("\\", "\\\\").replace('"', '\\"')
        app = "iTerm" if os.environ.get("TERM_PROGRAM") == "iTerm.app" else "Terminal"
        if app == "iTerm":
            script = f'tell application "iTerm" to create window with default profile command "{line}"'
        else:
            script = f'tell application "Terminal" to do script "{line}"\ntell application "Terminal" to activate'
        subprocess.Popen(["osascript", "-e", script], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, start_new_session=True)
        return
    if cfg.terminal_cmd:
        cmd = cfg.terminal_cmd.split() + inner
    elif shutil.which("ptyxis"):
        cmd = ["ptyxis", "--new-window", "--"] + inner
    elif shutil.which("gnome-terminal"):
        cmd = ["gnome-terminal", "--"] + inner
    elif shutil.which("konsole"):
        cmd = ["konsole", "-e"] + inner
    elif shutil.which("kitty"):
        cmd = ["kitty"] + inner
    else:
        cmd = ["xterm", "-e"] + inner
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     stdin=subprocess.DEVNULL, start_new_session=True)


# ------------------------------------------------------------ session
def cmd_run(args) -> int:
    if os.environ.get("STEPH_ACTIVE"):
        print("steph tourne déjà dans ce terminal.", file=sys.stderr)
        return 1
    cfg = load_config()
    if args.no_voice:
        cfg.tts_enabled = False
    from .llm import LLM
    from .narrator import Narrator
    from .proxy import PtyProxy
    from .server import ControlServer
    from .session import Session
    from .tts import Speaker

    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    sock = str(RUNTIME_DIR / f"session-{os.getpid()}.sock")
    session = Session()
    speaker = Speaker(cfg)
    llm = LLM(cfg)
    nar = Narrator(cfg, session, speaker, llm)
    server = ControlServer(sock, nar)

    def boot_llm():
        ok = llm.ensure_server(90)
        nar.llm_ready = ok
        if ok:
            nar.warm_system_prompts()
        else:
            speaker.say("Attention : le modèle local n'a pas démarré. Résumés simplifiés.", interrupt=False)

    speaker.say(f"Terminal parlant. {HELP_KEYS}")
    threading.Thread(target=boot_llm, daemon=True).start()
    nar.start()
    proxy = PtyProxy(cfg, nar, sock, on_ask=lambda: open_ask_window(sock, cfg))
    try:
        code = proxy.run()
    finally:
        server.close()
        speaker.close()
        zd = Path(sock).with_suffix(".zdotdir")
        shutil.rmtree(zd, ignore_errors=True)
        # dernier terminal parlant fermé : on libère la mémoire GPU
        if not any(_alive(str(p)) for p in RUNTIME_DIR.glob("session-*.sock")):
            llm.stop_server()
    return code


def cmd_server(args) -> int:
    from .llm import LLM
    llm = LLM(load_config())
    if args.action == "start":
        ok = llm.ensure_server()
        print("prêt" if ok else f"échec, voir {llm.logfile}")
        return 0 if ok else 1
    if args.action == "stop":
        llm.stop_server()
        return 0
    print("en marche" if llm.healthy() else "arrêté")
    return 0


def cmd_say(args) -> int:
    from .tts import Speaker
    import time
    sp = Speaker(load_config())
    sp.say(" ".join(args.text))
    time.sleep(0.2)
    while sp.speaking.is_set() or not sp._q.empty():
        time.sleep(0.05)
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="steph", description="Terminal parlant pour personnes malvoyantes.")
    sub = p.add_subparsers(dest="sub")
    r = sub.add_parser("run", help="lancer un shell parlant (par défaut)")
    r.add_argument("--no-voice", action="store_true", help="pas de synthèse vocale")
    a = sub.add_parser("ask", help="poser des questions sur la session")
    a.add_argument("--socket")
    a.add_argument("--once", action="store_true")
    a.add_argument("--mute", action="store_true", help="afficher sans lire à voix haute")
    a.add_argument("question", nargs="*")
    c = sub.add_parser("ctl", help="contrôler la session : stop, repeat, details, say, status, history")
    c.add_argument("action", choices=["stop", "repeat", "details", "say", "status", "history"])
    c.add_argument("text", nargs="*")
    c.add_argument("--socket")
    s = sub.add_parser("server", help="gérer le modèle local")
    s.add_argument("action", choices=["start", "stop", "status"])
    y = sub.add_parser("say", help="tester la voix")
    y.add_argument("text", nargs="+")
    args = p.parse_args(argv)
    if args.sub in (None, "run"):
        if args.sub is None:
            args.no_voice = False
        return cmd_run(args)
    return {"ask": cmd_ask, "ctl": cmd_ctl, "server": cmd_server, "say": cmd_say}[args.sub](args)


if __name__ == "__main__":
    sys.exit(main())
