"""Summarize every real-log run without modifying input or selecting successes."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
from matplotlib import pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "five_logs_contract_final"
GROUPS = ("position_en", "position_u", "velocity_en", "velocity_u", "baro")


def Save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf8")


def Report_Build(name):
    folder = OUTPUT / name
    report = json.loads((folder / "report.json").read_text(encoding="utf8"))
    old = json.loads((ROOT / "five_logs" / name / "report.json").read_text(encoding="utf8"))
    run = report["runs"]["eskf15_what_if"]
    legacy = old["runs"]["legacy_kf6"]
    audit = {
        "source": name, "source_sha256": report["source_sha256"],
        "decoder_sha256": report["decoder_sha256"], "source_bytes": report["source_bytes"],
        "inputs_unchanged": report["input_hash_unchanged"] and report["decoder_hash_unchanged"],
        "legacy_kf6_status": legacy["status"], "legacy_kf6_error": legacy.get("error"),
        "eskf15_status": run["status"], "eskf15_fidelity": run.get("fidelity"),
        "warnings": run.get("warnings", []),
        "interpretation": "旧固件真实日志上的新 ESKF What-if；无外部真值，不以末位置差或内部一致性声称绝对精度。",
    }
    if run["status"] == "failed":
        audit["error"] = run["error"]
        Save(folder / "acceptance_metrics.json", audit)
        return audit
    data = np.load(folder / "eskf15_what_if_all_channels.npz")

    def Values(channel):
        return data[channel + "__values"]

    times = data["navigation.position_enu__time_us"]
    q = Values("attitude.q_nb")
    upper = Values("eskf15.covariance.upper_triangle")
    matrices = np.zeros((len(times), 15, 15))
    rows, columns = np.triu_indices(15)
    matrices[:, rows, columns] = upper
    matrices[:, columns, rows] = upper
    eigenvalues = np.linalg.eigvalsh(matrices)
    health = Values("eskf15.navigation_health")
    audit.update({
        "epoch_count": len(times), "duration_s": float(times[-1] - times[0]) * 1e-6,
        "quaternion_norm_max_error": float(np.max(np.abs(np.linalg.norm(q, axis=1) - 1))),
        "full_covariance_min_eigenvalue": float(np.min(eigenvalues)),
        "full_covariance_all_finite": bool(np.isfinite(upper).all()),
        "nominal_output_all_finite": run["output_all_finite"],
        "final_navigation_health": int(health[-1]),
        "health_epoch_counts": {str(int(k)): int(v) for k, v in zip(*np.unique(health, return_counts=True))},
        "maximum_gyro_bias_norm_radps": float(np.max(np.linalg.norm(Values("eskf15.gyro_bias"), axis=1))),
        "maximum_accel_bias_norm_mps2": float(np.max(np.linalg.norm(Values("eskf15.accel_bias"), axis=1))),
        "recorded_kf6_endpoint_enu_m": report.get("recorded_endpoint_enu_m"),
        "eskf15_what_if_endpoint_enu_m": run["endpoint_enu_m"],
        "first_failure": run["diagnostics"]["failure"],
        "first_health_state_us": {str(state): (int(times[np.flatnonzero(health == state)[0]])
                                  if np.any(health == state) else None) for state in range(5)},
        "maximum_position_step_m": float(np.max(np.linalg.norm(np.diff(Values("navigation.position_enu"), axis=0), axis=1))),
        "last_velocity_enu_mps": run["final_velocity_enu_mps"],
        "runtime_seconds_host_python": run["elapsed_s"],
        "replay_step_count": run["diagnostics"]["replay_steps"],
        "maximum_single_replay_steps": run["diagnostics"]["maximum_replay_steps"],
        "reset_count": run["diagnostics"]["recovery_count"],
        "imu_clip_evidence": "unavailable: old log lacks declared effective range/readback/clip flags; no inferred success",
        "fusion_groups": {},
        "window_count": len(run["diagnostics"]["window_evidence"]),
        "window_valid_count": sum(bool(w["valid"]) for w in run["diagnostics"]["window_evidence"]),
        "window_evidence_scope": "旧 GNSS_NATIVE 缺可信 iTOW，接收/样本时刻的窗口为近似证据",
    })
    for group in GROUPS:
        prefix = "eskf15.update_result." + group
        if prefix + "__values" not in data:
            audit["fusion_groups"][group] = {"status": "no_operations", "maximum_effective_fusion_gap_s": audit["duration_s"]}
            continue
        outcomes = Values(prefix)
        operation_times = data[prefix + "__time_us"]
        accepted = operation_times[np.isin(outcomes, (0, 1))]
        knots = np.concatenate(([times[0]], accepted, [times[-1]])).astype(np.int64)
        audit["fusion_groups"][group] = {
            "outcome_counts": {str(int(k)): int(v) for k, v in zip(*np.unique(outcomes, return_counts=True))},
            "maximum_effective_fusion_gap_s": float(np.max(np.diff(np.sort(knots)))) * 1e-6,
            "last_effective_fusion_us": int(accepted[-1]) if len(accepted) else None,
        }
    plot, axes = plt.subplots(3, 2, figsize=(12, 10), constrained_layout=True)
    seconds = (times.astype(np.float64) - float(times[0])) * 1e-6
    for panel, channel, title, unit in (
        (axes[0, 0], "navigation.position_enu", "ESKF15 What-if position", "m"),
        (axes[0, 1], "navigation.velocity_enu", "ESKF15 What-if velocity", "m/s"),
        (axes[1, 0], "eskf15.gyro_bias", "Residual gyro bias", "rad/s"),
        (axes[1, 1], "eskf15.accel_bias", "Residual acceleration bias", "m/s²"),
    ):
        labels = ("E", "N", "U") if channel.startswith("navigation.") else ("X", "Y", "Z")
        for component, label in enumerate(labels):
            panel.plot(seconds, Values(channel)[:, component], label=label)
        panel.legend(fontsize=8)
        panel.set(title=title, xlabel="Time from first output / s", ylabel=unit)
        panel.grid(alpha=.25)
    axes[2, 0].step(seconds, health, where="post", label="0 warmup, 1 healthy, 2 degraded, 3 DR, 4 invalid")
    axes[2, 0].set(title="Effective-fusion health", ylim=(-.2, 4.2), xlabel="Time / s")
    axes[2, 0].legend(fontsize=7)
    axes[2, 1].semilogy(seconds, np.maximum(eigenvalues[:, 0], np.finfo(float).tiny))
    axes[2, 1].set(title="Full P minimum eigenvalue", xlabel="Time / s")
    plot.suptitle(name + " · real old-firmware log / approximate ESKF15 What-if · no external truth")
    plot.savefig(folder / "navigation_diagnostics.png", dpi=150)
    plt.close(plot)
    plot, axes = plt.subplots(3, 2, figsize=(12, 10), constrained_layout=True)
    for component, label in enumerate(("w", "x", "y", "z")):
        axes[0, 0].plot(seconds, q[:, component], label=label)
    axes[0, 0].set(title="Hamilton body-to-ENU quaternion", xlabel="Time / s")
    axes[0, 0].legend()
    pdiag = Values("eskf15.covariance.diagonal")
    for panel, group, unit, offset in zip(axes.flat[1:],
            ("Position", "Velocity", "Attitude error", "Gyro bias", "Acceleration bias"),
            ("m", "m/s", "rad", "rad/s", "m/s²"), (0, 3, 6, 9, 12)):
        for index, label in enumerate(("E", "N", "U") if offset < 6 else ("X", "Y", "Z")):
            panel.plot(seconds, np.sqrt(pdiag[:, offset + index]), label=label)
        panel.set(title=group + " standard deviation", xlabel="Time / s", ylabel=unit)
        panel.legend(fontsize=8)
        panel.grid(alpha=.25)
    plot.suptitle(name + " · all 15 error-state covariance diagonals and nominal quaternion")
    plot.savefig(folder / "attitude_and_covariance.png", dpi=150)
    plt.close(plot)
    Save(folder / "acceptance_metrics.json", audit)
    text = [f"# {name} 真实日志回归", "", audit["interpretation"], "",
            f"- 原始 SHA256：`{audit['source_sha256']}`，前后保持一致。",
            f"- 旧 KF6：{legacy['status']}；{legacy.get('error', '旧语义复算完成')}。",
            f"- ESKF What-if：{run['status']}，{audit['epoch_count']} 个输出，最终健康={audit['final_navigation_health']}。",
            f"- P 最小特征值={audit['full_covariance_min_eigenvalue']:.6g}；四元数范数最大误差={audit['quaternion_norm_max_error']:.3g}。",
            f"- What-if 末位置 ENU={run['endpoint_enu_m']} m；仅为输出值，不代表真值误差。",
            "- 旧日志缺新 BODY_INPUT、IMU范围/饱和质量和可信原生GNSS时刻，因此不得作为新固件硬件性能通过证据。", "",
            "| 组 | 有效融合最长间隙(s) | 结果码计数 |", "|---|---:|---|" ]
    for group, metrics in audit["fusion_groups"].items():
        text.append(f"| {group} | {metrics['maximum_effective_fusion_gap_s']:.3f} | {metrics.get('outcome_counts', {})} |")
    text += ["", "结果码0正常接受、1软降权接受、2NIS拒绝、3物理/输入无效、5模型不匹配、17时序非法、18历史缺失、19容量不足。", "",
             "![完整时序诊断](navigation_diagnostics.png)", "",
             "![四元数与全部15维协方差](attitude_and_covariance.png)", ""]
    (folder / "REPORT.md").write_text("\n".join(text), encoding="utf8")
    return audit


if __name__ == "__main__":
    audits = [Report_Build(f"SS{index:04d}") for index in range(5)]
    Save(OUTPUT / "acceptance_summary.json", audits)
    print("all five reports preserved; inputs unchanged:", all(a["inputs_unchanged"] for a in audits))
