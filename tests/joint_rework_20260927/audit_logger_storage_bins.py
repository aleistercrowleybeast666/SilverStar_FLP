"""Import actual LoggerBus/LoggerTask/codec/FatFs synthetic output, never relabel as flight."""
import hashlib
import json
from pathlib import Path
import shutil

from run_five_logs import Save
from silverstar_flp.decoder_profiles.discovery import DecoderProfileCache
from silverstar_flp.log_open import LogOpenCoordinator, LogOpenRequest
from silverstar_flp.plugins.registry import builtin_registry
from silverstar_flp.plugins.api.algorithm import ReplayRequest
from silverstar_flp.export.service import FlightExporter, ExportOptions, ExportLanguage

ROOT=Path(__file__).resolve().parent
FCCG=Path('D:/python_software/SilverStar_FCCG/tests/joint_rework_20260927')


def Run():
    results=[]
    for project_name in ('eskf_final','eskf_test_final'):
        project=FCCG/project_name
        source=project/'build/FCCG/Host/Tests/StorageIntegrity/logger-startup-burst.sslog'
        decoder=next(project.glob('*.ssdecoder'))
        output=ROOT/'logger_storage_import'/project_name
        output.mkdir(parents=True,exist_ok=True)
        source_hash=hashlib.sha256(source.read_bytes()).hexdigest()
        decoder_hash=hashlib.sha256(decoder.read_bytes()).hexdigest()
        captured=output/'SYNTHETIC_LOGGER_FATFS.sslog'
        captured_decoder=output/decoder.name
        shutil.copy2(source,captured)
        shutil.copy2(decoder,captured_decoder)
        assert hashlib.sha256(captured.read_bytes()).hexdigest()==source_hash
        assert hashlib.sha256(captured_decoder.read_bytes()).hexdigest()==decoder_hash
        row={'project':project_name,'producer':'actual LoggerBus/LoggerTask/SSLOG/FatFs throughput fixture',
            'source_path':str(source),'source_bytes':source.stat().st_size,'source_sha256':source_hash,
            'decoder_sha256':decoder_hash,'fixture_scope':'synthetic marker payloads, not ESKF numerical output; no FAITHFUL claim permitted'}
        registry=builtin_registry()
        try:
            dataset=LogOpenCoordinator(registry,cache=DecoderProfileCache(output/'cache')).Open(
                LogOpenRequest(log_path=captured,decoder_package_path=captured_decoder)).dataset
            row['import_status']='completed'
            row['data_quality']=dataset.data_quality.ToDict()
            row['records']={name:len(items) for name,items in dataset.records.items()}
            plugin=registry.Algorithm_Get('silverstar.algorithm.estimator.eskf15')
            try:
                result=plugin.run(dataset,ReplayRequest())
                row['replay_status']='completed'
                row['replay_fidelity']=result.fidelity.value
                row['missing_inputs']=result.missing_inputs
                row['warnings']=result.warnings
                row['recorded_parity']=result.diagnostics.get('recorded_parity')
                assert result.diagnostics.get('replay_claim')!='FAITHFUL','synthetic marker payload cannot claim faithful numerical parity'
            except Exception as error:
                row['replay_status']='rejected'
                row['replay_error']=type(error).__name__+':'+str(error)
            try:
                export_dir=output/'export'
                if export_dir.exists():
                    export_dir=output/('export_'+source_hash[:12])
                manifest=FlightExporter(registry).export(dataset,export_dir,options=ExportOptions(
                    language=ExportLanguage.EN,include_overview=True,include_diagnostics=True,
                    include_events=True,include_csv=False,include_plots=False,
                    include_full_covariance_keyframes=False,include_trajectory_3d=False,include_attitude_gif=False))
                row['export_files']=[str(path.relative_to(output)) for path in manifest.files]
                row['export_failures']=[str(failure) for failure in manifest.failures]
            except Exception as error:
                row['export_error']=type(error).__name__+':'+str(error)
        except Exception as error:
            row['import_status']='rejected'
            row['import_error']=type(error).__name__+':'+str(error)
        row['source_and_decoder_unchanged']=(hashlib.sha256(source.read_bytes()).hexdigest()==source_hash
            and hashlib.sha256(decoder.read_bytes()).hexdigest()==decoder_hash)
        assert row['source_and_decoder_unchanged']
        Save(output/'import_report.json',row)
        results.append(row)
        print(project_name,row['import_status'],row.get('replay_error'),flush=True)
    Save(ROOT/'evidence_final/logger_storage_import.json',results)


if __name__=='__main__':
    Run()
