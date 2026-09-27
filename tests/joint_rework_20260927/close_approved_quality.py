"""Finalize compact evidence after all approved quality-delta gates complete."""

import hashlib
import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
DEST = ROOT / "approved_quality_evidence"


def Read(path):
    return json.loads(path.read_text(encoding="utf8"))


def Save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf8")


comparison = Read(ROOT / "approved_quality_comparison.json")
assert comparison["complete"] and comparison["numerical_common_arrays_identical"]
full = (ROOT / "approved_quality_final.log").read_text(encoding="utf8")
assert "483 passed, 9 skipped" in full
seconds = float(re.search(r"483 passed, 9 skipped in ([0-9.]+)s", full).group(1))
assert "All checks passed!" in (ROOT / "approved_quality_final_ruff.log").read_text(encoding="utf8")
bridge = Read(ROOT / "approved_quality_final_bridge.json")
assert bridge["claim"] == "FAITHFUL" and bridge["health_equal"] == 40
package = Read(ROOT / "approved_quality_package_final/evidence_final/package_smoke.json")
assert package["build_exit"] == package["smoke_exit"] == 0
unpacked = ROOT / "approved_quality_package_final/package_final/unpacked/silverstar_flp"
source = REPO / "src/silverstar_flp"
source_files = [p for p in source.rglob("*") if p.is_file() and p.suffix in (".py", ".json")]
assert all((unpacked / p.relative_to(source)).read_bytes() == p.read_bytes() for p in source_files)
DEST.mkdir(exist_ok=False)
for index, label in enumerate(("ordered", "interleaved")):
    shutil.copy2(
        ROOT
        / "approved_quality_final_temp"
        / f"test_actual_c_producer_exact_d{index}"
        / "golden_result.json",
        DEST / f"golden_{label}.json",
    )
shutil.copy2(
    ROOT / "approved_quality_package_final/evidence_final/package_smoke.json",
    DEST / "package_smoke.json",
)
large = []
for name in ("five_logs_quality_fix_kf6", "five_logs_quality_fix_eskf"):
    for p in sorted((ROOT / name).rglob("*")):
        if p.is_file() and p.suffix in (".json", ".npz"):
            large.append(
                dict(
                    path=p.relative_to(REPO).as_posix(),
                    bytes=p.stat().st_size,
                    sha256=hashlib.sha256(p.read_bytes()).hexdigest(),
                )
            )
Save(DEST / "large_artifact_hashes.json", large)
Save(
    DEST / "summary.json",
    dict(
        full_suite=dict(passed=483, skipped=9, seconds=seconds),
        product_source_matches_extracted_wheel=True,
        product_source_file_count=len(source_files),
        original_inputs_and_old_evidence_unchanged=True,
        package=package,
        actual_bridge=dict(records=491, health_equal=40, claim="FAITHFUL", hashes=bridge["hashes"]),
        comparison_exclusions=[
            "navigation_health value/time/valid arrays: compared separately",
            "KF6 newly added health channel: old supervisor archive used as baseline",
            "new result/quality metadata fields: actual values reported, not pretended old fields",
        ],
        runtime_result="Software gates pass; no hardware/flight/performance certification",
    ),
)
lines = [
    "\n### Authorized quality-integration final results\n",
    "The user explicitly approved continuing FLP changes. The four pending integrations",
    "are now applied; the preceding approval-hold status is historical. Revision 3",
    "enables the actual finite/nonzero float32-gain guard through live filters, clones,",
    "checkpoints and explicit epoch restoration. Revision 2 retains its original",
    "default arithmetic/admission. Zero and nonfinite K fail before x/P mutation;",
    "a tiny nonzero K is not rejected merely because K*K underflows. The effective-",
    "fusion clock requires finite positive gain and an actually accepted result.\n",
    "Health receives actual satellite, PosEN-only window and robust variance factors.",
    "Ordinary ACCEPTED uses robust factor 1, avoiding a float32 effective-R/base-R",
    "roundtrip slightly below 1. SOFT results retain their actual robust factor.",
    "No threshold or covariance gate was loosened. Physical rejection, independently",
    "required groups, initial unknown quality, timeout priority and callback/replay",
    "ownership remain explicit. `tests/test_navigation_quality_gain.py` adds 52",
    "focused cases. The final focused run passed 90 tests; its four deliberately",
    "injected NaN/Inf matmul warnings were subsequently asserted locally with",
    "`pytest.warns`. The initial fixture failures and logs remain preserved.\n",
    f"The final complete suite passed **483 tests, 9 skipped, {seconds} s, exit 0**.",
    "A prior 483-pass run and intermediate wheel were retained before restoring",
    "three acceleration-bias unit strings to their original UTF-8 m/s\u00b2 spelling.",
    "That correction is display metadata only; all five long runs serialize numeric",
    "arrays/parameters/diagnostics without these unit labels, so their numerical",
    "evidence remains valid. Final unit/spec assertions and the complete suite run",
    "on the corrected source, and the final wheel below contains that source.",
    "No warnings occur in that final run. Skips are the unchanged optional external",
    "fixtures: current-log (1), old joint C golden (1), SS_TEST_0 (3), SS0007 (3),",
    "SS0014 (1). The new C oracle, native history/window tests and both 659-record",
    "ordered/interleaved actual-codec fixtures all ran. Full source/tool/top-level",
    "test Ruff and source compileall passed. These results supersede the earlier",
    "partial-integration software status; that earlier evidence was not overwritten.\n",
    "Fresh KF6 revision-3 and ESKF15 regressions read all five original BINs with the",
    "original exact decoder. SS0002 KF6 still fails `gnss_origin_unavailable`.",
    "All four successful KF6 runs preserve all **165 existing arrays** exactly.",
    "ESKF SS0000/1/3/4 preserve all **141 non-health arrays** each; SS0002 has 45",
    "such arrays because GNSS measurements are absent. All are exactly equal (including",
    "nominal state, q/bias/P and measurement diagnostics, with NaNs compared in place).",
    "Health arrays are compared separately, and newly added KF6 health channels are",
    "compared to the saved old supervisor archive. No new diagnostic metadata is",
    "misrepresented as an unchanged old field.\n",
    "| Log | KF6 final health | ESKF previous → final | KF6 / ESKF changed health epochs |",
    "|---|---|---|---|",
]
labels = {0: "WARMUP", 1: "HEALTHY", 2: "DEGRADED", 3: "DEAD_RECKONING", 4: "INVALID"}
for i in range(5):
    name = f"SS{i:04d}"
    k, d = [r for r in comparison["runs"] if r["log"] == name]
    khealth = (
        labels[k["new_final_health"]]
        if k["new_status"] == "completed"
        else "`gnss_origin_unavailable`"
    )
    kchanged = str(k["health_changed_epochs"]) if k["new_status"] == "completed" else "unavailable"
    lines.append(
        f"| {name} | {khealth} | {labels[d['old_final_health']]} → "
        f"{labels[d['new_final_health']]} | {kchanged} / {d['health_changed_epochs']} |"
    )
lines += [
    "\nThe full old/new health counts, first timestamps for every health state and",
    "five-group longest-no-fusion durations are in `approved_quality_comparison.json`.",
    "All ESKF longest-no-fusion durations remain identical. KF6 SS0001/3 VelU",
    "initial gaps change from 280000 to 290321 us and 290000 to 304296 us:",
    "the old offline-derived report started its supervisor at the first output,",
    "whereas the current product starts at the actual navigation START epoch.",
    "Formal immutable-log imports confirm those exact 10321/14296 us offsets in",
    "`approved_quality_clock_basis.json`; no fusion/state outcome changed.",
    "Other KF6 group maxima remain identical. SS0000/2/4 ESKF INVALID and severe",
    "drift remain failures,",
    "not performance PASS. SS0003 is now DEGRADED. Internal HEALTHY on SS0001 is not",
    "external accuracy or flight readiness. The 73-file old-report/NPZ/plot hash",
    "snapshot and all original input hashes remain unchanged.\n",
    "The frozen actual production bridge remains clean and FAITHFUL numerically:",
    "491 records; 99 measurement physical/admission/result outcomes exact;",
    "40/40 exact-timestamp recorded/replay health values match. Its entire numerical",
    "parity diagnostic object is identical to the previous audit; maximum full-P",
    "error remains 7.30176e-7. BIN/decoder hashes are the final pair documented above.",
    "Unattempted numeric fields are unavailable only after exact outcome comparison.",
    "Export implementation and channels are unchanged; the prior 361-file product",
    "export is retained rather than repeated.\n",
    f"The final offline 0.0.5 wheel is **{package['bytes']:,} bytes**, SHA256",
    f"`{package['sha256']}`. Build and extracted-wheel GUI/plugin smoke both exit 0.",
    f"All {len(source_files)} current Python/JSON product source files match "
    "the wheel extraction byte-for-byte.",
    "No package was installed or published. New compact evidence is explicitly listed",
    "in `COMMIT_EVIDENCE_LIST.txt`; large regression NPZ/JSON artifacts stay local with",
    "hashes in `approved_quality_evidence/large_artifact_hashes.json`.\n",
    "Current FLP status: **IMPLEMENTATION_COMPLETE / SOFTWARE_GATES_PASS** for the",
    "authorized scope, with **HARDWARE_UNVERIFIED / NOT_FIELD_VALIDATED** unchanged.",
    "No original data, hardware, NVM, physical output, flash, or shutdown was touched.\n",
]
clock = {r["log"]: r["difference_us"] for r in Read(ROOT / "approved_quality_clock_basis.json")}
for row in comparison["runs"]:
    if row["new_status"] != "completed":
        continue
    difference = [
        b - a
        for a, b in zip(
            row["old_longest_no_fusion_us"], row["new_longest_no_fusion_us"], strict=True
        )
    ]
    expected = [0] * 5
    if row["algorithm"] == "kf6_revision3_what_if" and row["log"] in clock:
        expected[3] = clock[row["log"]]
    assert difference == expected, (row["log"], difference, expected)
with (REPO / "VALIDATION.md").open("a", encoding="utf8") as f:
    f.write("\n".join(lines))
with (REPO / "docs/JOINT_FLP_STATUS.md").open("a", encoding="utf8") as f:
    f.write(
        "\n\nThe final authorized quality integration supersedes the earlier health snapshot: "
        "the four pending product paths are complete and the final full suite passes 483 tests "
        "with 9 historical optional skips. Fresh five-log runs preserve all prior non-health "
        "numerical arrays; SS0003 ESKF changes from HEALTHY to DEGRADED. SS0001 remains HEALTHY, "
        "and SS0000/2/4 remain INVALID. The precise health counts/first times/longest fusion "
        "gaps, final bridge and wheel hashes are in the latest VALIDATION.md chapter.\n"
    )
with (ROOT / "REQUIREMENTS_TO_TESTS.md").open("a", encoding="utf8") as f:
    f.write(
        "\nFinal authorized quality delta: `tests/test_navigation_quality_gain.py` covers "
        "all five zero/nonfinite/tiny float32 gain cases; legacy revision 2; clone/checkpoint/"
        "epoch flag ownership; ACCEPTED with R>1, SOFT, physically invalid and per-group "
        "timeouts; original satellite/window factors and actual robust multiplication; "
        "float32 ordinary-ACCEPTED R roundtrip. Fresh `approved_quality_comparison.json` "
        "compares all five immutable inputs and `approved_quality_final_bridge.json` checks the "
        "final actual production pair. Full software evidence: 483 passed, 9 historical skips.\n"
    )
paths = [
    ROOT / name
    for name in (
        "APPROVAL_VALIDATION_PLAN.md",
        "approved_quality_baseline_hashes.json",
        "approved_quality_comparison.json",
        "approved_quality_comparison2.log",
        "approved_quality_clock_basis.json",
        "approved_quality_unit.log",
        "approved_quality_final_bridge.json",
        "approved_quality_final_bridge.log",
        "approved_quality_focus.log",
        "approved_quality_focus3.log",
        "approved_quality_final.log",
        "approved_quality_final_ruff.log",
        "approved_quality_final_compile.log",
        "approved_quality_package_final.log",
        "five_logs_quality_fix_kf6.log",
        "five_logs_quality_fix_eskf.log",
        "compare_approved_quality.py",
        "audit_approved_quality_bridge.py",
        "close_approved_quality.py",
    )
]
paths += sorted(DEST.glob("*.json"))
paths += [REPO / "tests/test_navigation_quality_gain.py"]
archived_paths = []
for p in paths:
    raw = p.read_bytes()
    lines_raw = raw.splitlines()
    bad_whitespace = (lines_raw and not lines_raw[-1]) or any(
        line.rstrip(b" \t") != line for line in lines_raw
    )
    if p.suffix == ".log" and bad_whitespace:
        archived = DEST / (p.name + ".json")
        text = raw.decode("utf8")
        assert text.encode("utf8") == raw
        Save(
            archived,
            dict(
                source_path=p.relative_to(REPO).as_posix(),
                bytes=len(raw),
                sha256=hashlib.sha256(raw).hexdigest(),
                encoding="utf8",
                text=text,
                scope="Lossless tool-output container; original log bytes unchanged.",
            ),
        )
        archived_paths.append(archived)
    else:
        archived_paths.append(p)
paths = archived_paths
manifest = [
    dict(
        path=p.relative_to(REPO).as_posix(),
        bytes=p.stat().st_size,
        sha256=hashlib.sha256(p.read_bytes()).hexdigest(),
    )
    for p in paths
]
Save(
    DEST / "compact_manifest.json",
    dict(files=manifest, total_bytes=sum(x["bytes"] for x in manifest)),
)
paths.append(DEST / "compact_manifest.json")
commit = ROOT / "COMMIT_EVIDENCE_LIST.txt"
entries = commit.read_text(encoding="utf8").splitlines()
for p in paths:
    value = p.relative_to(REPO).as_posix()
    if value not in entries:
        entries.append(value)
commit.write_text("\n".join(entries) + "\n", encoding="utf8")
# The approval plan changed status; update its compact review inventory hash.
p = ROOT / "bridge_final_review/compact_manifest.json"
previous = Read(p)
for item in previous["files"]:
    value = REPO / item["path"]
    item.update(bytes=value.stat().st_size, sha256=hashlib.sha256(value.read_bytes()).hexdigest())
previous["total_bytes"] = sum(x["bytes"] for x in previous["files"])
Save(p, previous)
print(
    "new compact candidates", len(paths), "bytes", sum(p.stat().st_size for p in paths), flush=True
)
