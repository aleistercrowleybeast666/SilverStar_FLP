from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any

import numpy as np
from numpy.typing import NDArray

from silverstar_flp.core.diagnostics import ParserDiagnostics


@dataclass(frozen=True, slots=True)
class TimeSeries:
    timestamp_us: NDArray[np.uint64]
    values: NDArray[np.float64]
    unit: str
    quantity: str
    source: str
    valid: NDArray[np.bool_]
    columns: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        timestamps = np.asarray(self.timestamp_us, dtype=np.uint64)
        values = np.asarray(self.values)
        valid = np.asarray(self.valid, dtype=np.bool_)
        if values.ndim == 0:
            values = values.reshape(1)
        if timestamps.ndim != 1 or valid.ndim != 1:
            raise ValueError("timestamp_us and valid must be one-dimensional")
        if values.shape[0] != timestamps.size or valid.size != timestamps.size:
            raise ValueError("time-series arrays must have the same sample count")
        if timestamps.size > 1 and np.any(timestamps[1:] < timestamps[:-1]):
            raise ValueError("time-series timestamps must be monotonic")
        if self.columns and values.ndim > 1 and len(self.columns) != values.shape[1]:
            raise ValueError("column metadata does not match values")
        object.__setattr__(self, "timestamp_us", timestamps)
        object.__setattr__(self, "values", values)
        object.__setattr__(self, "valid", valid)
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    @property
    def count(self) -> int:
        return int(self.timestamp_us.size)

    @property
    def time_s(self) -> NDArray[np.float64]:
        if self.timestamp_us.size == 0:
            return np.asarray([], dtype=np.float64)
        return self.timestamp_us.astype(np.float64) * 1.0e-6

    def finite_values(self) -> NDArray[np.float64]:
        values = np.asarray(self.values, dtype=np.float64)
        if values.ndim == 1:
            return values[self.valid & np.isfinite(values)]
        return values[self.valid & np.all(np.isfinite(values), axis=1)]


@dataclass(frozen=True, slots=True)
class DecodedRecord:
    record_type: int
    record_name: str
    record_version: int
    payload_length: int
    record_sequence: int
    timestamp_us: int
    valid_flags: int
    payload: Mapping[str, Any]
    file_offset: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))


@dataclass(frozen=True, slots=True)
class FlightDataset:
    source_path: Path
    file_size: int
    header: Mapping[str, Any]
    diagnostics: ParserDiagnostics
    records: Mapping[str, tuple[DecodedRecord, ...]]
    series: Mapping[str, TimeSeries]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_path", Path(self.source_path))
        object.__setattr__(self, "header", MappingProxyType(dict(self.header)))
        object.__setattr__(
            self,
            "records",
            MappingProxyType({name: tuple(items) for name, items in self.records.items()}),
        )
        object.__setattr__(self, "series", MappingProxyType(dict(self.series)))
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    def Records_Get(self, record_name: str) -> tuple[DecodedRecord, ...]:
        return self.records.get(record_name, ())

    def Series_Get(self, channel_id: str) -> TimeSeries | None:
        return self.series.get(channel_id)

    @property
    def start_timestamp_us(self) -> int | None:
        initial = self.Records_Get("INITIAL_STATE")
        if initial:
            return initial[0].timestamp_us
        for record in self.Records_Get("EVENT"):
            if int(record.payload.get("event_id", 0)) == 0x03:
                return record.timestamp_us
        return None

    @property
    def mission_duration_s(self) -> float | None:
        start = self.start_timestamp_us
        last = self.diagnostics.last_timestamp_us
        if start is None or last is None or last < start:
            return None
        return (last - start) * 1.0e-6

    def capability_channels(self) -> frozenset[str]:
        return frozenset(self.series)


@dataclass(frozen=True, slots=True)
class ChannelDefinition:
    channel_id: str
    field_name: str
    unit: str
    quantity: str
    columns: tuple[str, ...] = ()
    timestamp_field: str | None = None
    validity_field: str | None = None
    validity_mask: int | None = None


class FlightDatasetBuilder:
    def __init__(self) -> None:
        self._records: dict[str, list[DecodedRecord]] = defaultdict(list)
        self._series_samples: dict[str, list[tuple[int, Any, bool]]] = defaultdict(list)
        self._series_definitions: dict[str, tuple[ChannelDefinition, str]] = {}

    def Record_Add(
        self,
        record: DecodedRecord,
        definitions: Iterable[ChannelDefinition] = (),
    ) -> None:
        self._records[record.record_name].append(record)
        for definition in definitions:
            if definition.field_name not in record.payload:
                continue
            timestamp = int(
                record.payload.get(definition.timestamp_field, record.timestamp_us)
                if definition.timestamp_field
                else record.timestamp_us
            )
            valid = True
            if definition.validity_field:
                raw_validity = (
                    record.valid_flags
                    if definition.validity_field == "__common_valid_flags__"
                    else record.payload.get(definition.validity_field, 0)
                )
                valid = (
                    (int(raw_validity) & definition.validity_mask) == definition.validity_mask
                    if definition.validity_mask is not None
                    else bool(raw_validity)
                )
            self._series_samples[definition.channel_id].append(
                (timestamp, record.payload[definition.field_name], valid)
            )
            self._series_definitions[definition.channel_id] = (
                definition,
                record.record_name,
            )

    def Build(
        self,
        *,
        source_path: Path,
        file_size: int,
        header: Mapping[str, Any],
        diagnostics: ParserDiagnostics,
        metadata: Mapping[str, Any] | None = None,
    ) -> FlightDataset:
        series: dict[str, TimeSeries] = {}
        for channel_id, samples in self._series_samples.items():
            definition, source = self._series_definitions[channel_id]
            ordered = sorted(samples, key=lambda sample: sample[0])
            timestamps = np.asarray([sample[0] for sample in ordered], dtype=np.uint64)
            try:
                values = np.asarray([sample[1] for sample in ordered], dtype=np.float64)
            except (TypeError, ValueError):
                continue
            valid = np.asarray([sample[2] for sample in ordered], dtype=np.bool_)
            series[channel_id] = TimeSeries(
                timestamp_us=timestamps,
                values=values,
                unit=definition.unit,
                quantity=definition.quantity,
                source=source,
                valid=valid,
                columns=definition.columns,
                metadata={"field_name": definition.field_name},
            )
        return FlightDataset(
            source_path=source_path,
            file_size=file_size,
            header=header,
            diagnostics=diagnostics,
            records={name: tuple(items) for name, items in self._records.items()},
            series=series,
            metadata=dict(metadata or {}),
        )
