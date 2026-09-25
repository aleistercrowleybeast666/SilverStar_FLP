"""Read-only field comparison for recorded, faithful, and assisted KF6.

Run from the FLP repository. Outputs must be placed below this repository during
internal acceptance; the log and decoder paths are only read.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, replace
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from silverstar_flp.analysis.gnss_integrity import GnssIntegrity_Build
from silverstar_flp.analysis.integrity_assistance import (
    IntegrityConfig,
    IntegrityDecisions_Build,
)
from silverstar_flp.decoder_profiles.discovery import DecoderProfileCache
from silverstar_flp.log_open import LogOpenCoordinator, LogOpenRequest
from silverstar_flp.plugins.algorithms.kf6.plugin import Kf6AlgorithmPlugin
from silverstar_flp.plugins.api.algorithm import ReplayMode, ReplayRequest
from silverstar_flp.plugins.registry import builtin_registry


def _ValidValues(series):
    values = np.asarray(series.values, dtype=np.float64)
    valid = np.asarray(series.valid, dtype=np.bool_).copy()
    if values.ndim == 2:
        valid &= np.all(np.isfinite(values), axis=1)
    else:
        valid &= np.isfinite(values)
    return values[valid]


def _PathMetrics(position, velocity):
    path = _ValidValues(position)
    speed = _ValidValues(velocity)
    if len(path) == 0 or len(speed) == 0:
        raise ValueError("navigation_series_empty")
    jumps = np.linalg.norm(np.diff(path, axis=0), axis=1)
    return {
        "final_position_enu_m": path[-1].tolist(),
        "final_horizontal_error_m": float(np.linalg.norm(path[-1, :2])),
        "max_trajectory_step_m": float(jumps.max()) if len(jumps) else 0.0,
        "velocity_rms_mps": float(np.sqrt(np.mean(np.sum(speed**2, axis=1)))),
        "final_velocity_enu_mps": speed[-1].tolist(),
    }


def _ReplayMetrics(result):
    metrics = _PathMetrics(result.channels["navigation.position_enu"],
                           result.channels["navigation.velocity_enu"])
    rows = [row for row in result.diagnostics.get("gnss_group_updates", ())
            if row["group"] == "Pos EN"]
    attempted = [row for row in rows if row["valid"]]
    rejected = [row for row in attempted if row["result"] in (2, 3, 4)]
    metrics["position_en_reject_ratio"] = (
        len(rejected) / len(attempted) if attempted else None
    )
    metrics["position_en_update_count"] = len(attempted)
    metrics["position_en_numeric_errors"] = sum(row["result"] == 4 for row in rows)
    metrics["health_flags"] = int(result.diagnostics.get("health_flags", 0))
    nis = result.channels.get("kf6.nis.position_en")
    if nis is not None:
        values = _ValidValues(nis)
        metrics["position_en_nis_p95"] = (
            float(np.percentile(values, 95)) if len(values) else None
        )
    covariance = result.channels.get("kf6.covariance.upper_triangle")
    if covariance is not None:
        values = _ValidValues(covariance)
        matrix = np.zeros((len(values), 6, 6), dtype=np.float64)
        upper = np.triu_indices(6)
        matrix[:, upper[0], upper[1]] = values
        matrix[:, upper[1], upper[0]] = values
        eigen = np.linalg.eigvalsh(matrix)
        metrics["covariance_finite"] = bool(np.isfinite(matrix).all())
        metrics["covariance_min_eigenvalue"] = float(eigen.min())
        metrics["covariance_psd"] = bool(eigen.min() >= -1.0e-6)
    if "integrity_assistance" in result.diagnostics:
        metrics["integrity"] = result.diagnostics["integrity_assistance"]
        metrics["analysis_events"] = result.diagnostics.get("integrity_analysis_events", ())
    return metrics


def _DrawSeries(ax, series, origin, label, axes, color, style):
    if series is None:
        return
    stride = max(1, series.count // 5000)
    time = (series.timestamp_us[::stride].astype(np.float64) - origin) * 1e-6
    values = np.asarray(series.values, dtype=np.float64)[::stride]
    valid = series.valid[::stride]
    for axis in axes:
        component = values[:, axis].copy()
        component[~valid] = np.nan
        ax.plot(time, component, style, linewidth=1.0, color=color[axis],
                alpha=.8, label=f"{label} {('E', 'N', 'U')[axis]}")


def _Plot_Write(dataset, faithful, assisted, closure, path):
    origin = int(dataset.start_timestamp_us or 0)
    recorded_position = dataset.Series_Get("kf6.recorded.navigation.position_enu")
    recorded_velocity = dataset.Series_Get("kf6.recorded.navigation.velocity_enu")
    fig, axes = plt.subplots(4, 2, figsize=(17, 17), constrained_layout=True)
    sources = (
        ("Recorded KF6", recorded_position, recorded_velocity, ("#9b9b9b", "#bbbbbb"), "--"),
        ("Faithful KF6", faithful.channels["navigation.position_enu"],
         faithful.channels["navigation.velocity_enu"], ("#2878b5", "#42a4df"), "-"),
        ("Integrity-assisted", assisted.channels["navigation.position_enu"],
         assisted.channels["navigation.velocity_enu"], ("#c85b20", "#e8994a"), "-"),
    )
    for label, position, velocity, color, style in sources:
        _DrawSeries(axes[0, 0], position, origin, label, (0, 1), color, style)
        _DrawSeries(axes[0, 1], velocity, origin, label, (0, 1), color, style)
        points = _ValidValues(position)
        stride = max(1, len(points) // 5000)
        axes[1, 0].plot(points[::stride, 0], points[::stride, 1], style,
                        color=color[0], label=label)
    axes[0, 0].set_title("Position EN / m")
    axes[0, 1].set_title("Velocity EN / m/s")
    axes[1, 0].set_title("2D trajectory / m")
    axes[1, 0].set_xlabel("East / m")
    axes[1, 0].set_ylabel("North / m")
    native_time = (closure.timestamp_us.astype(np.float64) - origin) * 1e-6
    anchored = np.linalg.norm(closure.anchored_residual_m[:, :2], axis=1)
    anchored[~closure.anchored_valid_en] = np.nan
    rolling = np.linalg.norm(closure.residual_m[:, :2], axis=1)
    rolling[~closure.valid_en] = np.nan
    axes[1, 1].plot(native_time, anchored, label="Anchored |EN|")
    axes[1, 1].plot(native_time, rolling, label="Rolling |EN|", alpha=.6)
    axes[1, 1].set_title("Receiver position/velocity closure / m")
    state = assisted.channels["kf6.integrity.state"]
    state_time = (state.timestamp_us.astype(np.float64) - origin) * 1e-6
    axes[2, 0].step(state_time, state.values, where="post")
    axes[2, 0].set_yticks((0, 1, 2, 3),
                         ("TRUSTED", "SUSPECT", "UNTRUSTED", "RECOVERING"))
    axes[2, 0].set_title("Integrity state")
    scale = assisted.channels["kf6.integrity.position_r_scale"]
    axes[2, 1].plot(state_time, scale.values, label="Pos EN R scale")
    axes[2, 1].set_title("Pos EN R scale")
    update = [row for row in assisted.diagnostics.get("gnss_group_updates", ())
              if row["group"] == "Pos EN"]
    if update:
        x = [(row["timestamp_us"] - origin) * 1e-6 for row in update]
        y = [-1 if not row["valid"] else row["result"] for row in update]
        axes[3, 0].scatter(x, y, s=2)
    axes[3, 0].set_yticks((-1, 0, 1, 2, 3, 4),
                         ("disabled", "accepted", "soft", "NIS reject", "invalid", "numeric"))
    axes[3, 0].set_title("Pos EN update allowed/rejected")
    for label, result, color, style in (
        ("Recorded", None, "#999999", "--"),
        ("Faithful", faithful, "#2878b5", "-"),
        ("Assisted", assisted, "#c85b20", "-"),
    ):
        nis = (dataset.Series_Get("kf6.recorded.nis.position_en") if result is None
               else result.channels.get("kf6.nis.position_en"))
        if nis is None:
            continue
        stride = max(1, nis.count // 5000)
        x = (nis.timestamp_us[::stride].astype(np.float64) - origin) * 1e-6
        y = np.asarray(nis.values[::stride], dtype=float).copy()
        y[~nis.valid[::stride]] = np.nan
        axes[3, 1].plot(x, y, style, color=color, linewidth=1, label=label)
    axes[3, 1].set_title("Pos EN NIS")
    for ax in axes.flat:
        if ax is not axes[1, 0]:
            ax.set_xlabel("Mission time / s")
        ax.grid(alpha=.2)
        if ax.lines and ax is not axes[2, 0]:
            ax.legend(fontsize=7)
    fig.savefig(path, dpi=130)
    plt.close(fig)


def _PlanScan(dataset, config):
    records = dataset.Records_Get("GNSS_NATIVE")
    sequences = np.asarray([int(row.payload.get("sequence", row.record_sequence))
                            for row in records], dtype=np.int64)
    coarse = []
    for window in (2, 5, 10):
        closure = GnssIntegrity_Build(dataset, window)
        for threshold in (12.0, 15.0, 20.0):
            for duration in (1.5, 2.0, 3.0):
                candidate = replace(config, window_s=window,
                                    anchored_threshold_m=threshold,
                                    suspect_duration_s=duration)
                plan = IntegrityDecisions_Build(closure, sequences, candidate)
                coarse.append({
                    "window_s": window,
                    "anchored_threshold_m": threshold,
                    "suspect_duration_s": duration,
                    "transition_count": len(plan.transitions),
                    "first_untrusted_us": next((time for time, state in plan.transitions
                                                if state.value == "UNTRUSTED"), None),
                })
    return coarse


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--scan", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    decoder = args.root / "HARDWARE/SS_0_5_TEST_2.ssdecoder"
    coordinator = LogOpenCoordinator(
        builtin_registry(), cache=DecoderProfileCache(args.output / "cache")
    )
    plugin = Kf6AlgorithmPlugin()
    summary = {}
    config = IntegrityConfig()
    for name in ("SS0000", "SS0001"):
        dataset = coordinator.Open(LogOpenRequest(
            log_path=args.root / "LOG" / f"{name}.BIN",
            decoder_package_path=decoder,
        )).dataset
        closure = GnssIntegrity_Build(dataset, config.window_s)
        faithful = plugin.run(dataset, ReplayRequest())
        assisted = plugin.run(dataset, ReplayRequest(
            mode=ReplayMode.INTEGRITY_ASSISTED,
            integrity_parameters=asdict(config),
        ))
        recorded = _PathMetrics(
            dataset.Series_Get("kf6.recorded.navigation.position_enu"),
            dataset.Series_Get("kf6.recorded.navigation.velocity_enu"),
        )
        deploy = next((row.timestamp_us for row in dataset.Records_Get("EVENT")
                       if int(row.payload.get("event_id", -1)) == 0x29), None)
        anchored = np.linalg.norm(closure.anchored_residual_m[:, :2], axis=1)
        anchored[~closure.anchored_valid_en] = np.nan
        crossed = np.flatnonzero(anchored > config.anchored_threshold_m)
        result = {
            "recorded": recorded,
            "faithful": _ReplayMetrics(faithful),
            "assisted": _ReplayMetrics(assisted),
            "rolling_closure": closure.summary["horizontal"],
            "anchored_closure": closure.summary["anchored_horizontal"],
            "bias_threshold_cross_us": (int(closure.timestamp_us[crossed[0]])
                                        if len(crossed) else None),
            "deploy_timestamp_us": deploy,
            "mission_start_timestamp_us": dataset.start_timestamp_us,
        }
        if args.scan:
            result["coarse_scan"] = _PlanScan(dataset, config)
            if name == "SS0001":
                result["scale_scan"] = {}
                for scale in (2.0, 4.0, 8.0, 16.0):
                    variant = (assisted if scale == config.integrity_scale else plugin.run(
                        dataset, ReplayRequest(
                            mode=ReplayMode.INTEGRITY_ASSISTED,
                            integrity_parameters={**asdict(config), "integrity_scale": scale},
                        )
                    ))
                    result["scale_scan"][str(scale)] = _ReplayMetrics(variant)
        summary[name] = result
        _Plot_Write(dataset, faithful, assisted, closure, args.output / f"{name}_comparison.png")
        (args.output / f"{name}.json").write_text(
            json.dumps(result, indent=2, allow_nan=False, default=float), encoding="utf-8"
        )
        print(name, "recorded", recorded["final_horizontal_error_m"],
              "faithful", result["faithful"]["final_horizontal_error_m"],
              "assisted", result["assisted"]["final_horizontal_error_m"], flush=True)
    (args.output / "summary.json").write_text(
        json.dumps(summary, indent=2, allow_nan=False, default=float), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
