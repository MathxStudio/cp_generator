# Android App

This directory contains a native Android shell for CP Generator.

- UI: Kotlin + Jetpack Compose
- Engine: shared Python package `cp_generator` via Chaquopy
- Layout target: portrait-first phone screens
- Product focus: fast crease generation, refinement, assignment, and diagnostics on a vertical phone display

The Android shell is intentionally lean in this first version:

- it preserves the origami engine and diagnostic pipeline
- it renders the crease sheet directly in Compose
- it does not yet replicate the full desktop Tkinter multi-pane workflow or 3D preview controls

## Local build

1. Open `android-app/` in Android Studio.
2. Install an Android SDK for the configured `compileSdk`.
3. Make sure Python 3.11 is available, then set `CHAQUOPY_BUILD_PYTHON` if your IDE shell does not already expose it.
4. Build and run the `app` module on a device or emulator.

## CI build

GitHub Actions can assemble a debug APK from the workflow at `.github/workflows/android-build.yml`.

The uploaded debug APK is directly installable on a phone for testing.
