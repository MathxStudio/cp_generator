# Copilot Instructions for Multi-Shape Paper Support

Extend this project to support multiple paper boundary symmetries and composed layouts while preserving valid crease-pattern behavior and the current square workflow.

## Scope

- Support paper domains:
  - Square (existing default)
  - Rectangle with user-input width and height
  - Isosceles right triangle (等腰直角三角形)
  - Right triangle (直角三角形)
- Support composed layouts that still render as one valid CP diagram:
  - Two `2:1` rectangles assembled into one square
  - Two or four isosceles right triangles assembled into one square
- For composed layouts, handle orientation/placement transforms and reverse mountain/valley assignment when a piece is mirrored so the merged result remains valid.

## Project-Fit Requirements

- Keep amendments minimal and aligned with current structure (`cp.py`, `cp_gen.py`).
- Preserve backward compatibility: square mode should remain the default behavior.
- Prefer introducing a shape/layout boundary abstraction over rewriting core graph logic.

## Implementation Guidance

- In `cp.py`, make boundary-dependent logic shape-aware (currently square-centric helpers such as edge/corner checks, edge snapping/removal, non-edge filtering, and boundary drawing).
- Keep the main pipeline intact (`triangulate -> evenize_vertices -> remove_edge_folds -> optimize -> assign_mv`), adapting boundary checks so it works across all supported domains.
- Add composition helpers to transform and merge piece-local CPs into a global CP (translate/rotate/reflect + coordinate remapping + fold parity handling for reflections).
- In `cp_gen.py`, add UI options for paper mode and dimensions with sensible defaults and basic validation.
- Ensure SVG export draws the active boundary shape/layout, not only a square outline.

## Acceptance Expectations

- Existing square generation remains stable.
- New shapes/layouts run through the same validity workflow.
- Merged composite layouts keep consistent fold orientation and valid MV behavior.
