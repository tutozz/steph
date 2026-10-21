---
name: Steph Speak Bench result
about: Submit a new leaderboard result for benchmark/
title: "[bench result] <model> on <hardware>"
labels: benchmark
---

<!-- For a pull request adding results/*.json directly, use this template to describe it
     instead: PRs are the preferred path (see benchmark/README.md, "Submit a result"). -->

## Model

- Name and size:
- Base model and license:
- Quantization:
- Source (Hugging Face repo, or how you built the GGUF):

## Backend

- Runner (llama.cpp, Ollama, LM Studio, other OpenAI-compatible server):
- Version / build:
- Command used to launch the server:

## Hardware

- CPU / GPU:
- RAM / VRAM:
- OS:

## Protocol

- [ ] Ran the `test` split, both languages, with an unmodified `data/v1` (checksums are
      recorded automatically in the result file).
- [ ] Used the default prompt and settings, or described every change in `--notes`.
- [ ] Never tuned on `test`.

## Files

<!-- Attach or link the result JSON files (benchmark/results/*.json) produced by
     `benchmark/run.py`. If you cannot open a pull request, paste them here instead. -->
