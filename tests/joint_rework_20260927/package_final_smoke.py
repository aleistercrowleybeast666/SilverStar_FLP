"""Offline wheel build and extracted-package GUI/plugin smoke, workspace-only."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = Path(__file__).resolve().parent / 'package_final'


def Run():
    OUTPUT.mkdir(exist_ok=True)
    stage = OUTPUT / 'source'
    stage.mkdir(exist_ok=True)
    for name in ('pyproject.toml', 'README.md'):
        shutil.copy2(ROOT / name, stage / name)
    shutil.copytree(ROOT / 'src', stage / 'src', dirs_exist_ok=True,
        ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '*.egg-info'))
    temporary = OUTPUT / 'temporary'
    temporary.mkdir(exist_ok=True)
    environment = dict(os.environ, TEMP=str(temporary), TMP=str(temporary),
        PYTHONDONTWRITEBYTECODE='1', QT_QPA_PLATFORM='offscreen')
    built = subprocess.run([sys.executable, '-m', 'pip', 'wheel', '--no-deps',
        '--no-build-isolation', '--no-cache-dir', '--no-index', '--wheel-dir', str(OUTPUT),
        str(stage)], capture_output=True, text=True, env=environment)
    (OUTPUT / 'build.log').write_text(built.stdout + built.stderr, encoding='utf8')
    assert built.returncode == 0, built.stdout + built.stderr
    wheel = next(OUTPUT.glob('silverstar_flp-0.0.5-*.whl'))
    unpacked = OUTPUT / 'unpacked'
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        assert 'silverstar_flp/plugins/algorithms/eskf15/navigation_v1.json' in names
        assert 'silverstar_flp/i18n/zh_CN.json' in names
        archive.extractall(unpacked)
    smoke = OUTPUT / 'gui_smoke.py'
    smoke.write_text('''from pathlib import Path
import json
from PySide6.QtCore import QSettings
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication
import silverstar_flp
from silverstar_flp.app.version import __version__
from silverstar_flp.plugins.registry import builtin_registry
from silverstar_flp.ui.main_window import MainWindow
root=Path(__file__).resolve().parent
assert Path(silverstar_flp.__file__).is_relative_to(root/'unpacked')
QSettings.setDefaultFormat(QSettings.Format.IniFormat)
for scope in (QSettings.Scope.UserScope,QSettings.Scope.SystemScope):
 QSettings.setPath(QSettings.Format.IniFormat,scope,str(root/'settings'))
app=QApplication([])
font_id=QFontDatabase.addApplicationFont('C:/Windows/Fonts/msyh.ttc')
assert font_id>=0
app.setFont(QFont(QFontDatabase.applicationFontFamilies(font_id)[0],10))
registry=builtin_registry()
plugin=registry.Algorithm_Get('silverstar.algorithm.estimator.eskf15')
assert plugin.metadata.plugin_id=='silverstar.algorithm.estimator.eskf15'
assert __version__=='0.0.5'
window=MainWindow(registry,language='zh_CN',theme='dark')
window.resize(1000,700)
window.show()
app.processEvents()
assert window.grab().save(str(root/'packaged_gui.png'))
window.close()
app.processEvents()
print(json.dumps({'version':__version__,'plugin':plugin.metadata.plugin_id,
 'package_path':str(Path(silverstar_flp.__file__))}))
''', encoding='utf8')
    environment['PYTHONPATH'] = str(unpacked)
    tested = subprocess.run([sys.executable, str(smoke)], capture_output=True, text=True,
        cwd=OUTPUT, env=environment)
    (OUTPUT / 'smoke.log').write_text(tested.stdout + tested.stderr, encoding='utf8')
    assert tested.returncode == 0, tested.stdout + tested.stderr
    result = dict(wheel=wheel.name, bytes=wheel.stat().st_size,
        sha256=hashlib.sha256(wheel.read_bytes()).hexdigest(),
        build_exit=built.returncode, smoke_exit=tested.returncode,
        runtime=json.loads(tested.stdout), scope='offline wheel extraction + offscreen GUI; no install or publish')
    (OUTPUT.parent / 'evidence_final/package_smoke.json').write_text(
        json.dumps(result, indent=2) + '\n', encoding='utf8')
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    Run()
