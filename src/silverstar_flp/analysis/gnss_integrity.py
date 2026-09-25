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
    anchored_position_displacement_m: np.ndarray | None = None
    anchored_velocity_displacement_m: np.ndarray | None = None
    segment_en: np.ndarray | None = None
    segment_u: np.ndarray | None = None
    rolling_reason_en: tuple[str, ...] = ()
    rolling_reason_u: tuple[str, ...] = ()
    anchored_reason_en: tuple[str, ...] = ()
    anchored_reason_u: tuple[str, ...] = ()
    position_timestamp_us: np.ndarray | None = None
    velocity_timestamp_us: np.ndarray | None = None
    evidence_cutoff_us: np.ndarray | None = None
    evidence_age_us: np.ndarray | None = None


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


def _EffectiveTimes_Get(dataset: FlightDataset, records: tuple) -> tuple[np.ndarray, np.ndarray]:
    """Use the resolved times actually recorded by the estimator when available."""
    measurements = {
        (int(row.payload.get("sequence", row.record_sequence)),
         int(row.payload.get("receive_timestamp_us", row.timestamp_us))): row.payload
        for row in dataset.Records_Get("GNSS_MEASUREMENT")
    }
    position_us = np.empty(len(records), dtype=np.int64)
    velocity_us = np.empty(len(records), dtype=np.int64)
    for index, record in enumerate(records):
        native = record.payload
        sample_us = int(native.get("sample_timestamp_us", record.timestamp_us))
        sequence = int(native.get("sequence", record.record_sequence))
        resolved = measurements.get((sequence, int(native.get("receive_timestamp_us", sample_us))))
        if resolved is None:
            # Native-only synthetic logs have one common sample time.
            position_us[index] = sample_us
            velocity_us[index] = sample_us
        else:
            position_us[index] = int(resolved["position_measurement_timestamp_us"])
            velocity_us[index] = int(resolved["velocity_measurement_timestamp_us"])
    if np.any(np.diff(position_us) <= 0) or np.any(np.diff(velocity_us) <= 0):
        raise ValueError("gnss_integrity_effective_times_nonmonotonic")
    return position_us, velocity_us


def _PositionAt(
    target_us: int, last_index: int, times: np.ndarray, position: np.ndarray,
    valid: np.ndarray, valid_indices: np.ndarray, gap_limit_us: int,
) -> np.ndarray | None:
    right_at = int(np.searchsorted(times[valid_indices], target_us, side="left"))
    if right_at >= len(valid_indices):
        return None
    right = int(valid_indices[right_at])
    if right > last_index:
        return None
    if times[right] == target_us:
        return position[right].copy()
    if right_at == 0:
        return None
    left = int(valid_indices[right_at - 1])
    span = int(times[right] - times[left])
    if span <= 0 or span > gap_limit_us or left >= last_index:
        return None
    fraction = (target_us - int(times[left])) / span
    return position[left] + fraction * (position[right] - position[left])


def _VelocityAt(
    target_us: int, last_index: int, times: np.ndarray, velocity: np.ndarray,
    valid: np.ndarray, bad_prefix: np.ndarray, broken_prefix: np.ndarray,
    integral: np.ndarray, gap_limit_us: int,
) -> tuple[np.ndarray, np.ndarray, int] | None:
    right = int(np.searchsorted(times, target_us, side="left"))
    if right > last_index:
        return None
    if times[right] == target_us:
        if not valid[right]:
            return None
        return velocity[right].copy(), integral[right].copy(), right
    if right == 0 or int(times[right] - times[right - 1]) > gap_limit_us:
        return None
    left = right - 1
    if (bad_prefix[right + 1] != bad_prefix[left]
            or broken_prefix[right] != broken_prefix[left]):
        return None
    fraction = (target_us - int(times[left])) / int(times[right] - times[left])
    value = velocity[left] + fraction * (velocity[right] - velocity[left])
    dt_s = (target_us - int(times[left])) * 1e-6
    return value, integral[left] + .5 * (velocity[left] + value) * dt_s, left


def _AlignedClosure_Build(
    receive_us: np.ndarray, position_us: np.ndarray, velocity_us: np.ndarray,
    position: np.ndarray, velocity: np.ndarray, group_valid: np.ndarray,
    sequence_jump: np.ndarray, mission_start_us: int, window_us: int,
    gap_limit_us: int,
) -> tuple:
    count = len(receive_us)
    rolling_pos = np.full((count, 3), np.nan)
    rolling_vel = np.full((count, 3), np.nan)
    rolling_res = np.full((count, 3), np.nan)
    anchored_pos = np.full((count, 3), np.nan)
    anchored_vel = np.full((count, 3), np.nan)
    anchored_res = np.full((count, 3), np.nan)
    rolling_valid = np.zeros((count, 2), dtype=bool)
    anchored_valid = np.zeros((count, 2), dtype=bool)
    reset = np.zeros((count, 2), dtype=bool)
    segment = np.zeros((count, 2), dtype=np.int32)
    cutoff = np.minimum(position_us, velocity_us)
    reasons_rolling = [["warmup"] * count for _ in range(2)]
    reasons_anchored = [["before_mission"] * count for _ in range(2)]
    for group, axes, pos_bit, vel_bit in ((0, (0, 1), 0, 2), (1, (2,), 1, 3)):
        pos_valid = group_valid[:, pos_bit]
        vel_valid = group_valid[:, vel_bit]
        valid_positions = np.flatnonzero(pos_valid)
        invalid_prefix = np.r_[0, np.cumsum((~vel_valid).astype(np.int64))]
        break_step = (np.diff(velocity_us) > gap_limit_us) | sequence_jump
        broken_prefix = np.r_[0, np.cumsum(break_step.astype(np.int64))]
        integrated = np.zeros((count, len(axes)), dtype=np.float64)
        for index in range(1, count):
            if vel_valid[index] and vel_valid[index - 1] and not break_step[index - 1]:
                integrated[index] = integrated[index - 1] + .5 * (
                    velocity[index, list(axes)] + velocity[index - 1, list(axes)]
                ) * (int(velocity_us[index]) - int(velocity_us[index - 1])) * 1e-6
            else:
                integrated[index] = integrated[index - 1]
        reference: tuple[int, np.ndarray, np.ndarray, int, int] | None = None
        generation = 0
        for index in range(count):
            if receive_us[index] < mission_start_us:
                continue
            end_us = int(cutoff[index])
            end_velocity = _VelocityAt(
                end_us, index, velocity_us, velocity[:, list(axes)], vel_valid,
                invalid_prefix, broken_prefix, integrated, gap_limit_us,
            )
            end_position = _PositionAt(
                end_us, index, position_us, position[:, list(axes)], pos_valid,
                valid_positions, gap_limit_us,
            )
            reason = "valid"
            if index > 0 and sequence_jump[index - 1]:
                reason = "sequence_jump"
            elif index > 0 and velocity_us[index] - velocity_us[index - 1] > gap_limit_us:
                reason = "time_gap"
            elif not vel_valid[index] or end_velocity is None:
                reason = "velocity_invalid"
            if reason != "valid":
                reference = None
            elif end_position is None:
                reason = "position_invalid"
            if reference is None and reason == "valid":
                assert end_position is not None and end_velocity is not None
                generation += 1
                reference = (end_us, end_position, end_velocity[1],
                             end_velocity[2], int(broken_prefix[end_velocity[2]]))
                reset[index, group] = True
                reason = "anchor_reset"
            if reference is not None and end_velocity is not None:
                segment[index, group] = generation
                ref_time, ref_pos, ref_int, ref_index, ref_break = reference
                if (int(broken_prefix[end_velocity[2]]) != ref_break
                        or invalid_prefix[end_velocity[2] + 1] != invalid_prefix[ref_index + 1]):
                    reference = None
                    reasons_anchored[group][index] = "velocity_invalid"
                else:
                    anchored_vel[index, list(axes)] = end_velocity[1] - ref_int
                    if end_position is not None and not reset[index, group]:
                        anchored_pos[index, list(axes)] = end_position - ref_pos
                        anchored_res[index, list(axes)] = (
                            anchored_pos[index, list(axes)] - anchored_vel[index, list(axes)]
                        )
                        anchored_valid[index, group] = True
                    reasons_anchored[group][index] = reason
            else:
                reasons_anchored[group][index] = reason
            start_us = end_us - window_us
            if start_us < int(cutoff[0]):
                continue
            start_velocity = _VelocityAt(
                start_us, index, velocity_us, velocity[:, list(axes)], vel_valid,
                invalid_prefix, broken_prefix, integrated, gap_limit_us,
            )
            if start_velocity is None or end_velocity is None:
                reasons_rolling[group][index] = "velocity_invalid"
                continue
            if (int(broken_prefix[end_velocity[2]]) != int(broken_prefix[start_velocity[2]])
                    or invalid_prefix[end_velocity[2] + 1]
                    != invalid_prefix[start_velocity[2] + 1]):
                reasons_rolling[group][index] = "time_gap" if (
                    int(broken_prefix[end_velocity[2]]) != int(broken_prefix[start_velocity[2]])
                ) else "velocity_invalid"
                continue
            rolling_vel[index, list(axes)] = end_velocity[1] - start_velocity[1]
            start_position = _PositionAt(
                start_us, index, position_us, position[:, list(axes)], pos_valid,
                valid_positions, gap_limit_us,
            )
            if start_position is None or end_position is None:
                reasons_rolling[group][index] = "position_invalid"
                continue
            rolling_pos[index, list(axes)] = end_position - start_position
            rolling_res[index, list(axes)] = (
                rolling_pos[index, list(axes)] - rolling_vel[index, list(axes)]
            )
            rolling_valid[index, group] = True
            reasons_rolling[group][index] = "valid"
    return (rolling_pos, rolling_vel, rolling_res, rolling_valid,
            anchored_pos, anchored_vel, anchored_res, anchored_valid,
            reset, segment, cutoff, reasons_rolling, reasons_anchored)


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
    measurements = tuple(dataset.Records_Get("GNSS_MEASUREMENT"))
    if measurements:
        observed = {
            (int(row.payload.get("sequence", row.record_sequence)),
             int(row.payload.get("receive_timestamp_us", row.timestamp_us)))
            for row in measurements
        }
        records = tuple(
            row for row in records
            if (int(row.payload.get("sequence", row.record_sequence)),
                int(row.payload.get("receive_timestamp_us", row.timestamp_us))) in observed
        )
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
    position_us, velocity_us = _EffectiveTimes_Get(dataset, records)
    sequence_step = (np.diff(sequence) & 0xFFFFFFFF)
    sequence_jump = sequence_step != 1
    gap_limit_us = 120_000
    window_us = window_s * 1_000_000
    (position_delta, velocity_delta, residual, rolling_valid,
     anchored_position, anchored_velocity, anchored, anchored_valid,
     anchor_reset, segment, cutoff, rolling_reasons,
     anchored_reasons) = _AlignedClosure_Build(
        time, position_us, velocity_us, position, velocity, group_valid,
        sequence_jump, int(dataset.start_timestamp_us or time[0]),
        window_us, gap_limit_us,
    )
    valid_en = rolling_valid[:, 0]
    valid_u = rolling_valid[:, 1]
    eligible = int(np.count_nonzero(cutoff - cutoff[0] >= window_us))
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
        anchored_position_displacement_m=anchored_position,
        anchored_velocity_displacement_m=anchored_velocity,
        segment_en=segment[:, 0], segment_u=segment[:, 1],
        rolling_reason_en=tuple(rolling_reasons[0]),
        rolling_reason_u=tuple(rolling_reasons[1]),
        anchored_reason_en=tuple(anchored_reasons[0]),
        anchored_reason_u=tuple(anchored_reasons[1]),
        position_timestamp_us=position_us, velocity_timestamp_us=velocity_us,
        evidence_cutoff_us=cutoff, evidence_age_us=time-cutoff,
    )
