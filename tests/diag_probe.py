"""Diagnostic : que montre le système pour un programme qui attend le clavier ?"""
import os, pty, subprocess, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from steph.ttyprobe import TtyProbe

CASES = {
    "python input()": [sys.executable, "-c", "input('nom ')"],
    "python stdin.read": [sys.executable, "-c", "import sys; sys.stdin.read(1)"],
    "cat": ["cat"],
    "bash read": ["bash", "-c", "read x"],
    "sleep (occupé)": ["sleep", "5"],
}
for name, argv in CASES.items():
    master, slave = os.openpty()
    sname = os.ttyname(slave)
    pid = os.fork()
    if pid == 0:
        os.close(master); os.login_tty(slave); os.execvp(argv[0], argv)
    os.close(slave)
    time.sleep(1.5)
    pg = os.getpgid(pid)
    ps = subprocess.run(["ps", "-A", "-o", "pid=,pgid=,stat=,wchan=,comm="], capture_output=True, text=True).stdout
    rows = [l for l in ps.splitlines() if l.split()[1:2] == [str(pg)]]
    print(f"{name:20} probe={TtyProbe(master, sname).waiting_for_input()}  ps={rows}")
    os.kill(pid, 9); os.waitpid(pid, 0); os.close(master)
