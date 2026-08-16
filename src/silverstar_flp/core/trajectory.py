from __future__ import annotations

from dataclasses import dataclass
from math import atan, radians, sin, tan

import numpy as np

from silverstar_flp.core.dataset import TimeSeries
from silverstar_flp.core.mission import MissionReplayBounds

Vector3 = tuple[float, float, float]


@dataclass(frozen=True, slots=True)
class TrajectoryBounds:
    min_enu: Vector3
    max_enu: Vector3
    center_enu: Vector3
    span_enu: Vector3
    max_span: float
    bounding_radius: float
    origin_enu: Vector3
    sample_count: int


def _Vector3_Get(values: np.ndarray) -> Vector3:
    vector = np.asarray(values, dtype=np.float64)
    return float(vector[0]), float(vector[1]), float(vector[2])


def TrajectoryPosition_At(series: TimeSeries, timestamp_us: int) -> np.ndarray | None:
    if series.count == 0:
        return None
    values = np.asarray(series.values, dtype=np.float64)
    if values.ndim != 2 or values.shape[1] != 3:
        return None
    valid = series.valid & np.all(np.isfinite(values), axis=1)
    timestamps = series.timestamp_us[valid]
    points = values[valid]
    if timestamps.size == 0:
        return None
    first = int(timestamps[0])
    last = int(timestamps[-1])
    if timestamp_us < first or timestamp_us > last:
        return None
    upper = int(np.searchsorted(timestamps, np.uint64(timestamp_us), side="right"))
    if upper == 0:
        return points[0].copy()
    if upper >= timestamps.size:
        return points[-1].copy()
    lower = upper - 1
    lower_time = int(timestamps[lower])
    upper_time = int(timestamps[upper])
    span = upper_time - lower_time
    ratio = 0.0 if span <= 0 else (timestamp_us - lower_time) / span
    return points[lower] + ratio * (points[upper] - points[lower])


def TrajectoryPosition_NearEvent(
    series: TimeSeries,
    timestamp_us: int,
) -> np.ndarray | None:
    interpolated = TrajectoryPosition_At(series, timestamp_us)
    if interpolated is not None:
        return interpolated
    values = np.asarray(series.values, dtype=np.float64)
    if values.ndim != 2 or values.shape[1] != 3:
        return None
    valid = series.valid & np.all(np.isfinite(values), axis=1)
    timestamps = series.timestamp_us[valid].astype(np.int64)
    points = values[valid]
    if timestamps.size == 0:
        return None
    intervals = np.diff(timestamps)
    positive_intervals = intervals[intervals > 0]
    typical_interval = float(np.median(positive_intervals)) if positive_intervals.size else 0.0
    tolerance_us = max(int(typical_interval * 5.0), 100_000)
    index = int(np.argmin(np.abs(timestamps - timestamp_us)))
    if abs(int(timestamps[index]) - timestamp_us) > tolerance_us:
        return None
    return points[index].copy()


def TrajectoryOrigin_Get(series: TimeSeries, start_timestamp_us: int) -> np.ndarray:
    interpolated = TrajectoryPosition_At(series, start_timestamp_us)
    if interpolated is not None:
        return interpolated
    values = np.asarray(series.values, dtype=np.float64)
    if values.ndim != 2 or values.shape[1] != 3:
        return np.zeros(3, dtype=np.float64)
    valid = series.valid & np.all(np.isfinite(values), axis=1)
    post_start = np.flatnonzero(
        valid & (series.timestamp_us >= np.uint64(max(start_timestamp_us, 0)))
    )
    if post_start.size:
        return values[post_start[0]].copy()
    available = np.flatnonzero(valid)
    if available.size:
        return values[available[0]].copy()
    return np.zeros(3, dtype=np.float64)


def TrajectoryBounds_Calculate(
    series: TimeSeries,
    mission_bounds: MissionReplayBounds,
) -> TrajectoryBounds:
    origin = TrajectoryOrigin_Get(series, mission_bounds.start_timestamp_us)
    values = np.asarray(series.values, dtype=np.float64)
    if values.ndim != 2 or values.shape[1] != 3:
        zero = (0.0, 0.0, 0.0)
        return TrajectoryBounds(
            min_enu=zero,
            max_enu=zero,
            center_enu=zero,
            span_enu=zero,
            max_span=0.0,
            bounding_radius=0.0,
            origin_enu=_Vector3_Get(origin),
            sample_count=0,
        )
    valid = (
        series.valid
        & np.all(np.isfinite(values), axis=1)
        & (series.timestamp_us >= np.uint64(max(mission_bounds.start_timestamp_us, 0)))
        & (series.timestamp_us <= np.uint64(max(mission_bounds.end_timestamp_us, 0)))
    )
    displayed = values[valid] - origin
    if displayed.size == 0:
        zero = (0.0, 0.0, 0.0)
        return TrajectoryBounds(
            min_enu=zero,
            max_enu=zero,
            center_enu=zero,
            span_enu=zero,
            max_span=0.0,
            bounding_radius=0.0,
            origin_enu=_Vector3_Get(origin),
            sample_count=0,
        )
    minimum = np.min(displayed, axis=0)
    maximum = np.max(displayed, axis=0)
    center = (minimum + maximum) * 0.5
    span = maximum - minimum
    radius = float(np.max(np.linalg.norm(displayed - center, axis=1)))
    return TrajectoryBounds(
        min_enu=_Vector3_Get(minimum),
        max_enu=_Vector3_Get(maximum),
        center_enu=_Vector3_Get(center),
        span_enu=_Vector3_Get(span),
        max_span=float(np.max(span)),
        bounding_radius=radius,
        origin_enu=_Vector3_Get(origin),
        sample_count=int(displayed.shape[0]),
    )


def TrajectoryCameraDistance_Get(
    bounds: TrajectoryBounds,
    *,
    horizontal_fov_deg: float,
    aspect_ratio: float,
    margin_ratio: float = 1.15,
    minimum_distance: float = 8.0,
) -> float:
    fov = float(horizontal_fov_deg)
    aspect = float(aspect_ratio)
    margin = float(margin_ratio)
    if not np.isfinite(fov) or fov <= 1.0 or fov >= 179.0:
        raise ValueError("trajectory_camera_fov_invalid")
    if not np.isfinite(aspect) or aspect <= 0.0:
        raise ValueError("trajectory_camera_aspect_invalid")
    if not np.isfinite(margin) or margin < 1.0:
        raise ValueError("trajectory_camera_margin_invalid")
    horizontal_half_angle = radians(fov * 0.5)
    vertical_half_angle = atan(tan(horizontal_half_angle) / aspect)
    limiting_half_angle = min(horizontal_half_angle, vertical_half_angle)
    radius = max(float(bounds.bounding_radius), 0.0)
    fitted = 0.0 if radius == 0.0 else radius / sin(limiting_half_angle) * margin
    return max(float(minimum_distance), fitted)
