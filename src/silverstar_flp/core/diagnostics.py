from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class DiagnosticSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class Diagnostic:
    code: str
    severity: DiagnosticSeverity
    offset: int | None = None
    record_sequence: int | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ParserDiagnostics:
    header_valid: bool = False
    header_crc_expected: int | None = None
    header_crc_actual: int | None = None
    record_count: int = 0
    decoded_record_count: int = 0
    record_crc_failures: int = 0
    recovered_after_crc: int = 0
    recovered_after_sync_loss: int = 0
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

    @property
    def header_crc_valid(self) -> bool:
        return (
            self.header_crc_expected is not None
            and self.header_crc_actual is not None
            and self.header_crc_expected == self.header_crc_actual
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
            "recovered_after_crc": self.recovered_after_crc,
            "recovered_after_sync_loss": self.recovered_after_sync_loss,
            "unknown_record_type_count": self.unknown_record_type_count,
            "unknown_record_version_count": self.unknown_record_version_count,
            "decoder_failure_count": self.decoder_failure_count,
            "sequence_gap_count": self.sequence_gap_count,
            "sequence_missing_count": self.sequence_missing_count,
            "truncated_tail": self.truncated_tail,
            "trailing_bytes": self.trailing_bytes,
            "first_timestamp_us": self.first_timestamp_us,
            "last_timestamp_us": self.last_timestamp_us,
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
