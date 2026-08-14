from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from silverstar_flp.core.dataset import FlightDataset, TimeSeries


@dataclass(frozen=True, slots=True)
class ApogeeEstimate:
    timestamp_us: int | None
    altitude_m: float | None
    method: str
    confidence: str


@dataclass(frozen=True, slots=True)
class TimelineEvent:
    timestamp_us: int
    name: str
    category: str
    arg0: int = 0
    arg1: int = 0


@dataclass(frozen=True, slots=True)
class FlightSummary:
    source_name: str
    mission_start_timestamp_us: int | None
    duration_s: float | None
    maximum_altitude_m: float | None
    maximum_speed_mps: float | None
    maximum_acceleration_mps2: float | None
    apogee: ApogeeEstimate
    timeline: tuple[TimelineEvent, ...]
    decoded_record_count: int
    crc_failure_count: int
    sequence_gap_count: int
    synthetic: bool


def _Navigation_Select(dataset: FlightDataset) -> tuple[str, TimeSeries | None, TimeSeries | None]:
    candidates = (
        (
            "Recorded KF6",
            "kf6.recorded.navigation.position_enu",
            "kf6.recorded.navigation.velocity_enu",
        ),
        (
            "Recorded Pure INS",
            "pure_ins.recorded.navigation.position_enu",
            "pure_ins.recorded.navigation.velocity_enu",
        ),
    )
    for name, position_id, velocity_id in candidates:
        position = dataset.Series_Get(position_id)
        velocity = dataset.Series_Get(velocity_id)
        if position is not None or velocity is not None:
            return name, position, velocity
    return "No navigation solution", None, None


def _Maximum_VectorNorm(series: TimeSeries | None) -> float | None:
    if series is None or series.count == 0:
        return None
    values = np.asarray(series.values, dtype=np.float64)
    if values.ndim != 2:
        finite = values[series.valid & np.isfinite(values)]
        return float(np.max(np.abs(finite))) if finite.size else None
    valid = series.valid & np.all(np.isfinite(values), axis=1)
    return float(np.max(np.linalg.norm(values[valid], axis=1))) if np.any(valid) else None


def _Apogee_Estimate(position: TimeSeries | None, velocity: TimeSeries | None) -> ApogeeEstimate:
    if position is None or position.count == 0 or position.values.ndim != 2:
        return ApogeeEstimate(None, None, "unavailable", "UNAVAILABLE")
    altitude = np.asarray(position.values[:, 2], dtype=np.float64)
    valid_altitude = position.valid & np.isfinite(altitude)
    if not np.any(valid_altitude):
        return ApogeeEstimate(None, None, "unavailable", "UNAVAILABLE")
    if velocity is not None and velocity.count >= 2 and velocity.values.ndim == 2:
        vertical_velocity = np.asarray(velocity.values[:, 2], dtype=np.float64)
        candidates = np.flatnonzero(
            velocity.valid[1:]
            & velocity.valid[:-1]
            & np.isfinite(vertical_velocity[1:])
            & np.isfinite(vertical_velocity[:-1])
            & (vertical_velocity[:-1] > 0.0)
            & (vertical_velocity[1:] <= 0.0)
        )
        if candidates.size:
            index = int(candidates[-1])
            first_time = int(velocity.timestamp_us[index])
            second_time = int(velocity.timestamp_us[index + 1])
            denominator = vertical_velocity[index] - vertical_velocity[index + 1]
            fraction = vertical_velocity[index] / denominator if denominator else 0.0
            timestamp = int(first_time + fraction * (second_time - first_time))
            altitude_value = float(
                np.interp(
                    timestamp,
                    position.timestamp_us.astype(np.float64),
                    altitude,
                )
            )
            return ApogeeEstimate(
                timestamp, altitude_value, "vertical_velocity_zero_crossing", "HIGH"
            )
    valid_indices = np.flatnonzero(valid_altitude)
    maximum_index = int(valid_indices[np.argmax(altitude[valid_altitude])])
    return ApogeeEstimate(
        int(position.timestamp_us[maximum_index]),
        float(altitude[maximum_index]),
        "maximum_recorded_altitude",
        "MEDIUM",
    )


def FlightSummary_Build(dataset: FlightDataset) -> FlightSummary:
    source_name, position, velocity = _Navigation_Select(dataset)
    maximum_altitude: float | None = None
    if position is not None and position.count and position.values.ndim == 2:
        altitude = np.asarray(position.values[:, 2], dtype=np.float64)
        valid = position.valid & np.isfinite(altitude)
        if np.any(valid):
            maximum_altitude = float(np.max(altitude[valid]))
    acceleration = dataset.Series_Get("pure_ins.recorded.navigation.linear_accel_enu")
    if acceleration is None:
        acceleration = dataset.Series_Get("imu.corrected.accel_b")
    events = tuple(
        TimelineEvent(
            timestamp_us=record.timestamp_us,
            name=str(record.payload["event_name"]),
            category=(
                "mission" if int(record.payload["event_id"]) in (0x03, 0x29, 0x2A) else "system"
            ),
            arg0=int(record.payload["arg0"]),
            arg1=int(record.payload["arg1"]),
        )
        for record in sorted(dataset.Records_Get("EVENT"), key=lambda item: item.timestamp_us)
    )
    duration = dataset.mission_duration_s
    if duration is not None and (not math.isfinite(duration) or duration < 0.0):
        duration = None
    return FlightSummary(
        source_name=source_name,
        mission_start_timestamp_us=dataset.start_timestamp_us,
        duration_s=duration,
        maximum_altitude_m=maximum_altitude,
        maximum_speed_mps=_Maximum_VectorNorm(velocity),
        maximum_acceleration_mps2=_Maximum_VectorNorm(acceleration),
        apogee=_Apogee_Estimate(position, velocity),
        timeline=events,
        decoded_record_count=dataset.diagnostics.decoded_record_count,
        crc_failure_count=dataset.diagnostics.record_crc_failures,
        sequence_gap_count=dataset.diagnostics.sequence_gap_count,
        synthetic=bool(dataset.metadata.get("synthetic", False)),
    )
