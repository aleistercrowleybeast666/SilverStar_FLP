from __future__ import annotations

import hashlib
from pathlib import Path

from silverstar_flp.core.project import Project_Load, Project_Save, ProjectDocument
from silverstar_flp.export.service import ExportLanguage, ExportOptions, FlightExporter
from silverstar_flp.plugins.log_parsers.sslog0.plugin import Sslog0ParserPlugin
from tests.sslog_synthetic import StationaryFlight_Build


def test_project_contains_references_only_and_raw_log_remains_unchanged(tmp_path: Path) -> None:
    log_path = StationaryFlight_Build(tmp_path / "SYNTHETIC_project_source.BIN")
    before = hashlib.sha256(log_path.read_bytes()).hexdigest()
    project_path = tmp_path / "flight.ssflp"
    document = ProjectDocument(project_path=project_path)
    document.LogReference_Add(log_path)
    document.notes = "synthetic fixture"
    Project_Save(document, project_path)
    loaded = Project_Load(project_path)
    assert loaded.LogPaths_Resolve() == (log_path.resolve(),)
    project_text = project_path.read_text(encoding="utf-8")
    assert "SSLOG0" not in project_text
    assert hashlib.sha256(log_path.read_bytes()).hexdigest() == before


def test_export_keeps_independent_channel_timestamps_and_language_suffix(
    tmp_path: Path,
) -> None:
    log_path = StationaryFlight_Build(tmp_path / "SYNTHETIC_export_source.BIN")
    dataset = Sslog0ParserPlugin().parse(log_path)
    before = hashlib.sha256(log_path.read_bytes()).hexdigest()
    manifest = FlightExporter().export(
        dataset,
        tmp_path / "exported",
        options=ExportOptions(
            language=ExportLanguage.EN,
            include_plots=False,
            include_trajectory_3d=False,
            include_attitude_gif=False,
        ),
    )
    assert manifest.files
    assert all("_EN" in path.name or "CSV_EN" in str(path.parent) for path in manifest.files)
    csv_files = [path for path in manifest.files if path.suffix.lower() == ".csv"]
    assert csv_files
    inertial_csv = next(path for path in csv_files if "inertial.increment.dt" in path.name)
    rows = inertial_csv.read_text(encoding="utf-8-sig").splitlines()
    assert "timestamp_us" in rows[1]
    assert len(rows) == 10  # metadata + header + eight real-rate samples
    assert hashlib.sha256(log_path.read_bytes()).hexdigest() == before
