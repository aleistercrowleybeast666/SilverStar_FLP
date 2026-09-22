# Field log replay and long-duration analysis

The FCCG generated decoder 1.2 remains the only production record/parameter authority.
Open through LogOpenCoordinator with the matching Descriptor; no historical SS0000–SS0003
special case or fixed-parser fallback is added. Retired SAMPLE, RAW_SENSOR, IMU_NATIVE and
HW_QUAT_NATIVE have no new production aliases. Raw arbitrary catalog channels remain immutable.

## Two independent checks

KF6 firmware-faithful replay consumes every recorded INERTIAL_INCREMENT and the actual
ESTIMATOR_STEP/GNSS_MEASUREMENT/BARO_MEASUREMENT operation identities. Within an epoch, merge
receive/predict/position/velocity/barometer operations by operation_sequence, never by guessed
arrival-to-next-increment timing. Source sequence plus interval end identifies a prediction.
Separate GNSS position/velocity measurement times remain separate. An explicit zero sequence
means the operation did not execute; duplicates/missing identities are rejected or diagnosed.

The bounded common fixed-lag engine restores historical x/P and recovery state, inserts by
measurement time, and replays subsequent IMU/GNSS/barometer events to present. GNSS receive
evidence is captured once. Capacity/history/numeric/work-limit failures remain failures; they do
not become current-state updates. Epoch changes require explicit initial ESTIMATOR x/q plus
adjacent full P; arbitrary mid-epoch snapshots cannot reconstruct missing internal state.

Mechanization verification independently rebuilds corrected IMU grouping/coning/sculling and
compares every recorded interval's delta theta/velocity, dt, endpoints and source identity. It
reports the first divergence and never applies calibration again. Pure INS remains an independent
offline navigation plugin. No KF6 Pure INS sidecar is required for q/p/v display.

## Existing Time Synchronization vs Fixed-Lag Replay

FCCG time synchronization resolves native/receive clocks to estimator measurement time upstream.
FLP consumes that recorded result and does not implement another clock offset/wrap/iTOW mapping.
Unchanged delay parameters preserve the recorded resolved times. A trusted native timestamp is
used directly; an untrusted JY901B sample uses receive minus configured delay, once. Zero delay
retains the recorded present-time fast path. Timestamp correction alone is not latency replay.

Cross-C numerical tests cover normal, independent GNSS/barometer delays and kilometre-drift
controlled group re-anchor. Fidelity remains APPROXIMATE because those tests do not establish
every firmware boundary or actual flight acceptance. Exact results and hashes belong in VALIDATION.md.

## Diagnosis

State Estimation contains GNSS, Landing and Mechanization tabs. GNSS lists Pos EN/Pos U/Vel EN/
Vel U validity, quality reason, update result, innovation/NIS/R, outage, consistency, inflation
and re-anchor. Communication/liveness, receiver quality and estimator NIS rejection remain
distinct. Display trajectories break at re-anchor boundaries and actual data gaps.

Landing displays recorded candidate/reset/complete transitions and time metrics. Explicit
recompute runs in the existing worker from corrected IMU, barometer observations, recorded
mission thresholds and deploy. It is APPROXIMATE: FlightTask evaluation ticks are not logged.
Missing configuration, inputs or ambiguous physical source is reported, never filled with defaults.

## Analysis Source and time range

Only Replay changes the global Analysis Source. Flight, state estimation, trajectories and exports
resolve the same selected source, with no automatic Pure INS/KF6 overlay. Recorded labels identify
the actual navigation algorithm; explicit comparisons remain separate. Recorded datasets never mutate.

TimeRangeModel/Controller owns start/end/preset/custom duration. The shared bar supplies two
handles, 5/10/30/60/120 s/Full/Custom presets, Start, End and Duration editors. Missions <=30 s
open Full; longer missions open the first 30 s. Duration changes preserve start, shifting left at
mission end. Signals are blocked during synchronization. .ssflp ui_state saves the range and
source identity; a saved normal replay/What-if source is recomputed from its saved configuration
on reopen, retaining its run identity. Raw data and CSV remain complete.

Time plots and Data Explorer use a display-only min/max envelope, preserving spikes and gaps.
The shared range filters navigation diagnostics and plot views without changing replay or statistics.

## Exports

Time PNGs default to consecutive 30 s pages, including a shorter final page. Presets are
5/10/30/60/120/Custom/Current View/Full. Category directories collect related plots, with
millisecond start/end in filenames. Whole-mission 3D and summary outputs are not forcibly paged.

GIF defaults to the current selected range, with explicit Full available. The entire source range
uses one constant scale: <=30 s real-time; >30 s compressed to 30 s motion, never truncated.
30 fps is followed by 30 visually identical final hold frames (1 s). No event slows playback or
warps frame timing. The dialog and GIF metadata JSON show source range/duration, playback,
speed, fps and frame counts. Preparation, PNG and GIF frame/encoding work shares cooperative
worker cancellation and progress. GIF codec centisecond delays approximate 30 fps by alternating
frame delays while preserving total playback duration.

See tests/test_joint_c_golden.py for explicit generated-project/C-log integration inputs;
tests/test_fixed_lag_contract.py, test_landing_time_window.py, test_joint_ranges.py and
test_joint_gui_state.py cover negative replay controls, time windows, real PNG pages and UI state.
