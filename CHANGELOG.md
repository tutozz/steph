# Changelog

All notable changes to steph are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), versioning follows
[Semantic Versioning](https://semver.org/). Not released publicly yet
(`pyproject.toml` is at `0.1.0`); this file starts tracking from the open-source
compliance pass onward.

## [Unreleased]

### Added

- `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, `CLA.md`, issue and pull
  request templates.
- MIT `LICENSE` for `bench/matrix/finetune/` (training and corpus-preparation scripts),
  with SPDX headers on every script.
- `docs/model-card-draft.md`: draft Hugging Face model card for the `steph-speak` family
  (Apache 2.0), numeric fields pending the model's final training round.

### Changed

- The benchmark's public display name is now **Steph Speak Bench** (was TermSpeak) in
  every user-facing string: `benchmark/README.md`, `README.fr.md`, `CITATION.cff`,
  `data/croissant.json`, `data/README.md`, `run.py`, and the tools under
  `benchmark/tools/`. File paths, the `termspeak` canary string, and historical
  `results/*.json` records are unchanged (see `docs/open-source.md`).

### Notes on licensing (see `docs/open-source.md` for the full rationale)

- Fine-tuned model weights are planned to ship under Apache 2.0 (license of the Granite
  and Qwen bases used).
- The training dataset's license changes from CC BY-NC 4.0 to CC BY 4.0.
- Training scripts (`bench/matrix/finetune/`) ship under MIT, matching the benchmark
  code, so the trained model can qualify as Open Source AI (OSAID requires the training
  code itself under an OSI-approved license).
- steph itself (`src/`, `scripts/`, `site/`) stays under PolyForm Noncommercial 1.0.0 +
  commercial license; this changelog entry does not change that.

Everything above stays private: no publication, no remote repository, nothing pushed to
Hugging Face, PyPI, or a public GitHub org, until explicitly ordered (see the internal mission log (not published)).
