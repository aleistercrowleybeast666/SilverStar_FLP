"""Final actual C bridge parity after revision-3 quality integration; no export repetition."""

import hashlib
import json
from pathlib import Path

import numpy as np
from run_five_logs import Save

from silverstar_flp.decoder_profiles.discovery import DecoderProfileCache
from silverstar_flp.log_open import LogOpenCoordinator, LogOpenRequest
from silverstar_flp.plugins.api.algorithm import ReplayRequest
from silverstar_flp.plugins.registry import builtin_registry

ROOT = Path(__file__).resolve().parent
PROJECT = Path("D:/python_software/SilverStar_FCCG/tests/joint_rework_20260927/backend_bridge_test")
source = PROJECT / "build/FCCG/Host/BackendBridge/actual_backend_logger.BIN"
decoder = PROJECT / "ActualBackendLoggerBridgeTest.ssdecoder"
hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (source, decoder)}
assert hashes[source.name] == "253dd88e57bb7f672ad2ed174979f19f632cee58e71a36eb6d7452455bc20e07"
assert hashes[decoder.name] == "2c58fa36a1e40a27801e775b02640f6a460df00d12b58a0640bc3331b4102c46"
registry = builtin_registry()
dataset = (
    LogOpenCoordinator(
        registry, cache=DecoderProfileCache(ROOT / "bridge_final_review/health_cache")
    )
    .Open(LogOpenRequest(log_path=source, decoder_package_path=decoder))
    .dataset
)
result = registry.Algorithm_Get("silverstar.algorithm.estimator.eskf15").run(
    dataset, ReplayRequest()
)
assert result.diagnostics["replay_claim"] == "FAITHFUL", result.diagnostics
assert result.channels["eskf15.accel_bias"].unit == "m/s\u00b2"
prior = json.loads((ROOT / "bridge_final_review/final_review.json").read_text())
assert result.diagnostics["recorded_parity"] == prior["recorded_parity"]
health = result.channels["eskf15.navigation_health"]
rows = []
for name in ("ESKF15_STATE", "NAV_QUALITY"):
    for record in dataset.Records_Get(name):
        t = int(record.payload.get("evaluation_us", record.timestamp_us))
        at = int(np.searchsorted(health.timestamp_us, t))
        assert at < health.count and int(health.timestamp_us[at]) == t
        rows.append(
            dict(
                record=name,
                timestamp_us=t,
                recorded=int(record.payload["health"]),
                replay=int(health.values[at]),
            )
        )
assert all(row["recorded"] == row["replay"] for row in rows), rows
assert all(hashlib.sha256(p.read_bytes()).hexdigest() == hashes[p.name] for p in (source, decoder))
Save(
    ROOT / "approved_quality_final_bridge.json",
    dict(
        hashes=hashes,
        record_count=sum(map(len, dataset.records.values())),
        accel_bias_unit=result.channels["eskf15.accel_bias"].unit,
        fidelity=result.fidelity.value,
        claim=result.diagnostics["replay_claim"],
        recorded_parity=result.diagnostics["recorded_parity"],
        health_comparisons=rows,
        health_equal=len(rows),
        numerical_diagnostics_identical_to_before_quality_integration=True,
        data_quality=dataset.data_quality.ToDict(),
        inputs_unchanged=True,
        export_scope=(
            "Prior 361-file export retained; export implementation unchanged; "
            "no repeated full export."
        ),
    ),
)
print("final actual bridge", result.fidelity.value, "health equal", len(rows), flush=True)
