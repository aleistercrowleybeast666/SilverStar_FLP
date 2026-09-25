"""Analysis-only GNSS horizontal-position integrity decisions.

Only receiver-native position, velocity, validity, and quality enter this plan.
No return-to-origin or recorded KF state is an input.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

import numpy as np

from silverstar_flp.analysis.gnss_integrity import GnssIntegrity_Build, GnssIntegrityResult
from silverstar_flp.core.dataset import FlightDataset


class IntegrityState(StrEnum):
    TRUSTED = "TRUSTED"
    SUSPECT = "SUSPECT"
    UNTRUSTED = "UNTRUSTED"
    RECOVERING = "RECOVERING"


@dataclass(frozen=True, slots=True)
class IntegrityConfig:
    window_s: int = 5
    rolling_threshold_m: float = 7.0
    anchored_threshold_m: float = 15.0
    suspect_duration_s: float = 2.0
    untrusted_duration_s: float = 5.0
    recovery_duration_s: float = 8.0
    integrity_scale: float = 4.0
    hacc_max_m: float = 6.0
    sacc_max_mps: float = 1.2
    recovery_rolling_m: float = 2.0
    recovery_local_closure_m: float = 2.0
    recovery_anchored_threshold_m: float = 8.0
    reanchor_min_distance_m: float = 8.0

    def __post_init__(self) -> None:
        if self.window_s not in (1, 2, 5, 10):
            raise ValueError("integrity_window_invalid")
        if any(value <= 0 or not np.isfinite(value) for value in (
            self.rolling_threshold_m, self.anchored_threshold_m,
            self.suspect_duration_s, self.untrusted_duration_s,
            self.recovery_duration_s, self.integrity_scale, self.hacc_max_m,
            self.sacc_max_mps, self.recovery_rolling_m,
            self.recovery_local_closure_m, self.recovery_anchored_threshold_m,
            self.reanchor_min_distance_m,
        )) or self.integrity_scale < 1:
            raise ValueError("integrity_parameter_invalid")


@dataclass(frozen=True, slots=True)
class IntegrityDecision:
    timestamp_us: int
    state: IntegrityState
    position_r_scale: float
    position_en_allowed: bool
    reanchor_ready: bool
    rolling_m: float
    anchored_m: float
    quality_valid: bool


@dataclass(frozen=True, slots=True)
class IntegrityPlan:
    decisions: Mapping[int, IntegrityDecision]
    transitions: tuple[tuple[int, IntegrityState], ...]
    config: IntegrityConfig
    closure: GnssIntegrityResult


def IntegrityDecisions_Build(
    closure: GnssIntegrityResult, sequences: np.ndarray,
    config: IntegrityConfig,
) -> IntegrityPlan:
    if len(sequences) != len(closure.timestamp_us):
        raise ValueError("integrity_sequence_count_mismatch")
    state = IntegrityState.TRUSTED
    abnormal_since: int | None = None
    suspect_since: int | None = None
    stable_since: int | None = None
    stable_anchor: np.ndarray | None = None
    recovering_since: int | None = None
    reference_lost = False
    transitions: list[tuple[int, IntegrityState]] = []
    decisions: dict[int, IntegrityDecision] = {}
    for index, timestamp in enumerate(closure.timestamp_us):
        now = int(timestamp)
        rolling = (float(np.linalg.norm(closure.residual_m[index, :2]))
                   if closure.valid_en[index] else np.nan)
        anchored = (float(np.linalg.norm(closure.anchored_residual_m[index, :2]))
                    if closure.anchored_valid_en[index] else np.nan)
        hacc = float(closure.quality[index, 0])
        sacc = float(closure.quality[index, 2])
        quality = bool(
            closure.anchored_valid_en[index]
            and np.isfinite(hacc) and 0 < hacc <= config.hacc_max_m
            and np.isfinite(sacc) and 0 < sacc <= config.sacc_max_mps
        )
        abnormal = quality and (
            (np.isfinite(rolling) and rolling > config.rolling_threshold_m)
            or (np.isfinite(anchored) and anchored > config.anchored_threshold_m)
        )
        if abnormal:
            if abnormal_since is None:
                abnormal_since = now
        else:
            abnormal_since = None
        reanchor_ready = False
        if state == IntegrityState.TRUSTED:
            if (abnormal_since is not None
                    and now - abnormal_since >= config.suspect_duration_s * 1e6):
                state = IntegrityState.SUSPECT
                suspect_since = now
                transitions.append((now, state))
        elif state == IntegrityState.SUSPECT:
            if not abnormal:
                state = IntegrityState.TRUSTED
                suspect_since = None
                transitions.append((now, state))
            elif (suspect_since is not None
                  and now - suspect_since >= config.untrusted_duration_s * 1e6):
                state = IntegrityState.UNTRUSTED
                stable_since = None
                stable_anchor = None
                reference_lost = False
                transitions.append((now, state))
        elif state == IntegrityState.UNTRUSTED:
            if closure.anchor_reset_en[index]:
                reference_lost = True
            stable = (not reference_lost and quality and np.isfinite(rolling)
                      and rolling <= config.recovery_rolling_m
                      and np.isfinite(anchored)
                      and anchored <= config.recovery_anchored_threshold_m)
            anchored_vector = closure.anchored_residual_m[index, :2]
            if stable and stable_since is None:
                stable_since = now
                stable_anchor = anchored_vector.copy()
            if stable and stable_anchor is not None:
                stable = bool(np.linalg.norm(anchored_vector - stable_anchor)
                              <= config.recovery_local_closure_m)
            if not stable:
                stable_since = None
                stable_anchor = None
            if stable_since is not None and now - stable_since >= config.recovery_duration_s * 1e6:
                state = IntegrityState.RECOVERING
                recovering_since = now
                reanchor_ready = True
                transitions.append((now, state))
        else:
            if (not quality or not np.isfinite(anchored)
                    or anchored > config.recovery_anchored_threshold_m
                    or (np.isfinite(rolling) and rolling > config.rolling_threshold_m)):
                state = IntegrityState.UNTRUSTED
                stable_since = None
                stable_anchor = None
                transitions.append((now, state))
            elif (recovering_since is not None
                  and now - recovering_since >= config.recovery_duration_s * 1e6):
                state = IntegrityState.TRUSTED
                abnormal_since = None
                transitions.append((now, state))
        if state == IntegrityState.SUSPECT:
            scale = config.integrity_scale
        elif state == IntegrityState.RECOVERING:
            progress = min(1.0, (now - (recovering_since or now)) /
                           (config.recovery_duration_s * 1e6))
            scale = 1.0 + (config.integrity_scale - 1.0) * (1.0 - progress)
        else:
            scale = 1.0
        sequence = int(sequences[index])
        decisions[sequence] = IntegrityDecision(
            now, state, scale, state != IntegrityState.UNTRUSTED,
            reanchor_ready, rolling, anchored, quality,
        )
    return IntegrityPlan(decisions, tuple(transitions), config, closure)


def IntegrityPlan_Build(dataset: FlightDataset, config: IntegrityConfig) -> IntegrityPlan:
    closure = GnssIntegrity_Build(dataset, config.window_s)
    records = dataset.Records_Get("GNSS_NATIVE")
    sequences = np.asarray(
        [int(row.payload.get("sequence", row.record_sequence)) for row in records],
        dtype=np.int64,
    )
    return IntegrityDecisions_Build(closure, sequences, config)
