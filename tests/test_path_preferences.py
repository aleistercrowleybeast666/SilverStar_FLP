import json
from pathlib import Path

from PySide6.QtWidgets import QApplication

from silverstar_flp.core.i18n import Translator
from silverstar_flp.core.path_preferences import ExportDirectory_Default, PathPreferences
from silverstar_flp.core.project import ProjectDocument
from silverstar_flp.plugins.registry import builtin_registry
from silverstar_flp.ui.main_window import MainWindow
from silverstar_flp.ui.new_project import NewProjectDialog
from silverstar_flp.ui.pages.export_settings import ExportDialog, ImportDialog


def test_json_roundtrip_corruption_and_nonexistent_root(tmp_path):
    store = PathPreferences(tmp_path / "settings/path_preferences.json")
    assert store.DefaultProjectRoot_Get() is None
    root = tmp_path / "中文 空格"
    root.mkdir()
    store.DefaultProjectRoot_Set(root)
    assert store.DefaultProjectRoot_Get() == root
    assert "中文" in store.path.read_text(encoding="utf-8")
    for document in (
        "{",
        "null",
        "[]",
        json.dumps({"schema_version": 1, "default_project_root": str(root / "missing")}),
    ):
        store.path.write_text(document, encoding="utf-8")
        assert store.DefaultProjectRoot_Get() is None
    assert not (root / "missing").exists()


def test_auto_directory_custom_edit_and_browse(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    dialog = NewProjectDialog(Translator("zh_CN"), tmp_path)
    dialog.name_edit.setText("试验 一")
    assert dialog.Path_Get() == tmp_path / "试验 一" / "试验 一.ssflp"
    dialog.name_edit.setText("二.ssflp")
    assert dialog.Path_Get() == tmp_path / "二" / "二.ssflp"
    custom = tmp_path / "custom"
    custom.mkdir()
    dialog.directory_edit.setText(str(custom))
    dialog.directory_edit.textEdited.emit(str(custom))
    dialog.name_edit.setText("三")
    assert dialog.Path_Get() == custom / "三.ssflp"
    calls = []

    def select(*args):
        calls.append(args[2])
        return str(tmp_path)

    monkeypatch.setattr("silverstar_flp.ui.new_project.QFileDialog.getExistingDirectory", select)
    dialog._Directory_Select()
    dialog.name_edit.setText("四")
    assert Path(calls[0]) == custom
    assert dialog.Path_Get() == tmp_path / "四.ssflp"
    app.processEvents()
    dialog.close()


def test_import_follows_current_project_and_manual_mode_survives_translation(tmp_path):
    app = QApplication.instance() or QApplication([])
    store = PathPreferences(tmp_path / "preferences.json")
    store.DefaultProjectRoot_Set(tmp_path)
    window = MainWindow(builtin_registry(), path_preferences=store)
    assert window.import_dialog.source_type_combo.currentData() == "folder_search"
    assert window._ImportDirectory_Get() == tmp_path
    for name in ("工程 一", "工程 二"):
        directory = tmp_path / name
        directory.mkdir()
        window._project = ProjectDocument(project_path=directory / (name + ".ssflp"))
        window._ImportDialog_Show()
        assert Path(window.import_dialog.folder_path_edit.text()) == directory
        window.import_dialog.reject()
    dialog = ImportDialog(Translator("en_US"))
    dialog.source_type_combo.setCurrentIndex(dialog.source_type_combo.findData("manual"))
    dialog.Language_Apply(Translator("zh_CN"))
    assert dialog.source_type_combo.currentData() == "manual"
    window._Project_SetDirty(False)
    window.close()
    app.processEvents()


def test_result_names_collision_and_manual_destination(tmp_path):
    app = QApplication.instance() or QApplication([])
    for name, expected in (
        ("SS0005.BIN", "Result_SS0005"),
        ("中文 日志 (1).sSlOg", "Result_中文 日志 (1)"),
        ("bad?name.BIN", "Result_bad_name"),
    ):
        result = ExportDirectory_Default(tmp_path / name)
        assert result.name == expected
        result.mkdir()
        sentinel = result / "existing.txt"
        sentinel.write_text("preserve")
        assert ExportDirectory_Default(tmp_path / name).name == expected + "_2"
        assert sentinel.read_text() == "preserve"
    dialog = ExportDialog(Translator("en_US"))
    dialog.OutputDirectory_Set(tmp_path / "automatic")
    dialog.folder_edit.setText(str(tmp_path / "manual"))
    dialog.folder_edit.textEdited.emit(dialog.folder_edit.text())
    dialog.OutputDirectory_Set(tmp_path / "next")
    assert Path(dialog.folder_edit.text()) == tmp_path / "manual"
    dialog.close()
    app.processEvents()
