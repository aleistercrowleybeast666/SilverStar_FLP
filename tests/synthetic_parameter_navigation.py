"""Matching synthetic .ssdecoder 1.2/log pair with dynamic IMU and barometer."""

import json
import math
import struct
from pathlib import Path

from silverstar_flp.decoder_profiles.discovery import DecoderProfileCache
from silverstar_flp.log_open import LogOpenCoordinator, LogOpenRequest
from silverstar_flp.plugins.registry import builtin_registry
from tests.parameter_fixtures import FirmwareSets_Build
from tests.sslog_synthetic import START_TIMESTAMP_US, SyntheticSslogBuilder
from tests.test_decoder_profiles import (
    _DescriptorPayload_Build,
    _Package_Write,
    _PackageFiles_Build,
)


def NavigationPair_Open(
    directory: Path, overrides=None, *, preflight_us=0, flight_samples=1001, omit_imu=False
):
    directory.mkdir(parents=True, exist_ok=True)
    fixtures = Path(__file__).parent / "fixtures/parameter_contracts"
    catalog = json.loads(
        (fixtures / "synthetic_navigation_catalog.json").read_text(encoding="utf8")
    )
    semantics = json.loads(
        (fixtures / "synthetic_navigation_semantics.json").read_text(encoding="utf8")
    )
    semantics["firmware_algorithm_parameters"] = FirmwareSets_Build(overrides)
    files, hashes = _PackageFiles_Build(catalog_document=catalog, semantics_document=semantics)
    package, _ = _Package_Write(directory / "SYNTHETIC_navigation.ssdecoder", files=files)
    records = {r["name"]: r for r in catalog["records"]}
    builder = SyntheticSslogBuilder()

    def add(name, timestamp, values, flags=0):
        record = records[name]
        payload = bytearray()
        formats = {
            "f32": "f",
            "f64": "d",
            "u8": "B",
            "u16": "H",
            "u32": "I",
            "u64": "Q",
            "i32": "i",
        }
        for field in record["fields"]:
            count = field.get("count", 1)
            kind = field["type"]
            if kind == "pad":
                payload.extend(bytes(count))
                continue
            value = values.get(field["name"], 0 if count == 1 else [0] * count)
            if count == 1:
                value = [value]
            payload.extend(struct.pack("<" + formats[kind] * count, *value))
        builder.Record_Add(int(record["id"], 0), bytes(payload), timestamp, valid_flags=flags)

    start = START_TIMESTAMP_US + preflight_us
    if preflight_us:
        add("EVENT", START_TIMESTAMP_US - 4, {"event_id": 1})
    builder.Record_Add(0x1D, _DescriptorPayload_Build(hashes), START_TIMESTAMP_US - 3)
    add(
        "CALIBRATION_RESULT",
        start - 2,
        {
            "source_id": 1,
            "virtual_imu_id": 1,
            "state": 4,
            "ready": 1,
            "accel_scale": [1] * 3,
            "gyro_scale": [1] * 3,
        },
    )
    kf = {p["id"]: p["value"] for p in semantics["firmware_algorithm_parameters"][1]["parameters"]}
    p0 = [kf[f"p0_{group}_{axis}"] for group in ("position", "velocity") for axis in "enu"]
    add(
        "SYSTEM_CONFIG",
        start - 1,
        {
            "configured_imu_rate_hz": 100,
            "mechanization_subsample_count": 2,
            "mechanization_min_sample_rate_hz": 50,
            "mechanization_max_sample_rate_hz": 200,
            "p0_diagonal": p0,
            "process_accel_std_mps2": [kf[f"process_accel_std_{axis}"] for axis in "enu"],
            "nis_profile": [
                kf[name]
                for name in (
                    "nis_1d_soft",
                    "nis_1d_hard",
                    "nis_2d_soft",
                    "nis_2d_hard",
                    "nis_3d_soft",
                    "nis_3d_hard",
                    "nis_max_r_scale",
                )
            ],
        },
    )
    add(
        "INITIAL_STATE",
        start,
        {"q_nb": [1, 0, 0, 0], "p0_diagonal": p0, "barometer_origin_std_m": 0.2},
    )
    add("EVENT", start, {"event_id": 3})
    for index in range(flight_samples):
        timestamp = start + index * 10000
        t = index * 0.01
        if not omit_imu:
            add(
                "IMU_CORRECTED",
                timestamp,
                {
                    "sample_timestamp_us": timestamp,
                    "receive_timestamp_us": timestamp,
                    "sequence": index + 1,
                    "source_id": 1,
                    "virtual_imu_id": 1,
                    "valid_mask": 3,
                    "accel_b_mps2": [
                        0.4 * math.cos(0.9 * t),
                        0.3 * math.sin(0.7 * t),
                        9.78 + 2 * math.sin(1.2 * t),
                    ],
                    "gyro_b_radps": [0, 0, 0.04 * math.cos(t)],
                    "correction_valid": 1,
                },
                3,
            )
        if index and index % 5 == 0:
            altitude = 2 / 1.2 * t - 2 / 1.2**2 * math.sin(1.2 * t)
            add(
                "BARO_NATIVE",
                timestamp,
                {
                    "source_descriptor_id": 3,
                    "sample_timestamp_us": timestamp,
                    "receive_timestamp_us": timestamp,
                    "sequence": index,
                    "altitude_m": altitude,
                    "altitude_variance_m2": 16,
                    "valid_mask": 1,
                },
                4,
            )
            add(
                "BARO_MEASUREMENT",
                timestamp,
                {
                    "sample_timestamp_us": timestamp,
                    "receive_timestamp_us": timestamp,
                    "sequence": index,
                    "relative_altitude_m": altitude,
                    "variance_m2": max(16, kf["baro_std_m"] ** 2) + 0.04,
                    "valid_mask": 1,
                },
                4,
            )
    log = builder.File_Write(directory / "SYNTHETIC_navigation.BIN")
    return LogOpenCoordinator(
        builtin_registry(), cache=DecoderProfileCache(directory / "cache")
    ).Open(LogOpenRequest(log_path=log, decoder_package_path=package))
