"""Proxy PTY : lance le shell de l'utilisateur, relaie les octets, capte les marqueurs."""

from __future__ import annotations

import base64
import fcntl
import os
import select
import signal
import struct
import sys
import termios
import tty
from pathlib import Path

from .config import Config

OSC_START = b"\x1b]6973;"
SHELL_DIR = Path(__file__).parent / "shell"


def _b64(s: str) -> str:
    try:
        return base64.b64decode(s).decode("utf-8", "replace")
    except (ValueError, TypeError):
        return ""


def _write_all(fd: int, data: bytes) -> None:
    while data:
        try:
            n = os.write(fd, data)
        except InterruptedError:
            continue
        except BlockingIOError:
            select.select([], [fd], [])
            continue
        data = data[n:]


class MarkerParser:
    """Sépare le flux de sortie en (texte, marqueur, texte, …).

    Un marqueur peut être coupé entre deux read() : on garde la fin
    incomplète en tampon.
    """

    def __init__(self) -> None:
        self.buf = b""

    def feed(self, data: bytes):
        self.buf += data
        out = []
        while True:
            i = self.buf.find(OSC_START)
            if i < 0:
                # garder un éventuel début de marqueur coupé
                keep = 0
                for k in range(1, len(OSC_START)):
                    if self.buf.endswith(OSC_START[:k]):
                        keep = k
                if keep:
                    out.append(("data", self.buf[:-keep]))
                    self.buf = self.buf[-keep:]
                else:
                    out.append(("data", self.buf))
                    self.buf = b""
                break
            if i:
                out.append(("data", self.buf[:i]))
            j = self.buf.find(b"\x07", i)
            if j < 0:
                self.buf = self.buf[i:]
                if len(self.buf) > 1 << 16:  # marqueur corrompu
                    out.append(("data", self.buf))
                    self.buf = b""
                break
            body = self.buf[i + len(OSC_START):j].decode("ascii", "replace")
            out.append(("marker", body))
            self.buf = self.buf[j + 1:]
        return [x for x in out if x[0] == "marker" or x[1]]


class PtyProxy:
    def __init__(self, cfg: Config, narrator, socket_path: str, on_ask=None):
        self.cfg = cfg
        self.nar = narrator
        self.socket_path = socket_path
        self.on_ask = on_ask
        self.parser = MarkerParser()
        self._typed = ""
        self.keys = {
            cfg.key_stop.encode(): "stop",
            cfg.key_repeat.encode(): "repeat",
            cfg.key_details.encode(): "details",
            cfg.key_ask.encode(): "ask",
        }

    def _shell_argv(self) -> tuple[list[str], dict]:
        shell = os.environ.get("SHELL", "/bin/bash")
        name = os.path.basename(shell)
        env = dict(os.environ)
        env["STEPH_SOCKET"] = self.socket_path
        env["STEPH_SHELL_DIR"] = str(SHELL_DIR)
        env["STEPH_ACTIVE"] = "1"
        if name == "zsh":
            if "ZDOTDIR" in os.environ:
                env["STEPH_ORIG_ZDOTDIR"] = os.environ["ZDOTDIR"]
            zdot = Path(self.socket_path).with_suffix(".zdotdir")
            zdot.mkdir(parents=True, exist_ok=True)
            for f in ("zshenv", "zshrc"):
                target = zdot / f".{f}"
                target.unlink(missing_ok=True)
                target.symlink_to(SHELL_DIR / f)
            env["ZDOTDIR"] = str(zdot)
            return [shell, "-i"], env
        if name == "bash":
            return [shell, "--rcfile", str(SHELL_DIR / "bashrc"), "-i"], env
        # autre shell : pas de marqueurs, on fait au mieux
        return [shell, "-i"], env

    def _winsize(self) -> bytes:
        try:
            return fcntl.ioctl(sys.stdin.fileno(), termios.TIOCGWINSZ, b"\0" * 8)
        except OSError:
            return struct.pack("HHHH", 24, 80, 0, 0)

    def run(self) -> int:
        argv, env = self._shell_argv()
        # openpty + login_tty plutôt que pty.fork() : on connaît le nom du
        # terminal esclave (/dev/pts/N, /dev/ttysNNN) sur Linux comme sur macOS
        master, slave = os.openpty()
        slave_name = os.ttyname(slave)
        fcntl.ioctl(slave, termios.TIOCSWINSZ, self._winsize())
        pid = os.fork()
        if pid == 0:
            try:
                os.close(master)
                os.login_tty(slave)
                os.execvpe(argv[0], argv, env)
            finally:
                os._exit(127)
        os.close(slave)
        from .ttyprobe import TtyProbe
        self.nar.tty_probe = TtyProbe(master, slave_name)

        def on_winch(*_):
            try:
                fcntl.ioctl(master, termios.TIOCSWINSZ, self._winsize())
                os.kill(pid, signal.SIGWINCH)
            except OSError:
                pass

        signal.signal(signal.SIGWINCH, on_winch)
        stdin = sys.stdin.fileno()
        stdout = sys.stdout.fileno()
        is_tty = os.isatty(stdin)
        old = termios.tcgetattr(stdin) if is_tty else None
        if is_tty:
            tty.setraw(stdin)
        try:
            self._loop(master, stdin, stdout)
        finally:
            if old is not None:
                termios.tcsetattr(stdin, termios.TCSAFLUSH, old)
        _, status = os.waitpid(pid, 0)
        return os.waitstatus_to_exitcode(status)

    def _loop(self, master: int, stdin: int, stdout: int) -> None:
        stdin_open = True
        while True:
            fds = [master] + ([stdin] if stdin_open else [])
            try:
                r, _, _ = select.select(fds, [], [])
            except InterruptedError:
                continue
            if master in r:
                try:
                    data = os.read(master, 65536)
                except OSError:
                    return
                if not data:
                    return
                self._on_output(data, stdout)
            if stdin_open and stdin in r:
                data = os.read(stdin, 4096)
                if not data:
                    stdin_open = False
                    continue
                data = self._on_input(data)
                if data:
                    _write_all(master, data)

    def _on_output(self, data: bytes, stdout: int) -> None:
        for kind, val in self.parser.feed(data):
            if kind == "data":
                _write_all(stdout, val)
                c = self.nar.s.current
                if c is not None:
                    c.feed(val)
            else:
                self._on_marker(val)

    def _on_marker(self, body: str) -> None:
        parts = body.split(";")
        if parts[0] == "C" and len(parts) >= 2:
            self.nar.on_command_start(_b64(parts[1]))
        elif parts[0] == "D" and len(parts) >= 3:
            try:
                code = int(parts[1])
            except ValueError:
                code = -1
            self.nar.on_command_end(code, _b64(parts[2]))

    def _track_typing(self, data: bytes) -> None:
        """Garde la ligne en cours de frappe (approximative : sans les flèches)."""
        text = data.decode("utf-8", "ignore")
        i = 0
        while i < len(text):
            ch = text[i]
            if ch == "\x1b":  # séquence d'échappement (flèches…) : ignorée
                i += 1
                while i < len(text) and not text[i].isalpha() and text[i] != "~":
                    i += 1
            elif ch in "\r\n":
                if self.nar.s.current is not None:
                    self.nar.on_enter(self._typed)
                self._typed = ""
            elif ch in "\x7f\x08":
                self._typed = self._typed[:-1]
            elif ch in "\x03\x15":  # Ctrl+C, Ctrl+U
                self._typed = ""
            elif ch >= " ":
                self._typed += ch
            i += 1

    def _on_input(self, data: bytes) -> bytes:
        self._track_typing(data)
        for seq, what in self.keys.items():
            if seq and seq in data:
                data = data.replace(seq, b"")
                if what == "ask":
                    if self.on_ask:
                        self.on_ask()
                else:
                    self.nar.on_key(what)
        return data
