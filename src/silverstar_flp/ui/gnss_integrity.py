"""Receiver-native GNSS position/velocity consistency view."""
from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PySide6.QtWidgets import QHBoxLayout, QLabel, QTabWidget, QVBoxLayout, QWidget

from silverstar_flp.analysis.gnss_integrity import WINDOW_SECONDS, GnssIntegrity_Build
from silverstar_flp.ui.plot_helpers import _Plot_Prepare, _Plot_Reset, _PlotViews_Reset
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
        self.axis_label = QLabel()
        self.axis_combo = StandardComboBox()
        self.axis_combo.addItem("E", 0)
        self.axis_combo.addItem("N", 1)
        self.axis_combo.currentIndexChanged.connect(self._Render)
        controls.addWidget(self.axis_label)
        controls.addWidget(self.axis_combo)
        self.closure_label = QLabel()
        self.closure_combo = StandardComboBox()
        self.closure_combo.addItem("", "anchored")
        self.closure_combo.addItem("", "recent")
        self.closure_combo.addItem("", "anchored_e")
        self.closure_combo.addItem("", "anchored_n")
        self.closure_combo.currentIndexChanged.connect(self._Render)
        controls.addWidget(self.closure_label)
        controls.addWidget(self.closure_combo)
        self.vertical_label = QLabel()
        self.vertical_combo = StandardComboBox()
        for mode in ("anchored_displacement", "anchored_difference",
                     "recent_displacement", "recent_difference"):
            self.vertical_combo.addItem("", mode)
        self.vertical_combo.currentIndexChanged.connect(self._Render)
        controls.addWidget(self.vertical_label)
        controls.addWidget(self.vertical_combo)
        self.quality_label = QLabel()
        self.quality_combo = StandardComboBox()
        self.quality_combo.addItem("", "position")
        self.quality_combo.addItem("", "velocity")
        self.quality_combo.currentIndexChanged.connect(self._Render)
        controls.addWidget(self.quality_label)
        controls.addWidget(self.quality_combo)
        controls.addStretch(1)
        layout.addLayout(controls)
        self.note = QLabel()
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.plot_tabs = QTabWidget()
        self.plots = tuple(pg.PlotWidget() for _ in range(5))
        for plot in self.plots:
            plot.setMinimumHeight(240)
            plot.addLegend()
            _Plot_Prepare(plot, self._theme)
            self.plot_tabs.addTab(plot, "")
        layout.addWidget(self.plot_tabs, 1)
        self.plot_tabs.currentChanged.connect(self._ModeControls_Update)
        self.Language_Apply(translator)
        self._ModeControls_Update()

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

    def _ModeControls_Update(self, *_args):
        tab = self.plot_tabs.currentIndex()
        for widgets, visible in (
            ((self.axis_label, self.axis_combo), tab == 0),
            ((self.closure_label, self.closure_combo), tab == 1),
            ((self.vertical_label, self.vertical_combo), tab == 2),
            ((self.quality_label, self.quality_combo), tab == 3),
        ):
            for widget in widgets:
                widget.setVisible(visible)

    def _Trace_Draw(self, plot, time, traces, title, unit, resets=None):
        colors = ("#2b77c2", "#ec8a20", "#1a9d6c")
        for index, (values, name) in enumerate(traces):
            plotted = np.asarray(values, dtype=np.float64).copy()
            if resets is not None:
                reset_indices = np.flatnonzero(resets)
                plotted[reset_indices[1:]] = np.nan
            plot.plot(time, plotted, pen=pg.mkPen(colors[index], width=1.5),
                      connect="finite", name=name)
        plot.setTitle(title)
        plot.setLabel("left", unit)
        plot.setLabel("bottom", self._translator.Text_Get("timeline.time"))
        if resets is not None:
            for index in np.flatnonzero(resets):
                plot.addItem(pg.InfiniteLine(
                    pos=float(time[index]), angle=90,
                    pen=pg.mkPen("#9299a5", width=1),
                ))

    def _Render(self, *_args):
        result = self._result
        if result is None:
            return
        _Plot_Reset(self.plots)
        t = (result.timestamp_us.astype(np.float64) - self._origin) * 1e-6
        label = self._translator.Text_Get
        anchored_pos = result.anchored_position_displacement_m
        anchored_vel = result.anchored_velocity_displacement_m
        if anchored_pos is None or anchored_vel is None:
            anchored_pos = result.position_displacement_m
            anchored_vel = result.velocity_displacement_m
        axis = int(self.axis_combo.currentData())
        self._Trace_Draw(
            self.plots[0], t,
            ((anchored_pos[:, axis], label("integrity.position_change")),
             (anchored_vel[:, axis], label("integrity.velocity_integral"))),
            label("integrity.displacement") + f" · {'E' if axis == 0 else 'N'}",
            "m", result.anchor_reset_en,
        )
        recent = np.linalg.norm(result.residual_m[:, :2], axis=1)
        recent[~result.valid_en] = np.nan
        anchored = np.linalg.norm(result.anchored_residual_m[:, :2], axis=1)
        anchored[~result.anchored_valid_en] = np.nan
        closure_mode = self.closure_combo.currentData()
        if closure_mode == "recent":
            closure_values = recent
            closure_title = label("integrity.closure_recent").format(
                seconds=result.window_s
            )
            closure_resets = None
        else:
            closure_values = (
                result.anchored_residual_m[:, 0]
                if closure_mode == "anchored_e" else
                result.anchored_residual_m[:, 1]
                if closure_mode == "anchored_n" else anchored
            )
            closure_title = label("integrity.closure_cumulative")
            closure_resets = result.anchor_reset_en
        self._Trace_Draw(
            self.plots[1], t, ((closure_values, closure_title),),
            closure_title, "m", closure_resets,
        )
        vertical_mode = self.vertical_combo.currentData()
        if vertical_mode.startswith("anchored"):
            vertical_pos = anchored_pos[:, 2]
            vertical_vel = anchored_vel[:, 2]
            vertical_residual = result.anchored_residual_m[:, 2]
            vertical_resets = result.anchor_reset_u
            vertical_title = label("integrity.vertical_cumulative")
        else:
            vertical_pos = result.position_displacement_m[:, 2]
            vertical_vel = result.velocity_displacement_m[:, 2]
            vertical_residual = result.residual_m[:, 2]
            vertical_resets = None
            vertical_title = label("integrity.vertical_recent").format(
                seconds=result.window_s
            )
        vertical_traces = (
            ((vertical_residual, label("integrity.vertical_difference")),)
            if vertical_mode.endswith("difference")
            else ((vertical_pos, label("integrity.position_change")),
                  (vertical_vel, label("integrity.velocity_integral")))
        )
        self._Trace_Draw(
            self.plots[2], t, vertical_traces, vertical_title, "m",
            vertical_resets,
        )
        if self.quality_combo.currentData() == "velocity":
            quality_traces = ((result.quality[:, 2], label("integrity.sacc")),)
            quality_unit = "m/s"
        else:
            quality_traces = (
                (result.quality[:, 0], label("integrity.hacc")),
                (result.quality[:, 1], label("integrity.vacc")),
            )
            quality_unit = "m"
        self._Trace_Draw(
            self.plots[3], t, quality_traces,
            label("integrity.receiver_precision"), quality_unit,
        )
        self._Trace_Draw(
            self.plots[4], t,
            ((result.quality[:, 3], label("integrity.satellites_label")),),
            label("integrity.satellites"), label("integrity.satellites_unit"),
        )
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
        if self._result is not None:
            resets = np.flatnonzero(self._result.anchor_reset_en)
            visible = [index for index in resets
                       if float(self._result.timestamp_us[index] - self._origin) * 1e-6 <= end]
            if visible:
                index = visible[-1]
                reference_time = float(self._result.timestamp_us[index] - self._origin) * 1e-6
                self.note.setText(self._translator.Text_Get(
                    "integrity.reference_current",
                    segment=len(visible), time=reference_time,
                ) + "\n" + self._translator.Text_Get("integrity.analysis_only"))
            else:
                self.note.setText(self._translator.Text_Get(
                    "integrity.warmup", seconds=self._result.window_s,
                ) + "\n" + self._translator.Text_Get("integrity.analysis_only"))

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
        lines.append(self._translator.Text_Get(
            "integrity.anchor_resets",
            en=max(0, int(np.count_nonzero(self._result.anchor_reset_en)) - 1),
            u=max(0, int(np.count_nonzero(self._result.anchor_reset_u)) - 1),
        ))
        self.summary.setText(
            self._translator.Text_Get("integrity.summary_scope") + "\n" +
            "\n".join(lines)
        )

    def Theme_Apply(self, theme):
        self._theme = theme
        for plot in self.plots:
            _Plot_Prepare(plot, theme)

    def Language_Apply(self, translator):
        self._translator = translator
        self.window_label.setText(translator.Text_Get("integrity.window"))
        self.axis_label.setText(translator.Text_Get("integrity.component"))
        self.closure_label.setText(translator.Text_Get("integrity.display"))
        self.vertical_label.setText(translator.Text_Get("integrity.display"))
        self.quality_label.setText(translator.Text_Get("integrity.display"))
        for combo, codes in (
            (self.closure_combo, ("integrity.cumulative_magnitude",
                                  "integrity.recent_magnitude",
                                  "integrity.cumulative_e",
                                  "integrity.cumulative_n")),
            (self.vertical_combo, ("integrity.vertical_cumulative_displacement",
                                   "integrity.vertical_cumulative_difference",
                                   "integrity.vertical_recent_displacement",
                                   "integrity.vertical_recent_difference")),
            (self.quality_combo, ("integrity.position_precision",
                                  "integrity.velocity_precision")),
        ):
            for index, code in enumerate(codes):
                combo.setItemText(index, translator.Text_Get(code))
        self.note.setText(translator.Text_Get("integrity.analysis_only"))
        for index, code in enumerate((
            "integrity.displacement", "integrity.closure", "integrity.vertical",
            "integrity.quality", "integrity.satellites",
        )):
            self.plot_tabs.setTabText(index, translator.Text_Get(code))
        self._Render()

    def ChartViews_Reset(self):
        _PlotViews_Reset(self.plots)
