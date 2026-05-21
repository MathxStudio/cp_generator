from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Literal

from . import core as cp

try:
    from reportlab.pdfgen import canvas as reportlab_canvas
except ImportError:  # pragma: no cover - optional at runtime for mobile builds
    reportlab_canvas = None


BatchSaveKind = Literal["json", "pdf", "both"]

A4_PAGE_WIDTH_PT = 210 * 72.0 / 25.4
A4_PAGE_HEIGHT_PT = 297 * 72.0 / 25.4
PATTERN_BORDER_WIDTH_PT = 2.0
CREASE_WIDTH_PT = 1.35
METADATA_MARGIN_X_PT = 18.0
METADATA_TOP_GAP_PT = 18.0
METADATA_LEADING_PT = 14.0
MAX_BATCH_INDEX = 100

_BATCH_NAME_PATTERN = re.compile(
    r"^cp-v(?P<vertex_count>\d+)-(?P<index>\d{2})(?:\.[^.]+)+$"
)


@dataclass(frozen=True)
class PatternBox:
    left: float
    bottom: float
    size: float
    stroke_width: float


@dataclass(frozen=True)
class StrokeSegment:
    x1: float
    y1: float
    x2: float
    y2: float
    color: str
    width: float


@dataclass(frozen=True)
class PrintablePagePlan:
    page_width: float
    page_height: float
    pattern_box: PatternBox
    segments: tuple[StrokeSegment, ...]
    metadata_lines: tuple[str, ...]
    metadata_start_x: float
    metadata_start_y: float
    metadata_leading: float


class BatchNameAllocator:
    def __init__(self, directory: Path):
        self.directory = Path(directory)
        self._used_indices = self._scan_existing_indices()

    def allocate(self, *, vertex_count: int, kind: BatchSaveKind) -> Path:
        if kind == "both":
            raise ValueError("Use allocate_pair() when saving both JSON and PDF.")
        vertex_count = max(int(vertex_count), 0)
        index = self._reserve_index(vertex_count)
        return self.path_for(vertex_count=vertex_count, index=index, kind=kind)

    def allocate_pair(self, *, vertex_count: int) -> tuple[Path, Path]:
        vertex_count = max(int(vertex_count), 0)
        index = self._reserve_index(vertex_count)
        return (
            self.path_for(vertex_count=vertex_count, index=index, kind="json"),
            self.path_for(vertex_count=vertex_count, index=index, kind="pdf"),
        )

    def path_for(self, *, vertex_count: int, index: int, kind: Literal["json", "pdf"]) -> Path:
        extension = _extension_for_kind(kind)
        return self.directory / f"cp-v{vertex_count}-{index:02d}{extension}"

    def _reserve_index(self, vertex_count: int) -> int:
        used = self._used_indices.setdefault(vertex_count, set())
        for index in range(MAX_BATCH_INDEX):
            if index in used:
                continue
            used.add(index)
            return index
        raise ValueError(
            f"All batch name slots are already used for {vertex_count} vertices."
        )

    def _scan_existing_indices(self) -> dict[int, set[int]]:
        used: dict[int, set[int]] = {}
        if not self.directory.exists():
            return used
        for path in self.directory.iterdir():
            if not path.is_file():
                continue
            match = _BATCH_NAME_PATTERN.match(path.name)
            if match is None:
                continue
            vertex_count = int(match.group("vertex_count"))
            index = int(match.group("index"))
            used.setdefault(vertex_count, set()).add(index)
        return used


def parse_vertex_target_spec(spec: str) -> tuple[int, ...]:
    targets: list[int] = []
    for raw_token in spec.split(","):
        token = raw_token.strip()
        if not token:
            continue
        if "-" not in token:
            targets.append(_parse_vertex_target(token))
            continue

        start_text, remainder = token.split("-", 1)
        step = 1
        if ":" in remainder:
            end_text, step_text = remainder.split(":", 1)
            step = int(step_text.strip())
        else:
            end_text = remainder

        start = _parse_vertex_target(start_text)
        end = _parse_vertex_target(end_text)
        if step <= 0:
            raise ValueError("Vertex target steps must be positive.")
        if end < start:
            raise ValueError("Vertex target ranges must be ascending.")

        targets.extend(range(start, end + 1, step))

    if not targets:
        raise ValueError("Enter at least one target vertex count.")
    unique_targets: list[int] = []
    seen: set[int] = set()
    for target in targets:
        if target in seen:
            continue
        seen.add(target)
        unique_targets.append(target)
    return tuple(unique_targets)


def build_printable_page_plans(
    pattern: cp.CreasePattern,
    file_name: str,
    *,
    extra_metadata_lines: tuple[str, ...] = (),
) -> tuple[PrintablePagePlan, PrintablePagePlan]:
    pattern_box = PatternBox(
        left=0.0,
        bottom=A4_PAGE_HEIGHT_PT - A4_PAGE_WIDTH_PT,
        size=A4_PAGE_WIDTH_PT,
        stroke_width=PATTERN_BORDER_WIDTH_PT,
    )
    base_metadata = (
        f"File: {file_name}",
        f"Vertices: {len(pattern.vertices)}",
        f"Folds: {len(pattern.folds)}",
        f"Assigned folds: {sum(1 for fold in pattern.folds if fold.type in (0, 1))}",
        *extra_metadata_lines,
    )
    return (
        PrintablePagePlan(
            page_width=A4_PAGE_WIDTH_PT,
            page_height=A4_PAGE_HEIGHT_PT,
            pattern_box=pattern_box,
            segments=_pattern_segments(pattern, pattern_box, mirror=False),
            metadata_lines=(*base_metadata, "Page: front"),
            metadata_start_x=METADATA_MARGIN_X_PT,
            metadata_start_y=pattern_box.bottom - METADATA_TOP_GAP_PT,
            metadata_leading=METADATA_LEADING_PT,
        ),
        PrintablePagePlan(
            page_width=A4_PAGE_WIDTH_PT,
            page_height=A4_PAGE_HEIGHT_PT,
            pattern_box=pattern_box,
            segments=_pattern_segments(pattern, pattern_box, mirror=True),
            metadata_lines=(
                *base_metadata,
                "Page: mirrored back for duplex printing",
            ),
            metadata_start_x=METADATA_MARGIN_X_PT,
            metadata_start_y=pattern_box.bottom - METADATA_TOP_GAP_PT,
            metadata_leading=METADATA_LEADING_PT,
        ),
    )


def write_printable_pdf(
    pattern: cp.CreasePattern,
    destination: Path,
    *,
    extra_metadata_lines: tuple[str, ...] = (),
) -> None:
    if reportlab_canvas is None:
        raise RuntimeError(
            "PDF export requires the optional 'reportlab' dependency."
        )

    plans = build_printable_page_plans(
        pattern,
        destination.name,
        extra_metadata_lines=extra_metadata_lines,
    )
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)

    pdf = reportlab_canvas.Canvas(
        str(destination),
        pagesize=(A4_PAGE_WIDTH_PT, A4_PAGE_HEIGHT_PT),
        pageCompression=1,
    )
    pdf.setTitle(destination.stem)
    pdf.setAuthor("CP Generator")

    for plan in plans:
        _draw_page_plan(pdf, plan)
        pdf.showPage()

    pdf.save()


def write_session_json(payload: dict[str, object], destination: Path) -> None:
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _pattern_segments(
    pattern: cp.CreasePattern,
    pattern_box: PatternBox,
    *,
    mirror: bool,
) -> tuple[StrokeSegment, ...]:
    side = float(pattern.side or 1.0)
    if side <= 0.0:
        side = 1.0

    inset = pattern_box.stroke_width / 2.0
    draw_size = pattern_box.size - pattern_box.stroke_width
    vertex_index = {vertex: index for index, vertex in enumerate(pattern.vertices)}
    ordered_folds = sorted(
        pattern.folds,
        key=lambda fold: tuple(sorted((vertex_index[fold.v1], vertex_index[fold.v2]))),
    )

    def project(vertex: cp.Vertex) -> tuple[float, float]:
        scaled_x = (float(vertex.x) / side) * draw_size
        if mirror:
            scaled_x = draw_size - scaled_x
        scaled_y = (float(vertex.y) / side) * draw_size
        return (
            pattern_box.left + inset + scaled_x,
            pattern_box.bottom + inset + scaled_y,
        )

    return tuple(
        StrokeSegment(
            x1=project(fold.v1)[0],
            y1=project(fold.v1)[1],
            x2=project(fold.v2)[0],
            y2=project(fold.v2)[1],
            color=_fold_color_hex(fold.type),
            width=CREASE_WIDTH_PT,
        )
        for fold in ordered_folds
    )


def _draw_page_plan(pdf, plan: PrintablePagePlan) -> None:
    pdf.setLineCap(1)
    pdf.setLineJoin(1)
    for segment in plan.segments:
        red, green, blue = _hex_to_rgb(segment.color)
        pdf.setStrokeColorRGB(red, green, blue)
        pdf.setLineWidth(segment.width)
        pdf.line(segment.x1, segment.y1, segment.x2, segment.y2)

    pdf.setStrokeColorRGB(0.0, 0.0, 0.0)
    pdf.setLineWidth(plan.pattern_box.stroke_width)

    inset = plan.pattern_box.stroke_width / 2.0
    left = plan.pattern_box.left + inset
    bottom = plan.pattern_box.bottom + inset
    right = plan.pattern_box.left + plan.pattern_box.size - inset
    top = plan.pattern_box.bottom + plan.pattern_box.size - inset
    pdf.line(left, bottom, right, bottom)
    pdf.line(right, bottom, right, top)
    pdf.line(right, top, left, top)
    pdf.line(left, top, left, bottom)

    pdf.setFillColorRGB(0.10, 0.10, 0.10)
    pdf.setFont("Courier", 10)
    cursor_y = plan.metadata_start_y
    for line in plan.metadata_lines:
        pdf.drawString(plan.metadata_start_x, cursor_y, line)
        cursor_y -= plan.metadata_leading


def _extension_for_kind(kind: BatchSaveKind) -> str:
    if kind == "pdf":
        return ".pdf"
    return ".cpfold.json"


def _parse_vertex_target(raw: str) -> int:
    target = int(raw.strip())
    if target < 4:
        raise ValueError("Vertex targets must be at least 4.")
    return target


def _fold_color_hex(fold_type: int) -> str:
    if fold_type == 0:
        return "#c62828"
    if fold_type == 1:
        return "#1565c0"
    return "#222222"


def _hex_to_rgb(color: str) -> tuple[float, float, float]:
    return (
        int(color[1:3], 16) / 255.0,
        int(color[3:5], 16) / 255.0,
        int(color[5:7], 16) / 255.0,
    )
