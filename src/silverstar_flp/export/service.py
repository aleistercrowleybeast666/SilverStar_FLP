from __future__ import annotations

import colorsys
import csv
import io
import json
import re
from collections.abc import Callable, Mapping
from contextlib import suppress
from dataclasses import asdict, dataclass, is_dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

import numpy as np

from silverstar_flp.analysis.overview import FlightSummary_Build
from silverstar_flp.core.analysis_source import (
    AnalysisSourceKind,
    ChannelResolver,
    ReplayResultStore,
)
from silverstar_flp.core.context import TaskContext
from silverstar_flp.core.dataset import FlightDataset, TimeSeries
from silverstar_flp.core.math import Quaternion_RotateVector
from silverstar_flp.core.visual_semantics import (
    TRAJECTORY_DEPLOY_COLOR,
    TRAJECTORY_LANDING_COLOR,
    TRAJECTORY_POST_DEPLOY_COLOR,
    TRAJECTORY_PRE_DEPLOY_COLOR,
    RocketFaceColors_Get,
    TrajectoryPhaseColor_Get,
)
from silverstar_flp.export.plot_metadata import (
    ChannelDisplayMetadata_Get,
    ComponentLabel_Get,
)
from silverstar_flp.plugins.api.algorithm import AlgorithmResult


class ExportLanguage(StrEnum):
    FOLLOW_UI = "follow_ui"
    ZH = "zh_CN"
    EN = "en_US"


class ExportTheme(StrEnum):
    LIGHT = "light"
    DARK = "dark"


@dataclass(frozen=True, slots=True)
class ExportOptions:
    language: ExportLanguage = ExportLanguage.FOLLOW_UI
    ui_language: str = "zh_CN"
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
class ExportFailure:
    item: str
    error: str


@dataclass(frozen=True, slots=True)
class ExportManifest:
    output_directory: Path
    files: tuple[Path, ...]
    language: ExportLanguage
    theme: ExportTheme
    failures: tuple[ExportFailure, ...] = ()


_LABELS = {
    ExportLanguage.ZH: {
        "time": "任务时间",
        "value": "数值",
        "valid": "有效",
        "trajectory": "三维飞行轨迹（任务起点相对 ENU）",
        "attitude": "姿态",
        "trajectory_panel": "三维轨迹",
        "recorded": "飞控记录",
        "recorded_pure_ins": "飞控纯惯导",
        "recorded_kf6": "飞控 KF_6",
        "active": "活动数据源",
        "synthetic": "合成测试数据",
        "pre_deploy": "开伞前",
        "post_deploy": "开伞后",
        "start": "任务开始",
        "deploy": "开伞",
        "landing": "着陆",
        "current": "当前位置",
        "innovation": "KF_6 新息",
        "nis": "KF_6 NIS",
        "measurement_update": "KF_6 量测更新",
    },
    ExportLanguage.EN: {
        "time": "Mission Time",
        "value": "Value",
        "valid": "Valid",
        "trajectory": "3D Flight Trajectory (Mission-relative ENU)",
        "attitude": "Attitude",
        "trajectory_panel": "3D Trajectory",
        "recorded": "Recorded",
        "recorded_pure_ins": "Recorded Pure INS",
        "recorded_kf6": "Recorded KF_6",
        "active": "Active Source",
        "synthetic": "Synthetic Test Data",
        "pre_deploy": "Pre-deploy",
        "post_deploy": "Post-deploy",
        "start": "Mission Start",
        "deploy": "Deploy",
        "landing": "Landing",
        "current": "Current Position",
        "innovation": "KF_6 Innovation",
        "nis": "KF_6 NIS",
        "measurement_update": "KF_6 Measurement Update",
    },
}

_COLORS = (
    "#2563EB",
    "#16A34A",
    "#EA580C",
    "#9333EA",
    "#DB2777",
    "#0891B2",
    "#CA8A04",
    "#DC2626",
    "#4F46E5",
    "#059669",
    "#C2410C",
    "#7C3AED",
    "#BE185D",
    "#0E7490",
    "#A16207",
    "#B91C1C",
)
_ROCKET_BASE_VERTICES = np.asarray(
    (
        (-0.35, -0.35, 0.0),
        (0.35, -0.35, 0.0),
        (0.35, 0.35, 0.0),
        (-0.35, 0.35, 0.0),
        (0.0, 0.0, 2.2),
    ),
    dtype=np.float64,
)
_ROCKET_FACES = np.asarray(
    (
        (0, 1, 4),
        (1, 2, 4),
        (2, 3, 4),
        (3, 0, 4),
        (0, 1, 2),
        (0, 2, 3),
    ),
    dtype=np.uint32,
)
_EVENT_MISSION_START = 0x03
_EVENT_DEPLOY = 0x29
_EVENT_LANDING = 0x2A


def _PlotColor_Get(index: int) -> str:
    if index < len(_COLORS):
        return _COLORS[index]
    hue = (0.61803398875 * index + 0.13) % 1.0
    red, green, blue = colorsys.hsv_to_rgb(hue, 0.68, 0.88)
    return f"#{round(red * 255):02X}{round(green * 255):02X}{round(blue * 255):02X}"


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


def _Event_Timestamp(dataset: FlightDataset, event_id: int) -> int | None:
    for record in dataset.Records_Get("EVENT"):
        if int(record.payload.get("event_id", -1)) == event_id:
            return int(record.timestamp_us)
    return None


def _Series_Crop(series: TimeSeries, start_timestamp_us: int) -> TimeSeries:
    mask = series.timestamp_us >= np.uint64(max(start_timestamp_us, 0))
    return TimeSeries(
        timestamp_us=series.timestamp_us[mask],
        values=np.asarray(series.values)[mask],
        unit=series.unit,
        quantity=series.quantity,
        source=series.source,
        valid=series.valid[mask],
        columns=series.columns,
        metadata=series.metadata,
    )


class FlightExporter:
    def export(
        self,
        dataset: FlightDataset,
        output_directory: Path,
        *,
        options: ExportOptions | None = None,
        algorithm_results: Mapping[str, AlgorithmResult] | None = None,
        replay_store: ReplayResultStore | None = None,
        context: TaskContext | None = None,
    ) -> ExportManifest:
        requested = options or ExportOptions()
        language = self._Language_Resolve(requested.language, requested.ui_language)
        task_context = context or TaskContext()
        output = Path(output_directory)
        output.mkdir(parents=True, exist_ok=True)
        suffix = "_ZH" if language == ExportLanguage.ZH else "_EN"
        files: list[Path] = []
        failures: list[ExportFailure] = []
        store = self._Store_Prepare(replay_store, algorithm_results or {})
        resolver = ChannelResolver(dataset, store)
        channels = resolver.ExplorerChannels_Get()
        if requested.selected_channels:
            selected = set(requested.selected_channels)
            channels = {name: series for name, series in channels.items() if name in selected}
        item_count = max(len(channels), 1)

        def attempt(item: str, path: Path, callback: Callable[[], None]) -> None:
            try:
                task_context.Cancel_RaiseIfRequested()
                callback()
                files.append(path)
            except Exception as exc:  # Each product must fail independently.
                failures.append(ExportFailure(item, f"{type(exc).__name__}: {exc}"))

        if requested.include_overview:
            task_context.Progress_Report(0.02, "export.overview")
            path = output / f"Flight_Overview{suffix}.json"
            attempt(
                "overview",
                path,
                lambda: path.write_text(
                    json.dumps(
                        FlightSummary_Build(dataset),
                        default=_Json_Default,
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                ),
            )
        if requested.include_diagnostics:
            path = output / f"Parser_Diagnostics{suffix}.json"
            attempt(
                "diagnostics",
                path,
                lambda: path.write_text(
                    json.dumps(dataset.diagnostics.to_dict(), ensure_ascii=False, indent=2),
                    encoding="utf-8",
                ),
            )
        if requested.include_events:
            path = output / f"Events{suffix}.csv"
            attempt("events", path, lambda: self._Events_Write(dataset, path))

        if requested.include_csv:
            csv_directory = output / f"CSV{suffix}"
            csv_directory.mkdir(exist_ok=True)
            for index, (channel_id, series) in enumerate(channels.items()):
                path = csv_directory / f"{_Filename_Sanitize(channel_id)}{suffix}.csv"
                attempt(
                    f"csv:{channel_id}",
                    path,
                    lambda p=path, c=channel_id, s=series: self._SeriesCsv_Write(
                        dataset, c, s, p
                    ),
                )
                task_context.Progress_Report(
                    0.05 + 0.30 * (index + 1) / item_count,
                    "export.csv",
                )

        if requested.include_plots:
            plot_directory = output / f"Plots{suffix}"
            plot_directory.mkdir(exist_ok=True)
            self._StandardPlots_Write(
                dataset,
                resolver,
                plot_directory,
                suffix,
                language,
                requested.theme,
                attempt,
            )
            if requested.selected_channels:
                for index, (channel_id, series) in enumerate(channels.items()):
                    if series.count == 0 or np.asarray(series.values).ndim > 2:
                        continue
                    path = plot_directory / (
                        f"Channel_{_Filename_Sanitize(channel_id)}{suffix}.png"
                    )
                    attempt(
                        f"plot:{channel_id}",
                        path,
                        lambda p=path, c=channel_id, s=series: self._SeriesPlot_Write(
                            dataset,
                            c,
                            s,
                            p,
                            language,
                            requested.theme,
                        ),
                    )
                    task_context.Progress_Report(
                        0.37 + 0.28 * (index + 1) / item_count,
                        "export.plots",
                    )

        if requested.include_trajectory_3d:
            path = output / f"Trajectory_3D{suffix}.png"
            attempt(
                "trajectory_3d",
                path,
                lambda: self._Trajectory_Write(
                    dataset,
                    self._Series_Require(
                        resolver.Series_Get("navigation.position_enu"),
                        "navigation.position_enu",
                    ),
                    path,
                    language,
                    requested.theme,
                ),
            )
        if requested.include_attitude_gif:
            task_context.Progress_Report(0.72, "export.gif")
            path = output / f"Flight_Replay{suffix}.gif"
            attempt(
                "flight_replay_gif",
                path,
                lambda: self._FlightReplayGif_Write(
                    dataset,
                    self._Series_Require(
                        resolver.Series_Get("attitude.q_nb"),
                        "attitude.q_nb",
                    ),
                    self._Series_Require(
                        resolver.Series_Get("navigation.position_enu"),
                        "navigation.position_enu",
                    ),
                    path,
                    language,
                    requested.theme,
                    task_context,
                ),
            )

        manifest_path = output / f"Export_Manifest{suffix}.json"
        try:
            self._Manifest_Write(
                manifest_path,
                output,
                files,
                failures,
                language,
                requested.theme,
                store,
            )
            files.append(manifest_path)
        except Exception as exc:
            failures.append(ExportFailure("manifest", f"{type(exc).__name__}: {exc}"))
        task_context.Progress_Report(1.0, "export.complete")
        return ExportManifest(
            output,
            tuple(files),
            language,
            requested.theme,
            tuple(failures),
        )

    @staticmethod
    def _Language_Resolve(language: ExportLanguage, ui_language: str) -> ExportLanguage:
        if language != ExportLanguage.FOLLOW_UI:
            return language
        return ExportLanguage.EN if ui_language == ExportLanguage.EN.value else ExportLanguage.ZH

    @staticmethod
    def _Store_Prepare(
        replay_store: ReplayResultStore | None,
        algorithm_results: Mapping[str, AlgorithmResult],
    ) -> ReplayResultStore:
        if replay_store is not None:
            return replay_store
        store = ReplayResultStore()
        latest_source = ReplayResultStore.RECORDED_SOURCE_ID
        for result_name, result in algorithm_results.items():
            entry = store.Result_Add(result, algorithm_name=result_name)
            latest_source = entry.source_id
        store.ActiveSource_Set(latest_source)
        return store

    @staticmethod
    def _Series_Require(series: TimeSeries | None, channel_id: str) -> TimeSeries:
        if series is None or series.count == 0:
            raise ValueError(f"channel_unavailable:{channel_id}")
        return series

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
    def _Manifest_Write(
        path: Path,
        output: Path,
        files: list[Path],
        failures: list[ExportFailure],
        language: ExportLanguage,
        theme: ExportTheme,
        store: ReplayResultStore,
    ) -> None:
        active = store.ActiveSource_Get()
        payload = {
            "language": language.value,
            "theme": theme.value,
            "active_analysis_source": active.source_id,
            "active_source_kind": active.kind.value,
            "files": [str(item.relative_to(output)) for item in files],
            "failures": [asdict(item) for item in failures],
        }
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def _Plot_Configure(theme: ExportTheme) -> tuple[str, str, str]:
        if theme == ExportTheme.DARK:
            return "#0B1220", "#E5E7EB", "#334155"
        return "#FFFFFF", "#111827", "#CBD5E1"

    @staticmethod
    def _Matplotlib_Configure() -> None:
        import matplotlib

        matplotlib.use("Agg")
        matplotlib.rcParams["font.sans-serif"] = [
            "Microsoft YaHei",
            "SimHei",
            "Noto Sans CJK SC",
            "Arial Unicode MS",
            "DejaVu Sans",
        ]
        matplotlib.rcParams["axes.unicode_minus"] = False

    def _Axes_Style(self, figure: Any, axis: Any, theme: ExportTheme) -> None:
        background, foreground, grid = self._Plot_Configure(theme)
        figure.patch.set_facecolor(background)
        axis.set_facecolor(background)
        axis.tick_params(colors=foreground)
        axis.grid(True, color=grid, alpha=0.32)
        for spine in axis.spines.values():
            spine.set_color(foreground)

    @staticmethod
    def _Time_Get(dataset: FlightDataset, series: TimeSeries) -> np.ndarray:
        start = dataset.start_timestamp_us or int(series.timestamp_us[0])
        return (series.timestamp_us.astype(np.float64) - start) * 1.0e-6

    def _SeriesPlot_Write(
        self,
        dataset: FlightDataset,
        channel_id: str,
        series: TimeSeries,
        path: Path,
        language: ExportLanguage,
        theme: ExportTheme,
    ) -> None:
        self._Matplotlib_Configure()
        from matplotlib import pyplot as plt

        start = dataset.start_timestamp_us or int(series.timestamp_us[0])
        cropped = _Series_Crop(series, start)
        if cropped.count == 0:
            raise ValueError(f"no_post_start_samples:{channel_id}")
        metadata = ChannelDisplayMetadata_Get(channel_id, cropped)
        background, foreground, _ = self._Plot_Configure(theme)
        figure, axis = plt.subplots(figsize=(10, 5), dpi=140)
        self._Axes_Style(figure, axis, theme)
        time = self._Time_Get(dataset, cropped)
        values = np.asarray(cropped.values, dtype=np.float64)
        values = values.copy()
        if values.ndim == 1:
            values[~cropped.valid] = np.nan
            axis.plot(time, values, color=_PlotColor_Get(0), linewidth=1.15)
        else:
            values[~cropped.valid, :] = np.nan
            for index in range(values.shape[1]):
                raw_label = cropped.columns[index] if cropped.columns else str(index)
                axis.plot(
                    time,
                    values[:, index],
                    color=_PlotColor_Get(index),
                    linewidth=1.05,
                    label=ComponentLabel_Get(raw_label, language.value),
                )
            axis.legend(facecolor=background, labelcolor=foreground, framealpha=0.82)
        labels = _LABELS[language]
        title = metadata.Title_Get(language.value)
        if bool(dataset.metadata.get("synthetic", False)):
            title += f" · {labels['synthetic']}"
        axis.set_title(title, color=foreground)
        axis.set_xlabel(f"{labels['time']} (s)", color=foreground)
        quantity = metadata.Quantity_Get(language.value)
        unit = "" if cropped.unit in ("", "1", "enum", "bitmask") else f" [{cropped.unit}]"
        axis.set_ylabel(f"{quantity}{unit}", color=foreground)
        figure.tight_layout()
        figure.savefig(path, facecolor=background)
        plt.close(figure)

    def _MultiSeriesPlot_Write(
        self,
        dataset: FlightDataset,
        layers: tuple[tuple[TimeSeries, str, str], ...],
        path: Path,
        title: str,
        ylabel: str,
        language: ExportLanguage,
        theme: ExportTheme,
    ) -> None:
        self._Matplotlib_Configure()
        from matplotlib import pyplot as plt

        background, foreground, _ = self._Plot_Configure(theme)
        figure, axis = plt.subplots(figsize=(10, 5), dpi=140)
        self._Axes_Style(figure, axis, theme)
        color_index = 0
        plotted = 0
        start = dataset.start_timestamp_us or 0
        for series, prefix, line_style in layers:
            cropped = _Series_Crop(series, start)
            if cropped.count == 0:
                continue
            time = self._Time_Get(dataset, cropped)
            values = np.asarray(cropped.values, dtype=np.float64)
            values = values[:, None] if values.ndim == 1 else values
            values = values.copy()
            values[~cropped.valid, :] = np.nan
            for index in range(values.shape[1]):
                component = cropped.columns[index] if cropped.columns else ""
                component = ComponentLabel_Get(component, language.value)
                label = " · ".join(item for item in (prefix, component) if item)
                axis.plot(
                    time,
                    values[:, index],
                    color=_PlotColor_Get(color_index),
                    linestyle=line_style,
                    linewidth=1.05,
                    label=label,
                )
                color_index += 1
                plotted += 1
        if plotted == 0:
            raise ValueError("no_post_start_samples")
        axis.set_title(title, color=foreground)
        axis.set_xlabel(f"{_LABELS[language]['time']} (s)", color=foreground)
        axis.set_ylabel(ylabel, color=foreground)
        axis.legend(facecolor=background, labelcolor=foreground, framealpha=0.82, ncol=2)
        figure.tight_layout()
        figure.savefig(path, facecolor=background)
        plt.close(figure)

    @staticmethod
    def _EstimatorSourceId_Select(resolver: ChannelResolver) -> str:
        active = resolver.store.ActiveSource_Get().source_id
        sources = resolver.EstimatorSources_Get()
        if any(source.source_id == active for source in sources):
            return active
        return sources[0].source_id if sources else ReplayResultStore.RECORDED_SOURCE_ID

    def _StandardPlots_Write(
        self,
        dataset: FlightDataset,
        resolver: ChannelResolver,
        directory: Path,
        suffix: str,
        language: ExportLanguage,
        theme: ExportTheme,
        attempt: Callable[[str, Path, Callable[[], None]], None],
    ) -> None:
        labels = _LABELS[language]
        active = resolver.store.ActiveSource_Get()

        def flight_layers(channel_id: str) -> tuple[tuple[TimeSeries, str, str], ...]:
            recorded_solutions = resolver.RecordedSolutionLayers_Get(channel_id)
            if active.kind == AnalysisSourceKind.RECORDED and recorded_solutions:
                return tuple(
                    (
                        layer.series,
                        labels.get(
                            f"recorded_{layer.solution_id}",
                            labels["recorded"],
                        ),
                        "-",
                    )
                    for layer in recorded_solutions
                )
            series = self._Series_Require(resolver.Series_Get(channel_id), channel_id)
            if active.kind == AnalysisSourceKind.RECORDED:
                return ((series, labels["recorded"], "-"),)
            layers = [(series, labels["active"], "-")]
            if recorded_solutions:
                layers.extend(
                    (
                        layer.series,
                        labels.get(
                            f"recorded_{layer.solution_id}",
                            labels["recorded"],
                        ),
                        "--",
                    )
                    for layer in recorded_solutions
                )
            else:
                recorded = resolver.RecordedSeries_Get(channel_id)
                if recorded is not None:
                    layers.append((recorded, labels["recorded"], "--"))
            return tuple(layers)

        standard_flight = (
            (
                "Flight_Velocity_ENU",
                "navigation.velocity_enu",
                "飞行速度（ENU）" if language == ExportLanguage.ZH else "Flight Velocity (ENU)",
                "速度 [m/s]" if language == ExportLanguage.ZH else "Velocity [m/s]",
            ),
            (
                "Flight_Position_ENU",
                "navigation.position_enu",
                "飞行位置（ENU）" if language == ExportLanguage.ZH else "Flight Position (ENU)",
                "位置 [m]" if language == ExportLanguage.ZH else "Position [m]",
            ),
            (
                "Flight_Attitude",
                "attitude.q_nb",
                (
                    "软件姿态四元数（WXYZ，机体 → ENU）"
                    if language == ExportLanguage.ZH
                    else "Software Attitude Quaternion (WXYZ, Body to ENU)"
                ),
                "四元数" if language == ExportLanguage.ZH else "Quaternion",
            ),
        )
        for file_stem, channel_id, title, ylabel in standard_flight:
            path = directory / f"{file_stem}{suffix}.png"
            attempt(
                f"standard_plot:{file_stem}",
                path,
                lambda p=path, c=channel_id, t=title, y=ylabel: self._MultiSeriesPlot_Write(
                    dataset,
                    flight_layers(c),
                    p,
                    t,
                    y,
                    language,
                    theme,
                ),
            )

        observed = (
            (
                "Flight_Acceleration_XYZ",
                "imu.corrected.accel_b",
                (
                    "校正后加速度（机体系 XYZ）"
                    if language == ExportLanguage.ZH
                    else "Corrected Acceleration (Body XYZ)"
                ),
                "加速度 [m/s²]" if language == ExportLanguage.ZH else "Acceleration [m/s²]",
            ),
            (
                "Flight_Angular_Rate_XYZ",
                "imu.corrected.gyro_b",
                (
                    "校正后角速度（机体系 XYZ）"
                    if language == ExportLanguage.ZH
                    else "Corrected Angular Rate (Body XYZ)"
                ),
                "角速度 [rad/s]" if language == ExportLanguage.ZH else "Angular Rate [rad/s]",
            ),
        )
        for file_stem, channel_id, title, ylabel in observed:
            path = directory / f"{file_stem}{suffix}.png"
            attempt(
                f"standard_plot:{file_stem}",
                path,
                lambda p=path, c=channel_id, t=title, y=ylabel: self._MultiSeriesPlot_Write(
                    dataset,
                    (
                        (
                            self._Series_Require(resolver.RecordedSeries_Get(c), c),
                            labels["recorded"],
                            "-",
                        ),
                    ),
                    p,
                    t,
                    y,
                    language,
                    theme,
                ),
            )

        estimator_source = self._EstimatorSourceId_Select(resolver)
        covariance = resolver.Series_Get("kf6.covariance.diagonal", estimator_source)
        path = directory / f"State_Covariance{suffix}.png"
        attempt(
            "standard_plot:State_Covariance",
            path,
            lambda: self._SeriesPlot_Write(
                dataset,
                "kf6.covariance.diagonal",
                self._Series_Require(covariance, "kf6.covariance.diagonal"),
                path,
                language,
                theme,
            ),
        )

        innovation_layers: list[tuple[TimeSeries, str, str]] = []
        nis_layers: list[tuple[TimeSeries, str, str]] = []
        for channel_id, zh, en in (
            ("kf6.innovation.position", "位置", "Position"),
            ("kf6.innovation.velocity", "速度", "Velocity"),
            ("kf6.innovation.baro", "气压高度", "Barometer"),
        ):
            series = resolver.Series_Get(channel_id, estimator_source)
            if series is not None:
                innovation_layers.append((series, zh if language == ExportLanguage.ZH else en, "-"))
        for channel_id, zh, en in (
            ("kf6.nis.position", "位置", "Position"),
            ("kf6.nis.velocity", "速度", "Velocity"),
            ("kf6.nis.baro", "气压高度", "Barometer"),
        ):
            series = resolver.Series_Get(channel_id, estimator_source)
            if series is not None:
                nis_layers.append((series, zh if language == ExportLanguage.ZH else en, "-"))
        path = directory / f"State_Innovation{suffix}.png"
        attempt(
            "standard_plot:State_Innovation",
            path,
            lambda: self._MultiSeriesPlot_Write(
                dataset,
                tuple(innovation_layers),
                path,
                labels["innovation"],
                (
                    "新息（记录单位）"
                    if language == ExportLanguage.ZH
                    else "Innovation (logged units)"
                ),
                language,
                theme,
            ),
        )
        path = directory / f"State_NIS{suffix}.png"
        attempt(
            "standard_plot:State_NIS",
            path,
            lambda: self._MultiSeriesPlot_Write(
                dataset,
                tuple(nis_layers),
                path,
                labels["nis"],
                "NIS",
                language,
                theme,
            ),
        )
        path = directory / f"State_Measurement_Update{suffix}.png"
        attempt(
            "standard_plot:State_Measurement_Update",
            path,
            lambda: self._MeasurementUpdatePlot_Write(
                dataset,
                self._Series_Require(
                    resolver.Series_Get("kf6.update_result", estimator_source),
                    "kf6.update_result",
                ),
                resolver.Series_Get("kf6.measurement_r_scale", estimator_source),
                path,
                language,
                theme,
            ),
        )

    def _MeasurementUpdatePlot_Write(
        self,
        dataset: FlightDataset,
        results: TimeSeries,
        r_scale: TimeSeries | None,
        path: Path,
        language: ExportLanguage,
        theme: ExportTheme,
    ) -> None:
        self._Matplotlib_Configure()
        from matplotlib import pyplot as plt

        background, foreground, _ = self._Plot_Configure(theme)
        rows = 2 if r_scale is not None and r_scale.count else 1
        figure, axes = plt.subplots(rows, 1, figsize=(10, 6 if rows == 2 else 4.5), dpi=140)
        axes_array = np.atleast_1d(axes)
        self._Axes_Style(figure, axes_array[0], theme)
        cropped = _Series_Crop(results, dataset.start_timestamp_us or 0)
        time = self._Time_Get(dataset, cropped)
        values = np.asarray(cropped.values, dtype=np.float64)
        values = values[:, None] if values.ndim == 1 else values
        for index in range(values.shape[1]):
            raw = cropped.columns[index] if cropped.columns else str(index)
            axes_array[0].step(
                time,
                values[:, index],
                where="post",
                color=_COLORS[index],
                label=ComponentLabel_Get(raw, language.value),
            )
        result_labels = (
            ("接受", "软降权", "NIS 拒绝", "无效", "数值错误")
            if language == ExportLanguage.ZH
            else ("Accepted", "Soft Weighted", "NIS Rejected", "Invalid", "Numeric Error")
        )
        axes_array[0].set_yticks(range(5), result_labels)
        axes_array[0].set_title(_LABELS[language]["measurement_update"], color=foreground)
        axes_array[0].set_ylabel(
            "更新结果" if language == ExportLanguage.ZH else "Update Result",
            color=foreground,
        )
        axes_array[0].legend(facecolor=background, labelcolor=foreground, framealpha=0.82)
        if rows == 2 and r_scale is not None:
            self._Axes_Style(figure, axes_array[1], theme)
            cropped_scale = _Series_Crop(r_scale, dataset.start_timestamp_us or 0)
            scale_time = self._Time_Get(dataset, cropped_scale)
            scale_values = np.asarray(cropped_scale.values, dtype=np.float64)
            scale_values = (
                scale_values[:, None] if scale_values.ndim == 1 else scale_values
            )
            for index in range(scale_values.shape[1]):
                raw = cropped_scale.columns[index] if cropped_scale.columns else str(index)
                axes_array[1].plot(
                    scale_time,
                    scale_values[:, index],
                    color=_COLORS[index],
                    label=ComponentLabel_Get(raw, language.value),
                )
            axes_array[1].set_ylabel("R 缩放" if language == ExportLanguage.ZH else "R Scale")
            axes_array[1].legend(
                facecolor=background,
                labelcolor=foreground,
                framealpha=0.82,
            )
        axes_array[-1].set_xlabel(f"{_LABELS[language]['time']} (s)", color=foreground)
        figure.tight_layout()
        figure.savefig(path, facecolor=background)
        plt.close(figure)

    @staticmethod
    def _Position_At(position: TimeSeries, timestamp_us: int) -> np.ndarray | None:
        if position.count == 0:
            return None
        values = np.asarray(position.values, dtype=np.float64)
        if values.ndim != 2 or values.shape[1] != 3:
            return None
        valid = position.valid & np.all(np.isfinite(values), axis=1)
        timestamps = position.timestamp_us[valid].astype(np.float64)
        values = values[valid]
        if timestamps.size == 0:
            return None
        if timestamp_us < timestamps[0] or timestamp_us > timestamps[-1]:
            return None
        if timestamp_us == timestamps[0]:
            return values[0].copy()
        if timestamp_us == timestamps[-1]:
            return values[-1].copy()
        upper = int(np.searchsorted(timestamps, float(timestamp_us), side="right"))
        lower = upper - 1
        span = timestamps[upper] - timestamps[lower]
        ratio = 0.0 if span <= 0.0 else (timestamp_us - timestamps[lower]) / span
        return values[lower] + ratio * (values[upper] - values[lower])

    @staticmethod
    def _Position_NearEvent(
        position: TimeSeries,
        timestamp_us: int,
    ) -> np.ndarray | None:
        interpolated = FlightExporter._Position_At(position, timestamp_us)
        if interpolated is not None:
            return interpolated
        values = np.asarray(position.values, dtype=np.float64)
        valid = position.valid & np.all(np.isfinite(values), axis=1)
        timestamps = position.timestamp_us[valid].astype(np.int64)
        points = values[valid]
        if timestamps.size == 0:
            return None
        intervals = np.diff(timestamps)
        typical_interval = float(np.median(intervals)) if intervals.size else 0.0
        tolerance_us = max(int(typical_interval * 5.0), 100_000)
        index = int(np.argmin(np.abs(timestamps - timestamp_us)))
        if abs(int(timestamps[index]) - timestamp_us) > tolerance_us:
            return None
        return points[index].copy()

    @staticmethod
    def _TrajectoryOrigin_Get(
        position: TimeSeries,
        start_timestamp_us: int,
    ) -> np.ndarray:
        interpolated = FlightExporter._Position_At(position, start_timestamp_us)
        if interpolated is not None:
            return interpolated
        values = np.asarray(position.values, dtype=np.float64)
        valid = position.valid & np.all(np.isfinite(values), axis=1)
        post_start = np.flatnonzero(
            valid
            & (
                position.timestamp_us
                >= np.uint64(max(start_timestamp_us, 0))
            )
        )
        if post_start.size:
            return values[post_start[0]].copy()
        available = np.flatnonzero(valid)
        if available.size:
            return values[available[0]].copy()
        return np.zeros(3, dtype=np.float64)

    @staticmethod
    def _TrajectorySegments_Get(
        position: TimeSeries,
        deploy_timestamp_us: int | None,
    ) -> tuple[np.ndarray, np.ndarray]:
        if deploy_timestamp_us is None:
            return np.arange(position.count, dtype=np.int64), np.asarray([], dtype=np.int64)
        timestamps = position.timestamp_us
        pre = np.flatnonzero(timestamps <= np.uint64(deploy_timestamp_us))
        post = np.flatnonzero(timestamps >= np.uint64(deploy_timestamp_us))
        return pre, post

    @staticmethod
    def _Axis3d_Equal(axis: Any, values: np.ndarray) -> None:
        if values.size == 0:
            return
        minimum = np.nanmin(values, axis=0)
        maximum = np.nanmax(values, axis=0)
        center = (minimum + maximum) * 0.5
        radius = max(float(np.nanmax(maximum - minimum)) * 0.55, 1.0)
        axis.set_xlim(center[0] - radius, center[0] + radius)
        axis.set_ylim(center[1] - radius, center[1] + radius)
        axis.set_zlim(center[2] - radius, center[2] + radius)
        with suppress(AttributeError):
            axis.set_box_aspect((1.0, 1.0, 1.0))

    def _Trajectory_AxisDraw(
        self,
        axis: Any,
        dataset: FlightDataset,
        position: TimeSeries,
        language: ExportLanguage,
        theme: ExportTheme,
        *,
        current_timestamp_us: int | None = None,
    ) -> None:
        background, foreground, _ = self._Plot_Configure(theme)
        start = dataset.start_timestamp_us or int(position.timestamp_us[0])
        origin = self._TrajectoryOrigin_Get(position, start)
        cropped = _Series_Crop(position, start)
        cropped_values = np.asarray(cropped.values, dtype=np.float64)
        finite_valid = cropped.valid & np.all(np.isfinite(cropped_values), axis=1)
        cropped = TimeSeries(
            timestamp_us=cropped.timestamp_us[finite_valid],
            values=cropped_values[finite_valid],
            unit=cropped.unit,
            quantity=cropped.quantity,
            source=cropped.source,
            valid=np.ones(int(np.count_nonzero(finite_valid)), dtype=np.bool_),
            columns=cropped.columns,
            metadata=cropped.metadata,
        )
        if current_timestamp_us is not None:
            mask = cropped.timestamp_us <= np.uint64(current_timestamp_us)
            cropped = TimeSeries(
                timestamp_us=cropped.timestamp_us[mask],
                values=np.asarray(cropped.values)[mask],
                unit=cropped.unit,
                quantity=cropped.quantity,
                source=cropped.source,
                valid=cropped.valid[mask],
                columns=cropped.columns,
                metadata=cropped.metadata,
            )
        if cropped.count == 0:
            raise ValueError("trajectory_has_no_post_start_samples")
        values = np.asarray(cropped.values, dtype=np.float64) - origin
        deploy = _Event_Timestamp(dataset, _EVENT_DEPLOY)
        landing = _Event_Timestamp(dataset, _EVENT_LANDING)
        pre, post = self._TrajectorySegments_Get(cropped, deploy)
        labels = _LABELS[language]
        if pre.size:
            axis.plot(
                values[pre, 0],
                values[pre, 1],
                values[pre, 2],
                color=TRAJECTORY_PRE_DEPLOY_COLOR,
                linewidth=1.7,
                label=labels["pre_deploy"],
            )
        if post.size:
            axis.plot(
                values[post, 0],
                values[post, 1],
                values[post, 2],
                color=TRAJECTORY_POST_DEPLOY_COLOR,
                linewidth=1.7,
                label=labels["post_deploy"],
            )
        if deploy is not None and deploy <= int(cropped.timestamp_us[-1]):
            point = self._Position_At(position, deploy)
            if point is not None:
                point = point - origin
                axis.scatter(
                    *point,
                    color=TRAJECTORY_DEPLOY_COLOR,
                    edgecolors=TRAJECTORY_DEPLOY_COLOR,
                    linewidths=0.6,
                    s=55,
                    marker="o",
                    depthshade=False,
                    label=labels["deploy"],
                )
        landing_reached = current_timestamp_us is None or (
            landing is not None and landing <= current_timestamp_us
        )
        if landing is not None and landing_reached:
            point = self._Position_NearEvent(position, landing)
            if point is not None:
                point = point - origin
                axis.scatter(
                    *point,
                    color=TRAJECTORY_LANDING_COLOR,
                    s=48,
                    marker="o",
                    label=labels["landing"],
                )
        axis.scatter(
            *values[-1],
            color=TrajectoryPhaseColor_Get(
                int(cropped.timestamp_us[-1]),
                deploy,
            ),
            s=38,
            marker="o",
            label=labels["current"],
        )
        axis.set_facecolor(background)
        axis.set_xlabel("E (m)", color=foreground)
        axis.set_ylabel("N (m)", color=foreground)
        axis.set_zlabel("U (m)", color=foreground)
        axis.tick_params(colors=foreground)
        axis.legend(facecolor=background, labelcolor=foreground, framealpha=0.78)
        full_values = np.asarray(position.values, dtype=np.float64)
        valid_values = (
            full_values[
                position.valid
                & np.all(np.isfinite(full_values), axis=1)
                & (position.timestamp_us >= np.uint64(max(start, 0)))
            ]
            - origin
        )
        self._Axis3d_Equal(axis, valid_values)

    def _Trajectory_Write(
        self,
        dataset: FlightDataset,
        position: TimeSeries,
        path: Path,
        language: ExportLanguage,
        theme: ExportTheme,
    ) -> None:
        self._Matplotlib_Configure()
        from matplotlib import pyplot as plt

        background, foreground, _ = self._Plot_Configure(theme)
        figure = plt.figure(figsize=(8, 7), dpi=150)
        figure.patch.set_facecolor(background)
        axis = figure.add_subplot(111, projection="3d")
        self._Trajectory_AxisDraw(axis, dataset, position, language, theme)
        title = _LABELS[language]["trajectory"]
        if bool(dataset.metadata.get("synthetic", False)):
            title += f" · {_LABELS[language]['synthetic']}"
        axis.set_title(title, color=foreground)
        figure.tight_layout()
        figure.savefig(path, facecolor=background)
        plt.close(figure)

    @staticmethod
    def _NearestIndex(timestamps: np.ndarray, timestamp_us: int) -> int:
        if timestamps.size == 0:
            return 0
        upper = int(np.searchsorted(timestamps, np.uint64(timestamp_us), side="left"))
        if upper <= 0:
            return 0
        if upper >= timestamps.size:
            return int(timestamps.size - 1)
        before = int(timestamps[upper - 1])
        after = int(timestamps[upper])
        return upper - 1 if timestamp_us - before <= after - timestamp_us else upper

    @staticmethod
    def _ReplayFrameTimestamps_Get(
        attitude: TimeSeries,
        position: TimeSeries,
        start_timestamp_us: int,
        maximum_frames: int = 60,
    ) -> np.ndarray:
        if maximum_frames <= 0:
            raise ValueError("maximum_frames_must_be_positive")
        attitude_times = attitude.timestamp_us[
            attitude.timestamp_us >= np.uint64(max(start_timestamp_us, 0))
        ]
        position_times = position.timestamp_us[
            position.timestamp_us >= np.uint64(max(start_timestamp_us, 0))
        ]
        if attitude_times.size == 0 or position_times.size == 0:
            return np.asarray([], dtype=np.uint64)
        start = max(int(attitude_times[0]), int(position_times[0]), start_timestamp_us)
        end = min(int(attitude_times[-1]), int(position_times[-1]))
        if end < start:
            return np.asarray([], dtype=np.uint64)
        available = max(int(attitude_times.size), int(position_times.size))
        count = min(maximum_frames, available)
        if count <= 1 or end == start:
            return np.asarray([start], dtype=np.uint64)
        return np.unique(np.linspace(start, end, count).round().astype(np.uint64))

    def _Attitude_AxisDraw(
        self,
        axis: Any,
        quaternion: np.ndarray,
        language: ExportLanguage,
        theme: ExportTheme,
    ) -> None:
        background, foreground, _ = self._Plot_Configure(theme)
        from mpl_toolkits.mplot3d.art3d import Poly3DCollection

        rotated_vertices = np.asarray(
            [
                Quaternion_RotateVector(quaternion, vertex)
                for vertex in _ROCKET_BASE_VERTICES
            ],
            dtype=np.float64,
        )
        polygons = [rotated_vertices[face] for face in _ROCKET_FACES]
        face_colors = RocketFaceColors_Get(theme.value)
        rocket = Poly3DCollection(
            polygons,
            facecolors=face_colors,
            edgecolors=foreground,
            linewidths=0.7,
            alpha=1.0,
        )
        axis.add_collection3d(rocket)

        body_endpoints = np.asarray(
            ((1.1, 0.0, 0.0), (0.0, 1.1, 0.0), (0.0, 0.0, 1.6)),
            dtype=np.float64,
        )
        rotated = np.asarray(
            [
                Quaternion_RotateVector(quaternion, endpoint)
                for endpoint in body_endpoints
            ]
        )
        for vector, color, label in zip(
            rotated,
            ("#EF4444", "#10B981", "#3B82F6"),
            ("Xb", "Yb", "Zb"),
            strict=True,
        ):
            axis.quiver(
                0.0,
                0.0,
                0.0,
                vector[0],
                vector[1],
                vector[2],
                color=color,
                linewidth=1.25,
                arrow_length_ratio=0.13,
                label=label,
            )
            axis.text(
                vector[0] * 1.08,
                vector[1] * 1.08,
                vector[2] * 1.08,
                label,
                color=color,
            )
        for vector, label in zip(np.eye(3), ("E", "N", "U"), strict=True):
            axis.plot(
                [0.0, vector[0] * 0.72],
                [0.0, vector[1] * 0.72],
                [0.0, vector[2] * 0.72],
                color=foreground,
                linestyle=":",
                linewidth=0.8,
            )
            axis.text(
                vector[0] * 0.78,
                vector[1] * 0.78,
                vector[2] * 0.78,
                f"+{label}",
                color=foreground,
            )
        self._Axis3d_Equal(
            axis,
            np.vstack(
                (
                    rotated_vertices,
                    rotated,
                    np.zeros((1, 3), dtype=np.float64),
                )
            ),
        )
        axis.set_facecolor(background)
        axis.set_xlabel("E", color=foreground)
        axis.set_ylabel("N", color=foreground)
        axis.set_zlabel("U", color=foreground)
        axis.tick_params(colors=foreground)
        axis.set_title(_LABELS[language]["attitude"], color=foreground)
        axis.legend(facecolor=background, labelcolor=foreground, framealpha=0.78)

    def _FlightReplayGif_Write(
        self,
        dataset: FlightDataset,
        attitude: TimeSeries,
        position: TimeSeries,
        path: Path,
        language: ExportLanguage,
        theme: ExportTheme,
        context: TaskContext,
    ) -> None:
        self._Matplotlib_Configure()
        from matplotlib import pyplot as plt
        from PIL import Image

        attitude_values = np.asarray(attitude.values, dtype=np.float64)
        position_values = np.asarray(position.values, dtype=np.float64)
        if attitude_values.ndim != 2 or attitude_values.shape[1] != 4:
            raise ValueError("attitude_channel_must_be_wxyz")
        if position_values.ndim != 2 or position_values.shape[1] != 3:
            raise ValueError("position_channel_must_be_enu")
        attitude_valid = attitude.valid & np.all(np.isfinite(attitude_values), axis=1)
        position_valid = position.valid & np.all(np.isfinite(position_values), axis=1)
        attitude = TimeSeries(
            timestamp_us=attitude.timestamp_us[attitude_valid],
            values=attitude_values[attitude_valid],
            unit=attitude.unit,
            quantity=attitude.quantity,
            source=attitude.source,
            valid=np.ones(int(np.count_nonzero(attitude_valid)), dtype=np.bool_),
            columns=attitude.columns,
            metadata=attitude.metadata,
        )
        position = TimeSeries(
            timestamp_us=position.timestamp_us[position_valid],
            values=position_values[position_valid],
            unit=position.unit,
            quantity=position.quantity,
            source=position.source,
            valid=np.ones(int(np.count_nonzero(position_valid)), dtype=np.bool_),
            columns=position.columns,
            metadata=position.metadata,
        )
        if attitude.count == 0 or position.count == 0:
            raise ValueError("no_valid_attitude_or_position_samples")
        start = dataset.start_timestamp_us or max(
            int(attitude.timestamp_us[0]),
            int(position.timestamp_us[0]),
        )
        frame_timestamps = self._ReplayFrameTimestamps_Get(
            attitude,
            position,
            start,
            maximum_frames=60,
        )
        if frame_timestamps.size == 0:
            raise ValueError("no_common_post_start_attitude_and_position")
        landing = _Event_Timestamp(dataset, _EVENT_LANDING)
        if (
            landing is not None
            and landing > int(frame_timestamps[-1])
            and landing - int(attitude.timestamp_us[-1]) <= 100_000
            and landing - int(position.timestamp_us[-1]) <= 100_000
        ):
            if frame_timestamps.size < 60:
                frame_timestamps = np.append(frame_timestamps, np.uint64(landing))
            else:
                frame_timestamps[-1] = np.uint64(landing)
        if frame_timestamps.size > 1:
            durations = np.diff(frame_timestamps).astype(np.float64) * 1.0e-3
            durations_ms = np.clip(durations, 10.0, 655350.0).astype(int).tolist()
            durations_ms.append(durations_ms[-1])
        else:
            durations_ms = [100]
        background, foreground, _ = self._Plot_Configure(theme)
        labels = _LABELS[language]
        frames: list[Image.Image] = []
        try:
            for frame_number, raw_timestamp in enumerate(frame_timestamps):
                context.Cancel_RaiseIfRequested()
                timestamp_us = int(raw_timestamp)
                attitude_index = self._NearestIndex(attitude.timestamp_us, timestamp_us)
                figure = plt.figure(figsize=(10, 5), dpi=90)
                figure.patch.set_facecolor(background)
                attitude_axis = figure.add_subplot(121, projection="3d")
                trajectory_axis = figure.add_subplot(122, projection="3d")
                self._Attitude_AxisDraw(
                    attitude_axis,
                    np.asarray(attitude.values[attitude_index], dtype=np.float64),
                    language,
                    theme,
                )
                self._Trajectory_AxisDraw(
                    trajectory_axis,
                    dataset,
                    position,
                    language,
                    theme,
                    current_timestamp_us=timestamp_us,
                )
                trajectory_axis.set_title(labels["trajectory_panel"], color=foreground)
                elapsed = (timestamp_us - start) * 1.0e-6
                figure.suptitle(
                    f"{labels['time']}: {elapsed:.3f} s",
                    color=foreground,
                    fontsize=12,
                )
                figure.tight_layout(rect=(0.0, 0.0, 1.0, 0.94))
                buffer = io.BytesIO()
                figure.savefig(buffer, format="png", facecolor=background)
                plt.close(figure)
                buffer.seek(0)
                with Image.open(buffer) as image:
                    frames.append(
                        image.convert("P", palette=Image.Palette.ADAPTIVE).copy()
                    )
                context.Progress_Report(
                    0.72 + 0.27 * (frame_number + 1) / len(frame_timestamps),
                    "export.gif",
                )
            frames[0].save(
                path,
                save_all=True,
                append_images=frames[1:],
                duration=durations_ms,
                loop=0,
                disposal=2,
            )
        finally:
            for frame in frames:
                frame.close()
