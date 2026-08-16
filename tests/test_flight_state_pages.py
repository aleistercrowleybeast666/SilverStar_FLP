from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

from silverstar_flp.core.analysis_source import ChannelResolver, ReplayResultStore
from silverstar_flp.core.i18n import Translator
from silverstar_flp.core.visual_semantics import (
    TRAJECTORY_DEPLOY_COLOR,
    TRAJECTORY_POST_DEPLOY_COLOR,
    TRAJECTORY_PRE_DEPLOY_COLOR,
    RocketFaceColors_Get,
    TrajectoryMarkerWorldSizes_Get,
    TrajectoryPhaseColor_Get,
)
from silverstar_flp.plugins.algorithms.pure_ins.plugin import PureInsAlgorithmPlugin
from silverstar_flp.plugins.api.algorithm import ReplayRequest
from silverstar_flp.plugins.log_parsers.sslog0.plugin import Sslog0ParserPlugin
from silverstar_flp.ui.pages.charts import (
    FlightPage,
    _RocketFaceColors_Get,
    _TrajectoryOrigin_Get,
)
from silverstar_flp.ui.pages.state_estimation import StateEstimationPage
from tests.sslog_synthetic import START_TIMESTAMP_US, AnalysisFlight_Build


def test_trajectory_marker_sizes_are_world_scaled_and_phase_color_changes() -> None:
    small = np.asarray(((0.0, 0.0, 0.0), (1.0, 0.5, 0.25)))
    large = small * 500.0
    small_sizes = np.asarray(TrajectoryMarkerWorldSizes_Get(small))
    large_sizes = np.asarray(TrajectoryMarkerWorldSizes_Get(large))
    assert np.allclose(large_sizes, small_sizes * 500.0)
    assert TrajectoryPhaseColor_Get(99, 100) == TRAJECTORY_PRE_DEPLOY_COLOR
    assert TrajectoryPhaseColor_Get(100, 100) == TRAJECTORY_POST_DEPLOY_COLOR


def test_flight_tabs_start_crop_complete_vectors_and_active_source(
    tmp_path: Path,
) -> None:
    application = QApplication.instance() or QApplication([])
    dataset = Sslog0ParserPlugin().parse(
        AnalysisFlight_Build(tmp_path / "SYNTHETIC_flight_page.BIN")
    )
    result = PureInsAlgorithmPlugin().run(
        dataset,
        ReplayRequest(),
    )
    store = ReplayResultStore()
    entry = store.Result_Add(result, algorithm_name="Pure INS")
    assert store.ActiveSource_Set(entry.source_id)
    resolver = ChannelResolver(dataset, store)

    page = FlightPage(Translator("en_US"))
    page.Dataset_Set(dataset, resolver)
    page.show()
    application.processEvents()

    assert page.tabs.count() == 6
    assert page._start_timestamp_us == START_TIMESTAMP_US
    assert page._position is result.channels["navigation.position_enu"]
    assert page._attitude is result.channels["attitude.q_nb"]
    assert not hasattr(page, "source_combo")
    assert "Pure INS" in page.source_value_label.text()
    assert len(page.velocity_plot.listDataItems()) == 9
    assert len(page.position_plot.listDataItems()) == 9
    assert len(page.acceleration_plot.listDataItems()) == 3
    assert len(page.angular_rate_plot.listDataItems()) == 3
    assert len(page.quaternion_plot.listDataItems()) == 8
    assert len(page.euler_plot.listDataItems()) == 6
    assert page._deploy_timestamp_us == START_TIMESTAMP_US + 110_000
    assert page.playback_slider.parent() is not None
    assert page.reset_charts_button.text() == "Reset Charts"
    page.velocity_plot.setXRange(200.0, 201.0, padding=0)
    page.velocity_plot.setYRange(200.0, 201.0, padding=0)
    velocity_legend = page.velocity_plot.getPlotItem().legend
    velocity_legend.setPos(180.0, 140.0)
    assert not all(page.velocity_plot.getViewBox().state["autoRange"])
    page.reset_charts_button.click()
    assert all(page.velocity_plot.getViewBox().state["autoRange"])
    assert np.allclose(
        (velocity_legend.pos().x(), velocity_legend.pos().y()),
        (30.0, 30.0),
    )
    velocity_names = {
        item.name() for item in page.velocity_plot.listDataItems() if item.name()
    }
    assert any("Recorded Pure INS" in name for name in velocity_names)
    assert any("Recorded KF_6" in name for name in velocity_names)
    velocity_colors = [
        item.opts["pen"].color().name()
        for item in page.velocity_plot.listDataItems()
    ]
    assert len(velocity_colors) == len(set(velocity_colors))
    assert np.allclose(
        page._trajectory_origin,
        _TrajectoryOrigin_Get(page._position, START_TIMESTAMP_US),
    )

    if hasattr(page, "pre_deploy_line"):
        page.trajectory_view.opts["distance"] = 123.0
        page.playback_slider.setValue(2500)
        application.processEvents()
        assert np.allclose(
            page.current_marker.color,
            QColor(TRAJECTORY_PRE_DEPLOY_COLOR).getRgbF(),
        )
        assert page.current_marker.pxMode is False
        assert page.deploy_marker.pxMode is False
        assert not hasattr(page, "deploy_marker_outline")
    page.playback_slider.setValue(10000)
    application.processEvents()
    if hasattr(page, "pre_deploy_line"):
        assert page.trajectory_view.opts["distance"] == 123.0
        assert page.pre_deploy_line.pos.shape[0] > 0
        assert page.post_deploy_line.pos.shape[0] > 0
        assert np.allclose(page.pre_deploy_line.pos[0], np.zeros(3), atol=1.0e-5)
        assert page.landing_marker.pos.shape[0] == 1
        assert page.rocket_mesh is not None
        assert not hasattr(page, "start_marker")
        assert len(page._trajectory_text_items) == 3
        expected_light_faces = np.asarray(
            [QColor(color).getRgbF() for color in RocketFaceColors_Get("light")],
            dtype=np.float32,
        )
        assert np.allclose(_RocketFaceColors_Get("light"), expected_light_faces)
        assert page.deploy_marker.pos.shape[0] == 1
        assert np.allclose(
            page.deploy_marker.color,
            QColor(TRAJECTORY_DEPLOY_COLOR).getRgbF(),
        )
        assert np.allclose(
            page.current_marker.color,
            QColor(TRAJECTORY_POST_DEPLOY_COLOR).getRgbF(),
        )
        valid_values = np.asarray(page._position.values)[page._position.valid]
        expected_sizes = TrajectoryMarkerWorldSizes_Get(
            valid_values - page._trajectory_origin
        )
        assert np.allclose(page._trajectory_marker_sizes, expected_sizes)
        assert np.isclose(page.deploy_marker.size, expected_sizes[0])
        assert np.isclose(page.current_marker.size, expected_sizes[1])
        assert page.deploy_marker.depthValue() > page.current_marker.depthValue()
        page.Theme_Apply("dark")
        expected_background = (17 / 255, 24 / 255, 39 / 255)
        assert np.allclose(
            page.attitude_view.opts["bgcolor"][:3],
            expected_background,
        )
        assert np.allclose(
            page.trajectory_view.opts["bgcolor"][:3],
            expected_background,
        )
    page.close()


def test_state_estimation_shows_recorded_kf6_diagnostics_and_i18n(
    tmp_path: Path,
) -> None:
    application = QApplication.instance() or QApplication([])
    dataset = Sslog0ParserPlugin().parse(
        AnalysisFlight_Build(tmp_path / "SYNTHETIC_state_page.BIN")
    )
    resolver = ChannelResolver(dataset, ReplayResultStore())
    page = StateEstimationPage(Translator("en_US"))
    page.Dataset_Set(dataset, resolver)
    page.show()
    application.processEvents()

    assert page.tabs.count() == 5
    assert not hasattr(page, "source_combo")
    assert "Recorded" in page.source_value_label.text()
    assert page.state_group_combo.count() == 2
    assert page.innovation_measurement_combo.count() == 3
    assert page.nis_measurement_combo.count() == 3
    assert page.measurement_group_combo.count() == 3
    assert len(page.covariance_plot.listDataItems()) == 3
    assert len(page.innovation_plot.listDataItems()) == 3
    assert len(page.nis_plot.listDataItems()) == 3
    assert len(page.measurement_uncertainty_plot.listDataItems()) == 3
    assert len(page.measurement_r_scale_plot.listDataItems()) == 1
    assert len(page.measurement_age_plot.listDataItems()) == 1
    assert page.update_table.rowCount() == 24
    assert page.update_table.item(0, 1).text() == "GNSS Position"
    assert page.update_table.item(0, 3).text() == "Accepted"
    assert page.update_table.item(1, 3).text() == "Soft Weighted"
    assert page.update_table.item(2, 3).text() == "NIS Rejected"
    assert page.reset_charts_button.text() == "Reset Charts"
    page.nis_plot.setXRange(200.0, 201.0, padding=0)
    page.nis_plot.setYRange(200.0, 201.0, padding=0)
    page.reset_charts_button.click()
    assert all(page.nis_plot.getViewBox().state["autoRange"])

    page.Language_Apply(Translator("zh_CN"))
    application.processEvents()
    assert page.reset_charts_button.text() == "复位图表"
    assert page.tabs.tabText(3) == "序贯更新"
    assert page.tabs.tabText(2) == "归一化新息平方（NIS）"
    assert page.update_table.item(0, 3).text() == "接受"
    assert page.update_table.item(1, 3).text() == "软加权"
    assert page.update_table.item(2, 3).text() == "NIS拒绝"
    page.close()


def test_trajectory_hides_deploy_point_when_no_deploy_event(
    tmp_path: Path,
) -> None:
    application = QApplication.instance() or QApplication([])
    dataset = Sslog0ParserPlugin().parse(
        AnalysisFlight_Build(
            tmp_path / "SYNTHETIC_no_deploy_marker.BIN",
            include_deploy_detail=False,
            include_deploy_event=False,
        )
    )
    page = FlightPage(Translator("en_US"))
    page.Dataset_Set(dataset, ChannelResolver(dataset, ReplayResultStore()))
    page.playback_slider.setValue(10000)
    application.processEvents()
    assert page._deploy_timestamp_us is None
    if hasattr(page, "deploy_marker"):
        assert page.deploy_marker.pos.shape[0] == 0
    page.close()
