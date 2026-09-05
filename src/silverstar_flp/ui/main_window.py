from __future__ import annotations

import logging
from dataclasses import replace
from pathlib import Path
from typing import Any

from PySide6.QtCore import QSettings, Qt, QThreadPool, QTimer, QUrl
from PySide6.QtGui import (
    QAction,
    QCloseEvent,
    QDesktopServices,
    QDragEnterEvent,
    QDropEvent,
)
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
    QStackedWidget,
    QStatusBar,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from silverstar_flp.app.version import PRODUCT_NAME, __version__
from silverstar_flp.core.analysis_source import ChannelResolver, ReplayResultStore
from silverstar_flp.core.dataset import FlightDataset
from silverstar_flp.core.i18n import Translator
from silverstar_flp.core.project import (
    Project_Load,
    Project_Save,
    ProjectDecoderProfile,
    ProjectDocument,
)
from silverstar_flp.export.service import ExportManifest, FlightExporter
from silverstar_flp.log_open import (
    LogOpenCoordinator,
    LogOpenRequest,
    LogOpenResult,
    LogOpenSourceMode,
)
from silverstar_flp.plugins.api.algorithm import AlgorithmResult, ReplayRequest
from silverstar_flp.plugins.registry import PluginRegistry
from silverstar_flp.ui.pages import (
    DataExplorerPage,
    ExportDialog,
    FlightPage,
    ImportDialog,
    OverviewPage,
    ReplayPage,
    StateEstimationPage,
)
from silverstar_flp.ui.theme import Theme_Apply, WindowCaption_Apply
from silverstar_flp.ui.widgets import StandardComboBox
from silverstar_flp.ui.workers import FunctionWorker

_DEFAULT_EXPORT_ROOT = Path(r"D:\SilverStar_FLP_Data")


class MainWindow(QMainWindow):
    PAGE_CODES = (
        "page.overview",
        "page.replay",
        "page.flight",
        "page.state_estimation",
        "page.data_explorer",
    )

    def __init__(
        self,
        registry: PluginRegistry,
        *,
        language: str = "zh_CN",
        theme: str = "light",
        initial_path: Path | None = None,
        initial_decoder_path: Path | None = None,
        initial_auto_find: bool = False,
    ) -> None:
        super().__init__()
        self._registry = registry
        self._log_open_coordinator = LogOpenCoordinator(registry)
        self._translator = Translator(language)
        self._theme = theme
        self._dataset: FlightDataset | None = None
        self._log_open_result: LogOpenResult | None = None
        self._replay_store = ReplayResultStore()
        self._channel_resolver: ChannelResolver | None = None
        self._project = ProjectDocument()
        self._thread_pool = QThreadPool.globalInstance()
        self._active_worker: FunctionWorker | None = None
        self._worker_error_callback = None
        self._settings = QSettings("SilverStar", "SilverStar_FLP")
        self.setAcceptDrops(True)
        self.setWindowTitle(PRODUCT_NAME)
        self.resize(1480, 920)
        self.setMinimumSize(1080, 700)
        self._Ui_Build()
        self._Menu_Build()
        self.Language_Apply(language)
        self.Theme_Apply(theme)
        if initial_path is not None:
            QTimer.singleShot(
                0,
                lambda: self.Path_Open(
                    initial_path,
                    decoder_path=initial_decoder_path,
                    auto_find=initial_auto_find,
                ),
            )

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
        self.version_label = QLabel(f"v{__version__}")
        self.version_label.setObjectName("headerVersion")
        self.credit_label = QLabel()
        self.credit_label.setObjectName("headerCredit")
        self.language_label = QLabel()
        self.language_label.setObjectName("headerControlLabel")
        self.language_combo = StandardComboBox()
        self.language_combo.setObjectName("headerLanguageCombo")
        self.language_combo.view().setObjectName("headerComboPopup")
        self.language_combo.addItem("简体中文", "zh_CN")
        self.language_combo.addItem("English", "en_US")
        self.language_combo.currentIndexChanged.connect(self._Language_Selected)
        self.theme_label = QLabel()
        self.theme_label.setObjectName("headerControlLabel")
        self.theme_combo = StandardComboBox()
        self.theme_combo.setObjectName("headerThemeCombo")
        self.theme_combo.view().setObjectName("headerComboPopup")
        self.theme_combo.addItem("浅色", "light")
        self.theme_combo.addItem("深色", "dark")
        self.theme_combo.currentIndexChanged.connect(self._Theme_Selected)
        header_layout.addWidget(self.title_label)
        header_layout.addWidget(self.version_label)
        header_layout.addWidget(self.credit_label)
        header_layout.addStretch(1)
        header_layout.addWidget(self.language_label)
        header_layout.addWidget(self.language_combo)
        header_layout.addWidget(self.theme_label)
        header_layout.addWidget(self.theme_combo)
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
        self.replay_page = ReplayPage(self._translator, self._registry)
        self.flight_page = FlightPage(self._translator)
        self.state_estimation_page = StateEstimationPage(
            self._translator,
            self._registry,
        )
        self.explorer_page = DataExplorerPage(self._translator)
        self._page_widgets = (
            self.overview_page,
            self.replay_page,
            self.flight_page,
            self.state_estimation_page,
            self.explorer_page,
        )
        for page in self._page_widgets:
            self.pages.addWidget(page)
        content_layout.addWidget(self.pages, 1)
        body_layout.addWidget(content, 1)
        root_layout.addWidget(body, 1)
        self.setCentralWidget(central)

        status_bar = QStatusBar()
        self.status_label = QLabel()
        self.cancel_button = QPushButton()
        self.cancel_button.clicked.connect(self._Task_Cancel)
        self.cancel_button.setVisible(False)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1000)
        self.progress_bar.setFixedWidth(240)
        self.progress_bar.setVisible(False)
        status_bar.addWidget(self.status_label, 1)
        status_bar.addPermanentWidget(self.cancel_button)
        status_bar.addPermanentWidget(self.progress_bar)
        self.setStatusBar(status_bar)

        self.replay_page.replayRequested.connect(self._Replay_Start)
        self.replay_page.analysisSourceRequested.connect(self._AnalysisSource_Set)
        self.import_dialog = ImportDialog(self._translator, self)
        self.import_dialog.importRequested.connect(self.LogPair_Open)
        self.import_dialog.folderSearchRequested.connect(self._FolderSearch_Start)
        self.export_dialog = ExportDialog(self._translator, self)
        self.export_dialog.exportRequested.connect(self._Export_Start)
        self.export_dialog.manifestOpenRequested.connect(self._ExportManifest_Open)
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
        self.save_project_as_action = QAction(self)
        self.save_project_as_action.setShortcut("Ctrl+Shift+S")
        self.save_project_as_action.triggered.connect(self._Project_SaveAs)
        self.file_menu.addAction(self.import_action)
        self.file_menu.addAction(self.export_action)
        self.file_menu.addAction(self.save_project_action)
        self.file_menu.addAction(self.save_project_as_action)
        self.file_menu.addAction(self.open_project_action)
        self.toolbar = QToolBar(self)
        self.toolbar.setObjectName("mainToolBar")
        self.toolbar.setMovable(False)
        self.toolbar.addAction(self.import_action)
        self.toolbar.addAction(self.export_action)
        self.toolbar.addAction(self.save_project_action)
        self.toolbar.addAction(self.open_project_action)
        self.addToolBar(self.toolbar)

    def _Page_Select(self, index: int) -> None:
        if 0 <= index < self.pages.count():
            self.pages.setCurrentIndex(index)

    def _ImportDialog_Show(self) -> None:
        self.import_dialog.result_label.hide()
        self.import_dialog.open()

    def _ExportDialog_Show(self) -> None:
        if self._dataset is None:
            return
        self.export_dialog.OutputDirectory_Set(self._ExportDirectory_Default())
        self.export_dialog.Result_Clear()
        self.export_dialog.open()

    def _ExportDirectory_Default(self) -> Path:
        if self._project.project_path is not None:
            export_name = self._project.project_path.stem
        elif self._dataset is not None:
            export_name = self._dataset.source_path.stem
        else:
            export_name = PRODUCT_NAME
        return _DEFAULT_EXPORT_ROOT / f"{export_name}_Data"

    def _Language_Selected(self) -> None:
        language = self.language_combo.currentData()
        if language is not None:
            self.Language_Apply(str(language))

    def _Theme_Selected(self) -> None:
        theme = self.theme_combo.currentData()
        if theme is not None:
            self.Theme_Apply(str(theme))

    def Path_Open(
        self,
        path: Path,
        *,
        decoder_path: Path | None = None,
        auto_find: bool = False,
    ) -> None:
        source_path = Path(path)
        suffix = source_path.suffix.casefold()
        if suffix == ".ssflp":
            self._Project_Open(source_path)
            return
        if suffix == ".ssdecoder":
            self.import_dialog.Paths_Set(decoder_path=source_path)
            self.import_dialog.open()
            return
        if suffix not in (".bin", ".sslog"):
            self._Error_Show(f"log_open_extension_unsupported:{suffix}")
            return
        if decoder_path is not None:
            self.LogPair_Open(source_path, decoder_path)
        elif auto_find:
            self.Log_Open(
                source_path,
                auto_find=True,
                source_mode=LogOpenSourceMode.FOLDER_SEARCH,
            )
        else:
            self.import_dialog.Paths_Set(log_path=source_path)
            self.import_dialog.open()

    def LogPair_Open(self, log_path: Path, decoder_path: Path) -> None:
        self.Log_Open(
            log_path,
            decoder_path=decoder_path,
            source_mode=LogOpenSourceMode.MANUAL,
        )

    def Log_Open(
        self,
        path: Path,
        *,
        decoder_path: Path | None = None,
        auto_find: bool = False,
        source_mode: LogOpenSourceMode = LogOpenSourceMode.MANUAL,
        project: ProjectDocument | None = None,
    ) -> None:
        source_path = Path(path)
        target_project = project or ProjectDocument()
        request = LogOpenRequest(
            log_path=source_path,
            decoder_package_path=decoder_path,
            auto_find=auto_find,
            task_directory=source_path.parent if auto_find else None,
            source_mode=source_mode,
        )
        self.status_label.setText(self._translator.Text_Get("status.loading"))
        worker = FunctionWorker(
            lambda context: self._log_open_coordinator.Open(request, context)
        )
        self._Task_Start(
            worker,
            lambda result: self._LogOpenResult_Set(result, target_project),
            lambda message: self._Error_Show(message),
        )

    def _ProjectLogOpen_Run(
        self,
        project: ProjectDocument,
        request: LogOpenRequest,
        context: object,
    ) -> LogOpenResult:
        result = self._log_open_coordinator.Open(request, context)
        expected = project.decoder_profile
        if expected is None:
            raise ValueError("project_decoder_profile_missing")
        actual = self._DecoderProfile_Build(result)
        comparisons = (
            (expected.package_sha256, actual.package_sha256),
            (
                expected.generation_profile_sha256,
                actual.generation_profile_sha256,
            ),
            (expected.record_catalog_sha256, actual.record_catalog_sha256),
            (expected.record_catalog_hash_128, actual.record_catalog_hash_128),
            (
                expected.project_semantics_sha256,
                actual.project_semantics_sha256,
            ),
            (
                expected.project_semantics_hash_128,
                actual.project_semantics_hash_128,
            ),
            (expected.container_plugin_id, actual.container_plugin_id),
            (expected.container_plugin_version, actual.container_plugin_version),
            (expected.exact_match_mode, actual.exact_match_mode),
        )
        if any(saved != opened for saved, opened in comparisons):
            raise ValueError("project_decoder_identity_mismatch")
        return result

    def _Project_Open(self, path: Path) -> None:
        try:
            project = Project_Load(Path(path))
            if project.decoder_profile is None:
                raise ValueError("project_decoder_profile_missing")
            decoder_source_path = project.DecoderSourcePath_Resolve()
            request = LogOpenRequest(
                log_path=project.LogPath_Resolve(),
                decoder_package_path=decoder_source_path,
                cache_reference=project.decoder_profile.cache_reference,
                task_directory=(
                    decoder_source_path.parent
                    if decoder_source_path is not None
                    else project.project_path.parent
                    if project.project_path is not None
                    else None
                ),
                source_mode=LogOpenSourceMode.PROJECT,
            )
        except Exception as exc:
            logging.exception("Project open failed")
            self._Error_Show(str(exc))
            return
        self.status_label.setText(self._translator.Text_Get("status.loading"))
        worker = FunctionWorker(
            lambda context: self._ProjectLogOpen_Run(project, request, context)
        )
        self._Task_Start(
            worker,
            lambda result: self._LogOpenResult_Set(result, project),
            lambda message: self._Error_Show(message),
        )

    def _FolderSearch_Start(self, folder_path: Path) -> None:
        selected_path = Path(folder_path)
        self.status_label.setText(self._translator.Text_Get("status.searching_pairs"))
        worker = FunctionWorker(
            lambda context: self._log_open_coordinator.PairDiscovery_Run(selected_path)
        )
        self._Task_Start(
            worker,
            self._FolderSearch_Set,
            lambda message: self._Error_Show(message),
        )

    def _FolderSearch_Set(self, discovery: object) -> None:
        self.import_dialog.PairDiscovery_Set(discovery)
        self.import_dialog.show()
        self.import_dialog.raise_()
        self.status_label.setText(self._translator.Text_Get("status.ready"))

    def _DecoderProfile_Build(
        self,
        result: LogOpenResult,
    ) -> ProjectDecoderProfile:
        package = result.package
        container = self._registry.LogContainer_Get(
            package.required_container_plugin_id
        )
        return ProjectDecoderProfile(
            source_reference=str(result.source_package_path.resolve()),
            cache_reference=result.cache_reference,
            package_sha256=package.package_sha256,
            generation_profile_sha256=package.generation_profile_sha256,
            record_catalog_sha256=package.checksums["record_catalog.json"],
            record_catalog_hash_128=package.record_catalog_hash_128,
            project_semantics_sha256=package.checksums["project_semantics.json"],
            project_semantics_hash_128=package.project_semantics_hash_128,
            container_plugin_id=container.metadata.plugin_id,
            container_plugin_version=container.metadata.version,
            exact_match_mode=result.match_mode,
        )

    def _LogOpenResult_Set(
        self,
        result: LogOpenResult,
        project: ProjectDocument,
    ) -> None:
        project.LogReference_Set(result.dataset.source_path)
        project.decoder_profile = self._DecoderProfile_Build(result)
        self._project = project
        self._log_open_result = result
        self._Dataset_Set(result.dataset)

    def _Dataset_Set(self, dataset: FlightDataset) -> None:
        self._dataset = dataset
        self._replay_store.Clear()
        self._channel_resolver = ChannelResolver(dataset, self._replay_store)
        self.export_action.setEnabled(True)
        semantic_context = dataset.semantic_context
        if semantic_context is None:
            status_text = self._translator.Text_Get(
                "status.loaded_file",
                name=dataset.source_path.name,
                count=dataset.diagnostics.decoded_record_count,
            )
        else:
            identity = semantic_context.PackageIdentity_Get()
            status_text = self._translator.Text_Get(
                "status.loaded_exact",
                name=dataset.source_path.name,
                project=semantic_context.Project_Get(),
                firmware=semantic_context.FirmwareVersion_Get(),
                package_hash=identity.package_sha256[:12],
            )
        self.status_label.setText(status_text)
        self._Pages_Refresh()

    def _Pages_Refresh(self) -> None:
        if self._dataset is None or self._channel_resolver is None:
            return
        self.overview_page.Dataset_Set(self._dataset)
        self.replay_page.Dataset_Set(self._dataset, self._replay_store)
        self.flight_page.Dataset_Set(self._dataset, self._channel_resolver)
        self.state_estimation_page.Dataset_Set(
            self._dataset, self._channel_resolver
        )
        self.explorer_page.Dataset_Set(self._dataset, self._replay_store)

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
        entry = self._replay_store.Result_Add(result, algorithm_name=display_name)
        self.replay_page.Result_Set(entry)
        self._Pages_Refresh()
        self.status_label.setText(
            self._translator.Text_Get(
                "replay.complete",
                fidelity=self._translator.Text_Get(
                    f"replay.fidelity.{result.fidelity.value.lower()}"
                ),
            )
        )

    def _AnalysisSource_Set(self, source_id: str) -> None:
        if not self._replay_store.ActiveSource_Set(source_id):
            return
        self._Pages_Refresh()
        if self._channel_resolver is not None:
            source = self._channel_resolver.Source_Get(source_id)
            self.status_label.setText(
                self._translator.Text_Get(
                    "status.analysis_source_changed",
                    value=self._translator.Text_Get(f"status.{source.kind.value}"),
                )
            )

    def _Export_Start(self, output_path: Path, options: Any) -> None:
        if self._dataset is None:
            self.export_dialog.Result_Error(self._translator.Text_Get("status.no_data"))
            return
        selected = self.explorer_page.ExportChannels_Get()
        options = replace(options, selected_channels=selected)
        dataset = self._dataset
        exporter = FlightExporter(self._registry)
        worker = FunctionWorker(
            lambda context: exporter.export(
                dataset,
                output_path,
                options=options,
                replay_store=self._replay_store,
                context=context,
            )
        )
        self._Task_Start(
            worker,
            self._Export_ResultSet,
            self.export_dialog.Result_Error,
        )

    def _Export_ResultSet(self, manifest: ExportManifest) -> None:
        self.export_dialog.Result_Set(manifest)
        code = "export.complete_with_failures" if manifest.failures else "export.complete"
        self.status_label.setText(
            self._translator.Text_Get(
                code,
                count=len(manifest.files),
                failures=len(manifest.failures),
            )
        )

    def _ExportManifest_Open(self, manifest_path: Path) -> None:
        path = Path(manifest_path)
        try:
            opened = path.is_file() and QDesktopServices.openUrl(
                QUrl.fromLocalFile(str(path.resolve()))
            )
        except Exception:
            logging.exception("Export manifest open failed: %s", path)
            opened = False
        if not opened:
            self.export_dialog.ManifestOpen_Error()

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
        self.import_action.setEnabled(False)
        self.export_action.setEnabled(False)
        self.open_project_action.setEnabled(False)
        self.save_project_action.setEnabled(False)
        self.save_project_as_action.setEnabled(False)
        self._thread_pool.start(worker)

    def _Task_Progress(self, progress: float, code: str) -> None:
        self.progress_bar.setValue(int(progress * 1000))
        self.status_label.setText(self._translator.Text_Get(code))

    def _Task_Error(self, message: str, traceback_text: str) -> None:
        logging.error("Background task failed: %s\n%s", message, traceback_text)
        if self._worker_error_callback is not None:
            self._worker_error_callback(message)
        else:
            self._Error_Show(message)

    def _Task_Finish(self) -> None:
        self.progress_bar.setVisible(False)
        self.cancel_button.setVisible(False)
        self.import_action.setEnabled(True)
        self.export_action.setEnabled(self._dataset is not None)
        self.open_project_action.setEnabled(True)
        self.save_project_action.setEnabled(True)
        self.save_project_as_action.setEnabled(True)
        self.export_dialog.Task_Finish()
        self.replay_page.Task_Finish()
        self._active_worker = None
        self._worker_error_callback = None

    def _Task_Cancel(self) -> None:
        if self._active_worker is not None:
            self._active_worker.Worker_Cancel()
            self.cancel_button.setEnabled(False)

    def _ProjectDialog_Open(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self,
            self._translator.Text_Get("action.open_project"),
            str(Path.home()),
            "SilverStar project (*.ssflp)",
        )
        if not selected:
            return
        self._Project_Open(Path(selected))

    def _Project_Save(self) -> None:
        path = self._project.project_path
        if path is None:
            path = self._ProjectPath_Select("action.save_project")
        if path is not None:
            self._Project_Write(path)

    def _Project_SaveAs(self) -> None:
        path = self._ProjectPath_Select("action.save_project_as")
        if path is not None:
            self._Project_Write(path)

    def _ProjectPath_Select(self, title_key: str) -> Path | None:
        suggested_path = self._project.project_path or Path.cwd() / "flight.ssflp"
        selected, _ = QFileDialog.getSaveFileName(
            self,
            self._translator.Text_Get(title_key),
            str(suggested_path),
            "SilverStar project (*.ssflp)",
        )
        if not selected:
            return None
        path = Path(selected)
        return path if path.suffix.lower() == ".ssflp" else path.with_suffix(".ssflp")

    def _Project_Write(self, path: Path) -> None:
        try:
            self._project.replay_configurations = {
                entry.result_id: {
                    "algorithm_id": entry.algorithm_id,
                    "mode": entry.mode.value,
                    "input_source": entry.input_source,
                    "parameters": dict(entry.parameters),
                    "fidelity": entry.fidelity.value,
                }
                for entry in self._replay_store.Entries_Get()
            }
            Project_Save(self._project, path)
            self.status_label.setText(self._translator.Text_Get("status.project_saved", path=path))
        except Exception as exc:
            logging.exception("Project save failed")
            self._Error_Show(str(exc))

    def _Error_Show(self, message: str) -> None:
        code, separator, details = message.partition(":")
        translation_key = f"error.code.{code.strip()}"
        translated = self._translator.Text_Get(translation_key)
        display_message = (
            translated + (f"\n{details.strip()}" if separator and details.strip() else "")
            if translated != translation_key
            else message
        )
        QMessageBox.critical(
            self,
            self._translator.Text_Get("error.title"),
            f"{display_message}\n\n{self._translator.Text_Get('error.detail_saved')}",
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
        self.version_label.setText(f"v{__version__}")
        self.credit_label.setText(self._translator.Text_Get("app.credit"))
        self.language_label.setText(self._translator.Text_Get("label.interface_language"))
        self.theme_label.setText(self._translator.Text_Get("label.theme"))
        self.cancel_button.setText(self._translator.Text_Get("action.cancel"))
        self.file_menu.setTitle(self._translator.Text_Get("menu.file"))
        self.import_action.setText(self._translator.Text_Get("action.import"))
        self.export_action.setText(self._translator.Text_Get("action.export"))
        self.open_project_action.setText(self._translator.Text_Get("action.open_project"))
        self.save_project_action.setText(self._translator.Text_Get("action.save_project"))
        self.save_project_as_action.setText(
            self._translator.Text_Get("action.save_project_as")
        )
        for index in range(self.navigation_list.count()):
            item = self.navigation_list.item(index)
            page_code = str(item.data(Qt.ItemDataRole.UserRole))
            item.setText(self._translator.Text_Get(page_code))
        for page in self._page_widgets:
            page.Language_Apply(self._translator)
        self.import_dialog.Language_Apply(self._translator)
        self.export_dialog.Language_Apply(self._translator)
        if self._dataset is None:
            self.status_label.setText(self._translator.Text_Get("status.ready"))
        elif self._dataset.semantic_context is not None:
            context = self._dataset.semantic_context
            identity = context.PackageIdentity_Get()
            self.status_label.setText(
                self._translator.Text_Get(
                    "status.loaded_exact",
                    name=self._dataset.source_path.name,
                    project=context.Project_Get(),
                    firmware=context.FirmwareVersion_Get(),
                    package_hash=identity.package_sha256[:12],
                )
            )
        else:
            self.status_label.setText(
                self._translator.Text_Get(
                    "status.loaded_file",
                    name=self._dataset.source_path.name,
                    count=self._dataset.diagnostics.decoded_record_count,
                )
            )
        self.setWindowTitle(PRODUCT_NAME)

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
        WindowCaption_Apply(self, theme)
        self.flight_page.Theme_Apply(theme)
        self.state_estimation_page.Theme_Apply(theme)
        self.export_dialog.Theme_Set(theme)

    @staticmethod
    def _DropPaths_Validate(urls: list[QUrl]) -> tuple[Path, ...] | None:
        if not urls or any(not url.isLocalFile() for url in urls):
            return None
        paths = tuple(Path(url.toLocalFile()) for url in urls)
        project_paths = tuple(
            path for path in paths if path.suffix.casefold() == ".ssflp"
        )
        log_paths = tuple(
            path for path in paths if path.suffix.casefold() in (".bin", ".sslog")
        )
        decoder_paths = tuple(
            path for path in paths if path.suffix.casefold() == ".ssdecoder"
        )
        if len(project_paths) == 1 and len(paths) == 1:
            return paths
        if (
            len(log_paths) == 1
            and len(decoder_paths) <= 1
            and len(paths) == len(log_paths) + len(decoder_paths)
        ):
            return paths
        return None

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if self._DropPaths_Validate(event.mimeData().urls()) is not None:
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        paths = self._DropPaths_Validate(event.mimeData().urls())
        if paths is None:
            self._Error_Show("drop_selection_invalid")
            event.ignore()
            return
        project_paths = tuple(
            path for path in paths if path.suffix.casefold() == ".ssflp"
        )
        if project_paths:
            self._Project_Open(project_paths[0])
            event.acceptProposedAction()
            return
        log_path = next(
            path for path in paths if path.suffix.casefold() in (".bin", ".sslog")
        )
        decoder_path = next(
            (path for path in paths if path.suffix.casefold() == ".ssdecoder"),
            None,
        )
        if decoder_path is None:
            self.Log_Open(
                log_path,
                auto_find=True,
                source_mode=LogOpenSourceMode.DRAG_DROP,
            )
        else:
            self.Log_Open(
                log_path,
                decoder_path=decoder_path,
                source_mode=LogOpenSourceMode.DRAG_DROP,
            )
        event.acceptProposedAction()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._active_worker is not None:
            self._active_worker.Worker_Cancel()
        event.accept()
