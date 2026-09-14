# Validation

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

