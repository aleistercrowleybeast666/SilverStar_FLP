# Changelog

## 0.0.2

- Added complete SSLOG0 profile 0 parser and all current record layouts.
- Added immutable multi-rate FlightDataset and parser integrity diagnostics.
- Added complete Pure INS replay from corrected IMU or recorded inertial increments.
- Added KF6 prediction, GNSS/barometer updates, P/NIS diagnostics, and What-if parameters.
- Added deploy/landing analysis, recorded/recomputed comparison, and automatic overview.
- Added five-page PySide6 GUI, fixed product title/version, dark-blue brand/side/tool bars,
  light-blue selected states, global tab styling, top-bar language/theme controls, modal
  import/export options, conventional scrolling combo boxes, larger 3D views, and Replay scrolling.
- Fixed GUI Replay input to corrected IMU while retaining recorded-increment support internally.
- Added a Replay-only Analysis Data Source selector with Recorded fallback and complete-result
  eligibility; Flight and State Estimation now show the source read-only.
- Kept Recorded Pure INS and Recorded KF_6 as distinct chart/export layers with non-repeating
  colors.
- Added the GSHC-style quaternion-rotated rocket mesh, mission-relative trajectory origin,
  point-only deploy/landing/current markers, reset/lock controls, and camera-preserving playback.
- Localized the Header display name and developer credit, added the `v` version prefix,
  brand-colored Windows caption, readable blue Header dropdowns, and accent-blue navigation.
- Reordered File/toolbar actions, added safe Project Save As, standardized the Chinese term
  `工程`, and added page-level reset controls for every 2D chart page.
- Synchronized the six rocket face colors with GSHC; segmented the trajectory/current point into
  red pre-deploy and blue post-deploy phases; and replaced the fixed pixel Deploy symbol with one
  orange, trajectory-extent-scaled world-space point in the GUI, PNG, and GIF outputs.
- Added estimator visualization metadata for state/measurement groups, generated the State
  Estimation page without KF6-specific channel IDs, and covered future ESKF-style state and
  magnetometer declarations with a test-only plugin.
- Grouped What-if parameters by engineering role, exposed parameter IDs and physical tooltips,
  added a modified indicator, and made Reset restore recorded SYSTEM_CONFIG/header values.
- Kept File-menu actions contiguous, including no separator between Save Project As and Open
  Project.
- Added reference-only projects and independent-language CSV/JSON/PNG/GIF export.
- Added CLI, synthetic integration tests, and PyInstaller preparation.
