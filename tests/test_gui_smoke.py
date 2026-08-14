from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QApplication

from silverstar_flp.plugins.log_parsers.sslog0.plugin import Sslog0ParserPlugin
from silverstar_flp.plugins.registry import builtin_registry
from silverstar_flp.ui.main_window import MainWindow
from silverstar_flp.ui.widgets import StandardComboBox
from tests.sslog_synthetic import StationaryFlight_Build


def test_six_page_gui_and_top_bar_accept_a_parsed_dataset(tmp_path: Path) -> None:
    application = QApplication.instance() or QApplication([])
    dataset = Sslog0ParserPlugin().parse(
        StationaryFlight_Build(tmp_path / "SYNTHETIC_gui_source.BIN")
    )
    window = MainWindow(builtin_registry())
    window._Dataset_Set(dataset)
    window.show()
    application.processEvents()
    assert window.pages.count() == 6
    assert window.timeline_frame.isVisibleTo(window)
    assert window.explorer_page.channel_list.count() == len(dataset.series)
    assert window.pages.indexOf(window.export_dialog) == -1
    assert window.import_dialog.isModal()
    assert window.export_dialog.isModal()
    assert window.export_button.isEnabled()

    combos = (
        window.language_combo,
        window.theme_combo,
        window.attitude_page.source_combo,
        window.replay_page.algorithm_combo,
        window.replay_page.source_combo,
        window.replay_page.mode_combo,
        window.explorer_page.record_combo,
        window.import_dialog.source_type_combo,
        window.export_dialog.export_language_combo,
        window.export_dialog.export_theme_combo,
    )
    assert all(isinstance(combo, StandardComboBox) for combo in combos)
    assert all(combo.maxVisibleItems() == 10 for combo in combos)
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

    window.Language_Apply("zh_CN")
    assert window.import_button.text() == "导入"
    assert window.replay_page.parameters_group.title() == "假设参数"
    window.Language_Apply("en_US")
    assert window.import_button.text() == "Import"
    assert window.replay_page.parameters_group.title() == "What-if parameters"

    window.Theme_Apply("light")
    assert "#123A78" in application.styleSheet()
    window.navigation_list.setCurrentRow(1)
    application.processEvents()
    chart_width, trajectory_width = window.flight_page.splitter.sizes()
    assert trajectory_width >= chart_width * 0.9
    assert (
        window.replay_page.scroll_area.verticalScrollBarPolicy()
        == Qt.ScrollBarPolicy.ScrollBarAsNeeded
    )
    window.navigation_list.setCurrentRow(4)
    window.replay_page.algorithm_combo.setCurrentIndex(1)
    window.replay_page.mode_combo.setCurrentIndex(1)
    application.processEvents()
    assert window.replay_page.scroll_area.verticalScrollBar().maximum() > 0
    window.close()
