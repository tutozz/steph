# Contributing to Steph Speak Bench

This folder (code and data) is permissively licensed on purpose: MIT for the code
(`LICENSE-CODE`), CC BY 4.0 for the data (`LICENSE-DATA`); so it can be reused, including
commercially, independently of the rest of the steph repository (PolyForm Noncommercial,
see the root `CONTRIBUTING.md`). Contributions here only need a Developer Certificate of
Origin sign-off (`git commit -s`), no CLA.

## Submitting a leaderboard result

See "Submit a result" in [README.md](README.md#submit-a-result) for the full checklist.
Short version:

1. Run the `test` split, both languages, with an unmodified `data/v1` (the result file
   records its own checksums).
2. Keep the default protocol, or document every deviation in `--notes`.
3. Open a pull request adding your `results/*.json` files, or use the
   [result issue template](../.github/ISSUE_TEMPLATE/benchmark_result.md) if you cannot
   open a PR.
4. Never tune on `test`. Tune on `dev`.

## Adding or changing a case

- `data/v1` is frozen once released: a correction ships as `data/v2` with a changelog
  entry, never as a silent edit. Open an issue first to discuss whether a change belongs
  in the next version.
- New synthetic cases go through `tools/cases/*.py`, rebuilt with
  `python3 tools/build_dataset.py`.
- Real-anonymized cases must pass the PII scanner
  (`bench/matrix/finetune/audit_pii.py`) with zero findings before submission.
- Run `python3 tools/validate.py` and `python3 tools/build_dataset.py --check` before
  opening a pull request.

## Questions

Open an issue, or see the root [CONTRIBUTING.md](../CONTRIBUTING.md) for anything that is
not specific to the benchmark.
