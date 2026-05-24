# Implementation Plan: Preview Motion Overhaul

## Overview
The current 3D preview has two visible problems:

1. Mid-animation fracture:
   - The exact preview propagates rigid transforms along a face spanning tree.
   - During intermediate poses, non-tree adjacencies are not enforced, so loop edges can crack open.
   - The mesh fallback makes this worse because every triangle becomes its own rigid panel.

2. End-state ugliness:
   - The preview settles into a layered flat stack by linearly blending face poses into a separated final arrangement.
   - This avoids a perfectly flat, thickness-free image, but the current spacing is visually too exploded and too obviously face-by-face.

The goal is to keep the existing strengths:
- exact face reconstruction when the sheet is globally flat-foldable,
- mesh fallback when exact reconstruction fails,
- a visible sense of thickness at the end,

while making the animation more realistic and more acceptable to watch.

## Peer Comparison

### Origami Simulator
- Source:
  - https://amandaghassaei.com/projects/origami_simulator/
- Strength:
  - continuous-looking motion because the paper is treated as a densely connected deforming mesh.
- Tradeoff:
  - visual continuity is strong, but it is not the same as preserving exact rigid faces of a flat-folded crease pattern.
- Relevance:
  - we should borrow the "continuous seam closure" goal, not the full deformable-sheet model.

### Tachi-style rigid origami simulation
- Sources:
  - https://origami.c.u-tokyo.ac.jp/~tachi/cg/SimulationOfRigidOrigami_tachi_4OSME.pdf
  - https://tsg.ne.jp/TT/cg/ThickRigidOrigami_tachi_5OSME.pdf
- Strength:
  - preserves rigid panels and aims for continuous folding motion.
- Tradeoff:
  - a true rigid-fold solution is hard in the general case, especially for looped crease graphs.
- Relevance:
  - for exact face reconstructions, we should offer a rigid-panels-oriented mode that avoids mesh cuts and avoids non-rigid settle-to-stack behavior.

### Oriedita / folded-figure viewers
- Sources:
  - https://oriedita.github.io/
  - https://github.com/oriedita/oriedita/blob/master/README.md
- Strength:
  - prioritizes interpretable folded states and readable layer structure.
- Tradeoff:
  - the folded state can be more important than a physically perfect motion path.
- Relevance:
  - our default preview should remain a readable folded preview, even if the optional rigid-panels mode is the more "motion-faithful" one.

## Architecture Decisions

- Default preview mode:
  - `balanced_stack`
  - Uses crack suppression during motion and a compressed layered finish.
  - Applies to both exact previews and mesh fallback.

- Optional preview mode:
  - `rigid_panels`
  - Available when the preview uses exact face reconstruction.
  - Keeps faces rigid throughout the motion and avoids the strong non-rigid settle into the stacked final state.
  - If the sheet falls back to mesh, the UI should explain that the mode is unavailable or gracefully fall back to `balanced_stack`.

- Motion improvement strategy:
  - Add an iterative face-vertex relaxation pass on top of the existing hinge-tree pose.
  - For each frame:
    1. build a pose from the current hinge tree,
    2. average duplicated vertex instances across all faces,
    3. refit each face as a rigid panel to those shared vertex targets,
    4. iterate a few rounds.
  - This should shrink loop-edge cracks without triangulating exact polygonal faces into visible fragments.

- Finish improvement strategy:
  - Compress end-state thickness substantially.
  - Keep stack readability, but avoid the current exploded-layer look.
  - For `rigid_panels`, keep the finish near-flat and primarily rigid, with only minimal display bias for readability.

- UI exposure:
  - Desktop: preview mode selector in the folded-figure control card, persisted in session payload.
  - Android: preview mode selector next to preview controls, wired through the Python bridge.

## Task List

### Phase 1: Foundation
- [ ] Task 1: Add research note and preview-motion plan.
- [ ] Task 2: Add regression tests that measure seam/crack quality and preview payload mode fields.

### Checkpoint: Foundation
- [ ] Test design proves the change is measurable before the solver is modified.

### Phase 2: Core Solver
- [ ] Task 3: Implement a reusable panel-relaxation pass for face-based and mesh-based preview models.
- [ ] Task 4: Introduce `balanced_stack` and `rigid_panels` preview motion profiles in the solver/model layer.

### Checkpoint: Core Solver
- [ ] Exact preview seams are tighter at intermediate progress than before.
- [ ] Mesh fallback also benefits from reduced fracture.

### Phase 3: Payload and Clients
- [ ] Task 5: Thread preview profile selection through `workflow.py` and `mobile_api.py`.
- [ ] Task 6: Add desktop controls and session persistence.
- [ ] Task 7: Add Android controls and bridge plumbing.

### Checkpoint: Client Integration
- [ ] Desktop and Android can both switch preview modes.
- [ ] Fallback behavior is clear when rigid-panels mode cannot be honored.

### Phase 4: Release
- [ ] Task 8: Run full verification and review the diff for correctness and UX regressions.
- [ ] Task 9: Open PR, merge to `main`, bump release metadata, tag, and publish a release.

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Relaxation makes motion unstable on some sheets | High | Keep iteration count small, clamp strength, and test both exact and mesh fixtures |
| Rigid-panels mode over-promises physical correctness | Medium | Describe it as a rigid-panels presentation of the exact face graph, not a universal proof of rigid foldability |
| Desktop and Android preview controls drift apart | Medium | Define shared mode strings in Python payload and keep client labels thin |
| Release work mixes with solver work | Medium | Keep solver changes and release metadata in separate commits |

## Acceptance Criteria

- The default preview no longer looks like a stack of fractured panels on common exact and mesh previews.
- The optional rigid-panels mode avoids triangulated exact-face cutting and keeps faces rigid through the motion.
- Desktop and Android expose the preview mode choice clearly.
- Regression tests cover payload mode plumbing and at least one seam-quality improvement signal.
- The branch is merged, a new release is published, and local plus remote git state are synced.

## Notes From Research

- We are intentionally not implementing a full deformable-sheet simulation:
  - that would pull the project toward Origami Simulator's global constraint solve and much denser mesh machinery.
- We are also intentionally not claiming a certified rigid-fold path for every exact flat-foldable sheet:
  - the new `rigid_panels` option is a face-rigid presentation mode built on iterative seam closure, not a proof engine.
- The default `balanced_stack` mode exists because readable folded-state communication matters:
  - Oriedita-style interpretability is a real user need, and pure rigid presentation can become visually too ambiguous near the final flat state.
