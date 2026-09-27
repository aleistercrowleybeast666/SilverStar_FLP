"""Read-only five-log regression; every failure retained, no endpoint tuning."""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

import numpy as np

from silverstar_flp.decoder_profiles.discovery import DecoderProfileCache
from silverstar_flp.log_open import LogOpenCoordinator, LogOpenRequest
from silverstar_flp.plugins.api.algorithm import ReplayMode, ReplayRequest
from silverstar_flp.plugins.registry import builtin_registry

ROOT = Path(__file__).resolve().parent
INPUT = Path("D:/stm32_project/SS_0_5_TEST_3")
EXPECTED = (
    "f774a990536b3b39c38f09639a7f1d9a5100ea15f3d219ee1667d351d3fac381",
    "65e19a1aeec9d24836a9831549156fbf9579a49b6cd822d1de06ca8f61b71e95",
    "b9e8e6a56a18497acb5e6405881fe5128464e478edb1a793822951a55b6989cc",
    "1cc5c363610245b1eefcab0f2beab6a5cf128ee4049fa6dc9e2deb1a703a588a",
    "f19bc4350816b2b3fabd298a788f78e7abf30556a563800ef6da178772b1938c",
)


def Json_Compatible(value):
    if isinstance(value, dict):
        return {str(k): Json_Compatible(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [Json_Compatible(v) for v in value]
    if isinstance(value, np.ndarray):
        return Json_Compatible(value.tolist())
    if isinstance(value, (np.integer, np.floating)):
        return Json_Compatible(value.item())
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def Save(path, data):
    path.write_text(
        json.dumps(
            Json_Compatible(data), ensure_ascii=False, indent=2, default=str, allow_nan=False
        ),
        encoding="utf8",
    )


def Run():
    registry = builtin_registry()
    decoder = INPUT / "HARDWARE/SS_0_5_TEST_3.ssdecoder"
    decoder_hash = hashlib.sha256(decoder.read_bytes()).hexdigest()
    coordinator = LogOpenCoordinator(registry, cache=DecoderProfileCache(ROOT / "cache"))
    summary = []
    for index, expected in enumerate(EXPECTED):
        name = f"SS{index:04d}"
        log = INPUT / "LOG" / (name + ".BIN")
        before = hashlib.sha256(log.read_bytes()).hexdigest()
        assert before == expected
        print(name, "exact import", flush=True)
        output_folder = os.environ.get("SILVERSTAR_LOG_RUN", "five_logs")
        output = ROOT / output_folder / name
        output.mkdir(parents=True, exist_ok=True)
        began = time.perf_counter()
        dataset = coordinator.Open(
            LogOpenRequest(log_path=log, decoder_package_path=decoder)
        ).dataset
        report = {
            "source_sha256": before,
            "decoder_sha256": decoder_hash,
            "source_bytes": log.stat().st_size,
            "match": "exact_generation_profile",
            "data_quality": dataset.data_quality.ToDict(),
            "initial_state": dict(dataset.initial_state.payload),
            "record_counts": {k: len(v) for k, v in dataset.records.items()},
            "runs": {},
        }
        recorded = dataset.Series_Get("kf6.recorded.navigation.position_enu")
        if recorded is not None:
            report["recorded_endpoint_enu_m"] = recorded.values[-1].tolist()
        for key, algorithm_id, mode in (
            ("legacy_kf6", "silverstar.algorithm.kf6", ReplayMode.RECORDED_CONFIGURATION),
            ("eskf15_what_if", "silverstar.algorithm.estimator.eskf15", ReplayMode.WHAT_IF),
            ("kf6_revision3_what_if", "silverstar.algorithm.kf6", ReplayMode.WHAT_IF),
        ):
            if key == "kf6_revision3_what_if" and not os.environ.get("SILVERSTAR_KF_REV3_ONLY"):
                continue
            if key != "kf6_revision3_what_if" and os.environ.get("SILVERSTAR_KF_REV3_ONLY"):
                continue
            if key == "legacy_kf6" and os.environ.get("SILVERSTAR_ESKF_ONLY"):
                continue
            started = time.perf_counter()
            try:
                print(name, key, "begin", flush=True)
                result = registry.Algorithm_Get(algorithm_id).run(dataset, ReplayRequest(
                    mode=mode, quality_policy_revision=3 if key == "kf6_revision3_what_if" else None))
                channels = result.channels
                arrays = {}
                for channel, series in channels.items():
                    arrays[channel + "__time_us"] = series.timestamp_us
                    arrays[channel + "__values"] = series.values
                    arrays[channel + "__valid"] = series.valid
                np.savez_compressed(output / (key + "_all_channels.npz"), **arrays)
                report["runs"][key] = {
                    "status": "partial" if result.missing_inputs else "completed",
                    "missing_inputs": result.missing_inputs,
                    "fidelity": result.fidelity.value,
                    "warnings": result.warnings,
                    "parameters": dict(result.parameters),
                    "diagnostics": dict(result.diagnostics),
                    "elapsed_s": time.perf_counter() - started,
                    "output_count": channels["navigation.position_enu"].count,
                    "endpoint_enu_m": channels["navigation.position_enu"].values[-1].tolist(),
                    "final_velocity_enu_mps": channels["navigation.velocity_enu"]
                    .values[-1]
                    .tolist(),
                    "output_all_finite": all(
                        np.isfinite(channels[c].values).all()
                        for c in (
                            "navigation.position_enu",
                            "navigation.velocity_enu",
                            "attitude.q_nb",
                        )
                    ),
                }
                print(name, key, "finished", report["runs"][key]["elapsed_s"], flush=True)
            except Exception as exc:
                report["runs"][key] = {
                    "status": "failed",
                    "error": type(exc).__name__ + ":" + str(exc),
                    "elapsed_s": time.perf_counter() - started,
                }
                print(name, key, "FAILED", repr(exc), flush=True)
            Save(output / "report.json", report)
        report["input_hash_unchanged"] = hashlib.sha256(log.read_bytes()).hexdigest() == before
        report["decoder_hash_unchanged"] = (
            hashlib.sha256(decoder.read_bytes()).hexdigest() == decoder_hash
        )
        report["elapsed_s"] = time.perf_counter() - began
        assert report["input_hash_unchanged"] and report["decoder_hash_unchanged"]
        Save(output / "report.json", report)
        summary.append(report)
        Save(ROOT / output_folder / "summary.json", summary)


if __name__ == "__main__":
    Run()
