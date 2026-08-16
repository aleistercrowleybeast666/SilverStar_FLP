from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QApplication, QFileDialog, QPushButton

from silverstar_flp.app.version import PRODUCT_NAME, __version__
from silverstar_flp.plugins.log_parsers.sslog0.plugin import Sslog0ParserPlugin
from silverstar_flp.plugins.registry import builtin_registry
from silverstar_flp.ui.main_window import MainWindow
from silverstar_flp.ui.widgets import StandardComboBox
from tests.sslog_synthetic import AnalysisFlight_Build


def test_five_page_gui_and_top_bar_accept_a_parsed_dataset(
    tmp_path: Path,
    monkeypatch,
) -> None:
    application = QApplication.instance() or QApplication([])
    dataset = Sslog0ParserPlugin().parse(
        AnalysisFlight_Build(tmp_path / "SYNTHETIC_gui_source.BIN")
    )
    window = MainWindow(builtin_registry())
    window._Dataset_Set(dataset)
    window.show()
    application.processEvents()
    assert window.pages.count() == 5
    assert window.windowTitle() == PRODUCT_NAME
    assert window.title_label.text() == "SilverStar 飞行日志解析器"
    assert window.version_label.text() == f"v{__version__}" == "v0.0.2"
    assert window.credit_label.text() == "辰星引力开发"
    assert dataset.source_path.name not in window.windowTitle()
    assert not hasattr(window, "timeline_frame")
    assert not hasattr(window, "timeline_slider")
    assert not hasattr(window, "attitude_page")
    assert not hasattr(window, "navigation_page")
    assert window.flight_page.tabs.count() == 6
    assert window.state_estimation_page.tabs.count() == 5
    assert (
        window.overview_page.calibration_group.geometry().top()
        == window.overview_page.alignment_group.geometry().top()
    )
    assert (
        window.overview_page.timeline_group.geometry().top()
        >= window.overview_page.calibration_group.geometry().bottom()
    )
    overview_buttons = window.overview_page.findChildren(QPushButton)
    assert all(button.text() not in ("查看详情", "Details") for button in overview_buttons)
    assert window.overview_page.calibration_group.property("statusLevel") == "success"
    assert window.overview_page.alignment_group.property("statusLevel") == "success"
    assert window.explorer_page.channel_list.count() == len(dataset.series)
    assert window.pages.indexOf(window.export_dialog) == -1
    assert window.import_dialog.isModal()
    assert window.export_dialog.isModal()
    assert window.export_action.isEnabled()
    assert not hasattr(window, "export_button")
    assert not hasattr(window, "import_button")
    assert window.toolbar.actions() == [
        window.import_action,
        window.export_action,
        window.save_project_action,
        window.open_project_action,
    ]
    assert [action for action in window.file_menu.actions() if not action.isSeparator()] == [
        window.import_action,
        window.export_action,
        window.save_project_action,
        window.save_project_as_action,
        window.open_project_action,
    ]
    assert all(not action.isSeparator() for action in window.file_menu.actions())
    saved_as_path = tmp_path / "SYNTHETIC_gui_project_copy.ssflp"
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        lambda *args, **kwargs: (str(saved_as_path), "SilverStar project (*.ssflp)"),
    )
    window.save_project_as_action.trigger()
    assert saved_as_path.is_file()
    assert window._project.project_path == saved_as_path.resolve()
    assert not hasattr(window.flight_page, "source_combo")
    assert not hasattr(window.state_estimation_page, "source_combo")
    assert not hasattr(window.replay_page, "source_combo")

    combos = (
        window.language_combo,
        window.theme_combo,
        window.flight_page.playback_speed_combo,
        window.replay_page.algorithm_combo,
        window.replay_page.analysis_source_combo,
        window.replay_page.mode_combo,
        window.replay_page.parameter_group_combo,
        window.state_estimation_page.state_group_combo,
        window.state_estimation_page.covariance_display_combo,
        window.state_estimation_page.innovation_measurement_combo,
        window.state_estimation_page.nis_measurement_combo,
        window.state_estimation_page.measurement_group_combo,
        window.explorer_page.record_combo,
        window.import_dialog.source_type_combo,
        window.export_dialog.export_language_combo,
        window.export_dialog.export_theme_combo,
    )
    assert all(isinstance(combo, StandardComboBox) for combo in combos)
    assert all(combo.maxVisibleItems() == 10 for combo in combos)
    assert window.language_combo.view().objectName() == "headerComboPopup"
    assert window.theme_combo.view().objectName() == "headerComboPopup"
    long_combo = StandardComboBox(window)
    long_combo.addItems([f"item-{index}" for index in range(11)])
    long_combo.setCurrentIndex(10)
    long_combo.move(260, 140)
    long_combo.resize(180, 30)
    long_combo.show()
    long_combo.showPopup()
    application.processEvents()
    assert long_combo.view().verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAsNeeded
    combo_bottom = long_combo.mapToGlobal(QPoint(0, long_combo.height())).y()
    assert long_combo.view().window().geometry().top() >= combo_bottom - 1
    long_combo.hidePopup()

    if window.flight_page.trajectory_view is not None:
        window.flight_page.trajectory_view.opts["distance"] = 73.0
    window.Language_Apply("zh_CN")
    assert window.import_action.text() == "导入"
    assert window.toolbar.actions()[1].text() == "导出"
    assert window.save_project_action.text() == "保存工程"
    assert window.open_project_action.text() == "打开工程"
    assert window.save_project_as_action.text() == "另存为…"
    assert window.title_label.text() == "SilverStar 飞行日志解析器"
    assert window.credit_label.text() == "辰星引力开发"
    assert window.replay_page.parameters_group.title() == "假设参数"
    window.Language_Apply("en_US")
    assert window.import_action.text() == "Import"
    assert window.save_project_action.text() == "Save Project"
    assert window.open_project_action.text() == "Open Project"
    assert window.save_project_as_action.text() == "Save Project As…"
    assert window.title_label.text() == "SilverStar Flight Log Parser"
    assert window.credit_label.text() == "By CXYL"
    assert window.replay_page.parameters_group.title() == "What-if parameters"
    assert window.windowTitle() == PRODUCT_NAME
    if window.flight_page.trajectory_view is not None:
        assert window.flight_page.trajectory_view.opts["distance"] == 73.0

    window.Theme_Apply("light")
    style_sheet = application.styleSheet()
    assert "#123A78" in style_sheet
    assert "#D6E6FF" in style_sheet
    assert "QAbstractItemView#headerComboPopup" in style_sheet
    assert (
        "QListWidget#navigation::item:selected { background: #2F6FED; color: #FFFFFF; }"
        in style_sheet
    )
    assert "QTabBar::tab:selected" in style_sheet
    assert "QToolBar#mainToolBar" in style_sheet
    window.navigation_list.setCurrentRow(2)
    application.processEvents()
    attitude_width, trajectory_width = window.flight_page.replay_splitter.sizes()
    assert trajectory_width >= attitude_width * 0.9
    assert window.flight_page.playback_slider.maximum() == 10000
    assert (
        window.replay_page.scroll_area.verticalScrollBarPolicy()
        == Qt.ScrollBarPolicy.ScrollBarAsNeeded
    )
    window.navigation_list.setCurrentRow(1)
    window.replay_page.algorithm_combo.setCurrentIndex(1)
    window.replay_page.mode_combo.setCurrentIndex(1)
    application.processEvents()
    assert window.replay_page.scroll_area.verticalScrollBar().maximum() > 0
    assert window.overview_page.scroll_area.widgetResizable()
    window.close()
