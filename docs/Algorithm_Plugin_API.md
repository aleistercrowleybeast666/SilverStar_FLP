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
- a covariance-diagonal channel and the component indices owned by the group.

The GUI creates the State Group selector from these entries. It plots only the selected group and
offers standard deviation (`sqrt(Pii)`, default) or variance (`Pii`) display. Adding ESKF position,
velocity, attitude-error, gyro-bias, or accelerometer-bias groups therefore does not require a GUI
change.

Each `MeasurementGroupSpec` declares:

- stable measurement-group ID, translated label, dimension, and component names;
- innovation, NIS, update-result, R-scale, and optional age/uncertainty/effective-R channels;
- vector-column indices and optional attempt-mask/dimension channels;
- optional soft/hard NIS threshold parameter IDs.

Innovation, NIS, Measurements, and the generic Update Event Table all consume this metadata.
Dimensions may be 1, 2, 3, or N. A future ESKF plugin can add Magnetometer, Dual-GNSS Heading,
Air Data, Star Tracker, or another measurement group without modifying State Estimation.

KF_6 currently declares Position and Velocity state groups plus GNSS Position, GNSS Velocity, and
Barometric Altitude measurement groups using its real recorded/recomputed channels. A new
estimator remains unavailable when any `required_records` or `required_channels` input is absent;
the GUI must report the missing inputs and must not manufacture a result.

## Plugin boundary

`builtin_registry()` remains the only discovery mechanism and registers SSLOG0, Pure INS, and
KF_6. Future SSLOG1/ESKF modules are added explicitly. This API does not implement a plugin store,
entry-point discovery, online installation, signatures, hot reload, or dependency management.
