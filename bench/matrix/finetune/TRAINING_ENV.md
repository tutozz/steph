# Training environment

Reproducibility gap 6 of `docs/open-source.md`: the training environment (this repository's
own `uv.lock` only covers the steph application, not the lab machines' training venvs).
This file is the dedicated place for it, kept separate from `pyproject.toml` on purpose.

## What the scripts actually import

Confirmed by reading `bench/matrix/finetune/train_lora.py`, `pref/train_dpo.py`,
`vocab/granite_*.py` (2026-09-27):

| Package | Used for | Evidence |
|---|---|---|
| `torch` | tensors, training loop | `train_lora.py`, `pref/train_dpo.py`, `vocab/granite_rebuild_soup.py`, `pref/merge_pref.py` |
| `transformers` | model and tokenizer loading; `transformers.models.granitemoehybrid` specifically, for Granite 4.0 H's hybrid Mamba/attention architecture | `pref/train_dpo.py:25,74`, `train_lora.py:309,338`, `vocab/granite_verify.py`, `vocab/granite_token_ids.py` |
| `peft` | LoRA adapters (`LoraConfig`, `get_peft_model`, `PeftModel`) | `pref/train_dpo.py:97`, `train_lora.py:308` |
| `safetensors` | loading merged/soup weights | `pref/train_dpo.py:24` |
| `jinja2` | rendering the chat template outside a server, for tokenizer checks | `vocab/collect.py` |

## Not directly imported here, but named in the mission's dependency list

the internal mission log (not published) and this task's brief also name **`trl`**, **`mamba_ssm`** and
**`causal_conv1d`**. Grepping every script in this repository (`bench/matrix/finetune/`,
recursively) on 2026-09-27 found no `import trl`, `import mamba_ssm` or
`import causal_conv1d`: the DPO loop in `pref/train_dpo.py` is hand-rolled on top of
`torch`/`transformers`/`peft`, not `trl.DPOTrainer`. `mamba_ssm` and `causal_conv1d` are
plausible transitive requirements of `transformers.models.granitemoehybrid` (Granite 4.0 H
is a hybrid Mamba/attention model; the CUDA kernels usually come from these two packages),
but that is inferred from the architecture, not confirmed by an import statement in this
repository.

**Consequence: this file cannot state exact version numbers without inventing them.**
They live only in each lab machine's virtual environment (`venv/` under
`bench/matrix/finetune/`, per `capture_corpus.py` and `sync.sh`), never committed here.

## How to fill this in

On each machine that actually trains (see the internal mission log (not published) for which ones), run:

```
venv/bin/pip freeze | grep -iE '^(torch|transformers|peft|trl|mamba-ssm|causal-conv1d|safetensors|jinja2|accelerate|bitsandbytes)=='
```

and paste the result below, one block per machine, so a version drift between machines is
visible instead of silently assumed identical.

<!-- pip-freeze:start -->
| Machine | torch | transformers | peft | trl | mamba_ssm | causal_conv1d |
|---|---|---|---|---|---|---|
| <à remplir> | <à remplir> | <à remplir> | <à remplir> | <à remplir> | <à remplir> | <à remplir> |
<!-- pip-freeze:end -->

## Other reproducibility elements already tracked

| Element | Where |
|---|---|
| Seeds | `42, 7, 123, 2024` (SFT soup), `--seed 42` default in `benchmark/run.py` |
| Training system prompt | `train_system_prompt.txt`, `train_system_prompt.en.txt` |
| GGUF conversion | manual, llama.cpp version not yet recorded (gap 6 continues: see `docs/open-source.md`) |
| Recipe (rank, alpha, lr, epochs) | `docs/model-card-draft.md`, section "Recette d'entraînement" |
