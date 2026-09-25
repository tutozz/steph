"""Le programme au premier plan attend-il une saisie clavier ?

On regarde les processus du groupe au premier plan du PTY : si l'un d'eux est
bloqué dans read() sur le terminal (/proc/<pid>/syscall), il attend l'utilisateur.
Bien plus fiable que de deviner à partir du texte affiché.
"""

from __future__ import annotations

import os

READ_SYSCALLS = {"0", "17", "19", "295"}  # read, pread64, readv, preadv (x86_64)
POLL_SYSCALLS = {"7", "23", "270", "271", "232", "281", "441"}  # poll, select, pselect6, ppoll, epoll_wait, epoll_pwait, epoll_pwait2


class TtyProbe:
    def __init__(self, master_fd: int, slave_name: str):
        self.master = master_fd
        self.slave = slave_name

    def _fg_pids(self) -> list[int]:
        try:
            pgid = os.tcgetpgrp(self.master)
        except OSError:
            return []
        pids = []
        for d in os.listdir("/proc"):
            if not d.isdigit():
                continue
            try:
                with open(f"/proc/{d}/stat") as f:
                    stat = f.read()
                fields = stat[stat.rindex(")") + 2:].split()
                if int(fields[2]) == pgid:
                    pids.append(int(d))
            except (OSError, ValueError, IndexError):
                continue
        return pids

    def waiting_for_input(self) -> bool | None:
        """True : lit le terminal ; False : occupé ; None : impossible à savoir."""
        pids = self._fg_pids()
        if not pids:
            return None
        unknown = False
        for pid in pids:
            try:
                with open(f"/proc/{pid}/syscall") as f:
                    parts = f.read().split()
            except OSError:
                unknown = True
                continue
            if not parts or parts[0] == "running":
                continue
            nr = parts[0]
            if nr in READ_SYSCALLS and len(parts) > 1:
                try:
                    fd = int(parts[1], 16)
                    target = os.readlink(f"/proc/{pid}/fd/{fd}")
                except (OSError, ValueError):
                    continue
                if target == self.slave or target == "/dev/tty":
                    return True
        return None if unknown else False
