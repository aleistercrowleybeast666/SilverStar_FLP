# Joint prompt 22: executable evidence map

These are software tests with explicit synthetic inputs and clocks. No physical
display, sensor, flight, or target timing is certified. Final command/results
are in `evidence_final/` and the new VALIDATION.md chapter.

| Requirement | FLP test / evidence | Scope |
|---|---|---|
| 22.1.1 gravity, small tilt, bias | `test_eskf15.py::test_stationary_gravity_and_bias_prediction`; acceptance `test_small_tilt_and_observable_residual_bias_recovery` | 60 s actual filter; observable gyro XY / accel Z recover. Static yaw and horizontal bias/tilt separation are not declared observable. |
| 22.1.2 constant velocity, acceleration, rotation | acceptance `test_constant_velocity_and_isolated_position_jump`, `test_analytic_strong_acceleration_multiaxis_rotation_at_two_gnss_rates` | Independent Rodrigues truth, strong piecewise acceleration, 10/25 Hz GNSS; p/v bounds 0.1 m/0.05 m/s. |
| 22.1.3 correct position, biased velocity | acceptance `test_long_causal_native_counterexamples_drive_actual_filter[velocity_bias-600]` | 30,000 predictions / 6000 position attempts, 118 windows; 0.2 m/s velocity bias does not accumulate a permanent position ban. |
| 22.1.4 position drift | same test `[position_drift-300]` | 1.2 m/s position drift versus zero velocity, 300 s; bounded R 1.44 and final INVALID retained. No future or endpoint correction. The 10 m threshold does not detect arbitrarily slow drift. |
| 22.1.5 jump, no fix, corruption | isolated position-jump test; independent-group test; `test_eskf15_records.py` actual seven C codec CRC negatives | Hard invalid or large NIS does not commit a correction. |
| 22.1.6 satellites 6/5/4/6 | `test_eskf15.py::test_soft_quality_has_effective_nonzero_gain_and_no_fix_stays_invalid` | Actual nonzero gain/state change under finite bounded quality R; no-fix remains invalid. |
| 22.1.7 independent groups; 22.1.9 baro | acceptance `test_bad_baro_prediction_and_four_groups_remain_independent` | PosEN/VelU accepted while bad PosU/VelEN reject; wrong 1000 m height plus valid baro rejects, INVALID after timeout, P grows. |
| 22.1.8 persistent prediction fault | acceptance `test_severe_tilt_with_valid_aids_cannot_remain_healthy_and_bad_p_rejects`; effective-fusion timeout test | 1.15 rad initial tilt causes actual MODEL_MISMATCH latch. INVALID is checked on exercised groups only. Later accepted updates cannot clear this fault. |
| 22.1.10 IMU fault paths | acceptance hard-IMU-quality/runtime-reset tests; C parity; severe-tilt test | CLIPPED/TIME_DISCONTINUITY/RANGE_UNVERIFIED/PAIR_SKEW reject without commit; runtime HISTORY_RESET requires initialization. Physical frame/range/byte decoding belongs to FCCG driver tests. |
| 22.1.11 outages/duplicate/late/source; 22.1.12 windows | `test_eskf15_native_parity.py`; staggered-window test; quality source-switch test | 750 C/Python epochs; non-dividing 97 ms boundaries, overlap, gaps, warmup, TTL. Known sources distinct; missing legacy source stays unknown. |
| 22.1.13 all aids invalid | acceptance `test_replay_step_limit_and_all_aids_invalid_are_explicit` | Zero accepted physical-invalid updates, 12 s timeout INVALID, uncertainty growth. |
| 22.1.14 bounds, invalid P, callback | acceptance capacity/callback atomicity, replay-step limit, severe-tilt/invalid-P tests | RuntimeError callback/capacity/step limit restore state/P; non-PSD and NaN initialization reject. New supervisor performs zero automatic resets without independent evidence, so no fake cooldown or recovery-success claim. Legacy KF recovery retains separate tests. |
| 22.1.15 q signs/near180/lever/units | `test_eskf15.py` right-reset, measurement/dynamics finite differences, q/-q/near-pi PSD; strict parameter tests | Independent Jacobian oracle including nonzero lever arm; 15-state dimensions and explicit SI units. |
| 22.2 time/replay | native C delayed tests at 100/250 Hz; acceptance three-group arrival permutation and identity rejection; chronological/history-miss test | 600 ms bounded history, mid-interval delays, position/velocity/baro permutation, raw-body repropagation after bias changes, outer effective-fusion clock only. No history miss applies a past measurement to current state. |
| 22.3 C/Python/oracle | `test_eskf15_c_parity.py`, native parity and independent Jacobian tests | Tolerance remains atol 2e-4 / rtol 3e-4, sub-mm/sub-mrad floating-point budget. Discrete results/admission exact. |
| 22.3 real logger closed loop | `audit_actual_backend_logger.py`, `evidence_final/actual_backend_logger.json` | Actual NONE calibration and production FlightTask snapshot, generated descriptor/header, actual ESKF backend/LoggerBus/LoggerTask append/flush, 491 records. Host fwrite sink; actual FatFs/DMA throughput tested separately in FCCG. |
| 22.3 ordered/interleaved/full-P modes | `test_eskf15_golden.py`, `test_eskf15_records.py` | Initial full P mandatory. Enabled/unknown periodic policy requires complete P; explicitly disabled periodic P is unavailable. Partial/conflicting/duplicate snapshots fail. Unattempted innovation/NIS/R unavailable only after exact admission/result agreement; attempted values remain strict. |
| 22.5 FLP pages/comparison | ESKF product test; `test_joint_gui_state.py`, `test_joint_ranges.py`, `test_two_source_comparison.py`, `test_nis_groups.py`, `test_landing_display_onset.py` | ESKF 5 groups / 15 covariance dimensions / bias, NIS selectors, GNSS three diagnostics, Landing summary, source legends and union bounds. |
| 22.5 GUI/export | ESKF product test; touch-scroll, joint-ranges, export-theme, i18n tests | zh/en × Light/Dark offscreen at 1000×700; existing scaled-text/touch tests. Explicit source survives GUI switching; cancellation/restart, categories and GIF durations checked. Physical 200% monitor/touchscreen not tested. |
| 22.5 FCCG/GSHC | FCCG initialization/retired-parameter tests; separate repository VALIDATION chapters | Actual read-only fixed profiles and inactive legacy parameters; firmware START gates and GSHC readiness/health are tested by their owners. |

Acceptance names refer to `tests/test_eskf15_acceptance.py`. All original five-log
outcomes remain in `four_way_comparison/SS0000` through `SS0004`, with full ESKF
diagnostics under `five_logs_contract_final/`. SS0002 origin is never substituted.
Old logs lack raw-body quality and trusted source/epoch evidence required for new
firmware faithful replay.

The final review added actual C trim-boundary negative tests to
`test_eskf15_native_parity.py`: CLIPPED/NaN/live non-PSD/prefix non-PSD preserve
all authoritative state/history bytes; two-prefix success removes its old
event only after prediction succeeds; full 192-slot rejection stays atomic.
The final 20-test delta (18.82 s) includes those cases and original math/window/
delay/golden policies, with no extra firmware state buffer.

Final authorized quality delta: `tests/test_navigation_quality_gain.py` covers all five zero/nonfinite/tiny float32 gain cases; legacy revision 2; clone/checkpoint/epoch flag ownership; ACCEPTED with R>1, SOFT, physically invalid and per-group timeouts; original satellite/window factors and actual robust multiplication; float32 ordinary-ACCEPTED R roundtrip. Fresh `approved_quality_comparison.json` compares all five immutable inputs and `approved_quality_final_bridge.json` checks the final actual production pair. Full software evidence: 483 passed, 9 historical skips.
