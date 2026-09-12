from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from silverstar_flp.app.version import PRODUCT_NAME, __version__
from silverstar_flp.core.i18n import Translator
from silverstar_flp.plugins.container_packages import ContainerPluginDiscovery
from silverstar_flp.plugins.registry import PluginRegistry


@dataclass(frozen=True, slots=True)
class PluginDisplayRow:
    plugin_type: str
    display_name: str
    plugin_id: str
    version: str
    source: str
    status: str


class PluginManagerDialog(QDialog):
    """Read-only view of active runtime plugins and safely discovered packages."""

    def __init__(self, translator: Translator, parent=None) -> None:
        super().__init__(parent)
        self.setModal(True)
        self.resize(900, 430)
        layout = QVBoxLayout(self)
        self.description_label = QLabel()
        self.description_label.setWordWrap(True)
        layout.addWidget(self.description_label)
        self.table = QTableWidget(0, 6)
        self.table.setObjectName("pluginManagerTable")
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._buttons = buttons
        self.Language_Apply(translator)

    def Language_Apply(self, translator: Translator) -> None:
        self._translator = translator
        self.setWindowTitle(translator.Text_Get("dialog.plugins.title"))
        self.description_label.setText(translator.Text_Get("dialog.plugins.description"))
        headers = (
            "plugin.column.type",
            "plugin.column.display_name",
            "plugin.column.id",
            "plugin.column.version",
            "plugin.column.source",
            "plugin.column.status",
        )
        self.table.setHorizontalHeaderLabels([translator.Text_Get(key) for key in headers])
        self._buttons.button(QDialogButtonBox.StandardButton.Close).setText(
            translator.Text_Get("action.close")
        )

    def Registry_Set(
        self,
        registry: PluginRegistry,
        discovery: ContainerPluginDiscovery,
    ) -> None:
        rows: list[PluginDisplayRow] = []
        active_ids: set[str] = set()
        for plugin in registry.algorithms:
            metadata = plugin.metadata
            active_ids.add(metadata.plugin_id)
            rows.append(
                PluginDisplayRow(
                    "plugin.type.algorithm",
                    metadata.display_name,
                    metadata.plugin_id,
                    metadata.version,
                    "plugin.source.builtin"
                    if plugin.__class__.__module__.startswith("silverstar_flp.plugins.")
                    else "plugin.source.installed",
                    "plugin.status.active",
                )
            )
        for plugin in registry.log_containers:
            metadata = plugin.metadata
            active_ids.add(metadata.plugin_id)
            rows.append(
                PluginDisplayRow(
                    "plugin.type.log_container",
                    f"{metadata.container_format_id} — {metadata.display_name}",
                    metadata.plugin_id,
                    metadata.version,
                    "plugin.source.builtin" if metadata.builtin else "plugin.source.installed",
                    "plugin.status.active",
                )
            )
        for manifest in discovery.manifests:
            if manifest.plugin_id not in active_ids:
                rows.append(
                    PluginDisplayRow(
                        "plugin.type.log_container",
                        manifest.plugin_id,
                        manifest.plugin_id,
                        manifest.version,
                        "plugin.source.installed",
                        "plugin.status.restart_required",
                    )
                )
        self.table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            values = (
                self._translator.Text_Get(row.plugin_type),
                row.display_name,
                row.plugin_id,
                row.version,
                self._translator.Text_Get(row.source),
                self._translator.Text_Get(row.status),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, row.plugin_id)
                self.table.setItem(row_index, column, item)


class AboutDialog(QDialog):
    def __init__(self, translator: Translator, parent=None) -> None:
        super().__init__(parent)
        self.setModal(True)
        self.setFixedSize(460, 250)
        layout = QVBoxLayout(self)
        self.product_label = QLabel(PRODUCT_NAME)
        self.product_label.setObjectName("aboutProduct")
        self.product_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.version_label = QLabel()
        self.version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.description_label = QLabel("SilverStar Flight Log Parser")
        self.description_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.credit_label = QLabel("辰星引力 / CXYL")
        self.credit_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        for widget in (
            self.product_label,
            self.version_label,
            self.description_label,
            self.credit_label,
        ):
            layout.addWidget(widget)
        layout.addStretch(1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)
        self._buttons = buttons
        self.Language_Apply(translator)

    def Language_Apply(self, translator: Translator) -> None:
        self.setWindowTitle(translator.Text_Get("dialog.about.title"))
        self.version_label.setText(f"{translator.Text_Get('label.version')} {__version__}")
        self._buttons.button(QDialogButtonBox.StandardButton.Ok).setText(
            translator.Text_Get("action.close")
        )
