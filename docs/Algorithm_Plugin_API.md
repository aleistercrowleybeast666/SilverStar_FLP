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

