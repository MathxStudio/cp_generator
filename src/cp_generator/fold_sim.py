from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, replace
import math

import numpy as np
from scipy.optimize import least_squares
from scipy.spatial import Delaunay, QhullError
from scipy.spatial.transform import Rotation, Slerp

from . import core as cp


BOUNDARY = "boundary"
FOLD = "fold"
PREVIEW_MOTION_LEGACY_LAYERED = "legacy_layered"
PREVIEW_MOTION_BALANCED_STACK = "balanced_stack"
PREVIEW_MOTION_RIGID_PANELS = "rigid_panels"
DEFAULT_PREVIEW_MOTION_PROFILE = PREVIEW_MOTION_LEGACY_LAYERED
SEAMLESS_RIGID_SAMPLE_COUNT = 41


class FoldSimulationError(RuntimeError):
    pass


@dataclass(frozen=True)
class PreviewMotionProfileSpec:
    key: str
    label: str
    description: str


@dataclass(frozen=True)
class SimulationEdge:
    a: int
    b: int
    kind: str
    fold_type: int | None = None
    boundary_group: int | None = None

    @property
    def key(self) -> tuple[int, int]:
        return tuple(sorted((self.a, self.b)))


@dataclass(frozen=True)
class SimulationFace:
    vertices: tuple[int, ...]
    area: float
    triangles: tuple[tuple[int, int, int], ...]


@dataclass(frozen=True)
class FaceRenderState:
    index: int
    points: np.ndarray
    triangles: tuple[tuple[int, int, int], ...]
    top_surface: bool


@dataclass(frozen=True)
class FoldSimulationDiagnostic:
    status: str
    face_count: int | None
    uses_provisional_signs: bool
    uses_approximate_cycles: bool
    cycle_drift: float | None
    crossing_fold_pairs: tuple[tuple[int, int], ...]
    message: str
    preview_mode: str = "none"
    used_reference_pattern: bool = False
    basis: str = "not_run"
    heuristic_reasons: tuple[str, ...] = ()


EXACT_PREVIEW_MOTION_PROFILES = (
    PreviewMotionProfileSpec(
        key=PREVIEW_MOTION_LEGACY_LAYERED,
        label="Legacy layered",
        description="Uses the original dissected fold preview and separated flat stack from the prior release.",
    ),
    PreviewMotionProfileSpec(
        key=PREVIEW_MOTION_BALANCED_STACK,
        label="Balanced stack",
        description="Closes seams during motion and keeps a modest display thickness at the finish.",
    ),
    PreviewMotionProfileSpec(
        key=PREVIEW_MOTION_RIGID_PANELS,
        label="Seamless rigid",
        description="Projects the exact fold motion onto a connected rigid-face path and lands on the complete folded figure.",
    ),
)
MESH_PREVIEW_MOTION_PROFILES = (
    EXACT_PREVIEW_MOTION_PROFILES[0],
    EXACT_PREVIEW_MOTION_PROFILES[1],
)
PREVIEW_MOTION_PROFILE_BY_KEY = {
    spec.key: spec
    for spec in EXACT_PREVIEW_MOTION_PROFILES
}


def preview_motion_profiles(
    *,
    is_mesh_approximation: bool,
) -> tuple[PreviewMotionProfileSpec, ...]:
    return (
        MESH_PREVIEW_MOTION_PROFILES
        if is_mesh_approximation
        else EXACT_PREVIEW_MOTION_PROFILES
    )


def resolve_motion_profile(
    requested: str | None,
    supported: tuple[str, ...],
) -> str:
    if requested in supported:
        return requested
    if DEFAULT_PREVIEW_MOTION_PROFILE in supported:
        return DEFAULT_PREVIEW_MOTION_PROFILE
    if supported:
        return supported[0]
    return DEFAULT_PREVIEW_MOTION_PROFILE


def motion_profile_label(key: str) -> str:
    spec = PREVIEW_MOTION_PROFILE_BY_KEY.get(key)
    if spec is not None:
        return spec.label
    return key.replace("_", " ").title()


def motion_profile_description(key: str) -> str:
    spec = PREVIEW_MOTION_PROFILE_BY_KEY.get(key)
    return "" if spec is None else spec.description


class FoldedFigureModel:
    def __init__(
        self,
        coords: np.ndarray,
        faces: tuple[SimulationFace, ...],
        flat_transforms: tuple[np.ndarray, ...],
        tree_order: tuple[int, ...],
        tree_parent: tuple[int | None, ...],
        parent_edges: tuple[tuple[int, int] | None, ...],
        edge_lookup: dict[tuple[int, int], SimulationEdge],
        face_edge_directions: dict[tuple[int, tuple[int, int]], tuple[int, int]],
        fold_signs: dict[tuple[int, int], float],
        uses_provisional_signs: bool,
        uses_approximate_cycles: bool,
        cycle_drift: float,
    ):
        self.coords = coords
        self.faces = faces
        self.flat_transforms = flat_transforms
        self.tree_order = tree_order
        self.tree_parent = tree_parent
        self.parent_edges = parent_edges
        self.edge_lookup = edge_lookup
        self.face_edge_directions = face_edge_directions
        self.fold_signs = fold_signs
        self.uses_provisional_signs = uses_provisional_signs
        self.uses_approximate_cycles = uses_approximate_cycles
        self.cycle_drift = cycle_drift
        self.face_count = len(faces)
        self.face_edge_keys = _build_face_edge_keys(faces)
        self.edge_render_kind = {edge_key: edge.kind for edge_key, edge in edge_lookup.items()}
        self.edge_boundary_groups = {
            edge_key: edge.boundary_group
            for edge_key, edge in edge_lookup.items()
            if edge.boundary_group is not None
        }
        self.max_angle = math.pi - 0.1
        self.supported_motion_profiles = tuple(
            spec.key for spec in preview_motion_profiles(is_mesh_approximation=False)
        )
        self.source_face_points = _build_source_face_points(coords, faces)
        self.vertex_occurrences = _build_vertex_occurrences(faces, len(coords))
        self.top_surface_flags = tuple(
            bool(np.linalg.det(transform[:2, :2]) > 0)
            for transform in flat_transforms
        )
        self.layer_offsets = self._build_layer_offsets(
            thickness_divisor=18.0,
            minimum_thickness=0.02,
        )
        self.final_face_points = self._build_final_face_points(self.layer_offsets)
        self._balanced_layer_offsets = self._build_layer_offsets(
            thickness_divisor=220.0,
            minimum_thickness=0.006,
        )
        self._balanced_stack_face_points = self._build_final_face_points(
            self._balanced_layer_offsets
        )
        self._exact_folded_face_points = self.face_points_at_angle(math.pi)
        self._closed_face_points = self._relaxed_face_points(
            self.face_points_at_angle(self.max_angle),
            iterations=6,
            strength=0.9,
        )
        self._balanced_final_face_points = _blend_face_points(
            self._closed_face_points,
            self._balanced_stack_face_points,
            0.36,
        )
        self.final_centroid = self._compute_overall_centroid(self.final_face_points)
        self.is_mesh_approximation = False
        self._seamless_rigid_progress_samples = np.linspace(
            0.0,
            1.0,
            SEAMLESS_RIGID_SAMPLE_COUNT,
            dtype=float,
        )
        self._seamless_rigid_rotvec_samples: np.ndarray | None = None
        self._seamless_rigid_translation_samples: np.ndarray | None = None
        self._seamless_rigid_available = True

    def _build_layer_offsets(
        self,
        *,
        thickness_divisor: float,
        minimum_thickness: float,
    ) -> tuple[float, ...]:
        nearly_flat = self._pose_tree(math.pi - 0.08)
        scores: list[tuple[float, float, float, int]] = []
        for index, face in enumerate(self.faces):
            points = np.array([_apply_transform_3d(nearly_flat[index], self.coords[i]) for i in face.vertices])
            centroid = points.mean(axis=0)
            scores.append((centroid[2], centroid[1], centroid[0], index))

        scores.sort()
        span = float(np.ptp(self.coords[:, 0]) + np.ptp(self.coords[:, 1]))
        thickness = max(
            span / max(len(self.faces) * thickness_divisor, 1.0),
            minimum_thickness,
        )
        offsets = [0.0] * len(self.faces)
        for rank, (_, _, _, index) in enumerate(scores):
            offsets[index] = rank * thickness

        if offsets:
            center = 0.5 * (min(offsets) + max(offsets))
            offsets = [value - center for value in offsets]
        return tuple(offsets)

    def face_points_at_angle(self, angle: float) -> tuple[np.ndarray, ...]:
        posed_transforms = self._pose_tree(angle)
        points_by_face: list[np.ndarray] = []
        for index, face in enumerate(self.faces):
            face_points = []
            for vertex_index in face.vertices:
                face_points.append(
                    _apply_transform_3d(posed_transforms[index], self.coords[vertex_index])
                )
            points_by_face.append(np.array(face_points, dtype=float))
        return tuple(points_by_face)

    def _relaxed_face_points(
        self,
        points_by_face: tuple[np.ndarray, ...],
        *,
        iterations: int,
        strength: float,
    ) -> tuple[np.ndarray, ...]:
        return _relax_face_points(
            points_by_face,
            self.faces,
            self.source_face_points,
            self.vertex_occurrences,
            iterations=iterations,
            strength=strength,
        )

    def _build_final_face_points(
        self,
        layer_offsets: tuple[float, ...],
    ) -> tuple[np.ndarray, ...]:
        states: list[np.ndarray] = []
        for index, face in enumerate(self.faces):
            flat_points = []
            for vertex_index in face.vertices:
                point = _apply_transform_2d(self.flat_transforms[index], self.coords[vertex_index])
                flat_points.append([point[0], point[1], layer_offsets[index]])
            states.append(np.array(flat_points, dtype=float))
        return tuple(states)

    def _compute_overall_centroid(self, states: tuple[np.ndarray, ...]) -> np.ndarray:
        all_points = np.concatenate(states, axis=0)
        return all_points.mean(axis=0)

    def _pose_tree(self, angle: float) -> tuple[np.ndarray, ...]:
        transforms: list[np.ndarray | None] = [None] * self.face_count
        if not transforms:
            return tuple()

        transforms[self.tree_order[0]] = np.identity(4)
        for face_index in self.tree_order[1:]:
            parent = self.tree_parent[face_index]
            if parent is None:
                raise FoldSimulationError("Fold tree is incomplete.")
            edge_key = self.parent_edges[face_index]
            if edge_key is None:
                raise FoldSimulationError("Missing parent edge for folded face.")

            parent_transform = transforms[parent]
            if parent_transform is None:
                raise FoldSimulationError("Parent transform was not initialized.")

            u, v = self.face_edge_directions[(parent, edge_key)]
            p = _apply_transform_3d(parent_transform, self.coords[u])
            q = _apply_transform_3d(parent_transform, self.coords[v])
            sign = self.fold_signs.get(edge_key, 1.0)
            rotation = _rotation_about_axis(p, q, sign * angle)
            transforms[face_index] = rotation @ parent_transform

        return tuple(transform for transform in transforms if transform is not None)

    def _render_states(
        self,
        points_by_face: tuple[np.ndarray, ...],
    ) -> tuple[FaceRenderState, ...]:
        states: list[FaceRenderState] = []
        for index, face in enumerate(self.faces):
            states.append(
                FaceRenderState(
                    index=index,
                    points=points_by_face[index],
                    triangles=face.triangles,
                    top_surface=self.top_surface_flags[index],
                )
            )
        return tuple(states)

    def _legacy_rigid_panel_face_points(
        self,
        progress: float,
        posed_points: tuple[np.ndarray, ...],
    ) -> tuple[np.ndarray, ...]:
        return self._relaxed_face_points(
            posed_points,
            iterations=4 if progress < 0.85 else 6,
            strength=0.94,
        )

    def _ensure_seamless_rigid_motion(self) -> None:
        if self._seamless_rigid_rotvec_samples is not None:
            return
        if not self._seamless_rigid_available:
            return

        try:
            sample_count = len(self._seamless_rigid_progress_samples)
            rotvec_samples = np.zeros((sample_count, self.face_count, 3), dtype=float)
            translation_samples = np.zeros((sample_count, self.face_count, 3), dtype=float)
            if self.face_count <= 1:
                self._seamless_rigid_rotvec_samples = rotvec_samples
                self._seamless_rigid_translation_samples = translation_samples
                return

            root_face = self.tree_order[0]
            non_root_faces = tuple(
                face_index for face_index in range(self.face_count) if face_index != root_face
            )
            if not non_root_faces:
                self._seamless_rigid_rotvec_samples = rotvec_samples
                self._seamless_rigid_translation_samples = translation_samples
                return

            final_rotations, final_translations = _fit_face_transforms(
                self.source_face_points,
                self._exact_folded_face_points,
            )
            final_parameters = _pack_face_transform_parameters(
                final_rotations,
                final_translations,
                non_root_faces,
            )
            parameters = np.zeros_like(final_parameters)

            for sample_index, raw_progress in enumerate(self._seamless_rigid_progress_samples):
                if sample_index == 0:
                    rotations, translations = _unpack_face_transform_parameters(
                        parameters,
                        self.face_count,
                        root_face,
                        non_root_faces,
                    )
                elif sample_index == sample_count - 1:
                    rotations = final_rotations
                    translations = final_translations
                else:
                    if raw_progress > 0.84:
                        parameters = (1.0 - raw_progress) * parameters + raw_progress * final_parameters
                    guide_points = self.face_points_at_angle(math.pi * _ease_in_out(float(raw_progress)))
                    result = least_squares(
                        _rigid_projection_residuals,
                        parameters,
                        args=(
                            guide_points,
                            self.source_face_points,
                            self.vertex_occurrences,
                            root_face,
                            non_root_faces,
                            130.0,
                            0.34,
                        ),
                        max_nfev=400,
                        xtol=1e-10,
                        ftol=1e-10,
                        gtol=1e-10,
                    )
                    parameters = result.x
                    rotations, translations = _unpack_face_transform_parameters(
                        parameters,
                        self.face_count,
                        root_face,
                        non_root_faces,
                    )
                    projected_points = _apply_face_transforms(
                        self.source_face_points,
                        rotations,
                        translations,
                    )
                    if (
                        not result.success
                        or _max_shared_edge_gap(self.face_edge_keys, projected_points) > 0.02
                    ):
                        self._seamless_rigid_available = False
                        return

                rotvec_samples[sample_index] = np.array(
                    [Rotation.from_matrix(rotation).as_rotvec() for rotation in rotations],
                    dtype=float,
                )
                translation_samples[sample_index] = np.array(translations, dtype=float)

            self._seamless_rigid_rotvec_samples = rotvec_samples
            self._seamless_rigid_translation_samples = translation_samples
        except Exception:
            self._seamless_rigid_available = False

    def _seamless_rigid_face_points(
        self,
        progress: float,
    ) -> tuple[np.ndarray, ...] | None:
        self._ensure_seamless_rigid_motion()
        if (
            self._seamless_rigid_rotvec_samples is None
            or self._seamless_rigid_translation_samples is None
        ):
            return None

        progress = min(max(progress, 0.0), 1.0)
        if progress <= 0.0:
            return tuple(np.array(points, dtype=float, copy=True) for points in self.source_face_points)
        if progress >= 1.0:
            return tuple(
                np.array(points, dtype=float, copy=True)
                for points in self._exact_folded_face_points
            )

        upper_index = int(np.searchsorted(self._seamless_rigid_progress_samples, progress, side="right"))
        lower_index = max(0, upper_index - 1)
        upper_index = min(upper_index, len(self._seamless_rigid_progress_samples) - 1)

        left_progress = float(self._seamless_rigid_progress_samples[lower_index])
        right_progress = float(self._seamless_rigid_progress_samples[upper_index])
        if upper_index == lower_index or right_progress - left_progress <= 1e-12:
            return _apply_face_transform_samples(
                self.source_face_points,
                self._seamless_rigid_rotvec_samples[lower_index],
                self._seamless_rigid_translation_samples[lower_index],
            )

        weight = (progress - left_progress) / (right_progress - left_progress)
        return _interpolate_face_transform_samples(
            self.source_face_points,
            self._seamless_rigid_rotvec_samples[lower_index],
            self._seamless_rigid_translation_samples[lower_index],
            self._seamless_rigid_rotvec_samples[upper_index],
            self._seamless_rigid_translation_samples[upper_index],
            weight,
        )

    def frame(
        self,
        progress: float,
        motion_profile: str = DEFAULT_PREVIEW_MOTION_PROFILE,
    ) -> tuple[FaceRenderState, ...]:
        progress = min(max(progress, 0.0), 1.0)
        if not self.faces:
            return tuple()

        motion_profile = resolve_motion_profile(
            motion_profile,
            self.supported_motion_profiles,
        )
        eased = _ease_in_out(progress)
        posed_points = self.face_points_at_angle(self.max_angle * eased)

        if motion_profile == PREVIEW_MOTION_LEGACY_LAYERED:
            settle = _smoothstep(0.72, 1.0, progress)
            return self._render_states(
                _blend_face_points(posed_points, self.final_face_points, settle)
            )

        if motion_profile == PREVIEW_MOTION_RIGID_PANELS:
            seamless = self._seamless_rigid_face_points(progress)
            if seamless is not None:
                return self._render_states(seamless)
            return self._render_states(
                self._legacy_rigid_panel_face_points(progress, posed_points)
            )

        relaxed = self._relaxed_face_points(
            posed_points,
            iterations=4 if progress < 0.65 else 5,
            strength=0.88,
        )
        settle = _smoothstep(0.76, 1.0, progress)
        return self._render_states(
            _blend_face_points(relaxed, self._balanced_final_face_points, settle)
        )


class ApproximateFoldedFigureModel:
    def __init__(
        self,
        coords: np.ndarray,
        faces: tuple[SimulationFace, ...],
        flat_transforms: tuple[np.ndarray, ...],
        tree_order: tuple[int, ...],
        tree_parent: tuple[int | None, ...],
        parent_edges: tuple[tuple[int, int] | None, ...],
        face_edge_directions: dict[tuple[int, tuple[int, int]], tuple[int, int]],
        edge_angles: dict[tuple[int, int], float],
        edge_is_fold: dict[tuple[int, int], bool],
        uses_provisional_signs: bool,
        settle_to_flat: bool = True,
        final_angle_scale: float = 1.0,
    ):
        self.coords = coords
        self.faces = faces
        self.flat_transforms = flat_transforms
        self.tree_order = tree_order
        self.tree_parent = tree_parent
        self.parent_edges = parent_edges
        self.face_edge_directions = face_edge_directions
        self.edge_angles = edge_angles
        self.edge_is_fold = edge_is_fold
        self.uses_provisional_signs = uses_provisional_signs
        self.uses_approximate_cycles = True
        self.cycle_drift = 0.0
        self.is_mesh_approximation = True
        self.settle_to_flat = settle_to_flat
        self.final_angle_scale = final_angle_scale
        self.face_count = len(faces)
        self.face_edge_keys = _build_face_edge_keys(faces)
        self.supported_motion_profiles = tuple(
            spec.key for spec in preview_motion_profiles(is_mesh_approximation=True)
        )
        self.source_face_points = _build_source_face_points(coords, faces)
        self.vertex_occurrences = _build_vertex_occurrences(faces, len(coords))
        self.top_surface_flags = tuple(
            bool(np.linalg.det(transform[:2, :2]) > 0)
            for transform in flat_transforms
        )
        self.edge_render_kind: dict[tuple[int, int], str] = {}
        self.edge_boundary_groups: dict[tuple[int, int], int] = {}
        self.max_angle = math.radians(76 if settle_to_flat else 88)
        self.layer_offsets = self._build_layer_offsets(
            thickness_divisor=30.0,
            minimum_thickness=0.02,
        )
        self.final_face_points = self._build_final_face_points(self.layer_offsets)
        self._balanced_layer_offsets = self._build_layer_offsets(
            thickness_divisor=280.0,
            minimum_thickness=0.004,
        )
        self._balanced_stack_face_points = self._build_final_face_points(
            self._balanced_layer_offsets
        )
        closed_angle_scale = self.max_angle * (
            self.final_angle_scale if not self.settle_to_flat else 1.0
        )
        self._closed_face_points = self._relaxed_face_points(
            self._pose_points(closed_angle_scale),
            iterations=4,
            strength=0.88,
        )
        balanced_blend = 0.44 if self.settle_to_flat else 0.18
        self._balanced_final_face_points = _blend_face_points(
            self._closed_face_points,
            self._balanced_stack_face_points,
            balanced_blend,
        )
        self.final_centroid = self._compute_overall_centroid(self.final_face_points)

    def _build_layer_offsets(
        self,
        *,
        thickness_divisor: float,
        minimum_thickness: float,
    ) -> tuple[float, ...]:
        offsets = [0.0] * len(self.faces)
        depth_map = {self.tree_order[0]: 0} if self.tree_order else {}
        for face_index in self.tree_order[1:]:
            parent = self.tree_parent[face_index]
            edge_key = self.parent_edges[face_index]
            increment = 1 if edge_key is not None and self.edge_is_fold.get(edge_key, False) else 0
            depth_map[face_index] = depth_map.get(parent, 0) + increment
        span = float(max(np.ptp(self.coords[:, 0]), np.ptp(self.coords[:, 1]), 1.0))
        thickness = max(
            span / max(len(self.faces) * thickness_divisor, 1.0),
            minimum_thickness,
        )
        for index in range(len(self.faces)):
            offsets[index] = depth_map.get(index, 0) * thickness
        if offsets:
            center = 0.5 * (min(offsets) + max(offsets))
            offsets = [value - center for value in offsets]
        return tuple(offsets)

    def _compute_overall_centroid(self, states: tuple[np.ndarray, ...]) -> np.ndarray:
        all_points = np.concatenate(states, axis=0)
        return all_points.mean(axis=0)

    def _pose_tree(self, angle_scale: float) -> tuple[np.ndarray, ...]:
        transforms: list[np.ndarray | None] = [None] * self.face_count
        if not transforms:
            return tuple()

        transforms[self.tree_order[0]] = np.identity(4)
        for face_index in self.tree_order[1:]:
            parent = self.tree_parent[face_index]
            edge_key = self.parent_edges[face_index]
            if parent is None or edge_key is None:
                raise FoldSimulationError("Approximate fold tree is incomplete.")
            parent_transform = transforms[parent]
            if parent_transform is None:
                raise FoldSimulationError("Approximate parent transform was not initialized.")

            if self.edge_is_fold.get(edge_key, False):
                u, v = self.face_edge_directions[(parent, edge_key)]
                p = _apply_transform_3d(parent_transform, self.coords[u])
                q = _apply_transform_3d(parent_transform, self.coords[v])
                angle = angle_scale * self.edge_angles.get(edge_key, 0.0)
                rotation = _rotation_about_axis(p, q, angle)
                transforms[face_index] = rotation @ parent_transform
            else:
                transforms[face_index] = parent_transform.copy()

        return tuple(transform for transform in transforms if transform is not None)

    def _build_final_face_points(
        self,
        layer_offsets: tuple[float, ...],
    ) -> tuple[np.ndarray, ...]:
        if not self.settle_to_flat:
            transforms = self._pose_tree(self.max_angle * self.final_angle_scale)
            states: list[np.ndarray] = []
            for index, face in enumerate(self.faces):
                pose_points = []
                depth_offset = layer_offsets[index]
                for vertex_index in face.vertices:
                    point = _apply_transform_3d(transforms[index], self.coords[vertex_index]).copy()
                    point[2] += depth_offset
                    pose_points.append(point)
                states.append(np.array(pose_points, dtype=float))
            return tuple(states)

        states: list[np.ndarray] = []
        for index, face in enumerate(self.faces):
            flat_points = []
            for vertex_index in face.vertices:
                point = _apply_transform_2d(self.flat_transforms[index], self.coords[vertex_index])
                flat_points.append([point[0], point[1], layer_offsets[index]])
            states.append(np.array(flat_points, dtype=float))
        return tuple(states)

    def _pose_points(self, angle_scale: float) -> tuple[np.ndarray, ...]:
        transforms = self._pose_tree(angle_scale)
        points_by_face: list[np.ndarray] = []
        for index, face in enumerate(self.faces):
            pose_points = []
            for vertex_index in face.vertices:
                point = _apply_transform_3d(transforms[index], self.coords[vertex_index]).copy()
                pose_points.append(point)
            points_by_face.append(np.array(pose_points, dtype=float))
        return tuple(points_by_face)

    def _relaxed_face_points(
        self,
        points_by_face: tuple[np.ndarray, ...],
        *,
        iterations: int,
        strength: float,
    ) -> tuple[np.ndarray, ...]:
        return _relax_face_points(
            points_by_face,
            self.faces,
            self.source_face_points,
            self.vertex_occurrences,
            iterations=iterations,
            strength=strength,
        )

    def _render_states(
        self,
        points_by_face: tuple[np.ndarray, ...],
    ) -> tuple[FaceRenderState, ...]:
        states: list[FaceRenderState] = []
        for index, face in enumerate(self.faces):
            states.append(
                FaceRenderState(
                    index=index,
                    points=points_by_face[index],
                    triangles=face.triangles,
                    top_surface=self.top_surface_flags[index],
                )
            )
        return tuple(states)

    def frame(
        self,
        progress: float,
        motion_profile: str = DEFAULT_PREVIEW_MOTION_PROFILE,
    ) -> tuple[FaceRenderState, ...]:
        progress = min(max(progress, 0.0), 1.0)
        if not self.faces:
            return tuple()

        motion_profile = resolve_motion_profile(
            motion_profile,
            self.supported_motion_profiles,
        )
        eased = _ease_in_out(progress)
        posed_points = self._pose_points(self.max_angle * eased)

        if motion_profile == PREVIEW_MOTION_LEGACY_LAYERED:
            settle = _smoothstep(0.70, 1.0, progress)
            if not self.settle_to_flat:
                settle = _smoothstep(0.82, 1.0, progress)
            return self._render_states(
                _blend_face_points(posed_points, self.final_face_points, settle)
            )

        relaxed = self._relaxed_face_points(
            posed_points,
            iterations=3 if progress < 0.65 else 4,
            strength=0.82,
        )
        settle = _smoothstep(0.72, 1.0, progress)
        if not self.settle_to_flat:
            settle = _smoothstep(0.84, 1.0, progress)
        return self._render_states(
            _blend_face_points(relaxed, self._balanced_final_face_points, settle)
        )


def build_folded_figure(pattern: cp.CreasePattern) -> FoldedFigureModel:
    if not pattern.folds:
        raise FoldSimulationError("Generate a crease pattern with interior folds first.")

    graph = _build_simulation_graph(pattern)
    faces, face_edge_directions = _extract_faces(graph["coords"], graph["adjacency"], graph["edges"])
    if not faces:
        raise FoldSimulationError("No interior faces were found for this crease pattern.")

    flat_transforms, tree_order, tree_parent, parent_edges, uses_approximate_cycles, cycle_drift = _build_face_transforms(
        graph["coords"],
        faces,
        graph["edges"],
        face_edge_directions,
    )
    fold_signs, uses_provisional_signs = _resolve_fold_signs(
        faces,
        tree_order,
        tree_parent,
        parent_edges,
        graph["edges"],
    )

    return FoldedFigureModel(
        coords=graph["coords"],
        faces=faces,
        flat_transforms=flat_transforms,
        tree_order=tree_order,
        tree_parent=tree_parent,
        parent_edges=parent_edges,
        edge_lookup=graph["edges"],
        face_edge_directions=face_edge_directions,
        fold_signs=fold_signs,
        uses_provisional_signs=uses_provisional_signs,
        uses_approximate_cycles=uses_approximate_cycles,
        cycle_drift=cycle_drift,
    )


def try_build_folded_figure(
    pattern: cp.CreasePattern,
) -> tuple[FoldedFigureModel | None, FoldSimulationDiagnostic]:
    try:
        model = build_folded_figure(pattern)
    except FoldSimulationError as exc:
        return None, FoldSimulationDiagnostic(
            status=cp.STATUS_FAIL,
            face_count=None,
            uses_provisional_signs=False,
            uses_approximate_cycles=False,
            cycle_drift=None,
            crossing_fold_pairs=pattern.crossing_fold_pairs(),
            message=str(exc),
            preview_mode="none",
            used_reference_pattern=False,
        )

    if model.uses_provisional_signs or model.uses_approximate_cycles:
        status = cp.STATUS_WARNING
        if model.uses_provisional_signs and model.uses_approximate_cycles:
            message = "Exact face reconstruction succeeded with provisional signs and approximate cycle closure."
        elif model.uses_provisional_signs:
            message = "Exact face reconstruction succeeded, but some fold signs were inferred provisionally."
        else:
            message = "Exact face reconstruction succeeded, but face-cycle closure remained approximate."
    else:
        status = cp.STATUS_PASS
        message = "Exact face reconstruction succeeded."

    return model, FoldSimulationDiagnostic(
        status=status,
        face_count=model.face_count,
        uses_provisional_signs=model.uses_provisional_signs,
        uses_approximate_cycles=model.uses_approximate_cycles,
        cycle_drift=model.cycle_drift,
        crossing_fold_pairs=pattern.crossing_fold_pairs(),
        message=message,
        preview_mode="exact",
        used_reference_pattern=False,
    )


def analyze_foldability(pattern: cp.CreasePattern) -> FoldSimulationDiagnostic:
    _, diagnostic = try_build_folded_figure(pattern)
    return diagnostic


def with_basis(
    diagnostic: FoldSimulationDiagnostic,
    *,
    basis: str,
    heuristic_reasons: tuple[str, ...] = (),
) -> FoldSimulationDiagnostic:
    return replace(
        diagnostic,
        basis=basis,
        heuristic_reasons=heuristic_reasons,
    )


def build_approximate_folded_figure(pattern: cp.CreasePattern) -> ApproximateFoldedFigureModel:
    return build_approximate_folded_figure_with_mode(pattern, spatial_mode=False)


def build_approximate_folded_figure_with_mode(
    pattern: cp.CreasePattern,
    spatial_mode: bool = False,
) -> ApproximateFoldedFigureModel:
    if len(pattern.vertices) < 3 or not pattern.folds:
        raise FoldSimulationError("Generate a crease pattern with interior folds first.")

    coords = np.array([[float(vertex.x), float(vertex.y)] for vertex in pattern.vertices], dtype=float)
    epsilon = max(1e-6 * float(pattern.side or 1.0), 1e-6)

    def find_or_add(point: tuple[float, float]) -> int:
        nonlocal coords
        if len(coords) == 0:
            coords = np.array([point], dtype=float)
            return 0
        distances = np.linalg.norm(coords - np.array(point, dtype=float), axis=1)
        match = np.where(distances <= epsilon)[0]
        if match.size:
            return int(match[0])
        coords = np.vstack([coords, np.array(point, dtype=float)])
        return len(coords) - 1

    side = float(pattern.side or 1.0)
    for corner in ((0.0, 0.0), (side, 0.0), (side, side), (0.0, side)):
        find_or_add(corner)

    try:
        simplices = Delaunay(coords).simplices
    except QhullError as exc:
        raise FoldSimulationError("The preview mesh could not be triangulated for 3D rendering.") from exc

    faces: list[SimulationFace] = []
    face_edge_directions: dict[tuple[int, tuple[int, int]], tuple[int, int]] = {}
    for simplex in simplices:
        face = tuple(int(index) for index in simplex)
        area = _signed_area(coords, face)
        if abs(area) <= 1e-10:
            continue
        if area < 0:
            face = (face[0], face[2], face[1])
            area = -area
        face_index = len(faces)
        faces.append(SimulationFace(vertices=face, area=area, triangles=((0, 1, 2),)))
        for a, b in zip(face, face[1:] + face[:1]):
            face_edge_directions[(face_index, tuple(sorted((a, b))))] = (a, b)

    if not faces:
        raise FoldSimulationError("The preview mesh did not contain any renderable faces.")

    edge_to_faces: dict[tuple[int, int], list[int]] = defaultdict(list)
    for face_index, face in enumerate(faces):
        for a, b in zip(face.vertices, face.vertices[1:] + face.vertices[:1]):
            edge_to_faces[tuple(sorted((a, b)))].append(face_index)

    actual_index = {vertex: index for index, vertex in enumerate(pattern.vertices)}
    fold_types = {
        tuple(sorted((actual_index[fold.v1], actual_index[fold.v2]))): fold.type
        for fold in pattern.folds
    }

    root = _pick_mesh_root(coords, tuple(faces), float(pattern.side or 1.0))
    tree_parent: list[int | None] = [None] * len(faces)
    parent_edge: list[tuple[int, int] | None] = [None] * len(faces)
    order = [root]
    queue: deque[int] = deque([root])
    visited = {root}
    edge_angles: dict[tuple[int, int], float] = {}
    edge_is_fold: dict[tuple[int, int], bool] = {}
    face_depth = {root: 0}
    uses_provisional_signs = False

    adjacency: dict[int, list[tuple[int, tuple[int, int]]]] = defaultdict(list)
    for edge_key, face_indices in edge_to_faces.items():
        if len(face_indices) != 2:
            continue
        first, second = face_indices
        adjacency[first].append((second, edge_key))
        adjacency[second].append((first, edge_key))

    while queue:
        face_index = queue.popleft()
        for neighbor_index, edge_key in adjacency[face_index]:
            if neighbor_index in visited:
                continue
            visited.add(neighbor_index)
            tree_parent[neighbor_index] = face_index
            parent_edge[neighbor_index] = edge_key
            face_depth[neighbor_index] = face_depth.get(face_index, 0) + 1
            order.append(neighbor_index)
            queue.append(neighbor_index)

            fold_type = fold_types.get(edge_key)
            if fold_type == 0:
                edge_angles[edge_key] = 1.0
                edge_is_fold[edge_key] = True
            elif fold_type == 1:
                edge_angles[edge_key] = -1.0
                edge_is_fold[edge_key] = True
            elif fold_type is None:
                edge_angles[edge_key] = 0.0
                edge_is_fold[edge_key] = False
            else:
                edge_angles[edge_key] = 0.18 if face_depth[neighbor_index] % 2 == 0 else -0.18
                edge_is_fold[edge_key] = True
                uses_provisional_signs = True

    if len(visited) != len(faces):
        raise FoldSimulationError("The preview mesh became disconnected during 3D reconstruction.")

    flat_transforms: list[np.ndarray | None] = [None] * len(faces)
    flat_transforms[root] = np.identity(3)
    for face_index in order[1:]:
        parent = tree_parent[face_index]
        edge_key = parent_edge[face_index]
        if parent is None or edge_key is None:
            raise FoldSimulationError("Approximate flat reconstruction is incomplete.")
        parent_transform = flat_transforms[parent]
        if parent_transform is None:
            raise FoldSimulationError("Approximate flat parent transform was not initialized.")

        if edge_is_fold.get(edge_key, False):
            u, v = face_edge_directions[(parent, edge_key)]
            p = _apply_transform_2d(parent_transform, coords[u])
            q = _apply_transform_2d(parent_transform, coords[v])
            flat_transforms[face_index] = _reflection_transform_2d(p, q) @ parent_transform
        else:
            flat_transforms[face_index] = parent_transform.copy()

    if any(transform is None for transform in flat_transforms):
        raise FoldSimulationError("Approximate flat reconstruction left gaps in the triangle mesh.")

    edge_render_kind: dict[tuple[int, int], str] = {}
    for edge_key, face_indices in edge_to_faces.items():
        if len(face_indices) == 1:
            edge_render_kind[edge_key] = BOUNDARY
        elif edge_is_fold.get(edge_key, False):
            edge_render_kind[edge_key] = FOLD
        else:
            edge_render_kind[edge_key] = "mesh"

    model = ApproximateFoldedFigureModel(
        coords=coords,
        faces=tuple(faces),
        flat_transforms=tuple(transform for transform in flat_transforms if transform is not None),
        tree_order=tuple(order),
        tree_parent=tuple(tree_parent),
        parent_edges=tuple(parent_edge),
        face_edge_directions=face_edge_directions,
        edge_angles=edge_angles,
        edge_is_fold=edge_is_fold,
        uses_provisional_signs=uses_provisional_signs,
        settle_to_flat=not spatial_mode,
        final_angle_scale=0.94 if spatial_mode else 1.0,
    )
    model.edge_render_kind = edge_render_kind
    model.edge_boundary_groups = {
        edge_key: boundary_group
        for edge_key, kind in edge_render_kind.items()
        if kind == BOUNDARY
        for boundary_group in [_boundary_group_for_edge(coords, edge_key, side, epsilon)]
        if boundary_group is not None
    }
    return model


def _build_simulation_graph(pattern: cp.CreasePattern) -> dict[str, object]:
    side = float(pattern.side or 1.0)
    if side <= 0:
        side = 1.0

    epsilon = max(1e-6 * side, 1e-6)
    coords = np.array([[float(vertex.x), float(vertex.y)] for vertex in pattern.vertices], dtype=float)

    def find_or_add(point: tuple[float, float]) -> int:
        nonlocal coords
        if len(coords) == 0:
            coords = np.array([point], dtype=float)
            return 0
        distances = np.linalg.norm(coords - np.array(point, dtype=float), axis=1)
        match = np.where(distances <= epsilon)[0]
        if match.size:
            return int(match[0])
        coords = np.vstack([coords, np.array(point, dtype=float)])
        return len(coords) - 1

    corners = [
        (0.0, 0.0),
        (side, 0.0),
        (side, side),
        (0.0, side),
    ]
    for corner in corners:
        find_or_add(corner)

    actual_index = {vertex: index for index, vertex in enumerate(pattern.vertices)}
    edges: dict[tuple[int, int], SimulationEdge] = {}

    fold_segments = []
    for fold in pattern.folds:
        a = actual_index[fold.v1]
        b = actual_index[fold.v2]
        key = tuple(sorted((a, b)))
        edges[key] = SimulationEdge(a=key[0], b=key[1], kind=FOLD, fold_type=fold.type)
        fold_segments.append((key, coords[key[0]], coords[key[1]]))

    for index, (key_a, a0, a1) in enumerate(fold_segments):
        for key_b, b0, b1 in fold_segments[index + 1 :]:
            if len({key_a[0], key_a[1], key_b[0], key_b[1]}) < 4:
                continue
            if _segments_intersect(a0, a1, b0, b1, epsilon):
                raise FoldSimulationError(
                    "The optimized geometry contains crossing folds, so the folded figure would be unreliable."
                )

    adjacency: dict[int, set[int]] = defaultdict(set)

    def add_edge(
        a: int,
        b: int,
        kind: str,
        fold_type: int | None = None,
        boundary_group: int | None = None,
    ) -> None:
        if a == b:
            return
        key = tuple(sorted((a, b)))
        if key not in edges:
            edges[key] = SimulationEdge(
                a=key[0],
                b=key[1],
                kind=kind,
                fold_type=fold_type,
                boundary_group=boundary_group,
            )
        adjacency[a].add(b)
        adjacency[b].add(a)

    for edge in edges.values():
        adjacency[edge.a].add(edge.b)
        adjacency[edge.b].add(edge.a)

    boundary_groups = [
        sorted(_boundary_indices(coords, axis=1, value=0.0, epsilon=epsilon), key=lambda i: coords[i][0]),
        sorted(_boundary_indices(coords, axis=0, value=side, epsilon=epsilon), key=lambda i: coords[i][1]),
        sorted(_boundary_indices(coords, axis=1, value=side, epsilon=epsilon), key=lambda i: -coords[i][0]),
        sorted(_boundary_indices(coords, axis=0, value=0.0, epsilon=epsilon), key=lambda i: -coords[i][1]),
    ]

    for boundary_group, group in enumerate(boundary_groups):
        for a, b in zip(group, group[1:]):
            add_edge(a, b, BOUNDARY, boundary_group=boundary_group)

    return {
        "coords": coords,
        "edges": edges,
        "adjacency": adjacency,
    }


def _boundary_indices(coords: np.ndarray, axis: int, value: float, epsilon: float) -> list[int]:
    return [index for index, point in enumerate(coords) if abs(point[axis] - value) <= epsilon]


def _boundary_group_for_edge(
    coords: np.ndarray,
    edge_key: tuple[int, int],
    side: float,
    epsilon: float,
) -> int | None:
    first = coords[edge_key[0]]
    second = coords[edge_key[1]]
    if abs(first[1]) <= epsilon and abs(second[1]) <= epsilon:
        return 0
    if abs(first[0] - side) <= epsilon and abs(second[0] - side) <= epsilon:
        return 1
    if abs(first[1] - side) <= epsilon and abs(second[1] - side) <= epsilon:
        return 2
    if abs(first[0]) <= epsilon and abs(second[0]) <= epsilon:
        return 3
    return None


def _extract_faces(
    coords: np.ndarray,
    adjacency: dict[int, set[int]],
    edges: dict[tuple[int, int], SimulationEdge],
) -> tuple[tuple[SimulationFace, ...], dict[tuple[int, tuple[int, int]], tuple[int, int]]]:
    neighbor_order: dict[int, list[int]] = {}
    for index, neighbors in adjacency.items():
        ordered = sorted(
            neighbors,
            key=lambda other: math.atan2(coords[other][1] - coords[index][1], coords[other][0] - coords[index][0]),
        )
        neighbor_order[index] = ordered

    seen: set[tuple[int, int]] = set()
    raw_faces: list[tuple[int, ...]] = []

    for start_a, neighbors in neighbor_order.items():
        for start_b in neighbors:
            if (start_a, start_b) in seen:
                continue
            face: list[int] = []
            current = (start_a, start_b)
            step_limit = max(len(edges) * 4, 16)
            for _ in range(step_limit):
                seen.add(current)
                u, v = current
                if u in face:
                    raise FoldSimulationError("The crease graph stopped being planar while tracing faces.")
                face.append(u)
                ordered = neighbor_order[v]
                position = ordered.index(u)
                w = ordered[position - 1]
                current = (v, w)
                if current == (start_a, start_b):
                    break
            else:
                raise FoldSimulationError("Face tracing did not close; the crease graph is not suitable for folding.")

            area = _signed_area(coords, face)
            if area > 1e-10:
                raw_faces.append(tuple(face))

    if not raw_faces:
        return tuple(), {}

    unique_faces: list[tuple[int, ...]] = []
    seen_cycles: set[tuple[int, ...]] = set()
    for face in raw_faces:
        canonical = _canonical_cycle(face)
        if canonical in seen_cycles:
            continue
        seen_cycles.add(canonical)
        unique_faces.append(face)

    faces: list[SimulationFace] = []
    face_edge_directions: dict[tuple[int, tuple[int, int]], tuple[int, int]] = {}
    for index, face in enumerate(unique_faces):
        area = _signed_area(coords, face)
        triangles = _triangulate_face(coords, face)
        faces.append(SimulationFace(vertices=face, area=area, triangles=triangles))
        for a, b in zip(face, face[1:] + face[:1]):
            face_edge_directions[(index, tuple(sorted((a, b))))] = (a, b)

    return tuple(faces), face_edge_directions


def _build_face_transforms(
    coords: np.ndarray,
    faces: tuple[SimulationFace, ...],
    edges: dict[tuple[int, int], SimulationEdge],
    face_edge_directions: dict[tuple[int, tuple[int, int]], tuple[int, int]],
) -> tuple[
    tuple[np.ndarray, ...],
    tuple[int, ...],
    tuple[int | None, ...],
    tuple[tuple[int, int] | None, ...],
    bool,
    float,
]:
    span = float(max(np.ptp(coords[:, 0]), np.ptp(coords[:, 1]), 1.0))
    soft_tolerance = max(span * 0.003, 5e-4)
    hard_tolerance = max(span * 0.12, 0.02)
    edge_to_faces: dict[tuple[int, int], list[int]] = defaultdict(list)
    for face_index, face in enumerate(faces):
        for a, b in zip(face.vertices, face.vertices[1:] + face.vertices[:1]):
            edge_to_faces[tuple(sorted((a, b)))].append(face_index)

    adjacency: dict[int, list[tuple[int, tuple[int, int]]]] = defaultdict(list)
    for key, edge in edges.items():
        if edge.kind != FOLD:
            continue
        face_indices = edge_to_faces.get(key, [])
        if len(face_indices) != 2:
            raise FoldSimulationError("A fold is not bordered by exactly two faces, so the 3D preview is unsafe.")
        first, second = face_indices
        adjacency[first].append((second, key))
        adjacency[second].append((first, key))

    if not faces:
        return tuple(), tuple(), tuple(), tuple()

    root = max(range(len(faces)), key=lambda index: faces[index].area)
    transforms: list[np.ndarray | None] = [None] * len(faces)
    transforms[root] = np.identity(3)
    parent: list[int | None] = [None] * len(faces)
    parent_edge: list[tuple[int, int] | None] = [None] * len(faces)
    order = [root]
    queue: deque[int] = deque([root])
    uses_approximate_cycles = False
    cycle_drift = 0.0

    while queue:
        face_index = queue.popleft()
        current_transform = transforms[face_index]
        if current_transform is None:
            raise FoldSimulationError("Internal transform state was incomplete.")

        for neighbor_index, edge_key in adjacency[face_index]:
            u, v = face_edge_directions[(face_index, edge_key)]
            p = _apply_transform_2d(current_transform, coords[u])
            q = _apply_transform_2d(current_transform, coords[v])
            reflected = _reflection_transform_2d(p, q) @ current_transform
            if transforms[neighbor_index] is None:
                transforms[neighbor_index] = reflected
                parent[neighbor_index] = face_index
                parent_edge[neighbor_index] = edge_key
                order.append(neighbor_index)
                queue.append(neighbor_index)
                continue

            discrepancy = _face_transform_error(coords, faces[neighbor_index].vertices, transforms[neighbor_index], reflected)
            cycle_drift = max(cycle_drift, discrepancy)
            if discrepancy > hard_tolerance:
                raise FoldSimulationError(
                    "The folded figure became inconsistent around a face cycle. Try regenerating or re-optimizing the sheet."
                )
            if discrepancy > soft_tolerance:
                uses_approximate_cycles = True

    if any(transform is None for transform in transforms):
        raise FoldSimulationError("The crease pattern produced disconnected faces, so the fold preview was aborted.")

    return (
        tuple(transform for transform in transforms if transform is not None),
        tuple(order),
        tuple(parent),
        tuple(parent_edge),
        uses_approximate_cycles,
        cycle_drift,
    )


def _resolve_fold_signs(
    faces: tuple[SimulationFace, ...],
    tree_order: tuple[int, ...],
    tree_parent: tuple[int | None, ...],
    parent_edges: tuple[tuple[int, int] | None, ...],
    edges: dict[tuple[int, int], SimulationEdge],
) -> tuple[dict[tuple[int, int], float], bool]:
    if not faces:
        return {}, False

    depth = {tree_order[0]: 0}
    for face_index in tree_order[1:]:
        parent = tree_parent[face_index]
        if parent is None:
            continue
        depth[face_index] = depth.get(parent, 0) + 1

    signs: dict[tuple[int, int], float] = {}
    uses_provisional = False
    for face_index in tree_order[1:]:
        edge_key = parent_edges[face_index]
        if edge_key is None:
            continue
        edge = edges[edge_key]
        if edge.fold_type == 0:
            signs[edge_key] = 1.0
        elif edge.fold_type == 1:
            signs[edge_key] = -1.0
        else:
            signs[edge_key] = -1.0 if depth.get(face_index, 0) % 2 else 1.0
            uses_provisional = True

    return signs, uses_provisional


def _face_transform_error(
    coords: np.ndarray,
    vertices: tuple[int, ...],
    left: np.ndarray,
    right: np.ndarray,
) -> float:
    max_error = 0.0
    for vertex in vertices:
        delta = _apply_transform_2d(left, coords[vertex]) - _apply_transform_2d(right, coords[vertex])
        max_error = max(max_error, float(np.linalg.norm(delta)))
    return max_error


def _build_face_edge_keys(faces: tuple[SimulationFace, ...]) -> tuple[tuple[tuple[int, int], ...], ...]:
    edge_keys: list[tuple[tuple[int, int], ...]] = []
    for face in faces:
        keys = tuple(tuple(sorted((a, b))) for a, b in zip(face.vertices, face.vertices[1:] + face.vertices[:1]))
        edge_keys.append(keys)
    return tuple(edge_keys)


def _build_source_face_points(
    coords: np.ndarray,
    faces: tuple[SimulationFace, ...],
) -> tuple[np.ndarray, ...]:
    return tuple(
        np.array(
            [[coords[vertex][0], coords[vertex][1], 0.0] for vertex in face.vertices],
            dtype=float,
        )
        for face in faces
    )


def _build_vertex_occurrences(
    faces: tuple[SimulationFace, ...],
    vertex_count: int,
) -> tuple[tuple[tuple[int, int], ...], ...]:
    occurrences: list[list[tuple[int, int]]] = [[] for _ in range(vertex_count)]
    for face_index, face in enumerate(faces):
        for local_index, vertex_index in enumerate(face.vertices):
            occurrences[vertex_index].append((face_index, local_index))
    return tuple(tuple(group) for group in occurrences)


def _blend_face_points(
    left: tuple[np.ndarray, ...],
    right: tuple[np.ndarray, ...],
    weight: float,
) -> tuple[np.ndarray, ...]:
    weight = min(max(weight, 0.0), 1.0)
    return tuple(
        (1.0 - weight) * first + weight * second
        for first, second in zip(left, right)
    )


def _relax_face_points(
    points_by_face: tuple[np.ndarray, ...],
    faces: tuple[SimulationFace, ...],
    source_face_points: tuple[np.ndarray, ...],
    vertex_occurrences: tuple[tuple[tuple[int, int], ...], ...],
    *,
    iterations: int,
    strength: float,
) -> tuple[np.ndarray, ...]:
    if iterations <= 0 or not points_by_face:
        return tuple(np.array(points, dtype=float, copy=True) for points in points_by_face)

    current = tuple(np.array(points, dtype=float, copy=True) for points in points_by_face)
    strength = min(max(strength, 0.0), 1.0)
    for _ in range(iterations):
        averaged_vertices: list[np.ndarray | None] = [None] * len(vertex_occurrences)
        for vertex_index, occurrences in enumerate(vertex_occurrences):
            if not occurrences:
                continue
            averaged_vertices[vertex_index] = np.mean(
                [current[face_index][local_index] for face_index, local_index in occurrences],
                axis=0,
            )

        updated: list[np.ndarray] = []
        for face_index, face in enumerate(faces):
            targets = np.array(current[face_index], dtype=float, copy=True)
            for local_index, vertex_index in enumerate(face.vertices):
                average = averaged_vertices[vertex_index]
                if average is None:
                    continue
                targets[local_index] = (
                    (1.0 - strength) * current[face_index][local_index] + strength * average
                )
            updated.append(_fit_rigid_face(source_face_points[face_index], targets))
        current = tuple(updated)
    return current


def _max_shared_edge_gap(
    face_edge_keys: tuple[tuple[tuple[int, int], ...], ...],
    points_by_face: tuple[np.ndarray, ...],
) -> float:
    edge_samples: dict[tuple[int, int], list[tuple[np.ndarray, np.ndarray]]] = defaultdict(list)
    for face_index, points in enumerate(points_by_face):
        for local_index, edge_key in enumerate(face_edge_keys[face_index]):
            next_index = (local_index + 1) % len(points)
            edge_samples[edge_key].append((points[local_index], points[next_index]))

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


def _fit_rigid_transform(source: np.ndarray, target: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    if len(source) != len(target):
        raise FoldSimulationError("Rigid face fitting received mismatched point counts.")

    source_centroid = source.mean(axis=0)
    target_centroid = target.mean(axis=0)
    centered_source = source - source_centroid
    centered_target = target - target_centroid
    covariance = centered_source.T @ centered_target
    left, _, right_t = np.linalg.svd(covariance)
    rotation = right_t.T @ left.T
    if np.linalg.det(rotation) < 0:
        right_t[-1, :] *= -1
        rotation = right_t.T @ left.T
    translation = target_centroid - source_centroid @ rotation.T
    return rotation, translation


def _fit_rigid_face(source: np.ndarray, target: np.ndarray) -> np.ndarray:
    rotation, translation = _fit_rigid_transform(source, target)
    return source @ rotation.T + translation


def _fit_face_transforms(
    source_face_points: tuple[np.ndarray, ...],
    target_face_points: tuple[np.ndarray, ...],
) -> tuple[tuple[np.ndarray, ...], tuple[np.ndarray, ...]]:
    rotations: list[np.ndarray] = []
    translations: list[np.ndarray] = []
    for source, target in zip(source_face_points, target_face_points):
        rotation, translation = _fit_rigid_transform(source, target)
        rotations.append(rotation)
        translations.append(translation)
    return tuple(rotations), tuple(translations)


def _pack_face_transform_parameters(
    rotations: tuple[np.ndarray, ...],
    translations: tuple[np.ndarray, ...],
    non_root_faces: tuple[int, ...],
) -> np.ndarray:
    parameters = np.zeros(len(non_root_faces) * 6, dtype=float)
    for offset, face_index in enumerate(non_root_faces):
        start = offset * 6
        parameters[start : start + 3] = Rotation.from_matrix(rotations[face_index]).as_rotvec()
        parameters[start + 3 : start + 6] = translations[face_index]
    return parameters


def _unpack_face_transform_parameters(
    parameters: np.ndarray,
    face_count: int,
    root_face: int,
    non_root_faces: tuple[int, ...],
) -> tuple[tuple[np.ndarray, ...], tuple[np.ndarray, ...]]:
    rotations: list[np.ndarray] = [np.identity(3) for _ in range(face_count)]
    translations: list[np.ndarray] = [np.zeros(3, dtype=float) for _ in range(face_count)]
    rotations[root_face] = np.identity(3)
    translations[root_face] = np.zeros(3, dtype=float)
    for offset, face_index in enumerate(non_root_faces):
        start = offset * 6
        rotations[face_index] = Rotation.from_rotvec(parameters[start : start + 3]).as_matrix()
        translations[face_index] = np.array(
            parameters[start + 3 : start + 6],
            dtype=float,
        )
    return tuple(rotations), tuple(translations)


def _apply_face_transforms(
    source_face_points: tuple[np.ndarray, ...],
    rotations: tuple[np.ndarray, ...],
    translations: tuple[np.ndarray, ...],
) -> tuple[np.ndarray, ...]:
    return tuple(
        source @ rotation.T + translation
        for source, rotation, translation in zip(source_face_points, rotations, translations)
    )


def _apply_face_transform_samples(
    source_face_points: tuple[np.ndarray, ...],
    rotvecs: np.ndarray,
    translations: np.ndarray,
) -> tuple[np.ndarray, ...]:
    rotations = tuple(
        Rotation.from_rotvec(rotvec).as_matrix()
        for rotvec in rotvecs
    )
    return _apply_face_transforms(
        source_face_points,
        rotations,
        tuple(np.array(translation, dtype=float) for translation in translations),
    )


def _interpolate_face_transform_samples(
    source_face_points: tuple[np.ndarray, ...],
    left_rotvecs: np.ndarray,
    left_translations: np.ndarray,
    right_rotvecs: np.ndarray,
    right_translations: np.ndarray,
    weight: float,
) -> tuple[np.ndarray, ...]:
    weight = min(max(weight, 0.0), 1.0)
    if weight <= 0.0:
        return _apply_face_transform_samples(
            source_face_points,
            left_rotvecs,
            left_translations,
        )
    if weight >= 1.0:
        return _apply_face_transform_samples(
            source_face_points,
            right_rotvecs,
            right_translations,
        )

    rotations: list[np.ndarray] = []
    translations: list[np.ndarray] = []
    for left_rotvec, right_rotvec, left_translation, right_translation in zip(
        left_rotvecs,
        right_rotvecs,
        left_translations,
        right_translations,
    ):
        if np.allclose(left_rotvec, right_rotvec, atol=1e-10):
            rotation = Rotation.from_rotvec(left_rotvec).as_matrix()
        else:
            keyframes = Rotation.from_rotvec(
                np.stack((left_rotvec, right_rotvec), axis=0)
            )
            rotation = Slerp([0.0, 1.0], keyframes)([weight]).as_matrix()[0]
        rotations.append(rotation)
        translations.append(
            (1.0 - weight) * np.array(left_translation, dtype=float)
            + weight * np.array(right_translation, dtype=float)
        )

    return _apply_face_transforms(
        source_face_points,
        tuple(rotations),
        tuple(translations),
    )


def _rigid_projection_residuals(
    parameters: np.ndarray,
    guide_points: tuple[np.ndarray, ...],
    source_face_points: tuple[np.ndarray, ...],
    vertex_occurrences: tuple[tuple[tuple[int, int], ...], ...],
    root_face: int,
    non_root_faces: tuple[int, ...],
    seam_weight: float,
    guide_weight: float,
) -> np.ndarray:
    rotations, translations = _unpack_face_transform_parameters(
        parameters,
        len(source_face_points),
        root_face,
        non_root_faces,
    )
    posed_points = _apply_face_transforms(
        source_face_points,
        rotations,
        translations,
    )

    residuals: list[float] = []
    for occurrences in vertex_occurrences:
        if len(occurrences) < 2:
            continue
        base_face, base_local_index = occurrences[0]
        base_point = posed_points[base_face][base_local_index]
        for face_index, local_index in occurrences[1:]:
            residuals.extend(
                (
                    seam_weight
                    * (posed_points[face_index][local_index] - base_point)
                ).tolist()
            )

    for face_index in non_root_faces:
        residuals.extend(
            (
                guide_weight
                * (posed_points[face_index] - guide_points[face_index])
            ).ravel().tolist()
        )

    return np.array(residuals, dtype=float)


def _signed_area(coords: np.ndarray, face: tuple[int, ...] | list[int]) -> float:
    area = 0.0
    points = [coords[index] for index in face]
    for first, second in zip(points, points[1:] + points[:1]):
        area += float(first[0] * second[1] - second[0] * first[1])
    return 0.5 * area


def _canonical_cycle(face: tuple[int, ...]) -> tuple[int, ...]:
    smallest = min(range(len(face)), key=lambda index: face[index])
    rotated = face[smallest:] + face[:smallest]
    return tuple(rotated)


def _triangulate_face(coords: np.ndarray, face: tuple[int, ...]) -> tuple[tuple[int, int, int], ...]:
    vertices = list(face)
    if len(vertices) < 3:
        raise FoldSimulationError("Encountered a face with fewer than three vertices.")
    if len(vertices) == 3:
        return ((0, 1, 2),)

    local_points = [coords[index] for index in vertices]
    remaining = list(range(len(vertices)))
    triangles: list[tuple[int, int, int]] = []
    epsilon = 1e-10

    while len(remaining) > 3:
        ear_found = False
        for position, current in enumerate(remaining):
            prev_index = remaining[position - 1]
            next_index = remaining[(position + 1) % len(remaining)]

            a = local_points[prev_index]
            b = local_points[current]
            c = local_points[next_index]
            if _triangle_cross(a, b, c) <= epsilon:
                continue

            if any(
                _point_in_triangle(local_points[other], a, b, c, epsilon)
                for other in remaining
                if other not in (prev_index, current, next_index)
            ):
                continue

            triangles.append((prev_index, current, next_index))
            del remaining[position]
            ear_found = True
            break

        if not ear_found:
            raise FoldSimulationError("A face could not be triangulated for 3D rendering.")

    triangles.append((remaining[0], remaining[1], remaining[2]))
    return tuple(triangles)


def _triangle_cross(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> float:
    return float((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]))


def _point_in_triangle(point: np.ndarray, a: np.ndarray, b: np.ndarray, c: np.ndarray, epsilon: float) -> bool:
    ab = _triangle_cross(a, b, point)
    bc = _triangle_cross(b, c, point)
    ca = _triangle_cross(c, a, point)
    has_negative = ab < -epsilon or bc < -epsilon or ca < -epsilon
    has_positive = ab > epsilon or bc > epsilon or ca > epsilon
    return not (has_negative and has_positive)


def _pick_mesh_root(coords: np.ndarray, faces: tuple[SimulationFace, ...], side: float) -> int:
    center = np.array([0.5 * side, 0.5 * side], dtype=float)
    containing_faces = []
    for index, face in enumerate(faces):
        a, b, c = (coords[vertex] for vertex in face.vertices)
        if _point_in_triangle(center, a, b, c, 1e-10):
            containing_faces.append((face.area, index))
    if containing_faces:
        containing_faces.sort(reverse=True)
        return containing_faces[0][1]
    return max(range(len(faces)), key=lambda index: faces[index].area)


def _reflection_transform_2d(p: np.ndarray, q: np.ndarray) -> np.ndarray:
    direction = q - p
    length = np.linalg.norm(direction)
    if length <= 1e-12:
        raise FoldSimulationError("A fold edge collapsed to zero length during reflection.")

    unit = direction / length
    reflection = np.array(
        [
            [2.0 * unit[0] * unit[0] - 1.0, 2.0 * unit[0] * unit[1]],
            [2.0 * unit[0] * unit[1], 2.0 * unit[1] * unit[1] - 1.0],
        ],
        dtype=float,
    )

    transform = np.identity(3)
    transform[:2, :2] = reflection
    transform[:2, 2] = p - reflection @ p
    return transform


def _rotation_about_axis(p: np.ndarray, q: np.ndarray, angle: float) -> np.ndarray:
    axis = q - p
    length = np.linalg.norm(axis)
    if length <= 1e-12:
        raise FoldSimulationError("A fold axis collapsed to zero length during animation.")

    axis = axis / length
    x, y, z = axis
    cosine = math.cos(angle)
    sine = math.sin(angle)
    complement = 1.0 - cosine

    rotation = np.array(
        [
            [cosine + x * x * complement, x * y * complement - z * sine, x * z * complement + y * sine],
            [y * x * complement + z * sine, cosine + y * y * complement, y * z * complement - x * sine],
            [z * x * complement - y * sine, z * y * complement + x * sine, cosine + z * z * complement],
        ],
        dtype=float,
    )

    transform = np.identity(4)
    transform[:3, :3] = rotation
    transform[:3, 3] = p - rotation @ p
    return transform


def _apply_transform_2d(transform: np.ndarray, point: np.ndarray) -> np.ndarray:
    vector = np.array([point[0], point[1], 1.0], dtype=float)
    return (transform @ vector)[:2]


def _apply_transform_3d(transform: np.ndarray, point: np.ndarray) -> np.ndarray:
    vector = np.array([point[0], point[1], 0.0, 1.0], dtype=float)
    return (transform @ vector)[:3]


def _segments_intersect(a0: np.ndarray, a1: np.ndarray, b0: np.ndarray, b1: np.ndarray, epsilon: float) -> bool:
    orientation_1 = _orientation(a0, a1, b0)
    orientation_2 = _orientation(a0, a1, b1)
    orientation_3 = _orientation(b0, b1, a0)
    orientation_4 = _orientation(b0, b1, a1)

    if min(abs(orientation_1), abs(orientation_2), abs(orientation_3), abs(orientation_4)) <= epsilon:
        return False

    return (orientation_1 > 0) != (orientation_2 > 0) and (orientation_3 > 0) != (orientation_4 > 0)


def _orientation(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> float:
    return float((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]))


def _ease_in_out(value: float) -> float:
    return 0.5 - 0.5 * math.cos(math.pi * value)


def _smoothstep(edge_0: float, edge_1: float, value: float) -> float:
    if edge_0 == edge_1:
        return 1.0
    t = min(max((value - edge_0) / (edge_1 - edge_0), 0.0), 1.0)
    return t * t * (3.0 - 2.0 * t)
