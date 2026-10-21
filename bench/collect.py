import json, subprocess, time, os
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PROJ = os.path.dirname(REPO)
cmds = [c.replace("{REPO}", REPO).replace("{PROJ}", PROJ) for c in [
 "ls -la /etc | head -40",
 "df -h",
 "git -C {REPO} status",
 "cat /nonexistent/file.txt",
 "python3 -c 'import json; d={}; print(d[\"key\"])'",
 "ping -c 3 127.0.0.1",
 "gcc -x c - -o /dev/null <<< 'int main(){ int x = ; return 0; }'",
 "free -h",
 "systemctl --user status pipewire --no-pager | head -20",
 "grep -rn 'def ' {REPO}/src/steph/llm.py",
 "curl -qsS https://nonexistent.invalid/",
 "ip -br addr",
 "ls {REPO}",
 "uname -a",
 "python3 -m pip --version",
 "find /usr/share/doc -maxdepth 1 -name 'py*' | head -20",
 "ssh -o BatchMode=yes -o ConnectTimeout=3 nobody@127.0.0.1 true",
 "rm /etc/hostname",
 "sort /etc/passwd | cut -d: -f1 | head -30",
 "du -sh {PROJ}/* 2>/dev/null | sort -h | tail",
 "dnf check-update --cacheonly 2>&1 | tail -30",
 "tar czf /tmp/x.tgz /nonexistent",
 "docker ps",
 "whoami",
]]
out = []
for c in cmds:
    t = time.time()
    p = subprocess.run(["bash", "-c", c], capture_output=True, text=True)
    out.append({"cmd": c, "exit": p.returncode, "duration": round(time.time()-t, 2),
                "output": (p.stdout + p.stderr)[:20000]})
json.dump(out, open("fixtures.json", "w"), ensure_ascii=False, indent=1)
for o in out: print(o["exit"], len(o["output"]), o["cmd"])

# Attention : fixtures.json contient alors des infos de TA machine (IP, projets…) : à anonymiser avant publication.
