"""Transient controls for KF6 diagnostics, hosted inside the Replay workspace."""

from __future__ import annotations

import pyqtgraph as pg
from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from silverstar_flp.plugins.algorithms.kf6.diagnostics import (
    DiagnosticResult_Export,
    Kf6DiagnosticOptions,
)
from silverstar_flp.ui.touch_scroll import TouchScroll_Enable
from silverstar_flp.ui.widgets import StandardComboBox


class OfflineDiagnosticsPanel(QWidget):
    requested = Signal(str)

    def __init__(self, translator):
        super().__init__()
        self._translator = translator
        self._scan = None
        self._metadata = None
        self._busy = False
        self._available = False
        self._labels = []
        layout = QVBoxLayout(self)
        self.mode_badge = QLabel()
        self.mode_badge.setWordWrap(True)
        self.mode_badge.setObjectName("warningLabel")
        layout.addWidget(self.mode_badge)
        self.result_badge = QLabel()
        self.result_badge.setWordWrap(True)
        layout.addWidget(self.result_badge)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        TouchScroll_Enable(scroll)
        body = QWidget()
        form = QFormLayout(body)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.mode = StandardComboBox()
        self.mode.addItems(["", ""])
        self.restore = QPushButton()
        self.manual = QCheckBox()
        self.shift = QSpinBox()
        self.shift.setRange(-500, 500)
        self.shift.setSingleStep(5)
        self.shift.setSuffix(" ms")
        self.reset_shift = QPushButton()
        self.baro_enabled = QCheckBox()
        self.baro_sigma = QDoubleSpinBox()
        self.baro_sigma.setRange(1.5, 100)
        self.baro_sigma.setSingleStep(0.25)
        self.baro_sigma.setValue(2)
        self.baro_sigma.setSuffix(" m")
        self.pu_disabled = QCheckBox()
        for control in (self.manual, self.baro_enabled, self.pu_disabled):
            control.setMinimumHeight(48)
        self.hint = QLabel()
        self.hint.setWordWrap(True)
        for key, widget in [
            ("mode", self.mode),
            ("restore", self.restore),
            ("manual", self.manual),
            ("shift", self.shift),
            ("reset_shift", self.reset_shift),
            ("baro_override", self.baro_enabled),
            ("baro_sigma", self.baro_sigma),
            ("pu_disabled", self.pu_disabled),
        ]:
            label = QLabel()
            label.setWordWrap(True)
            self._labels.append((key, label))
            form.addRow(label, widget)
        form.addRow(self.hint)
        self.actions = {}
        for key in ("inspect", "replay", "scan", "apply_best", "export"):
            button = QPushButton()
            self.actions[key] = button
            form.addRow(button)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        form.addRow(self.summary)
        self.weight_heading = QLabel()
        self.weight_heading.setWordWrap(True)
        form.addRow(self.weight_heading)
        self.weights = QTableWidget(0, 9)
        self.weights.setMinimumHeight(220)
        self.weights.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.weights.verticalHeader().hide()
        TouchScroll_Enable(self.weights)
        form.addRow(self.weights)
        scroll.setWidget(body)
        layout.addWidget(scroll, 3)
        self.plot = pg.PlotWidget()
        self.plot.setMinimumHeight(130)
        self.plot.showGrid(x=True, y=True, alpha=0.2)
        layout.addWidget(self.plot, 1)
        self.reset_chart = QPushButton()
        layout.addWidget(self.reset_chart)
        self.reset_chart.clicked.connect(lambda: self.plot.enableAutoRange())
        self.mode.currentIndexChanged.connect(self._Changed)
        for control in (self.manual, self.baro_enabled, self.pu_disabled):
            control.toggled.connect(self._Changed)
        self.shift.valueChanged.connect(self._Changed)
        self.baro_sigma.valueChanged.connect(self._Changed)
        self.restore.clicked.connect(self.Firmware_Restore)
        self.reset_shift.clicked.connect(self.Shift_Reset)
        for operation in ("inspect", "replay", "scan"):
            self.actions[operation].clicked.connect(
                lambda _checked=False, op=operation: self.requested.emit(op)
            )
        self.actions["apply_best"].clicked.connect(self.Best_Apply)
        self.actions["export"].clicked.connect(self._Export)
        self.Language_Apply(translator)
        self.Firmware_Restore()
        self._Theme_Apply()

    def Options_Get(self):
        if self.mode.currentIndex() == 0:
            return None
        return Kf6DiagnosticOptions(
            velocity_shift_ms=self.shift.value() if self.manual.isChecked() else 0,
            baro_effective_sigma_m=self.baro_sigma.value()
            if self.baro_enabled.isChecked()
            else None,
            gnss_position_vertical_disabled=self.pu_disabled.isChecked(),
        )

    def Firmware_Restore(self):
        for widget in (
            self.mode,
            self.manual,
            self.shift,
            self.baro_enabled,
            self.baro_sigma,
            self.pu_disabled,
        ):
            widget.blockSignals(True)
        self.mode.setCurrentIndex(0)
        self.manual.setChecked(False)
        self.shift.setValue(0)
        self.baro_enabled.setChecked(False)
        self.baro_sigma.setValue(2)
        self.pu_disabled.setChecked(False)
        for widget in (
            self.mode,
            self.manual,
            self.shift,
            self.baro_enabled,
            self.baro_sigma,
            self.pu_disabled,
        ):
            widget.blockSignals(False)
        self._Changed()

    def Shift_Reset(self):
        self.shift.setValue(0)
        self.manual.setChecked(False)

    def _Changed(self, *_):
        self.Scan_Clear()
        self._Controls_Refresh()

    def Scan_Clear(self):
        self._scan = None
        if hasattr(self, "plot"):
            self.plot.clear()
        self.summary.setText("")
        self.actions["apply_best"].setEnabled(False)

    def Context_Clear(self):
        self._metadata = None
        self.result_badge.clear()
        self.weights.setRowCount(0)
        self.Firmware_Restore()

    def Available_Set(self, value):
        self._available = value
        self._Controls_Refresh()

    def Busy_Set(self, value):
        self._busy = value
        self._Controls_Refresh()

    def _Controls_Refresh(self):
        active = self.mode.currentIndex() == 1
        available = self._available and not self._busy
        self.mode.setEnabled(available)
        self.restore.setEnabled(available)
        for w in (self.manual, self.baro_enabled, self.pu_disabled):
            w.setEnabled(active and available)
        self.shift.setEnabled(active and available and self.manual.isChecked())
        self.reset_shift.setEnabled(active and available)
        self.baro_sigma.setEnabled(active and available and self.baro_enabled.isChecked())
        for key in ("inspect", "replay", "scan"):
            self.actions[key].setEnabled(available)
        self.actions["apply_best"].setEnabled(available and self._scan is not None)
        self.actions["export"].setEnabled(not self._busy and self._metadata is not None)
        self.mode_badge.setText(
            self._translator.Text_Get(
                "diagnostic.analysis_notice" if active else "diagnostic.faithful_notice"
            )
        )

    def Result_Error(self, message):
        self.summary.setText(message)

    def Result_Set(self, result):
        self._metadata = dict(result.diagnostics.get("offline_diagnostics", {}))
        self._Result_Refresh()
        self._Controls_Refresh()

    def _Result_Refresh(self):
        if not self._metadata:
            return
        tr = self._translator.Text_Get
        mode = self._metadata["mode"]
        options = self._metadata.get("analysis_only_overrides", {})
        self.result_badge.setText(
            tr(
                "diagnostic.result_summary",
                mode=tr(
                    "diagnostic.analysis" if mode == "analysis_only" else "diagnostic.faithful"
                ),
                shift=options.get("velocity_shift_ms", 0),
                baro=options.get("baro_effective_sigma_m") or tr("diagnostic.off"),
                pu=tr(
                    "diagnostic.disabled"
                    if options.get("gnss_position_vertical_disabled")
                    else "diagnostic.enabled"
                ),
            )
        )
        parameters = self._metadata.get("firmware_parameters", {})
        self.result_badge.setText(
            self.result_badge.text()
            + "\n"
            + tr(
                "diagnostic.parameter_summary",
                pu=parameters.get("gnss_position_std_vertical", "—"),
                scale=parameters.get("gnss_velocity_vertical_scale", "—"),
                outage=parameters.get("gnss_reacquire_outage_ms", "—"),
            )
        )
        weights = self._metadata.get("measurement_weights", [])
        self.weights.setRowCount(len(weights))

        def display(value):
            if value is None:
                return tr("status.na")
            if isinstance(value, dict):
                return f"{value['min']:.4g} / {value['median']:.4g} / {value['max']:.4g}"
            return str(value)

        for row, item in enumerate(weights):
            fields = [
                tr("diagnostic.group." + item["group"]),
                item["configured_sigma"],
                item["native_sigma"],
                f"{item['receiver_scale']} × {item['vertical_scale']}",
                item["origin_variance"],
                item["firmware_effective_sigma"],
                item["effective_sigma"],
                item["effective_R"],
                tr("diagnostic.rule." + item["rule"]),
            ]
            for col, value in enumerate(fields):
                cell = QTableWidgetItem(display(value))
                cell.setToolTip(display(value))
                self.weights.setItem(row, col, cell)
        self.weights.resizeColumnsToContents()

    def Scan_Set(self, scan):
        self._scan = scan
        self._metadata = scan.get("offline_diagnostics")
        self._Result_Refresh()
        self.summary.setText(
            self._translator.Text_Get(
                "diagnostic.scan_summary",
                best=scan["best_shift_ms"],
                zero=f"{scan['score_zero_ms']:.5g}",
                score=f"{scan['score_best']:.5g}",
                improvement="—"
                if scan["improvement_percent"] is None
                else f"{scan['improvement_percent']:.2f}",
                width=scan["sampled_minimum_width_ms"],
            )
        )
        self.plot.clear()
        self.plot.plot(
            [r["shift_ms"] for r in scan["runs"]],
            [r["score"] for r in scan["runs"]],
            pen=pg.mkPen(self.palette().highlight().color(), width=2),
        )
        self._Controls_Refresh()

    def Best_Apply(self):
        if self._scan is None:
            return
        best = self._scan["best_shift_ms"]
        for w in (self.mode, self.manual, self.shift):
            w.blockSignals(True)
        self.mode.setCurrentIndex(1)
        self.manual.setChecked(True)
        self.shift.setValue(best)
        for w in (self.mode, self.manual, self.shift):
            w.blockSignals(False)
        self._Controls_Refresh()
        self.requested.emit("replay")

    def _Export(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            self._translator.Text_Get("diagnostic.export"),
            "KF6_diagnostic.json",
            "JSON (*.json)",
        )
        if not path:
            return
        try:
            DiagnosticResult_Export(path, self._metadata, self._scan)
        except (OSError, ValueError, TypeError) as exc:
            self.summary.setText(
                self._translator.Text_Get("diagnostic.export_error", error=str(exc))
            )

    def Language_Apply(self, translator):
        self._translator = translator
        tr = translator.Text_Get
        self.mode.setItemText(0, tr("diagnostic.faithful"))
        self.mode.setItemText(1, tr("diagnostic.analysis"))
        for key, label in self._labels:
            label.setText(tr("diagnostic." + key))
        self.restore.setText(tr("diagnostic.restore"))
        self.reset_shift.setText(tr("diagnostic.reset_shift"))
        self.hint.setText(tr("diagnostic.sign_hint"))
        self.weight_heading.setText(tr("diagnostic.inspector"))
        for key, button in self.actions.items():
            button.setText(tr("diagnostic." + key))
        self.reset_chart.setText(tr("diagnostic.reset_chart"))
        self.weights.setHorizontalHeaderLabels(
            [
                tr("diagnostic.column." + k)
                for k in (
                    "group",
                    "configured",
                    "native",
                    "scale",
                    "origin",
                    "firmware",
                    "effective",
                    "R",
                    "rule",
                )
            ]
        )
        self.plot.setLabel("bottom", tr("diagnostic.shift"), units="ms")
        self.plot.setLabel("left", tr("diagnostic.score"))
        self._Controls_Refresh()
        self._Result_Refresh()
        if self._scan is not None:
            self.Scan_Set(self._scan)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.PaletteChange and hasattr(self, "plot"):
            self._Theme_Apply()

    def _Theme_Apply(self):
        self.plot.setBackground(self.palette().base().color())
        for name in ("left", "bottom"):
            self.plot.getAxis(name).setTextPen(self.palette().text().color())
            self.plot.getAxis(name).setPen(self.palette().text().color())
