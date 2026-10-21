"""Turn the labeled files pulled from the GPUs into the audited training set.

    python3 finalize_labels.py labeled/raw labeled

Keeps only what training needs (source, messages), gives each machine a neutral source name,
drops rows the anonymization scanner still flags, and writes one train.jsonl for all sources.

SPDX-License-Identifier: MIT
"""

import json
import os
import sys
from pathlib import Path

from audit_pii import DEFAULT_NAMES, load_names, scan_text

# Raw file names can carry real host names: their neutral names live outside the repo.
SOURCES_FILE = Path(os.environ.get("STEPH_LABEL_SOURCES", Path.home() / ".config/steph/label_sources.json"))
SOURCES = json.loads(SOURCES_FILE.read_text()) if SOURCES_FILE.exists() else {}


def main(raw_dir: Path, out_dir: Path) -> None:
    names = load_names(os.environ.get("STEPH_PII_NAMES", DEFAULT_NAMES))
    out_dir.mkdir(parents=True, exist_ok=True)
    train, dropped = [], 0
    for f in sorted(raw_dir.glob("*.jsonl")):
        # skip bookkeeping files and outputs of an earlier run pulled back from a labeler
        if f.stem == "train" or f.stem.endswith(".rejects") or f.stem in SOURCES.values():
            continue
        source = SOURCES.get(f.stem, f.stem)
        rows = []
        for line in f.open():
            row = json.loads(line)
            messages = row.get("train_messages") or row["messages"]
            if scan_text("\n".join(m["content"] for m in messages), names):
                dropped += 1
                continue
            rows.append({"source": source, "messages": messages})
        with (out_dir / f"{source}.jsonl").open("w") as out:
            out.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
        train += rows
        print(f"{source} : {len(rows)} lignes")
    with (out_dir / "train.jsonl").open("w") as out:
        out.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in train)
    print(f"train.jsonl : {len(train)} lignes, {dropped} écartée(s) par le scanner")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
