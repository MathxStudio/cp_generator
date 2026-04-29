# CP Generator

A desktop application for generating, optimizing, and animating origami crease patterns. Starting from a random point set, it builds a Delaunay candidate graph, enforces local flat-fold conditions (Kawasaki and Maekawa), assigns mountain/valley folds, and renders a live animated 3D fold preview — all inside a single Tkinter window.

![Example output](result.jpg)

---

## Table of Contents

- [Run from source](#run-from-source)
- [Run a pre-built portable bundle](#run-a-pre-built-portable-bundle)
- [Build portable bundles via GitHub Actions](#build-portable-bundles-via-github-actions)
- [Download artifacts with the helper script](#download-artifacts-with-the-helper-script)
- [Windows launcher](#windows-launcher)
- [Features](#features)
- [Session files](#session-files)
- [Project layout](#project-layout)
- [Report](#report)

---

## Run from source

**Recommended — using [uv](https://docs.astral.sh/uv/):**

```bash
# install uv once (if you don't have it)
curl -LsSf https://astral.sh/uv/install.sh | sh   # macOS / Linux
# or: powershell -c "irm https://astral.sh/uv/install.ps1 | iex"  # Windows

# clone and run (uv resolves Python 3.14 + deps automatically)
git clone https://github.com/MathxStudio/cp_generator.git
cd cp_generator
uv run main.py
```

**Manual Python install (Python ≥ 3.14 required):**

```bash
pip install numpy scipy svgwrite cairosvg
python main.py
```

> **Linux note:** `cairosvg` requires the system `libcairo2` library.
> Install it with `sudo apt-get install libcairo2` (Debian/Ubuntu) or the
> equivalent for your distribution. Tkinter must also be present:
> `sudo apt-get install python3-tk`.

> **macOS note:** `cairosvg` requires cairo from Homebrew:
> `brew install cairo`.

---

## Run a pre-built portable bundle

Pre-built bundles are attached as artifacts to every GitHub Actions run.
They require **no Python installation** — just download, extract, and launch.

1. Go to **Actions** → **portable-build** on the repository page.
2. Click the most recent successful run.
3. Under **Artifacts**, download the archive for your platform:
   - `CPGenerator-linux.tar.gz` → Linux x86-64
   - `CPGenerator-windows.zip` → Windows x86-64
   - `CPGenerator-macos.zip` → macOS (arm64 / x86-64 depending on runner)
4. Extract and run:

   ```bash
   # Linux
   tar -xzf CPGenerator-linux.tar.gz
   ./CPGenerator/CPGenerator

   # macOS
   unzip CPGenerator-macos.zip
   ./CPGenerator/CPGenerator

   # Windows — open CPGenerator\ and double-click CPGenerator.exe
   ```

> **macOS Gatekeeper:** the first launch may be blocked because the bundle
> is unsigned. Right-click the binary → **Open** → **Open** to allow it, or run:
> `xattr -d com.apple.quarantine CPGenerator/CPGenerator`

---

## Build portable bundles via GitHub Actions

The workflow file is `.github/workflows/portable-build.yml`. It runs
automatically on every push to `main` or `master`, and can also be triggered
manually.

### Trigger manually (no code push needed)

**Via the GitHub web UI:**

1. Go to **Actions** → **portable-build** → **Run workflow**.
2. Select the branch (default: `main`) and click **Run workflow**.
3. Refresh the page after a few seconds to see the run appear.
4. Wait for all three matrix jobs (Linux, Windows, macOS) to complete — usually
   5–10 minutes in total.
5. Click the completed run, then scroll to **Artifacts** to download.

**Via the GitHub CLI (`gh`):**

```bash
# trigger and wait (requires gh auth login)
gh workflow run portable-build.yml --repo MathxStudio/cp_generator

# watch progress
gh run list --workflow portable-build.yml --repo MathxStudio/cp_generator --limit 1
gh run watch <RUN_ID> --repo MathxStudio/cp_generator
```

### What the workflow does

| Step | Detail |
|---|---|
| **System deps** | Installs `libcairo2` + `python3-tk` on Linux; `cairo` via Homebrew on macOS |
| **Python** | Sets up Python 3.14 via `actions/setup-python` |
| **uv** | Installs [uv](https://docs.astral.sh/uv/) and runs `uv sync --all-groups` to pin exact dependency versions from `uv.lock` |
| **PyInstaller** | Freezes the app into a self-contained `dist/CPGenerator/` directory with `--onedir --windowed` |
| **Archive** | Packs the directory into a platform-appropriate archive |
| **Upload** | Attaches the archive as a GitHub Actions artifact (retained for 30 days) |

---

## Download artifacts with the helper script

`scripts/package_portable.sh` automates the trigger-wait-download cycle using
the `gh` CLI.

```bash
# prerequisites: gh must be authenticated (gh auth login)
bash scripts/package_portable.sh
```

The script:
1. Triggers the `portable-build` workflow.
2. Waits for it to finish (streams live progress).
3. Downloads all three platform archives into `portable-dist/` in the current
   directory.

---

## Windows launcher

`Start_App.bat` provides a zero-install launch path on Windows without needing
a pre-built bundle. Double-click it from the project folder:

1. If `uv.exe` is not present, it downloads the standalone uv binary
   automatically.
2. It calls `uv run main.py`, which fetches Python 3.14 and all dependencies
   on first run (requires an internet connection the first time only).
3. On subsequent runs it starts immediately from the local cache.

---

## Features

- Random crease-pattern generation inside a square sheet
- Geometry optimization with Kawasaki-style alternating-angle constraints (SLSQP)
- Exhaustive mountain/valley assignment search with Maekawa filtering
- Bern–Hayes-style local reduction to minimize the combinatorial search space
- Live animated 3D fold preview with kinematic face rotation
- SVG and PNG export
- Session save/load (`.cpfold.json`)

---

## Session files

Use the **Save** and **Load** buttons in the left panel to persist and restore:

- crease geometry and vertex positions
- mountain/valley assignments
- preview-ready fold state
- UI toggles (labels, loop playback)

Loading a saved session in a fresh launch fully restores the crease sheet and
rebuilds the folded preview.

---

## Project layout

```
cp_generator/
├── main.py                  # entrypoint
├── cp_gen.py                # Tkinter GUI and user interactions
├── cp.py                    # crease-pattern graph, optimization, MV assignment, export
├── fold_sim.py              # 3D fold preview pipeline
├── pyproject.toml           # project metadata and dependency declarations
├── uv.lock                  # exact locked dependency versions
├── requirements.txt         # pip-compatible dependency list
├── Start_App.bat            # Windows zero-install launcher
├── scripts/
│   └── package_portable.sh  # trigger CI build and download artifacts
├── .github/
│   └── workflows/
│       └── portable-build.yml  # CI matrix build (Linux / Windows / macOS)
└── report/
    ├── crease_pattern_methods.tex  # LaTeX source (Beamer presentation)
    └── crease_pattern_methods.pdf  # compiled presentation
```

---

## Report

`report/crease_pattern_methods.tex` is a concise Beamer presentation covering
the four algorithms: graph construction, parity repair and Kawasaki
optimization, mountain/valley assignment, and 3D animation.

Build the PDF locally (requires a TeX distribution with XeLaTeX and
`beamer`/`metropolis`):

```bash
cd report
latexmk -xelatex -interaction=nonstopmode crease_pattern_methods.tex
```
