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

## Phase 2

- validate against real flight logs (including SS0007.BIN when supplied) and frozen firmware C
  golden datasets
- improve parameter scanning and high-dynamic timing/OOSM analysis

## Future

- ESKF15 Algorithm Plugin
- ESKF24 Algorithm Plugin

No ESKF implementation is part of Phase 1.
