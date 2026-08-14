# SilverStar Flight Log Processor

SilverStar_FLP is a Windows desktop application and command-line toolkit for SilverStar
`SSLOG0` flight logs. It parses the current binary profile, reconstructs the complete Pure INS
and KF6 navigation chains from `START`, compares recorded and recomputed results, visualizes the
flight, and exports timestamp-faithful data products.

Version: **0.1.0-dev**

> Raw `.BIN` logs are opened read-only. A `.ssflp` project stores references, replay settings,
> notes, and UI state; it never embeds or rewrites the raw log.

## Start here

### 1. Create the virtual environment

From this directory in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev,packaging]"
```

The repository's `main.py` automatically re-enters `.venv` when it exists, so after the first
installation you can also start it without manually activating the environment.

### 2. Open the application

```powershell
python main.py
```

Then choose **Open Flight Log** and select a flight-controller `.BIN` file. You can also drag a
`.BIN` onto the window or pass it directly:

```powershell
python main.py D:\logs\flight.BIN
```

Language, theme, import, and export controls are in the dark-blue top bar. Import and export open
focused option dialogs instead of occupying navigation pages. The six analysis pages are:

1. Overview — mission summary, apogee estimate, integrity status, and events.
2. Flight — altitude/velocity plots and an ENU 3D trajectory.
3. Attitude / IMU — software attitude, reference-only hardware quaternion, IMU, and 3D attitude.
4. Navigation — recorded/recomputed position, velocity, covariance, innovations, and NIS.
5. Replay — Pure INS or KF6, explicit input source, Recorded configuration or What-if.
6. Data Explorer — all standard channels and every decoded record field.

The Replay page scrolls when its What-if parameter form is taller than the available window.
Every combo box uses a conventional downward popup with at most ten visible rows; longer lists
scroll inside the popup.

Chinese and English interface text and Light/Dark themes are built in. Export language is an
independent choice; `_ZH` and `_EN` products contain matching image text.

## What the parser supports

The built-in parser ID is `silverstar.log_parser.sslog0`. It supports profile 0's 64-byte file
header, 24-byte common record header, payload, and CRC-32/IEEE trailer. All current record types
`0x01` through `0x19` are decoded, including both internal MISSION_CONFIG layouts.

- Unknown CRC-valid record types and versions are safely skipped by declared length.
- A bad record CRC or lost sync scans forward to the next byte-aligned `FLG1` candidate.
- An incomplete final record is reported as a truncated tail and ignored.
- Record counts, CRC errors, recoveries, sequence gaps, unknown types/versions, and offsets are
  retained in parser diagnostics.
- Each channel owns its real `timestamp_us`; unlike-rate sensors are never forced into one table
  and timestamps are never rebuilt from nominal rates.

AIR telemetry frames are intentionally not treated as flight logs. See [SSLOG.md](docs/SSLOG.md).

## Navigation replay semantics

At successful `START`, `INITIAL_STATE.q_nb` freezes the adopted WXYZ Hamilton Body-to-ENU
attitude. After that boundary, the mission attitude is propagated entirely in software. The
hardware quaternion remains a diagnostic reference and is never used as the authoritative
post-START replay attitude.

Pure INS has two explicit, non-interchangeable sources:

- **Corrected IMU**: trapezoidal subintervals, two-sample coning/sculling, quaternion propagation,
  Body-to-ENU specific force, gravity removal, velocity, and trapezoidal position.
- **Recorded Inertial Increment**: uses the recorded coning/sculling output and re-runs the same
  quaternion/velocity/position mechanization.

KF6 uses state order `[pE,pN,pU,vE,vN,vU]`, the order in current `navigation_kf.c`. It restores
P0, process acceleration standard deviations, NIS thresholds, and maximum soft-R scale; then it
uses the independent mechanization prediction plus logged GNSS and barometer measurements. It
exports full P, innovations, effective R, NIS, accepted/soft/rejected results, and reacquisition
diagnostics.

Every result is labeled:

- **Recorded** — values actually logged by the flight controller;
- **Recomputed** — replay using the recorded configuration;
- **What-if** — replay with explicitly modified parameters.

Separately, fidelity is `EXACT`, `APPROXIMATE`, or `UNAVAILABLE`. Missing required input never
causes a hidden source switch. Build mismatch, data gaps, missing measurement-application timing,
or decimation lower fidelity with an explicit warning. See [Replay.md](docs/Replay.md) and
[Architecture.md](docs/Architecture.md).

## Command line

After installation:

```powershell
sslog inspect D:\logs\flight.BIN
sslog replay D:\logs\flight.BIN --algorithm pure_ins --source corrected_imu
sslog replay D:\logs\flight.BIN --algorithm kf6 --parameter process_accel_std_u=2.5
sslog export D:\logs\flight.BIN D:\exports --language en_US --theme dark
sslog gui D:\logs\flight.BIN
```

`inspect` prints JSON metadata, record counts, channels, overview statistics, and parser
diagnostics. CSV export is one file per channel so every sensor keeps its own timing.

## Tests

```powershell
python -m pytest -q
```

The repository fixtures are generated in memory and are explicitly named **SYNTHETIC**. Tests
cover all current payload layouts, unknown records/versions, CRC recovery, sync recovery,
truncated tails, sequence gaps, stationary Pure INS through both input chains, KF6 covariance and
NIS rejection, quaternion sign-invariant error, deploy replay, project immutability, export, and a
headless six-page GUI/top-bar/dialog smoke test.

No real flight log is included. Phase 2 requires frozen real logs and host-C golden vectors from
the matching flight-controller build; this is tracked in [TARGETS.md](TARGETS.md).

## Windows packaging

Install the `packaging` extra and run:

```powershell
.\scripts\build_windows.ps1
```

The PyInstaller output appears under `dist\SilverStar_FLP`. Run the test suite before packaging.
PyInstaller preparation is included, but a distributable build is not committed to source
control.

## Design boundaries

There are exactly two plugin types:

- Log Parser Plugin — one incompatible log container generation;
- Algorithm Plugin — one complete navigation/estimation algorithm.

Pure INS and KF6 are the only first-release Algorithm Plugins. Deploy and landing replay are Core
flight-analysis services. ESKF15 and ESKF24 are future targets only; their interface can be added
without changing the standard navigation pages, but neither is implemented now.

## Source of truth and remaining risk

Protocol and algorithm behavior were derived from the current `Flight_Controller0.5` log,
mechanization, attitude, KF, recovery, configuration, and host-test sources. The first release is a
firmware-order NumPy `float32` reimplementation rather than a runtime firmware DLL; the rationale
is recorded in Architecture.md. Numerical order is intentionally close to the C implementation,
but cross-compiler floating-point differences remain possible. Never claim `EXACT` for a
different firmware build without adding and passing its golden tests.
