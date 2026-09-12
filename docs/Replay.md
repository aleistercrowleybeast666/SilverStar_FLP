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

GNSS is optional according to the KF_6 input contract. A receiver may be configured and online
while reporting no fix, no usable position/velocity, and no `GNSS_MEASUREMENT` Records. Replay
does not manufacture a 0/0 position, does not disable the whole algorithm for that condition, and
continues with available prediction/barometer inputs.

Every run is appended to `ReplayResultStore` with a unique `result_id`, algorithm, mode, input
source, parameter snapshot, fidelity, warnings, time coverage, channels, and diagnostics.
Recomputed and What-if runs from Pure INS and KF6 therefore coexist.

The Replay algorithm list is the desktop registry, not the firmware component list. Each row shows
independent tags for an installed offline plugin, firmware membership, and recorded output. A
future installed ESKF plugin therefore appears immediately and can run when its declared stable
inputs are present, even when the opened `.ssdecoder` says that ESKF was not onboard.

Replay exposes three configuration modes:

1. **Recorded configuration** requires firmware membership, available inputs, and every parameter
   required by that plugin to be present in the log. Defaults never complete a partial recording.
2. **Offline configuration** uses the plugin's explicit offline defaults and depends only on input
   availability, not on firmware membership or recorded output.
3. **What-if** starts from offline defaults and overlays the subset of parameters genuinely found
   in the log. User edits are then stored with the run as a distinct provenance snapshot.

Recorded algorithm output is a fourth, separate fact: it may be displayed as a comparison target,
but it neither proves that recorded configuration is complete nor becomes a replay input.

Replay remains a first-class analysis capability even when Recorded and Recomputed happen to be
close. It is the path for running new algorithms on old logs, comparing KF6/ESKF15/ESKF24,
parameter What-if studies, algorithm regression, diagnosing real-time task/timestamp/drop issues,
and comparing firmware algorithm versions. Availability is strict: missing required records or
channels produces `UNAVAILABLE` with explicit missing-input codes rather than a partial result.

What-if controls are generated from `ParameterSpec.group_key`. KF6 exposes Process Model, Initial
Covariance, Measurement Noise, and Consistency Gating groups, showing only the selected group's
editors. Modified values display a visible state. Reset restores the audited What-if baseline:
explicit offline defaults overlaid by the partial or complete values returned by
`recorded_parameters(dataset)`. Process-acceleration and measurement-R
tooltips distinguish process noise Q from IMU white noise and distinguish dynamic recorded sensor
uncertainty × R scale from a fixed sensor accuracy.

Pure INS and KF_6 remain `APPROXIMATE` for firmware `0.0.10`. Their audited host
implementation retains the `SILV0008` identity and emits explicit build/Golden warnings.
Exact package matching changes input provenance, not algorithm fidelity.

Corrected-IMU cadence is evaluated from recorded sample timestamps within the logged
SYSTEM_CONFIG bounds; stream-descriptor decimation is used when current SYSTEM_CONFIG no longer
contains the historical decimation array. A detected gap clears the coning/sculling history and
starts a new segment. No sample or trajectory point is interpolated across that input gap, and
the result remains `APPROXIMATE`. `EXACT` additionally requires an explicit matching Golden
validation reference and clean source integrity.

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

## Display-only event points

GUI and exported trajectories now share the cadence-guarded phase builder described in
[Display_DataQuality.md](Display_DataQuality.md). It can add an event point to drawing geometry
inside a normal position interval; replay inputs, quaternion propagation, timestamps, and result
TimeSeries are unchanged. Real channel gaps remain broken. Global sequence-gap segments and
missing IDs are record diagnostics, independent of the active position channel cadence.
