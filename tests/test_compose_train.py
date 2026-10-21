import hashlib
import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "bench/matrix/finetune/compose_train.py"


def row(user: str, label: str) -> dict:
    return {"source": "linux-dev", "messages": [
        {"role": "system", "content": "s"},
        {"role": "user", "content": user},
        {"role": "assistant", "content": label},
    ]}


def test_exclude_drops_judged_rows(tmp_path):
    users = [f"Commande : ls /tmp/dir{i}\nStatut : succès (code 0)\nSortie :\nfichier{i}" for i in range(4)]
    train = tmp_path / "train.jsonl"
    train.write_text("".join(json.dumps(row(u, "Succès.")) + "\n" for u in users))
    rejects = tmp_path / "rejects.txt"
    rejects.write_text("".join(hashlib.sha256(u.encode()).hexdigest() + "\n" for u in users[:2]))

    out = subprocess.run([sys.executable, str(SCRIPT), str(train), str(tmp_path / "mix"), "--exclude", str(rejects)],
                         capture_output=True, text=True, check=True).stdout

    kept = [json.loads(line)["messages"][1]["content"]
            for name in ("train", "val") for line in (tmp_path / "mix" / f"{name}.jsonl").open()]
    assert sorted(kept) == sorted(users[2:])
    assert "gardés 2" in out
    assert "'rejet juge': 2" in out
