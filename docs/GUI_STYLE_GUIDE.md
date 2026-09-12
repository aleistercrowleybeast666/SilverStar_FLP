# SilverStar_FLP GUI style guide

The normative cross-project GUI specification is
[`CXYL_Python_GUI_STYLE_GUIDE.md`](CXYL_Python_GUI_STYLE_GUIDE.md). Read that document before
changing layout, navigation, controls, plots, Replay, 3D views, themes, or i18n. This file is the
short project entry point and does not duplicate the full CXYL guide.

SilverStar_FLP 0.0.2 fixes these project invariants:

- OS title is always `SilverStar_FLP`; the loaded filename appears only in status/details. On
  supported Windows versions, the native caption uses the current theme's brand blue.
- The header shows a localized descriptive name, `v0.0.2`, localized developer credit, and a
  compact current-project name whose tooltip contains the full absolute `.ssflp` path.
  Language/theme fields and popups are deep blue with white text and accent-blue hover rows.
- The File menu is New Project, Open Project, Save Project, Save Project As, Import Log / Decoder,
  Export, and Exit, with separators between the three groups. There is no duplicate toolbar.
  Import and export remain modal option dialogs.
- Export defaults to `<project-directory>/Result` for a saved/open project; without one, use
  `<source-log-directory>/<source-log-stem>_Data`. The destination remains editable. After an
  export completes, the dialog exposes the generated localized export manifest directly. Failed
  items are listed by localized name with toggleable exception details; any failure also triggers
  a best-effort standard-I/O `Export_Failures_ZH|EN.txt`.
- Full P exports as one localized `<Algorithm>_Full_P_Keyframes_ZH|EN.txt`, driven by Algorithm
  Plugin metadata. It contains START, PARACHUTE_DEPLOY, and LANDING (or analysis-end fallback),
  using only the last valid non-future P without interpolation; START falls back to declared
  INITIAL_STATE P0 when it precedes the first full-P sample. Keep upper-triangle CSV; do not
  generate its generic multi-curve PNG.
- Batch Export writes all selected channels to CSV but creates PNGs only for standard engineering
  plots. Estimator state/measurement plots come from `EstimatorVisualizationSpec`; configured
  groups without valid updates receive explanatory plots, while explicitly unconfigured groups
  are recorded as skipped.
- Header, sidebar, menu, and unselected tabs are deep blue. Selected navigation uses the
  same accent blue as Header combo hover with white text. All tabs retain their global style.
- A combo popup opens downward, shows at most ten rows, and scrolls internally beyond ten.
- Every page containing 2D plots provides one Reset Charts action for all plots on that page.
- Replay has no input selector and always requests `corrected_imu`. Replay owns the only editable
  Analysis Data Source selector; Recorded is first, and only complete successful runs are listed.
  Flight and State Estimation display the source read-only.
- Recorded Pure INS and Recorded KF_6 remain distinct visible layers. A plot refresh never reuses a
  color; after the base sixteen colors, generate additional HSV colors.
- Attitude uses the shared GSHC-proportion and GSHC face-color rocket mesh plus the existing WXYZ
  Body-to-ENU quaternion helper. Trajectory coordinates are relative to mission START. Pre-deploy
  path/current are red, post-deploy path/current are blue, and Deploy is one small opaque orange
  world-space mesh. Landing is the same small opaque mesh geometry in purple. Both sizes follow the
  cached mission-trajectory extent; do not add outlines or floating event text. At Landing, hide
  Current and show Landing.
- Normal Replay, Flight plots, the 3D slider, trajectory PNG, and replay GIF use START-to-Landing as
  their mission horizon. Without a valid Landing event, use the active source's valid end. Raw logs,
  Data Explorer channels, raw CSV, and explicitly selected generic channel plots remain complete
  and immutable; samples before START use negative mission time in generic channel plots.
- Cache mission-relative `TrajectoryBounds` separately for Recorded Pure INS, Recorded KF_6, and
  every Recomputed/What-if result. Initial/Reset View fitting uses cached center and bounding radius
  with the OpenGL view's FOV and aspect ratio plus margin. Playback updates geometry only; it must
  not rescan bounds or reset orbit, pan, or zoom.
- Every user-visible Replay fidelity, warning, parameter, provenance, result, and source label must
  exist in both `zh_CN.json` and `en_US.json`; keep raw diagnostic IDs in tooltips.


- Semantic columns, record quality labels, and shared event drawing geometry follow
  [Display_DataQuality.md](Display_DataQuality.md). The existing diagnostics inner tab contains
  a per-gap table. Flight separately reports position timestamp gaps and the drawing threshold.
  Event-marker interpolation is permitted only across valid normal-cadence samples; the nearest
  scheduling fallback applies only outside channel coverage, never inside a data hole.

## Shell menus and plugin visibility

The header order is product, version, credit, current project, stretch, language, theme. Top-level menus are File, Plugins, Help. Plugins contains Manage, Install, Refresh; Help contains About. Plugin Manager is registry-driven and uses shared theme/i18n.


## Shared compact dialogs

About follows the FCCG information-dialog layout: information icon on the left, localized
product/version/description on the right, and one bottom-right OK button. New Project uses
name and output-directory rows before exact-pair import; cancellation creates no project file.
Plugin Manager uses a heading, descriptive notice, install/refresh action row and ID-first table.
The Install menu opens this manager. FLP retains its trusted-container installation rules;
FCCG declarative firmware component installation/removal is not an FLP runtime capability.
All three dialogs follow the active Light/Dark theme and interface language.
