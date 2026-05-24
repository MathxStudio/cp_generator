# Math Documentation Source Audit

Date: 2026-05-24

## Purpose

This note records the external mathematical references consulted while bringing
the Beamer deck and the formal report into closer alignment with the current
implementation.

I did not vendor PDF copies into the repository. The existing report/deck use a
small manual bibliography, and the additional writeup only needed one more
simulation-oriented citation plus a sharper mapping from the literature to the
implemented certifiers.

## Sources consulted

### Hull — local flat-foldability

- Thomas C. Hull, *On the Mathematics of Flat Origamis*, Congressus
  Numerantium 100 (1994), 215–224.
- Retrieval links consulted:
  - https://origametry.net/papers/origamimath.pdf
  - https://www.researchgate.net/profile/Thomas-Hull-2/publication/2357716_On_the_Mathematics_of_Flat_Origamis/links/53f47f410cf22be01c3ec6b9/On-the-Mathematics-of-Flat-Origamis.pdf

Used for:
- Kawasaki and Maekawa single-vertex constraints.
- Clear separation between local flat-foldability theorems and the stronger
  multi-vertex global claims that the program does **not** fully decide.

### Bern–Hayes — local reduction and overlap-order complexity

- Marshall Bern and Barry Hayes, *The Complexity of Flat Origami*, SODA 1996.
- Retrieval links consulted:
  - https://www.osti.gov/biblio/416799
  - https://www.academia.edu/72836864/The_complexity_of_flat_origami

Used for:
- The wedge-reduction / local sign-pairing explanation behind `assign_mv()`.
- The overlap-order viewpoint referenced when describing the bounded exact
  checker.

### Abel–Cantarella–Demaine–Eppstein–Hull–Ku–Lang–Tachi — rigid origami

- Zachary Abel et al., *Rigid Origami Vertices: Conditions and Forcing Sets*,
  Journal of Computational Geometry.
- Retrieval links consulted:
  - https://arxiv.org/abs/1507.01644
  - https://erikdemaine.org/papers/RigidOrigami_JoCG/paper.pdf

Used for:
- The rigid-panel / hinge-rotation interpretation of the exact preview modes.
- Terminology around rigidly moving faces while preserving crease hinges.

### Tachi — rigid-origami simulation

- Tomohiro Tachi, *Simulation of Rigid Origami*, in *Origami^4* (2009).
- Retrieval links consulted:
  - https://origami.c.u-tokyo.ac.jp/~tachi/cg/SimulationOfRigidOrigami_tachi_4OSME.pdf
  - https://doczz.net/doc/6629367/simulation-of-rigid-origami

Used for:
- Background context on rigid-origami simulation as a continuous-motion goal.
- Justification for adding a simulation-oriented citation alongside the older
  rigid-vertex reference.

### Eppstein — parameterized flat folding

- David Eppstein, *A Parameterized Algorithm for Flat Folding* (2023).
- Retrieval links consulted:
  - https://arxiv.org/abs/2306.11939
  - https://ics.uci.edu/~eppstein/pubs/2023.html

Used for:
- Positioning the bounded exact checker as a small-instance, overlap-order
  certificate rather than a full global flat-foldability algorithm.
- Explaining why the current checker is deliberately bounded by face count and
  exact-face availability.

## Mapping to implementation details

The following sections are implementation-derived rather than taken from any
single external paper:

- the scale-normalized generic-geometry guard in `workflow.py`,
- the obtuse monochrome glitch repair in `core.py`,
- the exact/current/reference/mesh diagnostic semantics in `workflow.py` and
  `fold_sim.py`,
- the bounded exact checker’s concrete near-flat sampling, triangle clipping,
  and bitmask order-counting logic in `exact_checker.py`,
- the current three preview motion families and their solver-specific fallback
  behavior in `fold_sim.py`.

Those parts of the report/deck were written directly from code inspection and
tests, with the literature above used only to frame the surrounding mathematical
context correctly.
