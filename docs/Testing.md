# Testing and validation

`tests/sslog_synthetic.py` is the sole fixture generator. Every generated filename begins with
`SYNTHETIC_`; these files are deterministic protocol tests, not evidence of real-flight accuracy.

The suite verifies parser layout/CRC/recovery behavior, multi-rate timestamps, quaternion and
mechanization invariants, KF prediction/update health, provenance, replay-source refusal,
read-only project/export behavior, and GUI construction. Run `python -m pytest -q`.

Before a production release, add frozen (privacy-reviewed) logs for every supported firmware
build and golden outputs produced by the matching Flight Controller Host algorithms. Compare
quaternion geodesic angle, velocity, position, full P, innovations, NIS, update result, and recovery
event timestamp. A new firmware build tag remains APPROXIMATE until those vectors pass.

