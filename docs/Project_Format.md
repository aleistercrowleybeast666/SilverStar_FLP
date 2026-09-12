# Project format v3

`.ssflp` is an atomic, single-log reference document. It never embeds or modifies a log or decoder.
Version 3 rejects all older versions, including v2 multiplier configurations; no migration exists.
Decoder, generation, Catalog, Semantics, cache and container identity checks remain mandatory.

Each `replay_configurations` item contains exactly:

- `algorithm_id` and `algorithm_version`;
- `mode`: `recorded_configuration`, `what_if`, or explicit `offline`;
- `input_source`;
- `actual_values`: ID-to-value map;
- `parameter_schema_identity`: SHA-256 of plugin schema metadata;
- `provenance`: `Firmware build configuration from .ssdecoder` or `Algorithm Plugin actual defaults`.

Unknown fields/IDs, missing values, invalid types/ranges, non-finite numbers, old plugin/schema
identities and invalid modes are rejected. Recorded values cannot override the package.
Restore checks every saved configuration against the opened dataset and validates provenance
before publishing it. The `draft` entry preserves unsubmitted What-if edits; historical run
configurations remain available in the document, while result arrays are recomputed when requested.
Saves flush a temporary UTF-8 JSON file and atomically replace the target.
