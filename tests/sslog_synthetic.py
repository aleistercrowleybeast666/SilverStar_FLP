from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass, field
from pathlib import Path

GRAVITY_MPS2 = 9.78
START_TIMESTAMP_US = 1_000_000


def Header_Build(*, build_id: bytes = b"SILV0008") -> bytes:
    header = bytearray(64)
    header[0:8] = b"SSLOG0\x00\x00"
    struct.pack_into("<H", header, 8, 0)
    struct.pack_into("<H", header, 10, 64)
    struct.pack_into("<H", header, 12, 24)
    struct.pack_into("<H", header, 14, 100)
    struct.pack_into("<H", header, 16, 50)
    header[18] = 1
    header[19:22] = bytes((3, 1, 2))
    header[22] = 1
    header[23] = 1
    struct.pack_into("<f", header, 24, GRAVITY_MPS2)
    header[28:36] = b"AIR-NCRC"
    header[36:44] = build_id
    struct.pack_into("<H", header, 44, 4)
    struct.pack_into("<H", header, 46, 2)
    header[48:52] = bytes((0, 1, 0, 8))
    struct.pack_into("<H", header, 52, 256)
    struct.pack_into("<I", header, 60, zlib.crc32(header[:60]) & 0xFFFFFFFF)
    return bytes(header)


def Event_Payload(event_id: int, arg0: int = 0, arg1: int = 0) -> bytes:
    return struct.pack("<B3xII", event_id, arg0, arg1)


def InitialState_Payload() -> bytes:
    payload = bytearray()
    payload += struct.pack("<BBBBHHHH", 1, 1, 1, 3, 200, 10, 20, 0)
    payload += struct.pack("<4f", 1.0, 0.0, 0.0, 0.0)
    payload += struct.pack("<3f", 0.0, 0.0, GRAVITY_MPS2)
    payload += struct.pack("<3f", 0.0, 0.0, 0.0)
    payload += struct.pack("<3f", 20.0, 0.0, 40.0)
    payload += struct.pack("<iii", 31_0000000, 121_0000000, 100_000)
    payload += struct.pack("<3f", 1.0, 1.0, 2.0)
    payload += struct.pack("<3f", 0.0, 0.0, 0.0)
    payload += struct.pack("<3f", 0.5, 0.5, 0.5)
    payload += struct.pack("<ff", 120.0, 1.0)
    payload += struct.pack("<6f", 4.0, 4.0, 9.0, 0.25, 0.25, 0.25)
    assert len(payload) == 144
    return bytes(payload)


def SystemConfig_Payload(
    *, imu_corrected_decimation: int = 1, increment_decimation: int = 1
) -> bytes:
    payload = bytearray()
    payload += bytes((0, 1, 0, 8))
    payload += struct.pack("<I", 0)
    payload += bytes(range(1, 11))
    payload += bytes((1, 1, 1, 1))
    payload += struct.pack("<BB", 1, imu_corrected_decimation)
    payload += struct.pack("<6f", 4.0, 4.0, 9.0, 0.25, 0.25, 0.25)
    payload += struct.pack("<3f", 1.5, 1.5, 2.0)
    payload += struct.pack("<5f", 1.0, 1.5, 2.5, 0.3, 5.0)
    payload += struct.pack("<7f", 6.635, 10.828, 9.210, 13.816, 11.345, 16.266, 10.0)
    payload += struct.pack("<II", 0xFFFFFFFF, 0x12345678)
    payload += struct.pack("<10H", 100, 10, 50, 50, 50, 2, 50, 50, 500, 0)
    decimation = [1] * 10
    decimation[5] = increment_decimation
    payload += struct.pack("<10H", *decimation)
    payload += struct.pack("<4I", 100_000, 100_000, 100_000, 1_000_000)
    payload += struct.pack("<HBB", 4096, 16, 16)
    assert len(payload) == 176
    return bytes(payload)


def MissionConfig_Payload(
    *, deploy_mask: int = 4, deploy_delay_ms: int = 100, landing_enable: int = 0
) -> bytes:
    payload = bytearray()
    payload += struct.pack("<8B", 2, 1, 0, deploy_mask, 0, landing_enable, 2, 1)
    payload += struct.pack("<4f", 0.0, 0.0, 45.0, -1.0)
    payload += struct.pack("<4I", 20, deploy_delay_ms, 500, 5)
    payload += struct.pack("<fIf", 0.5, 1000, 0.2)
    payload += struct.pack("<f4I3f2I", 1.0, 5, 50, 80, 500, 30.0, 0.1, 0.5, 1000, 200)
    assert len(payload) == 92
    return bytes(payload)


def ImuCorrected_Payload(timestamp_us: int, sequence: int) -> bytes:
    payload = struct.pack(
        "<QQIHHI3f3ffBBH",
        timestamp_us,
        timestamp_us + 100,
        sequence,
        1,
        1,
        3,
        0.0,
        0.0,
        GRAVITY_MPS2,
        0.0,
        0.0,
        0.0,
        25.0,
        1,
        1,
        0,
    )
    assert len(payload) == 60
    return payload


def InertialIncrement_Payload(start_us: int, end_us: int, sequence: int) -> bytes:
    dt_s = (end_us - start_us) * 1.0e-6
    payload = struct.pack(
        "<QQIf3f3fI",
        start_us,
        end_us,
        sequence,
        dt_s,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        GRAVITY_MPS2 * dt_s,
        0,
    )
    assert len(payload) == 52
    return payload


def PureIns_Payload(update_sequence: int, dt_s: float = 0.02) -> bytes:
    payload = bytearray()
    payload += struct.pack("<I", update_sequence)
    payload += struct.pack("<4f", 1.0, 0.0, 0.0, 0.0)
    payload += struct.pack("<3f", 0.0, 0.0, 0.0)
    payload += struct.pack("<3f", 0.0, 0.0, 0.0)
    payload += struct.pack("<3f", 0.0, 0.0, 0.0)
    payload += struct.pack("<fIBB2x", dt_s, 0, 1, 1)
    assert len(payload) == 68
    return payload


@dataclass(slots=True)
class SyntheticSslogBuilder:
    """Builds explicitly synthetic SSLOG0 test bytes; never presented as flight data."""

    records: list[bytes] = field(default_factory=list)
    sequence: int = 0
    build_id: bytes = b"SILV0008"

    def Record_Add(
        self,
        record_type: int,
        payload: bytes,
        timestamp_us: int,
        *,
        valid_flags: int = 0,
        record_version: int = 0,
        corrupt_crc: bool = False,
        sequence: int | None = None,
    ) -> None:
        record_sequence = self.sequence if sequence is None else sequence
        header = struct.pack(
            "<IBBHIQI",
            0x31474C46,
            record_version,
            record_type,
            len(payload),
            record_sequence,
            timestamp_us,
            valid_flags,
        )
        crc = zlib.crc32(header + payload) & 0xFFFFFFFF
        if corrupt_crc:
            crc ^= 0xFFFFFFFF
        self.records.append(header + payload + struct.pack("<I", crc))
        self.sequence = (record_sequence + 1) & 0xFFFFFFFF

    def Bytes_Build(self, *, trailing_bytes: bytes = b"") -> bytes:
        return Header_Build(build_id=self.build_id) + b"".join(self.records) + trailing_bytes

    def File_Write(self, path: Path, *, trailing_bytes: bytes = b"") -> Path:
        path.write_bytes(self.Bytes_Build(trailing_bytes=trailing_bytes))
        return path


def StationaryFlight_Build(
    path: Path,
    *,
    include_corrected_imu: bool = True,
    include_recorded_increment: bool = True,
    update_count: int = 8,
) -> Path:
    builder = SyntheticSslogBuilder()
    builder.Record_Add(0x19, MissionConfig_Payload(), START_TIMESTAMP_US)
    builder.Record_Add(0x05, SystemConfig_Payload(), START_TIMESTAMP_US)
    builder.Record_Add(0x0D, InitialState_Payload(), START_TIMESTAMP_US)
    builder.Record_Add(0x02, Event_Payload(0x03), START_TIMESTAMP_US)
    if include_corrected_imu:
        for sample_index in range(update_count * 2 + 1):
            timestamp = START_TIMESTAMP_US + sample_index * 10_000
            builder.Record_Add(
                0x16,
                ImuCorrected_Payload(timestamp, sample_index + 1),
                timestamp,
                valid_flags=3,
            )
    if include_recorded_increment:
        for update_index in range(update_count):
            start = START_TIMESTAMP_US + update_index * 20_000
            end = start + 20_000
            builder.Record_Add(
                0x13,
                InertialIncrement_Payload(start, end, update_index + 1),
                end,
                valid_flags=3,
            )
            builder.Record_Add(
                0x07,
                PureIns_Payload(update_index + 1),
                end,
                valid_flags=3,
            )
    return builder.File_Write(path)
