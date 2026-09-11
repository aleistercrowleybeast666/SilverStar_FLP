from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Any


class DiagnosticSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class DataQualityStatus(StrEnum):
    CLEAN = "clean"
    WARNINGS = "warnings"


@dataclass(frozen=True, slots=True)
class Diagnostic:
    code: str
    severity: DiagnosticSeverity
    offset: int | None = None
    record_sequence: int | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DamagedSpan:
    start_offset: int
    end_offset: int
    reason: str
    raw_hex: str
    record_sequence: int | None = None
    record_type: int | None = None
    record_version: int | None = None
    timestamp_us: int | None = None

    @property
    def byte_count(self) -> int:
        return max(0, self.end_offset - self.start_offset)

    def ToDict(self) -> dict[str, Any]:
        return {
            "start_offset": self.start_offset,
            "end_offset": self.end_offset,
            "byte_count": self.byte_count,
            "reason": self.reason,
            "raw_hex": self.raw_hex,
            "record_sequence": self.record_sequence,
            "record_type": self.record_type,
            "record_version": self.record_version,
            "timestamp_us": self.timestamp_us,
        }


@dataclass(slots=True)
class ParserDiagnostics:
    header_valid: bool = False
    header_crc_expected: int | None = None
    header_crc_actual: int | None = None
    record_count: int = 0
    decoded_record_count: int = 0
    record_crc_failures: int = 0
    record_length_failures: int = 0
    recovered_after_crc: int = 0
    recovered_after_sync_loss: int = 0
    resync_count: int = 0
    resync_candidate_count: int = 0
    resync_failure_count: int = 0
    unknown_record_type_count: int = 0
    unknown_record_version_count: int = 0
    decoder_failure_count: int = 0
    sequence_gap_count: int = 0
    sequence_missing_count: int = 0
    truncated_tail: bool = False
    trailing_bytes: int = 0
    first_timestamp_us: int | None = None
    last_timestamp_us: int | None = None
    diagnostics: list[Diagnostic] = field(default_factory=list)
    damaged_spans: list[DamagedSpan] = field(default_factory=list)

    def Diagnostic_Add(
        self,
        code: str,
        severity: DiagnosticSeverity,
        *,
        offset: int | None = None,
        record_sequence: int | None = None,
        **details: Any,
    ) -> None:
        self.diagnostics.append(
            Diagnostic(
                code=code,
                severity=severity,
                offset=offset,
                record_sequence=record_sequence,
                details=dict(details),
            )
        )

    def DamagedSpan_Add(
        self,
        *,
        start_offset: int,
        end_offset: int,
        reason: str,
        raw_bytes: bytes,
        record_sequence: int | None = None,
        record_type: int | None = None,
        record_version: int | None = None,
        timestamp_us: int | None = None,
    ) -> None:
        self.damaged_spans.append(
            DamagedSpan(
                start_offset=start_offset,
                end_offset=end_offset,
                reason=reason,
                raw_hex=raw_bytes.hex().upper(),
                record_sequence=record_sequence,
                record_type=record_type,
                record_version=record_version,
                timestamp_us=timestamp_us,
            )
        )

    @property
    def header_crc_valid(self) -> bool:
        return (
            self.header_crc_expected is not None
            and self.header_crc_actual is not None
            and self.header_crc_expected == self.header_crc_actual
        )

    @property
    def has_integrity_warnings(self) -> bool:
        return bool(
            not self.header_valid
            or self.record_crc_failures
            or self.record_length_failures
            or self.resync_count
            or self.resync_failure_count
            or self.sequence_gap_count
            or self.truncated_tail
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "header_valid": self.header_valid,
            "header_crc_valid": self.header_crc_valid,
            "header_crc_expected": self.header_crc_expected,
            "header_crc_actual": self.header_crc_actual,
            "record_count": self.record_count,
            "decoded_record_count": self.decoded_record_count,
            "record_crc_failures": self.record_crc_failures,
            "record_length_failures": self.record_length_failures,
            "recovered_after_crc": self.recovered_after_crc,
            "recovered_after_sync_loss": self.recovered_after_sync_loss,
            "resync_count": self.resync_count,
            "resync_candidate_count": self.resync_candidate_count,
            "resync_failure_count": self.resync_failure_count,
            "unknown_record_type_count": self.unknown_record_type_count,
            "unknown_record_version_count": self.unknown_record_version_count,
            "decoder_failure_count": self.decoder_failure_count,
            "sequence_gap_count": self.sequence_gap_count,
            "sequence_missing_count": self.sequence_missing_count,
            "truncated_tail": self.truncated_tail,
            "trailing_bytes": self.trailing_bytes,
            "first_timestamp_us": self.first_timestamp_us,
            "last_timestamp_us": self.last_timestamp_us,
            "damaged_spans": [item.ToDict() for item in self.damaged_spans],
            "diagnostics": [
                {
                    "code": item.code,
                    "severity": item.severity.value,
                    "offset": item.offset,
                    "record_sequence": item.record_sequence,
                    "details": item.details,
                }
                for item in self.diagnostics
            ],
        }


@dataclass(frozen=True, slots=True)
class DataQualitySummary:
    status: DataQualityStatus
    valid_record_count: int
    crc_failure_count: int
    length_failure_count: int
    resync_count: int
    sequence_gap_count: int
    sequence_missing_count: int
    unknown_record_count: int
    decoder_failure_count: int
    damaged_span_count: int
    logger_overflow_count: int
    truncated_tail: bool
    record_counts: Mapping[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "record_counts",
            MappingProxyType(dict(self.record_counts)),
        )

    @classmethod
    def FromDiagnostics(
        cls,
        diagnostics: ParserDiagnostics,
        *,
        record_counts: Mapping[str, int] | None = None,
        logger_overflow_count: int = 0,
    ) -> DataQualitySummary:
        has_warnings = bool(
            diagnostics.has_integrity_warnings
            or diagnostics.unknown_record_type_count
            or diagnostics.unknown_record_version_count
            or diagnostics.decoder_failure_count
            or logger_overflow_count
        )
        return cls(
            status=(
                DataQualityStatus.WARNINGS
                if has_warnings
                else DataQualityStatus.CLEAN
            ),
            valid_record_count=diagnostics.record_count,
            crc_failure_count=diagnostics.record_crc_failures,
            length_failure_count=diagnostics.record_length_failures,
            resync_count=diagnostics.resync_count,
            sequence_gap_count=diagnostics.sequence_gap_count,
            sequence_missing_count=diagnostics.sequence_missing_count,
            unknown_record_count=(
                diagnostics.unknown_record_type_count
                + diagnostics.unknown_record_version_count
            ),
            decoder_failure_count=diagnostics.decoder_failure_count,
            damaged_span_count=len(diagnostics.damaged_spans),
            logger_overflow_count=logger_overflow_count,
            truncated_tail=diagnostics.truncated_tail,
            record_counts=dict(record_counts or {}),
        )

    def ToDict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "valid_record_count": self.valid_record_count,
            "crc_failure_count": self.crc_failure_count,
            "length_failure_count": self.length_failure_count,
            "resync_count": self.resync_count,
            "sequence_gap_count": self.sequence_gap_count,
            "sequence_missing_count": self.sequence_missing_count,
            "unknown_record_count": self.unknown_record_count,
            "decoder_failure_count": self.decoder_failure_count,
            "damaged_span_count": self.damaged_span_count,
            "logger_overflow_count": self.logger_overflow_count,
            "truncated_tail": self.truncated_tail,
            "record_counts": dict(self.record_counts),
        }
