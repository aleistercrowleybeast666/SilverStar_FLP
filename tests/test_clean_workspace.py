from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from tools.clean_workspace import WorkspaceClean_Apply, WorkspaceClean_Plan, WorkspaceCleanResult


def _Repository_Create(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", str(root)], check=True, capture_output=True)
    return root


def _File_Write(root, name):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("preserve-or-clean", encoding="utf8")
    return path


def test_cleanup_dry_run_apply_and_protected_inputs(tmp_path):
    root = _Repository_Create(tmp_path)
    generated = _File_Write(root, "build/report.png")
    cache = _File_Write(root, "src/pkg/__pycache__/module.pyc")
    protected = [
        _File_Write(root, name)
        for name in (
            "build/flight.BIN",
            "build/profile.ssdecoder",
            "build/project.ssflp",
            "build/raw.sslog",
            "tests/fixtures/result.png",
            "docs/figure.png",
            "src/change.py",
            "build/unknown.xyz",
            "build/keep.json",
            "main.zip",
        )
    ]
    subprocess.run(["git", "-C", str(root), "add", "build/keep.json"], check=True)
    targets = WorkspaceClean_Plan(root)
    assert generated in targets and cache in targets
    assert generated.exists() and cache.exists()  # dry run never writes
    result, removed = WorkspaceClean_Apply(root, targets)
    assert result == WorkspaceCleanResult.APPLIED
    assert generated in removed and not generated.exists()
    assert not cache.parent.exists()
    assert all(path.exists() for path in protected)


def test_apply_rechecks_index_and_rejects_outside_target(tmp_path):
    root = _Repository_Create(tmp_path)
    path = _File_Write(root, "dist/keep.png")
    targets = WorkspaceClean_Plan(root)
    subprocess.run(["git", "-C", str(root), "add", "dist/keep.png"], check=True)
    outside = _File_Write(tmp_path, "outside.png")
    result, _ = WorkspaceClean_Apply(root, (*targets, outside))
    assert result == WorkspaceCleanResult.REFUSED
    assert path.exists() and outside.exists()


def test_symlink_escape_and_replaced_parent_are_refused(tmp_path):
    root = _Repository_Create(tmp_path)
    generated = _File_Write(root, "build/report.png")
    targets = WorkspaceClean_Plan(root)
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = _File_Write(outside, "report.png")
    generated.unlink()
    generated.parent.rmdir()
    try:
        generated.parent.symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        if os.name != "nt":
            pytest.skip(f"symlink permission unavailable: {exc}")
        # Directory junctions exercise Windows reparse-point escape without admin rights.
        import _winapi

        _winapi.CreateJunction(str(outside), str(generated.parent))
    assert not WorkspaceClean_Plan(root)
    result, removed = WorkspaceClean_Apply(root, targets)
    assert result == WorkspaceCleanResult.REFUSED and not removed
    assert sentinel.exists()


def test_gitignore_does_not_hide_sources_or_fixtures(tmp_path):
    root = _Repository_Create(tmp_path)
    source_root = Path(__file__).resolve().parents[1]
    (root / ".gitignore").write_bytes((source_root / ".gitignore").read_bytes())
    for path in (
        ".codex_pytest_new/a.json",
        ".acceptance/export.png",
        "build/a.png",
        "src/pkg/__pycache__/a.pyc",
    ):
        assert subprocess.run(["git", "-C", str(root), "check-ignore", "-q", path]).returncode == 0
    for path in (
        "tests/fixtures/golden.png",
        "docs/plot.png",
        "src/change.py",
        "flight.BIN",
        "profile.ssdecoder",
        "project.ssflp",
        "unknown.json",
    ):
        assert subprocess.run(["git", "-C", str(root), "check-ignore", "-q", path]).returncode == 1


def test_explicit_retirement_removes_tracked_test_outputs_only(tmp_path):
    from tools.clean_workspace import WorkspaceClean_RetireTests
    root = _Repository_Create(tmp_path)
    generated = _File_Write(root, ".codex_pytest_old/test_case/SYNTHETIC_run.BIN")
    source = _File_Write(root, "tests/fixtures/reference.BIN")
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    assert generated not in WorkspaceClean_Plan(root)
    result, count = WorkspaceClean_RetireTests(root, (".codex_pytest_old",))
    assert result == WorkspaceCleanResult.APPLIED and count == 3
    assert source.exists() and not generated.exists()
    result, _ = WorkspaceClean_RetireTests(root, ("tests",))
    assert result == WorkspaceCleanResult.REFUSED and source.exists()


def test_retirement_refuses_junction_before_removing_any_run_file(tmp_path):
    from tools.clean_workspace import WorkspaceClean_RetireTests
    root = _Repository_Create(tmp_path)
    generated = _File_Write(root, ".codex_pytest_old/test_case/generated.png")
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = _File_Write(outside, "actual.BIN")
    link = generated.parent / "linked"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        if os.name != "nt":
            pytest.skip("symlink not available")
        import _winapi
        _winapi.CreateJunction(str(outside), str(link))
    result, count = WorkspaceClean_RetireTests(root, (".codex_pytest_old",))
    assert result == WorkspaceCleanResult.REFUSED and count == 0
    assert generated.exists() and sentinel.exists()
