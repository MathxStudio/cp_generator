# Contributing

## Development setup

1. Install `uv`.
2. Clone the repository and enter the project root.
3. Run `uv sync --all-groups`.
4. Start the desktop app with `uv run cp-generator`.

On Linux, install `libcairo2` and `python3-tk` first. For Android work, use Python 3.10 for Chaquopy builds.

## Before opening a PR

Run the same checks that CI enforces:

```bash
uv run python -m unittest discover -s tests -t . -q
uv run cp-generator-diagnostics --fail-on-mismatch
python -m py_compile \
  src/cp_generator/app.py \
  src/cp_generator/mobile_api.py \
  src/cp_generator/workflow.py \
  src/cp_generator/exact_checker.py \
  src/cp_generator/validation_corpus.py \
  src/cp_generator/diagnostics_cli.py
```

If you change Android code, also run the Gradle debug-quality path from `android-app/`:

```bash
gradle :app:lintDebug :app:testDebugUnitTest :app:assembleDebug
```

## Change discipline

- Keep changes small and reviewable.
- Add or update tests for behavior changes.
- Preserve `.cpfold.json` compatibility unless a migration plan is documented first.
- Prefer shared workflow/core changes over duplicating logic in desktop and mobile layers.
- Do not publish unsigned or debug Android APKs as stable release assets.

## Branches and commits

- Branch from `main`.
- Use descriptive commit messages such as `fix: reject near-degenerate all-green results`.
- Open PRs against `main`.

## Mathematical quality bar

For automation features, a result is not “good” merely because the badges are green. Near-degenerate sheets should be rejected and retried until the geometry is generic enough to be meaningful.
