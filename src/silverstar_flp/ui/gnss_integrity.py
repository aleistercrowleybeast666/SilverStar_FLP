"""Receiver-native GNSS position/velocity consistency view."""
from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSplitter, QVBoxLayout, QWidget

from silverstar_flp.analysis.gnss_integrity import WINDOW_SECONDS, GnssIntegrity_Build
from silverstar_flp.ui.pages.charts import _Plot_Prepare, _Plot_Reset, _PlotViews_Reset
from silverstar_flp.ui.widgets import StandardComboBox


class GnssIntegrityPage(QWidget):
    def __init__(self, translator, parent=None):
        super().__init__(parent)
        self._translator = translator
        self._theme = "light"
        self._dataset = None
        self._result = None
        self._origin = 0
        self._interval = (0.0, float("inf"))
        layout = QVBoxLayout(self)
        controls = QHBoxLayout()
        self.window_label = QLabel()
        self.window_combo = StandardComboBox()
        for seconds in WINDOW_SECONDS:
            self.window_combo.addItem(f"{seconds} s", seconds)
        self.window_combo.setCurrentIndex(self.window_combo.findData(5))
        self.window_combo.currentIndexChanged.connect(self._Rebuild)
        controls.addWidget(self.window_label)
        controls.addWidget(self.window_combo)
        controls.addStretch(1)
        layout.addLayout(controls)
        self.note = QLabel()
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        splitter = QSplitter(Qt.Orientation.Vertical)
        self.plots = tuple(pg.PlotWidget() for _ in range(5))
        for plot in self.plots:
            plot.setMinimumHeight(80)
            plot.addLegend()
            _Plot_Prepare(plot, self._theme)
            splitter.addWidget(plot)
        layout.addWidget(splitter, 1)
        self.Language_Apply(translator)

    def Dataset_Set(self, dataset):
        self._dataset = dataset
        self._origin = dataset.start_timestamp_us or dataset.diagnostics.first_timestamp_us or 0
        self._Rebuild()

    def _Rebuild(self):
        if self._dataset is None:
            return
        try:
            result = GnssIntegrity_Build(self._dataset, int(self.window_combo.currentData()))
        except (ValueError, KeyError, TypeError) as error:
            self._result = None
            self.summary.setText(str(error))
            _Plot_Reset(self.plots)
            return
        self._result = result
        self._Render()

    def _Render(self):
        result = self._result
        if result is None:
            return
        _Plot_Reset(self.plots)
        t = (result.timestamp_us.astype(np.float64) - self._origin) * 1e-6
        pos = result.position_displacement_m
        vel = result.velocity_displacement_m
        residual = result.residual_m
        horizontal_norm = np.linalg.norm(residual[:, :2], axis=1)
        horizontal_norm[~result.valid_en] = np.nan
        label = self._translator.Text_Get
        traces = (
            ((pos[:, 0], label("integrity.pos_e")),
             (vel[:, 0], label("integrity.vel_e")),
             (pos[:, 1], label("integrity.pos_n")),
             (vel[:, 1], label("integrity.vel_n"))),
            ((residual[:, 0], label("integrity.res_e")),
             (residual[:, 1], label("integrity.res_n")),
             (horizontal_norm, label("integrity.res_en"))),
            ((pos[:, 2], label("integrity.pos_u")),
             (vel[:, 2], label("integrity.vel_u")),
             (residual[:, 2], label("integrity.res_u"))),
            ((result.quality[:, 0], label("integrity.hacc")),
             (result.quality[:, 1], label("integrity.vacc")),
             (result.quality[:, 2], label("integrity.sacc"))),
            ((result.quality[:, 3], label("integrity.satellites_label")),),
        )
        colors = ("#2b77c2", "#ec8a20", "#1a9d6c", "#a44ca0")
        titles = (
            "integrity.displacement", "integrity.closure",
            "integrity.vertical", "integrity.quality", "integrity.satellites",
        )
        for plot, series, title in zip(self.plots, traces, titles, strict=True):
            for index, (values, name) in enumerate(series):
                plot.plot(t, values, pen=pg.mkPen(colors[index], width=1.5),
                          connect="finite", name=name)
            plot.setTitle(self._translator.Text_Get(title))
            plot.setLabel("bottom", self._translator.Text_Get("timeline.time"))
        self._Summary_Set()
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

    def _Summary_Set(self):
        if self._result is None:
            return
        lines = []
        for group, label in (("horizontal", "integrity.horizontal"),
                             ("vertical", "integrity.vertical_group")):
            summary = self._result.summary[group]
            lines.append(self._translator.Text_Get(
                "integrity.summary", group=self._translator.Text_Get(label),
                count=summary["valid_window_count"], coverage=summary["coverage"] * 100,
                median=summary["median_m"], p95=summary["p95_m"], maximum=summary["max_m"],
            ))
        self.summary.setText("\n".join(lines))

    def Theme_Apply(self, theme):
        self._theme = theme
        for plot in self.plots:
            _Plot_Prepare(plot, theme)

    def Language_Apply(self, translator):
        self._translator = translator
        self.window_label.setText(translator.Text_Get("integrity.window"))
        self.note.setText(translator.Text_Get("integrity.analysis_only"))
        self._Render()

    def ChartViews_Reset(self):
        _PlotViews_Reset(self.plots)
