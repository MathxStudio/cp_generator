# Android App

This directory contains a native Android shell for CP Generator.

- UI: Kotlin + Jetpack Compose
- Engine: shared Python package `cp_generator` via Chaquopy
- Layout target: portrait-first phone screens
- Product focus: fast crease generation, refinement, assignment, 3D folding preview, and diagnostics on a vertical phone display

The Android shell now includes the main mobile-friendly parts of the desktop workflow:

- it preserves the origami engine and diagnostic pipeline
- it renders the crease sheet directly in Compose
- it includes a 3D folded-figure preview with drag rotation and fold-progress scrubbing
- it includes local automation and full "auto all green" search
- it can check the GitHub release channel for a newer APK and hand that APK to Android's installer

## Update channel

The in-app updater checks the repository's **GitHub Releases** feed, not temporary
workflow artifacts. That means:

- `build-artifacts` is still useful for quick testing APKs
- the updater expects a published release containing an `.apk` asset
- for real upgrade continuity between installed versions, that release APK should be signed consistently

Right now, GitHub Actions only uploads the **debug** APK as a workflow artifact.
Tagged GitHub Releases intentionally skip Android APK publication until a
consistently signed release build is configured.

## Local build

1. Open `android-app/` in Android Studio.
2. Install an Android SDK for the configured `compileSdk`.
3. Make sure Python 3.10 is available, then set `CHAQUOPY_BUILD_PYTHON` if your IDE shell does not already expose it.
4. Build and run the `app` module on a device or emulator.

## CI build

GitHub Actions can assemble a debug APK from the workflow at `.github/workflows/android-build.yml`.

The uploaded debug APK is directly installable on a phone for testing.
