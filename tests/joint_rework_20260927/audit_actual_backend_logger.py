"""Run the unmodified actual backend/LoggerTask Test output through FLP products."""
from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from run_five_logs import Save
from silverstar_flp.core.analysis_source import ReplayResultStore
from silverstar_flp.decoder_profiles.discovery import DecoderProfileCache
from silverstar_flp.export.service import ExportLanguage, ExportOptions, FlightExporter
from silverstar_flp.log_open import LogOpenCoordinator, LogOpenRequest
from silverstar_flp.plugins.api.algorithm import ReplayRequest
from silverstar_flp.plugins.registry import builtin_registry

ROOT = Path(__file__).resolve().parent
PROJECT = Path('D:/python_software/SilverStar_FCCG/tests/joint_rework_20260927/backend_bridge_test')


def Run():
    source = PROJECT / 'build/FCCG/Host/BackendBridge/actual_backend_logger.BIN'
    decoder = PROJECT / 'ActualBackendLoggerBridgeTest.ssdecoder'
    output = ROOT / 'actual_backend_logger'
    output.mkdir(exist_ok=True)
    hashes = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in (source, decoder)}
    for path in (source, decoder):
        shutil.copy2(path, output / path.name)
    row = {
        'producer': 'actual ESKF backend -> LoggerBus -> LoggerTask RecordAppend/Flush -> host fwrite/fflush sink',
        'scope': 'synthetic host input/clock; real NONE calibration, generated descriptor, header, core and logger; FatFs/DMA timing tested separately',
        'hashes_before': hashes,
        'source_paths': [str(source), str(decoder)],
        'source_sizes': {path.name: path.stat().st_size for path in (source, decoder)},
    }
    registry = builtin_registry()
    try:
        dataset = LogOpenCoordinator(registry, cache=DecoderProfileCache(output / 'cache')).Open(
            LogOpenRequest(log_path=output / source.name, decoder_package_path=output / decoder.name)
        ).dataset
        row['import_status'] = 'completed'
        row['data_quality'] = dataset.data_quality.ToDict()
        row['record_counts'] = {name: len(records) for name, records in dataset.records.items()}
        result = registry.Algorithm_Get('silverstar.algorithm.estimator.eskf15').run(dataset, ReplayRequest())
        row['replay_fidelity'] = result.fidelity.value
        row['replay_claim'] = result.diagnostics.get('replay_claim')
        row['missing_inputs'] = result.missing_inputs
        row['warnings'] = result.warnings
        row['recorded_parity'] = result.diagnostics.get('recorded_parity')
        row['replay_diagnostics'] = result.diagnostics
        store = ReplayResultStore()
        entry = store.Result_Add(result, algorithm_name='ESKF_15')
        from PySide6.QtGui import QFont, QFontDatabase
        from PySide6.QtWidgets import QApplication
        from silverstar_flp.core.analysis_source import ChannelResolver
        from silverstar_flp.core.i18n import Translator
        from silverstar_flp.ui.pages.state_estimation import StateEstimationPage
        from silverstar_flp.ui.theme import Theme_Apply
        application = QApplication.instance() or QApplication([])
        font_id = QFontDatabase.addApplicationFont('C:/Windows/Fonts/msyh.ttc')
        assert font_id >= 0
        application.setFont(QFont(QFontDatabase.applicationFontFamilies(font_id)[0], 10))
        assert store.ActiveSource_Set(entry.source_id)
        page = StateEstimationPage(Translator('en_US'), registry)
        page.Dataset_Set(dataset, ChannelResolver(dataset, store))
        page.resize(1000, 700)
        page.show()
        assert page.state_group_combo.count() == 5
        assert page.nis_measurement_combo.count() == 5
        page.state_group_combo.setCurrentIndex(page.state_group_combo.findData('gyro_bias'))
        row['gui_snapshots'] = []
        for language, theme in (('en_US', 'light'), ('zh_CN', 'dark')):
            Theme_Apply(application, theme)
            page.Theme_Apply(theme)
            page.Language_Apply(Translator(language))
            application.processEvents()
            assert len(page.state_estimate_plot.listDataItems()) == 6, 'recorded plus replay bias XYZ'
            assert len(page.covariance_plot.listDataItems()) == 6, 'recorded plus replay bias sigma XYZ'
            image_path = output / ('actual_body_bias_' + language + '_' + theme + '.png')
            assert page.grab().save(str(image_path))
            row['gui_snapshots'].append(str(image_path.relative_to(output)))
        page.close()
        export = output / ('export_' + hashes[source.name][:12])
        attempt = 0
        while export.exists():
            attempt += 1
            export = output / ('export_' + hashes[source.name][:12] + '_' + str(attempt))
        manifest = FlightExporter(registry).export(
            dataset, export, replay_store=store,
            options=ExportOptions(source_mode='explicit', source_id=entry.source_id,
                language=ExportLanguage.EN, include_overview=True, include_diagnostics=True,
                include_events=True, include_csv=True, include_plots=True,
                include_full_covariance_keyframes=True, include_trajectory_3d=False,
                include_attitude_gif=False))
        row['export_files'] = [str(path.relative_to(output)) for path in manifest.files]
        row['export_failures'] = [str(failure) for failure in manifest.failures]
        row['export_skipped'] = [str(skipped) for skipped in manifest.skipped]
    except Exception as error:
        import traceback
        row['traceback'] = traceback.format_exc()
        row['error'] = type(error).__name__ + ': ' + str(error)
    row['source_and_decoder_unchanged'] = all(
        hashlib.sha256(path.read_bytes()).hexdigest() == hashes[path.name] for path in (source, decoder))
    assert row['source_and_decoder_unchanged']
    Save(output / 'result.json', row)
    Save(ROOT / 'evidence_final/actual_backend_logger.json', row)
    print(row.get('import_status'), row.get('replay_claim'), row.get('error'), flush=True)
    print(row.get('recorded_parity'), flush=True)
    assert 'error' not in row, row.get('error')
    assert row['replay_claim'] == 'FAITHFUL', row.get('recorded_parity')
    assert not row['export_failures'], row['export_failures']


if __name__ == '__main__':
    Run()
