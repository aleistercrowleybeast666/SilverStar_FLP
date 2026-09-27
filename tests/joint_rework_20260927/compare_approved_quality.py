"""Compare preserved old outputs with fresh quality-fix regressions."""

import hashlib
import json
from pathlib import Path

import numpy as np
from run_five_logs import Save

ROOT = Path(__file__).resolve().parent
rows = []
for name in [f"SS{i:04d}" for i in range(5)]:
    for old_folder, new_folder, key, health_key in (
        (
            "five_logs_kf6_rev3",
            "five_logs_quality_fix_kf6",
            "kf6_revision3_what_if",
            "kf6.navigation_health",
        ),
        (
            "five_logs_contract_final",
            "five_logs_quality_fix_eskf",
            "eskf15_what_if",
            "eskf15.navigation_health",
        ),
    ):
        old_path, new_path = ROOT / old_folder / name, ROOT / new_folder / name
        old_report = json.loads((old_path / "report.json").read_text(encoding="utf8"))
        new_report = json.loads((new_path / "report.json").read_text(encoding="utf8"))
        old_run, new_run = old_report["runs"][key], new_report["runs"][key]
        row = dict(
            log=name,
            algorithm=key,
            old_status=old_run["status"],
            new_status=new_run["status"],
            raw_sha256=new_report["source_sha256"],
            decoder_sha256=new_report["decoder_sha256"],
        )
        assert old_report["source_sha256"] == new_report["source_sha256"]
        assert old_report["decoder_sha256"] == new_report["decoder_sha256"]
        assert new_report["input_hash_unchanged"] and new_report["decoder_hash_unchanged"]
        if new_run["status"] == "failed":
            row.update(old_error=old_run.get("error"), new_error=new_run.get("error"))
            assert old_run["status"] == "failed" and row["old_error"] == row["new_error"]
            rows.append(row)
            continue
        old_data = np.load(old_path / (key + "_all_channels.npz"))
        new_data = np.load(new_path / (key + "_all_channels.npz"))
        common = sorted(set(old_data.files) & set(new_data.files))
        differences = []
        for channel in common:
            if "navigation_health" in channel:
                continue
            left, right = old_data[channel], new_data[channel]
            if not np.array_equal(left, right, equal_nan=True):
                delta = (
                    np.abs(left.astype(float) - right.astype(float))
                    if left.shape == right.shape
                    else None
                )
                differences.append(
                    dict(
                        channel=channel,
                        old_shape=left.shape,
                        new_shape=right.shape,
                        max_abs=float(np.nanmax(delta)) if delta is not None else None,
                    )
                )
        new_health = new_data[health_key + "__values"]
        new_times = new_data[health_key + "__time_us"]
        if key == "kf6_revision3_what_if":
            saved = np.load(ROOT / "four_way_comparison" / name / "kf6_revision3_health.npz")
            old_health, old_times = saved["health"], saved["timestamp_us"]
        else:
            old_health, old_times = (
                old_data[health_key + "__values"],
                old_data[health_key + "__time_us"],
            )
        assert np.array_equal(old_times, new_times)

        def Counts(values):
            k, v = np.unique(values, return_counts=True)
            return {str(int(a)): int(b) for a, b in zip(k, v, strict=True)}

        old_groups = old_run["diagnostics"].get("fusion_groups")
        if old_groups is None:
            old_comparison = json.loads(
                (ROOT / "four_way_comparison" / name / "comparison.json").read_text(encoding="utf8")
            )
            old_groups = old_comparison["C_revision3_kf6"]["acceptance"]["fusion_groups"]
        new_groups = new_run["diagnostics"]["fusion_groups"]
        old_longest = [g["longest_no_fusion_us"] for g in old_groups]
        new_longest = [g["longest_no_fusion_us"] for g in new_groups]
        old_first = {
            str(i): int(old_times[np.flatnonzero(old_health == i)[0]])
            if np.any(old_health == i)
            else None
            for i in range(5)
        }
        new_first = {
            str(i): int(new_times[np.flatnonzero(new_health == i)[0]])
            if np.any(new_health == i)
            else None
            for i in range(5)
        }
        changes = np.flatnonzero(old_health != new_health)
        row.update(
            common_nonnavigationhealth_arrays=sum("navigation_health" not in k for k in common),
            differing_numeric_arrays=differences,
            additional_keys=sorted(set(new_data.files) - set(old_data.files)),
            old_first_health_us=old_first,
            new_first_health_us=new_first,
            old_longest_no_fusion_us=old_longest,
            new_longest_no_fusion_us=new_longest,
            longest_no_fusion_unchanged=old_longest == new_longest,
            old_final_health=int(old_health[-1]),
            new_final_health=int(new_health[-1]),
            old_health_counts=Counts(old_health),
            new_health_counts=Counts(new_health),
            health_changed_epochs=len(changes),
            first_health_change_us=int(new_times[changes[0]]) if len(changes) else None,
            endpoint_enu_m=new_run["endpoint_enu_m"],
            final_velocity_enu_mps=new_run["final_velocity_enu_mps"],
            output_all_finite=new_run["output_all_finite"],
            invalid_or_failure_retained=new_run["diagnostics"].get("failure"),
            interpretation=(
                "Internal health is not external accuracy truth; old logs use approximate What-if."
            ),
        )
        assert not differences, differences
        rows.append(row)
        Save(ROOT / "approved_quality_comparison.json", {"runs": rows, "complete": False})
for row in json.loads((ROOT / "approved_quality_baseline_hashes.json").read_text(encoding="utf8")):
    path = ROOT.parents[1] / row["path"]
    assert path.stat().st_size == row["bytes"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == row["sha256"]
Save(
    ROOT / "approved_quality_comparison.json",
    dict(
        runs=rows,
        complete=True,
        old_evidence_unchanged=True,
        source_logs_and_decoder_unchanged=True,
        numerical_common_arrays_identical=True,
        scope="Revision-3 What-if health fix; no hardware or flight accuracy claim.",
    ),
)
for row in rows:
    print(
        row["log"],
        row["algorithm"],
        row["new_status"],
        row.get("old_final_health"),
        row.get("new_final_health"),
        "changed_epochs",
        row.get("health_changed_epochs"),
        flush=True,
    )
