from __future__ import annotations

from collections.abc import Mapping

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QSlider,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from silverstar_flp.core.dataset import FlightDataset, TimeSeries
from silverstar_flp.core.i18n import Translator
from silverstar_flp.core.math import Quaternion_RotateVector, Quaternion_ToEulerEnuDeg
from silverstar_flp.plugins.api.algorithm import AlgorithmResult
from silverstar_flp.ui.theme import Plot_Colors
from silverstar_flp.ui.widgets import StandardComboBox

try:
    import pyqtgraph.opengl as gl
except Exception:  # OpenGL is optional at runtime; charts remain available.
    gl = None


_COLORS = ("#3B82F6", "#10B981", "#F97316", "#A855F7", "#EC4899", "#14B8A6")


def _Plot_Prepare(plot: pg.PlotWidget, theme: str) -> None:
    background, foreground = Plot_Colors(theme)
    plot.setBackground(background)
    plot.getAxis("bottom").setTextPen(foreground)
    plot.getAxis("left").setTextPen(foreground)
    plot.showGrid(x=True, y=True, alpha=0.2)


def _Series_Plot(
    plot: pg.PlotWidget,
    series: TimeSeries | None,
    start_timestamp_us: int,
    *,
    prefix: str = "",
    width: float = 1.2,
) -> None:
    if series is None or series.count == 0:
        return
    values = np.asarray(series.values, dtype=np.float64)
    stride = max(1, series.count // 6000)
    time = (series.timestamp_us[::stride].astype(np.float64) - start_timestamp_us) * 1.0e-6
    if values.ndim == 1:
        plot.plot(
            time,
            values[::stride],
            pen=pg.mkPen(_COLORS[0], width=width),
            name=prefix or series.quantity,
        )
        return
    for index in range(values.shape[1]):
        column = series.columns[index] if series.columns else str(index)
        plot.plot(
            time,
            values[::stride, index],
            pen=pg.mkPen(_COLORS[index % len(_COLORS)], width=width),
            name=f"{prefix}{column}",
        )


class FlightPage(QWidget):
    def __init__(self, translator: Translator) -> None:
        super().__init__()
        self._translator = translator
        self._theme = "light"
        self._dataset: FlightDataset | None = None
        layout = QVBoxLayout(self)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        charts = QWidget()
        chart_layout = QVBoxLayout(charts)
        self.altitude_plot = pg.PlotWidget()
        self.speed_plot = pg.PlotWidget()
        for plot in (self.altitude_plot, self.speed_plot):
            plot.addLegend()
            _Plot_Prepare(plot, self._theme)
            chart_layout.addWidget(plot)
        self.splitter.addWidget(charts)
        self.trajectory_container = QGroupBox()
        self.trajectory_container.setMinimumWidth(420)
        trajectory_layout = QVBoxLayout(self.trajectory_container)
        if gl is not None:
            self.trajectory_view = gl.GLViewWidget()
            self.trajectory_view.opts["distance"] = 40
            self.trajectory_view.addItem(gl.GLGridItem())
            trajectory_layout.addWidget(self.trajectory_view)
        else:
            self.trajectory_view = None
            self.opengl_unavailable_label = QLabel()
            trajectory_layout.addWidget(self.opengl_unavailable_label)
        self.splitter.addWidget(self.trajectory_container)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes((700, 700))
        layout.addWidget(self.splitter)
        self.Language_Apply(translator)

    def Dataset_Set(
        self, dataset: FlightDataset, results: Mapping[str, AlgorithmResult] | None = None
    ) -> None:
        self._dataset = dataset
        self.altitude_plot.clear()
        self.speed_plot.clear()
        self.altitude_plot.addLegend()
        self.speed_plot.addLegend()
        start = dataset.start_timestamp_us or dataset.diagnostics.first_timestamp_us or 0
        position = dataset.Series_Get("kf6.recorded.navigation.position_enu")
        velocity = dataset.Series_Get("kf6.recorded.navigation.velocity_enu")
        if position is None:
            position = dataset.Series_Get("pure_ins.recorded.navigation.position_enu")
        if velocity is None:
            velocity = dataset.Series_Get("pure_ins.recorded.navigation.velocity_enu")
        if position is not None:
            altitude = TimeSeries(
                position.timestamp_us,
                position.values[:, 2],
                position.unit,
                "altitude",
                position.source,
                position.valid,
                metadata=position.metadata,
            )
            _Series_Plot(self.altitude_plot, altitude, start, prefix="Recorded U")
        _Series_Plot(self.speed_plot, velocity, start, prefix="Recorded ")
        for name, result in (results or {}).items():
            recomputed_position = result.channels.get("navigation.position_enu")
            recomputed_velocity = result.channels.get("navigation.velocity_enu")
            if recomputed_position is not None:
                altitude = TimeSeries(
                    recomputed_position.timestamp_us,
                    recomputed_position.values[:, 2],
                    recomputed_position.unit,
                    "altitude",
                    recomputed_position.source,
                    recomputed_position.valid,
                    metadata=recomputed_position.metadata,
                )
                _Series_Plot(self.altitude_plot, altitude, start, prefix=f"{name} U", width=1.6)
            _Series_Plot(self.speed_plot, recomputed_velocity, start, prefix=f"{name} ", width=1.6)
        if self.trajectory_view is not None and position is not None:
            for item in list(self.trajectory_view.items):
                if isinstance(item, gl.GLLinePlotItem):
                    self.trajectory_view.removeItem(item)
            values = np.asarray(position.values, dtype=np.float32)
            stride = max(1, len(values) // 10000)
            line = gl.GLLinePlotItem(
                pos=values[::stride], color=(0.15, 0.5, 1.0, 1.0), width=2.0, antialias=True
            )
            self.trajectory_view.addItem(line)

    def Theme_Apply(self, theme: str) -> None:
        self._theme = theme
        for plot in (self.altitude_plot, self.speed_plot):
            _Plot_Prepare(plot, theme)

    def Language_Apply(self, translator: Translator) -> None:
        self._translator = translator
        self.altitude_plot.setTitle(translator.Text_Get("chart.altitude"))
        self.speed_plot.setTitle(translator.Text_Get("chart.velocity"))
        self.trajectory_container.setTitle(translator.Text_Get("chart.trajectory_3d"))
        if self.trajectory_view is None:
            self.opengl_unavailable_label.setText(translator.Text_Get("status.opengl_unavailable"))


class AttitudeImuPage(QWidget):
    def __init__(self, translator: Translator) -> None:
        super().__init__()
        self._translator = translator
        self._theme = "light"
        self._dataset: FlightDataset | None = None
        self._results: Mapping[str, AlgorithmResult] = {}
        self._attitude_sources: dict[str, TimeSeries] = {}
        layout = QVBoxLayout(self)
        source_layout = QHBoxLayout()
        self.source_label = QLabel()
        source_layout.addWidget(self.source_label)
        self.source_combo = StandardComboBox()
        self.source_combo.currentIndexChanged.connect(self._Source_Refresh)
        source_layout.addWidget(self.source_combo, 1)
        layout.addLayout(source_layout)
        self.tabs = QTabWidget()
        self.euler_plot = pg.PlotWidget()
        self.euler_plot.addLegend()
        self.imu_plot = pg.PlotWidget()
        self.imu_plot.addLegend()
        _Plot_Prepare(self.euler_plot, self._theme)
        _Plot_Prepare(self.imu_plot, self._theme)
        self.tabs.addTab(self.euler_plot, "")
        self.tabs.addTab(self.imu_plot, "IMU")
        viewer = QWidget()
        viewer_layout = QVBoxLayout(viewer)
        if gl is not None:
            self.attitude_view = gl.GLViewWidget()
            self.attitude_view.opts["distance"] = 5
            self.attitude_view.addItem(gl.GLGridItem())
            self._axis_items = [gl.GLLinePlotItem(width=4.0, antialias=True) for _ in range(3)]
            for axis_item in self._axis_items:
                self.attitude_view.addItem(axis_item)
            viewer_layout.addWidget(self.attitude_view)
        else:
            self.attitude_view = None
            self._axis_items = []
            self.opengl_unavailable_label = QLabel()
            viewer_layout.addWidget(self.opengl_unavailable_label)
        self.sample_slider = QSlider(Qt.Orientation.Horizontal)
        self.sample_slider.valueChanged.connect(self._Viewer_Refresh)
        viewer_layout.addWidget(self.sample_slider)
        self.viewer_time_label = QLabel("—")
        viewer_layout.addWidget(self.viewer_time_label)
        self.tabs.addTab(viewer, "3D")
        layout.addWidget(self.tabs)
        self.Language_Apply(translator)

    def Dataset_Set(
        self, dataset: FlightDataset, results: Mapping[str, AlgorithmResult] | None = None
    ) -> None:
        self._dataset = dataset
        self._results = results or {}
        self._attitude_sources = {}
        recorded = dataset.Series_Get("pure_ins.recorded.attitude.q_nb")
        hardware = dataset.Series_Get("hardware_attitude.reference.q_nb")
        if recorded is not None:
            self._attitude_sources[
                self._translator.Text_Get("attitude.source.recorded_software")
            ] = recorded
        if hardware is not None:
            self._attitude_sources[
                self._translator.Text_Get("attitude.source.hardware_reference")
            ] = hardware
        for name, result in self._results.items():
            attitude = result.channels.get("attitude.q_nb")
            if attitude is not None:
                provenance_code = (
                    "status.what_if" if result.provenance == "What-if" else "status.recomputed"
                )
                self._attitude_sources[f"{name} · {self._translator.Text_Get(provenance_code)}"] = (
                    attitude
                )
        self.source_combo.blockSignals(True)
        self.source_combo.clear()
        self.source_combo.addItems(self._attitude_sources)
        self.source_combo.blockSignals(False)
        self.imu_plot.clear()
        self.imu_plot.addLegend()
        start = dataset.start_timestamp_us or dataset.diagnostics.first_timestamp_us or 0
        _Series_Plot(
            self.imu_plot,
            dataset.Series_Get("imu.corrected.accel_b"),
            start,
            prefix="Accel ",
        )
        _Series_Plot(
            self.imu_plot,
            dataset.Series_Get("imu.corrected.gyro_b"),
            start,
            prefix="Gyro ",
        )
        self._Source_Refresh()

    def _Source_Refresh(self) -> None:
        self.euler_plot.clear()
        self.euler_plot.addLegend()
        name = self.source_combo.currentText()
        series = self._attitude_sources.get(name)
        if series is None or self._dataset is None:
            self.sample_slider.setRange(0, 0)
            return
        stride = max(1, series.count // 5000)
        indices = np.arange(0, series.count, stride)
        euler = np.asarray([Quaternion_ToEulerEnuDeg(series.values[index]) for index in indices])
        start = self._dataset.start_timestamp_us or int(series.timestamp_us[0])
        time = (series.timestamp_us[indices].astype(np.float64) - start) * 1.0e-6
        for axis, label in enumerate(
            (
                self._translator.Text_Get("axis.roll"),
                self._translator.Text_Get("axis.pitch"),
                self._translator.Text_Get("axis.yaw"),
            )
        ):
            self.euler_plot.plot(
                time, euler[:, axis], pen=pg.mkPen(_COLORS[axis], width=1.2), name=label
            )
        self.sample_slider.setRange(0, max(0, series.count - 1))
        self._Viewer_Refresh()

    def _Viewer_Refresh(self) -> None:
        series = self._attitude_sources.get(self.source_combo.currentText())
        if series is None or series.count == 0:
            return
        index = min(self.sample_slider.value(), series.count - 1)
        quaternion = series.values[index]
        elapsed = 0.0
        if self._dataset is not None:
            start = self._dataset.start_timestamp_us or int(series.timestamp_us[0])
            elapsed = (int(series.timestamp_us[index]) - start) * 1.0e-6
        self.viewer_time_label.setText(f"t = {elapsed:.6f} s · WXYZ={quaternion}")
        if self.attitude_view is None:
            return
        colors = ((1.0, 0.2, 0.2, 1.0), (0.2, 1.0, 0.4, 1.0), (0.2, 0.5, 1.0, 1.0))
        for axis, item in enumerate(self._axis_items):
            vector = Quaternion_RotateVector(quaternion, np.eye(3, dtype=np.float32)[axis])
            item.setData(
                pos=np.asarray(((0.0, 0.0, 0.0), vector), dtype=np.float32),
                color=colors[axis],
                width=4.0,
            )

    def Timeline_Set(self, timestamp_us: int) -> None:
        series = self._attitude_sources.get(self.source_combo.currentText())
        if series is None:
            return
        index = int(np.searchsorted(series.timestamp_us, timestamp_us, side="left"))
        self.sample_slider.setValue(min(max(index, 0), series.count - 1))

    def Theme_Apply(self, theme: str) -> None:
        self._theme = theme
        _Plot_Prepare(self.euler_plot, theme)
        _Plot_Prepare(self.imu_plot, theme)

    def Language_Apply(self, translator: Translator) -> None:
        self._translator = translator
        self.source_label.setText(translator.Text_Get("label.attitude_source"))
        self.euler_plot.setTitle(translator.Text_Get("chart.euler"))
        self.imu_plot.setTitle(translator.Text_Get("chart.corrected_imu"))
        self.tabs.setTabText(0, translator.Text_Get("tab.attitude"))
        self.tabs.setTabText(1, translator.Text_Get("tab.imu"))
        self.tabs.setTabText(2, translator.Text_Get("tab.three_d"))
        if self.attitude_view is None:
            self.opengl_unavailable_label.setText(translator.Text_Get("status.opengl_unavailable"))
        if self._dataset is not None:
            self.Dataset_Set(self._dataset, self._results)


class NavigationPage(QWidget):
    def __init__(self, translator: Translator) -> None:
        super().__init__()
        self._translator = translator
        self._theme = "light"
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        self.position_plot = pg.PlotWidget()
        self.velocity_plot = pg.PlotWidget()
        self.covariance_plot = pg.PlotWidget()
        self.nis_plot = pg.PlotWidget()
        for widget, title in (
            (self.position_plot, "Position"),
            (self.velocity_plot, "Velocity"),
            (self.covariance_plot, "P"),
            (self.nis_plot, "NIS"),
        ):
            widget.addLegend()
            _Plot_Prepare(widget, self._theme)
            self.tabs.addTab(widget, title)
        layout.addWidget(self.tabs)
        self.Language_Apply(translator)

    def Dataset_Set(
        self, dataset: FlightDataset, results: Mapping[str, AlgorithmResult] | None = None
    ) -> None:
        for plot in (
            self.position_plot,
            self.velocity_plot,
            self.covariance_plot,
            self.nis_plot,
        ):
            plot.clear()
            plot.addLegend()
        start = dataset.start_timestamp_us or dataset.diagnostics.first_timestamp_us or 0
        _Series_Plot(
            self.position_plot,
            dataset.Series_Get("kf6.recorded.navigation.position_enu"),
            start,
            prefix="Recorded ",
        )
        _Series_Plot(
            self.velocity_plot,
            dataset.Series_Get("kf6.recorded.navigation.velocity_enu"),
            start,
            prefix="Recorded ",
        )
        _Series_Plot(
            self.covariance_plot,
            dataset.Series_Get("kf6.recorded.covariance.diagonal"),
            start,
            prefix="Recorded ",
        )
        for nis_id, name in (
            ("kf6.recorded.nis.position", "Recorded position"),
            ("kf6.recorded.nis.velocity", "Recorded velocity"),
            ("kf6.recorded.nis.baro", "Recorded baro"),
        ):
            _Series_Plot(self.nis_plot, dataset.Series_Get(nis_id), start, prefix=name)
        for name, result in (results or {}).items():
            _Series_Plot(
                self.position_plot,
                result.channels.get("navigation.position_enu"),
                start,
                prefix=f"{name} ",
                width=1.6,
            )
            _Series_Plot(
                self.velocity_plot,
                result.channels.get("navigation.velocity_enu"),
                start,
                prefix=f"{name} ",
                width=1.6,
            )
            _Series_Plot(
                self.covariance_plot,
                result.channels.get("kf6.covariance.diagonal"),
                start,
                prefix=f"{name} ",
            )
            for channel_id, label in (
                ("kf6.nis.position", "position"),
                ("kf6.nis.velocity", "velocity"),
                ("kf6.nis.baro", "baro"),
            ):
                _Series_Plot(
                    self.nis_plot,
                    result.channels.get(channel_id),
                    start,
                    prefix=f"{name} {label}",
                )

    def Theme_Apply(self, theme: str) -> None:
        self._theme = theme
        for plot in (
            self.position_plot,
            self.velocity_plot,
            self.covariance_plot,
            self.nis_plot,
        ):
            _Plot_Prepare(plot, theme)

    def Language_Apply(self, translator: Translator) -> None:
        self._translator = translator
        self.position_plot.setTitle(translator.Text_Get("chart.position_enu"))
        self.velocity_plot.setTitle(translator.Text_Get("chart.velocity_enu"))
        self.covariance_plot.setTitle(translator.Text_Get("chart.kf6_covariance"))
        self.nis_plot.setTitle(translator.Text_Get("chart.kf6_nis"))
        self.tabs.setTabText(0, translator.Text_Get("tab.position"))
        self.tabs.setTabText(1, translator.Text_Get("tab.velocity"))
        self.tabs.setTabText(2, "P")
        self.tabs.setTabText(3, "NIS")
