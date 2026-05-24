from __future__ import annotations

from collections import defaultdict
import json
import math
from pathlib import Path
import unittest

import numpy as np

from cp_generator import core as cp
from cp_generator import fold_sim
from cp_generator import validation_corpus
from cp_generator import workflow


CASE_MAP = validation_corpus.case_map()
FIXTURE_ROOT = Path(__file__).with_name("fixtures")


def _load_pattern(case_id: str) -> cp.CreasePattern:
    payload = validation_corpus.load_case_payload(CASE_MAP[case_id])
    return cp.CreasePattern.from_data(payload["pattern"])


def _load_session(filename: str) -> workflow.RestoredSession:
    payload = json.loads((FIXTURE_ROOT / filename).read_text(encoding="utf-8"))
    return workflow.restore_session_payload(payload)


def _max_shared_edge_gap(
    model: fold_sim.FoldedFigureModel | fold_sim.ApproximateFoldedFigureModel,
    states: tuple[fold_sim.FaceRenderState, ...],
) -> float:
    edge_samples: dict[tuple[int, int], list[tuple[np.ndarray, np.ndarray]]] = defaultdict(list)
    for face_index, state in enumerate(states):
        edge_keys = model.face_edge_keys[face_index]
        for local_index, edge_key in enumerate(edge_keys):
            next_index = (local_index + 1) % len(state.points)
            edge_samples[edge_key].append(
                (
                    np.array(state.points[local_index], dtype=float),
                    np.array(state.points[next_index], dtype=float),
                )
            )

    max_gap = 0.0
    for samples in edge_samples.values():
        if len(samples) != 2:
            continue
        (first_a, first_b), (second_a, second_b) = samples
        direct = max(
            float(np.linalg.norm(first_a - second_a)),
            float(np.linalg.norm(first_b - second_b)),
        )
        flipped = max(
            float(np.linalg.norm(first_a - second_b)),
            float(np.linalg.norm(first_b - second_a)),
        )
        max_gap = max(max_gap, min(direct, flipped))
    return max_gap


def _edge_dihedral_angle(
    model: fold_sim.FoldedFigureModel | fold_sim.ApproximateFoldedFigureModel,
    states: tuple[fold_sim.FaceRenderState, ...],
    edge_key: tuple[int, int],
) -> float:
    key = tuple(sorted(edge_key))
    incident_faces: list[int] = []
    for face_index, face in enumerate(model.faces):
        vertices = face.vertices
        for start, end in zip(vertices, vertices[1:] + vertices[:1]):
            if tuple(sorted((start, end))) == key:
                incident_faces.append(face_index)
                break

    if len(incident_faces) != 2:
        raise AssertionError(f"Expected edge {key} to border exactly two faces.")

    def face_normal(points: np.ndarray) -> np.ndarray:
        base = points[0]
        for first in range(1, len(points) - 1):
            normal = np.cross(points[first] - base, points[first + 1] - base)
            norm = float(np.linalg.norm(normal))
            if norm > 1e-9:
                return normal / norm
        raise AssertionError("Face normal was degenerate.")

    first_normal = face_normal(np.array(states[incident_faces[0]].points, dtype=float))
    second_normal = face_normal(np.array(states[incident_faces[1]].points, dtype=float))
    return math.degrees(
        math.acos(float(np.clip(np.dot(first_normal, second_normal), -1.0, 1.0)))
    )


def _face_pairwise_lengths(points: np.ndarray) -> tuple[float, ...]:
    lengths: list[float] = []
    for first in range(len(points)):
        for second in range(first + 1, len(points)):
            lengths.append(float(np.linalg.norm(points[first] - points[second])))
    return tuple(lengths)


class FoldedFigureMotionTests(unittest.TestCase):
    def test_balanced_stack_reduces_midfold_shared_edge_gaps(self) -> None:
        pattern = _load_pattern("all_green")
        model = fold_sim.build_folded_figure(pattern)

        angle = (math.pi - 0.1) * 0.5
        raw_points = model.face_points_at_angle(angle)
        raw_states = tuple(
            fold_sim.FaceRenderState(
                index=index,
                points=points,
                triangles=model.faces[index].triangles,
                top_surface=True,
            )
            for index, points in enumerate(raw_points)
        )

        balanced_states = model.frame(0.5, motion_profile=fold_sim.PREVIEW_MOTION_BALANCED_STACK)

        self.assertLess(
            _max_shared_edge_gap(model, balanced_states),
            _max_shared_edge_gap(model, raw_states),
        )

    def test_rigid_panels_keeps_exact_faces_rigid(self) -> None:
        pattern = _load_pattern("all_green")
        model = fold_sim.build_folded_figure(pattern)

        states = model.frame(0.6, motion_profile=fold_sim.PREVIEW_MOTION_RIGID_PANELS)

        for face, state in zip(model.faces, states):
            source = np.array(
                [[model.coords[index][0], model.coords[index][1], 0.0] for index in face.vertices],
                dtype=float,
            )
            self.assertEqual(
                len(_face_pairwise_lengths(source)),
                len(_face_pairwise_lengths(state.points)),
            )
            for source_length, rendered_length in zip(
                _face_pairwise_lengths(source),
                _face_pairwise_lengths(state.points),
            ):
                self.assertAlmostEqual(source_length, rendered_length, places=6)

    def test_rigid_panels_closes_midfold_shared_edges(self) -> None:
        pattern = _load_pattern("all_green")
        model = fold_sim.build_folded_figure(pattern)

        raw_points = model.face_points_at_angle(math.pi * 0.5)
        raw_states = tuple(
            fold_sim.FaceRenderState(
                index=index,
                points=points,
                triangles=model.faces[index].triangles,
                top_surface=True,
            )
            for index, points in enumerate(raw_points)
        )
        rigid_states = model.frame(0.5, motion_profile=fold_sim.PREVIEW_MOTION_RIGID_PANELS)

        self.assertLess(_max_shared_edge_gap(model, rigid_states), 0.05)
        self.assertLess(
            _max_shared_edge_gap(model, rigid_states),
            _max_shared_edge_gap(model, raw_states),
        )

    def test_rigid_panels_reaches_the_exact_folded_figure(self) -> None:
        pattern = _load_pattern("all_green")
        model = fold_sim.build_folded_figure(pattern)

        final_states = model.frame(1.0, motion_profile=fold_sim.PREVIEW_MOTION_RIGID_PANELS)
        exact_points = model.face_points_at_angle(math.pi)

        self.assertLess(_max_shared_edge_gap(model, final_states), 1e-6)
        for state, expected in zip(final_states, exact_points):
            np.testing.assert_allclose(state.points, expected, atol=1e-6)

    def test_rigid_panels_keeps_regression_session_hinges_moving_midfold(self) -> None:
        session = _load_session("cp-v11-00.cpfold.json")
        model = fold_sim.build_folded_figure(session.pattern)

        mid_states = model.frame(0.5, motion_profile=fold_sim.PREVIEW_MOTION_RIGID_PANELS)

        self.assertLess(_max_shared_edge_gap(model, mid_states), 0.05)
        self.assertGreater(_edge_dihedral_angle(model, mid_states, (1, 7)), 40.0)
        self.assertGreater(_edge_dihedral_angle(model, mid_states, (5, 7)), 40.0)

    def test_rigid_panels_bridges_across_failed_exact_sample(self) -> None:
        pattern = _load_pattern("all_green")
        model = fold_sim.build_folded_figure(pattern)
        sample_progress = model._seamless_rigid_progress_samples
        center_index = len(sample_progress) // 2

        model._ensure_seamless_rigid_motion(center_index - 1)
        model._ensure_seamless_rigid_motion(center_index + 1)
        model._seamless_rigid_sample_failed[center_index] = True

        bridged_states = model.frame(
            float(sample_progress[center_index]),
            motion_profile=fold_sim.PREVIEW_MOTION_RIGID_PANELS,
        )
        posed_points = model.face_points_at_angle(math.pi * float(sample_progress[center_index]))
        legacy_states = tuple(
            fold_sim.FaceRenderState(
                index=index,
                points=points,
                triangles=model.faces[index].triangles,
                top_surface=True,
            )
            for index, points in enumerate(model._legacy_rigid_panel_face_points(0.5, posed_points))
        )

        self.assertLess(_max_shared_edge_gap(model, bridged_states), 0.05)
        self.assertLess(
            _max_shared_edge_gap(model, bridged_states),
            _max_shared_edge_gap(model, legacy_states),
        )


if __name__ == "__main__":
    unittest.main()
