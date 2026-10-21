"""Un jeu de données Hugging Face vit sous /datasets/ : sans ce segment, le lien public répond 404."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATASETS = ("steph-speak-bench", "steph-speak-train")
PUBLIC = ["README.md", "README.fr.md", "site/public/index.html", "site/public/en/index.html",
          *[str(p.relative_to(ROOT)) for p in ROOT.glob("release/hf/*/README.md")]]


def test_dataset_links_carry_the_datasets_segment():
    bad = []
    for name in PUBLIC:
        text = (ROOT / name).read_text()
        for m in re.finditer(r"huggingface\.co/([\w-]+)/(" + "|".join(DATASETS) + r")\b", text):
            if m.group(1) != "datasets":
                bad.append(f"{name}: {m.group(0)}")
    assert not bad, bad
