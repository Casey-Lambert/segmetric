"""Headless (QT_QPA_PLATFORM=offscreen) smoke tests for segmetric.set's
GUI wiring -- core logic (splitting/presets) has its own thorough tests;
this covers the integration points: browse-vs-manual sample entry, and
Save/Load Preset from manual entry alone (no folder ever browsed).
"""
import os

import cv2
import numpy as np
import pytest
from PyQt6.QtWidgets import QApplication, QMessageBox

from segmetric.set.gui.main_window import MainWindow


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    QMessageBox.information = staticmethod(lambda *a, **k: None)
    QMessageBox.critical = staticmethod(lambda *a, **k: None)
    QMessageBox.warning = staticmethod(lambda *a, **k: None)
    return app


def test_manual_entry_builds_the_same_table_a_real_file_would(qapp, tmp_path):
    stem = "H6_120HR_34C_NR_1004_RH"
    crops_dir = tmp_path / "crops"
    crops_dir.mkdir()
    cv2.imwrite(str(crops_dir / f"{stem}.png"), np.full((10, 10, 3), 200, dtype=np.uint8))

    browsed = MainWindow()
    browsed.on_browse_input = lambda: None  # would open a real QFileDialog otherwise
    browsed.input_folder = str(crops_dir)
    from segmetric.tag.core.discovery import find_input_files

    files = find_input_files(str(crops_dir))
    browsed._set_segments_from_text(files[0], os.path.basename(files[0]))

    typed = MainWindow()
    typed.manual_mode_radio.setChecked(True)
    typed.manual_name_edit.setText(stem)
    typed.on_manual_filename_changed()

    assert [(s.raw_value, s.column_name) for s in typed.segments] == [
        (s.raw_value, s.column_name) for s in browsed.segments
    ]


def test_manual_mode_toggle_swaps_the_visible_input_row(qapp):
    window = MainWindow()
    assert window.browse_form.isVisibleTo(window) is True
    assert window.manual_form.isVisibleTo(window) is False

    window.manual_mode_radio.setChecked(True)
    assert window.browse_form.isVisibleTo(window) is False
    assert window.manual_form.isVisibleTo(window) is True


def test_save_preset_succeeds_from_manual_entry_alone(qapp, tmp_path):
    window = MainWindow()
    window.manual_mode_radio.setChecked(True)
    window.manual_name_edit.setText("H6_120HR_RH")
    window.on_manual_filename_changed()
    window.preset_name_edit.setText("ManualPreset")

    save_path = tmp_path / "preset.json"
    from PyQt6.QtWidgets import QFileDialog

    original_get_save = QFileDialog.getSaveFileName
    QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (str(save_path), ""))
    try:
        window.on_save_preset()
    finally:
        QFileDialog.getSaveFileName = original_get_save

    assert save_path.exists()

    from segmetric.set.core.presets import load_preset

    loaded = load_preset(str(save_path))
    assert loaded.name == "ManualPreset"
    assert len(loaded.segments) == 3  # H6, 120HR, RH
