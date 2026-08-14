from __future__ import annotations

import json
from collections.abc import Mapping

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from silverstar_flp.core.dataset import FlightDataset, TimeSeries
from silverstar_flp.core.i18n import Translator
from silverstar_flp.plugins.api.algorithm import AlgorithmResult
from silverstar_flp.ui.widgets import StandardComboBox


class DataExplorerPage(QWidget):
    def __init__(self, translator: Translator) -> None:
        super().__init__()
        self._translator = translator
        self._dataset: FlightDataset | None = None
        self._channels: dict[str, TimeSeries] = {}
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()

        channel_widget = QWidget()
        channel_layout = QVBoxLayout(channel_widget)
        self.search_edit = QLineEdit()
        self.search_edit.textChanged.connect(self._Channels_Filter)
        channel_layout.addWidget(self.search_edit)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.channel_list = QListWidget()
        self.channel_list.currentItemChanged.connect(self._Channel_Show)
        splitter.addWidget(self.channel_list)
        detail_widget = QWidget()
        detail_layout = QVBoxLayout(detail_widget)
        self.channel_metadata = QLabel("—")
        self.channel_metadata.setWordWrap(True)
        self.channel_metadata.setObjectName("muted")
        detail_layout.addWidget(self.channel_metadata)
        self.channel_table = QTableWidget()
        self.channel_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.channel_table.verticalHeader().setVisible(False)
        detail_layout.addWidget(self.channel_table, 1)
        self.display_note = QLabel(
            "The table is display-downsampled above 5,000 rows; exports retain every sample."
        )
        self.display_note.setObjectName("muted")
        detail_layout.addWidget(self.display_note)
        splitter.addWidget(detail_widget)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 4)
        channel_layout.addWidget(splitter)
        self.tabs.addTab(channel_widget, "")

        record_widget = QWidget()
        record_layout = QVBoxLayout(record_widget)
        selector_layout = QHBoxLayout()
        self.record_type_label = QLabel()
        selector_layout.addWidget(self.record_type_label)
        self.record_combo = StandardComboBox()
        self.record_combo.currentIndexChanged.connect(self._Records_Show)
        selector_layout.addWidget(self.record_combo, 1)
        record_layout.addLayout(selector_layout)
        self.record_table = QTableWidget()
        self.record_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.record_table.verticalHeader().setVisible(False)
        record_layout.addWidget(self.record_table)
        self.tabs.addTab(record_widget, "")
        layout.addWidget(self.tabs)
        self.Language_Apply(translator)

    def Dataset_Set(
        self,
        dataset: FlightDataset,
        results: Mapping[str, AlgorithmResult] | None = None,
    ) -> None:
        self._dataset = dataset
        self._channels = dict(dataset.series)
        for result_name, result in (results or {}).items():
            for channel_id, series in result.channels.items():
                self._channels[f"{result_name}.{channel_id}"] = series
        checked_before = {
            self.channel_list.item(index).data(Qt.ItemDataRole.UserRole)
            for index in range(self.channel_list.count())
            if self.channel_list.item(index).checkState() == Qt.CheckState.Checked
        }
        self.channel_list.clear()
        for channel_id in sorted(self._channels):
            series = self._channels[channel_id]
            item = QListWidgetItem(f"{channel_id}  ({series.count})")
            item.setData(Qt.ItemDataRole.UserRole, channel_id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked
                if not checked_before or channel_id in checked_before
                else Qt.CheckState.Unchecked
            )
            self.channel_list.addItem(item)
        if self.channel_list.count():
            self.channel_list.setCurrentRow(0)
        self.record_combo.blockSignals(True)
        self.record_combo.clear()
        self.record_combo.addItems(sorted(dataset.records))
        self.record_combo.blockSignals(False)
        self._Records_Show()

    def _Channels_Filter(self, text: str) -> None:
        needle = text.strip().casefold()
        for index in range(self.channel_list.count()):
            item = self.channel_list.item(index)
            channel_id = str(item.data(Qt.ItemDataRole.UserRole))
            item.setHidden(bool(needle and needle not in channel_id.casefold()))

    def _Channel_Show(self, current: QListWidgetItem | None) -> None:
        if current is None:
            return
        channel_id = str(current.data(Qt.ItemDataRole.UserRole))
        series = self._channels[channel_id]
        self.channel_metadata.setText(
            self._translator.Text_Get(
                "explorer.channel_metadata",
                channel=channel_id,
                quantity=series.quantity,
                unit=series.unit,
                source=series.source,
                count=series.count,
            )
        )
        values = np.asarray(series.values)
        value_columns = (
            list(series.columns or tuple(f"value_{index}" for index in range(values.shape[1])))
            if values.ndim == 2
            else ["value"]
        )
        headers = ["timestamp_us", "time_s", *value_columns, "valid"]
        self.channel_table.setColumnCount(len(headers))
        self.channel_table.setHorizontalHeaderLabels(headers)
        indices = np.unique(
            np.linspace(0, max(series.count - 1, 0), min(series.count, 5000)).astype(int)
        )
        self.channel_table.setRowCount(len(indices))
        origin = int(series.timestamp_us[0]) if series.count else 0
        for row, sample_index in enumerate(indices):
            sample = values[sample_index]
            sample_values = sample.tolist() if values.ndim == 2 else [sample.item()]
            cells = [
                str(int(series.timestamp_us[sample_index])),
                f"{(int(series.timestamp_us[sample_index]) - origin) * 1.0e-6:.9f}",
                *[f"{float(value):.9g}" for value in sample_values],
                str(bool(series.valid[sample_index])),
            ]
            for column, value in enumerate(cells):
                self.channel_table.setItem(row, column, QTableWidgetItem(value))
        self.channel_table.resizeColumnsToContents()

    def _Records_Show(self) -> None:
        if self._dataset is None:
            return
        record_name = self.record_combo.currentText()
        records = self._dataset.Records_Get(record_name)
        if not records:
            self.record_table.setRowCount(0)
            return
        fields = sorted({field for record in records for field in record.payload})
        headers = ["timestamp_us", "record_sequence", "valid_flags", *fields]
        self.record_table.setColumnCount(len(headers))
        self.record_table.setHorizontalHeaderLabels(headers)
        indices = np.unique(np.linspace(0, len(records) - 1, min(len(records), 2000)).astype(int))
        self.record_table.setRowCount(len(indices))
        for row, record_index in enumerate(indices):
            record = records[record_index]
            prefix = [record.timestamp_us, record.record_sequence, record.valid_flags]
            values = prefix + [record.payload.get(field, "") for field in fields]
            for column, value in enumerate(values):
                if isinstance(value, (tuple, list, dict)):
                    text = json.dumps(value, ensure_ascii=False)
                else:
                    text = str(value)
                self.record_table.setItem(row, column, QTableWidgetItem(text))
        self.record_table.resizeColumnsToContents()

    def ExportChannels_Get(self) -> tuple[str, ...]:
        return tuple(
            str(self.channel_list.item(index).data(Qt.ItemDataRole.UserRole))
            for index in range(self.channel_list.count())
            if self.channel_list.item(index).checkState() == Qt.CheckState.Checked
        )

    def Language_Apply(self, translator: Translator) -> None:
        self._translator = translator
        self.search_edit.setPlaceholderText(translator.Text_Get("explorer.filter_channels"))
        self.display_note.setText(translator.Text_Get("explorer.display_note"))
        self.record_type_label.setText(translator.Text_Get("explorer.record_type"))
        self.tabs.setTabText(0, translator.Text_Get("explorer.channels"))
        self.tabs.setTabText(1, translator.Text_Get("explorer.decoded_records"))
        self._Channel_Show(self.channel_list.currentItem())
