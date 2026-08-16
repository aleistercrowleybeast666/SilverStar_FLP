from __future__ import annotations

import inspect
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PySide6.QtWidgets import QApplication

from silverstar_flp.core.analysis_source import ChannelResolver, ReplayResultStore
from silverstar_flp.core.context import TaskContext
from silverstar_flp.core.dataset import FlightDataset, TimeSeries
from silverstar_flp.core.i18n import Translator
from silverstar_flp.plugins.algorithms.kf6.plugin import Kf6AlgorithmPlugin
from silverstar_flp.plugins.algorithms.pure_ins.plugin import PureInsAlgorithmPlugin
from silverstar_flp.plugins.api.algorithm import (
    AlgorithmAvailability,
    AlgorithmMetadata,
    AlgorithmPlugin,
    AlgorithmResult,
    EstimatorVisualizationSpec,
    MeasurementGroupSpec,
    ReplayFidelity,
    ReplayRequest,
    StateGroupSpec,
)
from silverstar_flp.plugins.log_parsers.sslog0.plugin import Sslog0ParserPlugin
from silverstar_flp.plugins.registry import PluginRegistry
from silverstar_flp.ui.pages.state_estimation import StateEstimationPage
from tests.sslog_synthetic import START_TIMESTAMP_US, AnalysisFlight_Build


def _Series(
    timestamps: np.ndarray,
    values: np.ndarray,
    *,
    columns: tuple[str, ...] = (),
    unit: str = "1",
    quantity: str = "diagnostic",
) -> TimeSeries:
    return TimeSeries(
        timestamp_us=timestamps,
        values=np.asarray(values, dtype=np.float64),
        unit=unit,
        quantity=quantity,
        source="test.algorithm.fake_eskf",
        valid=np.ones(timestamps.size, dtype=np.bool_),
        columns=columns,
        metadata={"provenance": "Recomputed"},
    )


_FAKE_STATE_GROUPS = (
    StateGroupSpec(
        "position_error",
        "state.position_error",
        ("E", "N", "U"),
        "m",
        "fake.covariance.diagonal",
        (0, 1, 2),
    ),
    StateGroupSpec(
        "velocity_error",
        "state.velocity_error",
        ("E", "N", "U"),
        "m/s",
        "fake.covariance.diagonal",
        (3, 4, 5),
    ),
    StateGroupSpec(
        "attitude_error",
        "state.attitude_error",
        ("X", "Y", "Z"),
        "rad",
        "fake.covariance.diagonal",
        (6, 7, 8),
    ),
    StateGroupSpec(
        "gyro_bias",
        "state.gyro_bias",
        ("X", "Y", "Z"),
        "rad/s",
        "fake.covariance.diagonal",
        (9, 10, 11),
    ),
    StateGroupSpec(
        "accel_bias",
        "state.accel_bias",
        ("X", "Y", "Z"),
        "m/s²",
        "fake.covariance.diagonal",
        (12, 13, 14),
    ),
)


def _Measurement(
    group_id: str,
    label_key: str,
    index: int,
    dimension: int,
) -> MeasurementGroupSpec:
    components = ("E", "N", "U") if dimension == 3 else ("U",)
    return MeasurementGroupSpec(
        group_id,
        label_key,
        dimension,
        components,
        f"fake.innovation.{group_id}",
        f"fake.nis.{group_id}",
        "fake.update_result",
        "fake.r_scale",
        measurement_age_channel=f"fake.age.{group_id}",
        update_result_index=index,
        r_scale_index=index,
    )


class _FakeEskfPlugin(AlgorithmPlugin):
    metadata = AlgorithmMetadata(
        plugin_id="test.algorithm.fake_eskf",
        version="test",
        display_name="Fake ESKF",
        description="test-only metadata compatibility estimator",
        required_records=(),
        optional_records=(),
        required_channels=(),
        optional_channels=(),
        parameter_schema=(),
        standard_outputs=(
            "attitude.q_nb",
            "navigation.velocity_enu",
            "navigation.position_enu",
        ),
        diagnostic_outputs=("fake.covariance.diagonal",),
        estimator_visualization=EstimatorVisualizationSpec(
            state_groups=_FAKE_STATE_GROUPS,
            measurement_groups=(
                _Measurement("gnss_position", "measurement.gnss_position", 0, 3),
                _Measurement(
                    "barometric_altitude",
                    "measurement.barometric_altitude",
                    1,
                    1,
                ),
                _Measurement("magnetometer", "measurement.magnetometer", 2, 3),
            ),
        ),
    )

    def availability(
        self,
        dataset: FlightDataset,
        input_source: str | None = None,
    ) -> AlgorithmAvailability:
        del dataset, input_source
        return AlgorithmAvailability(True, ReplayFidelity.EXACT)

    def run(
        self,
        dataset: FlightDataset,
        request: ReplayRequest,
        context: TaskContext | None = None,
    ) -> AlgorithmResult:
        del dataset, request, context
        raise NotImplementedError


def _FakeResult_Create() -> AlgorithmResult:
    timestamps = np.asarray(
        [START_TIMESTAMP_US + index * 20_000 for index in range(4)],
        dtype=np.uint64,
    )
    channels = {
        "attitude.q_nb": _Series(
            timestamps,
            np.tile((1.0, 0.0, 0.0, 0.0), (4, 1)),
            columns=("W", "X", "Y", "Z"),
        ),
        "navigation.velocity_enu": _Series(
            timestamps,
            np.zeros((4, 3)),
            columns=("E", "N", "U"),
            unit="m/s",
        ),
        "navigation.position_enu": _Series(
            timestamps,
            np.zeros((4, 3)),
            columns=("E", "N", "U"),
            unit="m",
        ),
        "fake.covariance.diagonal": _Series(
            timestamps,
            np.tile(np.linspace(0.01, 0.15, 15), (4, 1)),
            columns=tuple(f"P{index}" for index in range(15)),
        ),
        "fake.update_result": _Series(
            timestamps,
            np.tile((0.0, 1.0, 2.0), (4, 1)),
            columns=("GNSS", "Baro", "Mag"),
        ),
        "fake.r_scale": _Series(
            timestamps,
            np.tile((1.0, 1.5, 2.0), (4, 1)),
            columns=("GNSS", "Baro", "Mag"),
        ),
    }
    for group in _FakeEskfPlugin.metadata.estimator_visualization.measurement_groups:
        channels[group.innovation_channel] = _Series(
            timestamps,
            np.ones((4, group.dimension)),
            columns=group.component_names,
        )
        channels[group.nis_channel] = _Series(
            timestamps,
            np.linspace(1.0, 2.0, 4),
            quantity="nis",
        )
        channels[group.measurement_age_channel] = _Series(
            timestamps,
            np.full(4, 10_000.0),
            unit="us",
            quantity="time",
        )
    return AlgorithmResult(
        algorithm_id=_FakeEskfPlugin.metadata.plugin_id,
        algorithm_version="test",
        input_source="corrected_imu",
        parameters={},
        fidelity=ReplayFidelity.EXACT,
        missing_inputs=(),
        warnings=(),
        channels=channels,
        provenance="Recomputed",
    )


def test_kf6_declares_estimator_visualization_and_parameter_groups() -> None:
    visualization = Kf6AlgorithmPlugin.metadata.estimator_visualization
    assert visualization is not None
    assert {group.group_id for group in visualization.state_groups} == {
        "position",
        "velocity",
    }
    assert {
        group.measurement_group_id for group in visualization.measurement_groups
    } == {
        "gnss_position",
        "gnss_velocity",
        "barometric_altitude",
    }
    assert {group.dimension for group in visualization.measurement_groups} == {1, 3}
    assert PureInsAlgorithmPlugin.metadata.estimator_visualization is None
    assert {
        parameter.group_key for parameter in Kf6AlgorithmPlugin.metadata.parameter_schema
    } == {
        "parameter_group.process_model",
        "parameter_group.initial_covariance",
        "parameter_group.measurement_noise",
        "parameter_group.consistency_gating",
    }


def test_fake_eskf_and_magnetometer_need_no_state_page_code_change(
    tmp_path: Path,
) -> None:
    application = QApplication.instance() or QApplication([])
    dataset = Sslog0ParserPlugin().parse(
        AnalysisFlight_Build(tmp_path / "SYNTHETIC_fake_eskf.BIN")
    )
    registry = PluginRegistry()
    registry.Algorithm_Register(_FakeEskfPlugin())
    store = ReplayResultStore()
    entry = store.Result_Add(_FakeResult_Create(), algorithm_name="Fake ESKF")
    assert store.ActiveSource_Set(entry.source_id)
    page = StateEstimationPage(Translator("en_US"), registry)
    page.Dataset_Set(dataset, ChannelResolver(dataset, store))
    page.show()
    application.processEvents()

    assert "kf6." not in inspect.getsource(StateEstimationPage)
    assert page.state_group_combo.count() == 5
    assert page.innovation_measurement_combo.count() == 3
    assert page.nis_measurement_combo.count() == 3
    assert page.measurement_group_combo.count() == 3
    assert len(page.covariance_plot.listDataItems()) == 3

    magnetometer = page.innovation_measurement_combo.findData("magnetometer")
    page.innovation_measurement_combo.setCurrentIndex(magnetometer)
    page.nis_measurement_combo.setCurrentIndex(
        page.nis_measurement_combo.findData("magnetometer")
    )
    page.measurement_group_combo.setCurrentIndex(
        page.measurement_group_combo.findData("magnetometer")
    )
    application.processEvents()
    assert len(page.innovation_plot.listDataItems()) == 3
    assert len(page.nis_plot.listDataItems()) == 1
    assert len(page.measurement_r_scale_plot.listDataItems()) == 1
    assert page.update_table.rowCount() == 12
    assert any(
        page.update_table.item(row, 1).text() == "Magnetometer"
        for row in range(page.update_table.rowCount())
    )

    page.Language_Apply(Translator("zh_CN"))
    assert page.tabs.tabText(2) == "归一化新息平方（NIS）"
    assert page.innovation_measurement_combo.currentText() == "磁力计"
    page.close()
