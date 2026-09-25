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
    reference_max_age_s: float = 30.0
    velocity_bias_bound_mps: float = 0.15
    reference_renewal_max_m: float = 2.0
    evidence_max_age_ms: int = 550
    max_gap_ms: int = 120
    recovery_min_samples: int = 25

    def __post_init__(self) -> None:
        if self.window_s not in (1, 2, 5, 10):
            raise ValueError("integrity_window_invalid")
        if any(value <= 0 or not np.isfinite(value) for value in (
            self.rolling_threshold_m, self.anchored_threshold_m,
            self.suspect_duration_s, self.untrusted_duration_s,
            self.recovery_duration_s, self.integrity_scale, self.hacc_max_m,
            self.sacc_max_mps, self.recovery_rolling_m,
            self.recovery_local_closure_m, self.recovery_anchored_threshold_m,
            self.reanchor_min_distance_m, self.reference_max_age_s,
            self.velocity_bias_bound_mps, self.reference_renewal_max_m,
            self.evidence_max_age_ms,
            self.max_gap_ms, self.recovery_min_samples,
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
    evidence_valid: bool = False
    evidence_cutoff_us: int = 0
    evidence_age_us: int = 0
    reason: str = "unavailable"
    reference_generation: int = 0


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
    """Consume each received epoch once; no future samples or KF output enter evidence."""
    if len(sequences) != len(closure.timestamp_us):
        raise ValueError("integrity_sequence_count_mismatch")
    state = IntegrityState.TRUSTED
    abnormal_us = 0
    healthy_us = 0
    recovery_us = 0
    healthy_count = 0
    previous_us: int | None = None
    reference_us: int | None = None
    reference_generation = 0
    reference_trusted = False
    reference_baseline = np.zeros(2, dtype=np.float64)
    transitions: list[tuple[int, IntegrityState]] = []
    decisions: dict[int, IntegrityDecision] = {}
    for index, timestamp in enumerate(closure.timestamp_us):
        now = int(timestamp)
        cutoff = (int(closure.evidence_cutoff_us[index])
                  if closure.evidence_cutoff_us is not None else now)
        age_us = now - cutoff
        rolling = (float(np.linalg.norm(closure.residual_m[index, :2]))
                   if closure.valid_en[index] else np.nan)
        anchored_vector = closure.anchored_residual_m[index, :2]
        anchored = (float(np.linalg.norm(anchored_vector - reference_baseline))
                    if closure.anchored_valid_en[index] else np.nan)
        hacc = float(closure.quality[index, 0])
        sacc = float(closure.quality[index, 2])
        quality = bool(
            np.isfinite(hacc) and 0 < hacc <= config.hacc_max_m
            and np.isfinite(sacc) and 0 < sacc <= config.sacc_max_mps
        )
        generation = (int(closure.segment_en[index])
                      if closure.segment_en is not None else 1)
        if closure.anchor_reset_en[index] or (
                index == 0 and closure.anchored_valid_en[index]
                and reference_us is None):
            reference_us = cutoff
            reference_generation = generation
            reference_trusted = state == IntegrityState.TRUSTED
            reference_baseline = np.zeros(2, dtype=np.float64)
        if generation != reference_generation:
            reference_trusted = False
        reference_age_s = ((cutoff - reference_us) * 1e-6
                           if reference_us is not None else np.inf)
        if reference_age_s > config.reference_max_age_s:
            renewable = bool(
                state == IntegrityState.TRUSTED and reference_trusted
                and np.isfinite(anchored) and anchored <= config.reference_renewal_max_m
                and np.isfinite(rolling) and rolling <= config.recovery_rolling_m
            )
            if renewable:
                reference_baseline = anchored_vector.copy()
                reference_us = cutoff
                reference_age_s = 0.0
                anchored = 0.0
            else:
                reference_trusted = False
                if state == IntegrityState.TRUSTED:
                    state = IntegrityState.SUSPECT
                    transitions.append((now, state))
        rolling_valid = bool(np.isfinite(rolling))
        anchored_valid = bool(np.isfinite(anchored) and reference_trusted)
        evidence_valid = bool(
            quality and rolling_valid and 0 <= age_us <= config.evidence_max_age_ms * 1000
        )
        anchored_limit = (config.anchored_threshold_m
                          + config.velocity_bias_bound_mps * reference_age_s)
        abnormal = bool(evidence_valid and (
            rolling > config.rolling_threshold_m
            or (anchored_valid and anchored > anchored_limit)
        ))
        recovery_healthy = bool(
            evidence_valid and rolling <= config.recovery_rolling_m
            and anchored_valid and anchored <= config.recovery_anchored_threshold_m
        )
        delta_us = 0 if previous_us is None else now - previous_us
        contiguous = 0 < delta_us <= config.max_gap_ms * 1000
        previous_us = now
        if evidence_valid and contiguous:
            if abnormal:
                abnormal_us += delta_us
                healthy_us = 0
            elif recovery_healthy:
                healthy_us += delta_us
                abnormal_us = 0
            else:
                abnormal_us = 0
                healthy_us = 0
        elif evidence_valid:
            abnormal_us = 0
            healthy_us = 0
        # Missing/poor evidence is never a healthy vote. Pause both timers.
        if recovery_healthy:
            healthy_count += 1
            if contiguous:
                recovery_us += delta_us
        elif evidence_valid:
            healthy_count = 0
            recovery_us = 0
        reanchor_ready = False
        if state == IntegrityState.TRUSTED:
            if abnormal_us >= int(config.suspect_duration_s * 1_000_000):
                state = IntegrityState.SUSPECT
                transitions.append((now, state))
        elif state == IntegrityState.SUSPECT:
            if abnormal_us >= int((config.suspect_duration_s
                                   + config.untrusted_duration_s) * 1_000_000):
                state = IntegrityState.UNTRUSTED
                transitions.append((now, state))
            elif healthy_us >= int(config.suspect_duration_s * 1_000_000):
                state = IntegrityState.TRUSTED
                transitions.append((now, state))
        elif state == IntegrityState.UNTRUSTED:
            if (recovery_healthy
                    and healthy_count >= config.recovery_min_samples
                    and recovery_us >= int(config.recovery_duration_s * 1_000_000)):
                state = IntegrityState.RECOVERING
                recovery_us = 0
                healthy_count = 0
                reanchor_ready = True
                transitions.append((now, state))
        else:
            if abnormal:
                state = IntegrityState.UNTRUSTED
                recovery_us = 0
                healthy_count = 0
                transitions.append((now, state))
            elif (recovery_healthy
                  and healthy_count >= config.recovery_min_samples
                  and recovery_us >= int(config.recovery_duration_s * 1_000_000)):
                state = IntegrityState.TRUSTED
                transitions.append((now, state))
        if not quality:
            reason = "quality_unavailable"
        elif age_us < 0 or age_us > config.evidence_max_age_ms * 1000:
            reason = "evidence_age"
        elif not rolling_valid:
            reason = (closure.rolling_reason_en[index]
                      if closure.rolling_reason_en else "window_unavailable")
        elif not anchored_valid:
            reason = "reference_untrusted_or_expired"
        elif abnormal:
            reason = "closure_abnormal"
        else:
            reason = "healthy_evidence"
        scale = config.integrity_scale if state in (
            IntegrityState.SUSPECT, IntegrityState.RECOVERING,
        ) else 1.0
        sequence = int(sequences[index])
        if sequence in decisions:
            raise ValueError("integrity_sequence_duplicate")
        decisions[sequence] = IntegrityDecision(
            now, state, scale, state != IntegrityState.UNTRUSTED,
            reanchor_ready, rolling, anchored, quality,
            evidence_valid, cutoff, age_us, reason, generation,
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
