"""Read saved numerical results and immutable exact logs; never tune or repair inputs."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt
import numpy as np

from run_five_logs import (ROOT, INPUT, EXPECTED, Save, LogOpenCoordinator,
    LogOpenRequest, DecoderProfileCache, builtin_registry)
from silverstar_flp.analysis.navigation_revision3 import Revision3Health_Build


def Read(path):
    return json.loads(path.read_text(encoding='utf8'))


def Build():
    output = ROOT / 'four_way_comparison'
    output.mkdir(exist_ok=True)
    coordinator = LogOpenCoordinator(builtin_registry(), cache=DecoderProfileCache(ROOT / 'cache'))
    decoder = INPUT / 'HARDWARE/SS_0_5_TEST_3.ssdecoder'
    decoder_hash = hashlib.sha256(decoder.read_bytes()).hexdigest()
    summary = []
    for index, expected in enumerate(EXPECTED):
        name = f'SS{index:04d}'
        folder = output / name
        folder.mkdir(exist_ok=True)
        log = INPUT / 'LOG' / (name + '.BIN')
        assert hashlib.sha256(log.read_bytes()).hexdigest() == expected
        dataset = coordinator.Open(LogOpenRequest(log_path=log, decoder_package_path=decoder)).dataset
        old = Read(ROOT / 'five_logs' / name / 'report.json')
        revised = Read(ROOT / 'five_logs_kf6_rev3' / name / 'report.json')
        eskf = Read(ROOT / 'five_logs_contract_final' / name / 'acceptance_metrics.json')
        c = revised['runs']['kf6_revision3_what_if']
        b = old['runs']['legacy_kf6']
        report = {'source': name, 'source_sha256': expected, 'decoder_sha256': decoder_hash,
            'data_quality': old['data_quality'], 'initial_state': old['initial_state'],
            'A_recorded_endpoint_enu_m': old.get('recorded_endpoint_enu_m'),
            'B_legacy_kf6': {k: b.get(k) for k in ('status','error','fidelity','endpoint_enu_m','final_velocity_enu_mps')},
            'C_revision3_kf6': {k: c.get(k) for k in ('status','error','fidelity','endpoint_enu_m','final_velocity_enu_mps','elapsed_s')},
            'D_eskf15': eskf,
            'interpretation': 'No external truth; endpoints are outputs, not accuracy. All new algorithms on these old logs are approximate What-if.',
            'C_scope': 'New physical/quality/window variance and outer fusion health; retained recorded operation/resolved-time schedule. Missing old operations are not fabricated.',
            'new_quality_parameters': 'Four active window parameters; six revision-2 values retained as inactive legacy snapshot. Saved runs use unchanged 120ms/10m/cap4 defaults.',
            'imu_evidence': 'Legacy logs lack actual range/readback/clipping flags; no saturation or hardware qualification inferred.'}
        if c['status'] != 'failed':
            data = np.load(ROOT / 'five_logs_kf6_rev3' / name / 'kf6_revision3_what_if_all_channels.npz')
            times = data['navigation.position_enu__time_us']
            diagnostics = deepcopy(c['diagnostics'])
            for row in diagnostics['gnss_group_updates']:
                if row.get('nis') is None:
                    row['nis'] = float('nan')
            for row in diagnostics['measurement_events']:
                row['effective_variance'] = np.asarray(row['effective_variance'], dtype=float)
            health, facts = Revision3Health_Build(times, diagnostics['gnss_group_updates'],
                diagnostics['measurement_events'], int(times[0]))
            facts.update({'final_health': int(health.values[-1]),
                'health_counts': {str(int(k)): int(v) for k,v in zip(*np.unique(health.values,return_counts=True))},
                'first_health_us': {str(s): int(times[np.flatnonzero(health.values == s)[0]])
                    if np.any(health.values == s) else None for s in range(5)},
                'window_evidence': diagnostics['window_evidence'],
                'all_output_finite': c['output_all_finite'],
                'maximum_position_step_m': float(np.linalg.norm(np.diff(data['navigation.position_enu__values'],axis=0),axis=1).max()),
                'baro_accept_count': facts['fusion_groups'][4]['accepted'],
                'baro_reject_count': facts['fusion_groups'][4]['nis_rejected'],
                'reanchor_counts': diagnostics['reanchor_counts'],
                'execution_mismatches': diagnostics['execution_mismatches'],
                'diagnostics_derivation': 'Health computed from preserved outer-update outcomes; no numerical state recalculation or successful fusion inferred from receiver liveness.'})
            report['C_revision3_kf6']['acceptance'] = facts
            np.savez_compressed(folder / 'kf6_revision3_health.npz',timestamp_us=health.timestamp_us,health=health.values)
        plot, axes = plt.subplots(3,2,figsize=(13,10),constrained_layout=True)
        t0 = int(dataset.initial_state.timestamp_us)
        for label, source_folder, prefix in (
                ('A Recorded', None, None), ('B Legacy KF6', 'five_logs', 'legacy_kf6'),
                ('C Revised KF6','five_logs_kf6_rev3','kf6_revision3_what_if'),
                ('D ESKF15','five_logs_contract_final','eskf15_what_if')):
            data_path = ROOT / (source_folder or '') / name / ((prefix or '') + '_all_channels.npz')
            if source_folder and not data_path.exists():
                continue
            data = np.load(data_path) if source_folder else None
            for column, channel in enumerate(('navigation.position_enu','navigation.velocity_enu')):
                if source_folder:
                    times, values = data[channel+'__time_us'], data[channel+'__values']
                else:
                    series = dataset.Series_Get('kf6.recorded.'+channel)
                    if series is None: continue
                    times, values = series.timestamp_us, series.values
                for axis in range(3):
                    axes[axis,column].plot((times.astype(float)-t0)*1e-6, values[:,axis],label=label,linewidth=.8)
        for axis in range(3):
            for column, unit in enumerate(('m','m/s')):
                axes[axis,column].set(title=('Position ' if column==0 else 'Velocity ')+('E','N','U')[axis],xlabel='Time / s',ylabel=unit)
                axes[axis,column].grid(alpha=.25)
                axes[axis,column].legend(fontsize=7)
        plot.suptitle(name+' · Four preserved results; no external ground truth')
        plot.savefig(folder/'four_way_position_velocity.png',dpi=140)
        plt.close(plot)
        native = dataset.Records_Get('GNSS_NATIVE')
        baro = dataset.Records_Get('BARO_MEASUREMENT')
        plot,axes=plt.subplots(3,1,figsize=(12,8),constrained_layout=True)
        t=np.asarray([r.payload['sample_timestamp_us'] for r in native],dtype=float)
        for field,panel in [('satellite_count',axes[0]),('horizontal_accuracy_m',axes[1]),('speed_accuracy_mps',axes[1])]:
            panel.plot((t-t0)*1e-6,[r.payload[field] for r in native],label=field)
        axes[2].plot([(r.timestamp_us-t0)*1e-6 for r in baro],[r.payload['relative_altitude_m'] for r in baro],label='Recorded barometer relative altitude / m')
        for panel in axes:
            panel.legend();panel.grid(alpha=.25);panel.set_xlabel('Time / s')
        plot.suptitle(name+' · Original receiver quality and barometer context')
        plot.savefig(folder/'receiver_and_baro.png',dpi=140)
        plt.close(plot)
        assert hashlib.sha256(log.read_bytes()).hexdigest()==expected
        assert hashlib.sha256(decoder.read_bytes()).hexdigest()==decoder_hash
        report['source_and_decoder_unchanged']=True
        Save(folder/'comparison.json',report)
        lines=[f'# {name} 四组真实日志对比','',
            '所有输入与匹配 decoder 均只读且前后 SHA256 相同。无独立真值；末位置只是输出，不是误差。',
            '', '| 组 | 结果 | 末位置 ENU / m |','|---|---|---|',
            f"| A Recorded | 原始记录 | {report['A_recorded_endpoint_enu_m']} |",
            f"| B 旧版 KF6 | {b['status']}: {b.get('error','')} | {b.get('endpoint_enu_m')} |",
            f"| C 修复后 KF6 | {c['status']}: {c.get('error','')} | {c.get('endpoint_enu_m')} |",
            f"| D ESKF15 | {eskf['eskf15_status']}; 健康 {eskf['final_navigation_health']} | {eskf['eskf15_what_if_endpoint_enu_m']} |",'',
            'C 保留旧记录的操作及已解析时序，仅应用新物理/质量/窗口方差与外层有效融合监督；旧日志没有的操作不补造。C/D 均为 What-if，不能冒充新固件同版实飞。',
            'SS0002 缺 GNSS 原点造成的 KF 失败原样保留。SS0000/SS0002/SS0004 的 ESKF 长时间拒融与严重漂移仍为 INVALID，不能宣称性能通过。',
            '新 IMU 范围读回、饱和和质量标志在旧日志中缺失；原生 GNSS 绝对 iTOW 对齐证据不足。主机计算耗时不是 MCU 实时预算。','',
            '![全部四组位置与速度](four_way_position_velocity.png)','', '![原始接收机与气压输入](receiver_and_baro.png)','',
            f'ESKF 全部15维协方差、四元数、bias和融合组诊断见 ../../five_logs_contract_final/{name}/REPORT.md。',
            'C 健康与窗口逐证据见 comparison.json；原始完整数值结果保留在各自运行目录。','']
        (folder/'REPORT.md').write_text('\n'.join(lines),encoding='utf8')
        summary.append({'source':name,'source_sha256':expected,'B':report['B_legacy_kf6'],
                        'C':{k:v for k,v in report['C_revision3_kf6'].items() if k!='acceptance'},
                        'D_final_health':eskf['final_navigation_health'],'inputs_unchanged':True})
        print(name,'four-way report complete',flush=True)
    Save(output/'summary.json',summary)


if __name__=='__main__':
    Build()
