# Algorithm Plugin API

An `AlgorithmPlugin` declares stable identity/version metadata, required and optional records and
channels, a typed parameter schema, standard outputs, and diagnostic outputs. `availability()`
returns supported input sources, missing input codes, warnings, and `EXACT`, `APPROXIMATE`, or
`UNAVAILABLE`. `run()` receives a `ReplayRequest` and returns an immutable `AlgorithmResult`.

Standard output IDs such as `attitude.q_nb`, `navigation.velocity_enu`, and
`navigation.position_enu` let shared Navigation views work with future ESKF15/24 plugins. Plugin
specific channels such as `kf6.nis.position_horizontal` remain discoverable by Data Explorer and
diagnostic views without changing the common page.

Recorded, Recomputed, and What-if are provenance labels. Fidelity is separate: it describes input
and implementation completeness, never whether a curve merely looks close.

The desktop Replay page always constructs `ReplayRequest(input_source="corrected_imu")`. Plugins
must retain explicit availability checks and must not silently fall back. The internal API may
continue to accept `recorded_inertial_increment` for CLI, validation, and golden-vector work.

Each user-editable parameter supplies stable `label_key`, `group_key`, and `tooltip_key` values,
plus unit/range/step metadata. The GUI translates those keys, keeps the raw `parameter_id` in the
tooltip, and builds the What-if group selector without parameter-specific branches.
`recorded_parameters(dataset)` returns the values represented by that particular log. Reset uses
this mapping, not `ParameterSpec.default`; scale parameters that do not exist as firmware values
use their recorded neutral factor (`1.0`). Warnings remain stable raw codes in algorithm results
and are translated only at the GUI/export boundary.

## Estimator visualization metadata

An estimator plugin may set `AlgorithmMetadata.estimator_visualization` to an
`EstimatorVisualizationSpec`. Pure INS deliberately leaves it as `None`, because it has no
covariance, innovation, NIS, or measurement-update diagnostics. State Estimation considers only
plugins that provide this spec.

Each `StateGroupSpec` declares:

- stable `group_id` and translated `label_key`;
- component names and state-domain unit;
- a covariance-diagonal channel and the component indices owned by the group;
- an optional stable export `file_stem`.

The GUI creates the State Group selector from these entries. It plots only the selected group and
offers standard deviation (`sqrt(Pii)`, default) or variance (`Pii`) display. Adding ESKF position,
velocity, attitude-error, gyro-bias, or accelerometer-bias groups therefore does not require a GUI
change. Standard Export consumes the same entries and writes one engineering plot per group as
`sqrt(Pii)` in that group's physical unit; it never combines state groups with different units.

Each `MeasurementGroupSpec` declares:

- stable measurement-group ID, translated label, dimension, and component names;
- innovation, NIS, update-result, R-scale, and optional age/uncertainty/effective-R channels;
- vector-column indices and optional attempt-mask/dimension channels;
- optional soft/hard NIS threshold parameter IDs;
- the measurement-domain unit and optional stable export `file_stem`;
- generic participation evidence: SYSTEM_CONFIG field names/provider indices, measurement record
  names, and an optional validity channel.

Innovation, NIS, Measurements, the generic Update Event Table, and Standard Export all consume
this metadata. A measurement group that is configured but has no valid updates still gets
Innovation, NIS, and `sqrt(R)` standard plots with an explanatory message. A group for which
configuration evidence is explicitly present and disabled is not plotted and is recorded in the
export manifest as `measurement_not_configured`; data values (including all-zero diagnostics) are
never used to infer participation.
Dimensions may be 1, 2, 3, or N. A future ESKF plugin can add Magnetometer, Dual-GNSS Heading,
Air Data, Star Tracker, or another measurement group without modifying State Estimation or the
exporter.

An estimator that exposes full covariance sets `EstimatorVisualizationSpec.full_covariance` to a
`FullCovarianceSpec`. The spec owns the stable upper-triangle/full-matrix channel ID, output file
stem, ordered state symbols, physical state units, storage layout, and optional initial-record /
initial-diagonal field metadata. Export reconstructs NxN
from this metadata; KF_6 is 6-state today, while ESKF_15/24 require no exporter dimension branch.
The keyframe TXT uses only the last valid P whose timestamp is not later than START,
PARACHUTE_DEPLOY, or LANDING. If LANDING is absent, analysis end is the third event time. P is
never interpolated and a future sample is never substituted. When START precedes the first full-P
sample, the declared initial diagonal (KF_6: `INITIAL_STATE.p0_diagonal`) supplies the diagonal
P0. The raw full-P time-series CSV stays available. Batch Export creates only defined engineering
plots and does not mirror selected CSV channels into generic `Channel_*.png` files.

KF_6 currently declares Position and Velocity state groups plus GNSS Position, GNSS Velocity, and
Barometric Altitude measurement groups using its real recorded/recomputed channels. A new
estimator remains unavailable when any `required_records` or `required_channels` input is absent;
the GUI must report the missing inputs and must not manufacture a result.

## Plugin boundary

`builtin_registry()` remains the only discovery mechanism and registers SSLOG0, Pure INS, and
KF_6. Future SSLOG1/ESKF modules are added explicitly. This API does not implement a plugin store,
entry-point discovery, online installation, signatures, hot reload, or dependency management.
