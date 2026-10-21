"""`sync.sh qa`: fetch the P15a question file, audit it with the private name list, push it to every trainer.

ssh and sshpass are stubbed: nothing leaves the machine.
"""

import json
import os
import subprocess
import tarfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "bench/matrix/finetune/sync.sh"

SSH_STUB = """#!/bin/bash
host=$1; shift
cmd="$*"
if [[ "$cmd" == cat\\ * ]]; then cat "$FAKE_QA"; exit 0; fi
n=$(ls "$CALLS" | wc -l | tr -d ' ')
echo "$host|$cmd" > "$CALLS/$n.cmd"
cat > "$CALLS/$n.tar"
"""

SSHPASS_STUB = """#!/bin/bash
# sshpass -p root ssh -o PubkeyAuthentication=no host cmd
shift 2; shift; shift 2
exec ssh "$@"
"""


def run_sync(tmp_path, qa_text, names):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in (("ssh", SSH_STUB), ("sshpass", SSHPASS_STUB)):
        stub = bin_dir / name
        stub.write_text(body)
        stub.chmod(0o755)
    calls = tmp_path / "calls"
    calls.mkdir()
    fake_qa = tmp_path / "remote_qa.jsonl"
    fake_qa.write_text(qa_text)
    names_file = tmp_path / "names.tsv"
    if names is not None:
        names_file.write_text(names)
    hosts = tmp_path / "hosts.sh"
    hosts.write_text('LABELERS=("vault:/v/data")\n'
                     'TRAINERS=("${LABELERS[@]}" "root@gpu:/g/data")\n'
                     'PASSWORD_HOSTS=("root@gpu")\n')
    env = dict(os.environ, PATH=f"{bin_dir}:{os.environ['PATH']}", CALLS=str(calls), FAKE_QA=str(fake_qa),
               STEPH_LAB_HOSTS=str(hosts), STEPH_PII_NAMES=str(names_file),
               STEPH_QA_DIR=str(tmp_path / "local"))
    result = subprocess.run(["bash", str(SCRIPT), "qa"], env=env, capture_output=True, text=True)
    return result, calls, tmp_path / "local"


def qa_row(text):
    return json.dumps({"source": "qa", "_key": "k", "messages": [{"role": "user", "content": text},
                                                                 {"role": "assistant", "content": "Pas dans l'historique."}]}) + "\n"


def test_clean_file_is_pushed_to_every_trainer_final_dir(tmp_path):
    result, calls, local = run_sync(tmp_path, qa_row("Commande : ls\nSortie :\na.txt"), "zorglub-host\tmachine\n")
    assert result.returncode == 0, result.stderr
    assert (local / "qa_train.jsonl").read_text() == qa_row("Commande : ls\nSortie :\na.txt")
    pushed = sorted((calls / f).read_text().strip() for f in os.listdir(calls) if f.endswith(".cmd"))
    assert pushed == ["root@gpu|mkdir -p /g/data/final && tar xf - -C /g/data/final",
                      "vault|mkdir -p /v/data/final && tar xf - -C /v/data/final"]
    for tar_path in calls.glob("*.tar"):
        with tarfile.open(tar_path) as tar:
            assert tar.getnames() == ["qa_train.jsonl"]


def test_private_name_in_messages_blocks_every_push(tmp_path):
    result, calls, _ = run_sync(tmp_path, qa_row("ssh zorglub-host uptime"), "zorglub-host\tmachine\n")
    assert result.returncode != 0
    assert not list(calls.glob("*.cmd"))


def test_missing_private_name_list_blocks_every_push(tmp_path):
    result, calls, _ = run_sync(tmp_path, qa_row("ls"), None)
    assert result.returncode != 0
    assert "liste de noms introuvable" in result.stderr
    assert not list(calls.glob("*.cmd"))
