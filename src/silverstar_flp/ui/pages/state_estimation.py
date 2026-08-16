from __future__ import annotations

from collections.abc import Mapping

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from silverstar_flp.core.analysis_source import (
    AnalysisSource,
    AnalysisSourceKind,
    ChannelResolver,
    ReplayResultStore,
)
from silverstar_flp.core.dataset import FlightDataset, TimeSeries
from silverstar_flp.core.i18n import Translator
from silverstar_flp.plugins.api.algorithm import (
    EstimatorVisualizationSpec,
    MeasurementGroupSpec,
    StateGroupSpec,
)
from silverstar_flp.plugins.registry import PluginRegistry, builtin_registry
from silverstar_flp.ui.pages.charts import (
    TraceColorAllocator,
    _NearestIndex,
    _Plot_Prepare,
    _Plot_Reset,
    _PlotViews_Reset,
    _Series_Plot,
    _Source_Label,
)
from silverstar_flp.ui.widgets import StandardComboBox


def _Series_ComponentsSelect(
    series: TimeSeries | None,
    indices: tuple[int, ...],
    columns: tuple[str, ...],
    *,
    unit: str | None = None,
    quantity: str | None = None,
) -> TimeSeries | None:
    if series is None or series.count == 0 or not indices:
        return None
    values = np.asarray(series.values, dtype=np.float64)
    if values.ndim == 1:
        values = values.reshape(-1, 1)
    if max(indices) >= values.shape[1]:
        return None
    selected = values[:, indices].copy()
    valid = np.asarray(series.valid, dtype=np.bool_) & np.all(np.isfinite(selected), axis=1)
    return TimeSeries(
        timestamp_us=series.timestamp_us,
        values=selected,
        unit=series.unit if unit is None else unit,
        quantity=series.quantity if quantity is None else quantity,
        source=series.source,
        valid=valid,
        columns=columns,
        metadata={**series.metadata, "display_derived": True},
    )


def _Series_ColumnSelect(series: TimeSeries | None, index: int) -> TimeSeries | None:
    selected = _Series_ComponentsSelect(
        series,
        (index,),
        (),
    )
    if selected is None:
        return None
    return TimeSeries(
        timestamp_us=selected.timestamp_us,
        values=np.asarray(selected.values)[:, 0],
        unit=selected.unit,
        quantity=selected.quantity,
        source=selected.source,
        valid=selected.valid,
        metadata=selected.metadata,
    )


class StateEstimationPage(QWidget):
    """Metadata-driven high-level estimator diagnostics."""

    def __init__(
        self,
        translator: Translator,
        registry: PluginRegistry | None = None,
    ) -> None:
        super().__init__()
        self._translator = translator
        self._registry = registry or builtin_registry()
        self._theme = "light"
        self._dataset: FlightDataset | None = None
        self._resolver: ChannelResolver | None = None
        self._estimator_source: AnalysisSource | None = None
        self._visualization: EstimatorVisualizationSpec | None = None
        self._source_parameters: Mapping[str, object] = {}

        layout = QVBoxLayout(self)
        source_row = QHBoxLayout()
        self.source_label = QLabel()
        self.source_value_label = QLabel("—")
        self.source_value_label.setObjectName("muted")
        self.diagnostic_label = QLabel()
        self.diagnostic_label.setObjectName("muted")
        source_row.addWidget(self.source_label)
        source_row.addWidget(self.source_value_label, 1)
        source_row.addWidget(self.diagnostic_label, 2)
        self.reset_charts_button = QPushButton()
        self.reset_charts_button.clicked.connect(self._ChartViews_Reset)
        source_row.addWidget(self.reset_charts_button)
        layout.addLayout(source_row)

        self.tabs = QTabWidget()
        self._CovarianceTab_Build()
        self._InnovationTab_Build()
        self._NisTab_Build()
        self._UpdatesTab_Build()
        self._MeasurementsTab_Build()
        layout.addWidget(self.tabs)
        self.Language_Apply(translator)

    def _CovarianceTab_Build(self) -> None:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        controls = QHBoxLayout()
        self.state_group_label = QLabel()
        self.state_group_combo = StandardComboBox()
        self.covariance_display_label = QLabel()
        self.covariance_display_combo = StandardComboBox()
        self.state_group_combo.currentIndexChanged.connect(self._Covariance_Refresh)
        self.covariance_display_combo.currentIndexChanged.connect(
            self._Covariance_Refresh
        )
        controls.addWidget(self.state_group_label)
        controls.addWidget(self.state_group_combo)
        controls.addSpacing(12)
        controls.addWidget(self.covariance_display_label)
        controls.addWidget(self.covariance_display_combo)
        controls.addStretch(1)
        layout.addLayout(controls)
        self.covariance_plot = self._Plot_Create()
        layout.addWidget(self.covariance_plot)
        self.tabs.addTab(widget, "")

    def _InnovationTab_Build(self) -> None:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        controls = QHBoxLayout()
        self.innovation_measurement_label = QLabel()
        self.innovation_measurement_combo = StandardComboBox()
        self.innovation_measurement_combo.currentIndexChanged.connect(
            self._Innovation_Refresh
        )
        controls.addWidget(self.innovation_measurement_label)
        controls.addWidget(self.innovation_measurement_combo)
        controls.addStretch(1)
        layout.addLayout(controls)
        self.innovation_plot = self._Plot_Create()
        layout.addWidget(self.innovation_plot)
        self.tabs.addTab(widget, "")

    def _NisTab_Build(self) -> None:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        controls = QHBoxLayout()
        self.nis_measurement_label = QLabel()
        self.nis_measurement_combo = StandardComboBox()
        self.nis_measurement_combo.currentIndexChanged.connect(self._Nis_Refresh)
        controls.addWidget(self.nis_measurement_label)
        controls.addWidget(self.nis_measurement_combo)
        controls.addStretch(1)
        layout.addLayout(controls)
        self.nis_plot = self._Plot_Create()
        layout.addWidget(self.nis_plot)
        self.tabs.addTab(widget, "")

    def _UpdatesTab_Build(self) -> None:
        self.update_table = QTableWidget(0, 7)
        self.update_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.update_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.update_table.verticalHeader().setVisible(False)
        self.tabs.addTab(self.update_table, "")

    def _MeasurementsTab_Build(self) -> None:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        controls = QHBoxLayout()
        self.measurement_group_label = QLabel()
        self.measurement_group_combo = StandardComboBox()
        self.measurement_group_combo.currentIndexChanged.connect(
            self._Measurements_Refresh
        )
        controls.addWidget(self.measurement_group_label)
        controls.addWidget(self.measurement_group_combo)
        controls.addStretch(1)
        layout.addLayout(controls)
        splitter = QSplitter(Qt.Orientation.Vertical)
        self.measurement_uncertainty_plot = self._Plot_Create()
        self.measurement_r_scale_plot = self._Plot_Create()
        self.measurement_age_plot = self._Plot_Create()
        splitter.addWidget(self.measurement_uncertainty_plot)
        splitter.addWidget(self.measurement_r_scale_plot)
        splitter.addWidget(self.measurement_age_plot)
        layout.addWidget(splitter)
        self.tabs.addTab(widget, "")

    def _Plot_Create(self) -> pg.PlotWidget:
        plot = pg.PlotWidget()
        plot.addLegend()
        _Plot_Prepare(plot, self._theme)
        return plot

    def _Plots_Get(self) -> tuple[pg.PlotWidget, ...]:
        return (
            self.covariance_plot,
            self.innovation_plot,
            self.nis_plot,
            self.measurement_uncertainty_plot,
            self.measurement_r_scale_plot,
            self.measurement_age_plot,
        )

    def _ChartViews_Reset(self) -> None:
        _PlotViews_Reset(self._Plots_Get())

    def Dataset_Set(
        self,
        dataset: FlightDataset,
        resolver: ChannelResolver | None = None,
    ) -> None:
        self._dataset = dataset
        self._resolver = resolver or ChannelResolver(dataset, ReplayResultStore())
        self._Estimator_Select()

    def _Estimator_Select(self) -> None:
        if self._dataset is None or self._resolver is None:
            self._Content_Clear()
            return
        algorithm_ids = tuple(
            plugin.metadata.plugin_id
            for plugin in self._registry.algorithms
            if plugin.metadata.estimator_visualization is not None
        )
        sources = self._resolver.EstimatorSources_Get(algorithm_ids)
        active = self._resolver.store.ActiveSource_Get()
        selected = next(
            (
                source
                for source in sources
                if active.kind != AnalysisSourceKind.RECORDED
                and source.source_id == active.source_id
            ),
            None,
        )
        if selected is None:
            recorded = [
                source for source in sources if source.kind == AnalysisSourceKind.RECORDED
            ]
            selected = max(recorded, key=self._SourceScore_Get, default=None)
        if selected is None:
            self._Content_Clear()
            return
        try:
            plugin = self._registry.Algorithm_Get(str(selected.algorithm_id))
        except KeyError:
            self._Content_Clear()
            return
        visualization = plugin.metadata.estimator_visualization
        if visualization is None:
            self._Content_Clear()
            return
        self._estimator_source = selected
        self._visualization = visualization
        if selected.kind == AnalysisSourceKind.RECORDED:
            self._source_parameters = plugin.recorded_parameters(self._dataset)
            self.diagnostic_label.setText(
                self._translator.Text_Get("state.recorded_diagnostic")
            )
        else:
            entry = self._resolver.store.SourceEntry_Get(selected.source_id)
            self._source_parameters = entry.parameters if entry is not None else {}
            self.diagnostic_label.setText(
                self._translator.Text_Get("state.recomputed_diagnostic")
            )
        self.source_value_label.setText(
            _Source_Label(self._translator, self._resolver, selected.source_id)
        )
        self._Selectors_Refresh()
        self._Refresh()

    def _SourceScore_Get(self, source: AnalysisSource) -> int:
        if self._resolver is None or source.algorithm_id is None:
            return -1
        try:
            plugin = self._registry.Algorithm_Get(source.algorithm_id)
        except KeyError:
            return -1
        visualization = plugin.metadata.estimator_visualization
        if visualization is None:
            return -1
        channels = [group.covariance_channel for group in visualization.state_groups]
        for group in visualization.measurement_groups:
            channels.extend(
                (
                    group.innovation_channel,
                    group.nis_channel,
                    group.update_result_channel,
                    group.r_scale_channel,
                    group.measurement_age_channel,
                    group.measurement_uncertainty_channel,
                    group.effective_r_channel,
                )
            )
        return sum(
            bool(channel_id)
            and self._resolver.Series_Get(channel_id, source.source_id) is not None
            for channel_id in channels
        )

    def _Content_Clear(self) -> None:
        self._estimator_source = None
        self._visualization = None
        self._source_parameters = {}
        self.source_value_label.setText(self._translator.Text_Get("status.na"))
        self.diagnostic_label.setText(self._translator.Text_Get("state.no_estimator_metadata"))
        for combo in (
            self.state_group_combo,
            self.innovation_measurement_combo,
            self.nis_measurement_combo,
            self.measurement_group_combo,
        ):
            combo.clear()
        _Plot_Reset(self._Plots_Get())
        self.update_table.setRowCount(0)

    def _Selectors_Refresh(self) -> None:
        if self._visualization is None:
            return
        self._Combo_Refresh(
            self.state_group_combo,
            (
                (group.group_id, self._translator.Text_Get(group.label_key))
                for group in self._visualization.state_groups
            ),
        )
        measurement_items = tuple(
            (
                group.measurement_group_id,
                self._translator.Text_Get(group.label_key),
            )
            for group in self._visualization.measurement_groups
        )
        for combo in (
            self.innovation_measurement_combo,
            self.nis_measurement_combo,
            self.measurement_group_combo,
        ):
            self._Combo_Refresh(combo, measurement_items)
        display = str(self.covariance_display_combo.currentData() or "standard_deviation")
        self.covariance_display_combo.blockSignals(True)
        self.covariance_display_combo.clear()
        self.covariance_display_combo.addItem(
            self._translator.Text_Get("state.standard_deviation_1sigma"),
            "standard_deviation",
        )
        self.covariance_display_combo.addItem(
            self._translator.Text_Get("state.variance_pii"),
            "variance",
        )
        index = self.covariance_display_combo.findData(display)
        self.covariance_display_combo.setCurrentIndex(max(index, 0))
        self.covariance_display_combo.blockSignals(False)

    @staticmethod
    def _Combo_Refresh(
        combo: StandardComboBox,
        items: object,
    ) -> None:
        selected = combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        for item_id, label in items:
            combo.addItem(label, item_id)
        index = combo.findData(selected)
        combo.setCurrentIndex(max(index, 0))
        combo.blockSignals(False)

    def _Refresh(self) -> None:
        if self._visualization is None:
            return
        self._Covariance_Refresh()
        self._Innovation_Refresh()
        self._Nis_Refresh()
        self._Measurements_Refresh()
        self._Updates_Set()

    def _StartTimestamp_Get(self) -> int:
        if self._dataset is None:
            return 0
        return (
            self._dataset.start_timestamp_us
            or self._dataset.diagnostics.first_timestamp_us
            or 0
        )

    def _Series_Get(self, channel_id: str) -> TimeSeries | None:
        if (
            not channel_id
            or self._resolver is None
            or self._estimator_source is None
        ):
            return None
        return self._resolver.Series_Get(channel_id, self._estimator_source.source_id)

    def _StateGroup_Get(self) -> StateGroupSpec | None:
        if self._visualization is None:
            return None
        group_id = self.state_group_combo.currentData()
        return next(
            (
                group
                for group in self._visualization.state_groups
                if group.group_id == group_id
            ),
            None,
        )

    def _MeasurementGroup_Get(
        self,
        combo: StandardComboBox,
    ) -> MeasurementGroupSpec | None:
        if self._visualization is None:
            return None
        group_id = combo.currentData()
        return next(
            (
                group
                for group in self._visualization.measurement_groups
                if group.measurement_group_id == group_id
            ),
            None,
        )

    def _Covariance_Refresh(self) -> None:
        _Plot_Reset((self.covariance_plot,))
        group = self._StateGroup_Get()
        if group is None:
            return
        raw = _Series_ComponentsSelect(
            self._Series_Get(group.covariance_channel),
            group.covariance_diagonal_indices,
            group.component_names,
        )
        if raw is None:
            return
        group_label = self._translator.Text_Get(group.label_key)
        values = np.asarray(raw.values, dtype=np.float64).copy()
        display = self.covariance_display_combo.currentData()
        if display == "variance":
            columns = tuple(f"P({name},{name})" for name in group.component_names)
            unit = f"({group.unit})²" if group.unit not in ("", "1") else "1"
        else:
            values[values < 0.0] = np.nan
            values = np.sqrt(values)
            columns = tuple(
                self._translator.Text_Get(
                    "state.standard_deviation_trace",
                    group=group_label,
                    component=name,
                )
                for name in group.component_names
            )
            unit = group.unit
        series = TimeSeries(
            timestamp_us=raw.timestamp_us,
            values=values,
            unit=unit,
            quantity="covariance",
            source=raw.source,
            valid=raw.valid & np.all(np.isfinite(values), axis=1),
            columns=columns,
            metadata=raw.metadata,
        )
        _Series_Plot(
            self.covariance_plot,
            series,
            self._StartTimestamp_Get(),
            colors=TraceColorAllocator(),
        )
        self.covariance_plot.setTitle(
            f"{self._translator.Text_Get('chart.covariance')} · {group_label}"
        )
        self.covariance_plot.setLabel("left", unit)

    def _MeasurementSeries_Get(
        self,
        channel_id: str,
        group: MeasurementGroupSpec,
    ) -> TimeSeries | None:
        return _Series_ComponentsSelect(
            self._Series_Get(channel_id),
            tuple(range(group.dimension)),
            group.component_names,
        )

    def _Innovation_Refresh(self) -> None:
        _Plot_Reset((self.innovation_plot,))
        group = self._MeasurementGroup_Get(self.innovation_measurement_combo)
        if group is None:
            return
        series = self._MeasurementSeries_Get(group.innovation_channel, group)
        label = self._translator.Text_Get(group.label_key)
        _Series_Plot(
            self.innovation_plot,
            series,
            self._StartTimestamp_Get(),
            colors=TraceColorAllocator(),
            prefix=f"{self._translator.Text_Get('chart.innovation')} ",
        )
        self.innovation_plot.setTitle(
            f"{self._translator.Text_Get('chart.innovation')} · {label}"
        )
        if series is not None:
            self.innovation_plot.setLabel("left", series.unit)

    def _Nis_Refresh(self) -> None:
        _Plot_Reset((self.nis_plot,))
        group = self._MeasurementGroup_Get(self.nis_measurement_combo)
        if group is None:
            return
        series = self._Series_Get(group.nis_channel)
        colors = TraceColorAllocator()
        _Series_Plot(
            self.nis_plot,
            series,
            self._StartTimestamp_Get(),
            colors=colors,
            prefix="NIS",
            width=1.8,
        )
        self._NisThreshold_Plot(
            series,
            group.soft_threshold_parameter_id,
            "state.nis_soft_threshold",
            Qt.PenStyle.DashLine,
            colors,
        )
        self._NisThreshold_Plot(
            series,
            group.hard_threshold_parameter_id,
            "state.nis_hard_threshold",
            Qt.PenStyle.DashDotLine,
            colors,
        )
        label = self._translator.Text_Get(group.label_key)
        self.nis_plot.setTitle(
            f"{self._translator.Text_Get('chart.nis_full')} · {label}"
        )
        self.nis_plot.setLabel("left", "1")

    def _NisThreshold_Plot(
        self,
        series: TimeSeries | None,
        parameter_id: str,
        label_key: str,
        style: Qt.PenStyle,
        colors: TraceColorAllocator,
    ) -> None:
        if series is None or not parameter_id:
            return
        try:
            threshold = float(self._source_parameters[parameter_id])
        except (KeyError, TypeError, ValueError):
            return
        if not np.isfinite(threshold):
            return
        selected = np.flatnonzero(
            series.valid
            & (series.timestamp_us >= np.uint64(self._StartTimestamp_Get()))
        )
        if selected.size == 0:
            return
        time = (
            series.timestamp_us[selected[[0, -1]]].astype(np.float64)
            - float(self._StartTimestamp_Get())
        ) * 1.0e-6
        self.nis_plot.plot(
            time,
            np.asarray((threshold, threshold), dtype=np.float64),
            pen=pg.mkPen(colors.Color_Next(), width=1.4, style=style),
            name=self._translator.Text_Get(label_key),
        )

    def _Measurements_Refresh(self) -> None:
        plots = (
            self.measurement_uncertainty_plot,
            self.measurement_r_scale_plot,
            self.measurement_age_plot,
        )
        _Plot_Reset(plots)
        group = self._MeasurementGroup_Get(self.measurement_group_combo)
        if group is None:
            return
        label = self._translator.Text_Get(group.label_key)
        uncertainty_colors = TraceColorAllocator()
        for channel_id, label_key in (
            (group.measurement_uncertainty_channel, "state.measurement_uncertainty"),
            (group.effective_r_channel, "state.effective_r"),
        ):
            _Series_Plot(
                self.measurement_uncertainty_plot,
                self._MeasurementSeries_Get(channel_id, group),
                self._StartTimestamp_Get(),
                colors=uncertainty_colors,
                prefix=f"{self._translator.Text_Get(label_key)} · ",
            )
        r_scale = _Series_ColumnSelect(
            self._Series_Get(group.r_scale_channel),
            group.r_scale_index,
        )
        _Series_Plot(
            self.measurement_r_scale_plot,
            r_scale,
            self._StartTimestamp_Get(),
            colors=TraceColorAllocator(),
            prefix=self._translator.Text_Get("state.r_scale_short"),
        )
        age = self._Series_Get(group.measurement_age_channel)
        _Series_Plot(
            self.measurement_age_plot,
            age,
            self._StartTimestamp_Get(),
            colors=TraceColorAllocator(),
            prefix=self._translator.Text_Get("state.measurement_age"),
        )
        self.measurement_uncertainty_plot.setTitle(
            f"{self._translator.Text_Get('chart.measurement_r')} · {label}"
        )
        self.measurement_r_scale_plot.setTitle(
            f"{self._translator.Text_Get('state.r_scale_short')} · {label}"
        )
        self.measurement_age_plot.setTitle(
            f"{self._translator.Text_Get('chart.measurement_age')} · {label}"
        )
        self.measurement_r_scale_plot.setLabel("left", "1")
        if age is not None:
            self.measurement_age_plot.setLabel("left", age.unit)

    def _Updates_Set(self) -> None:
        if self._visualization is None:
            self.update_table.setRowCount(0)
            return
        rows: list[tuple[int, int, tuple[str, ...]]] = []
        start = self._StartTimestamp_Get()
        for group_order, group in enumerate(self._visualization.measurement_groups):
            result_series = self._Series_Get(group.update_result_channel)
            if result_series is None:
                continue
            selected = np.flatnonzero(result_series.timestamp_us >= np.uint64(start))
            attempt_series = self._Series_Get(group.attempt_mask_channel)
            dimension_series = self._Series_Get(group.dimension_channel)
            nis_series = self._Series_Get(group.nis_channel)
            r_scale_series = self._Series_Get(group.r_scale_channel)
            age_series = self._Series_Get(group.measurement_age_channel)
            for index in selected:
                timestamp = int(result_series.timestamp_us[index])
                attempt = self._NearestValue_Get(attempt_series, timestamp, 0)
                if (
                    attempt_series is not None
                    and group.attempt_mask_bit
                    and (int(attempt) & group.attempt_mask_bit) == 0
                ):
                    continue
                result = self._SeriesValue_Get(
                    result_series,
                    int(index),
                    group.update_result_index,
                )
                dimension = self._NearestValue_Get(
                    dimension_series,
                    timestamp,
                    0,
                    fallback=float(group.dimension),
                )
                nis = self._NearestValue_Get(nis_series, timestamp, 0)
                r_scale = self._NearestValue_Get(
                    r_scale_series,
                    timestamp,
                    group.r_scale_index,
                )
                age = self._NearestValue_Get(age_series, timestamp, 0)
                age_text = self._Number_Text(age)
                if age_series is not None and age_text != "—" and age_series.unit:
                    age_text = f"{age_text} {age_series.unit}"
                values = (
                    f"{(timestamp - start) * 1.0e-6:.6f}",
                    self._translator.Text_Get(group.label_key),
                    str(int(dimension)) if np.isfinite(dimension) else "—",
                    self._UpdateResult_Text(result),
                    self._Number_Text(nis),
                    self._Number_Text(r_scale),
                    age_text,
                )
                rows.append((timestamp, group_order, values))
        rows.sort(key=lambda item: (item[0], item[1]))
        if len(rows) > 2000:
            indices = np.linspace(0, len(rows) - 1, 2000, dtype=int)
            rows = [rows[index] for index in indices]
        self.update_table.setRowCount(len(rows))
        for row, (_, _, values) in enumerate(rows):
            for column, value in enumerate(values):
                self.update_table.setItem(row, column, QTableWidgetItem(value))
        self.update_table.resizeColumnsToContents()

    @staticmethod
    def _SeriesValue_Get(series: TimeSeries, row: int, column: int) -> float:
        raw = np.asarray(series.values[row], dtype=np.float64)
        if raw.ndim == 0:
            return float(raw) if column == 0 else np.nan
        return float(raw[column]) if column < raw.size else np.nan

    @classmethod
    def _NearestValue_Get(
        cls,
        series: TimeSeries | None,
        timestamp_us: int,
        column: int,
        *,
        fallback: float = np.nan,
    ) -> float:
        if series is None or series.count == 0:
            return fallback
        index = _NearestIndex(series.timestamp_us, timestamp_us)
        return cls._SeriesValue_Get(series, index, column)

    @staticmethod
    def _Number_Text(value: float) -> str:
        return "—" if not np.isfinite(value) else f"{value:.6g}"

    def _UpdateResult_Text(self, value: float) -> str:
        codes = {
            0: "update.accepted",
            1: "update.soft_weighted",
            2: "update.nis_rejected",
            3: "update.invalid",
            4: "update.numeric_error",
            5: "update.not_attempted",
            -1: "update.not_attempted",
        }
        code = (
            codes.get(int(value), "update.unknown")
            if np.isfinite(value)
            else "update.not_attempted"
        )
        return self._translator.Text_Get(code)

    def Theme_Apply(self, theme: str) -> None:
        self._theme = theme
        for plot in self._Plots_Get():
            _Plot_Prepare(plot, theme)

    def Language_Apply(self, translator: Translator) -> None:
        self._translator = translator
        self.source_label.setText(translator.Text_Get("label.estimator_source"))
        self.reset_charts_button.setText(translator.Text_Get("action.reset_charts"))
        self.reset_charts_button.setToolTip(
            translator.Text_Get("action.reset_charts_tooltip")
        )
        self.state_group_label.setText(translator.Text_Get("state.state_group"))
        self.covariance_display_label.setText(translator.Text_Get("state.display"))
        for label in (
            self.innovation_measurement_label,
            self.nis_measurement_label,
            self.measurement_group_label,
        ):
            label.setText(translator.Text_Get("state.measurement"))
        tab_codes = (
            "tab.covariance",
            "tab.innovation",
            "tab.nis_full",
            "tab.sequential_updates",
            "tab.measurements",
        )
        for index, code in enumerate(tab_codes):
            self.tabs.setTabText(index, translator.Text_Get(code))
        for plot in self._Plots_Get():
            plot.setLabel("bottom", translator.Text_Get("timeline.time"))
        self.update_table.setHorizontalHeaderLabels(
            [
                translator.Text_Get("timeline.time"),
                translator.Text_Get("state.measurement"),
                translator.Text_Get("state.dimension"),
                translator.Text_Get("state.result"),
                "NIS",
                translator.Text_Get("state.r_scale_short"),
                translator.Text_Get("state.measurement_age"),
            ]
        )
        if self._visualization is not None:
            self._Selectors_Refresh()
            self._Refresh()
            if self._resolver is not None and self._estimator_source is not None:
                self.source_value_label.setText(
                    _Source_Label(
                        self._translator,
                        self._resolver,
                        self._estimator_source.source_id,
                    )
                )
                self.diagnostic_label.setText(
                    self._translator.Text_Get(
                        "state.recorded_diagnostic"
                        if self._estimator_source.kind == AnalysisSourceKind.RECORDED
                        else "state.recomputed_diagnostic"
                    )
                )
