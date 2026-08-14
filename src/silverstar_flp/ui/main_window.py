from __future__ import annotations

import logging
from dataclasses import replace
from pathlib import Path
from typing import Any

from PySide6.QtCore import QSettings, Qt, QThreadPool, QTimer
from PySide6.QtGui import QAction, QCloseEvent, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSlider,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from silverstar_flp.core.dataset import FlightDataset
from silverstar_flp.core.i18n import Translator
from silverstar_flp.core.project import Project_Load, Project_Save, ProjectDocument
from silverstar_flp.export.service import ExportManifest, FlightExporter
from silverstar_flp.plugins.api.algorithm import AlgorithmResult, ReplayRequest
from silverstar_flp.plugins.registry import PluginRegistry
from silverstar_flp.ui.pages import (
    AttitudeImuPage,
    DataExplorerPage,
    ExportDialog,
    FlightPage,
    ImportDialog,
    NavigationPage,
    OverviewPage,
    ReplayPage,
)
from silverstar_flp.ui.theme import Theme_Apply
from silverstar_flp.ui.widgets import StandardComboBox
from silverstar_flp.ui.workers import FunctionWorker


class MainWindow(QMainWindow):
    PAGE_CODES = (
        "page.overview",
        "page.flight",
        "page.attitude_imu",
        "page.navigation",
        "page.replay",
        "page.data_explorer",
    )

    def __init__(
        self,
        registry: PluginRegistry,
        *,
        language: str = "zh_CN",
        theme: str = "light",
        initial_path: Path | None = None,
    ) -> None:
        super().__init__()
        self._registry = registry
        self._translator = Translator(language)
        self._theme = theme
        self._dataset: FlightDataset | None = None
        self._algorithm_results: dict[str, AlgorithmResult] = {}
        self._project = ProjectDocument()
        self._thread_pool = QThreadPool.globalInstance()
        self._active_worker: FunctionWorker | None = None
        self._worker_error_callback = None
        self._timeline_first_us = 0
        self._timeline_last_us = 0
        self._settings = QSettings("SilverStar", "SilverStar_FLP")
        self.setAcceptDrops(True)
        self.resize(1480, 920)
        self.setMinimumSize(1080, 700)
        self._Ui_Build()
        self._Menu_Build()
        self.Language_Apply(language)
        self.Theme_Apply(theme)
        if initial_path is not None:
            QTimer.singleShot(0, lambda: self.Path_Open(initial_path))

    def _Ui_Build(self) -> None:
        central = QWidget()
        central.setObjectName("centralRoot")
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        header = QFrame()
        header.setObjectName("headerBar")
        header.setMinimumHeight(54)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(14, 6, 14, 6)
        header_layout.setSpacing(8)
        self.title_label = QLabel()
        self.title_label.setObjectName("headerTitle")
        self.file_label = QLabel()
        self.file_label.setObjectName("headerFile")
        self.file_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.import_button = QPushButton()
        self.import_button.setObjectName("topActionButton")
        self.import_button.clicked.connect(self._ImportDialog_Show)
        self.export_button = QPushButton()
        self.export_button.setObjectName("topActionButton")
        self.export_button.clicked.connect(self._ExportDialog_Show)
        self.export_button.setEnabled(False)
        self.language_label = QLabel()
        self.language_label.setObjectName("headerControlLabel")
        self.language_combo = StandardComboBox()
        self.language_combo.setObjectName("headerCombo")
        self.language_combo.addItem("简体中文", "zh_CN")
        self.language_combo.addItem("English", "en_US")
        self.language_combo.currentIndexChanged.connect(self._Language_Selected)
        self.theme_label = QLabel()
        self.theme_label.setObjectName("headerControlLabel")
        self.theme_combo = StandardComboBox()
        self.theme_combo.setObjectName("headerCombo")
        self.theme_combo.addItem("浅色", "light")
        self.theme_combo.addItem("深色", "dark")
        self.theme_combo.currentIndexChanged.connect(self._Theme_Selected)
        self.cancel_button = QPushButton()
        self.cancel_button.setObjectName("topActionButton")
        self.cancel_button.clicked.connect(self._Task_Cancel)
        self.cancel_button.setVisible(False)
        header_layout.addWidget(self.title_label)
        header_layout.addWidget(self.file_label, 1)
        header_layout.addWidget(self.import_button)
        header_layout.addWidget(self.export_button)
        header_layout.addSpacing(4)
        header_layout.addWidget(self.language_label)
        header_layout.addWidget(self.language_combo)
        header_layout.addWidget(self.theme_label)
        header_layout.addWidget(self.theme_combo)
        header_layout.addWidget(self.cancel_button)
        root_layout.addWidget(header)

        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(190)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 8, 0, 8)
        self.navigation_list = QListWidget()
        self.navigation_list.setObjectName("navigation")
        for page_code in self.PAGE_CODES:
            item = QListWidgetItem(page_code)
            item.setData(Qt.ItemDataRole.UserRole, page_code)
            self.navigation_list.addItem(item)
        self.navigation_list.currentRowChanged.connect(self._Page_Select)
        sidebar_layout.addWidget(self.navigation_list)
        body_layout.addWidget(sidebar)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        self.pages = QStackedWidget()
        self.overview_page = OverviewPage(self._translator)
        self.flight_page = FlightPage(self._translator)
        self.attitude_page = AttitudeImuPage(self._translator)
        self.navigation_page = NavigationPage(self._translator)
        self.replay_page = ReplayPage(self._translator, self._registry)
        self.explorer_page = DataExplorerPage(self._translator)
        self._page_widgets = (
            self.overview_page,
            self.flight_page,
            self.attitude_page,
            self.navigation_page,
            self.replay_page,
            self.explorer_page,
        )
        for page in self._page_widgets:
            self.pages.addWidget(page)
        content_layout.addWidget(self.pages, 1)

        self.timeline_frame = QFrame()
        timeline_layout = QHBoxLayout(self.timeline_frame)
        self.start_boundary_label = QLabel("START")
        self.start_boundary_label.setStyleSheet(
            "background:#F97316;color:white;border-radius:4px;padding:4px 8px;font-weight:700;"
        )
        self.timeline_slider = QSlider(Qt.Orientation.Horizontal)
        self.timeline_slider.setRange(0, 10000)
        self.timeline_slider.valueChanged.connect(self._Timeline_Changed)
        self.timeline_time_label = QLabel("—")
        self.timeline_time_label.setMinimumWidth(180)
        timeline_layout.addWidget(self.start_boundary_label)
        timeline_layout.addWidget(self.timeline_slider, 1)
        timeline_layout.addWidget(self.timeline_time_label)
        self.timeline_frame.setVisible(False)
        content_layout.addWidget(self.timeline_frame)
        body_layout.addWidget(content, 1)
        root_layout.addWidget(body, 1)
        self.setCentralWidget(central)

        status_bar = QStatusBar()
        self.status_label = QLabel()
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1000)
        self.progress_bar.setFixedWidth(240)
        self.progress_bar.setVisible(False)
        status_bar.addWidget(self.status_label, 1)
        status_bar.addPermanentWidget(self.progress_bar)
        self.setStatusBar(status_bar)

        self.replay_page.replayRequested.connect(self._Replay_Start)
        self.import_dialog = ImportDialog(self._translator, self)
        self.import_dialog.importRequested.connect(self.Path_Open)
        self.export_dialog = ExportDialog(self._translator, self)
        self.export_dialog.exportRequested.connect(self._Export_Start)
        self.navigation_list.setCurrentRow(0)

    def _Menu_Build(self) -> None:
        self.menuBar().setObjectName("mainMenuBar")
        self.file_menu = self.menuBar().addMenu("")
        self.import_action = QAction(self)
        self.import_action.setShortcut("Ctrl+O")
        self.import_action.triggered.connect(self._ImportDialog_Show)
        self.export_action = QAction(self)
        self.export_action.setShortcut("Ctrl+E")
        self.export_action.setEnabled(False)
        self.export_action.triggered.connect(self._ExportDialog_Show)
        self.open_project_action = QAction(self)
        self.open_project_action.triggered.connect(self._ProjectDialog_Open)
        self.save_project_action = QAction(self)
        self.save_project_action.setShortcut("Ctrl+S")
        self.save_project_action.triggered.connect(self._Project_Save)
        self.file_menu.addAction(self.import_action)
        self.file_menu.addAction(self.export_action)
        self.file_menu.addSeparator()
        self.file_menu.addAction(self.open_project_action)
        self.file_menu.addAction(self.save_project_action)

    def _Page_Select(self, index: int) -> None:
        if 0 <= index < self.pages.count():
            self.pages.setCurrentIndex(index)

    def _ImportDialog_Show(self) -> None:
        self.import_dialog.result_label.hide()
        self.import_dialog.open()

    def _ExportDialog_Show(self) -> None:
        if self._dataset is None:
            return
        self.export_dialog.open()

    def _Language_Selected(self) -> None:
        language = self.language_combo.currentData()
        if language is not None:
            self.Language_Apply(str(language))

    def _Theme_Selected(self) -> None:
        theme = self.theme_combo.currentData()
        if theme is not None:
            self.Theme_Apply(str(theme))

    def Path_Open(self, path: Path) -> None:
        source_path = Path(path)
        if source_path.suffix.lower() != ".ssflp":
            self.Log_Open(source_path)
            return
        try:
            self._project = Project_Load(source_path)
            paths = self._project.LogPaths_Resolve()
            if not paths:
                raise ValueError("project_has_no_log_reference")
            index = min(max(self._project.active_log_index, 0), len(paths) - 1)
            self.Log_Open(paths[index])
        except Exception as exc:
            logging.exception("Project open failed")
            self._Error_Show(str(exc))

    def Log_Open(self, path: Path) -> None:
        source_path = Path(path).resolve()
        if not source_path.is_file():
            self._Error_Show(f"file_not_found: {source_path}")
            return
        parser = self._registry.LogParser_Probe(source_path)
        if parser is None:
            self._Error_Show(self._translator.Text_Get("error.parser_unrecognized"))
            return
        self.file_label.setText(str(source_path))
        self.status_label.setText(self._translator.Text_Get("status.loading"))
        worker = FunctionWorker(lambda context: parser.parse(source_path, context))
        self._Task_Start(
            worker,
            self._Dataset_Set,
            lambda message: self._Error_Show(message),
        )

    def _Dataset_Set(self, dataset: FlightDataset) -> None:
        self._dataset = dataset
        self._algorithm_results.clear()
        self.export_button.setEnabled(True)
        self.export_action.setEnabled(True)
        self._project.LogReference_Add(dataset.source_path)
        self.file_label.setText(str(dataset.source_path))
        self.status_label.setText(
            self._translator.Text_Get(
                "status.loaded", count=dataset.diagnostics.decoded_record_count
            )
        )
        self._Pages_Refresh()
        first = dataset.diagnostics.first_timestamp_us
        last = dataset.diagnostics.last_timestamp_us
        if first is not None and last is not None and last >= first:
            self._timeline_first_us = first
            self._timeline_last_us = last
            start = dataset.start_timestamp_us
            self.start_boundary_label.setText(
                f"START  {(start - first) * 1.0e-6:.3f} s"
                if start is not None
                else self._translator.Text_Get("status.start_unavailable")
            )
            self.timeline_frame.setVisible(True)
            if start is not None and last > first:
                slider_value = int((start - first) * 10000 / (last - first))
                self.timeline_slider.setValue(max(0, min(10000, slider_value)))
        self.setWindowTitle(
            f"{self._translator.Text_Get('app.title')} — {dataset.source_path.name}"
        )

    def _Pages_Refresh(self) -> None:
        if self._dataset is None:
            return
        self.overview_page.Dataset_Set(self._dataset)
        self.flight_page.Dataset_Set(self._dataset, self._algorithm_results)
        self.attitude_page.Dataset_Set(self._dataset, self._algorithm_results)
        self.navigation_page.Dataset_Set(self._dataset, self._algorithm_results)
        self.replay_page.Dataset_Set(self._dataset, self._algorithm_results)
        self.explorer_page.Dataset_Set(self._dataset, self._algorithm_results)

    def _Replay_Start(self, algorithm_id: str, request: ReplayRequest) -> None:
        if self._dataset is None:
            self.replay_page.Result_Error(self._translator.Text_Get("status.no_data"))
            return
        plugin = self._registry.Algorithm_Get(algorithm_id)
        dataset = self._dataset
        worker = FunctionWorker(lambda context: plugin.run(dataset, request, context))
        self._Task_Start(
            worker,
            self._Replay_ResultSet,
            self.replay_page.Result_Error,
        )

    def _Replay_ResultSet(self, result: AlgorithmResult) -> None:
        display_name = self._registry.Algorithm_Get(result.algorithm_id).metadata.display_name
        self._algorithm_results[display_name] = result
        self.replay_page.Result_Set(result)
        if self._dataset is not None:
            self.flight_page.Dataset_Set(self._dataset, self._algorithm_results)
            self.attitude_page.Dataset_Set(self._dataset, self._algorithm_results)
            self.navigation_page.Dataset_Set(self._dataset, self._algorithm_results)
            self.explorer_page.Dataset_Set(self._dataset, self._algorithm_results)
        self.status_label.setText(
            self._translator.Text_Get("replay.complete", fidelity=result.fidelity.value)
        )

    def _Export_Start(self, output_path: Path, options: Any) -> None:
        if self._dataset is None:
            self.export_dialog.Result_Error(self._translator.Text_Get("status.no_data"))
            return
        selected = self.explorer_page.ExportChannels_Get()
        options = replace(options, selected_channels=selected)
        dataset = self._dataset
        results = dict(self._algorithm_results)
        exporter = FlightExporter()
        worker = FunctionWorker(
            lambda context: exporter.export(
                dataset,
                output_path,
                options=options,
                algorithm_results=results,
                context=context,
            )
        )
        self._Task_Start(
            worker,
            self._Export_ResultSet,
            self.export_dialog.Result_Error,
        )

    def _Export_ResultSet(self, manifest: ExportManifest) -> None:
        self.export_dialog.Result_Set(len(manifest.files))
        self.status_label.setText(
            self._translator.Text_Get("export.complete", count=len(manifest.files))
        )

    def _Task_Start(self, worker, result_callback, error_callback) -> None:
        if self._active_worker is not None:
            error_callback("another_background_task_is_running")
            return
        self._active_worker = worker
        self._worker_error_callback = error_callback
        worker.signals.progress.connect(self._Task_Progress)
        worker.signals.result.connect(result_callback)
        worker.signals.error.connect(self._Task_Error)
        worker.signals.cancelled.connect(
            lambda: self.status_label.setText(self._translator.Text_Get("status.task_cancelled"))
        )
        worker.signals.finished.connect(self._Task_Finish)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self.cancel_button.setEnabled(True)
        self.cancel_button.setVisible(True)
        self.import_button.setEnabled(False)
        self.export_button.setEnabled(False)
        self.import_action.setEnabled(False)
        self.export_action.setEnabled(False)
        self._thread_pool.start(worker)

    def _Task_Progress(self, progress: float, code: str) -> None:
        self.progress_bar.setValue(int(progress * 1000))
        self.status_label.setText(self._translator.Text_Get(code))

    def _Task_Error(self, message: str, traceback_text: str) -> None:
        logging.error("Background task failed: %s\n%s", message, traceback_text)
        if self._worker_error_callback is not None:
            self._worker_error_callback(message)
        self._Error_Show(message)

    def _Task_Finish(self) -> None:
        self.progress_bar.setVisible(False)
        self.cancel_button.setVisible(False)
        self.import_button.setEnabled(True)
        self.export_button.setEnabled(self._dataset is not None)
        self.import_action.setEnabled(True)
        self.export_action.setEnabled(self._dataset is not None)
        self.export_dialog.Task_Finish()
        self.replay_page.Task_Finish()
        self._active_worker = None
        self._worker_error_callback = None

    def _Task_Cancel(self) -> None:
        if self._active_worker is not None:
            self._active_worker.Worker_Cancel()
            self.cancel_button.setEnabled(False)

    def _Timeline_Changed(self, value: int) -> None:
        if self._timeline_last_us <= self._timeline_first_us:
            return
        timestamp = int(
            self._timeline_first_us
            + (self._timeline_last_us - self._timeline_first_us) * value / 10000
        )
        start = (
            self._dataset.start_timestamp_us
            if self._dataset is not None and self._dataset.start_timestamp_us is not None
            else self._timeline_first_us
        )
        self.timeline_time_label.setText(
            f"t = {(timestamp - start) * 1.0e-6:.6f} s · {timestamp} µs"
        )
        self.attitude_page.Timeline_Set(timestamp)

    def _ProjectDialog_Open(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self,
            self._translator.Text_Get("action.open_project"),
            str(Path.home()),
            "SilverStar project (*.ssflp)",
        )
        if not selected:
            return
        try:
            self._project = Project_Load(Path(selected))
            log_paths = self._project.LogPaths_Resolve()
            if not log_paths:
                raise ValueError("project_has_no_log_reference")
            index = min(max(self._project.active_log_index, 0), len(log_paths) - 1)
            self.Log_Open(log_paths[index])
        except Exception as exc:
            logging.exception("Project open failed")
            self._Error_Show(str(exc))

    def _Project_Save(self) -> None:
        if self._project.project_path is None:
            selected, _ = QFileDialog.getSaveFileName(
                self,
                self._translator.Text_Get("action.save_project"),
                str(Path.cwd() / "flight.ssflp"),
                "SilverStar project (*.ssflp)",
            )
            if not selected:
                return
            path = Path(selected)
            if path.suffix.lower() != ".ssflp":
                path = path.with_suffix(".ssflp")
        else:
            path = self._project.project_path
        try:
            self._project.replay_configurations = {
                name: {
                    "algorithm_id": result.algorithm_id,
                    "input_source": result.input_source,
                    "parameters": dict(result.parameters),
                    "fidelity": result.fidelity.value,
                }
                for name, result in self._algorithm_results.items()
            }
            Project_Save(self._project, path)
            self.status_label.setText(self._translator.Text_Get("status.project_saved", path=path))
        except Exception as exc:
            logging.exception("Project save failed")
            self._Error_Show(str(exc))

    def _Error_Show(self, message: str) -> None:
        QMessageBox.critical(
            self,
            self._translator.Text_Get("error.title"),
            f"{message}\n\n{self._translator.Text_Get('error.detail_saved')}",
        )

    def Language_Apply(self, language: str) -> None:
        try:
            self._translator.Language_Set(language)
        except ValueError:
            return
        self._settings.setValue("language", language)
        language_index = self.language_combo.findData(language)
        if language_index >= 0:
            self.language_combo.blockSignals(True)
            self.language_combo.setCurrentIndex(language_index)
            self.language_combo.blockSignals(False)

        selected_theme = self.theme_combo.currentData() or self._theme
        self.theme_combo.blockSignals(True)
        self.theme_combo.clear()
        self.theme_combo.addItem(self._translator.Text_Get("theme.light"), "light")
        self.theme_combo.addItem(self._translator.Text_Get("theme.dark"), "dark")
        self.theme_combo.setCurrentIndex(max(self.theme_combo.findData(selected_theme), 0))
        self.theme_combo.blockSignals(False)

        self.title_label.setText(self._translator.Text_Get("app.title"))
        self.import_button.setText(self._translator.Text_Get("action.import"))
        self.export_button.setText(self._translator.Text_Get("action.export"))
        self.language_label.setText(self._translator.Text_Get("label.interface_language"))
        self.theme_label.setText(self._translator.Text_Get("label.theme"))
        self.cancel_button.setText(self._translator.Text_Get("action.cancel"))
        self.file_menu.setTitle(self._translator.Text_Get("menu.file"))
        self.import_action.setText(self._translator.Text_Get("action.import"))
        self.export_action.setText(self._translator.Text_Get("action.export"))
        self.open_project_action.setText(self._translator.Text_Get("action.open_project"))
        self.save_project_action.setText(self._translator.Text_Get("action.save_project"))
        for index in range(self.navigation_list.count()):
            item = self.navigation_list.item(index)
            page_code = str(item.data(Qt.ItemDataRole.UserRole))
            item.setText(self._translator.Text_Get(page_code))
        for page in self._page_widgets:
            page.Language_Apply(self._translator)
        self.import_dialog.Language_Apply(self._translator)
        self.export_dialog.Language_Apply(self._translator)
        if self._dataset is None:
            self.file_label.setText(self._translator.Text_Get("status.no_data"))
            self.status_label.setText(self._translator.Text_Get("status.ready"))
            self.setWindowTitle(self._translator.Text_Get("app.title"))
        else:
            self._Pages_Refresh()
            self.status_label.setText(
                self._translator.Text_Get(
                    "status.loaded",
                    count=self._dataset.diagnostics.decoded_record_count,
                )
            )
            self.setWindowTitle(
                f"{self._translator.Text_Get('app.title')} — {self._dataset.source_path.name}"
            )

    def Theme_Apply(self, theme: str) -> None:
        if theme not in ("light", "dark"):
            return
        self._theme = theme
        self._settings.setValue("theme", theme)
        theme_index = self.theme_combo.findData(theme)
        if theme_index >= 0:
            self.theme_combo.blockSignals(True)
            self.theme_combo.setCurrentIndex(theme_index)
            self.theme_combo.blockSignals(False)
        application = QApplication.instance()
        if application is not None:
            Theme_Apply(application, theme)
        self.flight_page.Theme_Apply(theme)
        self.attitude_page.Theme_Apply(theme)
        self.navigation_page.Theme_Apply(theme)
        self.export_dialog.Theme_Set(theme)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        urls = event.mimeData().urls()
        if urls and urls[0].isLocalFile():
            suffix = Path(urls[0].toLocalFile()).suffix.lower()
            if suffix in (".bin", ".ssflp"):
                event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        path = Path(event.mimeData().urls()[0].toLocalFile())
        if path.suffix.lower() == ".ssflp":
            try:
                self._project = Project_Load(path)
                paths = self._project.LogPaths_Resolve()
                if paths:
                    self.Log_Open(paths[0])
            except Exception as exc:
                self._Error_Show(str(exc))
        else:
            self.Log_Open(path)
        event.acceptProposedAction()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._active_worker is not None:
            self._active_worker.Worker_Cancel()
        event.accept()
