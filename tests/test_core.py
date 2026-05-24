from __future__ import annotations

import math
import unittest
from unittest import mock

from cp_generator import core as cp


def _ray_to_boundary(
    center_x: float,
    center_y: float,
    side: float,
    angle_deg: float,
) -> tuple[float, float]:
    theta = math.radians(angle_deg)
    dx = math.cos(theta)
    dy = math.sin(theta)
    candidates: list[tuple[float, float, float]] = []

    if abs(dx) > 1e-9:
        for x in (0.0, side):
            scale = (x - center_x) / dx
            if scale <= 1e-9:
                continue
            y = center_y + scale * dy
            if -1e-9 <= y <= side + 1e-9:
                candidates.append((scale, x, y))

    if abs(dy) > 1e-9:
        for y in (0.0, side):
            scale = (y - center_y) / dy
            if scale <= 1e-9:
                continue
            x = center_x + scale * dx
            if -1e-9 <= x <= side + 1e-9:
                candidates.append((scale, x, y))

    _, x, y = min(candidates)
    return x, y


def _obtuse_glitch_pattern() -> tuple[cp.CreasePattern, cp.Vertex]:
    pattern = cp.CreasePattern()
    pattern.side = 10.0

    center = cp.Vertex(5.0, 5.0)
    pattern.vertices.append(center)

    for angle_deg in (-170.0, -70.0, 30.0, 110.0):
        x, y = _ray_to_boundary(center.x, center.y, pattern.side, angle_deg)
        boundary_vertex = cp.Vertex(x, y)
        pattern.vertices.append(boundary_vertex)
        pattern.add_fold(center, boundary_vertex, -1)

    return pattern, center


class ObtuseAngleGlitchRepairTests(unittest.TestCase):
    def test_repair_makes_consecutive_obtuse_triplet_monochrome(self) -> None:
        pattern, center = _obtuse_glitch_pattern()
        folds = pattern.clockwise_folds(center)
        for fold, fold_type in zip(folds, (0, 1, 0, 0)):
            fold.type = fold_type

        self.assertEqual(pattern.maekawa_balance(center), 2)

        repairs = pattern.repair_obtuse_monochrome_glitches()

        self.assertEqual(repairs, 1)
        self.assertEqual(
            [fold.type for fold in pattern.clockwise_folds(center)],
            [1, 1, 1, 0],
        )
        self.assertEqual(pattern.maekawa_balance(center), -2)

    def test_repair_skips_vertices_without_the_glitch_pattern(self) -> None:
        pattern, center = _obtuse_glitch_pattern()
        folds = pattern.clockwise_folds(center)
        for fold, fold_type in zip(folds, (0, 0, 0, 1)):
            fold.type = fold_type

        repairs = pattern.repair_obtuse_monochrome_glitches()

        self.assertEqual(repairs, 0)
        self.assertEqual(
            [fold.type for fold in pattern.clockwise_folds(center)],
            [0, 0, 0, 1],
        )

    def test_assign_mv_runs_the_repair_pass_before_returning(self) -> None:
        pattern, _ = _obtuse_glitch_pattern()

        with mock.patch.object(
            cp.CreasePattern,
            "repair_obtuse_monochrome_glitches",
            return_value=1,
        ) as repair:
            result = pattern.assign_mv()

        self.assertTrue(result.success)
        repair.assert_called_once_with()
        self.assertIn("after repairing 1 obtuse-angle glitch", result.message)


if __name__ == "__main__":
    unittest.main()
