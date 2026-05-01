# CP Generator

A desktop application for generating, optimizing, and animating origami crease patterns. Starting from a random point set, it builds a Delaunay candidate graph, enforces local flat-fold conditions (Kawasaki and Maekawa), assigns mountain/valley folds, and renders a live animated 3D fold preview — all inside a single Tkinter window.

![Example output](assets/images/result.jpg)

> **Credits:** `assets/images/box_head.png` is reconstructed from **"Box Head – 16×16 Grid"** by
> **Boice** (Origami by Boice), designed for the East Bay Origami Convention 2024.
> [Source](https://www.obb.design/crease-patterns/box-head---16x16-grid)

---

## Table of Contents

- [Run from source](#run-from-source)
- [Run a pre-built portable bundle](#run-a-pre-built-portable-bundle)
- [Build artifacts via GitHub Actions](#build-artifacts-via-github-actions)
- [Download artifacts with the helper script](#download-artifacts-with-the-helper-script)
- [Windows launcher](#windows-launcher)
- [Features](#features)
- [Session files](#session-files)
- [Project layout](#project-layout)
- [Android app](#android-app)
- [Report](#report)

---

## Run from source

**Recommended — using [uv](https://docs.astral.sh/uv/):**

```bash
# install uv once (if you don't have it)
curl -LsSf https://astral.sh/uv/install.sh | sh   # macOS / Linux
# or: powershell -c "irm https://astral.sh/uv/install.ps1 | iex"  # Windows

# clone and run from the project root (uv resolves Python 3.14 + deps automatically)
git clone https://github.com/MathxStudio/cp_generator.git
cd cp_generator
uv run cp-generator
# or: uv run python -m cp_generator
```

**Manual Python install (Python ≥ 3.14 required):**

```bash
pip install .
cp-generator
# or: python -m cp_generator
```

> **Linux note:** `cairosvg` requires the system `libcairo2` library.
> Install it with `sudo apt-get install libcairo2` (Debian/Ubuntu) or the
> equivalent for your distribution. Tkinter must also be present:
> `sudo apt-get install python3-tk`.

> **macOS note:** `cairosvg` requires cairo from Homebrew:
> `brew install cairo`.

---

## Run a pre-built portable bundle

Pre-built bundles are attached as artifacts to every successful `build-artifacts`
GitHub Actions run. They require **no Python installation** — just download,
extract, and launch.

1. Go to **Actions** → **build-artifacts** on the repository page.
2. Click the most recent successful run.
3. Under **Artifacts**, download the archive for your platform:
   - `cp-generator-linux-portable.tar.gz` → Linux x86-64
   - `cp-generator-windows-portable.zip` → Windows x86-64
   - `cp-generator-macos-portable.zip` → macOS (arm64 / x86-64 depending on runner)
   - `cp-generator-android-debug-apk` → Android debug APK artifact
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

## Build artifacts via GitHub Actions

The main workflow file is `.github/workflows/build-artifacts.yml`. It runs
automatically on every push to `main`, and can also be triggered manually.
Each successful run puts the desktop bundles and Android APK in one place.

### Trigger manually (no code push needed)

**Via the GitHub web UI:**

1. Go to **Actions** → **build-artifacts** → **Run workflow**.
2. Select the branch (default: `main`) and click **Run workflow**.
3. Refresh the page after a few seconds to see the run appear.
4. Wait for all three matrix jobs (Linux, Windows, macOS) to complete — usually
   5–10 minutes in total.
5. Click the completed run, then scroll to **Artifacts** to download.

**Via the GitHub CLI (`gh`):**

```bash
# trigger and wait (requires gh auth login)
gh workflow run build-artifacts.yml --repo MathxStudio/cp_generator

# watch progress
gh run list --workflow build-artifacts.yml --repo MathxStudio/cp_generator --limit 1
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
| **Android** | Builds `app-debug.apk` with Gradle + Chaquopy on Ubuntu |
| **Upload** | Attaches all desktop archives plus the Android APK as GitHub Actions artifacts (retained for 30 days) |

---

## Download artifacts with the helper script

`scripts/package_portable.sh` still automates the desktop trigger-wait-download
cycle using the `gh` CLI. The new unified workflow is the easiest path if you
want Android and desktop artifacts from the same run.

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
2. It calls `uv run cp-generator`, which fetches Python 3.14 and all dependencies
   on first run (requires an internet connection the first time only).
3. On subsequent runs it starts immediately from the local cache.

---

## Android app

The repository now includes a native Android shell under `android-app/`.

- **UI:** Kotlin + Jetpack Compose, tuned for portrait phone screens
- **Engine:** the shared Python package under `src/cp_generator/`, bridged into Android through Chaquopy
- **Workflow:** `build-artifacts` uploads the Android APK alongside the desktop bundles on every push to `main`

The Android UI intentionally stays compact:

- a square crease-sheet stage sized for vertical screens
- one-touch actions for randomize, refine, assign, and sample loading
- compact diagnostics and stats beneath the stage instead of a desktop-style multi-pane layout
- a deliberately lean first release focused on crease exploration rather than the full desktop 3D control surface

For more detail, see `android-app/README.md`.

---

## Features

- Random crease-pattern generation inside a square sheet
- Geometry optimization with Kawasaki-style alternating-angle constraints (SLSQP)
- Exhaustive mountain/valley assignment search with Maekawa filtering
- Bern–Hayes-style local reduction to minimize the combinatorial search space
- Diagnostics that separate local admissibility, fold assignment, global consistency, and exact-preview status
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
├── src/
│   └── cp_generator/
│       ├── __main__.py      # package entrypoint
│       ├── app.py           # Tkinter GUI and user interactions
│       ├── core.py          # crease-pattern graph, optimization, MV assignment, export
│       ├── fold_sim.py      # 3D fold preview pipeline
│       └── samples/
│           └── box_head.py  # authored Box Head sample pattern
├── assets/
│   ├── README.md
│   └── images/
│       ├── box_head.png
│       └── result.jpg
├── android-app/
│   ├── app/                 # native Android app module
│   ├── build.gradle.kts     # Android build root
│   ├── gradle.properties
│   └── settings.gradle.kts
├── examples/
│   ├── README.md
│   └── sessions/
│       └── fold_session.cpfold.json
├── pyproject.toml           # project metadata and dependency declarations
├── uv.lock                  # exact locked dependency versions
├── requirements.txt         # pip-compatible dependency list
├── Start_App.bat            # Windows zero-install launcher
├── scripts/
│   └── package_portable.sh  # trigger CI build and download artifacts
├── .github/
│   └── workflows/
│       ├── build-artifacts.yml # unified CI artifacts run (desktop + Android)
│       ├── portable-build.yml  # manual-only desktop build workflow
│       └── android-build.yml   # manual-only Android build workflow
└── report/
    ├── crease_pattern_methods.tex  # LaTeX source (Beamer presentation)
    └── crease_pattern_methods.pdf  # compiled presentation
```

---

## Report

`report/crease_pattern_methods.tex` is a concise Beamer presentation covering
graph construction, parity repair and Kawasaki optimization, mountain/valley
assignment, exact/current-geometry preview certification, and the current
global-consistency diagnostics.

Build the PDF locally (requires a TeX distribution with XeLaTeX and
`beamer`/`metropolis`):

```bash
cd report
latexmk -xelatex -interaction=nonstopmode crease_pattern_methods.tex
```
