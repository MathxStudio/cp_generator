# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog, and versions use the repository's Git tags.

## [Unreleased]

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
