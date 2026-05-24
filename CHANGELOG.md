# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog, and versions use the repository's Git tags.

## [Unreleased]

## [0.3.5] - 2026-05-24

### Fixed
- Kept `Seamless rigid` preview motion continuous by holding the nearest solved seam-closed sample when an exact intermediate solve fails, instead of snapping to the gappy fallback path.
- Stopped desktop preview rebuild and report generation from eagerly serializing preview payloads, which restores responsive optimize/save steps for large sessions.
- Added a regression fixture for the `cp-v11-00` session so the once-stalled lower-right creases keep folding during rigid preview playback.

### Documentation
- Expanded the report and Beamer slides to explain the Maekawa-preserving obtuse-angle repair and the mathematics behind the three 3D preview motion families.

## [0.3.4] - 2026-05-24

### Fixed
- Replaced the exact `Seamless rigid` 3D preview path with a seam-closed rigid continuation that keeps faces connected throughout the motion and lands on the complete exact folded figure.
- Added regression coverage so the exact rigid preview stays edge-connected mid-motion and reaches the exact folded endpoint instead of stalling in the earlier near-flat relaxation.

## [0.3.3] - 2026-05-24

### Fixed
- Bundled the macOS cairo runtime into portable desktop builds and switched the macOS artifact path to a portable `.app` bundle so frozen previews launch without a Homebrew cairo install.
- Expanded PR portable smoke coverage across Linux, Windows, and macOS so release-only packaging regressions are caught before merge.

## [0.3.2] - 2026-05-24

### Fixed
- Replaced the broken package-relative desktop launcher path in portable builds with an absolute-import launcher that works in frozen release bundles.
- Added source and frozen-binary smoke tests to CI and release workflows so desktop assets are verified before publication.

## [0.3.1] - 2026-05-24

### Fixed
- Repaired the two-obtuse-angle mountain/valley glitch by forcing a Maekawa-safe monochrome resolution when a conflicting middle crease blocks flat folding.
- Added regression coverage for the obtuse-angle repair pass and its integration into `assign_mv()`.

## [0.3.0] - 2026-05-23

### Added
- Shared workflow engine for desktop and mobile orchestration.
- Checked-in validation corpus and `cp-generator-diagnostics` CLI.
- Bounded small-instance exact checker for research and regression work.
- Geometry-quality guard so local/all-green automation rejects near-degenerate sheets whose vertices collapse almost onto each other.
- GitHub Actions CI workflow for Python validation, wheel smoke tests, and Android lint/build checks.
- Baseline repository policy files for contributing and security reporting.

### Changed
- Desktop and mobile flows now share one diagnostics/preview/session workflow layer.
- Tagged releases now verify that Python and Android version metadata match the Git tag before publishing.
- GitHub Releases publish desktop assets only until a consistently signed Android release channel is configured.

## [0.2.1] - 2026-05-21

### Changed
- Portable desktop bundles and release artifact packaging were refreshed for the 0.2.1 release line.
