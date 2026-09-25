"""Test de bout en bout : pilote `steph` dans un PTY, relève le journal de parole.

Usage : uv run python tests/e2e.py [scénario]
"""
import os, pty, select, sys, time, json, signal

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG = os.environ.get("E2E_LOG", f"/tmp/steph-e2e-speech-{os.getuid()}.log")

SCENARIOS = {
 "basic": [
   ("echo bonjour", 3), ("ls /usr", 3), ("cd /tmp", 2), ("cat /nope", 3),
   ("ls -la /etc | head -30", 6), ("false", 2), ("nosuchcmd", 2),
   ("python3 -c 'import json; json.loads(\"{\")'", 6),
 ],
 "lsla": [("ls -la /etc | head -30", 12), ("echo fin", 3)],
 "repl": [("python3", 3), ("1+1", 3), ("import os; print(len(os.listdir('/usr/bin')))", 3),
          ("[x*x for x in range(60)]", 6), ("1/0", 6), ("exit()", 3)],
 "subshell": [("bash --norc", 2), ("ls /usr", 3), ("cat /etc/os-release", 7), ("exit", 3)],
 "keys": [("dnf --cacheonly list --installed 2>/dev/null | head -80", 8), ("KEY:\x1b[21~", 10), ("KEY:\x1b[20~", 4),
          ("ASK:quel est le plus gros paquet listé ?\net combien de paquets python ?", 25)],
 "real": [("rm -rf /tmp/steph-clone && git clone --progress https://github.com/rhasspy/piper.git /tmp/steph-clone", 25),
          ("sleep 30", 6), ("KEY:\x03", 3),
          ("python3 -c \"import getpass; getpass.getpass('Mot de passe : '); print('lu')\"", 3), ("secret", 3),
          ("python3 -c \"n=input('Quel est ton nom ');print('salut', n)\"", 4), ("Luis", 3),
          ("ls --color=always /tmp/steph-clone", 6)],
 "typeahead": [("sleep 7", 1), ("echo tapé en avance", 12)],
 "long": [
   (f"python3 {SCRIPT_DIR}/fake_apt.py", 45),
 ],
 "prompt": [
   (f"python3 {SCRIPT_DIR}/fake_apt.py --ask", 8), ("n", 4),
 ],
 "ask": [
   ("cat /etc/nonexistent.conf", 4),
   ("ls /usr/share | wc -l", 3),
   ("q pourquoi la première commande a échoué ?", 15),
 ],
}


# Phrases qui doivent apparaître (sans LLM : seulement le déterministe)
EXPECT = {
    "basic": ["bonjour", "Dossier tmp", "Aucun fichier ou dossier", "Commande introuvable : nosuchcmd"],
    "ci": ["bonjour", "Dossier tmp", "Commande introuvable", "Question : Quel est ton nom", "salut Luis",
           "python3 interactif", "Fin de python3"],
}
SCENARIOS["ci"] = [
    ("echo bonjour", 3), ("cd /tmp", 2), ("nosuchcmd_xyz", 3),
    ("python3 -c \"n=input('Quel est ton nom ');print('salut', n)\"", 4), ("Luis", 3),
    ("python3", 3), ("1+1", 3), ("exit()", 3),
]


def run(name):
    open(LOG, "w").close()
    env = dict(os.environ, STEPH_TTS_ENABLED="0", STEPH_SPEECH_LOG=LOG, TERM="xterm-256color")
    env.pop("STEPH_ACTIVE", None); env.pop("STEPH_SOCKET", None)
    pid, fd = pty.fork()
    if pid == 0:
        os.execvpe("uv", ["uv", "run", "--project", os.path.dirname(SCRIPT_DIR), "steph"], env)
    out = bytearray()
    def pump(t):
        end = time.time() + t
        while time.time() < end:
            r, _, _ = select.select([fd], [], [], 0.1)
            if r:
                try: out.extend(os.read(fd, 65536))
                except OSError: return
    t0 = time.time()
    pump(8)  # démarrage shell + modèle
    import glob, subprocess
    for cmd, wait in SCENARIOS[name]:
        if cmd.startswith("KEY:"):
            os.write(fd, cmd[4:].encode())
        elif cmd.startswith("ASK:"):
            sys.path.insert(0, os.path.join(os.path.dirname(SCRIPT_DIR), "src"))
            from steph.config import RUNTIME_DIR
            sock = max(glob.glob(str(RUNTIME_DIR / "session-*.sock")), key=os.path.getmtime)
            p = subprocess.Popen(["steph", "ask", "--socket", sock], stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            import threading
            res = {}
            threading.Thread(target=lambda: res.setdefault("out", p.communicate(cmd[4:] + "\n")[0])).start()
            pump(wait)
            print("=== fenêtre questions ===\n" + res.get("out", "(pas fini)"))
            continue
        else:
            os.write(fd, cmd.encode() + b"\r")
        pump(wait)
    os.write(fd, b"exit\r"); pump(3)
    try: os.kill(pid, signal.SIGTERM)
    except OSError: pass
    print("=== parole ===")
    for line in open(LOG):
        ts, txt = line.rstrip("\n").split("\t", 1)
        print(f"+{float(ts)-t0:6.2f}s  {txt}")
    if os.environ.get("E2E_SHOW_OUT"):
        print("=== écran ===")
        print(out.decode("utf-8", "replace")[-3000:])
    spoken = open(LOG).read()
    missing = [e for e in EXPECT.get(name, []) if e not in spoken]
    if missing and os.environ.get("E2E_CHECK"):
        print("MANQUANT :", missing)
        if not os.environ.get("E2E_SHOW_OUT"):
            print(out.decode("utf-8", "replace")[-4000:])
        sys.exit(1)

run(sys.argv[1] if len(sys.argv) > 1 else "basic")
