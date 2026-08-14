# Replay semantics

Pure INS offers two explicit sources:

- **Corrected IMU** rebuilds subinterval increments, coning/sculling compensation, software
  quaternion, ENU acceleration, velocity, and position from START.
- **Recorded Inertial Increment** skips IMU preprocessing and re-runs mechanization from START.

The application never silently changes source when data is absent. KF6 consumes an independently
propagated attitude/mechanization prediction plus logged GNSS and barometer measurements, restored
P0/Q/R/NIS configuration, and optional What-if overrides. Recorded algorithm outputs are only
comparison targets.

