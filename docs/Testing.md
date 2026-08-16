# Testing and validation

`tests/sslog_synthetic.py` is the sole fixture generator. Every generated filename begins with
`SYNTHETIC_`; these files are deterministic protocol tests, not evidence of real-flight accuracy.

The suite verifies parser layout/CRC/recovery behavior, multi-rate timestamps, quaternion and
mechanization invariants, KF prediction/update health, provenance, replay-source refusal,
read-only project/export behavior, and GUI construction. The analysis-rich synthetic fixture also
contains the exact current CALIBRATION_RESULT, ALIGNMENT_RESULT, INITIAL_STATE, KF6_STATE, and
KF6_DIAGNOSTIC wire layouts, plus distinct enabled/actual deploy masks.

The 0.0.2 suite additionally verifies the fixed title/version authority, deep-blue/light-blue GUI
states, conventional ten-row combo popups, modal import/export workflow, fixed corrected-IMU GUI
request, complete Replay fidelity/warning/parameter translations, strict source eligibility,
return to Recorded, Replay-only source authority, and read-only Flight/State source displays.

Visualization/export tests require separate Recorded Pure INS and KF_6 layers, non-repeating
colors beyond the base palette, START-relative coordinates without mutating the dataset,
quaternion-rotated rocket meshes, red pre-deploy and blue post-deploy trajectory/current phases,
a single orange Deploy marker with `pxMode=False` and trajectory-extent-derived world size, camera
distance preservation during playback and language changes, synchronized PNG/GIF behavior,
combined GIF frame count, and partial-failure manifests.

Estimator tests declare a test-only ESKF-like plugin with five state groups and GNSS, barometer,
and magnetometer measurement groups. They verify that the State Estimation controls, plots, and
generic update table are created solely from metadata and that the page source contains no
KF6-specific channel IDs. What-if tests use non-default recorded SYSTEM_CONFIG values, modify
parameters, and verify that Reset restores those recorded values. Replay regression also compares
the deterministic KF6 result hash before and after the GUI/metadata refactor.

Run `python -m pytest -q`.

Before a production release, add frozen (privacy-reviewed) logs for every supported firmware
build and golden outputs produced by the matching Flight Controller Host algorithms. Compare
quaternion geodesic angle, velocity, position, full P, innovations, NIS, update result, and recovery
event timestamp. A new firmware build tag remains APPROXIMATE until those vectors pass.

Manual release validation must additionally open the requested real `SS0007.BIN` and compare its
Overview calibration/alignment/deploy values with decoded records. Synthetic fixtures cannot be
used to mark that real-log check as passed.
