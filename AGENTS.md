# SilverStar_FLP agent guidance

Before any GUI change, read `docs/GUI_STYLE_GUIDE.md` and the complete normative
`docs/CXYL_Python_GUI_STYLE_GUIDE.md`.

Preserve these boundaries:

- `src/silverstar_flp/app/version.py` is the only application identity/version authority.
- Recorded datasets and source logs are immutable.
- Production log opening must go through `LogOpenCoordinator`: one log, exact `.ssdecoder` 1.1,
  mandatory Descriptor, validation before cache, dynamic parser, semantic adapter, and mandatory
  Calibration Result. Do not add package 1.0, unsigned, Descriptor-less, filename, manual-override,
  or fixed-parser fallbacks.
- The production plugin registry owns trusted containers and offline algorithms only; firmware
  component IDs from Project Semantics never instantiate executable plugins.
- Preserve raw dynamic channels. Stable semantic roles must remain audited, immutable, zero-copy
  aliases; upper GUI/export/algorithm code must query `DatasetSemanticContext` rather than infer
  offsets or silently select an ambiguous device.
- Keep firmware membership, recorded output presence, complete recorded configuration, and
  offline plugin availability independent. Offline defaults must never be reported as recorded.
- `.ssflp` is an atomic single-log v2 reference format with full decoder/cache/container identity;
  old project versions and identity mismatches are rejected.
- Only Replay may change the global Analysis Data Source.
- Recorded Pure INS and KF_6 layers must not be collapsed into one generic Recorded curve.
- GUI and export must share quaternion convention, mission-relative trajectory semantics, event
  marker colors, curve-source labels, and language behavior.
- Do not restore removed input/source dropdowns, import/export navigation pages, or floating 3D
  event text.
- Changes belong only to this repository. RETLDC and GSHC may be inspected as references but must
  not be modified as part of an FLP task.
- Run lint plus focused tests, then the full test suite. A real package alone proves only package
  validity; decoded/replay claims require its matching actual log. Synthetic fixtures never
  satisfy SS0007 or SS_TEST_0 real-log validation gates.
