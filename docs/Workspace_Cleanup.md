# Safe workspace cleanup

From the repository root:

```powershell
python tools/clean_workspace.py --dry-run
python tools/clean_workspace.py --apply
```

Without arguments the tool performs a dry run. It never invokes `git clean`. It validates the
actual Git root, stays inside it, rejects symlink/junction/reparse ancestors, and rechecks the
Git index and path immediately before each removal. It unlinks approved individual files and
uses only nonrecursive `rmdir` for empty directories. Busy or changed targets are reported refused.
Run it after local test/export/package jobs have finished.

Candidates are Python bytecode, documented cache trees (`__pycache__`, `.pytest_cache`,
`.ruff_cache`, `.mypy_cache`), and known generated suffixes only beneath root build/dist,
`.acceptance`, `.codex_pytest_*`, and `.codex_container_stage_*`. Arbitrary root PNG/JSON/CSV
files and unknown suffixes are not candidates. The virtual environment, Git internals, docs,
fixtures, golden directories, tracked files, source files, and `.BIN`/`.sslog`/`.ssdecoder`/
`.ssflp` inputs are preserved. A directory containing any protected file remains in place.

Some historical `.codex_pytest_*` and `.codex_container_stage_*` outputs are already tracked.
New ignore rules prevent adding future leftovers; they do not remove existing tracked files.
This task does not rewrite history or silently untrack/delete those assets. No raw user log,
decoder, project, or source archive is removed.

New acceptance runs use `.acceptance/<run-name>` or pytest `tmp_path`; long-term fixtures belong
in `tests/fixtures` and must be reviewed and explicitly added. See
[Display_DataQuality.md](Display_DataQuality.md) for the display/quality contract.
