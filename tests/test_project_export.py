from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image

from silverstar_flp.core.dataset import TimeSeries
from silverstar_flp.core.project import Project_Load, Project_Save, ProjectDocument
from silverstar_flp.core.visual_semantics import (
    TRAJECTORY_DEPLOY_COLOR,
    TRAJECTORY_POST_DEPLOY_COLOR,
    TRAJECTORY_PRE_DEPLOY_COLOR,
    RocketFaceColors_Get,
)
from silverstar_flp.export.plot_metadata import ChannelDisplayMetadata_Get
from silverstar_flp.export.service import (
    ExportLanguage,
    ExportOptions,
    ExportTheme,
    FlightExporter,
    _PlotColor_Get,
)
from silverstar_flp.plugins.log_parsers.sslog0.plugin import Sslog0ParserPlugin
from tests.sslog_synthetic import AnalysisFlight_Build, StationaryFlight_Build


def test_project_contains_references_only_and_raw_log_remains_unchanged(tmp_path: Path) -> None:
    log_path = StationaryFlight_Build(tmp_path / "SYNTHETIC_project_source.BIN")
    before = hashlib.sha256(log_path.read_bytes()).hexdigest()
    project_path = tmp_path / "flight.ssflp"
    document = ProjectDocument(project_path=project_path)
    document.LogReference_Add(log_path)
    document.notes = "synthetic fixture"
    Project_Save(document, project_path)
    loaded = Project_Load(project_path)
    assert loaded.LogPaths_Resolve() == (log_path.resolve(),)
    project_text = project_path.read_text(encoding="utf-8")
    assert "SSLOG0" not in project_text
    assert hashlib.sha256(log_path.read_bytes()).hexdigest() == before


def test_project_save_as_keeps_log_reference_resolvable(tmp_path: Path) -> None:
    source_folder = tmp_path / "source"
    source_folder.mkdir()
    log_path = StationaryFlight_Build(source_folder / "SYNTHETIC_save_as_source.BIN")
    original_path = source_folder / "flight.ssflp"
    document = ProjectDocument(project_path=original_path)
    document.LogReference_Add(log_path)
    Project_Save(document, original_path)

    loaded = Project_Load(original_path)
    saved_as_path = tmp_path / "copy" / "flight_copy.ssflp"
    Project_Save(loaded, saved_as_path)

    saved_as = Project_Load(saved_as_path)
    assert saved_as.LogPaths_Resolve() == (log_path.resolve(),)
    assert Project_Load(original_path).LogPaths_Resolve() == (log_path.resolve(),)


def test_export_keeps_independent_channel_timestamps_and_language_suffix(
    tmp_path: Path,
) -> None:
    log_path = StationaryFlight_Build(tmp_path / "SYNTHETIC_export_source.BIN")
    dataset = Sslog0ParserPlugin().parse(log_path)
    before = hashlib.sha256(log_path.read_bytes()).hexdigest()
    manifest = FlightExporter().export(
        dataset,
        tmp_path / "exported",
        options=ExportOptions(
            language=ExportLanguage.EN,
            include_plots=False,
            include_trajectory_3d=False,
            include_attitude_gif=False,
        ),
    )
    assert manifest.files
    assert all("_EN" in path.name or "CSV_EN" in str(path.parent) for path in manifest.files)
    csv_files = [path for path in manifest.files if path.suffix.lower() == ".csv"]
    assert csv_files
    inertial_csv = next(path for path in csv_files if "inertial.increment.dt" in path.name)
    rows = inertial_csv.read_text(encoding="utf-8-sig").splitlines()
    assert "timestamp_us" in rows[1]
    assert len(rows) == 10  # metadata + header + eight real-rate samples
    assert hashlib.sha256(log_path.read_bytes()).hexdigest() == before


def test_follow_ui_exports_standard_plot_set_segmented_trajectory_and_combined_gif(
    tmp_path: Path,
) -> None:
    dataset = Sslog0ParserPlugin().parse(
        AnalysisFlight_Build(tmp_path / "SYNTHETIC_export_analysis.BIN")
    )
    manifest = FlightExporter().export(
        dataset,
        tmp_path / "analysis_export",
        options=ExportOptions(
            language=ExportLanguage.FOLLOW_UI,
            ui_language="zh_CN",
            theme=ExportTheme.DARK,
            include_overview=False,
            include_diagnostics=False,
            include_events=False,
            include_csv=False,
            include_plots=True,
            include_trajectory_3d=True,
            include_attitude_gif=True,
        ),
    )
    assert manifest.language == ExportLanguage.ZH
    assert manifest.theme == ExportTheme.DARK
    assert not manifest.failures
    names = {path.name for path in manifest.files}
    assert {
        "Flight_Velocity_ENU_ZH.png",
        "Flight_Position_ENU_ZH.png",
        "Flight_Acceleration_XYZ_ZH.png",
        "Flight_Angular_Rate_XYZ_ZH.png",
        "Flight_Attitude_ZH.png",
        "State_Covariance_ZH.png",
        "State_Innovation_ZH.png",
        "State_NIS_ZH.png",
        "State_Measurement_Update_ZH.png",
        "Trajectory_3D_ZH.png",
        "Flight_Replay_ZH.gif",
        "Export_Manifest_ZH.json",
    } <= names
    gif_path = next(path for path in manifest.files if path.name == "Flight_Replay_ZH.gif")
    with Image.open(gif_path) as image:
        assert 1 < image.n_frames <= 60
    manifest_payload = json.loads(
        (tmp_path / "analysis_export" / "Export_Manifest_ZH.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest_payload["language"] == "zh_CN"
    assert manifest_payload["theme"] == "dark"
    assert manifest_payload["failures"] == []

    position = dataset.Series_Get("kf6.recorded.navigation.position_enu")
    assert position is not None
    deploy = next(
        record.timestamp_us
        for record in dataset.Records_Get("EVENT")
        if int(record.payload["event_id"]) == 0x29
    )
    pre, post = FlightExporter._TrajectorySegments_Get(position, deploy)
    assert pre.size > 0
    assert post.size > 0
    landing = next(
        record.timestamp_us
        for record in dataset.Records_Get("EVENT")
        if int(record.payload["event_id"]) == 0x2A
    )
    assert FlightExporter._Position_At(position, landing) is None
    assert np.allclose(
        FlightExporter._Position_NearEvent(position, landing),
        position.values[-1],
    )


def test_plot_metadata_has_language_specific_titles(tmp_path: Path) -> None:
    dataset = Sslog0ParserPlugin().parse(
        AnalysisFlight_Build(tmp_path / "SYNTHETIC_plot_metadata.BIN")
    )
    series = dataset.Series_Get("kf6.recorded.navigation.velocity_enu")
    assert series is not None
    metadata = ChannelDisplayMetadata_Get("navigation.velocity_enu", series)
    assert metadata.Title_Get("zh_CN") == "飞行速度（ENU）"
    assert metadata.Title_Get("en_US") == "Flight Velocity (ENU)"
    assert "Flight" not in metadata.Title_Get("zh_CN")
    assert "飞行" not in metadata.Title_Get("en_US")
    low_level = dataset.Series_Get("inertial.increment.dt")
    assert low_level is not None
    generic = ChannelDisplayMetadata_Get("inertial.increment.dt", low_level)
    assert generic.Title_Get("zh_CN") == "时间（数据通道）"
    assert generic.Title_Get("en_US") == "Time (Data Channel)"
    assert "inertial" not in generic.Title_Get("zh_CN")


def test_export_3d_uses_unique_colors_rocket_mesh_and_mission_relative_points(
    tmp_path: Path,
) -> None:
    colors = [_PlotColor_Get(index) for index in range(32)]
    assert len(colors) == len(set(colors))

    dataset = Sslog0ParserPlugin().parse(
        AnalysisFlight_Build(tmp_path / "SYNTHETIC_export_3d_rules.BIN")
    )
    position = dataset.Series_Get("kf6.recorded.navigation.position_enu")
    assert position is not None
    raw_before = np.asarray(position.values).copy()
    start = dataset.start_timestamp_us
    assert start is not None
    origin = FlightExporter._TrajectoryOrigin_Get(position, start)

    FlightExporter._Matplotlib_Configure()
    from matplotlib import pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    exporter = FlightExporter()
    trajectory_figure = plt.figure()
    trajectory_axis = trajectory_figure.add_subplot(111, projection="3d")
    exporter._Trajectory_AxisDraw(
        trajectory_axis,
        dataset,
        position,
        ExportLanguage.EN,
        ExportTheme.LIGHT,
    )
    labels = {artist.get_label() for artist in trajectory_axis.collections}
    assert "Mission Start" not in labels
    assert {"Deploy", "Landing", "Current Position"} <= labels
    deploy_collection = next(
        artist for artist in trajectory_axis.collections if artist.get_label() == "Deploy"
    )
    current_collection = next(
        artist
        for artist in trajectory_axis.collections
        if artist.get_label() == "Current Position"
    )
    from matplotlib.colors import to_rgba

    assert np.allclose(deploy_collection.get_facecolor()[0], to_rgba(TRAJECTORY_DEPLOY_COLOR))
    assert np.allclose(deploy_collection.get_edgecolor()[0], to_rgba(TRAJECTORY_DEPLOY_COLOR))
    assert np.allclose(
        current_collection.get_facecolor()[0],
        to_rgba(TRAJECTORY_POST_DEPLOY_COLOR),
    )
    assert trajectory_axis.lines[0].get_color() == TRAJECTORY_PRE_DEPLOY_COLOR
    assert trajectory_axis.lines[1].get_color() == TRAJECTORY_POST_DEPLOY_COLOR
    assert not trajectory_axis.texts
    first_pre = np.asarray(trajectory_axis.lines[0].get_data_3d()).T[0]
    assert np.allclose(first_pre, np.zeros(3), atol=1.0e-6)
    post_start = np.flatnonzero(
        position.valid & (position.timestamp_us >= np.uint64(start))
    )
    assert post_start.size
    assert np.allclose(origin, position.values[post_start[0]])
    assert np.array_equal(position.values, raw_before)
    plt.close(trajectory_figure)

    attitude_figure = plt.figure()
    attitude_axis = attitude_figure.add_subplot(111, projection="3d")
    exporter._Attitude_AxisDraw(
        attitude_axis,
        np.asarray((1.0, 0.0, 0.0, 0.0)),
        ExportLanguage.EN,
        ExportTheme.DARK,
    )
    rocket_collection = next(
        collection
        for collection in attitude_axis.collections
        if isinstance(collection, Poly3DCollection)
    )
    actual_face_colors = {
        tuple(np.round(color, 6)) for color in rocket_collection.get_facecolor()
    }
    expected_face_colors = {
        tuple(np.round(to_rgba(color), 6)) for color in RocketFaceColors_Get("dark")
    }
    assert actual_face_colors == expected_face_colors
    plt.close(attitude_figure)


def test_export_records_individual_failure_and_continues(
    tmp_path: Path,
    monkeypatch,
) -> None:
    dataset = Sslog0ParserPlugin().parse(
        StationaryFlight_Build(tmp_path / "SYNTHETIC_partial_export.BIN")
    )
    exporter = FlightExporter()
    original = exporter._SeriesCsv_Write
    selected = (
        "inertial.increment.dt",
        "pure_ins.recorded.navigation.position_enu",
    )

    def selectively_fail(dataset_arg, channel_id, series, path):
        if channel_id == selected[0]:
            raise RuntimeError("intentional_csv_failure")
        original(dataset_arg, channel_id, series, path)

    monkeypatch.setattr(exporter, "_SeriesCsv_Write", selectively_fail)
    manifest = exporter.export(
        dataset,
        tmp_path / "partial_export",
        options=ExportOptions(
            language=ExportLanguage.EN,
            include_overview=False,
            include_diagnostics=False,
            include_events=False,
            include_csv=True,
            include_plots=False,
            include_trajectory_3d=False,
            include_attitude_gif=False,
            selected_channels=selected,
        ),
    )
    assert len(manifest.failures) == 1
    assert manifest.failures[0].item == f"csv:{selected[0]}"
    assert any(selected[1] in path.name for path in manifest.files)
    payload = json.loads(
        (tmp_path / "partial_export" / "Export_Manifest_EN.json").read_text(
            encoding="utf-8"
        )
    )
    assert payload["failures"][0]["item"] == f"csv:{selected[0]}"


def test_gif_frame_targets_are_uniform_in_mission_time_and_capped_at_60() -> None:
    timestamps = np.asarray(
        [1_000_000 + index * index * 1_000 for index in range(100)],
        dtype=np.uint64,
    )
    attitude = TimeSeries(
        timestamp_us=timestamps,
        values=np.tile(np.asarray((1.0, 0.0, 0.0, 0.0)), (timestamps.size, 1)),
        unit="1",
        quantity="quaternion",
        source="synthetic",
        valid=np.ones(timestamps.size, dtype=np.bool_),
        columns=("W", "X", "Y", "Z"),
    )
    position = TimeSeries(
        timestamp_us=timestamps,
        values=np.column_stack(
            (
                np.linspace(0.0, 1.0, timestamps.size),
                np.linspace(0.0, 2.0, timestamps.size),
                np.linspace(0.0, 3.0, timestamps.size),
            )
        ),
        unit="m",
        quantity="position",
        source="synthetic",
        valid=np.ones(timestamps.size, dtype=np.bool_),
        columns=("E", "N", "U"),
    )
    targets = FlightExporter._ReplayFrameTimestamps_Get(
        attitude,
        position,
        1_000_000,
    )
    assert targets.size == 60
    assert targets[0] == timestamps[0]
    assert targets[-1] == timestamps[-1]
    intervals = np.diff(targets.astype(np.int64))
    assert int(intervals.max() - intervals.min()) <= 1
