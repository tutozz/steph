"""Cœurs occupés (somme, en cœurs) sur une liste de CPU, mesurés sur N secondes via /proc/stat."""
import sys, time
def snap():
    d = {}
    for l in open("/proc/stat"):
        if l.startswith("cpu") and l[3].isdigit():
            f = l.split(); v = list(map(int, f[1:])); d[int(f[0][3:])] = (sum(v), v[3] + v[4])
    return d
lo, hi, dur = int(sys.argv[1]), int(sys.argv[2]), float(sys.argv[3])
a = snap(); time.sleep(dur); b = snap()
busy = sum(1 - (b[c][1] - a[c][1]) / max(1, b[c][0] - a[c][0]) for c in range(lo, hi + 1))
print(f"{busy:.2f}")
