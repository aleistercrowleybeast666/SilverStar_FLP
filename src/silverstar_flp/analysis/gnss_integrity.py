"""Analysis-only GNSS position/velocity closure using receiver-native epochs.

The local ENU transform is a direct numerical port of FCCG GeoLocalFrame_Init/
GeoLocalFrame_ToEnu (WGS84 origin curvature and longitude wrap). It is not a
Kalman NIS or a firmware acceptance rule.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from silverstar_flp.core.dataset import FlightDataset

WINDOW_SECONDS = (1, 2, 5, 10)
_WGS84_A_M = 6378137.0
_WGS84_INV_F = 298.257223563
_RAD_PER_E7 = math.pi / (180.0 * 10_000_000.0)


@dataclass(frozen=True, slots=True)
class GnssIntegrityResult:
    window_s: int
    timestamp_us: np.ndarray
    position_displacement_m: np.ndarray
    velocity_displacement_m: np.ndarray
    residual_m: np.ndarray
    valid_en: np.ndarray
    valid_u: np.ndarray
    anchored_residual_m: np.ndarray
    anchored_valid_en: np.ndarray
    anchored_valid_u: np.ndarray
    anchor_reset_en: np.ndarray
    anchor_reset_u: np.ndarray
    quality: np.ndarray
    summary: dict[str, dict[str, float | int]]


def GeoLocal_ToEnu(
    lat_e7: np.ndarray, lon_e7: np.ndarray, height_mm: np.ndarray,
    origin: tuple[int, int, int],
) -> np.ndarray:
    """Match the firmware's origin-local WGS84 curvature and height convention."""
    origin_lat, origin_lon, origin_height = origin
    if not (-900_000_000 <= origin_lat <= 900_000_000
            and -1_800_000_000 <= origin_lon <= 1_800_000_000):
        raise ValueError("gnss_origin_invalid")
    flattening = 1.0 / _WGS84_INV_F
    eccentricity_squared = flattening * (2.0 - flattening)
    latitude = origin_lat * _RAD_PER_E7
    sin_lat = math.sin(latitude)
    denominator = 1.0 - eccentricity_squared * sin_lat * sin_lat
    prime_vertical = _WGS84_A_M / math.sqrt(denominator)
    meridian = _WGS84_A_M * (1.0 - eccentricity_squared) / denominator ** 1.5
    origin_height_m = origin_height * .001
    east_scale = (prime_vertical + origin_height_m) * math.cos(latitude) * _RAD_PER_E7
    north_scale = (meridian + origin_height_m) * _RAD_PER_E7
    if east_scale <= 0 or north_scale <= 0:
        raise ValueError("gnss_origin_invalid")
    delta_lon = np.asarray(lon_e7, dtype=np.int64) - origin_lon
    delta_lon = np.where(delta_lon > 1_800_000_000, delta_lon - 3_600_000_000, delta_lon)
    delta_lon = np.where(delta_lon < -1_800_000_000, delta_lon + 3_600_000_000, delta_lon)
    return np.column_stack((
        delta_lon * east_scale,
        (np.asarray(lat_e7, dtype=np.int64) - origin_lat) * north_scale,
        (np.asarray(height_mm, dtype=np.int64) - origin_height) * .001,
    ))


def _Summary_Get(values: np.ndarray, eligible: int) -> dict[str, float | int]:
    finite = values[np.isfinite(values)]
    return {
        "valid_window_count": int(finite.size),
        "coverage": float(finite.size / eligible) if eligible else 0.0,
        "median_m": float(np.median(finite)) if finite.size else math.nan,
        "p95_m": float(np.percentile(finite, 95)) if finite.size else math.nan,
        "max_m": float(np.max(finite)) if finite.size else math.nan,
    }


def _AnchoredClosure_Build(
    time: np.ndarray,
    position: np.ndarray,
    velocity: np.ndarray,
    group_valid: np.ndarray,
    broken: np.ndarray,
    mission_start_us: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Integrate only continuous, independently valid EN and U segments."""
    residual = np.full(position.shape, np.nan, dtype=np.float64)
    valid = np.zeros((len(time), 2), dtype=np.bool_)
    anchor_reset = np.zeros((len(time), 2), dtype=np.bool_)
    anchors: list[np.ndarray | None] = [None, None]
    integrated = np.zeros(3, dtype=np.float64)
    for index in range(len(time)):
        for group, axes, required in ((0, (0, 1), (0, 2)), (1, (2,), (1, 3))):
            if time[index] < mission_start_us or not all(
                group_valid[index, item] for item in required
            ):
                anchors[group] = None
                continue
            if anchors[group] is None or index == 0 or broken[index - 1]:
                anchors[group] = position[index, list(axes)].copy()
                integrated[list(axes)] = 0.0
                anchor_reset[index, group] = True
                continue
            dt_s = (int(time[index]) - int(time[index - 1])) * 1e-6
            integrated[list(axes)] += (
                0.5 * (velocity[index - 1, list(axes)] + velocity[index, list(axes)]) * dt_s
            )
            residual[index, list(axes)] = (
                position[index, list(axes)] - anchors[group] - integrated[list(axes)]
            )
            valid[index, group] = True
    return residual, valid, anchor_reset


def GnssIntegrity_Build(dataset: FlightDataset, window_s: int = 5) -> GnssIntegrityResult:
    if window_s not in WINDOW_SECONDS:
        raise ValueError("gnss_integrity_window_invalid")
    initial = dataset.initial_state
    if initial is None or not int(initial.payload.get("origin_valid_flags", 0)) & 1:
        raise ValueError("gnss_origin_unavailable")
    fields = ("gnss_origin_latitude_e7", "gnss_origin_longitude_e7", "gnss_origin_height_mm")
    if any(field not in initial.payload for field in fields):
        raise ValueError("gnss_origin_unavailable")
    origin = tuple(int(initial.payload[field]) for field in fields)
    records = tuple(dataset.Records_Get("GNSS_NATIVE"))
    if not records:
        raise ValueError("gnss_native_unavailable")
    descriptor_ids = {
        (r.payload.get("source_descriptor_id"), r.payload.get("instance_id"))
        for r in records
    }
    if len(descriptor_ids) != 1:
        raise ValueError("gnss_native_source_ambiguous")
    payloads = tuple(record.payload for record in records)
    time = np.asarray([int(p.get("sample_timestamp_us", record.timestamp_us))
                       for p, record in zip(payloads, records, strict=True)], dtype=np.int64)
    if np.any(time < 0) or np.any(np.diff(time) <= 0):
        raise ValueError("gnss_native_timestamps_nonmonotonic")
    sequence = np.asarray([int(p.get("sequence", record.record_sequence))
                           for p, record in zip(payloads, records, strict=True)], dtype=np.int64)
    lat = np.asarray([int(p["latitude_e7"]) for p in payloads], dtype=np.int64)
    lon = np.asarray([int(p["longitude_e7"]) for p in payloads], dtype=np.int64)
    height = np.asarray([int(p["ellipsoid_height_mm"]) for p in payloads], dtype=np.int64)
    position = GeoLocal_ToEnu(lat, lon, height, origin)
    velocity = np.asarray([p["velocity_enu_mps"] for p in payloads], dtype=np.float64)
    if velocity.shape != (len(payloads), 3):
        raise ValueError("gnss_native_velocity_invalid")
    quality = np.asarray([
        (float(p.get("horizontal_accuracy_m", math.nan)),
         float(p.get("vertical_accuracy_m", math.nan)),
         float(p.get("speed_accuracy_mps", math.nan)),
         float(p.get("satellite_count", math.nan)))
        for p in payloads
    ], dtype=np.float64)
    # New records own four independent bits. Aggregate flags are a legacy fallback only.
    masks = np.asarray([
        int(p["valid_group_mask"]) if "valid_group_mask" in p else (
            (0x03 if bool(p.get("position_usable", 0)) else 0)
            | (0x04 if int(p.get("velocity_valid_mask", 0)) & 0x03 == 0x03 else 0)
            | (0x08 if int(p.get("velocity_valid_mask", 0)) & 0x04 else 0)
        )
        for p in payloads
    ], dtype=np.int64)
    geographic_valid = ((lat >= -900_000_000) & (lat <= 900_000_000)
                        & (lon >= -1_800_000_000) & (lon <= 1_800_000_000))
    group_valid = np.column_stack((
        (masks & 1 != 0) & geographic_valid,
        (masks & 2 != 0) & geographic_valid,
        masks & 4 != 0,
        masks & 8 != 0,
    ))
    group_valid[:, 0] &= np.isfinite(position[:, :2]).all(axis=1)
    group_valid[:, 1] &= np.isfinite(position[:, 2])
    group_valid[:, 2] &= np.isfinite(velocity[:, :2]).all(axis=1)
    group_valid[:, 3] &= np.isfinite(velocity[:, 2])
    dt_us = np.diff(time)
    cadence = float(np.median(dt_us)) if dt_us.size else 0.0
    gap_limit_us = max(3.0 * cadence, 120_000.0)
    sequence_step = (np.diff(sequence) & 0xFFFFFFFF)
    broken = (dt_us > gap_limit_us) | (sequence_step != 1)
    broken_prefix = np.r_[0, np.cumsum(broken.astype(np.int64))]
    invalid_prefix = np.vstack((
        np.zeros((1, 4), dtype=np.int64),
        np.cumsum((~group_valid).astype(np.int64), axis=0),
    ))
    dt_s = dt_us.astype(np.float64) * 1e-6
    safe_velocity = np.where(np.isfinite(velocity), velocity, 0.0)
    integrals = np.vstack((
        np.zeros((1, 3), dtype=np.float64),
        np.cumsum(.5 * (safe_velocity[1:] + safe_velocity[:-1]) * dt_s[:, None], axis=0),
    ))
    position_delta = np.full((len(time), 3), np.nan)
    velocity_delta = np.full((len(time), 3), np.nan)
    residual = np.full((len(time), 3), np.nan)
    valid_en = np.zeros(len(time), dtype=bool)
    valid_u = np.zeros(len(time), dtype=bool)
    window_us = window_s * 1_000_000
    eligible = int(np.count_nonzero(time - time[0] >= window_us))
    for end in range(len(time)):
        target = int(time[end]) - window_us
        if target < time[0]:
            continue
        start = int(np.searchsorted(time, target, side="left"))
        if end - start < 2 or time[end] - time[start] < .9 * window_us:
            continue
        if broken_prefix[end] != broken_prefix[start]:
            continue
        for horizontal, required, axes in (
            (True, (0, 2), (0, 1)),
            (False, (1, 3), (2,)),
        ):
            if any(invalid_prefix[end + 1, group] != invalid_prefix[start, group]
                   for group in required):
                continue
            dp = position[end, list(axes)] - position[start, list(axes)]
            dv = integrals[end, list(axes)] - integrals[start, list(axes)]
            position_delta[end, list(axes)] = dp
            velocity_delta[end, list(axes)] = dv
            residual[end, list(axes)] = dp - dv
            if horizontal:
                valid_en[end] = True
            else:
                valid_u[end] = True
    anchored, anchored_valid, anchor_reset = _AnchoredClosure_Build(
        time, position, velocity, group_valid, broken,
        int(dataset.start_timestamp_us or time[0]),
    )
    horizontal_error = np.linalg.norm(residual[valid_en, :2], axis=1)
    vertical_error = np.abs(residual[valid_u, 2])
    anchored_horizontal = np.linalg.norm(anchored[anchored_valid[:, 0], :2], axis=1)
    anchored_vertical = np.abs(anchored[anchored_valid[:, 1], 2])
    return GnssIntegrityResult(
        window_s=window_s, timestamp_us=time, position_displacement_m=position_delta,
        velocity_displacement_m=velocity_delta, residual_m=residual,
        valid_en=valid_en, valid_u=valid_u,
        anchored_residual_m=anchored,
        anchored_valid_en=anchored_valid[:, 0],
        anchored_valid_u=anchored_valid[:, 1],
        anchor_reset_en=anchor_reset[:, 0],
        anchor_reset_u=anchor_reset[:, 1],
        quality=quality,
        summary={"horizontal": _Summary_Get(horizontal_error, eligible),
                 "vertical": _Summary_Get(vertical_error, eligible),
                 "anchored_horizontal": _Summary_Get(anchored_horizontal, len(time)),
                 "anchored_vertical": _Summary_Get(anchored_vertical, len(time))},
    )
