from __future__ import annotations

import csv
import io
import json
import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass, is_dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

import numpy as np

from silverstar_flp.analysis.overview import FlightSummary_Build
from silverstar_flp.core.context import TaskContext
from silverstar_flp.core.dataset import FlightDataset, TimeSeries
from silverstar_flp.core.math import Quaternion_RotateVector
from silverstar_flp.plugins.api.algorithm import AlgorithmResult


class ExportLanguage(StrEnum):
    ZH = "zh_CN"
    EN = "en_US"


class ExportTheme(StrEnum):
    LIGHT = "light"
    DARK = "dark"


@dataclass(frozen=True, slots=True)
class ExportOptions:
    language: ExportLanguage = ExportLanguage.ZH
    theme: ExportTheme = ExportTheme.LIGHT
    include_overview: bool = True
    include_diagnostics: bool = True
    include_events: bool = True
    include_csv: bool = True
    include_plots: bool = True
    include_trajectory_3d: bool = True
    include_attitude_gif: bool = True
    selected_channels: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ExportManifest:
    output_directory: Path
    files: tuple[Path, ...]
    language: ExportLanguage
    theme: ExportTheme


_LABELS = {
    ExportLanguage.ZH: {
        "time": "时间",
        "value": "数值",
        "valid": "有效",
        "trajectory": "三维轨迹（ENU）",
        "attitude": "软件姿态（WXYZ / Body→ENU）",
        "recorded": "飞控记录",
        "recomputed": "离线复算",
        "synthetic": "合成数据",
    },
    ExportLanguage.EN: {
        "time": "Time",
        "value": "Value",
        "valid": "Valid",
        "trajectory": "3D trajectory (ENU)",
        "attitude": "Software attitude (WXYZ / Body to ENU)",
        "recorded": "Recorded",
        "recomputed": "Recomputed",
        "synthetic": "Synthetic data",
    },
}


def _Filename_Sanitize(value: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_.")
    return sanitized[:120] or "channel"


def _Json_Default(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if hasattr(value, "value"):
        return value.value
    raise TypeError(type(value).__name__)


class FlightExporter:
    def export(
        self,
        dataset: FlightDataset,
        output_directory: Path,
        *,
        options: ExportOptions | None = None,
        algorithm_results: Mapping[str, AlgorithmResult] | None = None,
        context: TaskContext | None = None,
    ) -> ExportManifest:
        export_options = options or ExportOptions()
        task_context = context or TaskContext()
        output = Path(output_directory)
        output.mkdir(parents=True, exist_ok=True)
        suffix = "_ZH" if export_options.language == ExportLanguage.ZH else "_EN"
        files: list[Path] = []
        channels = self._Channels_Collect(dataset, algorithm_results or {})
        if export_options.selected_channels:
            selected = set(export_options.selected_channels)
            channels = {name: series for name, series in channels.items() if name in selected}
        item_count = max(len(channels), 1)

        if export_options.include_overview:
            task_context.Progress_Report(0.02, "export.overview")
            summary_path = output / f"Flight_Overview{suffix}.json"
            summary = FlightSummary_Build(dataset)
            summary_path.write_text(
                json.dumps(summary, default=_Json_Default, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            files.append(summary_path)
        if export_options.include_diagnostics:
            diagnostics_path = output / f"Parser_Diagnostics{suffix}.json"
            diagnostics_path.write_text(
                json.dumps(dataset.diagnostics.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            files.append(diagnostics_path)
        if export_options.include_events:
            events_path = output / f"Events{suffix}.csv"
            self._Events_Write(dataset, events_path)
            files.append(events_path)

        if export_options.include_csv:
            csv_directory = output / f"CSV{suffix}"
            csv_directory.mkdir(exist_ok=True)
            for index, (channel_id, series) in enumerate(channels.items()):
                task_context.Cancel_RaiseIfRequested()
                csv_path = csv_directory / f"{_Filename_Sanitize(channel_id)}{suffix}.csv"
                self._SeriesCsv_Write(dataset, channel_id, series, csv_path)
                files.append(csv_path)
                task_context.Progress_Report(0.05 + 0.36 * (index + 1) / item_count, "export.csv")

        if export_options.include_plots:
            plot_directory = output / f"Plots{suffix}"
            plot_directory.mkdir(exist_ok=True)
            for index, (channel_id, series) in enumerate(channels.items()):
                task_context.Cancel_RaiseIfRequested()
                if series.count == 0 or np.asarray(series.values).ndim > 2:
                    continue
                image_path = plot_directory / f"{_Filename_Sanitize(channel_id)}{suffix}.png"
                self._SeriesPlot_Write(
                    dataset,
                    channel_id,
                    series,
                    image_path,
                    export_options.language,
                    export_options.theme,
                )
                files.append(image_path)
                task_context.Progress_Report(0.43 + 0.35 * (index + 1) / item_count, "export.plots")

        if export_options.include_trajectory_3d:
            position = self._Position_Select(channels)
            if position is not None:
                trajectory_path = output / f"Trajectory_3D{suffix}.png"
                self._Trajectory_Write(
                    dataset,
                    position,
                    trajectory_path,
                    export_options.language,
                    export_options.theme,
                )
                files.append(trajectory_path)
        if export_options.include_attitude_gif:
            attitude = self._Attitude_Select(channels)
            if attitude is not None and attitude.count >= 2:
                task_context.Progress_Report(0.82, "export.gif")
                gif_path = output / f"Attitude_3D{suffix}.gif"
                self._AttitudeGif_Write(
                    dataset,
                    attitude,
                    gif_path,
                    export_options.language,
                    export_options.theme,
                    task_context,
                )
                files.append(gif_path)
        task_context.Progress_Report(1.0, "export.complete")
        return ExportManifest(output, tuple(files), export_options.language, export_options.theme)

    @staticmethod
    def _Channels_Collect(
        dataset: FlightDataset, algorithm_results: Mapping[str, AlgorithmResult]
    ) -> dict[str, TimeSeries]:
        channels = dict(dataset.series)
        for result_name, result in algorithm_results.items():
            for channel_id, series in result.channels.items():
                channels[f"{result_name}.{channel_id}"] = series
        return dict(sorted(channels.items()))

    @staticmethod
    def _SeriesCsv_Write(
        dataset: FlightDataset,
        channel_id: str,
        series: TimeSeries,
        path: Path,
    ) -> None:
        values = np.asarray(series.values)
        columns = series.columns or (
            tuple(f"value_{index}" for index in range(values.shape[1]))
            if values.ndim == 2
            else ("value",)
        )
        start = dataset.start_timestamp_us or (int(series.timestamp_us[0]) if series.count else 0)
        with path.open("w", encoding="utf-8-sig", newline="") as target:
            writer = csv.writer(target)
            writer.writerow(
                [
                    f"# channel={channel_id}",
                    f"unit={series.unit}",
                    f"quantity={series.quantity}",
                    f"source={series.source}",
                    f"synthetic={bool(dataset.metadata.get('synthetic', False))}",
                ]
            )
            writer.writerow(["timestamp_us", "time_from_start_s", *columns, "valid"])
            for index, timestamp in enumerate(series.timestamp_us):
                sample = values[index]
                sample_values = sample.tolist() if values.ndim == 2 else [sample.item()]
                writer.writerow(
                    [
                        int(timestamp),
                        f"{(int(timestamp) - start) * 1.0e-6:.9f}",
                        *sample_values,
                        int(series.valid[index]),
                    ]
                )

    @staticmethod
    def _Events_Write(dataset: FlightDataset, path: Path) -> None:
        with path.open("w", encoding="utf-8-sig", newline="") as target:
            writer = csv.writer(target)
            writer.writerow(
                ["timestamp_us", "record_sequence", "event_id", "event_name", "arg0", "arg1"]
            )
            for record in dataset.Records_Get("EVENT"):
                writer.writerow(
                    [
                        record.timestamp_us,
                        record.record_sequence,
                        int(record.payload["event_id"]),
                        record.payload["event_name"],
                        int(record.payload["arg0"]),
                        int(record.payload["arg1"]),
                    ]
                )

    @staticmethod
    def _Plot_Configure(theme: ExportTheme) -> tuple[str, str, str]:
        if theme == ExportTheme.DARK:
            return "#111827", "#E5E7EB", "#60A5FA"
        return "#FFFFFF", "#111827", "#2563EB"

    def _SeriesPlot_Write(
        self,
        dataset: FlightDataset,
        channel_id: str,
        series: TimeSeries,
        path: Path,
        language: ExportLanguage,
        theme: ExportTheme,
    ) -> None:
        import matplotlib

        matplotlib.use("Agg")
        from matplotlib import pyplot as plt

        background, foreground, accent = self._Plot_Configure(theme)
        figure, axis = plt.subplots(figsize=(10, 5), dpi=140)
        figure.patch.set_facecolor(background)
        axis.set_facecolor(background)
        axis.tick_params(colors=foreground)
        for spine in axis.spines.values():
            spine.set_color(foreground)
        start = dataset.start_timestamp_us or int(series.timestamp_us[0])
        time = (series.timestamp_us.astype(np.float64) - start) * 1.0e-6
        values = np.asarray(series.values, dtype=np.float64)
        if values.ndim == 1:
            axis.plot(time, values, color=accent, linewidth=1.1, label=channel_id)
        else:
            colors = ("#2563EB", "#10B981", "#F97316", "#A855F7", "#EC4899", "#14B8A6")
            for index in range(values.shape[1]):
                label = series.columns[index] if series.columns else str(index)
                axis.plot(
                    time,
                    values[:, index],
                    color=colors[index % len(colors)],
                    linewidth=1.0,
                    label=label,
                )
            axis.legend(facecolor=background, labelcolor=foreground, framealpha=0.8)
        labels = _LABELS[language]
        title = channel_id
        if bool(dataset.metadata.get("synthetic", False)):
            title += f" — {labels['synthetic']}"
        axis.set_title(title, color=foreground)
        axis.set_xlabel(f"{labels['time']} (s)", color=foreground)
        axis.set_ylabel(f"{series.quantity} [{series.unit}]", color=foreground)
        axis.grid(True, alpha=0.22)
        figure.tight_layout()
        figure.savefig(path, facecolor=background)
        plt.close(figure)

    @staticmethod
    def _Position_Select(channels: Mapping[str, TimeSeries]) -> TimeSeries | None:
        preferred_suffixes = (
            "navigation.position_enu",
            "kf6.recorded.navigation.position_enu",
            "pure_ins.recorded.navigation.position_enu",
        )
        for suffix in preferred_suffixes:
            for channel_id, series in channels.items():
                if (
                    (channel_id == suffix or channel_id.endswith("." + suffix))
                    and series.values.ndim == 2
                    and series.values.shape[1] == 3
                ):
                    return series
        return None

    @staticmethod
    def _Attitude_Select(channels: Mapping[str, TimeSeries]) -> TimeSeries | None:
        preferred_suffixes = (
            "attitude.q_nb",
            "pure_ins.recorded.attitude.q_nb",
        )
        for suffix in preferred_suffixes:
            for channel_id, series in channels.items():
                if (
                    (channel_id == suffix or channel_id.endswith("." + suffix))
                    and series.values.ndim == 2
                    and series.values.shape[1] == 4
                ):
                    return series
        return None

    def _Trajectory_Write(
        self,
        dataset: FlightDataset,
        position: TimeSeries,
        path: Path,
        language: ExportLanguage,
        theme: ExportTheme,
    ) -> None:
        import matplotlib

        matplotlib.use("Agg")
        from matplotlib import pyplot as plt

        background, foreground, accent = self._Plot_Configure(theme)
        figure = plt.figure(figsize=(8, 7), dpi=150)
        figure.patch.set_facecolor(background)
        axis = figure.add_subplot(111, projection="3d")
        axis.set_facecolor(background)
        values = np.asarray(position.values, dtype=np.float64)
        axis.plot(values[:, 0], values[:, 1], values[:, 2], color=accent, linewidth=1.4)
        axis.scatter(values[0, 0], values[0, 1], values[0, 2], color="#10B981", s=24)
        axis.scatter(values[-1, 0], values[-1, 1], values[-1, 2], color="#EF4444", s=24)
        labels = _LABELS[language]
        title = labels["trajectory"]
        if bool(dataset.metadata.get("synthetic", False)):
            title += f" — {labels['synthetic']}"
        axis.set_title(title, color=foreground)
        axis.set_xlabel("E (m)", color=foreground)
        axis.set_ylabel("N (m)", color=foreground)
        axis.set_zlabel("U (m)", color=foreground)
        axis.tick_params(colors=foreground)
        figure.tight_layout()
        figure.savefig(path, facecolor=background)
        plt.close(figure)

    def _AttitudeGif_Write(
        self,
        dataset: FlightDataset,
        attitude: TimeSeries,
        path: Path,
        language: ExportLanguage,
        theme: ExportTheme,
        context: TaskContext,
    ) -> None:
        import matplotlib

        matplotlib.use("Agg")
        from matplotlib import pyplot as plt
        from PIL import Image

        maximum_frames = 160
        frame_indices = np.unique(
            np.linspace(0, attitude.count - 1, min(maximum_frames, attitude.count)).astype(int)
        )
        timestamps = attitude.timestamp_us[frame_indices]
        if len(timestamps) > 1:
            durations = np.diff(timestamps).astype(np.float64) * 1.0e-3
            # GIF stores delays in 10 ms units. Preserve logged timing up to the
            # format's 16-bit delay limit instead of rebuilding a nominal rate.
            durations = np.clip(durations, 10.0, 655350.0).astype(int).tolist()
            durations.append(durations[-1])
        else:
            durations = [100]
        background, foreground, _ = self._Plot_Configure(theme)
        frames: list[Image.Image] = []
        labels = _LABELS[language]
        body_axes = np.eye(3, dtype=np.float32)
        for frame_number, sample_index in enumerate(frame_indices):
            context.Cancel_RaiseIfRequested()
            quaternion = attitude.values[sample_index]
            rotated = np.asarray(
                [Quaternion_RotateVector(quaternion, body_axes[index]) for index in range(3)]
            )
            figure = plt.figure(figsize=(5, 5), dpi=90)
            figure.patch.set_facecolor(background)
            axis = figure.add_subplot(111, projection="3d")
            axis.set_facecolor(background)
            for vector, color, label in zip(
                rotated,
                ("#EF4444", "#10B981", "#3B82F6"),
                ("Body X", "Body Y", "Body Z"),
                strict=True,
            ):
                axis.quiver(0, 0, 0, vector[0], vector[1], vector[2], color=color, label=label)
            axis.set_xlim(-1.0, 1.0)
            axis.set_ylim(-1.0, 1.0)
            axis.set_zlim(-1.0, 1.0)
            axis.set_xlabel("E", color=foreground)
            axis.set_ylabel("N", color=foreground)
            axis.set_zlabel("U", color=foreground)
            elapsed = (
                int(attitude.timestamp_us[sample_index]) - int(attitude.timestamp_us[0])
            ) * 1.0e-6
            title = f"{labels['attitude']}\nt = {elapsed:.3f} s"
            if bool(dataset.metadata.get("synthetic", False)):
                title += f" — {labels['synthetic']}"
            axis.set_title(title, color=foreground)
            axis.tick_params(colors=foreground)
            figure.tight_layout()
            buffer = io.BytesIO()
            figure.savefig(buffer, format="png", facecolor=background)
            plt.close(figure)
            buffer.seek(0)
            frames.append(Image.open(buffer).convert("P", palette=Image.Palette.ADAPTIVE))
            context.Progress_Report(
                0.82 + 0.17 * (frame_number + 1) / len(frame_indices), "export.gif"
            )
        frames[0].save(
            path,
            save_all=True,
            append_images=frames[1:],
            duration=durations,
            loop=0,
            disposal=2,
        )
