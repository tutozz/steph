# Contributing to steph

Thanks for taking the time to contribute. This repository mixes two licensing regimes,
so which rule applies depends on what you touch.

## Two zones, two rules

| Area | License | Contribution rule |
|---|---|---|
| `src/`, `scripts/`, `site/`, everything under the root `LICENSE.md` | PolyForm Noncommercial 1.0.0 + commercial license (`COMMERCIAL.md`) | **CLA required** (see `CLA.md`) |
| `benchmark/` (code and data) | MIT (`benchmark/LICENSE-CODE`) + CC BY 4.0 (`benchmark/LICENSE-DATA`) | DCO only (`Signed-off-by`), no CLA |
| `bench/matrix/finetune/` (training and corpus-preparation scripts) | MIT (`bench/matrix/finetune/LICENSE`) | DCO only, no CLA |

steph itself is sold under a separate commercial license (`COMMERCIAL.md`). A patch
received under PolyForm Noncommercial cannot be resold commercially without the
contributor's explicit agreement, so any contribution touching the steph product code
requires signing the CLA once (see `CLA.md`). Contributions to the benchmark or the
training scripts are Apache/MIT-style permissive: a Developer Certificate of Origin
sign-off is enough, "inbound = outbound".

## Before you open a pull request

1. **Sign the CLA** if your change touches anything outside `benchmark/` and
   `bench/matrix/finetune/`. See `CLA.md` for the text and how to sign.
2. **Add a `Signed-off-by` line** (`git commit -s`) on every commit, everywhere in the
   repository. This is required even when the CLA also applies.
3. **Tests first.** This project follows TDD: a failing test before the fix, then the
   minimal change to make it pass. Run the targeted test file during development, the
   full suite before opening the PR:
   ```
   uv run pytest tests/<the file you touched>.py
   uv run pytest -q tests
   ```
4. **Benchmark changes** additionally require:
   ```
   python3 benchmark/tools/validate.py
   python3 benchmark/tools/build_dataset.py --check
   ```
   and a PII scanner report of zero findings for any new real-anonymized case (see
   `benchmark/README.md`, section Anonymization).
5. **No unsolicited refactors.** Fix what's asked; keep the diff minimal and readable.
6. **French accents stay on.** Comments, commit messages, and user-facing strings in
   French keep their accents; code identifiers stay in English.

## Reporting a security issue

Do not open a public issue for a vulnerability. See `SECURITY.md`.

## Code of conduct

This project follows the `CODE_OF_CONDUCT.md` (Contributor Covenant 2.1).

## Submitting a benchmark result

The benchmark (`benchmark/`) has its own submission procedure, kept close to the code it
concerns: see `benchmark/CONTRIBUTING.md` and the "Submit a result" section of
`benchmark/README.md`.

## Governance

Single maintainer (BDFL) at this stage: Luis Parra. Decisions on what enters the
benchmark, the training scripts, or the product code are made by the maintainer; this
document is updated if that changes.
