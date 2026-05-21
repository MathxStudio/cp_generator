from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cp_generator import core as cp
from cp_generator import exporting


class BatchNameAllocatorTests(unittest.TestCase):
    def test_allocator_fills_lowest_free_indices_across_formats(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            directory = Path(tmpdir)
            (directory / "cp-v12-00.pdf").write_text("", encoding="utf-8")
            (directory / "cp-v12-02.cpfold.json").write_text("", encoding="utf-8")
            (directory / "cp-v8-00.pdf").write_text("", encoding="utf-8")

            allocator = exporting.BatchNameAllocator(directory)

            self.assertEqual(
                allocator.allocate(vertex_count=12, kind="pdf").name,
                "cp-v12-01.pdf",
            )
            self.assertEqual(
                allocator.allocate(vertex_count=12, kind="json").name,
                "cp-v12-03.cpfold.json",
            )
            self.assertEqual(
                allocator.allocate(vertex_count=8, kind="json").name,
                "cp-v8-01.cpfold.json",
            )

    def test_allocator_rejects_when_all_slots_are_taken(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            directory = Path(tmpdir)
            for index in range(100):
                (directory / f"cp-v9-{index:02d}.pdf").write_text("", encoding="utf-8")

            allocator = exporting.BatchNameAllocator(directory)

            with self.assertRaises(ValueError):
                allocator.allocate(vertex_count=9, kind="pdf")

    def test_allocator_pair_uses_shared_lowest_free_slot(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            directory = Path(tmpdir)
            (directory / "cp-v12-00.pdf").write_text("", encoding="utf-8")
            (directory / "cp-v12-02.cpfold.json").write_text("", encoding="utf-8")

            allocator = exporting.BatchNameAllocator(directory)

            json_path, pdf_path = allocator.allocate_pair(vertex_count=12)

            self.assertEqual(json_path.name, "cp-v12-01.cpfold.json")
            self.assertEqual(pdf_path.name, "cp-v12-01.pdf")


class VertexTargetParsingTests(unittest.TestCase):
    def test_parser_supports_ranges_steps_and_discrete_values(self) -> None:
        self.assertEqual(
            exporting.parse_vertex_target_spec("8-12:2, 15, 18-19"),
            (8, 10, 12, 15, 18, 19),
        )

    def test_parser_rejects_invalid_targets(self) -> None:
        with self.assertRaises(ValueError):
            exporting.parse_vertex_target_spec("3, 6")

        with self.assertRaises(ValueError):
            exporting.parse_vertex_target_spec("12-8")

        with self.assertRaises(ValueError):
            exporting.parse_vertex_target_spec("8-12:0")


class PrintablePdfPlanTests(unittest.TestCase):
    def test_page_plan_uses_full_a4_width_and_mirrors_the_back_page(self) -> None:
        pattern = _pattern_with_cross_diagonals()

        front_page, back_page = exporting.build_printable_page_plans(
            pattern,
            "cp-v4-00.pdf",
        )

        self.assertAlmostEqual(front_page.pattern_box.size, front_page.page_width)
        self.assertAlmostEqual(
            front_page.pattern_box.bottom + front_page.pattern_box.size,
            front_page.page_height,
        )
        self.assertEqual(len(front_page.segments), len(back_page.segments))

        for front_segment, back_segment in zip(
            front_page.segments,
            back_page.segments,
            strict=True,
        ):
            self.assertAlmostEqual(front_segment.x1 + back_segment.x1, front_page.page_width)
            self.assertAlmostEqual(front_segment.x2 + back_segment.x2, front_page.page_width)
            self.assertAlmostEqual(front_segment.y1, back_segment.y1)
            self.assertAlmostEqual(front_segment.y2, back_segment.y2)

    def test_page_plan_appends_metadata_below_the_pattern(self) -> None:
        pattern = _pattern_with_cross_diagonals()

        front_page, back_page = exporting.build_printable_page_plans(
            pattern,
            "cp-v4-00.pdf",
            extra_metadata_lines=("Interior points: 0",),
        )

        self.assertIn("File: cp-v4-00.pdf", front_page.metadata_lines)
        self.assertIn("Vertices: 4", front_page.metadata_lines)
        self.assertIn("Interior points: 0", front_page.metadata_lines)
        self.assertIn("Page: front", front_page.metadata_lines)
        self.assertIn("Page: mirrored back for duplex printing", back_page.metadata_lines)
        self.assertLess(front_page.metadata_start_y, front_page.pattern_box.bottom)


def _pattern_with_cross_diagonals() -> cp.CreasePattern:
    pattern = cp.CreasePattern()
    pattern.side = 10

    top_left = cp.Vertex(0, 0)
    top_right = cp.Vertex(10, 0)
    bottom_right = cp.Vertex(10, 10)
    bottom_left = cp.Vertex(0, 10)

    pattern.add_fold(top_left, bottom_right, 0)
    pattern.add_fold(top_right, bottom_left, 1)
    return pattern


if __name__ == "__main__":
    unittest.main()
