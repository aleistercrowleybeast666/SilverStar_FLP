"""Optional sibling integration gate: real generated C codec and numerical outputs.

Set SILVERSTAR_FCCG_GENERATED and SILVERSTAR_C_GOLDEN to explicit test artifacts.
The caller generates these with FCCG tests/joint_navigation_support.py; this test
never writes to that repository or claims validation of an actual flight log.
"""
import os
from pathlib import Path

import numpy as np
import pytest

from silverstar_flp.decoder_profiles.discovery import DecoderProfileCache
from silverstar_flp.log_open import LogOpenCoordinator, LogOpenRequest
from silverstar_flp.plugins.api.algorithm import ReplayFidelity, ReplayRequest
from silverstar_flp.plugins.registry import builtin_registry


def test_generated_c_log_exact_decoder_replay_and_mechanization(tmp_path):
    project = os.environ.get('SILVERSTAR_FCCG_GENERATED')
    log = os.environ.get('SILVERSTAR_C_GOLDEN')
    if not project or not log:
        pytest.skip('explicit FCCG generated project and C golden required')
    registry = builtin_registry()
    opened = LogOpenCoordinator(registry, cache=DecoderProfileCache(tmp_path / "cache")).Open(
        LogOpenRequest(
            log_path=Path(log), decoder_package_path=Path(project) / "JointContract.ssdecoder"
        )
    )
    dataset = opened.dataset
    assert dataset.diagnostics.header_crc_valid
    assert dataset.diagnostics.record_crc_failures == 0
    assert dataset.diagnostics.sequence_gap_count == 0
    assert dataset.diagnostics.unknown_record_type_count == 0
    assert not dataset.diagnostics.truncated_tail
    assert (
        not {"SAMPLE", "RAW_SENSOR", "IMU_NATIVE", "HW_QUAT_NATIVE", "PURE_INS"}
        & dataset.records.keys()
    )
    plugin = registry.Algorithm_Get('silverstar.algorithm.kf6')
    assert plugin.availability(dataset).available
    result = plugin.run(dataset, ReplayRequest())
    assert (
        result.fidelity == ReplayFidelity.APPROXIMATE
    )  # Bounded tested scope, no universal EXACT.
    assert not result.diagnostics['measurement_timing_inferred']
    assert not result.diagnostics['execution_mismatches']
    verification = result.diagnostics['mechanization_verification']
    assert verification['passed'] and verification['first_divergence'] is None
    assert verification['calibration_applied'] is False
    for role, name, field in [
        ('navigation.position_enu','ESTIMATOR','position_enu_m'),
        ('navigation.velocity_enu','ESTIMATOR','velocity_enu_mps'),
        ('attitude.q_nb','ESTIMATOR','q_nb'),
        ('kf6.covariance.upper_triangle','KF6_FULL_P','covariance_upper_triangle')]:
        actual = result.channels[role]
        expected = {r.timestamp_us:r.payload[field] for r in dataset.Records_Get(name)}
        np.testing.assert_allclose(actual.values, [expected[int(t)] for t in actual.timestamp_us],
                                   rtol=1e-6, atol=5e-7)
