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

from . import setup, term_style, tui
from .config import CONFIG_PATH, Config
from .menu import Menu, split_keys

OSC_START = b"\x1b]6973;"
SHELL_DIR = Path(__file__).parent / "shell"
# écran alternatif : séquences suivies dans la sortie pour savoir si le
# programme enfant (vim, htop…) y était déjà quand le menu F6 s'ouvre
ALT_SCREEN_ON = (b"\x1b[?1049h", b"\x1b[?1047h", b"\x1b[?47h")
ALT_SCREEN_OFF = (b"\x1b[?1049l", b"\x1b[?1047l", b"\x1b[?47l")


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


def overlay_on() -> bytes:
    """Titre de fenêtre, pour voir d'un coup d'œil que la session parle. Pas de
    badge iTerm2 : l'aide des touches vit dans le menu F6 (voir menu.py)."""
    return b"\x1b[22;0t" + b"\x1b]0;steph\x07"


def overlay_off() -> bytes:
    """Restaure le titre d'origine et efface un badge iTerm2 qu'une version
    antérieure de steph aurait laissé (aucun n'est plus posé par overlay_on)."""
    return b"\x1b]1337;SetBadgeFormat=\x07\x1b[23;0t"


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
    def __init__(self, cfg: Config, narrator, socket_path: str, on_ask=None, help_keys: str = "",
                 menu_key: str = ""):
        self.cfg = cfg
        self.help_keys = help_keys
        self.menu_key = menu_key
        self.nar = narrator
        self.socket_path = socket_path
        self.on_ask = on_ask
        self.parser = MarkerParser()
        self._typed = ""
        self.keys = {
            cfg.key_menu.encode(): "menu",
            cfg.key_stop.encode(): "stop",
            cfg.key_repeat.encode(): "repeat",
            cfg.key_details.encode(): "details",
            cfg.key_ask.encode(): "ask",
            cfg.key_line_first.encode(): "first",
            cfg.key_line_prev.encode(): "prev",
            cfg.key_line_next.encode(): "next",
            cfg.key_line_last.encode(): "last",
        }
        # menu F6 : machine à états dans menu.py, le proxy applique parole/actions/réglages
        self.menu: Menu | None = None
        self._menu_line = False  # mode ligne : ajout seul, une ligne par événement (docs/tui-a11y.md)
        self._menu_alt = False  # écran alternatif ouvert pour le menu (jamais sous TERM=dumb)
        self.screen_reader = tui.screen_reader_active  # sondé à chaque ouverture : remplacé par les tests
        self._menu_out_buf = bytearray()
        self._child_pid: int | None = None
        self._child_alt_screen = False  # l'enfant (vim, htop…) était-il en écran alternatif ?
        self._is_tty = True  # écrasé par run() ; True par défaut pour les tests unitaires

    def _shell_argv(self) -> tuple[list[str], dict]:
        shell = os.environ.get("SHELL", "/bin/bash")
        name = os.path.basename(shell)
        env = dict(os.environ)
        env["STEPH_SOCKET"] = self.socket_path
        env["STEPH_SHELL_DIR"] = str(SHELL_DIR)
        env["STEPH_ACTIVE"] = "1"
        env["STEPH_MENU_KEY"] = self.menu_key
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

    def _rowscols(self) -> tuple[int, int]:
        rows, cols, _, _ = struct.unpack("HHHH", self._winsize())
        return (rows or 24, cols or 80)

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
        self._child_pid = pid
        from .ttyprobe import TtyProbe
        self.nar.tty_probe = TtyProbe(master, slave_name)

        def on_winch(*_):
            try:
                fcntl.ioctl(master, termios.TIOCSWINSZ, self._winsize())
                os.kill(pid, signal.SIGWINCH)
            except OSError:
                pass
            if self.menu is not None and not self._menu_line and os.isatty(stdout):
                rows, cols = self._rowscols()
                _write_all(stdout, self.menu.render(rows, cols))

        signal.signal(signal.SIGWINCH, on_winch)
        stdin = sys.stdin.fileno()
        stdout = sys.stdout.fileno()
        is_tty = os.isatty(stdin)
        self._is_tty = is_tty
        old = termios.tcgetattr(stdin) if is_tty else None
        if is_tty:
            tty.setraw(stdin)
        if os.isatty(stdout):
            _write_all(stdout, overlay_on())
        try:
            self._loop(master, stdin, stdout)
        finally:
            if os.isatty(stdout):
                _write_all(stdout, overlay_off())
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
                data = self._on_input(data, stdout)
                if data:
                    _write_all(master, data)

    def _on_output(self, data: bytes, stdout: int) -> None:
        for kind, val in self.parser.feed(data):
            if kind == "data":
                self._track_alt_screen(val)
                if self.menu is not None:
                    self._menu_out_buf += val
                else:
                    _write_all(stdout, val)
                c = self.nar.s.current
                if c is not None:
                    c.feed(val)
            else:
                self._on_marker(val)

    def _track_alt_screen(self, data: bytes) -> None:
        """Suivi simple par recherche de sous-chaînes : une séquence coupée entre
        deux read() (peu probable, mais possible) ne sera pas détectée."""
        last_on = max((data.rfind(seq) for seq in ALT_SCREEN_ON), default=-1)
        last_off = max((data.rfind(seq) for seq in ALT_SCREEN_OFF), default=-1)
        if last_on == -1 and last_off == -1:
            return
        self._child_alt_screen = last_on > last_off

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

    def _on_input(self, data: bytes, stdout: int | None = None) -> bytes:
        stdout = sys.stdout.fileno() if stdout is None else stdout
        if self.menu is not None:
            # menu ouvert : toute la frappe lui revient, rien n'est transmis au shell
            self._handle_menu_input(data, stdout)
            return b""
        self._track_typing(data)
        speaker = self._speaker()
        if speaker is not None:
            speaker.note_input()
        for seq, what in self.keys.items():
            if seq and seq in data:
                data = data.replace(seq, b"")
                if what == "menu":
                    self._open_menu(stdout)
                elif what == "ask":
                    if self.on_ask:
                        self.on_ask()
                else:
                    self.nar.on_key(what)
        return data

    # ------------------------------------------------------------ menu F6
    def _speaker(self):
        return getattr(self.nar, "speaker", None)

    def _open_menu(self, stdout: int) -> None:
        if not self._is_tty:
            return
        self.menu = Menu(self.cfg, help_text=self.help_keys, voices_dir=Path(self.cfg.voice).parent,
                         style=term_style.for_stream(sys.stdout))
        self._menu_out_buf = bytearray()
        mode, reason = tui.ui_mode(self.cfg.ui, os.environ, os.isatty(stdout), self.screen_reader)
        self._menu_line = mode == "line"
        self._menu_alt = os.isatty(stdout) and reason != "dumb"
        opening = self.menu.opening_announcement()
        speaker = self._speaker()
        if speaker is not None:
            speaker.say(opening, force=True)
        if os.isatty(stdout):
            # écran alternatif dans les deux modes : l'écran du shell reste intact ;
            # sous TERM=dumb, aucune séquence, le texte s'ajoute simplement
            if self._menu_line:
                start = tui.ENTER_SCREEN + "\x1b[H\x1b[2J" if self._menu_alt else "\r\n"
                lines = f"{start}{self.menu._t('menu.line_opening')}\r\n{opening}\r\n"
                _write_all(stdout, lines.encode())
            else:
                rows, cols = self._rowscols()
                _write_all(stdout, tui.ENTER_SCREEN.encode() + self.menu.render(rows, cols))

    def _handle_menu_input(self, data: bytes, stdout: int) -> None:
        speaker = self._speaker()
        for key in split_keys(data):
            result = self.menu.handle(key)
            if result.say and speaker is not None:
                speaker.say(result.say, force=True)
            if result.setting is not None:
                self._apply_setting(result.setting, speaker)
            is_tty = os.isatty(stdout)
            if self._menu_line and result.say and is_tty:
                _write_all(stdout, f"{result.say}\r\n".encode())
            if result.closed:
                self._close_menu(result.action, stdout)
                return
            # touche sans effet (lettre tapée par erreur…) : rien n'est écrit ; sinon
            # seulement ce qui a changé (un collage rapide pourrait remplir le tampon
            # du terminal et bloquer l'écriture si rien ne le lit)
            if is_tty and not self._menu_line:
                rows, cols = self._rowscols()
                update = self.menu.render_update(rows, cols)
                if update:
                    _write_all(stdout, update)

    def _apply_setting(self, setting: tuple[str, object], speaker) -> None:
        name, value = setting  # cfg déjà muté par le menu (même objet partagé)
        if speaker is not None:
            if name == "tts_enabled":
                speaker.enabled = value
            elif name == "voice":
                speaker.reload_voice(value)
            elif name == "speech_rate":
                speaker.set_rate(value)
        try:
            setup.save_settings(CONFIG_PATH, {name: value})
        except OSError:
            pass

    def _close_menu(self, action: str | None, stdout: int) -> None:
        self.menu = None
        buf, self._menu_out_buf = bytes(self._menu_out_buf), bytearray()
        if self._menu_alt and os.isatty(stdout):
            _write_all(stdout, b"\x1b[?25h\x1b[?1049l")
            if self._child_alt_screen and self._child_pid:
                # l'enfant (vim, htop…) était en écran alternatif : on y retourne
                # et on lui demande de se redessiner (best effort : certains
                # programmes ne repeignent que sur un vrai changement de taille)
                _write_all(stdout, b"\x1b[?1049h")
                try:
                    os.kill(self._child_pid, signal.SIGWINCH)
                except OSError:
                    pass
        # la sortie accumulée est de la vraie sortie shell : toujours relayée,
        # comme le fait _on_output en dehors du menu (pas seulement sur un tty)
        if buf:
            _write_all(stdout, buf)
        if action == "ask":
            if self.on_ask:
                self.on_ask()
        elif action:
            self.nar.on_key(action)
