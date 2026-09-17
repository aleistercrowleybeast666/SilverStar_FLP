# KF6 field analysis and project paths

FLP remains 0.0.2; `.ssflp` remains v3 with one log per project. Decoder/project semantics stay
1.2, parameter schema stays 1.0 and wire formats are unchanged. Exact validation snapshots live
only in [VALIDATION.md](../VALIDATION.md).

## Outage policy and compatible parameters

Four GNSS groups independently track valid sample timestamps. NIS rejection does not expire
availability. Only a true gap strictly exceeding `gnss_reacquire_outage_ms` (default 300 ms)
authorizes return confirmation. A normal fused return clears eligibility without inflation.
Otherwise five hard rejects plus three consistent intervals permit factor-2 selective DPD'
inflation, at five rejected-epoch intervals, up to eight attempts. Three fused returns exit.
Repeated losses reset prior recovery attempts. Zero/duplicate/rollback timestamps cannot authorize
inflation; malformed group values do not refresh that group's validity clock.

Keep `gnss_velocity_std` and add `gnss_velocity_vertical_scale` (default 1): only U's measurement
sigma is multiplied after `max(receiver_sigma * 1.25, configured_floor)`. R squares this final
sigma. P0, Q, gravity, attitude, six-state dimension, Barometer pU observation/cross-covariance
vU correction and the source-quality/START gates remain unchanged.

Old `.ssflp` parameter identities are accepted only when they exactly match the prior KF6 schema.
Only the two new fields use explicit compatibility defaults; old required parameters remain
required. Diagnostics list the compatibility defaults. Old GNSS logs using the changed recovery
policy are approximate reproductions. Recorded values remain immutable and separate from What-if.

## Offline experiments

From the repository (or installed environment with its tools), run:

```powershell
.venv/Scripts/python.exe tools/kf6_field_analysis.py `
  --pair "D:/logs/SS0005.BIN" "D:/logs/Flight.ssdecoder" `
  --pair "D:/logs/SS0006.BIN" "D:/logs/Flight.ssdecoder" `
  --output "D:/analysis/field-run-01"
```

The output must be a new directory. Inputs are opened as exact hash-matched pairs, never rewritten;
source SHA-256 is checked before/after. Each log gets its own analysis JSON and the comparison
JSON lists independently estimated shifts. This creates no multi-log `.ssflp` format or runtime
FCCG/GSHC dependency. Development/test output must stay below this repository's `tests/`.

The report runs the current policy, an explicitly labeled old rejection-gate comparator, and
independent sweeps of outage threshold 160/200/250/300/500 ms, GNSS pU floor 2.5/3/4/5/6 m,
Barometer floor 1.5/2/3/5 m and velocity U sigma scale 1/1.25/1.5/2. The analysis keeps INITIAL_STATE
and P0 fixed; it does not claim to reproduce pre-START origin collection with different noise.
R changes still require the exact native uncertainty/source match. Missing native records produce
an explicit unavailable result instead of an invented fixed R. Normal What-if retains its
initialization evidence gate.

Velocity latency uses -500…+500 ms in 20 ms increments, then 5 ms refinement around the best coarse
candidate. Positive shift delays the velocity signal. Velocity and receiver variance are resampled
on the original GNSS sample grid in a common interior window. Position/Barometer timing is fixed;
there is no extrapolation or interpolation across source gaps. This is approximate offline
analysis; no firmware timestamp subtraction is applied. The diagnostic ranking uses EN/U p95 NIS
normalized by the actual group hard threshold plus hard-reject fractions. A minimum score alone
is not evidence of physical accuracy or an approved timing compensation.

Reports include per-group accepted/soft/hard/invalid counts, NIS max/percentiles and inflation
counts, final position/velocity, covariance peaks, exact-timestamp Recorded residuals and Pure INS
comparison. Residuals against recorded KF6 are not ground-truth errors. Stationary velocity RMSE
is absent unless a verified interval is explicitly supplied with `--stationary-us START END`.
The programmatic summary accepts a reference velocity series; absent reference data yields null,
not a claimed accuracy. Without multiple qualified real logs, retain conservative flight defaults.

## Advanced Offline Diagnostics in Replay

Select KF6 in Replay, then open its Advanced Offline Diagnostics child tab. This does not add a
main navigation page. Firmware-faithful is the default; Analysis-only is an explicit transient
mode with a persistent banner and a separate last-result summary. Base parameters retain their
existing Recorded Configuration / What-if meaning.

- Inspect Measurement Weights runs through the existing worker and reports five groups:
  position EN/U, velocity EN/U, and Baro U. It shows configured/native sigma, receiver/U scales,
  recorded origin variance, firmware effective sigma, analysis effective sigma/R, and the actual
  rule. Dynamic values are min/median/max, not an invented fixed R. R is the input before NIS soft
  weighting; native statistics cover available canonical-source records, while effective R covers
  the replay schedule. Position uses m/m²; velocity uses m/s and m²/s². Missing native values stay N/A.
- Manual shift uses -500…+500 ms, step 5 ms. Negative moves GNSS velocity earlier; positive delays
  it. It changes actual replay input and receiver variance, not just a plot. Manual zero preserves
  the original schedule including edges. Scan zero intentionally uses the common interior window,
  so scan scores and a full unshifted run are not identical evaluation windows.
- Auto Scan uses the existing background worker, progress and cancel controls. It reports best
  shift, zero/best scores, improvement, a sampled 5%-of-minimum envelope and the score curve.
  This width is neither a confidence interval nor necessarily one contiguous minimum. Apply Best
  is the only operation that applies the estimate to the current analysis and runs it. Scanning
  alone does not change the controls. No fixed firmware compensation is authorized by a minimum.
- Baro effective sigma override directly uses R=sigma², bypassing both the native floor and origin
  addition. The input range is 1.5…100 m. The inspector retains the firmware-side R for comparison;
  source native variances and the production resolver are never overwritten.
- Disable GNSS pU actually skips only the vertical position update. It does not use a huge sigma;
  E/N position continues through its normal update. Gravity, P0, Q, NIS and policy defaults are
  unchanged. Analysis uses the recorded initial state; it is not a simulated pre-START solve.
- Restore Firmware-faithful resets every transient switch/value and the scan. Existing completed
  Analysis-only results retain their original labels; restoring controls does not relabel curves.

Diagnostic options live outside ReplayRequest's parameter schema and outside `.ssflp`/decoder.
A project save omits analysis-only stored configurations and only persists the normal parameter
draft/results. Recorded Configuration remains immutable. Export Diagnostic Result creates a new
JSON containing log/decoder identity, base parameters, transient overrides, R audit and optional
scan. Existing filenames are not overwritten. Normal replay exports also include diagnostic
metadata and explicit Analysis-only source labels. This adds no automatic tuning, firmware write,
OOSM, adaptive R, P0/Q tuning, or multi-log project format.

## Default Project Root and result directories

File → 默认工程根目录... / Default Project Root... stores UTF-8 JSON in the application's
AppLocalDataLocation as `path_preferences.json`, schema_version 1. It is independent of `.ssflp`,
registry settings and source data. Invalid/missing JSON or a missing root falls back safely;
selecting a preference does not create the selected root.

New Project defaults to `<root>/<name>/<name>.ssflp`. Renaming follows until the first manual
path edit or Browse selection. A custom selected directory is used directly, without appending
another name directory. New directory creation occurs only after accepting the destination;
cancelling exact-pair import leaves no project file.

Import defaults to folder search. Its initial folder follows the current/pending project;
without a project it uses the default root, then the last successful import directory, then
an existing fallback. Manual exact-pair selection is still available.

Export defaults to `<project-directory>/Result_<log-stem>` (beside the log without a project).
Case-insensitive BIN/SSLOG suffixes are removed; Chinese, spaces and parentheses are retained,
Windows-illegal filename characters are replaced. Existing directories yield `_2`, `_3`, …
for automatic defaults. Manual destinations remain selected. Export refuses a nonempty destination
and preserves existing results. No automatic cleanup or overwrite is performed.
