from __future__ import annotations

import numpy as np

ROCKET_FACE_COLORS_LIGHT = (
    "#FF5A5F",
    "#22C55E",
    "#3B82F6",
    "#F5B942",
    "#A8B3C2",
    "#7F8B9D",
)

ROCKET_FACE_COLORS_DARK = (
    "#FF7B86",
    "#4ADE80",
    "#60A5FA",
    "#FACC15",
    "#CBD5E1",
    "#94A3B8",
)

TRAJECTORY_PRE_DEPLOY_COLOR = "#EF4444"
TRAJECTORY_POST_DEPLOY_COLOR = "#3B82F6"
TRAJECTORY_DEPLOY_COLOR = "#F97316"
TRAJECTORY_LANDING_COLOR = "#8B5CF6"


def RocketFaceColors_Get(theme: str) -> tuple[str, ...]:
    return ROCKET_FACE_COLORS_DARK if theme == "dark" else ROCKET_FACE_COLORS_LIGHT


def TrajectoryPhaseColor_Get(
    timestamp_us: int,
    deploy_timestamp_us: int | None,
) -> str:
    if deploy_timestamp_us is not None and timestamp_us >= deploy_timestamp_us:
        return TRAJECTORY_POST_DEPLOY_COLOR
    return TRAJECTORY_PRE_DEPLOY_COLOR


def TrajectoryCharacteristicExtent_Get(
    values: np.ndarray,
    *,
    minimum_extent: float = 1.0,
) -> float:
    points = np.asarray(values, dtype=np.float64)
    if points.ndim != 2 or points.shape[1] != 3 or points.size == 0:
        return float(minimum_extent)
    finite = points[np.all(np.isfinite(points), axis=1)]
    if finite.size == 0:
        return float(minimum_extent)
    spans = np.max(finite, axis=0) - np.min(finite, axis=0)
    return max(float(np.max(spans)), float(minimum_extent))


def TrajectoryMarkerWorldSizes_Get(values: np.ndarray) -> tuple[float, float, float]:
    """Return Deploy, Current, and Landing marker diameters in trajectory units."""

    extent = TrajectoryCharacteristicExtent_Get(values)
    return extent * 0.035, extent * 0.028, extent * 0.028
