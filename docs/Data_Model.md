# FlightDataset data model

`FlightDataset` is immutable after parsing. It contains the parsed header, decoded records grouped
by record name, independent `TimeSeries` channels, source metadata, and `ParserDiagnostics`.

Every `TimeSeries` contains its own `uint64 timestamp_us`, values, unit, physical quantity, source,
validity vector, column names, and metadata. Times are sorted using the logged timestamp. No
nominal sample rate is used to synthesize time and different rates are not interpolated until a
specific comparison explicitly requests it.

Algorithm results use the same `TimeSeries` model. Standard IDs (`attitude.q_nb`,
`navigation.velocity_enu`, `navigation.position_enu`) feed common views. Algorithm-specific IDs
remain discoverable in Data Explorer and export.

