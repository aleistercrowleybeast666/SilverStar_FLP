"""Verify later hard-boundary fixes do not alter the completed real-log runs."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from silverstar_flp.decoder_profiles.discovery import DecoderProfileCache
from silverstar_flp.log_open import LogOpenCoordinator, LogOpenRequest
from silverstar_flp.plugins.algorithms.eskf15.plugin import Native_PhysicalMask
from silverstar_flp.plugins.registry import builtin_registry

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "five_logs_contract_final"
INPUT = Path("D:/stm32_project/SS_0_5_TEST_3")


def PreviousMask_Get(p):
    fields = int(p["supported_fields"]) & int(p["valid_fields"])
    if fields & 3 != 3 or not p["online"] or not p["fix_ok"] or p["fix_type"] != 3:
        return 0
    mask = sum(1 << group for group, required in enumerate((40, 80, 640, 768))
               if fields & required == required)
    if p["velocity_valid_mask"] & 3 != 3:
        mask &= ~4
    if not p["velocity_valid_mask"] & 4:
        mask &= ~8
    return mask


if __name__ == "__main__":
    decoder = INPUT / "HARDWARE/SS_0_5_TEST_3.ssdecoder"
    coordinator = LogOpenCoordinator(builtin_registry(), cache=DecoderProfileCache(ROOT / "cache"))
    results = []
    for index in range(5):
        name = f"SS{index:04d}"
        log = INPUT / "LOG" / (name + ".BIN")
        before = hashlib.sha256(log.read_bytes()).hexdigest()
        dataset = coordinator.Open(LogOpenRequest(log_path=log, decoder_package_path=decoder)).dataset
        mask_changes = sum(PreviousMask_Get(r.payload) != Native_PhysicalMask(r.payload)
                           for r in dataset.Records_Get("GNSS_NATIVE"))
        npz_path = OUTPUT / name / "eskf15_what_if_all_channels.npz"
        data = np.load(npz_path)
        mismatch_count = sum(int(np.count_nonzero(data[key] == 5)) for key in data.files
                             if key.startswith("eskf15.update_result.") and key.endswith("__values"))
        baro_age = float(np.max(data["eskf15.receive_age.baro__values"]))
        report = json.loads((OUTPUT / name / "report.json").read_text(encoding="utf8"))
        history = report["runs"]["eskf15_what_if"]["diagnostics"]["maximum_history_steps"]
        item = {"source": name, "source_sha256": before,
                "raw_hash_unchanged": hashlib.sha256(log.read_bytes()).hexdigest() == before,
                "native_physical_mask_changes": mask_changes,
                "model_mismatch_count": mismatch_count, "maximum_baro_receive_age_ms": baro_age,
                "maximum_history_steps": history, "prior_capacity": 144, "final_capacity": 192,
                "numerical_output_sha256": hashlib.sha256(npz_path.read_bytes()).hexdigest()}
        item["equivalent_inputs_and_control_flow"] = (item["raw_hash_unchanged"]
            and mask_changes == 0 and mismatch_count == 0 and baro_age <= 500 and history < 144)
        results.append(item)
        print(name, item["equivalent_inputs_and_control_flow"], flush=True)
    (OUTPUT / "final_policy_equivalence.json").write_text(
        json.dumps(results, indent=2), encoding="utf8")
    assert all(item["equivalent_inputs_and_control_flow"] for item in results)
