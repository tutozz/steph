## What and why

<!-- One or two sentences: what changes, and the reason. -->

## Checklist

- [ ] Tests added or updated, and green: `uv run pytest -q tests`
- [ ] If this touches `src/`, `scripts/`, `site/`, or anything else outside `benchmark/`
      and `bench/matrix/finetune/`: I have signed the CLA (`CLA.md`), or already have.
- [ ] Every commit has a `Signed-off-by` line (`git commit -s`).
- [ ] No unrelated refactor bundled in.

### If this changes `benchmark/data/`

- [ ] `python3 benchmark/tools/validate.py` passes.
- [ ] `python3 benchmark/tools/build_dataset.py --check` reports 0 problems.
- [ ] New real-anonymized cases pass the PII scanner with 0 findings
      (`bench/matrix/finetune/audit_pii.py`).
- [ ] `python3 benchmark/tools/leaderboard.py --update-readme` was run if scores moved.

### If this adds a `benchmark/results/*.json` submission

- [ ] Produced by an unmodified `data/v1` (see the "Submit a result" checklist in
      `benchmark/README.md`).
- [ ] Never tuned on the `test` split.
