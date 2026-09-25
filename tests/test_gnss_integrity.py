from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from silverstar_flp.analysis.gnss_integrity import GeoLocal_ToEnu, GnssIntegrity_Build
from silverstar_flp.core.dataset import DecodedRecord, FlightDataset
from silverstar_flp.core.diagnostics import ParserDiagnostics
from silverstar_flp.export.service import ExportLanguage, ExportTheme, FlightExporter


def Dataset_Build(
    *, velocity_e=1.0, position_e_rate=1.0, noise=False,
    gap=False, invalid_pos_u=False, invalid_vel_en=False, position_usable=1,
):
    origin = dict(gnss_origin_latitude_e7=0, gnss_origin_longitude_e7=0,
                  gnss_origin_height_mm=0, origin_valid_flags=1)
    initial = DecodedRecord(0, "INITIAL_STATE", 1, 0, 0, 0, 0, origin, 0)
    east_per_e7 = GeoLocal_ToEnu(
        np.array([0]), np.array([1]), np.array([0]), (0, 0, 0)
    )[0, 0]
    native = []
    for index in range(501):
        if gap and 225 <= index <= 240:
            continue
        t = index * 40_000
        east = position_e_rate * (t * 1e-6)
        if noise and index == 300:
            east += 4.0
        payload = dict(
            source_descriptor_id=1, instance_id=0,
            sample_timestamp_us=t, sequence=index,
            latitude_e7=0, longitude_e7=round(east / east_per_e7),
            ellipsoid_height_mm=0, velocity_enu_mps=(velocity_e, 0.0, 0.0),
            valid_group_mask=(0x0F & (~2 if invalid_pos_u else 0x0F)
                              & (~4 if invalid_vel_en else 0x0F)),
            velocity_valid_mask=7, position_usable=position_usable,
            measurement_timestamp_trusted=1,
            horizontal_accuracy_m=1.0, vertical_accuracy_m=2.0,
            speed_accuracy_mps=.1, satellite_count=15,
        )
        native.append(DecodedRecord(0, "GNSS_NATIVE", 1, 0, index + 1,
                                    t, 0, payload, 0))
    return FlightDataset(
        Path("synthetic.bin"), 0, {}, ParserDiagnostics(),
        {"INITIAL_STATE": (initial,), "GNSS_NATIVE": tuple(native)}, {},
    )


@pytest.mark.parametrize("window", (1, 2, 5, 10))
def test_constant_velocity_closes_with_firmware_geodesy(window):
    result = GnssIntegrity_Build(Dataset_Build(), window)
    assert result.summary["horizontal"]["valid_window_count"] > 0
    assert result.summary["horizontal"]["p95_m"] < .03
    assert result.summary["vertical"]["max_m"] == 0


def test_position_drift_grows_with_window_and_is_not_nis():
    dataset = Dataset_Build(velocity_e=0, position_e_rate=1)
    medians = [GnssIntegrity_Build(dataset, window).summary["horizontal"]["median_m"]
               for window in (1, 2, 5, 10)]
    assert medians[0] < medians[1] < medians[2] < medians[3]
    np.testing.assert_allclose(medians, (1, 2, 5, 10), atol=.05)


def test_short_position_noise_has_finite_robust_statistics():
    result = GnssIntegrity_Build(Dataset_Build(noise=True), 5)
    stats = result.summary["horizontal"]
    assert stats["median_m"] < .03
    assert stats["max_m"] > 3.9
    assert stats["p95_m"] >= stats["median_m"]


def test_velocity_gap_invalidates_only_crossing_windows():
    result = GnssIntegrity_Build(Dataset_Build(gap=True), 5)
    assert not result.valid_en[230]
    assert result.summary["horizontal"]["coverage"] < 1
    assert result.valid_en[-1]


def test_position_u_invalid_leaves_horizontal_closure():
    result = GnssIntegrity_Build(Dataset_Build(invalid_pos_u=True), 5)
    assert result.valid_en.any()
    assert not result.valid_u.any()


def test_position_en_valid_with_aggregate_unusable_keeps_en_closure():
    result = GnssIntegrity_Build(
        Dataset_Build(invalid_pos_u=True, position_usable=0), 5
    )
    assert result.valid_en.any()
    assert result.anchored_valid_en.any()
    assert not result.valid_u.any()
    assert not result.anchored_valid_u.any()


def test_anchored_closure_detects_drift_and_resets_after_gap():
    clean = GnssIntegrity_Build(Dataset_Build(), 5)
    drift = GnssIntegrity_Build(Dataset_Build(velocity_e=0), 5)
    assert clean.summary["anchored_horizontal"]["p95_m"] < .03
    assert drift.anchored_residual_m[-1, 0] == pytest.approx(20.0, abs=.03)
    assert np.count_nonzero(drift.anchor_reset_en) == 1
    gapped = GnssIntegrity_Build(Dataset_Build(gap=True), 5)
    resets = np.flatnonzero(gapped.anchor_reset_en)
    assert len(resets) == 2
    assert np.isnan(gapped.anchored_residual_m[resets[1], 0])
    assert gapped.anchored_valid_en[-1]


def test_legacy_aggregate_validity_is_only_fallback():
    dataset = Dataset_Build()
    native = tuple(
        replace(record, payload={key: value for key, value in record.payload.items()
                                 if key != "valid_group_mask"})
        for record in dataset.Records_Get("GNSS_NATIVE")
    )
    legacy = replace(dataset, records={**dataset.records, "GNSS_NATIVE": native})
    assert GnssIntegrity_Build(legacy, 5).valid_en.any()


def test_velocity_en_invalid_leaves_vertical_closure():
    result = GnssIntegrity_Build(Dataset_Build(invalid_vel_en=True), 5)
    assert not result.valid_en.any()
    assert result.valid_u.any()


def test_invalid_origin_is_not_used_as_local_frame():
    dataset = Dataset_Build()
    initial = dataset.initial_state
    invalid = replace(initial, payload={**initial.payload, "origin_valid_flags": 0})
    dataset = replace(dataset, records={**dataset.records, "INITIAL_STATE": (invalid,)})
    with pytest.raises(ValueError, match="gnss_origin_unavailable"):
        GnssIntegrity_Build(dataset)


def test_nonfinite_vertical_velocity_leaves_horizontal_closure():
    dataset = Dataset_Build()
    native = tuple(
        replace(record, payload={**record.payload, "velocity_enu_mps": (1.0, 0.0, np.nan)})
        for record in dataset.Records_Get("GNSS_NATIVE")
    )
    dataset = replace(dataset, records={**dataset.records, "GNSS_NATIVE": native})
    result = GnssIntegrity_Build(dataset, 5)
    assert result.valid_en.any()
    assert not result.valid_u.any()


@pytest.mark.parametrize("language", (ExportLanguage.EN, ExportLanguage.ZH))
def test_integrity_export_plots_and_summary_render_in_selected_language(tmp_path, language):
    dataset = Dataset_Build()
    result = GnssIntegrity_Build(dataset, 5)
    exporter = FlightExporter()
    for kind in ("Position_Velocity_Displacement", "Closure_Error", "Receiver_Quality"):
        path = tmp_path / f"{kind}.png"
        exporter._GnssIntegrityPlot_Write(
            dataset, result, kind, path, language, ExportTheme.LIGHT, 0.0, 20.0
        )
        assert path.is_file() and path.stat().st_size > 1000
    summary = tmp_path / "summary.txt"
    exporter._GnssIntegritySummaryText_Write({5: result}, summary, language)
    content = summary.read_text(encoding="utf-8")
    assert ("覆盖率" if language is ExportLanguage.ZH else "coverage") in content


def test_integrity_gui_has_five_independent_tabs_and_shared_time_range():
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from silverstar_flp.core.i18n import Translator
    from silverstar_flp.ui.gnss_integrity import GnssIntegrityPage

    app = QApplication.instance() or QApplication([])
    page = GnssIntegrityPage(Translator("en_US"))
    page.Dataset_Set(Dataset_Build())
    page.resize(900, 600)
    page.show()
    app.processEvents()
    assert page.plot_tabs.count() == 5
    assert page.plot_tabs.widget(0) is page.plots[0]
    assert page.plot_tabs.widget(4) is page.plots[4]
    assert len(page.plots[1].listDataItems()) == 6
    assert any("Anchored" in item.name() for item in page.plots[1].listDataItems())
    page.TimeRange_Set(3.0, 8.0)
    for plot in page.plots:
        low, high = plot.getViewBox().viewRange()[0]
        assert abs(low - 3.0) < 1e-6 and abs(high - 8.0) < 1e-6
    page.window_combo.setCurrentIndex(page.window_combo.findData(2))
    assert page._result.window_s == 2
    page.Language_Apply(Translator("zh_CN"))
    assert page.plot_tabs.tabText(1) == "水平闭合误差 / m"
    page.close()
