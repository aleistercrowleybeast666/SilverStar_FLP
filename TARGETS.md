# Development targets

## Phase 1

- SSLOG0 parser, corruption recovery, complete current Record registry
- FlightDataset, CLI, project model, Overview and Data Explorer
- PySide6 GUI, Light/Dark, Chinese/English, plots and 3D viewers
- Pure INS and KF6 replay, Recorded/Recomputed comparison, What-if parameters
- persistent ReplayResultStore plus Replay-only Recorded/Recomputed/What-if analysis-source
  selection with strict complete-result eligibility
- Overview calibration model, initial alignment, deploy altitude/reason, and event timeline
- consolidated Flight page with separate Recorded Pure INS/KF_6 layers, filter-only read-only
  State Estimation source display, and themed mission-relative rocket/trajectory playback
- Follow UI / ZH / EN standard plot set, segmented trajectory, combined <=60-frame GIF
- partial-failure export manifest
- trusted `LogContainerPlugin` API with the built-in SSLOG0 0.0 container
- exact-only `.ssdecoder` 1.1 import, dynamic Record Catalog decoding, Project Semantics,
  multi-instance raw channels plus stable aliases, mandatory calibration validation, Descriptor
  matching, bounded discovery, and content-addressed cache
- one atomic single-log coordinator shared by GUI import/folder search/drag-drop, CLI, and `.ssflp`
  v2 restore; no production fixed-parser or Descriptor-less fallback
- semantic Overview/Replay/State/Data Explorer pages and audit export manifest with full decoder,
  firmware, calibration, alias, and replay provenance

## Phase 2

- validate against real flight logs (including SS0007.BIN when supplied) and frozen firmware C
  golden datasets
- validate the supplied FCCG 0.0.10 package against its matching immutable real log and frozen host
  golden output before changing Pure INS/KF_6 fidelity from `APPROXIMATE`
- improve parameter scanning and high-dynamic timing/OOSM analysis

## Future

- ESKF15 Algorithm Plugin
- ESKF24 Algorithm Plugin

No ESKF implementation is part of Phase 1.
