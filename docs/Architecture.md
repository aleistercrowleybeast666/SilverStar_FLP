# SilverStar_FLP Architecture

## Design boundary

SilverStar_FLP has exactly two plugin types:

1. **Log Parser Plugin** converts one incompatible flight-log container generation into a
   GUI-independent `FlightDataset`. SSLOG0 is one parser plugin. Record decoders are a private
   `(record_type, record_version)` registry inside that parser, not plugins.
2. **Algorithm Plugin** represents one complete navigation/state-estimation algorithm. The
   built-ins are Pure INS and KF_6. Plotting, export, project persistence, Data Explorer, deploy
   replay, landing replay, and GUI code remain Core services.

The GUI never reads byte offsets. It consumes `FlightDataset`, standard channels, algorithm
results, stable diagnostic codes, and metadata.

## Protocol truth and data flow

The implementation is based on the current `Flight_Controller0.5` sources, especially
`STORAGE_AND_FLIGHT_LOG.md`, `logger_bus.*`, `logger_task.c`, `ins_mechanization.c`,
`attitude_frame.c`, `navigation_kf.c`, and their Host Tests. AIR frames are deliberately outside
the SSLOG parser.

```text
read-only SSLOG BIN
  -> SSLOG0 parser (header/record CRC, FLG1 recovery, decoder registry)
  -> FlightDataset (independent multi-rate time series + decoded records)
  -> Algorithm Plugin replay
  -> ReplayResultStore (every Recomputed and What-if run is retained)
  -> AnalysisSource + ChannelResolver
  -> Overview / Flight / State Estimation / Data Explorer
  -> Core export (JSON/CSV/localized PNG/segmented 3D PNG/combined GIF)
```

Every series owns its real timestamp array. No channel is reconstructed from a nominal sample
frequency and unlike-rate records are not forced into one large table.

## Analysis surface

Overview is recorded mission truth: file integrity, START-cropped metrics, Calibration Result,
Initial Alignment/INITIAL_STATE, actual deploy event/detail, and the translated event timeline.
Flight owns velocity, position, corrected IMU, attitude, and 3D playback. State Estimation owns
filter internals only. Replay is page two, the source-generation entry point, and the only page
allowed to change the global Analysis Data Source. Flight and State Estimation show that source
read-only.

State Estimation contains no KF6 channel IDs. It resolves the active estimator's
`EstimatorVisualizationSpec`, builds State Group and Measurement selectors, and renders
covariance, innovation, NIS, measurement diagnostics, and a generic update-event table from
`StateGroupSpec`/`MeasurementGroupSpec`. Pure INS has no estimator visualization spec. Future
ESKF_15/24 state or sensor groups are plugin metadata changes, not page changes.

`ReplayResultStore` assigns a unique result/source ID to every run and never replaces a prior
Recomputed or What-if result. `ChannelResolver` is the single Recorded/replay lookup layer used
by Flight, State Estimation, Data Explorer, and export. Only complete results with valid attitude,
velocity, and position can be selected. Recorded Pure INS and Recorded KF_6 navigation are
separate layers. A replay source is plotted with both recorded layers as dashed references;
Recorded mode shows both as primary curves.

## START and attitude authority

`INITIAL_STATE` freezes the START-adopted `q_nb0`. It is WXYZ Hamilton and rotates Body vectors
into ENU. From START onward, the authoritative task attitude is produced only by software:

```text
INITIAL_STATE.q_nb
  + IMU_CORRECTED (GUI authority; recorded INERTIAL_INCREMENT remains internal/CLI)
  + two-sample coning/sculling
  + right-multiplied body rotation increment
  -> software q_nb -> ENU specific force -> gravity compensation -> v -> p
```

`HW_QUAT_NATIVE` remains diagnostic/reference data after START. `PURE_INS` and `KF6_STATE` are
recorded outputs used for comparison; neither is fed back as normal replay input.

## Visualization invariants

The attitude view and PNG/GIF export rotate every vertex of the same square-base, 2.2-unit rocket
mesh with `Quaternion_RotateVector`; body axes remain a thinner secondary reference. Trajectory
rendering subtracts a display-only origin interpolated at mission START (or the first valid
post-START navigation sample). The immutable dataset is never rewritten.

Pre-deploy trajectory and Current use red; at and after Deploy both use blue. Deploy is one orange
point and Landing is purple. OpenGL event/current markers use `pxMode=False` and diameters derived
from the E/N/U trajectory extent, so they are world-space geometry rather than fixed screen-pixel
circles. START is represented by the coordinate origin, not a marker, and event names are not
rendered as floating 3D text.
Full-trajectory grid/camera fitting runs only when data/source changes or Reset View is requested;
playback frames never overwrite user zoom or orbit. Plot refreshes allocate at least sixteen
distinct colors and generate additional HSV colors without modulo cycling.

## Firmware algorithm reuse decision

Two options were evaluated:

- a runtime DLL binding to the firmware C sources;
- a faithful Python/NumPy implementation with firmware-order float32 operations and golden
  validation against the same C sources.

The first phase uses the second option. The C units include build-time user configuration and
embedded interface headers; shipping a DLL would either bind FLP to an external firmware checkout
or duplicate that configuration behind an ABI. The Python implementation keeps What-if parameter
editing and PyInstaller distribution straightforward. Operation order, quaternion convention,
two-sample grouping, gravity sign, KF state ordering, Joseph update, NIS gates, and timestamps are
kept aligned with `SILV0008`. A firmware build-tag mismatch lowers replay fidelity rather than
silently claiming an exact reproduction. The remaining drift risk is documented and guarded by
golden/integration tests.

## KF6 state convention

The current firmware source is authoritative: KF6 state order is
`[pE, pN, pU, vE, vN, vU]`. Some early design prose listed velocity first; FLP follows the actual
`navigation_kf.c` implementation and SSLOG fields.

## Responsiveness and errors

Parsing, replay, export, and GIF creation accept a cooperative `TaskContext`. The GUI runs them in
worker threads, reports progress, and requests cancellation without terminating Python. Core and
plugins emit stable codes; the i18n layer translates them. Full tracebacks go to the application
log while dialogs show concise user-facing messages.
