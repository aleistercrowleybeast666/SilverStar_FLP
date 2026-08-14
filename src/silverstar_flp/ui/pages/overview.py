from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGridLayout,
    QGroupBox,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from silverstar_flp.analysis.overview import FlightSummary_Build
from silverstar_flp.core.dataset import FlightDataset
from silverstar_flp.core.i18n import Translator


class _MetricCard(QGroupBox):
    def __init__(self, title: str) -> None:
        super().__init__(title)
        layout = QVBoxLayout(self)
        self.value_label = QLabel("—")
        self.value_label.setObjectName("metricValue")
        self.detail_label = QLabel("")
        self.detail_label.setObjectName("muted")
        self.detail_label.setWordWrap(True)
        layout.addWidget(self.value_label)
        layout.addWidget(self.detail_label)


class OverviewPage(QWidget):
    def __init__(self, translator: Translator) -> None:
        super().__init__()
        self._translator = translator
        self._dataset: FlightDataset | None = None
        layout = QVBoxLayout(self)
        self.file_label = QLabel(translator.Text_Get("status.no_data"))
        self.file_label.setWordWrap(True)
        layout.addWidget(self.file_label)

        metrics = QGridLayout()
        self.duration_card = _MetricCard(translator.Text_Get("label.duration"))
        self.altitude_card = _MetricCard(translator.Text_Get("label.max_altitude"))
        self.speed_card = _MetricCard(translator.Text_Get("label.max_speed"))
        self.acceleration_card = _MetricCard(translator.Text_Get("label.max_acceleration"))
        self.apogee_card = _MetricCard(translator.Text_Get("label.apogee"))
        self.quality_card = _MetricCard(translator.Text_Get("label.data_quality"))
        cards = (
            self.duration_card,
            self.altitude_card,
            self.speed_card,
            self.acceleration_card,
            self.apogee_card,
            self.quality_card,
        )
        for index, card in enumerate(cards):
            metrics.addWidget(card, index // 3, index % 3)
        layout.addLayout(metrics)

        self.timeline_group = QGroupBox(translator.Text_Get("label.timeline"))
        timeline_layout = QVBoxLayout(self.timeline_group)
        self.timeline_table = QTableWidget(0, 4)
        self.timeline_table.setHorizontalHeaderLabels(["Time (s)", "Event", "arg0", "arg1"])
        self.timeline_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.timeline_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.timeline_table.verticalHeader().setVisible(False)
        self.timeline_table.horizontalHeader().setStretchLastSection(True)
        timeline_layout.addWidget(self.timeline_table)
        layout.addWidget(self.timeline_group, 1)

    def Dataset_Set(self, dataset: FlightDataset) -> None:
        self._dataset = dataset
        summary = FlightSummary_Build(dataset)
        synthetic = (
            f" · {self._translator.Text_Get('status.synthetic')}" if summary.synthetic else ""
        )
        self.file_label.setText(
            f"{dataset.source_path} · SSLOG0 · {summary.source_name}{synthetic}"
        )
        self.duration_card.value_label.setText(
            f"{summary.duration_s:.3f} s" if summary.duration_s is not None else "—"
        )
        self.altitude_card.value_label.setText(
            f"{summary.maximum_altitude_m:.3f} m" if summary.maximum_altitude_m is not None else "—"
        )
        self.speed_card.value_label.setText(
            f"{summary.maximum_speed_mps:.3f} m/s" if summary.maximum_speed_mps is not None else "—"
        )
        self.acceleration_card.value_label.setText(
            f"{summary.maximum_acceleration_mps2:.3f} m/s²"
            if summary.maximum_acceleration_mps2 is not None
            else "—"
        )
        self.apogee_card.value_label.setText(
            f"{summary.apogee.altitude_m:.3f} m" if summary.apogee.altitude_m is not None else "—"
        )
        self.apogee_card.detail_label.setText(
            f"{summary.apogee.method} · {summary.apogee.confidence}"
        )
        self.quality_card.value_label.setText(
            self._translator.Text_Get("overview.records", count=summary.decoded_record_count)
        )
        self.quality_card.detail_label.setText(
            self._translator.Text_Get(
                "overview.quality_detail",
                crc=summary.crc_failure_count,
                gaps=summary.sequence_gap_count,
            )
        )
        start = summary.mission_start_timestamp_us or (
            summary.timeline[0].timestamp_us if summary.timeline else 0
        )
        self.timeline_table.setRowCount(len(summary.timeline))
        for row, event in enumerate(summary.timeline):
            values = (
                f"{(event.timestamp_us - start) * 1.0e-6:.6f}",
                event.name,
                str(event.arg0),
                str(event.arg1),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if event.name == "MISSION_START":
                    item.setBackground(Qt.GlobalColor.darkCyan)
                self.timeline_table.setItem(row, column, item)
        self.timeline_table.resizeColumnsToContents()

    def Language_Apply(self, translator: Translator) -> None:
        self._translator = translator
        self.duration_card.setTitle(translator.Text_Get("label.duration"))
        self.altitude_card.setTitle(translator.Text_Get("label.max_altitude"))
        self.speed_card.setTitle(translator.Text_Get("label.max_speed"))
        self.acceleration_card.setTitle(translator.Text_Get("label.max_acceleration"))
        self.apogee_card.setTitle(translator.Text_Get("label.apogee"))
        self.quality_card.setTitle(translator.Text_Get("label.data_quality"))
        self.timeline_group.setTitle(translator.Text_Get("label.timeline"))
        self.timeline_table.setHorizontalHeaderLabels(
            [
                translator.Text_Get("timeline.time"),
                translator.Text_Get("timeline.event"),
                "arg0",
                "arg1",
            ]
        )
        if self._dataset is not None:
            self.Dataset_Set(self._dataset)
