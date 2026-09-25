from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from silverstar_flp.core.i18n import Translator
from silverstar_flp.ui.navigation_diagnostics import NavigationDiagnostics


def _Dataset_Build():
    measurement = SimpleNamespace(payload={
        "replay_epoch": 3,
        "sequence": 17,
        "estimator_present_timestamp_us": 2_000_000,
        "valid_group_mask": 15,
        "group_update_result": (0, 0, 0, 0),
        "group_nis": (1.0, 1.0, 1.0, 1.0),
        "position_innovation_m": (0.1, 0.2, 0.3),
        "velocity_innovation_mps": (0.1, 0.2, 0.3),
        "position_variance_m2": (1.0, 1.0, 1.0),
        "velocity_variance_m2ps2": (1.0, 1.0, 1.0),
        "position_operation_sequence": 4,
        "velocity_operation_sequence": 5,
    })
    wrong_recovery = SimpleNamespace(payload={
        "replay_epoch": 3,
        "source_sequence": 17,
        "estimator_present_timestamp_us": 2_040_000,
        "quality_reject_mask": (1, 1, 1, 1),
    })
    records = {
        "GNSS_MEASUREMENT": (measurement,),
        "GNSS_RECOVERY": (wrong_recovery,),
    }
    return SimpleNamespace(
        start_timestamp_us=1_000_000,
        Records_Get=lambda name: records.get(name, ()),
    )


def _Resolver_Build(entry):
    store = SimpleNamespace(
        ActiveSource_Get=lambda: SimpleNamespace(
            source_id="recorded" if entry is None else "replay:one"
        ),
        SourceEntry_Get=lambda _source_id: entry,
    )
    return SimpleNamespace(store=store)


def test_gnss_diagnostics_route_recorded_pure_ins_and_kf6() -> None:
    app = QApplication.instance() or QApplication([])
    page = NavigationDiagnostics("gnss", Translator("en_US"))
    dataset = _Dataset_Build()
    page.Dataset_Set(dataset, _Resolver_Build(None))
    assert page.model.rowCount() == 4
    assert page.model.rows[0]["quality"] is None
    assert "Onboard record" in page.note.text()

    pure_ins = SimpleNamespace(
        algorithm_id="silverstar.algorithm.pure_ins", run_index=2,
        diagnostics={},
    )
    page.Dataset_Set(dataset, _Resolver_Build(pure_ins))
    assert page.model.rowCount() == 4
    assert "no GNSS fusion" in page.note.text()

    kf6 = SimpleNamespace(
        algorithm_id="silverstar.algorithm.kf6", run_index=3,
        diagnostics={"gnss_group_updates": ({
            "timestamp_us": 2_000_000, "group": "position_en",
            "valid": True, "result": 0, "nis": 1.0,
        },)},
    )
    page.Dataset_Set(dataset, _Resolver_Build(kf6))
    assert page.model.rowCount() == 1
    assert "Replay #3" in page.note.text()
    page.TimeRange_Set(2.0, 3.0)
    assert page.model.rowCount() == 0
    assert "0 rows" in page.count_note.text()
    page.full_range_button.click()
    assert page.model.rowCount() == 1

    kf6.diagnostics = {}
    page.Dataset_Set(dataset, _Resolver_Build(kf6))
    assert page.model.rowCount() == 0
    assert "no GNSS update diagnostics" in page.note.text()
    page.close()
    app.processEvents()
