from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest import mock

from cp_generator import core as cp
from cp_generator import validation_corpus
from cp_generator import workflow


CASE_MAP = validation_corpus.case_map()


def _load_payload(case_id: str) -> dict[str, object]:
    return validation_corpus.load_case_payload(CASE_MAP[case_id])


def _load_pattern(case_id: str) -> cp.CreasePattern:
    payload = _load_payload(case_id)
    return cp.CreasePattern.from_data(payload["pattern"])


def _pattern_from_vertices(*coords: tuple[float, float], side: float = 1.0) -> cp.CreasePattern:
    pattern = cp.CreasePattern()
    pattern.side = side
    for x, y in coords:
        pattern.add_vertex(x, y)
    return pattern


def _local_pass_report() -> cp.PatternDiagnosticReport:
    return cp.PatternDiagnosticReport(
        local_status=cp.STATUS_PASS,
        global_status=cp.STATUS_NOT_RUN,
        preview_status=cp.STATUS_NOT_RUN,
        fold_assignment_status=cp.STATUS_NOT_RUN,
        vertex_diagnostics=(),
        fold_assignment=cp.FoldAssignmentDiagnostic(
            assigned_fold_count=0,
            unassigned_fold_count=0,
            maekawa_failures=(),
            underdetermined=False,
        ),
        global_diagnostic=cp.GlobalDiagnostic(
            status=cp.STATUS_NOT_RUN,
            used_exact_faces=False,
            used_reference_pattern=False,
            uses_provisional_signs=False,
            uses_approximate_cycles=False,
            cycle_drift=None,
            message="Only local checks passed.",
        ),
        summary=(),
    )


class SessionPayloadTests(unittest.TestCase):
    def test_round_trip_preserves_pattern_reference_and_extra_state(self) -> None:
        pattern = _load_pattern("all_green")
        reference_pattern = pattern.clone()

        payload = workflow.build_session_payload(
            pattern,
            point_count="9",
            preview_reference_pattern=reference_pattern,
            fold_assignment_ready=True,
            extra_state={
                "show_labels": True,
                "sidebar_width": 420,
                "preview_motion_profile": "rigid_panels",
            },
        )

        restored = workflow.restore_session_payload(payload)

        self.assertEqual(restored.point_count, "9")
        self.assertTrue(restored.fold_assignment_ready)
        self.assertEqual(restored.pattern.to_data(), pattern.to_data())
        self.assertIsNotNone(restored.preview_reference_pattern)
        self.assertEqual(
            restored.preview_reference_pattern.to_data(),
            reference_pattern.to_data(),
        )
        self.assertEqual(
            restored.extra_state,
            {
                "show_labels": True,
                "sidebar_width": 420,
                "preview_motion_profile": "rigid_panels",
            },
        )

    def test_restore_rejects_unknown_session_format(self) -> None:
        with self.assertRaises(ValueError):
            workflow.restore_session_payload({"format": "not-cp-generator"})


class DiagnosticMergingTests(unittest.TestCase):
    def test_preview_cannot_promote_global_pass_when_assignment_failed(self) -> None:
        pattern = _load_pattern("maekawa_fail")
        report = pattern.analyze_pattern()
        preview = workflow.build_preview(pattern)

        merged = workflow.merge_report_with_preview(report, preview.diagnostic)

        self.assertEqual(preview.diagnostic.status, cp.STATUS_PASS)
        self.assertEqual(merged.fold_assignment_status, cp.STATUS_FAIL)
        self.assertEqual(merged.global_status, cp.STATUS_FAIL)
        self.assertEqual(merged.global_diagnostic.basis, "certified")

    def test_reserved_session_keys_cannot_be_overridden_by_extra_state(self) -> None:
        pattern = _load_pattern("all_green")

        payload = workflow.build_session_payload(
            pattern,
            point_count="5",
            fold_assignment_ready=True,
            extra_state={
                "format": "wrong",
                "version": 999,
                "pattern": {"oops": True},
                "point_count": "999",
                "sidebar_width": 360,
            },
        )

        self.assertEqual(payload["format"], "cp-generator-session")
        self.assertEqual(payload["version"], 1)
        self.assertEqual(payload["point_count"], "5")
        self.assertEqual(payload["pattern"], pattern.to_data())
        self.assertEqual(payload["sidebar_width"], 360)


class PreviewPayloadTests(unittest.TestCase):
    def test_build_preview_can_skip_serialized_payload_generation(self) -> None:
        pattern = _load_pattern("all_green")

        with mock.patch(
            "cp_generator.workflow._preview_payload",
            side_effect=AssertionError("payload generation should be skipped"),
        ):
            preview = workflow.build_preview(pattern, include_payload=False)

        self.assertIsNotNone(preview.model)
        self.assertIsNone(preview.payload)

    def test_exact_preview_payload_lists_balanced_and_rigid_profiles(self) -> None:
        pattern = _load_pattern("all_green")

        preview = workflow.build_preview(pattern)

        self.assertIsNotNone(preview.payload)
        assert preview.payload is not None
        self.assertEqual(preview.payload["default_motion_profile"], "legacy_layered")
        self.assertEqual(
            [profile["key"] for profile in preview.payload["motion_profiles"]],
            ["legacy_layered", "balanced_stack", "rigid_panels"],
        )

    def test_mesh_preview_payload_only_lists_balanced_profile(self) -> None:
        pattern = _load_pattern("crossing_folds")

        preview = workflow.build_preview(pattern)

        self.assertIsNotNone(preview.payload)
        assert preview.payload is not None
        self.assertEqual(preview.payload["default_motion_profile"], "legacy_layered")
        self.assertEqual(
            [profile["key"] for profile in preview.payload["motion_profiles"]],
            ["legacy_layered", "balanced_stack"],
        )


class GeometryQualityTests(unittest.TestCase):
    def test_geometry_quality_flags_extremely_close_vertices(self) -> None:
        pattern = _pattern_from_vertices(
            (0.0, 0.0),
            (1.0, 0.0),
            (1.0, 1.0),
            (0.0, 1.0),
            (0.5, 0.5),
            (0.5002, 0.5002),
        )

        quality = workflow.geometry_quality(pattern)

        self.assertFalse(quality.generic)
        self.assertLess(quality.min_vertex_distance, quality.threshold)
        self.assertEqual(quality.closest_vertex_pair, (4, 5))

    def test_build_pattern_retries_past_near_degenerate_generation(self) -> None:
        degenerate = _pattern_from_vertices(
            (0.0, 0.0),
            (1.0, 0.0),
            (1.0, 1.0),
            (0.0, 1.0),
            (0.25, 0.25),
            (0.2501, 0.2501),
        )
        generic = _pattern_from_vertices(
            (0.0, 0.0),
            (1.0, 0.0),
            (1.0, 1.0),
            (0.0, 1.0),
            (0.25, 0.25),
            (0.75, 0.75),
        )

        with mock.patch(
            "cp_generator.workflow._build_pattern_once",
            side_effect=[degenerate, generic],
        ) as build_once:
            pattern = workflow.build_pattern(2, side=1)

        self.assertTrue(workflow.is_generic_geometry(pattern))
        self.assertEqual(build_once.call_count, 2)

    def test_optimize_until_local_green_keeps_going_until_geometry_is_generic(self) -> None:
        class FakePattern:
            def __init__(self) -> None:
                self.side = 1.0
                self.vertices = [
                    cp.Vertex(0.0, 0.0),
                    cp.Vertex(1.0, 0.0),
                    cp.Vertex(1.0, 1.0),
                    cp.Vertex(0.0, 1.0),
                    cp.Vertex(0.5, 0.5),
                    cp.Vertex(0.5002, 0.5002),
                ]
                self.folds: set[cp.Fold] = set()
                self.optimize_calls = 0

            def analyze_pattern(self) -> cp.PatternDiagnosticReport:
                return _local_pass_report()

            def optimize(self) -> SimpleNamespace:
                self.optimize_calls += 1
                self.vertices[-1].x = 0.8
                self.vertices[-1].y = 0.8
                return SimpleNamespace(nit=1, fun=0.0)

        pattern = FakePattern()

        result = workflow.optimize_until_local_green(pattern, max_rounds=2)

        self.assertTrue(result.green)
        self.assertEqual(result.rounds, 1)
        self.assertEqual(pattern.optimize_calls, 1)
        self.assertIsNotNone(result.geometry_quality)
        self.assertTrue(result.geometry_quality.generic)


if __name__ == "__main__":
    unittest.main()
