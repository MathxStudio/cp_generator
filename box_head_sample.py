from __future__ import annotations

import cp


BOX_HEAD_TITLE = "Box Head - 16x16 Grid"
BOX_HEAD_KEY = "box_head"
BOX_HEAD_SIDE = 16.0


MOUNTAIN = 0
VALLEY = 1


def build_box_head_pattern() -> cp.CreasePattern:
    pattern = cp.CreasePattern()
    pattern.side = BOX_HEAD_SIDE

    vertices: dict[tuple[int, int], cp.Vertex] = {}

    def vertex(x: int, y: int) -> cp.Vertex:
        key = (x, y)
        existing = vertices.get(key)
        if existing is not None:
            return existing
        pattern.add_vertex(float(x), float(y))
        created = next(item for item in pattern.vertices if item.x == float(x) and item.y == float(y))
        vertices[key] = created
        return created

    def add(x1: int, y1: int, x2: int, y2: int, fold_type: int) -> None:
        pattern.add_fold(vertex(x1, y1), vertex(x2, y2), fold_type)

    def add_segments(segments: tuple[tuple[int, int, int, int], ...], fold_type: int) -> None:
        for x1, y1, x2, y2 in segments:
            add(x1, y1, x2, y2, fold_type)

    # These segments were rebuilt from box_head.png and then compressed so
    # only true fold intersections become crease-pattern vertices.
    mountains = (
        (0, 4, 2, 4),
        (2, 4, 6, 4),
        (6, 4, 10, 4),
        (10, 4, 14, 4),
        (14, 4, 16, 4),
        (0, 8, 2, 8),
        (2, 8, 4, 8),
        (4, 8, 6, 8),
        (6, 8, 8, 8),
        (8, 8, 10, 8),
        (10, 8, 12, 8),
        (12, 8, 14, 8),
        (14, 8, 16, 8),
        (0, 11, 4, 11),
        (12, 11, 16, 11),
        (4, 14, 6, 14),
        (10, 14, 12, 14),
        (2, 0, 2, 4),
        (2, 4, 2, 8),
        (2, 8, 2, 9),
        (2, 13, 2, 16),
        (4, 8, 4, 11),
        (4, 11, 4, 14),
        (6, 0, 6, 4),
        (6, 4, 6, 6),
        (6, 8, 6, 14),
        (8, 8, 8, 16),
        (10, 0, 10, 4),
        (10, 4, 10, 8),
        (10, 8, 10, 14),
        (12, 8, 12, 11),
        (12, 11, 12, 14),
        (14, 0, 14, 4),
        (14, 4, 14, 8),
        (14, 8, 14, 9),
        (14, 13, 14, 16),
        (1, 12, 2, 13),
        (2, 9, 3, 10),
        (3, 7, 4, 8),
        (6, 14, 7, 15),
        (7, 7, 8, 8),
        (11, 7, 12, 8),
        (12, 14, 13, 15),
        (13, 12, 14, 13),
        (14, 9, 15, 10),
        (15, 7, 16, 8),
        (0, 8, 1, 7),
        (1, 10, 2, 9),
        (2, 13, 3, 12),
        (3, 15, 4, 14),
        (4, 8, 5, 7),
        (8, 8, 9, 7),
        (9, 15, 10, 14),
        (12, 8, 13, 7),
        (13, 10, 14, 9),
        (14, 13, 15, 12),
    )

    valleys = (
        (0, 6, 2, 6),
        (2, 6, 4, 6),
        (4, 6, 6, 6),
        (6, 6, 10, 6),
        (10, 6, 12, 6),
        (12, 6, 14, 6),
        (14, 6, 16, 6),
        (0, 7, 1, 7),
        (3, 7, 5, 7),
        (7, 7, 9, 7),
        (11, 7, 13, 7),
        (15, 7, 16, 7),
        (1, 10, 3, 10),
        (13, 10, 15, 10),
        (1, 12, 3, 12),
        (13, 12, 15, 12),
        (3, 15, 7, 15),
        (9, 15, 13, 15),
        (1, 7, 1, 10),
        (1, 12, 1, 16),
        (3, 7, 3, 10),
        (3, 12, 3, 15),
        (5, 7, 5, 13),
        (6, 6, 6, 8),
        (7, 7, 7, 15),
        (9, 7, 9, 15),
        (11, 7, 11, 13),
        (13, 7, 13, 10),
        (13, 12, 13, 15),
        (15, 7, 15, 10),
        (15, 12, 15, 16),
        (0, 11, 1, 12),
        (2, 4, 4, 6),
        (2, 6, 3, 7),
        (3, 10, 4, 11),
        (5, 13, 6, 14),
        (6, 6, 7, 7),
        (7, 15, 8, 16),
        (10, 4, 12, 6),
        (10, 6, 11, 7),
        (11, 13, 12, 14),
        (12, 11, 13, 12),
        (13, 15, 14, 16),
        (14, 4, 16, 6),
        (14, 6, 15, 7),
        (15, 10, 16, 11),
        (0, 6, 2, 4),
        (0, 11, 1, 10),
        (1, 7, 2, 6),
        (2, 16, 3, 15),
        (3, 12, 4, 11),
        (4, 6, 6, 4),
        (4, 14, 5, 13),
        (5, 7, 6, 6),
        (8, 16, 9, 15),
        (9, 7, 10, 6),
        (10, 14, 11, 13),
        (12, 6, 14, 4),
        (12, 11, 13, 10),
        (13, 7, 14, 6),
        (15, 12, 16, 11),
    )

    add_segments(mountains, MOUNTAIN)
    add_segments(valleys, VALLEY)

    return pattern
