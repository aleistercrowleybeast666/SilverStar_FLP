from __future__ import annotations

import colorsys
from collections.abc import Iterable

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QVector3D
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from silverstar_flp.core.analysis_source import (
    AnalysisSourceKind,
    ChannelResolver,
    ReplayResultStore,
)
from silverstar_flp.core.dataset import FlightDataset, TimeSeries
from silverstar_flp.core.i18n import Translator
from silverstar_flp.core.math import Quaternion_RotateVector, Quaternion_ToEulerEnuDeg
from silverstar_flp.core.visual_semantics import (
    TRAJECTORY_DEPLOY_COLOR,
    TRAJECTORY_LANDING_COLOR,
    TRAJECTORY_POST_DEPLOY_COLOR,
    TRAJECTORY_PRE_DEPLOY_COLOR,
    RocketFaceColors_Get,
    TrajectoryMarkerWorldSizes_Get,
    TrajectoryPhaseColor_Get,
)
from silverstar_flp.ui.theme import Plot_Colors
from silverstar_flp.ui.widgets import StandardComboBox

try:
    import pyqtgraph.opengl as gl
except Exception:  # OpenGL is optional; all 2D analysis remains available.
    gl = None


if gl is not None:

    class CameraLockGLViewWidget(gl.GLViewWidget):
        """3D view that can lock mouse rotation/panning while retaining wheel zoom."""

        def __init__(self, parent: QWidget | None = None) -> None:
            super().__init__(parent)
            self._camera_locked = True

        def CameraLocked_Set(self, locked: bool) -> None:
            self._camera_locked = bool(locked)

        def mouseMoveEvent(self, event: object) -> None:
            if self._camera_locked:
                event.accept()
                return
            super().mouseMoveEvent(event)


_ROCKET_BASE_VERTICES = np.asarray(
    (
        (-0.35, -0.35, 0.0),
        (0.35, -0.35, 0.0),
        (0.35, 0.35, 0.0),
        (-0.35, 0.35, 0.0),
        (0.0, 0.0, 2.2),
    ),
    dtype=np.float32,
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


def _RocketVertices_Rotate(quaternion: np.ndarray) -> np.ndarray:
    return np.asarray(
        [Quaternion_RotateVector(quaternion, vertex) for vertex in _ROCKET_BASE_VERTICES],
        dtype=np.float32,
    )


def _RocketFaceColors_Get(theme: str) -> np.ndarray:
    return np.asarray(
        [QColor(color).getRgbF() for color in RocketFaceColors_Get(theme)],
        dtype=np.float32,
    )


def _RocketEdgeColor_Get(theme: str) -> tuple[float, float, float, float]:
    color = QColor("#E5E7EB" if theme == "dark" else "#334155")
    return color.getRgbF()


_TRACE_COLORS = (
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


class TraceColorAllocator:
    """Allocate stable, non-repeating colors for one complete plot refresh."""

    def __init__(self) -> None:
        self._index = 0

    def Color_Next(self) -> str:
        index = self._index
        self._index += 1
        if index < len(_TRACE_COLORS):
            return _TRACE_COLORS[index]
        hue = (0.61803398875 * index + 0.13) % 1.0
        red, green, blue = colorsys.hsv_to_rgb(hue, 0.68, 0.88)
        return f"#{round(red * 255):02X}{round(green * 255):02X}{round(blue * 255):02X}"


def _Plot_Prepare(plot: pg.PlotWidget, theme: str) -> None:
    background, foreground = Plot_Colors(theme)
    plot.setBackground(background)
    plot.getAxis("bottom").setTextPen(foreground)
    plot.getAxis("left").setTextPen(foreground)
    plot.getAxis("bottom").setPen(foreground)
    plot.getAxis("left").setPen(foreground)
    plot.showGrid(x=True, y=True, alpha=0.2)


def _Series_Plot(
    plot: pg.PlotWidget,
    series: TimeSeries | None,
    start_timestamp_us: int,
    *,
    colors: TraceColorAllocator,
    prefix: str = "",
    width: float = 1.4,
    reference: bool = False,
) -> None:
    if series is None or series.count == 0:
        return
    selected = np.flatnonzero(series.timestamp_us >= np.uint64(start_timestamp_us))
    if selected.size == 0:
        return
    selected = selected[:: max(1, selected.size // 6000)]
    time = (
        series.timestamp_us[selected].astype(np.float64) - float(start_timestamp_us)
    ) * 1.0e-6
    values = np.asarray(series.values, dtype=np.float64)[selected].copy()
    valid = np.asarray(series.valid, dtype=np.bool_)[selected]
    style = Qt.PenStyle.DashLine if reference else Qt.PenStyle.SolidLine
    if values.ndim == 1:
        values[~valid] = np.nan
        plot.plot(
            time,
            values,
            pen=pg.mkPen(colors.Color_Next(), width=width, style=style),
            name=prefix or series.quantity,
        )
        return
    values[~valid, :] = np.nan
    for index in range(values.shape[1]):
        column = series.columns[index] if series.columns else str(index)
        plot.plot(
            time,
            values[:, index],
            pen=pg.mkPen(colors.Color_Next(), width=width, style=style),
            name=f"{prefix}{column}",
        )


def _Plot_Reset(plots: Iterable[pg.PlotWidget]) -> None:
    for plot in plots:
        plot.clear()
        plot.addLegend()


def _PlotViews_Reset(plots: Iterable[pg.PlotWidget]) -> None:
    for plot in plots:
        view_box = plot.getViewBox()
        view_box.enableAutoRange(axis=pg.ViewBox.XYAxes, enable=True)
        view_box.updateAutoRange()
        legend = plot.getPlotItem().legend
        if legend is not None:
            legend.anchor(itemPos=(0, 0), parentPos=(0, 0), offset=(30, 30))


def _EulerSeries_Create(series: TimeSeries) -> TimeSeries:
    values = np.asarray(series.values, dtype=np.float64)
    euler = np.full((series.count, 3), np.nan, dtype=np.float64)
    for index in np.flatnonzero(series.valid):
        try:
            euler[index] = Quaternion_ToEulerEnuDeg(values[index])
        except ValueError:
            continue
    return TimeSeries(
        timestamp_us=series.timestamp_us,
        values=euler,
        unit="deg",
        quantity="euler",
        source=series.source,
        valid=series.valid & np.all(np.isfinite(euler), axis=1),
        columns=("Roll", "Pitch", "Yaw"),
        metadata={"display_only": True, "quaternion_authoritative": True},
    )


def _Source_Label(
    translator: Translator,
    resolver: ChannelResolver,
    source_id: str,
) -> str:
    source = resolver.Source_Get(source_id)
    if source.kind == AnalysisSourceKind.RECORDED:
        return translator.Text_Get("status.recorded")
    entry = resolver.store.SourceEntry_Get(source.source_id)
    if entry is None:
        return translator.Text_Get("status.recorded")
    mode_code = (
        "status.what_if"
        if entry.kind == AnalysisSourceKind.WHAT_IF
        else "status.recomputed"
    )
    return f"{entry.algorithm_name} · {translator.Text_Get(mode_code)} #{entry.run_index}"


def _RecordedSolution_Label(translator: Translator, solution_id: str) -> str:
    code = {
        "pure_ins": "solution.recorded_pure_ins",
        "kf6": "solution.recorded_kf6",
    }.get(solution_id, "status.recorded")
    return translator.Text_Get(code)


def _Event_Timestamp(dataset: FlightDataset, event_id: int) -> int | None:
    for record in sorted(dataset.Records_Get("EVENT"), key=lambda item: item.timestamp_us):
        if int(record.payload["event_id"]) == event_id:
            return record.timestamp_us
    return None


def _NearestIndex(timestamps: np.ndarray, timestamp_us: int) -> int:
    right = int(np.searchsorted(timestamps, timestamp_us, side="left"))
    if right <= 0:
        return 0
    if right >= timestamps.size:
        return timestamps.size - 1
    left = right - 1
    return (
        left
        if timestamp_us - int(timestamps[left]) <= int(timestamps[right]) - timestamp_us
        else right
    )


def _Position_At(series: TimeSeries, timestamp_us: int) -> np.ndarray | None:
    values = np.asarray(series.values, dtype=np.float64)
    valid = series.valid & np.all(np.isfinite(values), axis=1)
    timestamps = series.timestamp_us[valid].astype(np.float64)
    points = values[valid]
    if (
        timestamps.size == 0
        or timestamp_us < timestamps[0]
        or timestamp_us > timestamps[-1]
    ):
        return None
    return np.asarray(
        [np.interp(float(timestamp_us), timestamps, points[:, axis]) for axis in range(3)],
        dtype=np.float32,
    )


def _Position_NearEvent(series: TimeSeries, timestamp_us: int) -> np.ndarray | None:
    interpolated = _Position_At(series, timestamp_us)
    if interpolated is not None:
        return interpolated
    values = np.asarray(series.values, dtype=np.float64)
    valid = series.valid & np.all(np.isfinite(values), axis=1)
    timestamps = series.timestamp_us[valid]
    points = values[valid]
    if timestamps.size == 0:
        return None
    intervals = np.diff(timestamps.astype(np.int64))
    typical_interval = float(np.median(intervals)) if intervals.size else 0.0
    tolerance_us = max(int(typical_interval * 5.0), 100_000)
    index = _NearestIndex(timestamps, timestamp_us)
    if abs(int(timestamps[index]) - timestamp_us) > tolerance_us:
        return None
    return np.asarray(points[index], dtype=np.float32)


def _TrajectoryOrigin_Get(series: TimeSeries, start_timestamp_us: int) -> np.ndarray:
    interpolated = _Position_At(series, start_timestamp_us)
    if interpolated is not None:
        return interpolated
    values = np.asarray(series.values, dtype=np.float64)
    valid = series.valid & np.all(np.isfinite(values), axis=1)
    post_start = np.flatnonzero(
        valid & (series.timestamp_us >= np.uint64(max(start_timestamp_us, 0)))
    )
    if post_start.size:
        return np.asarray(values[post_start[0]], dtype=np.float32)
    available = np.flatnonzero(valid)
    if available.size:
        return np.asarray(values[available[0]], dtype=np.float32)
    return np.zeros(3, dtype=np.float32)


class FlightPage(QWidget):
    def __init__(self, translator: Translator) -> None:
        super().__init__()
        self._translator = translator
        self._theme = "light"
        self._dataset: FlightDataset | None = None
        self._resolver: ChannelResolver | None = None
        self._start_timestamp_us = 0
        self._end_timestamp_us = 0
        self._playback_time_us = 0
        self._position: TimeSeries | None = None
        self._attitude: TimeSeries | None = None
        self._deploy_timestamp_us: int | None = None
        self._landing_timestamp_us: int | None = None
        self._trajectory_origin = np.zeros(3, dtype=np.float32)
        self._trajectory_camera_center = np.zeros(3, dtype=np.float32)
        self._trajectory_camera_distance = 40.0
        self._trajectory_marker_sizes = (0.035, 0.028, 0.028)

        layout = QVBoxLayout(self)
        source_row = QHBoxLayout()
        self.source_label = QLabel()
        self.source_value_label = QLabel("—")
        self.source_value_label.setObjectName("muted")
        self.source_detail_label = QLabel()
        self.source_detail_label.setObjectName("muted")
        self.source_detail_label.setWordWrap(True)
        source_row.addWidget(self.source_label)
        source_row.addWidget(self.source_value_label, 1)
        source_row.addWidget(self.source_detail_label, 2)
        self.reset_charts_button = QPushButton()
        self.reset_charts_button.clicked.connect(self._ChartViews_Reset)
        source_row.addWidget(self.reset_charts_button)
        layout.addLayout(source_row)

        self.tabs = QTabWidget()
        self.velocity_plot = self._Plot_Create()
        self.position_plot = self._Plot_Create()
        self.acceleration_plot = self._Plot_Create()
        self.angular_rate_plot = self._Plot_Create()
        self.attitude_widget = self._AttitudeWidget_Create()
        self.replay_3d_widget = self._Replay3d_Create()
        for widget in (
            self.velocity_plot,
            self.position_plot,
            self.acceleration_plot,
            self.angular_rate_plot,
            self.attitude_widget,
            self.replay_3d_widget,
        ):
            self.tabs.addTab(widget, "")
        layout.addWidget(self.tabs)

        self.playback_timer = QTimer(self)
        self.playback_timer.setInterval(40)
        self.playback_timer.timeout.connect(self._Playback_Tick)
        self.Language_Apply(translator)

    def _Plot_Create(self) -> pg.PlotWidget:
        plot = pg.PlotWidget()
        plot.addLegend()
        _Plot_Prepare(plot, self._theme)
        return plot

    def _ChartViews_Reset(self) -> None:
        _PlotViews_Reset(
            (
                self.velocity_plot,
                self.position_plot,
                self.acceleration_plot,
                self.angular_rate_plot,
                self.quaternion_plot,
                self.euler_plot,
            )
        )

    def _AttitudeWidget_Create(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        self.attitude_authority_label = QLabel()
        self.attitude_authority_label.setObjectName("muted")
        self.attitude_authority_label.setWordWrap(True)
        layout.addWidget(self.attitude_authority_label)
        splitter = QSplitter(Qt.Orientation.Vertical)
        self.quaternion_plot = self._Plot_Create()
        self.euler_plot = self._Plot_Create()
        splitter.addWidget(self.quaternion_plot)
        splitter.addWidget(self.euler_plot)
        splitter.setSizes((320, 320))
        layout.addWidget(splitter, 1)
        return widget

    def _Replay3d_Create(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        self.replay_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.replay_splitter.setChildrenCollapsible(False)
        self.attitude_3d_group = QGroupBox()
        attitude_layout = QVBoxLayout(self.attitude_3d_group)
        self.trajectory_3d_group = QGroupBox()
        trajectory_layout = QVBoxLayout(self.trajectory_3d_group)
        if gl is None:
            self.attitude_view = None
            self.trajectory_view = None
            self.rocket_mesh = None
            self.opengl_unavailable_label = QLabel()
            self.opengl_unavailable_label.setWordWrap(True)
            attitude_layout.addWidget(self.opengl_unavailable_label)
            trajectory_layout.addWidget(QLabel("—"))
            self._attitude_body_items = []
            self._world_items = []
            self._gl_text_items = []
        else:
            self.attitude_view = CameraLockGLViewWidget()
            self.attitude_view.setMinimumHeight(400)
            self.attitude_view.setCameraPosition(
                pos=QVector3D(0.0, 0.0, 0.7),
                distance=5.5,
                elevation=18.0,
                azimuth=-50.0,
            )
            self.attitude_grid = gl.GLGridItem()
            self.attitude_grid.setSize(4, 4)
            self.attitude_grid.setSpacing(0.5, 0.5)
            self.attitude_view.addItem(self.attitude_grid)
            self._attitude_world_items = [
                gl.GLLinePlotItem(width=2.0, antialias=True) for _ in range(3)
            ]
            self._attitude_body_items = [
                gl.GLLinePlotItem(width=3.0, antialias=True) for _ in range(3)
            ]
            for item in (*self._attitude_world_items, *self._attitude_body_items):
                self.attitude_view.addItem(item)
            rocket_data = gl.MeshData(
                vertexes=_ROCKET_BASE_VERTICES,
                faces=_ROCKET_FACES,
                faceColors=_RocketFaceColors_Get(self._theme),
            )
            self.rocket_mesh = gl.GLMeshItem(
                meshdata=rocket_data,
                smooth=False,
                computeNormals=False,
                drawEdges=True,
                edgeColor=_RocketEdgeColor_Get(self._theme),
                shader=None,
            )
            self.attitude_view.addItem(self.rocket_mesh)
            self._attitude_text_items = [
                gl.GLTextItem(pos=(0, 0, 0), text=text)
                for text in ("+E", "+N", "+U", "Xb", "Yb", "Zb")
            ]
            for item in self._attitude_text_items:
                self.attitude_view.addItem(item)
            attitude_layout.addWidget(self.attitude_view)

            self.trajectory_view = CameraLockGLViewWidget()
            self.trajectory_view.setMinimumHeight(400)
            self.trajectory_view.setCameraPosition(
                pos=QVector3D(0.0, 0.0, 0.0),
                distance=40.0,
                elevation=24.0,
                azimuth=-52.0,
            )
            self.trajectory_grid = gl.GLGridItem()
            self.trajectory_view.addItem(self.trajectory_grid)
            self._trajectory_world_items = [
                gl.GLLinePlotItem(width=2.0, antialias=True) for _ in range(3)
            ]
            self.pre_deploy_line = gl.GLLinePlotItem(width=3.0, antialias=True)
            self.post_deploy_line = gl.GLLinePlotItem(width=3.0, antialias=True)
            self.deploy_marker = gl.GLScatterPlotItem(size=0.035, pxMode=False)
            self.landing_marker = gl.GLScatterPlotItem(size=0.028, pxMode=False)
            self.current_marker = gl.GLScatterPlotItem(size=0.028, pxMode=False)
            self.current_marker.setDepthValue(28)
            self.landing_marker.setDepthValue(29)
            self.deploy_marker.setDepthValue(30)
            for item in (
                *self._trajectory_world_items,
                self.pre_deploy_line,
                self.post_deploy_line,
                self.deploy_marker,
                self.landing_marker,
                self.current_marker,
            ):
                self.trajectory_view.addItem(item)
            self._trajectory_text_items = [
                gl.GLTextItem(pos=(0, 0, 0), text=text)
                for text in ("E", "N", "U")
            ]
            for item in self._trajectory_text_items:
                self.trajectory_view.addItem(item)
            trajectory_layout.addWidget(self.trajectory_view)
            self._world_items = [
                *self._attitude_world_items,
                *self._trajectory_world_items,
            ]
            self._gl_text_items = [
                *self._attitude_text_items,
                *self._trajectory_text_items,
            ]
        self.attitude_axes_legend = QLabel()
        self.attitude_axes_legend.setObjectName("muted")
        self.attitude_axes_legend.setWordWrap(True)
        attitude_layout.addWidget(self.attitude_axes_legend)
        self.trajectory_axes_legend = QLabel()
        self.trajectory_axes_legend.setObjectName("muted")
        self.trajectory_axes_legend.setWordWrap(True)
        trajectory_layout.addWidget(self.trajectory_axes_legend)
        self.replay_splitter.addWidget(self.attitude_3d_group)
        self.replay_splitter.addWidget(self.trajectory_3d_group)
        self.replay_splitter.setStretchFactor(0, 1)
        self.replay_splitter.setStretchFactor(1, 1)
        self.replay_splitter.setSizes((650, 650))
        layout.addWidget(self.replay_splitter, 1)

        camera_controls = QHBoxLayout()
        self.camera_lock_button = QPushButton()
        self.camera_lock_button.setCheckable(True)
        self.camera_lock_button.toggled.connect(self._CameraLock_Toggled)
        self.reset_camera_button = QPushButton()
        self.reset_camera_button.clicked.connect(self._Cameras_Reset)
        self.camera_lock_button.setEnabled(gl is not None)
        self.reset_camera_button.setEnabled(gl is not None)
        camera_controls.addWidget(self.camera_lock_button)
        camera_controls.addWidget(self.reset_camera_button)
        camera_controls.addStretch(1)
        layout.addLayout(camera_controls)

        controls = QHBoxLayout()
        self.play_button = QPushButton()
        self.play_button.setObjectName("primaryButton")
        self.play_button.clicked.connect(self._Playback_Toggle)
        self.playback_slider = QSlider(Qt.Orientation.Horizontal)
        self.playback_slider.setRange(0, 10000)
        self.playback_slider.valueChanged.connect(self._ThreeD_Refresh)
        self.playback_speed_label = QLabel()
        self.playback_speed_combo = StandardComboBox()
        for value in (0.5, 1.0, 2.0, 4.0):
            self.playback_speed_combo.addItem(f"{value:g}×", value)
        self.playback_speed_combo.setCurrentIndex(1)
        self.playback_time_label = QLabel("—")
        self.playback_time_label.setMinimumWidth(190)
        controls.addWidget(self.play_button)
        controls.addWidget(self.playback_slider, 1)
        controls.addWidget(self.playback_speed_label)
        controls.addWidget(self.playback_speed_combo)
        controls.addWidget(self.playback_time_label)
        layout.addLayout(controls)
        return widget

    def Dataset_Set(
        self,
        dataset: FlightDataset,
        resolver: ChannelResolver | None = None,
    ) -> None:
        self._dataset = dataset
        self._resolver = resolver or ChannelResolver(dataset, ReplayResultStore())
        self._Plots_Refresh()

    def _Plots_Refresh(self, *, reset_camera: bool = True) -> None:
        if self._dataset is None or self._resolver is None:
            return
        source_id = self._resolver.store.ActiveSource_Get().source_id
        source = self._resolver.Source_Get(source_id)
        self.source_value_label.setText(
            _Source_Label(self._translator, self._resolver, source_id)
        )
        start = self._dataset.start_timestamp_us
        if start is None:
            start = self._dataset.diagnostics.first_timestamp_us or 0
            self.source_detail_label.setText(
                self._translator.Text_Get("flight.start_fallback")
            )
        else:
            self.source_detail_label.setText(
                self._translator.Text_Get("flight.start_crop", timestamp=start)
            )
        self._start_timestamp_us = start
        _Plot_Reset(
            (
                self.velocity_plot,
                self.position_plot,
                self.acceleration_plot,
                self.angular_rate_plot,
                self.quaternion_plot,
                self.euler_plot,
            )
        )
        color_allocators = {
            plot: TraceColorAllocator()
            for plot in (
                self.velocity_plot,
                self.position_plot,
                self.acceleration_plot,
                self.angular_rate_plot,
                self.quaternion_plot,
                self.euler_plot,
            )
        }
        velocity = self._resolver.Series_Get("navigation.velocity_enu", source_id)
        position = self._resolver.Series_Get("navigation.position_enu", source_id)
        attitude = self._resolver.Series_Get("attitude.q_nb", source_id)
        if source.kind == AnalysisSourceKind.RECORDED:
            for channel_id, plot in (
                ("navigation.velocity_enu", self.velocity_plot),
                ("navigation.position_enu", self.position_plot),
            ):
                for layer in self._resolver.RecordedSolutionLayers_Get(channel_id):
                    _Series_Plot(
                        plot,
                        layer.series,
                        start,
                        colors=color_allocators[plot],
                        prefix=f"{_RecordedSolution_Label(self._translator, layer.solution_id)} · ",
                        width=1.7,
                    )
        else:
            active_prefix = f"{_Source_Label(self._translator, self._resolver, source_id)} · "
            _Series_Plot(
                self.velocity_plot,
                velocity,
                start,
                colors=color_allocators[self.velocity_plot],
                prefix=active_prefix,
                width=1.9,
            )
            _Series_Plot(
                self.position_plot,
                position,
                start,
                colors=color_allocators[self.position_plot],
                prefix=active_prefix,
                width=1.9,
            )
            for channel_id, plot in (
                ("navigation.velocity_enu", self.velocity_plot),
                ("navigation.position_enu", self.position_plot),
            ):
                for layer in self._resolver.RecordedSolutionLayers_Get(channel_id):
                    _Series_Plot(
                        plot,
                        layer.series,
                        start,
                        colors=color_allocators[plot],
                        prefix=f"{_RecordedSolution_Label(self._translator, layer.solution_id)} · ",
                        reference=True,
                    )
        attitude_prefix = (
            f"{self._translator.Text_Get('status.recorded')} · "
            if source.kind == AnalysisSourceKind.RECORDED
            else f"{_Source_Label(self._translator, self._resolver, source_id)} · "
        )
        _Series_Plot(
            self.quaternion_plot,
            attitude,
            start,
            colors=color_allocators[self.quaternion_plot],
            prefix=attitude_prefix,
            width=1.7,
        )
        if attitude is not None:
            _Series_Plot(
                self.euler_plot,
                _EulerSeries_Create(attitude),
                start,
                colors=color_allocators[self.euler_plot],
                prefix=attitude_prefix,
                width=1.7,
            )
        if source.kind != AnalysisSourceKind.RECORDED:
            recorded_attitude = self._resolver.RecordedSeries_Get("attitude.q_nb")
            _Series_Plot(
                self.quaternion_plot,
                recorded_attitude,
                start,
                colors=color_allocators[self.quaternion_plot],
                prefix=f"{self._translator.Text_Get('flight.recorded_reference')} · ",
                reference=True,
            )
            if recorded_attitude is not None:
                _Series_Plot(
                    self.euler_plot,
                    _EulerSeries_Create(recorded_attitude),
                    start,
                    colors=color_allocators[self.euler_plot],
                    prefix=f"{self._translator.Text_Get('flight.recorded_reference')} · ",
                    reference=True,
                )
        _Series_Plot(
            self.acceleration_plot,
            self._resolver.RecordedSeries_Get("imu.corrected.accel_b"),
            start,
            colors=color_allocators[self.acceleration_plot],
            prefix=f"{self._translator.Text_Get('status.recorded')} · ",
        )
        _Series_Plot(
            self.angular_rate_plot,
            self._resolver.RecordedSeries_Get("imu.corrected.gyro_b"),
            start,
            colors=color_allocators[self.angular_rate_plot],
            prefix=f"{self._translator.Text_Get('status.recorded')} · ",
        )
        self._position = position
        self._attitude = attitude
        self._deploy_timestamp_us = _Event_Timestamp(self._dataset, 0x29)
        self._landing_timestamp_us = _Event_Timestamp(self._dataset, 0x2A)
        self._trajectory_origin = (
            _TrajectoryOrigin_Get(position, start)
            if position is not None and position.count
            else np.zeros(3, dtype=np.float32)
        )
        end_candidates = [
            int(series.timestamp_us[-1])
            for series in (self._position, self._attitude)
            if series is not None and series.count
        ]
        self._end_timestamp_us = max(end_candidates, default=start)
        if (
            self._landing_timestamp_us is not None
            and self._landing_timestamp_us >= self._end_timestamp_us
            and self._landing_timestamp_us - self._end_timestamp_us <= 100_000
        ):
            self._end_timestamp_us = self._landing_timestamp_us
        self._playback_time_us = start
        self.playback_slider.blockSignals(True)
        self.playback_slider.setValue(0)
        self.playback_slider.blockSignals(False)
        self._Trajectory3d_Prepare(reset_camera=reset_camera)
        self._ThreeD_Refresh(0)

    def _CameraLock_Toggled(self, unlocked: bool) -> None:
        if gl is not None:
            self.attitude_view.CameraLocked_Set(not unlocked)
            self.trajectory_view.CameraLocked_Set(not unlocked)
        self.camera_lock_button.setText(
            self._translator.Text_Get(
                "action.lock_camera" if unlocked else "action.unlock_camera"
            )
        )

    def _Cameras_Reset(self) -> None:
        if gl is None:
            return
        self.attitude_view.setCameraPosition(
            pos=QVector3D(0.0, 0.0, 0.7),
            distance=5.5,
            elevation=18.0,
            azimuth=-50.0,
        )
        center = self._trajectory_camera_center
        self.trajectory_view.setCameraPosition(
            pos=QVector3D(float(center[0]), float(center[1]), float(center[2])),
            distance=self._trajectory_camera_distance,
            elevation=24.0,
            azimuth=-52.0,
        )

    def _Trajectory3d_Prepare(self, *, reset_camera: bool) -> None:
        if gl is None:
            return
        axis_colors = (
            (0.95, 0.2, 0.2, 1.0),
            (0.2, 0.9, 0.35, 1.0),
            (0.2, 0.5, 1.0, 1.0),
        )
        valid_values = np.empty((0, 3), dtype=np.float32)
        if self._position is not None and self._position.count:
            raw_values = np.asarray(self._position.values, dtype=np.float32)
            valid = (
                self._position.valid
                & np.all(np.isfinite(raw_values), axis=1)
                & (
                    self._position.timestamp_us
                    >= np.uint64(max(self._start_timestamp_us, 0))
                )
            )
            valid_values = raw_values[valid] - self._trajectory_origin
        if valid_values.size:
            minimum = np.min(valid_values, axis=0)
            maximum = np.max(valid_values, axis=0)
            spans = maximum - minimum
            extent = max(float(np.max(spans)), 1.0)
            self._trajectory_camera_center = (minimum + maximum) * 0.5
            self._trajectory_camera_distance = max(extent * 1.8, 8.0)
        else:
            spans = np.ones(3, dtype=np.float32)
            extent = 4.0
            self._trajectory_camera_center = np.zeros(3, dtype=np.float32)
            self._trajectory_camera_distance = 8.0
        self._trajectory_marker_sizes = TrajectoryMarkerWorldSizes_Get(valid_values)
        axis_length = max(float(np.max(spans)) * 0.2, 1.0)
        for axis, item in enumerate(self._trajectory_world_items):
            endpoint = np.zeros(3, dtype=np.float32)
            endpoint[axis] = axis_length
            item.setData(
                pos=np.asarray(((0.0, 0.0, 0.0), endpoint), dtype=np.float32),
                color=axis_colors[axis],
                width=2.0,
            )
            self._trajectory_text_items[axis].setData(pos=tuple(endpoint))
        self.trajectory_grid.setSize(extent * 1.3, extent * 1.3)
        spacing = max(extent / 10.0, 0.5)
        self.trajectory_grid.setSpacing(spacing, spacing)
        if reset_camera:
            self._Cameras_Reset()

    def _Playback_Toggle(self) -> None:
        if self.playback_timer.isActive():
            self.playback_timer.stop()
        else:
            if self.playback_slider.value() >= 10000:
                self.playback_slider.setValue(0)
            self.playback_timer.start()
        self._PlaybackButton_Refresh()

    def _PlaybackButton_Refresh(self) -> None:
        self.play_button.setText(
            self._translator.Text_Get(
                "action.pause" if self.playback_timer.isActive() else "action.play"
            )
        )

    def _Playback_Tick(self) -> None:
        if self._end_timestamp_us <= self._start_timestamp_us:
            self.playback_timer.stop()
            self._PlaybackButton_Refresh()
            return
        speed = float(self.playback_speed_combo.currentData() or 1.0)
        self._playback_time_us += int(
            self.playback_timer.interval() * 1000 * speed
        )
        if self._playback_time_us >= self._end_timestamp_us:
            self._playback_time_us = self._end_timestamp_us
            self.playback_timer.stop()
            self._PlaybackButton_Refresh()
        value = int(
            (self._playback_time_us - self._start_timestamp_us)
            * 10000
            / (self._end_timestamp_us - self._start_timestamp_us)
        )
        self.playback_slider.setValue(max(0, min(10000, value)))

    def _ThreeD_Refresh(self, value: int) -> None:
        if self._end_timestamp_us <= self._start_timestamp_us:
            timestamp_us = self._start_timestamp_us
        else:
            timestamp_us = int(
                self._start_timestamp_us
                + (self._end_timestamp_us - self._start_timestamp_us)
                * value
                / 10000
            )
        self._playback_time_us = timestamp_us
        mission_time = (timestamp_us - self._start_timestamp_us) * 1.0e-6
        self.playback_time_label.setText(
            self._translator.Text_Get("flight.mission_time", value=mission_time)
        )
        if gl is None:
            return
        self._Attitude3d_Refresh(timestamp_us)
        self._Trajectory3d_Refresh(timestamp_us)

    def _Attitude3d_Refresh(self, timestamp_us: int) -> None:
        if self._attitude is None or self._attitude.count == 0:
            return
        index = _NearestIndex(self._attitude.timestamp_us, timestamp_us)
        quaternion = np.asarray(self._attitude.values[index], dtype=np.float32)
        try:
            rotated_vertices = _RocketVertices_Rotate(quaternion)
        except ValueError:
            return
        mesh_data = gl.MeshData(
            vertexes=rotated_vertices,
            faces=_ROCKET_FACES,
            faceColors=_RocketFaceColors_Get(self._theme),
        )
        self.rocket_mesh.setMeshData(
            meshdata=mesh_data,
            edgeColor=_RocketEdgeColor_Get(self._theme),
        )
        colors = (
            (0.95, 0.2, 0.2, 1.0),
            (0.2, 0.9, 0.35, 1.0),
            (0.2, 0.5, 1.0, 1.0),
        )
        identity = np.eye(3, dtype=np.float32)
        body_lengths = np.asarray((1.1, 1.1, 1.6), dtype=np.float32)
        for axis, item in enumerate(self._attitude_world_items):
            endpoint = identity[axis] * 1.25
            item.setData(
                pos=np.asarray(((0.0, 0.0, 0.0), endpoint), dtype=np.float32),
                color=colors[axis],
                width=2.0,
            )
            self._attitude_text_items[axis].setData(pos=tuple(endpoint))
        for axis, item in enumerate(self._attitude_body_items):
            endpoint = Quaternion_RotateVector(
                quaternion,
                identity[axis] * body_lengths[axis],
            )
            item.setData(
                pos=np.asarray(((0.0, 0.0, 0.0), endpoint), dtype=np.float32),
                color=colors[axis],
                width=3.0,
            )
            self._attitude_text_items[axis + 3].setData(pos=tuple(endpoint))

    def _Trajectory3d_Refresh(self, timestamp_us: int) -> None:
        empty = np.empty((0, 3), dtype=np.float32)
        if self._position is None or self._position.count == 0:
            self.pre_deploy_line.setData(pos=empty)
            self.post_deploy_line.setData(pos=empty)
            self.deploy_marker.setData(pos=empty)
            self.landing_marker.setData(pos=empty)
            self.current_marker.setData(pos=empty)
            return
        raw_values = np.asarray(self._position.values, dtype=np.float32)
        finite = np.all(np.isfinite(raw_values), axis=1)
        valid = (
            self._position.valid
            & finite
            & (self._position.timestamp_us >= np.uint64(self._start_timestamp_us))
            & (self._position.timestamp_us <= np.uint64(timestamp_us))
        )
        points = raw_values[valid] - self._trajectory_origin
        times = self._position.timestamp_us[valid]
        if points.size == 0:
            self.pre_deploy_line.setData(pos=empty)
            self.post_deploy_line.setData(pos=empty)
            self.deploy_marker.setData(pos=empty)
            self.landing_marker.setData(pos=empty)
            self.current_marker.setData(pos=empty)
            return
        stride = max(1, len(points) // 10000)
        points = points[::stride]
        times = times[::stride]
        deploy = self._deploy_timestamp_us
        if deploy is None:
            pre = points
            post = empty
        else:
            pre = points[times <= np.uint64(deploy)]
            post = points[times >= np.uint64(deploy)]
        self.pre_deploy_line.setData(
            pos=pre,
            color=QColor(TRAJECTORY_PRE_DEPLOY_COLOR).getRgbF(),
            width=3.0,
        )
        self.post_deploy_line.setData(
            pos=post,
            color=QColor(TRAJECTORY_POST_DEPLOY_COLOR).getRgbF(),
            width=3.0,
        )
        current = points[-1]
        current_color = TrajectoryPhaseColor_Get(timestamp_us, deploy)
        deploy_size, current_size, landing_size = self._trajectory_marker_sizes
        self.current_marker.setData(
            pos=np.asarray([current], dtype=np.float32),
            color=QColor(current_color).getRgbF(),
            size=current_size,
        )
        deploy_point = (
            _Position_At(self._position, deploy)
            if deploy is not None and timestamp_us >= deploy
            else None
        )
        if deploy_point is not None:
            deploy_point = deploy_point - self._trajectory_origin
        deploy_positions = (
            np.asarray([deploy_point], dtype=np.float32)
            if deploy_point is not None
            else empty
        )
        self.deploy_marker.setData(
            pos=deploy_positions,
            color=QColor(TRAJECTORY_DEPLOY_COLOR).getRgbF(),
            size=deploy_size,
        )
        landing_point = (
            _Position_NearEvent(self._position, self._landing_timestamp_us)
            if self._landing_timestamp_us is not None
            and timestamp_us >= self._landing_timestamp_us
            else None
        )
        if landing_point is not None:
            landing_point = landing_point - self._trajectory_origin
        self.landing_marker.setData(
            pos=(
                np.asarray([landing_point], dtype=np.float32)
                if landing_point is not None
                else empty
            ),
            color=QColor(TRAJECTORY_LANDING_COLOR).getRgbF(),
            size=landing_size,
        )

    def Theme_Apply(self, theme: str) -> None:
        self._theme = theme
        for plot in (
            self.velocity_plot,
            self.position_plot,
            self.acceleration_plot,
            self.angular_rate_plot,
            self.quaternion_plot,
            self.euler_plot,
        ):
            _Plot_Prepare(plot, theme)
        if gl is not None:
            background = QColor("#111827" if theme == "dark" else "#FFFFFF")
            grid = QColor("#64748B" if theme == "dark" else "#94A3B8")
            foreground = QColor("#E5E7EB" if theme == "dark" else "#172033")
            self.attitude_view.setBackgroundColor(background)
            self.trajectory_view.setBackgroundColor(background)
            self.attitude_grid.setColor(grid)
            self.trajectory_grid.setColor(grid)
            for item in self._gl_text_items:
                item.setData(color=foreground)
            if self._attitude is not None and self._attitude.count:
                self._Attitude3d_Refresh(self._playback_time_us)
            else:
                mesh_data = gl.MeshData(
                    vertexes=_ROCKET_BASE_VERTICES,
                    faces=_ROCKET_FACES,
                    faceColors=_RocketFaceColors_Get(theme),
                )
                self.rocket_mesh.setMeshData(
                    meshdata=mesh_data,
                    edgeColor=_RocketEdgeColor_Get(theme),
                )
            self._Trajectory3d_Refresh(self._playback_time_us)

    def Language_Apply(self, translator: Translator) -> None:
        self._translator = translator
        self.source_label.setText(translator.Text_Get("label.analysis_source"))
        self.velocity_plot.setTitle(translator.Text_Get("chart.velocity_enu"))
        self.position_plot.setTitle(translator.Text_Get("chart.position_enu"))
        self.acceleration_plot.setTitle(
            translator.Text_Get("chart.corrected_acceleration")
        )
        self.angular_rate_plot.setTitle(
            translator.Text_Get("chart.corrected_angular_rate")
        )
        self.quaternion_plot.setTitle(translator.Text_Get("chart.quaternion_wxyz"))
        self.euler_plot.setTitle(translator.Text_Get("chart.euler_display"))
        self.attitude_authority_label.setText(
            translator.Text_Get("flight.attitude_authority")
        )
        tab_codes = (
            "tab.velocity",
            "tab.position",
            "tab.acceleration",
            "tab.angular_rate",
            "tab.attitude",
            "tab.replay_3d",
        )
        for index, code in enumerate(tab_codes):
            self.tabs.setTabText(index, translator.Text_Get(code))
        self.attitude_3d_group.setTitle(translator.Text_Get("flight.attitude_3d"))
        self.trajectory_3d_group.setTitle(
            translator.Text_Get("flight.trajectory_3d")
        )
        self.attitude_axes_legend.setText(
            translator.Text_Get("flight.attitude_axes_legend")
        )
        self.trajectory_axes_legend.setText(
            translator.Text_Get("flight.trajectory_axes_legend")
        )
        self.playback_speed_label.setText(
            translator.Text_Get("flight.playback_speed")
        )
        self.reset_camera_button.setText(translator.Text_Get("action.reset_view"))
        self.reset_charts_button.setText(translator.Text_Get("action.reset_charts"))
        self.reset_charts_button.setToolTip(
            translator.Text_Get("action.reset_charts_tooltip")
        )
        self._CameraLock_Toggled(self.camera_lock_button.isChecked())
        self._PlaybackButton_Refresh()
        if gl is None:
            self.opengl_unavailable_label.setText(
                translator.Text_Get("status.opengl_unavailable")
            )
        if self._dataset is not None and self._resolver is not None:
            self._Plots_Refresh(reset_camera=False)
