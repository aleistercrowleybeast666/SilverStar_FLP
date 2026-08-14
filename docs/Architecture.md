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
  -> Core overview / plots / Data Explorer / event analysis
  -> Algorithm Plugin replay
  -> Recorded vs Recomputed comparison
  -> Core export (TXT/JSON/CSV/PNG/GIF)
```

Every series owns its real timestamp array. No channel is reconstructed from a nominal sample
frequency and unlike-rate records are not forced into one large table.

## START and attitude authority

`INITIAL_STATE` freezes the START-adopted `q_nb0`. It is WXYZ Hamilton and rotates Body vectors
into ENU. From START onward, the authoritative task attitude is produced only by software:

```text
INITIAL_STATE.q_nb
  + IMU_CORRECTED (or recorded INERTIAL_INCREMENT)
  + two-sample coning/sculling
  + right-multiplied body rotation increment
  -> software q_nb -> ENU specific force -> gravity compensation -> v -> p
```

`HW_QUAT_NATIVE` remains diagnostic/reference data after START. `PURE_INS` and `KF6_STATE` are
recorded outputs used for comparison; neither is fed back as normal replay input.

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

