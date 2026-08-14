from __future__ import annotations

from collections.abc import Mapping

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLayout,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from silverstar_flp.core.comparison import Series_Compare
from silverstar_flp.core.dataset import FlightDataset
from silverstar_flp.core.i18n import Translator
from silverstar_flp.plugins.api.algorithm import AlgorithmResult, ReplayMode, ReplayRequest
from silverstar_flp.plugins.registry import PluginRegistry
from silverstar_flp.ui.widgets import StandardComboBox


class ReplayPage(QWidget):
    replayRequested = Signal(str, object)

    def __init__(self, translator: Translator, registry: PluginRegistry) -> None:
        super().__init__()
        self._translator = translator
        self._registry = registry
        self._dataset: FlightDataset | None = None
        self._last_result: AlgorithmResult | None = None
        self._parameter_widgets: dict[str, QDoubleSpinBox] = {}
        self._parameter_labels: dict[str, QLabel] = {}

        page_layout = QVBoxLayout(self)
        page_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_content = QWidget()
        content_layout = QVBoxLayout(scroll_content)
        content_layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        content_layout.setContentsMargins(12, 10, 12, 14)
        content_layout.setSpacing(10)

        self.controls_group = QGroupBox()
        self.controls_form = QFormLayout(self.controls_group)
        self.controls_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.algorithm_label = QLabel()
        self.algorithm_combo = StandardComboBox()
        for plugin in registry.algorithms:
            self.algorithm_combo.addItem(plugin.metadata.display_name, plugin.metadata.plugin_id)
        self.source_label = QLabel()
        self.source_combo = StandardComboBox()
        self.mode_label = QLabel()
        self.mode_combo = StandardComboBox()
        self.fidelity_label = QLabel()
        self.availability_label = QLabel("—")
        self.availability_label.setWordWrap(True)
        self.controls_form.addRow(self.algorithm_label, self.algorithm_combo)
        self.controls_form.addRow(self.source_label, self.source_combo)
        self.controls_form.addRow(self.mode_label, self.mode_combo)
        self.controls_form.addRow(self.fidelity_label, self.availability_label)
        content_layout.addWidget(self.controls_group)

        self.parameters_group = QGroupBox()
        self.parameters_form = QFormLayout(self.parameters_group)
        self.parameters_form.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow
        )
        content_layout.addWidget(self.parameters_group)

        action_layout = QHBoxLayout()
        self.run_button = QPushButton()
        self.run_button.setObjectName("primaryButton")
        self.run_button.clicked.connect(self._Replay_Request)
        self.result_label = QLabel("—")
        self.result_label.setWordWrap(True)
        action_layout.addWidget(self.run_button)
        action_layout.addWidget(self.result_label, 1)
        content_layout.addLayout(action_layout)

        self.comparison_group = QGroupBox()
        comparison_layout = QVBoxLayout(self.comparison_group)
        self.comparison_table = QTableWidget(0, 5)
        self.comparison_table.setMinimumHeight(280)
        self.comparison_table.horizontalHeader().setStretchLastSection(True)
        self.comparison_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.comparison_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.comparison_table.verticalHeader().setVisible(False)
        comparison_layout.addWidget(self.comparison_table)
        content_layout.addWidget(self.comparison_group)
        content_layout.addStretch(1)

        self.scroll_area.setWidget(scroll_content)
        page_layout.addWidget(self.scroll_area)

        self.algorithm_combo.currentIndexChanged.connect(self._Algorithm_Refresh)
        self.source_combo.currentIndexChanged.connect(self._Availability_Refresh)
        self.mode_combo.currentIndexChanged.connect(self._Mode_Refresh)
        self.Language_Apply(translator)
        self._Algorithm_Refresh()

    def Dataset_Set(
        self,
        dataset: FlightDataset,
        results: Mapping[str, AlgorithmResult] | None = None,
    ) -> None:
        self._dataset = dataset
        self._Availability_Refresh()

    def _Algorithm_Refresh(self) -> None:
        while self.parameters_form.rowCount():
            self.parameters_form.removeRow(0)
        self._parameter_widgets = {}
        self._parameter_labels = {}
        plugin = self._CurrentPlugin_Get()
        for parameter in plugin.metadata.parameter_schema:
            if parameter.kind != "float":
                continue
            editor = QDoubleSpinBox()
            editor.setDecimals(6)
            editor.setKeyboardTracking(False)
            editor.setRange(
                parameter.minimum if parameter.minimum is not None else -1.0e12,
                parameter.maximum if parameter.maximum is not None else 1.0e12,
            )
            editor.setValue(float(parameter.default))
            editor.setSuffix(f" {parameter.unit}" if parameter.unit else "")
            label = QLabel(self._Parameter_Label(parameter.parameter_id))
            label.setToolTip(parameter.parameter_id)
            self.parameters_form.addRow(label, editor)
            self._parameter_widgets[parameter.parameter_id] = editor
            self._parameter_labels[parameter.parameter_id] = label
        self._Mode_Refresh()
        self._Availability_Refresh()

    def _Parameter_Label(self, parameter_id: str) -> str:
        code = f"parameter.{parameter_id}"
        translated = self._translator.Text_Get(code)
        return parameter_id if translated == code else translated

    def _Mode_Refresh(self) -> None:
        what_if = self.mode_combo.currentData() == ReplayMode.WHAT_IF
        self.parameters_group.setEnabled(what_if)

    def _CurrentPlugin_Get(self):
        return self._registry.Algorithm_Get(str(self.algorithm_combo.currentData()))

    def _Availability_Refresh(self) -> None:
        if self._dataset is None:
            self.availability_label.setText(self._translator.Text_Get("status.no_data"))
            self.run_button.setEnabled(False)
            return
        plugin = self._CurrentPlugin_Get()
        source = str(self.source_combo.currentData())
        availability = plugin.availability(self._dataset, source)
        details = availability.fidelity.value
        if availability.missing_inputs:
            details += " · " + self._translator.Text_Get(
                "replay.missing_inputs", values=", ".join(availability.missing_inputs)
            )
        if availability.warnings:
            details += " · " + "; ".join(availability.warnings)
        self.availability_label.setText(details)
        self.run_button.setEnabled(availability.available)

    def _Replay_Request(self) -> None:
        mode = self.mode_combo.currentData()
        parameters = (
            {name: editor.value() for name, editor in self._parameter_widgets.items()}
            if mode == ReplayMode.WHAT_IF
            else {}
        )
        request = ReplayRequest(
            mode=mode,
            input_source=str(self.source_combo.currentData()),
            parameters=parameters,
        )
        self.run_button.setEnabled(False)
        self.result_label.setText(self._translator.Text_Get("replay.running"))
        self.replayRequested.emit(str(self.algorithm_combo.currentData()), request)

    def Result_Set(self, result: AlgorithmResult) -> None:
        self._last_result = result
        provenance_codes = {
            "Recorded": "status.recorded",
            "Recomputed": "status.recomputed",
            "What-if": "status.what_if",
        }
        provenance = self._translator.Text_Get(
            provenance_codes.get(result.provenance, "status.recomputed")
        )
        self.result_label.setText(
            self._translator.Text_Get(
                "replay.result",
                provenance=provenance,
                fidelity=result.fidelity.value,
                count=result.diagnostics.get("output_count", 0),
            )
        )
        self.run_button.setEnabled(True)
        self._Comparison_Set(result)

    def Result_Error(self, message: str) -> None:
        self.result_label.setText(message)
        self._Availability_Refresh()

    def Task_Finish(self) -> None:
        self._Availability_Refresh()

    def _Comparison_Set(self, result: AlgorithmResult) -> None:
        if self._dataset is None:
            return
        if result.algorithm_id.endswith("pure_ins"):
            mappings = (
                ("comparison.attitude", "pure_ins.recorded.attitude.q_nb", "attitude.q_nb", True),
                (
                    "comparison.velocity",
                    "pure_ins.recorded.navigation.velocity_enu",
                    "navigation.velocity_enu",
                    False,
                ),
                (
                    "comparison.position",
                    "pure_ins.recorded.navigation.position_enu",
                    "navigation.position_enu",
                    False,
                ),
            )
        else:
            mappings = (
                (
                    "comparison.velocity",
                    "kf6.recorded.navigation.velocity_enu",
                    "navigation.velocity_enu",
                    False,
                ),
                (
                    "comparison.position",
                    "kf6.recorded.navigation.position_enu",
                    "navigation.position_enu",
                    False,
                ),
            )
        rows: list[tuple[str, object]] = []
        for name_code, recorded_id, recomputed_id, quaternion in mappings:
            recorded = self._dataset.Series_Get(recorded_id)
            recomputed = result.channels.get(recomputed_id)
            if recorded is None or recomputed is None:
                continue
            comparison = Series_Compare(recorded, recomputed, quaternion=quaternion)
            rows.append((self._translator.Text_Get(name_code), comparison))
        self.comparison_table.setRowCount(len(rows))
        for row, (name, comparison) in enumerate(rows):
            statistics = comparison.statistics
            values = (
                name,
                str(statistics.sample_count),
                f"{statistics.mean_absolute_error:.6g} {comparison.unit}",
                f"{statistics.root_mean_square_error:.6g} {comparison.unit}",
                f"{statistics.maximum_absolute_error:.6g} {comparison.unit}",
            )
            for column, value in enumerate(values):
                self.comparison_table.setItem(row, column, QTableWidgetItem(value))
        self.comparison_table.resizeColumnsToContents()

    def _ComboLabels_Refresh(self) -> None:
        source = self.source_combo.currentData() or "recorded_inertial_increment"
        mode = self.mode_combo.currentData() or ReplayMode.RECORDED_CONFIGURATION
        self.source_combo.blockSignals(True)
        self.source_combo.clear()
        self.source_combo.addItem(
            self._translator.Text_Get("replay.source.recorded_increment"),
            "recorded_inertial_increment",
        )
        self.source_combo.addItem(
            self._translator.Text_Get("replay.source.corrected_imu"), "corrected_imu"
        )
        self.source_combo.setCurrentIndex(max(self.source_combo.findData(source), 0))
        self.source_combo.blockSignals(False)

        self.mode_combo.blockSignals(True)
        self.mode_combo.clear()
        self.mode_combo.addItem(
            self._translator.Text_Get("replay.mode.recorded"),
            ReplayMode.RECORDED_CONFIGURATION,
        )
        self.mode_combo.addItem(
            self._translator.Text_Get("replay.mode.what_if"), ReplayMode.WHAT_IF
        )
        self.mode_combo.setCurrentIndex(max(self.mode_combo.findData(mode), 0))
        self.mode_combo.blockSignals(False)

    def Language_Apply(self, translator: Translator) -> None:
        self._translator = translator
        self._ComboLabels_Refresh()
        self.controls_group.setTitle(translator.Text_Get("replay.configuration"))
        self.algorithm_label.setText(translator.Text_Get("label.algorithm"))
        self.source_label.setText(translator.Text_Get("label.input_source"))
        self.mode_label.setText(translator.Text_Get("label.mode"))
        self.fidelity_label.setText(translator.Text_Get("label.fidelity"))
        self.parameters_group.setTitle(translator.Text_Get("replay.what_if_parameters"))
        self.run_button.setText(translator.Text_Get("action.run_replay"))
        self.comparison_group.setTitle(translator.Text_Get("replay.comparison"))
        self.comparison_table.setHorizontalHeaderLabels(
            [
                translator.Text_Get("comparison.channel"),
                translator.Text_Get("comparison.samples"),
                "MAE",
                "RMSE",
                translator.Text_Get("comparison.maximum_error"),
            ]
        )
        for parameter_id, label in self._parameter_labels.items():
            label.setText(self._Parameter_Label(parameter_id))
        self._Mode_Refresh()
        self._Availability_Refresh()
        if self._last_result is not None:
            self.Result_Set(self._last_result)
