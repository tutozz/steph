"""Marqueurs OSC 6973 de l'intégration bash : un D à chaque invite, un C seulement
pour la commande tapée, jamais pendant le rendu de l'invite."""

import base64
import os
import pty
import re
import select
import shutil
import time
from pathlib import Path

import pytest

BASHRC = Path(__file__).resolve().parents[1] / "src" / "steph" / "shell" / "bashrc"
MARKER = re.compile(rb"\x1b\]6973;([CD]);([^\x07]*)\x07")


def drive(bash: str, home: Path, commands: list[str]) -> list[tuple[str, str]]:
    env = {"HOME": str(home), "PATH": "/usr/bin:/bin", "TERM": "xterm", "STEPH_MENU_KEY": "F6"}
    pid, fd = pty.fork()
    if pid == 0:
        os.execve(bash, [bash, "--rcfile", str(BASHRC), "-i"], env)
    out = bytearray()

    def pump(seconds: float) -> None:
        end = time.time() + seconds
        while time.time() < end:
            if select.select([fd], [], [], 0.1)[0]:
                try:
                    out.extend(os.read(fd, 65536))
                except OSError:
                    return

    pump(1.5)
    for cmd in commands:
        os.write(fd, cmd.encode() + b"\r")
        pump(0.8)
    os.write(fd, b"exit\r")
    pump(0.5)
    os.waitpid(pid, 0)
    return [(k.decode(), base64.b64decode(v).decode() if k == b"C" else v.decode()) for k, v in MARKER.findall(bytes(out))]


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash absent")
def test_bash_emits_command_marker_only_for_typed_commands(tmp_path):
    marks = drive(shutil.which("bash"), tmp_path, ["echo hi", "cd /tmp"])
    kinds = [k for k, _ in marks]
    commands = [v for k, v in marks if k == "C"]
    assert commands[:2] == ["echo hi", "cd /tmp"]  # pas de C fantôme avant la première commande
    assert kinds[0] == "D"
    assert all(a != b for a, b in zip(kinds, kinds[1:]))  # alternance stricte D, C, D, C...
