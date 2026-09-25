from __future__ import annotations

import numpy as np

from silverstar_flp.analysis.gnss_integrity import GnssIntegrityResult
from silverstar_flp.analysis.integrity_assistance import (
    IntegrityConfig,
    IntegrityDecisions_Build,
    IntegrityState,
)
from silverstar_flp.plugins.algorithms.kf6.fixed_lag import (
    FixedLagReplay,
    ReplayEvent,
    ReplayResult,
)
from tests.test_fixed_lag_contract import state_create


def _Closure(rolling, anchored, *, sacc=None, resets=()):
    count = len(rolling)
    time = np.arange(count, dtype=np.int64) * 1_000_000 + 1_000_000
    residual = np.column_stack((rolling, np.zeros(count), np.zeros(count)))
    anchored_residual = np.column_stack((anchored, np.zeros(count), np.zeros(count)))
    quality = np.column_stack((
        np.full(count, 2.0), np.full(count, 3.0),
        np.full(count, .4) if sacc is None else np.asarray(sacc),
        np.full(count, 12.0),
    ))
    anchor_reset = np.zeros(count, dtype=np.bool_)
    anchor_reset[list(resets)] = True
    return GnssIntegrityResult(
        5, time, residual, residual, residual,
        np.ones(count, dtype=np.bool_), np.ones(count, dtype=np.bool_),
        anchored_residual, np.ones(count, dtype=np.bool_),
        np.ones(count, dtype=np.bool_), anchor_reset,
        np.zeros(count, dtype=np.bool_), quality, {},
    )


def _Plan(rolling, anchored, **kwargs):
    result = _Closure(rolling, anchored, **kwargs)
    return IntegrityDecisions_Build(result, np.arange(len(rolling)), IntegrityConfig())


def test_clean_remains_trusted_and_single_spike_cannot_disable():
    clean = _Plan(np.full(100, .5), np.full(100, 1.0))
    assert not clean.transitions
    assert all(row.state == IntegrityState.TRUSTED for row in clean.decisions.values())
    rolling = np.full(100, .5)
    anchored = np.full(100, 1.0)
    anchored[20] = 30.0
    spike = _Plan(rolling, anchored)
    assert all(row.position_en_allowed for row in spike.decisions.values())


def test_slow_position_drift_suspect_then_untrusted_without_chatter():
    anchored = np.minimum(np.arange(100, dtype=float), 30.0)
    plan = _Plan(np.full(100, 1.0), anchored)
    assert [state for _, state in plan.transitions] == [
        IntegrityState.SUSPECT, IntegrityState.UNTRUSTED,
    ]
    assert not plan.decisions[90].position_en_allowed
    assert plan.decisions[90].position_r_scale == 1.0


def test_bad_velocity_quality_cannot_blame_position_or_u():
    count = 60
    plan = _Plan(np.full(count, 20.0), np.full(count, 30.0),
                 sacc=np.full(count, 3.0))
    assert not plan.transitions
    result = _Closure(np.full(count, .5), np.full(count, 1.0))
    # A vertical-only anomaly never enters the horizontal decision inputs.
    result.residual_m[:, 2] = 1000.0
    plan = IntegrityDecisions_Build(result, np.arange(count), IntegrityConfig())
    assert not plan.transitions


def test_temporary_multipath_recovers_and_reanchor_ready_once():
    anchored = np.r_[np.arange(30, dtype=float), np.full(14, 30.0),
                     np.zeros(30)]
    rolling = np.r_[np.full(44, 1.0), np.full(30, .5)]
    plan = _Plan(rolling, anchored)
    states = [state for _, state in plan.transitions]
    assert states == [IntegrityState.SUSPECT, IntegrityState.UNTRUSTED,
                      IntegrityState.RECOVERING, IntegrityState.TRUSTED]
    assert sum(row.reanchor_ready for row in plan.decisions.values()) == 1
    assert plan.decisions[len(anchored) - 1].position_en_allowed
    gap = _Plan(rolling, anchored, resets=(44,))
    assert IntegrityState.RECOVERING not in [state for _, state in gap.transitions]


def test_controlled_reanchor_changes_only_horizontal_position_and_covariance_block():
    replay = FixedLagReplay(state_create(), timestamp_us=100_000)
    replay.state.state[:] = (1, 2, 3, 4, 5, 6)
    before_state = replay.state.state.copy()
    before_covariance = replay.state.covariance.copy()
    event = ReplayEvent(
        100_000, 100_000, 1, 8, 1,
        {"target_position_en": (20.0, -10.0), "target_variance_en": (4.0, 9.0)},
    )
    assert replay.Insert(event) == ReplayResult.OK
    np.testing.assert_array_equal(replay.state.state[:2], (20.0, -10.0))
    np.testing.assert_array_equal(replay.state.state[2:], before_state[2:])
    np.testing.assert_array_equal(replay.state.covariance[2:, 2:], before_covariance[2:, 2:])
    np.testing.assert_array_equal(replay.state.covariance[:2, 2:], 0.0)
    np.testing.assert_array_equal(replay.state.covariance[2:, :2], 0.0)
    assert np.linalg.eigvalsh(replay.state.covariance).min() > 0.0
