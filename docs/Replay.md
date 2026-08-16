# Replay semantics

The GUI has one fixed replay input: **Corrected IMU**. It rebuilds subinterval increments,
coning/sculling compensation, software quaternion, ENU acceleration, velocity, and position from
START. There is no GUI input-source selector.

The algorithm API and CLI retain **Recorded Inertial Increment** for validation and advanced
workflows. It skips IMU preprocessing and re-runs mechanization from START. Neither path silently
falls back to the other when required data is absent.

KF6 consumes an independently propagated attitude/mechanization prediction plus logged GNSS and
barometer measurements, restored P0/Q/R/NIS configuration, and optional What-if overrides.
Recorded algorithm outputs are comparison targets, never replay inputs.

Every run is appended to `ReplayResultStore` with a unique `result_id`, algorithm, mode, input
source, parameter snapshot, fidelity, warnings, time coverage, channels, and diagnostics.
Recomputed and What-if runs from Pure INS and KF6 therefore coexist.

Replay remains a first-class analysis capability even when Recorded and Recomputed happen to be
close. It is the path for running new algorithms on old logs, comparing KF6/ESKF15/ESKF24,
parameter What-if studies, algorithm regression, diagnosing real-time task/timestamp/drop issues,
and comparing firmware algorithm versions. Availability is strict: missing required records or
channels produces `UNAVAILABLE` with explicit missing-input codes rather than a partial result.

What-if controls are generated from `ParameterSpec.group_key`. KF6 exposes Process Model, Initial
Covariance, Measurement Noise, and Consistency Gating groups, showing only the selected group's
editors. Modified values display a visible state. Reset calls the selected plugin's
`recorded_parameters(dataset)` mapping, restoring SYSTEM_CONFIG/header-derived values and neutral
R/P scale factors instead of Python schema defaults. Process-acceleration and measurement-R
tooltips distinguish process noise Q from IMU white noise and distinguish dynamic recorded sensor
uncertainty × R scale from a fixed sensor accuracy.

The Replay page owns the only editable **Analysis Data Source** selector:

1. Recorded is always the first item and remains selectable.
2. A replay result is listed only when fidelity is not UNAVAILABLE, no required input is missing,
   and attitude, velocity, and position outputs each contain valid samples.
3. Incomplete or failed runs remain visible in Stored Results for diagnosis but cannot become the
   global analysis source.

Flight and State Estimation display the active source read-only. Flight and export resolve it
through `ChannelResolver`. Recorded Pure INS and Recorded KF_6 navigation stay separate layers;
when a replay source is active, both recorded layers are dashed references. State Estimation uses
only compatible estimator diagnostics declared by that algorithm's visualization metadata and
never invents per-axis sequential updates. Data Explorer exposes every run under a unique
human-readable prefix. No source selection copies or overwrites the immutable recorded dataset.
