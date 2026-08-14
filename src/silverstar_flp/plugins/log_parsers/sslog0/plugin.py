from __future__ import annotations

import struct
import zlib
from pathlib import Path

from silverstar_flp.core.context import TaskContext
from silverstar_flp.core.dataset import DecodedRecord, FlightDataset, FlightDatasetBuilder
from silverstar_flp.core.diagnostics import DiagnosticSeverity, ParserDiagnostics
from silverstar_flp.plugins.api.log_parser import LogParserMetadata, LogParserPlugin, ParserError
from silverstar_flp.plugins.log_parsers.sslog0.records import (
    RECORD_DEFINITIONS,
    PayloadDecodeError,
)

FILE_HEADER_SIZE = 64
RECORD_HEADER_SIZE = 24
RECORD_CRC_SIZE = 4
FILE_MAGIC = b"SSLOG0\x00\x00"
SYNC_VALUE = 0x31474C46
SYNC_BYTES = b"FLG1"
COMMON_HEADER_STRUCT = struct.Struct("<IBBHIQI")


class Sslog0ParserPlugin(LogParserPlugin):
    metadata = LogParserMetadata(
        plugin_id="silverstar.log_parser.sslog0",
        version="0.1.0",
        display_name="SSLOG0",
        description="SilverStar Flight Log profile 0 parser",
        supported_profiles=(0,),
    )

    def probe(self, path: Path) -> float:
        try:
            with Path(path).open("rb") as source:
                prefix = source.read(12)
        except OSError:
            return 0.0
        if prefix[:8] != FILE_MAGIC:
            return 0.0
        profile = struct.unpack_from("<H", prefix, 8)[0] if len(prefix) >= 10 else -1
        return 1.0 if profile == 0 else 0.8

    def parse(self, path: Path, context: TaskContext | None = None) -> FlightDataset:
        parse_context = context or TaskContext()
        source_path = Path(path)
        try:
            data = source_path.read_bytes()
        except OSError as exc:
            raise ParserError("log_open_failed", str(exc)) from exc
        if len(data) < FILE_HEADER_SIZE:
            raise ParserError("truncated_file_header", f"size={len(data)}")

        parse_context.Progress_Report(0.01, "parser.header")
        diagnostics = ParserDiagnostics()
        header = self._Header_Parse(data[:FILE_HEADER_SIZE], diagnostics)
        if header["magic_bytes"] != FILE_MAGIC:
            raise ParserError("invalid_sslog_magic")
        if header["profile_id"] not in self.metadata.supported_profiles:
            raise ParserError("unsupported_profile", str(header["profile_id"]))
        if header["file_header_size"] != FILE_HEADER_SIZE:
            raise ParserError("unsupported_file_header_size", str(header["file_header_size"]))
        if header["record_header_size"] != RECORD_HEADER_SIZE:
            raise ParserError("unsupported_record_header_size", str(header["record_header_size"]))
        if header["record_crc_size"] != RECORD_CRC_SIZE:
            raise ParserError("unsupported_record_crc_size", str(header["record_crc_size"]))

        builder = FlightDatasetBuilder()
        offset = FILE_HEADER_SIZE
        previous_sequence: int | None = None
        crc_failure_pending = False
        file_size = len(data)

        while offset < file_size:
            parse_context.Cancel_RaiseIfRequested()
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

            definition = RECORD_DEFINITIONS.get(record_type)
            if definition is None:
                diagnostics.unknown_record_type_count += 1
                diagnostics.Diagnostic_Add(
                    "unknown_record_type",
                    DiagnosticSeverity.INFO,
                    offset=offset,
                    record_sequence=record_sequence,
                    record_type=record_type,
                    record_version=record_version,
                    payload_length=payload_length,
                )
                offset += total_size
                continue
            if record_version not in definition.common_versions:
                diagnostics.unknown_record_version_count += 1
                diagnostics.Diagnostic_Add(
                    "unknown_record_version",
                    DiagnosticSeverity.INFO,
                    offset=offset,
                    record_sequence=record_sequence,
                    record_type=record_type,
                    record_version=record_version,
                    payload_length=payload_length,
                )
                offset += total_size
                continue
            if payload_length not in definition.payload_lengths:
                diagnostics.decoder_failure_count += 1
                diagnostics.Diagnostic_Add(
                    "record_payload_length_mismatch",
                    DiagnosticSeverity.WARNING,
                    offset=offset,
                    record_sequence=record_sequence,
                    record_type=record_type,
                    payload_length=payload_length,
                    expected_lengths=definition.payload_lengths,
                )
                offset += total_size
                continue

            payload_bytes = data[
                offset + RECORD_HEADER_SIZE : offset + RECORD_HEADER_SIZE + payload_length
            ]
            try:
                payload = definition.decoder(payload_bytes)
            except (PayloadDecodeError, struct.error, ValueError) as exc:
                diagnostics.decoder_failure_count += 1
                diagnostics.Diagnostic_Add(
                    "record_decode_failure",
                    DiagnosticSeverity.WARNING,
                    offset=offset,
                    record_sequence=record_sequence,
                    record_type=record_type,
                    error=str(exc),
                )
                offset += total_size
                continue

            builder.Record_Add(
                DecodedRecord(
                    record_type=record_type,
                    record_name=definition.name,
                    record_version=record_version,
                    payload_length=payload_length,
                    record_sequence=record_sequence,
                    timestamp_us=timestamp_us,
                    valid_flags=valid_flags,
                    payload=payload,
                    file_offset=offset,
                ),
                definition.channels,
            )
            diagnostics.decoded_record_count += 1
            offset += total_size
            if diagnostics.record_count % 256 == 0:
                parse_context.Progress_Report(
                    0.02 + (0.96 * offset / max(file_size, 1)), "parser.records"
                )

        parse_context.Progress_Report(0.99, "parser.dataset")
        dataset = builder.Build(
            source_path=source_path,
            file_size=file_size,
            header=header,
            diagnostics=diagnostics,
            metadata={
                "parser_plugin_id": self.metadata.plugin_id,
                "parser_plugin_version": self.metadata.version,
                "container_generation": "SSLOG0",
                "synthetic": False,
            },
        )
        parse_context.Progress_Report(1.0, "parser.complete")
        return dataset

    @staticmethod
    def _Header_Parse(header_bytes: bytes, diagnostics: ParserDiagnostics) -> dict[str, object]:
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
                "header_semantics_invalid", DiagnosticSeverity.ERROR, offset=0
            )
        return header
