# Validation

## 2026-09-16 — GNSS NIS semantics and sparse PRE-FLIGHT closeout

Clean initial source worktree at `f4b10f8`; user attachment explicitly authorized independent
FLP changes. No reset, checkout, commit or push. Version 0.0.2, .ssdecoder/project-semantics
1.2, SSLOG 0.0 and existing project formats remain unchanged.

### Root cause, fix and scope

KF6's recorded/recomputed position and velocity NIS are max(horizontal EN 2D, vertical U 1D).
Visualization metadata incorrectly named nis_3d_soft/hard as the thresholds for these aggregates.
`last_group_nis` exists inside the numerical filter, but the current exposed/recorded semantic
channels provide the aggregates; this patch does not invent group channels or extend log fields.

`NisThresholdSpec` plus optional MeasurementGroupSpec description/reference metadata supply the
shared GUI/export renderer. GNSS position/velocity now show:

| Reference | Default actual value |
| --- | ---: |
| U / 1D soft | 6.635 |
| U / 1D hard | 10.828 |
| EN / 2D soft | 9.210 |
| EN / 2D hard | 13.816 |

The title explains `max(EN 2D, U 1D)` and explicitly says the lines are group references,
not a unified aggregate pass/fail gate. Values use the source's actual parameter mapping;
float32 representation is preserved. Barometer keeps its existing pair of 1D thresholds.
English/Chinese labels and PNG titles use the same metadata. Other algorithms keep the
existing two-threshold fallback; fake future-estimator tests pass without page branches.
The 3D parameter declarations are retained because this is a presentation correction,
not a change to filter mathematics, parameters or historical data.

The parser/replay already accepts sparse preflight correctly. No parser, sequence-gap,
timestamp, required-stream, comparison-sampling or numerical code was changed or weakened.

### Files and regression coverage

- `src/silverstar_flp/plugins/api/algorithm.py`: generic NIS reference metadata and fallback.
- `src/silverstar_flp/plugins/algorithms/kf6/plugin.py`: visualization declarations only;
  position/velocity no longer reference nis_3d_* gates.
- `src/silverstar_flp/ui/pages/state_estimation.py`, `src/silverstar_flp/export/service.py`:
  metadata-driven reference lines and explanatory title for both surfaces.
- `src/silverstar_flp/i18n/en_US.json`, `zh_CN.json`: four reference names and aggregate meaning.
- `tests/test_estimator_visualization.py`, `tests/test_flight_state_pages.py`: four GNSS
  references, correct actual values, 1D barometer, both languages, generic-renderer regression;
  the GNSS plot contains one data curve plus four references instead of the old three curves.
- `tests/synthetic_parameter_navigation.py`: optional sparse preflight/flight length and missing
  IMU fixture switches; its original default fixture and frozen numerical outputs remain intact.
- `tests/test_sparse_preflight.py`: exact matching synthetic decoder/log, 120 s sparse preflight,
  20 s corrected IMU plus selected Baro inputs; CRC/header/record sequence clean, Data Quality
  CLEAN, KF6/Pure INS replay available, all four pages render, CSV/PNG/export succeeds.
  A separate exact package with missing mission IMU remains unavailable/rejected despite
  continuous SSLOG record sequences. The fixture selects IMU/Baro; it is not a GNSS hardware test.
- `docs/GUI_STYLE_GUIDE.md`, this report: interpretation and acceptance boundary.

### Verification

All output, TEMP/TMP and MPLCONFIGDIR are local to `tests/.pytest_cache/nis_0916/`;
QT_QPA_PLATFORM=offscreen, PYTHONDONTWRITEBYTECODE=1.

```powershell
.venv/Scripts/python.exe -m pytest tests/test_estimator_visualization.py tests/test_sparse_preflight.py -q --basetemp=tests/.pytest_cache/nis_0916/run4 -o cache_dir=tests/.pytest_cache/nis_0916/cache
.venv/Scripts/python.exe -m pytest -q --basetemp=tests/.pytest_cache/nis_0916/full2 -o cache_dir=tests/.pytest_cache/nis_0916/cache
.venv/Scripts/python.exe -m ruff check src/silverstar_flp/plugins/api/algorithm.py src/silverstar_flp/plugins/algorithms/kf6/plugin.py src/silverstar_flp/ui/pages/state_estimation.py src/silverstar_flp/export/service.py tests/test_sparse_preflight.py tests/test_estimator_visualization.py tests/synthetic_parameter_navigation.py --no-cache
```

Focused **9 passed**. Full **257 passed, 8 skipped in 74.54 s**; ruff passes and
`git diff --check` passes. Full coverage includes replay, timestamp semantics, comparison
sampling, touch, state GUI, export and the unchanged frozen `legacy_dynamic_outputs.npz`
comparison for every default algorithm result channel. No golden file was regenerated.
All KF6 plugin callable implementations match HEAD structurally (AST comparison).

Eight skips require unavailable explicitly named real logs: current SS0000, SS0007 (3),
SS0014 and SS_TEST_0 (3). These are not synthetic acceptance passes or hardware claims.

Artifacts: `tests/.pytest_cache/nis_0916/full2.log`; sparse exact .BIN/.ssdecoder pair, four
page screenshots and exported files under
`tests/.pytest_cache/nis_0916/full2/test_sparse_120_seconds_import0/`.
English GNSS reference PNGs under
`tests/.pytest_cache/nis_0916/full2/test_configured_without_valid_0/configured_no_updates_export/Plots_EN/`
were visually inspected: title, reference legends and lines fit without clipping. This fixture
correctly leaves the data plot empty when no valid GNSS updates exist.

The unavailable real logs and hardware acceptance remain the only unverified data sources.
No GNSS quality/reacquisition algorithm, covariance inflation, deployment or sampling logic changed.

<!-- closeout-git-begin -->
### Final Git snapshot

Tracked diff (new files are listed separately by status):

```text
 VALIDATION.md                                      | 122 +++++++++++++++++++++
 docs/GUI_STYLE_GUIDE.md                            |  15 +++
 src/silverstar_flp/export/service.py               |  20 +---
 src/silverstar_flp/i18n/en_US.json                 |   7 +-
 src/silverstar_flp/i18n/zh_CN.json                 |   7 +-
 .../plugins/algorithms/kf6/plugin.py               |  19 +++-
 src/silverstar_flp/plugins/api/algorithm.py        |  23 ++++
 src/silverstar_flp/ui/pages/state_estimation.py    |  27 ++---
 tests/synthetic_parameter_navigation.py            |  53 +++++----
 tests/test_estimator_visualization.py              |  42 ++++++-
 tests/test_flight_state_pages.py                   |   2 +-
 11 files changed, 273 insertions(+), 64 deletions(-)
```

```text
 M VALIDATION.md
 M docs/GUI_STYLE_GUIDE.md
 M src/silverstar_flp/export/service.py
 M src/silverstar_flp/i18n/en_US.json
 M src/silverstar_flp/i18n/zh_CN.json
 M src/silverstar_flp/plugins/algorithms/kf6/plugin.py
 M src/silverstar_flp/plugins/api/algorithm.py
 M src/silverstar_flp/ui/pages/state_estimation.py
 M tests/synthetic_parameter_navigation.py
 M tests/test_estimator_visualization.py
 M tests/test_flight_state_pages.py
?? tests/test_sparse_preflight.py
```
<!-- closeout-git-end -->


## 2026-09-14 — GUI touch-scrolling closeout

Scope: GUI registration/helper, GUI tests and documentation only. Initial working tree was clean;
no reset, checkout, commit, push, version change or cross-repository dependency was introduced.

<!-- touch-git-snapshot -->
### Modified files and Git snapshot

- `VALIDATION.md`
- `docs/GUI_STYLE_GUIDE.md`
- `src/silverstar_flp/ui/main_window.py`
- `src/silverstar_flp/ui/pages/data_explorer.py`
- `src/silverstar_flp/ui/pages/export_settings.py`
- `src/silverstar_flp/ui/pages/overview.py`
- `src/silverstar_flp/ui/pages/replay.py`
- `src/silverstar_flp/ui/pages/state_estimation.py`
- `src/silverstar_flp/ui/plugin_manager.py`
- `src/silverstar_flp/ui/touch_scroll.py`
- `src/silverstar_flp/ui/widgets.py`
- `tests/test_touch_scroll.py`

`git diff --stat` (tracked files only; new files are listed above):

```text
 docs/GUI_STYLE_GUIDE.md                         | 16 ++++++++++++++++
 src/silverstar_flp/ui/main_window.py            |  2 ++
 src/silverstar_flp/ui/pages/data_explorer.py    |  6 ++++++
 src/silverstar_flp/ui/pages/export_settings.py  |  3 +++
 src/silverstar_flp/ui/pages/overview.py         |  5 +++++
 src/silverstar_flp/ui/pages/replay.py           |  4 ++++
 src/silverstar_flp/ui/pages/state_estimation.py |  2 ++
 src/silverstar_flp/ui/plugin_manager.py         |  2 ++
 src/silverstar_flp/ui/widgets.py                |  3 +++
 9 files changed, 43 insertions(+)
```

`git status --short`:

```text
 M docs/GUI_STYLE_GUIDE.md
 M src/silverstar_flp/ui/main_window.py
 M src/silverstar_flp/ui/pages/data_explorer.py
 M src/silverstar_flp/ui/pages/export_settings.py
 M src/silverstar_flp/ui/pages/overview.py
 M src/silverstar_flp/ui/pages/replay.py
 M src/silverstar_flp/ui/pages/state_estimation.py
 M src/silverstar_flp/ui/plugin_manager.py
 M src/silverstar_flp/ui/widgets.py
?? VALIDATION.md
?? src/silverstar_flp/ui/touch_scroll.py
?? tests/test_touch_scroll.py
```
<!-- /touch-git-snapshot -->

### Cause and repair

Ordinary scrolling widgets had no native touch-scroller registration. Added the local
`TouchScroll_Enable` allowlist helper and explicit constructor calls. Coverage: Overview page
and calibration/alignment/timeline tables; Replay form and stored-result/comparison tables;
Data Explorer channel list and channel/record/diagnostic/sequence-gap tables; State Estimation
update table; Export Settings item scroll and failure details; navigation and Plugin Manager
table; StandardComboBox popup views. Existing pixel/item scroll modes stay unchanged.

2D PlotWidget/QGraphicsView, GLViewWidget and the playback slider are not registered, and runtime
coverage tests confirm they have no registered page-scroll ancestor. Flight/State Estimation
charts keep their expandable plotting layout. No Dataset, decoder, semantic adapter, timestamps,
KF6/Pure INS replay, comparison sampling, chart values, export logic or project format changed.

### Executed checks

- `.venv/Scripts/python.exe -B -m pytest tests/test_gui_smoke.py tests/test_comparison_sampling_gui.py tests/test_replay_page.py -q --basetemp=tests/.pytest-work-touch-focused -o cache_dir=tests/.pytest-cache-touch`: **14 passed**.
- `.venv/Scripts/python.exe -B -m pytest tests/test_touch_scroll.py -q --basetemp=tests/.pytest-work-touch-new2 -o cache_dir=tests/.pytest-cache-touch`: **18 passed**.
- Full pytest via `pytest.main(['-q', '--basetemp=tests/.pytest_cache/touch-validation/full', '-o', 'cache_dir=tests/.pytest_cache/touch-validation/cache'])`: **254 passed, 8 skipped**, 58.86 s.
- `.venv/Scripts/python.exe -B -m ruff check src tests --no-cache`: **passed**.
- `git diff --check` and static scroll/graphics inventory: **passed**.

Full-run wrapper sets `QT_QPA_PLATFORM=offscreen`, `PYTHONDONTWRITEBYTECODE=1`, process-local TEMP,
TMP and MPLCONFIGDIR below `tests/.pytest_cache/touch-validation`; QSettings uses IniFormat and
that directory's settings subtree. The full log is `tests/.pytest_cache/touch-validation/full.log`.
New tests cover native viewport registration/type, exclusion of inputs/graphics/headers, retained
mouse row selection and scrollbar movement, actual synthesized finger swipes on page/list/table/text,
main-window coverage and Plugin Manager construction.

### Remaining validation limits

The eight existing opt-in real-log gates skipped because `SILVERSTAR_CURRENT_LOG_ROOT`,
`SILVERSTAR_SS0007_PATH`, `SILVERSTAR_SS0014_ROOT` and `SILVERSTAR_SS_TEST_0_ROOT` were not supplied.
No CF-33 physical touchscreen/stylus or hardware-driver acceptance is claimed. No known remaining
failure in the executed GUI, comparison, replay or export regression suite.

