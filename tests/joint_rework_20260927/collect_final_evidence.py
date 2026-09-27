"""Collect compact reproducible evidence; leave large numerical caches local."""
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEST = ROOT / 'evidence_final'


def Run():
    DEST.mkdir(exist_ok=True)
    for name in ('final_complete.log', 'ruff_complete.log', 'compile_complete.log',
                 'diff_complete.log', 'actual_backend_logger_gui2.log', 'package_final.log',
                 'transaction_delta.log',
                 'runtime_parameters3.log', 'retired_flp2.log', 'four_way_report.log'):
        shutil.copy2(ROOT / name, DEST / name)
    final = ROOT / 'final_complete_temp'
    for pattern, target in (
        ('test_actual_c_float32_against_0/parity.json', 'c_python_parity.json'),
        ('test_actual_c_mid_interval_del0/delayed_parity.json', 'delayed_100hz.json'),
        ('test_actual_c_mid_interval_del1/delayed_parity.json', 'delayed_250hz.json'),
        ('test_actual_c_windows_gaps_dup0/window_parity.json', 'window_parity.json')):
        shutil.copy2(final / pattern, DEST / target)
    for index, name in enumerate(('ordered', 'interleaved')):
        shutil.copy2(ROOT / 'transaction_delta_temp' / f'test_actual_c_producer_exact_d{index}' / 'golden_result.json',
                     DEST / f'golden_{name}.json')
    transaction = next((ROOT / 'transaction_delta_temp').glob(
        'test_multiple_prefix_commit_an*/transaction_boundaries.json'))
    shutil.copy2(transaction, DEST / 'transaction_boundaries.json')
    for index, name in enumerate(('velocity_bias', 'position_drift')):
        shutil.copy2(final / f'test_long_causal_native_counte{index}' / (name + '.json'),
            DEST / (name + '.json'))
    for name in ('actual_body_bias_en_US_light.png', 'actual_body_bias_zh_CN_dark.png'):
        shutil.copy2(ROOT / 'actual_backend_logger' / name, DEST / name)
    shutil.copy2(ROOT / 'package_final/packaged_gui.png', DEST / 'packaged_gui.png')
    for path in (final / 'test_real_eskf_bias_gui_and_fr0').glob('eskf15_bias_*.png'):
        shutil.copy2(path, DEST / path.name)
    shutil.copy2(ROOT / 'five_logs_contract_final/final_policy_equivalence.json', DEST / 'final_policy_equivalence.json')
    manifest = []
    for folder in ('five_logs', 'five_logs_contract_final', 'five_logs_kf6_rev3'):
        for path in sorted((ROOT / folder).glob('SS*/*')):
            if path.suffix not in ('.npz', '.json'):
                continue
            manifest.append({'path': str(path.relative_to(ROOT)).replace('\\', '/'),
                'bytes': path.stat().st_size, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    for index in range(5):
        report = json.loads((ROOT / 'five_logs_kf6_rev3' / f'SS{index:04d}' / 'report.json').read_text(encoding='utf8'))
        run = report['runs']['kf6_revision3_what_if']
        if run['status'] != 'failed':
            p = run['parameters']
            assert (p['gnss_integrity_max_gap_ms'], p['gnss_integrity_error_threshold_m'],
                    p['gnss_integrity_position_r_scale']) == (120, 10.0, 4.0)
    (DEST / 'large_artifact_hashes.json').write_text(json.dumps(manifest, indent=2) + '\n',encoding='utf8')
    (DEST / 'README.md').write_text(
        '# Compact FLP software evidence\n\n'
        'All raw input and matching decoder hashes are preserved in the per-log reports. '
        'The final 426-pass full suite includes current source/C parity and both final '
        'C-codec arrival order cases. Nine unrelated manual fixtures '
        'were explicitly skipped because their required external inputs were absent.\n\n'
        'A later C-only prediction/history transaction fix passed a separate 20-test '
        'delta (18.82 s), including 600 ms rejection rollback, multiple-prefix commit, '
        '192-slot overflow and original math/window/delay/golden cases. No extra '
        'global/full-state storage was added. The full-suite result remains separately dated.\n\n'
        'All five four-way reports live at ../four_way_comparison/SS0000 through SS0004. '
        'All five ESKF 15-state diagnostic reports live at ../five_logs_contract_final/SS0000 '
        'through SS0004. Numerical NPZ/run JSON files are kept locally and hash-listed here; '
        'do not add temporary builds, DLLs, executables, cache directories or raw BIN files.\n\n'
        'Final binding of max-gap/threshold/cap uses the same explicit 120 ms / 10 m / 4 values '
        'stored in every completed C replay. The retirement patch does not change those '
        'numerical inputs. The independent parameter-effect regression demonstrates all '
        'three values really affect new-policy windows.\n\n'
        'actual_backend_logger.json records a separate actual production backend/LoggerBus/'
        'LoggerTask closed loop: 491 records, exact decoder, FAITHFUL numeric comparison, '
        '361 exported files and zero export failures. Two unavailable legacy corrected-IMU '
        'plots are explicitly skipped. Its synthetic host sink is not a target FatFs timing test. '
        'Initial complete covariance is mandatory; Flight explicitly disabled periodic '
        'covariance is reported unavailable. Unattempted numeric diagnostics are unavailable '
        'only after exact admission and result comparison.\n\n'
        'Package smoke builds 0.0.5 offline and loads the wheel extraction, plugin and '
        'contract/translation resources; no install or publication. Offscreen screenshots '
        'load the existing Windows Chinese font and are not physical-display certification.\n\n'
        'These are software fixtures and old-log What-if analyses, not hardware or flight '
        'acceptance. SS0002 origin failures and SS0000/2/4 ESKF INVALID results remain visible.\n',
        encoding='utf8')
    print('compact evidence files:', len(list(DEST.iterdir())), flush=True)


if __name__ == '__main__':
    Run()
