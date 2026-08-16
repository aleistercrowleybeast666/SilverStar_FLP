from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import numpy as np

from silverstar_flp.core.dataset import FlightDataset

_EVENT_LANDING = 0x2A


class MissionReplayEndReason(StrEnum):
    LANDING = "landing"
    SOURCE_END = "source_end"


@dataclass(frozen=True, slots=True)
class MissionReplayBounds:
    start_timestamp_us: int
    end_timestamp_us: int
    end_reason: MissionReplayEndReason


def MissionLandingTimestamp_Get(
    dataset: FlightDataset,
    *,
    start_timestamp_us: int | None = None,
) -> int | None:
    start = dataset.start_timestamp_us if start_timestamp_us is None else start_timestamp_us
    candidates = (
        int(record.timestamp_us)
        for record in dataset.Records_Get("EVENT")
        if int(record.payload.get("event_id", -1)) == _EVENT_LANDING
        and (start is None or int(record.timestamp_us) >= start)
    )
    return min(candidates, default=None)


def _DatasetValidEndTimestamp_Get(dataset: FlightDataset) -> int | None:
    candidates: list[int] = []
    for series in dataset.series.values():
        if series.count == 0:
            continue
        valid_indices = np.flatnonzero(series.valid)
        if valid_indices.size:
            candidates.append(int(series.timestamp_us[valid_indices[-1]]))
    if candidates:
        return max(candidates)
    return dataset.diagnostics.last_timestamp_us


def MissionReplayBounds_Get(
    dataset: FlightDataset,
    *,
    source_end_timestamp_us: int | None = None,
) -> MissionReplayBounds:
    start = dataset.start_timestamp_us
    if start is None:
        start = dataset.diagnostics.first_timestamp_us or 0
    start = int(start)
    landing = MissionLandingTimestamp_Get(dataset, start_timestamp_us=start)
    if landing is not None:
        return MissionReplayBounds(
            start_timestamp_us=start,
            end_timestamp_us=max(start, landing),
            end_reason=MissionReplayEndReason.LANDING,
        )
    source_end = source_end_timestamp_us
    if source_end is None:
        source_end = _DatasetValidEndTimestamp_Get(dataset)
    return MissionReplayBounds(
        start_timestamp_us=start,
        end_timestamp_us=max(start, int(source_end if source_end is not None else start)),
        end_reason=MissionReplayEndReason.SOURCE_END,
    )
