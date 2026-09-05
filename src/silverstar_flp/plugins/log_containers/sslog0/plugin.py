from __future__ import annotations

import struct
import zlib
from collections.abc import Iterator, Mapping
from typing import Any, BinaryIO

from silverstar_flp.core.diagnostics import DiagnosticSeverity
from silverstar_flp.plugins.api.log_container import (
    ContainerError,
    LogContainerMetadata,
    LogContainerPlugin,
    ParseOptions,
    ProbeResult,
    RawRecordFrame,
)

FILE_HEADER_SIZE = 64
RECORD_HEADER_SIZE = 24
RECORD_CRC_SIZE = 4
FILE_MAGIC = b"SSLOG0\x00\x00"
SYNC_VALUE = 0x31474C46
SYNC_BYTES = b"FLG1"
COMMON_HEADER_STRUCT = struct.Struct("<IBBHIQI")


class Sslog0ContainerPlugin(LogContainerPlugin):
    metadata = LogContainerMetadata(
        plugin_id="silverstar.flight_log.container.0_0",
        container_format_id="SSLOG0",
        version="0.0",
        api_version=1,
        display_name="SilverStar Flight Log Container 0.0",
        builtin=True,
    )

    def probe(self, source: BinaryIO) -> ProbeResult:
        original_offset = source.tell()
        try:
            source.seek(0)
            prefix = source.read(12)
        finally:
            source.seek(original_offset)
        if prefix[:8] != FILE_MAGIC:
            return ProbeResult(0.0, self.metadata.container_format_id)
        profile = struct.unpack_from("<H", prefix, 8)[0] if len(prefix) >= 10 else -1
        return ProbeResult(
            1.0 if profile == 0 else 0.8,
            self.metadata.container_format_id,
            {"profile_id": profile},
        )

    def header_read(
        self,
        source: BinaryIO,
        options: ParseOptions,
    ) -> Mapping[str, Any]:
        source.seek(0)
        header_bytes = source.read(FILE_HEADER_SIZE)
        if len(header_bytes) < FILE_HEADER_SIZE:
            raise ContainerError("truncated_file_header", f"size={len(header_bytes)}")
        options.context.Progress_Report(0.01, "parser.header")
        header = self.Header_ParseBytes(header_bytes, options)
        if header["magic_bytes"] != FILE_MAGIC:
            raise ContainerError("invalid_sslog_magic")
        if header["profile_id"] != 0:
            raise ContainerError("unsupported_profile", str(header["profile_id"]))
        expected_sizes = (
            ("file_header_size", FILE_HEADER_SIZE),
            ("record_header_size", RECORD_HEADER_SIZE),
            ("record_crc_size", RECORD_CRC_SIZE),
        )
        for field_name, expected in expected_sizes:
            if header[field_name] != expected:
                raise ContainerError(f"unsupported_{field_name}", str(header[field_name]))
        return header

    def iter_frames(
        self,
        source: BinaryIO,
        options: ParseOptions,
    ) -> Iterator[RawRecordFrame]:
        diagnostics = options.diagnostics
        source.seek(0)
        data = source.read()
        file_size = len(data)
        offset = FILE_HEADER_SIZE
        previous_sequence: int | None = None
        crc_failure_pending = False

        while offset < file_size:
            options.context.Cancel_RaiseIfRequested()
            remaining = file_size - offset
            if remaining < RECORD_HEADER_SIZE:
                diagnostics.truncated_tail = True
                diagnostics.trailing_bytes = remaining
                diagnostics.Diagnostic_Add(
                    "truncated_record_header",
                    DiagnosticSeverity.WARNING,
                    offset=offset,
                    remaining=remaining,
                )
                break

            if data[offset : offset + 4] != SYNC_BYTES:
                next_sync = data.find(SYNC_BYTES, offset + 1)
                if next_sync < 0:
                    diagnostics.truncated_tail = True
                    diagnostics.trailing_bytes = remaining
                    diagnostics.Diagnostic_Add(
                        "sync_not_found_before_eof",
                        DiagnosticSeverity.WARNING,
                        offset=offset,
                        remaining=remaining,
                    )
                    break
                diagnostics.recovered_after_sync_loss += 1
                diagnostics.Diagnostic_Add(
                    "sync_loss_recovered",
                    DiagnosticSeverity.WARNING,
                    offset=offset,
                    recovered_offset=next_sync,
                    skipped_bytes=next_sync - offset,
                )
                offset = next_sync
                continue

            (
                sync,
                record_version,
                record_type,
                payload_length,
                record_sequence,
                timestamp_us,
                valid_flags,
            ) = COMMON_HEADER_STRUCT.unpack_from(data, offset)
            if sync != SYNC_VALUE:
                offset += 1
                continue
            if payload_length > options.maximum_payload_length:
                diagnostics.Diagnostic_Add(
                    "record_payload_length_exceeds_limit",
                    DiagnosticSeverity.WARNING,
                    offset=offset,
                    record_sequence=record_sequence,
                    payload_length=payload_length,
                    maximum_payload_length=options.maximum_payload_length,
                )
                next_sync = data.find(SYNC_BYTES, offset + 4)
                if next_sync < 0:
                    diagnostics.truncated_tail = True
                    diagnostics.trailing_bytes = remaining
                    break
                diagnostics.recovered_after_sync_loss += 1
                offset = next_sync
                continue

            total_size = RECORD_HEADER_SIZE + payload_length + RECORD_CRC_SIZE
            if total_size > remaining:
                next_sync = data.find(SYNC_BYTES, offset + 4)
                if next_sync >= 0:
                    diagnostics.recovered_after_sync_loss += 1
                    diagnostics.Diagnostic_Add(
                        "invalid_length_recovered",
                        DiagnosticSeverity.WARNING,
                        offset=offset,
                        record_sequence=record_sequence,
                        payload_length=payload_length,
                        recovered_offset=next_sync,
                    )
                    offset = next_sync
                    continue
                diagnostics.truncated_tail = True
                diagnostics.trailing_bytes = remaining
                diagnostics.Diagnostic_Add(
                    "truncated_record_payload",
                    DiagnosticSeverity.WARNING,
                    offset=offset,
                    record_sequence=record_sequence,
                    payload_length=payload_length,
                    remaining=remaining,
                )
                break

            crc_offset = offset + RECORD_HEADER_SIZE + payload_length
            expected_crc = struct.unpack_from("<I", data, crc_offset)[0]
            actual_crc = zlib.crc32(data[offset:crc_offset]) & 0xFFFFFFFF
            if expected_crc != actual_crc:
                diagnostics.record_crc_failures += 1
                diagnostics.Diagnostic_Add(
                    "record_crc_failure",
                    DiagnosticSeverity.WARNING,
                    offset=offset,
                    record_sequence=record_sequence,
                    expected_crc=expected_crc,
                    actual_crc=actual_crc,
                )
                next_sync = data.find(SYNC_BYTES, offset + 1)
                if next_sync < 0:
                    diagnostics.truncated_tail = True
                    diagnostics.trailing_bytes = file_size - offset
                    break
                crc_failure_pending = True
                offset = next_sync
                continue

            if crc_failure_pending:
                diagnostics.recovered_after_crc += 1
                crc_failure_pending = False

            diagnostics.record_count += 1
            diagnostics.first_timestamp_us = (
                timestamp_us
                if diagnostics.first_timestamp_us is None
                else min(diagnostics.first_timestamp_us, timestamp_us)
            )
            diagnostics.last_timestamp_us = (
                timestamp_us
                if diagnostics.last_timestamp_us is None
                else max(diagnostics.last_timestamp_us, timestamp_us)
            )
            if previous_sequence is not None:
                expected_sequence = (previous_sequence + 1) & 0xFFFFFFFF
                if record_sequence != expected_sequence:
                    diagnostics.sequence_gap_count += 1
                    missing = (
                        (record_sequence - expected_sequence) & 0xFFFFFFFF
                        if record_sequence != previous_sequence
                        else 1
                    )
                    if missing > 1_000_000_000:
                        missing = 1
                    diagnostics.sequence_missing_count += int(missing)
                    diagnostics.Diagnostic_Add(
                        "record_sequence_gap",
                        DiagnosticSeverity.WARNING,
                        offset=offset,
                        record_sequence=record_sequence,
                        previous_sequence=previous_sequence,
                        missing_count=int(missing),
                    )
            previous_sequence = record_sequence

            payload_offset = offset + RECORD_HEADER_SIZE
            yield RawRecordFrame(
                record_type=record_type,
                record_version=record_version,
                payload_length=payload_length,
                sequence=record_sequence,
                timestamp_us=timestamp_us,
                valid_flags=valid_flags,
                payload_bytes=bytes(data[payload_offset:crc_offset]),
                source_offset=offset,
                crc_valid=True,
            )
            offset += total_size
            if diagnostics.record_count % 256 == 0:
                options.context.Progress_Report(
                    0.02 + (0.80 * offset / max(file_size, 1)),
                    "parser.records",
                )

    @staticmethod
    def Header_ParseBytes(
        header_bytes: bytes,
        options: ParseOptions,
    ) -> dict[str, object]:
        diagnostics = options.diagnostics
        expected_crc = struct.unpack_from("<I", header_bytes, 60)[0]
        actual_crc = zlib.crc32(header_bytes[:60]) & 0xFFFFFFFF
        diagnostics.header_crc_expected = expected_crc
        diagnostics.header_crc_actual = actual_crc
        header = {
            "magic_bytes": header_bytes[:8],
            "magic": header_bytes[:6].decode("ascii", errors="replace"),
            "profile_id": struct.unpack_from("<H", header_bytes, 8)[0],
            "file_header_size": struct.unpack_from("<H", header_bytes, 10)[0],
            "record_header_size": struct.unpack_from("<H", header_bytes, 12)[0],
            "configured_imu_rate_hz": struct.unpack_from("<H", header_bytes, 14)[0],
            "expected_mechanization_rate_hz": struct.unpack_from("<H", header_bytes, 16)[0],
            "coordinate_frame": header_bytes[18],
            "axis_numbers": tuple(header_bytes[19:22]),
            "quaternion_order": header_bytes[22],
            "quaternion_convention": header_bytes[23],
            "gravity_mps2": struct.unpack_from("<f", header_bytes, 24)[0],
            "air_compatibility_tag": header_bytes[28:36].decode("ascii", errors="replace"),
            "build_id": header_bytes[36:44].decode("ascii", errors="replace"),
            "record_crc_size": struct.unpack_from("<H", header_bytes, 44)[0],
            "mechanization_subsample_count": struct.unpack_from("<H", header_bytes, 46)[0],
            "firmware_version": tuple(header_bytes[48:52]),
            "maximum_record_size": struct.unpack_from("<H", header_bytes, 52)[0],
            "header_crc32": expected_crc,
        }
        semantics_valid = (
            header["magic_bytes"] == FILE_MAGIC
            and header["file_header_size"] == FILE_HEADER_SIZE
            and header["record_header_size"] == RECORD_HEADER_SIZE
            and header["record_crc_size"] == RECORD_CRC_SIZE
            and header["coordinate_frame"] == 1
            and header["axis_numbers"] == (3, 1, 2)
            and header["quaternion_order"] == 1
            and header["quaternion_convention"] == 1
        )
        diagnostics.header_valid = bool(semantics_valid and expected_crc == actual_crc)
        if expected_crc != actual_crc:
            diagnostics.Diagnostic_Add(
                "header_crc_failure",
                DiagnosticSeverity.WARNING,
                offset=60,
                expected_crc=expected_crc,
                actual_crc=actual_crc,
            )
        if not semantics_valid:
            diagnostics.Diagnostic_Add(
                "header_semantics_invalid",
                DiagnosticSeverity.ERROR,
                offset=0,
            )
        return header
