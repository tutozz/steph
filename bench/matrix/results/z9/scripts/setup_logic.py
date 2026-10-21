import json
from steph.config import load_config
from steph import setup, speed
from steph.catalog import detect_tier, load_catalog
from steph.catalog import detect_machine
m = detect_machine()
print("machine", m)
print("tier", detect_tier(load_catalog(), m))
cfg = load_config(apply_profile=True)
models, lines = setup._setup_llm(cfg, print)
for x in models:
    print(x.id if hasattr(x, "id") else x.label, "recommended=", x.recommended, "tps=", x.prompt_tokens_per_sec, "path_present=", __import__("pathlib").Path(x.path).is_file())
print("\n".join(lines))
