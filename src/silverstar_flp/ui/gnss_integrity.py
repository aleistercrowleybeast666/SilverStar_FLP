"""Three receiver-native GNSS horizontal self-check chart pages."""
from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PySide6.QtWidgets import QLabel, QTabWidget, QVBoxLayout, QWidget

from silverstar_flp.analysis.gnss_integrity_stream import GnssIntegrityStream_Build
from silverstar_flp.ui.plot_helpers import _Plot_Prepare, _Plot_Reset, _PlotViews_Reset


class GnssIntegrityPage(QWidget):
    def __init__(self, translator, parent=None):
        super().__init__(parent)
        self._translator = translator
        self._theme = "light"
        self._dataset = None
        self._parameters = {}
        self._result = None
        self._origin = 0
        self._interval = (0.0, float("inf"))
        layout = QVBoxLayout(self)
        self.note = QLabel()
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        self.plot_tabs = QTabWidget()
        self.displacement_plot = pg.PlotWidget()
        self.closure_plot = pg.PlotWidget()
        self.quality_plot = pg.PlotWidget()
        self.satellite_plot = pg.PlotWidget()
        self.plots = (self.displacement_plot, self.closure_plot,
                      self.quality_plot, self.satellite_plot)
        for plot in self.plots:
            plot.setMinimumHeight(180)
            plot.addLegend()
            _Plot_Prepare(plot, self._theme)
        self.plot_tabs.addTab(self.displacement_plot, "")
        self.plot_tabs.addTab(self.closure_plot, "")
        quality_page = QWidget()
        quality_layout = QVBoxLayout(quality_page)
        quality_layout.addWidget(self.quality_plot)
        quality_layout.addWidget(self.satellite_plot)
        self.plot_tabs.addTab(quality_page, "")
        layout.addWidget(self.plot_tabs, 1)
        self.Language_Apply(translator)

    def Dataset_Set(self, dataset):
        self._dataset = dataset
        self._origin = dataset.start_timestamp_us or dataset.diagnostics.first_timestamp_us or 0
        self._Rebuild()

    def Parameters_Set(self, parameters):
        self._parameters = dict(parameters or {})
        # Older logs have no onboard policy, but the desktop chart can still
        # display receiver-native kinematic evidence for comparison.
        self._parameters["gnss_integrity_enable"] = 1
        self._Rebuild()

    def _Rebuild(self):
        if self._dataset is None:
            return
        try:
            self._result = GnssIntegrityStream_Build(self._dataset, self._parameters)
        except (ValueError, KeyError, TypeError) as error:
            self._result = None
            self.note.setText(str(error))
            _Plot_Reset(self.plots)
            return
        self._Render()

    def _Trace_Draw(self, plot, time, values, name, color):
        plot.plot(time, np.asarray(values, dtype=np.float64),
                  pen=pg.mkPen(color, width=1.5), connect="finite", name=name)

    def _Markers_Draw(self, plot, time, result):
        for index in np.flatnonzero(result.chain_reset):
            plot.addItem(pg.InfiniteLine(pos=float(time[index]), angle=90,
                pen=pg.mkPen("#9299a5", width=1)))
        states = result.state
        for index in range(1, len(states)):
            if states[index] != states[index - 1]:
                color = ("#1a9d6c", "#ec8a20", "#d84a4a")[int(states[index])]
                plot.addItem(pg.InfiniteLine(pos=float(time[index]), angle=90,
                    pen=pg.mkPen(color, width=2)))

    def _Render(self):
        result = self._result
        if result is None:
            return
        _Plot_Reset(self.plots)
        label = self._translator.Text_Get
        t = (result.timestamp_us.astype(np.float64) - self._origin) * 1e-6
        p = result.position_displacement_en.copy()
        v = result.integrated_velocity_en.copy()
        c = result.closure_en.copy()
        for index in np.flatnonzero(result.chain_reset):
            p[index, :] = np.nan
            v[index, :] = np.nan
            c[index, :] = np.nan
        for values, key, color in (
            (p[:, 0], "integrity.pos_e", "#2b77c2"),
            (v[:, 0], "integrity.vel_e", "#ec8a20"),
            (p[:, 1], "integrity.pos_n", "#1a9d6c"),
            (v[:, 1], "integrity.vel_n", "#aa69b0"),
        ):
            self._Trace_Draw(self.displacement_plot, t, values, label(key), color)
        for values, key, color in (
            (c[:, 0], "integrity.res_e", "#2b77c2"),
            (c[:, 1], "integrity.res_n", "#1a9d6c"),
            (result.closure_norm_m, "integrity.res_en", "#d84a4a"),
        ):
            self._Trace_Draw(self.closure_plot, t, values, label(key), color)
        error = float(self._parameters.get("gnss_integrity_error_threshold_m", 10.0))
        recovery = float(self._parameters.get("gnss_integrity_recovery_threshold_m", 4.0))
        for threshold, key, color in (
            (error, "integrity.error_threshold", "#d84a4a"),
            (recovery, "integrity.recovery_threshold", "#1a9d6c"),
        ):
            self.closure_plot.addItem(pg.InfiniteLine(pos=threshold, angle=0,
                pen=pg.mkPen(color, width=1, style=pg.QtCore.Qt.PenStyle.DashLine),
                label=label(key)))
        for index, key, color in (
            (0, "integrity.hacc", "#2b77c2"),
            (1, "integrity.vacc", "#1a9d6c"),
            (2, "integrity.sacc", "#ec8a20"),
        ):
            self._Trace_Draw(self.quality_plot, t, result.quality[:, index], label(key), color)
        self._Trace_Draw(self.satellite_plot, t, result.quality[:, 3],
                         label("integrity.satellites_label"), "#9467bd")
        for plot in (self.displacement_plot, self.closure_plot):
            self._Markers_Draw(plot, t, result)
            plot.setLabel("left", "m")
        self.quality_plot.setLabel("left", "m / m/s")
        self.satellite_plot.setLabel("left", label("integrity.satellites_label"))
        for plot in self.plots:
            plot.setLabel("bottom", label("timeline.time"))
        self.note.setText(label("integrity.analysis_only") + "\n" +
            label("integrity.integration_reference_reset"))
        self.TimeRange_Set(*self._interval)

    def TimeRange_Set(self, start: float, end: float):
        self._interval = (start, end)
        if not np.isfinite(end):
            if self._result is None or not len(self._result.timestamp_us):
                return
            end = (float(self._result.timestamp_us[-1]) - self._origin) * 1e-6
        end = max(end, start + .001)
        for plot in self.plots:
            plot.setLimits(xMin=start, xMax=end)
            plot.setXRange(start, end, padding=0)

    def Theme_Apply(self, theme):
        self._theme = theme
        for plot in self.plots:
            _Plot_Prepare(plot, theme)

    def Language_Apply(self, translator):
        self._translator = translator
        for index, key in enumerate(("integrity.displacement", "integrity.closure",
                                     "integrity.quality")):
            self.plot_tabs.setTabText(index, translator.Text_Get(key))
        self._Render()

    def ChartViews_Reset(self):
        _PlotViews_Reset(self.plots)
