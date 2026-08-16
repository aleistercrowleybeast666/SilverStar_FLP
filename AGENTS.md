# SilverStar_FLP agent guidance

Before any GUI change, read `docs/GUI_STYLE_GUIDE.md` and the complete normative
`docs/CXYL_Python_GUI_STYLE_GUIDE.md`.

Preserve these boundaries:

- `src/silverstar_flp/app/version.py` is the only application identity/version authority.
- Recorded datasets and source logs are immutable.
- Only Replay may change the global Analysis Data Source.
- Recorded Pure INS and KF_6 layers must not be collapsed into one generic Recorded curve.
- GUI and export must share quaternion convention, mission-relative trajectory semantics, event
  marker colors, curve-source labels, and language behavior.
- Do not restore removed input/source dropdowns, import/export navigation pages, or floating 3D
  event text.
- Changes belong only to this repository. RETLDC and GSHC may be inspected as references but must
  not be modified as part of an FLP task.
- Run lint plus focused tests, then the full test suite. Real-log claims require the actual log;
  synthetic fixtures never satisfy the SS0007 manual validation gate.
