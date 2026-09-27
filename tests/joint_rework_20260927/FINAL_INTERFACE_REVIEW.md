# Final C / Python interface review — 2026-09-27

Scope: actual FCCG ESKF core/replay/backend, Core navigation health and INS BODY
producer, against the FLP filter/replay/record adapter. This is code review plus
the named targeted software tests; it is not hardware or performance acceptance.

Three concrete findings were reported and corrected:

1. C prediction previously called history trim before rejecting invalid BODY.
   The existing compiled DLL reproduced anchor/count changing from
   `(1000000, 60)` to `(1010000, 59)` after CLIPPED rejection while live time
   stayed 1600000. `navigation_eskf_replay.c` now plans the prefix, builds its
   candidate in existing `working` scratch, and commits anchor/history only
   after transactional core prediction succeeds. The final 20-test delta
   checks all authoritative bytes after CLIPPED, NaN, live-P and prefix-P
   failures, successful multi-prefix commit, and capacity rejection. No extra
   full state/global buffer or ABI was added.
2. C health originally lacked the Python MODEL_MISMATCH latch. Its owner added
   `s_model_mismatch`, set on the typed MODEL_MISMATCH reason, cleared only by
   lifecycle Reset; GroupGet/OverallGet report INVALID while latched. Later
   good input cannot silently restore health. The reviewed final code contains
   this path; its actual Host/target gates are recorded by FCCG's owner.
3. C health rejected equal receive times even when source changed. Its owner
   restricted duplicate/old-time rejection to the same source, matching Python.
   Missing legacy source remains unknown rather than being fabricated.

The following paths agree under review and executed evidence:

- Core prediction/update construct candidate nominal/P in workspace. Finite,
  covariance, large-angle/bias and gain checks precede live state commit.
  Rejected measurements do not commit P or nominal correction.
- Replay insertion orders measurement/group/source/sequence, runs only on
  scratch working state and commits live state after the complete replay.
  Failed insertion removes its candidate event. History miss is explicit.
  Physical body source/epoch is immutable within the navigation lifecycle.
- `Backend_OutcomePublish` is outside historical `Replay_Run`. Effective
  evidence requires a committed replay, physical validity, admission, accepted
  result and positive gain. `SystemNavigationHealth_Observe` stores actual
  evaluation time, not measurement or receive time, as successful fusion.
  Five groups retain independent clocks; no-success uses the epoch start.
- INS records hard IMU faults before dropping invalid samples. The health
  manager OR-latches the hard mask; subsequent good samples only change the
  transient quality field. Backend prediction failures additionally latch a
  time fault. Overall and group reads consult the persistent latch.
- INS applies the calibration correction before constructing two actual body
  half-interval means. The ESKF backend reads only those BODY arrays; legacy
  coning/sculling delta arrays occupy independent fields and are not consumed
  by ESKF. The core subtracts residual biases and owns coning/sculling once.
  Its continuous noise/R definitions and right-error reset agree with Python.
- Body logs carry actual calibration generation; initialization separately
  supplies navigation epoch. The parser/replay checks both identities without
  treating calibration generation as epoch. Four P fragments use complete
  timestamp/snapshot/algorithm/epoch/source/calibration/phase identity.
- The final actual-backend logger pair independently traverses production
  calibration/header/LoggerBus/LoggerTask and exact FLP import, nominal/full-P/
  attempted-measurement comparison and export. Discrete admission/results are
  exact. Undefined unattempted diagnostics are visibly unavailable, not passed
  by a wider numeric tolerance. Ordered/interleaved codec tests separately
  guard nonadjacent covariance pieces.

No further concrete defect was found in this scoped review. The five old-log
What-if failures, including final INVALID states and large drift, remain
recorded and are not described as accuracy/performance success.
