# Pending revision-3 integration: resumption plan

This plan was prepared during the approval hold. The user subsequently explicitly
approved continuing FLP changes; the four-file patch has now been applied.
Execution evidence is recorded separately in VALIDATION.md and fresh outputs.
The inert patch is at
`D:/python_software/SilverStar_FCCG/tests/joint_rework_20260927/FLP_REV3_PENDING.patch`.
Its original patch remains an inert historical review artifact; the final implementation
also corrects ordinary-ACCEPTED float32 R roundtrip handling.

## Remaining integration and tests

- `src/silverstar_flp/plugins/algorithms/kf6/plugin.py`: enable actual-float32
  finite/nonzero-gain qualification only for revision 3; emit actual result and
  total quality/consistency/robust scale.
- `src/silverstar_flp/plugins/algorithms/kf6/fixed_lag.py`: preserve the new flag
  in epoch restoration/model identity; emit actual result and total scale.
  Shallow clone already preserves the flag.
- `src/silverstar_flp/analysis/navigation_revision3.py`: carry all four
  group-specific quality scales into measurement events and the supervisor.
- `src/silverstar_flp/plugins/algorithms/eskf15/plugin.py`: pass actual total
  variance scale to the supervisor without changing nominal/P arithmetic.

Add regression cases for all five groups: zero/nonfinite gain rejects without
state/P/success-clock changes; tiny nonzero K remains effective even when K*K
underflows; zero innovation with nonzero K remains accepted; legacy revision 2
unchanged; clone/checkpoint/epoch restore retain qualification. Cover accepted
+ R>1, soft result, physical rejection, initially unknown quality and timeout
priority. Satellite, PosEN-only consistency and robust scale each apply once.
The latest bridge's 40/40 health match does not cover accepted + R>1.

## Commands after approval

Run from `D:/python_software/SilverStar_FLP` in PowerShell. Require exit 0 after
each gate. Add the newly created regression file to the focused command below.

```powershell
$env:PYTHONPATH='src;tests;tests/joint_rework_20260927'
$env:PYTHONDONTWRITEBYTECODE='1'
$env:QT_QPA_PLATFORM='offscreen'
$env:SILVERSTAR_FCCG_ROOT='D:/python_software/SilverStar_FCCG'
$env:SILVERSTAR_ESKF_GENERATED='D:/python_software/SilverStar_FCCG/tests/joint_rework_20260927/verified_matrix/eskf15_flight'
$flpPython='D:/python_software/SilverStar_FLP/.venv/Scripts/python.exe'
& $flpPython -m pytest tests/test_navigation_revision_contract.py tests/test_quality_revision_selection.py tests/test_kf6_outage.py tests/test_eskf15.py -q --basetemp=tests/joint_rework_20260927/approved_quality_focus_temp -o cache_dir=tests/joint_rework_20260927/approved_quality_focus_cache
```

Before real-log runs, save old report/NPZ hashes under a fresh evidence folder.
Never overwrite `five_logs`, `five_logs_kf6_rev3`, `five_logs_contract_final`, or
`four_way_comparison`. Original BINs and exact decoder remain read-only.

```powershell
$env:SILVERSTAR_LOG_RUN='five_logs_quality_fix_kf6'
$env:SILVERSTAR_KF_REV3_ONLY='1'
$env:SILVERSTAR_ESKF_ONLY=$null
& $flpPython tests/joint_rework_20260927/run_five_logs.py *> tests/joint_rework_20260927/five_logs_quality_fix_kf6.log
$env:SILVERSTAR_LOG_RUN='five_logs_quality_fix_eskf'
$env:SILVERSTAR_KF_REV3_ONLY=$null
$env:SILVERSTAR_ESKF_ONLY='1'
& $flpPython tests/joint_rework_20260927/run_five_logs.py *> tests/joint_rework_20260927/five_logs_quality_fix_eskf.log
$env:SILVERSTAR_ESKF_ONLY=$null
$env:SILVERSTAR_LOG_RUN=$null
```

Compare every new numerical channel against its saved predecessor; derive new
health from actual new outcomes/scales. Preserve SS0002 origin failure. Use a
fresh report folder for health distributions/endpoints/first failures/hashes.
`build_four_way_report.py` hardcodes old paths, so do not rerun it unchanged.

Expected, not measured: ESKF health wiring has no kernel feedback, so nominal/P
should match. KF revision 3 should differ only for actual all-zero/nonfinite K;
usual positive-K arithmetic order stays unchanged. Prior INVALID outcomes in
SS0000/2/4 remain dominant if timing/outcomes stay unchanged. SS0001/3 may move
from HEALTHY to DEGRADED due to R>1. The actual new table requires the reruns.
Legacy revision 2 must not be recomputed with revision 3 semantics.

After the last product/test edit run the full top-level suite once:

```powershell
$flpTests=Get-ChildItem tests -File -Filter 'test_*.py' | ForEach-Object { $_.FullName }
& $flpPython -m pytest @flpTests -q --basetemp=tests/joint_rework_20260927/approved_quality_full_temp -o cache_dir=tests/joint_rework_20260927/approved_quality_full_cache *> tests/joint_rework_20260927/approved_quality_full.log
& $flpPython -m ruff check src tools @flpTests *> tests/joint_rework_20260927/approved_quality_ruff.log
$env:PYTHONPYCACHEPREFIX='D:/python_software/SilverStar_FLP/tests/joint_rework_20260927/approved_quality_compile_cache'
& $flpPython -m compileall -q src *> tests/joint_rework_20260927/approved_quality_compile.log
$env:PYTHONPYCACHEPREFIX=$null
```

Retain actual skip reasons; nine historical optional fixtures were absent in
the old 426-pass run. C parity/direct-codec golden tests are in this suite.
Reload the latest production bridge pair and compare nominal/P/measurements
plus exact-timestamp health. Repeating all 361 exports is unnecessary unless
export code or available channels change.

Package with the existing helper and a fresh output root; no install/network:

```powershell
& $flpPython -c "from pathlib import Path; import package_final_smoke as p; r=Path('tests/joint_rework_20260927/approved_quality_package').resolve(); r.mkdir(exist_ok=False); (r/'evidence_final').mkdir(); p.OUTPUT=r/'package_final'; p.Run()" *> tests/joint_rework_20260927/approved_quality_package.log
```

Finish with `git diff --check`, append actual new results to VALIDATION and the
compact evidence list, and report paths to root for staging. Root alone
commits/pushes. No hardware, NVM, physical output or shutdown is authorized here.
