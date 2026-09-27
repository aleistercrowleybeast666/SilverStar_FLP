"""Read-only product review of the final frozen C bridge pair."""

import hashlib
import json
from pathlib import Path

import audit_actual_backend_logger as audit
import numpy as np
from run_five_logs import Save

from silverstar_flp.decoder_profiles.discovery import DecoderProfileCache
from silverstar_flp.log_open import LogOpenCoordinator, LogOpenRequest
from silverstar_flp.plugins.api.algorithm import ReplayRequest
from silverstar_flp.plugins.registry import builtin_registry

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
OUTPUT = ROOT / "bridge_final_review"


def Digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


protected = [
    REPO / "src/silverstar_flp" / name
    for name in (
        "plugins/algorithms/kf6/plugin.py",
        "plugins/algorithms/kf6/fixed_lag.py",
        "analysis/navigation_revision3.py",
        "plugins/algorithms/eskf15/plugin.py",
    )
]
protected += [ROOT / "evidence_final/actual_backend_logger.json"]
protected += sorted((ROOT / "actual_backend_logger").rglob("*"))
protected = [path for path in protected if path.is_file()]
before = {str(path.relative_to(REPO)): Digest(path) for path in protected}
OUTPUT.mkdir(exist_ok=False)
(OUTPUT / "evidence_final").mkdir()
Save(OUTPUT / "protected_before.json", before)
source = audit.PROJECT / "build/FCCG/Host/BackendBridge/actual_backend_logger.BIN"
decoder = audit.PROJECT / "ActualBackendLoggerBridgeTest.ssdecoder"
assert Digest(source) == "253dd88e57bb7f672ad2ed174979f19f632cee58e71a36eb6d7452455bc20e07"
assert Digest(decoder) == "2c58fa36a1e40a27801e775b02640f6a460df00d12b58a0640bc3331b4102c46"
audit.ROOT = OUTPUT
audit.Run()
registry = builtin_registry()
dataset = (
    LogOpenCoordinator(registry, cache=DecoderProfileCache(OUTPUT / "health_cache"))
    .Open(LogOpenRequest(log_path=source, decoder_package_path=decoder))
    .dataset
)
result = registry.Algorithm_Get("silverstar.algorithm.estimator.eskf15").run(
    dataset, ReplayRequest()
)
series = result.channels["eskf15.navigation_health"]
rows = []
for record_name in ("ESKF15_STATE", "NAV_QUALITY"):
    records = dataset.Records_Get(record_name)
    for record in records:
        payload = record.payload
        timestamp = int(payload.get("evaluation_us", record.timestamp_us))
        at = int(np.searchsorted(series.timestamp_us, timestamp))
        match = at < series.count and int(series.timestamp_us[at]) == timestamp
        recorded = int(payload["health"])
        replay = int(series.values[at]) if match else None
        rows.append(
            dict(
                record=record_name,
                timestamp_us=timestamp,
                recorded=recorded,
                replay=replay,
                exact_timestamp_match=match,
                equal=match and recorded == replay,
            )
        )
health = dict(
    scope=(
        "Separate health audit; existing recorded_parity covers nominal/P/measurements, not health."
    ),
    consumer_status=(
        "Four pending integration files not modified; "
        "quality variance scale is not yet supplied to supervisor."
    ),
    rows=rows,
    compared=sum(row["exact_timestamp_match"] for row in rows),
    mismatches=[row for row in rows if row["exact_timestamp_match"] and not row["equal"]],
    missing=[row for row in rows if not row["exact_timestamp_match"]],
)
Save(OUTPUT / "health_comparison.json", health)
after = {str(path.relative_to(REPO)): Digest(path) for path in protected}
assert before == after, "Protected old evidence or pending product file changed"
Save(OUTPUT / "protected_after.json", after)
summary = json.loads((OUTPUT / "actual_backend_logger/result.json").read_text(encoding="utf8"))
compact = {
    key: summary[key]
    for key in (
        "hashes_before",
        "source_sizes",
        "record_counts",
        "replay_fidelity",
        "replay_claim",
        "recorded_parity",
        "export_failures",
        "export_skipped",
        "source_and_decoder_unchanged",
    )
}
compact.update(
    export_count=len(summary["export_files"]),
    health=health,
    protected_files_unchanged=True,
    protected_file_count=len(before),
)
Save(OUTPUT / "final_review.json", compact)
print(
    json.dumps(
        {
            "health_compared": health["compared"],
            "health_mismatches": health["mismatches"],
            "health_missing": health["missing"],
            "export_count": compact["export_count"],
            "protected_files": len(before),
        },
        indent=2,
    ),
    flush=True,
)
