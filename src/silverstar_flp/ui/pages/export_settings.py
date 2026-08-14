from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from silverstar_flp.core.i18n import Translator
from silverstar_flp.export.service import ExportLanguage, ExportOptions, ExportTheme
from silverstar_flp.ui.widgets import StandardComboBox


class ImportDialog(QDialog):
    importRequested = Signal(object)

    def __init__(self, translator: Translator, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._translator = translator
        self.setModal(True)
        self.resize(640, 250)
        self.setMinimumWidth(520)

        layout = QVBoxLayout(self)
        self.source_group = QGroupBox()
        form = QFormLayout(self.source_group)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

        self.source_type_label = QLabel()
        self.source_type_combo = StandardComboBox()
        self.source_type_combo.currentIndexChanged.connect(self._SourceType_Changed)
        form.addRow(self.source_type_label, self.source_type_combo)

        self.source_file_label = QLabel()
        file_row = QHBoxLayout()
        self.path_edit = QLineEdit()
        self.path_edit.returnPressed.connect(self._Import_Request)
        self.browse_button = QPushButton()
        self.browse_button.clicked.connect(self._File_Browse)
        file_row.addWidget(self.path_edit, 1)
        file_row.addWidget(self.browse_button)
        form.addRow(self.source_file_label, file_row)
        layout.addWidget(self.source_group)

        self.note_label = QLabel()
        self.note_label.setObjectName("muted")
        self.note_label.setWordWrap(True)
        layout.addWidget(self.note_label)
        self.result_label = QLabel()
        self.result_label.setObjectName("warningLabel")
        self.result_label.setWordWrap(True)
        self.result_label.hide()
        layout.addWidget(self.result_label)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self.cancel_button = QPushButton()
        self.cancel_button.clicked.connect(self.reject)
        self.import_button = QPushButton()
        self.import_button.setObjectName("primaryButton")
        self.import_button.clicked.connect(self._Import_Request)
        button_row.addWidget(self.cancel_button)
        button_row.addWidget(self.import_button)
        layout.addLayout(button_row)
        self.Language_Apply(translator)

    def _SourceType_Changed(self) -> None:
        source_type = str(self.source_type_combo.currentData() or "flight_log")
        self.path_edit.setPlaceholderText(
            self._translator.Text_Get(
                "import.flight_log_placeholder"
                if source_type == "flight_log"
                else "import.project_placeholder"
            )
        )

    def _File_Browse(self) -> None:
        source_type = str(self.source_type_combo.currentData() or "flight_log")
        file_filter = (
            "SilverStar flight logs (*.BIN *.bin);;All files (*)"
            if source_type == "flight_log"
            else "SilverStar project (*.ssflp);;All files (*)"
        )
        selected, _ = QFileDialog.getOpenFileName(
            self,
            self._translator.Text_Get("dialog.import.title"),
            str(Path.home()),
            file_filter,
        )
        if selected:
            self.path_edit.setText(selected)

    def _Import_Request(self) -> None:
        path_text = self.path_edit.text().strip()
        if not path_text:
            self.result_label.setText(self._translator.Text_Get("import.path_required"))
            self.result_label.show()
            return
        self.result_label.hide()
        self.importRequested.emit(Path(path_text))
        self.accept()

    def Language_Apply(self, translator: Translator) -> None:
        self._translator = translator
        selected_type = self.source_type_combo.currentData()
        self.source_type_combo.blockSignals(True)
        self.source_type_combo.clear()
        self.source_type_combo.addItem(translator.Text_Get("import.flight_log"), "flight_log")
        self.source_type_combo.addItem(translator.Text_Get("import.project"), "project")
        index = self.source_type_combo.findData(selected_type)
        self.source_type_combo.setCurrentIndex(max(index, 0))
        self.source_type_combo.blockSignals(False)

        self.setWindowTitle(translator.Text_Get("dialog.import.title"))
        self.source_group.setTitle(translator.Text_Get("dialog.import.source"))
        self.source_type_label.setText(translator.Text_Get("label.import_type"))
        self.source_file_label.setText(translator.Text_Get("label.source_file"))
        self.browse_button.setText(translator.Text_Get("action.browse"))
        self.cancel_button.setText(translator.Text_Get("action.dialog_cancel"))
        self.import_button.setText(translator.Text_Get("action.import"))
        self.note_label.setText(translator.Text_Get("import.read_only_note"))
        self._SourceType_Changed()


class ExportDialog(QDialog):
    exportRequested = Signal(object, object)

    def __init__(self, translator: Translator, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._translator = translator
        self.setModal(True)
        self.resize(680, 650)
        self.setMinimumSize(560, 500)

        layout = QVBoxLayout(self)
        self.destination_group = QGroupBox()
        form = QFormLayout(self.destination_group)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.folder_label = QLabel()
        folder_row = QHBoxLayout()
        self.folder_edit = QLineEdit(str(Path.cwd() / "exports"))
        self.browse_button = QPushButton()
        self.browse_button.clicked.connect(self._Folder_Browse)
        folder_row.addWidget(self.folder_edit, 1)
        folder_row.addWidget(self.browse_button)
        form.addRow(self.folder_label, folder_row)

        self.export_language_label = QLabel()
        self.export_language_combo = StandardComboBox()
        form.addRow(self.export_language_label, self.export_language_combo)
        self.export_theme_label = QLabel()
        self.export_theme_combo = StandardComboBox()
        form.addRow(self.export_theme_label, self.export_theme_combo)
        layout.addWidget(self.destination_group)

        self.items_group = QGroupBox()
        items_group_layout = QVBoxLayout(self.items_group)
        self.items_scroll = QScrollArea()
        self.items_scroll.setWidgetResizable(True)
        self.items_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.items_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        items_widget = QWidget()
        self.items_layout = QVBoxLayout(items_widget)
        self.overview_check = QCheckBox()
        self.diagnostics_check = QCheckBox()
        self.events_check = QCheckBox()
        self.csv_check = QCheckBox()
        self.plots_check = QCheckBox()
        self.trajectory_check = QCheckBox()
        self.gif_check = QCheckBox()
        self._checks = (
            self.overview_check,
            self.diagnostics_check,
            self.events_check,
            self.csv_check,
            self.plots_check,
            self.trajectory_check,
            self.gif_check,
        )
        for checkbox in self._checks:
            checkbox.setChecked(True)
            self.items_layout.addWidget(checkbox)
        self.items_layout.addStretch(1)
        self.items_scroll.setWidget(items_widget)
        items_group_layout.addWidget(self.items_scroll)
        layout.addWidget(self.items_group, 1)

        self.note_label = QLabel()
        self.note_label.setWordWrap(True)
        self.note_label.setObjectName("muted")
        layout.addWidget(self.note_label)
        self.result_label = QLabel("—")
        self.result_label.setWordWrap(True)
        layout.addWidget(self.result_label)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self.close_button = QPushButton()
        self.close_button.clicked.connect(self.reject)
        self.export_button = QPushButton()
        self.export_button.setObjectName("primaryButton")
        self.export_button.clicked.connect(self._Export_Request)
        button_row.addWidget(self.close_button)
        button_row.addWidget(self.export_button)
        layout.addLayout(button_row)
        self.Language_Apply(translator)

    def _Folder_Browse(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self,
            self._translator.Text_Get("label.output_folder"),
            self.folder_edit.text(),
        )
        if selected:
            self.folder_edit.setText(selected)

    def _Export_Request(self) -> None:
        folder_text = self.folder_edit.text().strip()
        if not folder_text:
            self.result_label.setText(self._translator.Text_Get("export.folder_required"))
            return
        options = ExportOptions(
            language=self.export_language_combo.currentData(),
            theme=self.export_theme_combo.currentData(),
            include_overview=self.overview_check.isChecked(),
            include_diagnostics=self.diagnostics_check.isChecked(),
            include_events=self.events_check.isChecked(),
            include_csv=self.csv_check.isChecked(),
            include_plots=self.plots_check.isChecked(),
            include_trajectory_3d=self.trajectory_check.isChecked(),
            include_attitude_gif=self.gif_check.isChecked(),
        )
        self.export_button.setEnabled(False)
        self.result_label.setText(self._translator.Text_Get("export.running"))
        self.exportRequested.emit(Path(folder_text), options)

    def Result_Set(self, count: int) -> None:
        self.export_button.setEnabled(True)
        self.result_label.setText(self._translator.Text_Get("export.complete", count=count))

    def Result_Error(self, message: str) -> None:
        self.export_button.setEnabled(True)
        self.result_label.setText(message)

    def Task_Finish(self) -> None:
        self.export_button.setEnabled(True)

    def Theme_Set(self, theme: str) -> None:
        try:
            target = ExportTheme(theme)
        except ValueError:
            return
        index = self.export_theme_combo.findData(target)
        if index >= 0:
            self.export_theme_combo.setCurrentIndex(index)

    def Language_Apply(self, translator: Translator) -> None:
        self._translator = translator
        language = self.export_language_combo.currentData() or ExportLanguage.ZH
        theme = self.export_theme_combo.currentData() or ExportTheme.LIGHT

        self.export_language_combo.blockSignals(True)
        self.export_language_combo.clear()
        self.export_language_combo.addItem(
            translator.Text_Get("export.language_zh"), ExportLanguage.ZH
        )
        self.export_language_combo.addItem(
            translator.Text_Get("export.language_en"), ExportLanguage.EN
        )
        self.export_language_combo.setCurrentIndex(
            max(self.export_language_combo.findData(language), 0)
        )
        self.export_language_combo.blockSignals(False)

        self.export_theme_combo.blockSignals(True)
        self.export_theme_combo.clear()
        self.export_theme_combo.addItem(translator.Text_Get("theme.light"), ExportTheme.LIGHT)
        self.export_theme_combo.addItem(translator.Text_Get("theme.dark"), ExportTheme.DARK)
        self.export_theme_combo.setCurrentIndex(max(self.export_theme_combo.findData(theme), 0))
        self.export_theme_combo.blockSignals(False)

        self.setWindowTitle(translator.Text_Get("dialog.export.title"))
        self.destination_group.setTitle(translator.Text_Get("dialog.export.destination"))
        self.folder_label.setText(translator.Text_Get("label.output_folder"))
        self.browse_button.setText(translator.Text_Get("action.browse"))
        self.export_language_label.setText(translator.Text_Get("label.export_language"))
        self.export_theme_label.setText(translator.Text_Get("label.export_theme"))
        self.items_group.setTitle(translator.Text_Get("dialog.export.items"))
        labels = (
            "export.item.overview",
            "export.item.diagnostics",
            "export.item.events",
            "export.item.csv",
            "export.item.plots",
            "export.item.trajectory",
            "export.item.gif",
        )
        for checkbox, code in zip(self._checks, labels, strict=True):
            checkbox.setText(translator.Text_Get(code))
        self.note_label.setText(translator.Text_Get("export.note"))
        self.close_button.setText(translator.Text_Get("action.close"))
        self.export_button.setText(translator.Text_Get("action.export"))
