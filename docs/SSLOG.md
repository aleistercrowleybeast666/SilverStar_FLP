# SSLOG0 support

The built-in parser implements profile 0: a 64-byte header followed by records containing a
24-byte common header, payload, and 4-byte CRC-32/IEEE. It dispatches by
`(record_type, record_version)`, supports all current IDs `0x01` through `0x19`, and understands
MISSION_CONFIG internal draft payload versions 1 and 2.

CRC failure or an unexpected byte sequence causes a scan for the next byte-aligned `FLG1` sync.
Already decoded records remain available. A final incomplete header, payload, or CRC is marked as
a truncated tail and ignored. CRC-valid unknown record types and unknown versions are skipped by
their declared payload length and counted in diagnostics.

