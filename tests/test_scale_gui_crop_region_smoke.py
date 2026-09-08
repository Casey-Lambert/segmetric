"""Headless (QT_QPA_PLATFORM=offscreen) smoke tests for segmetric.scale's
marker-relative crop region controls -- core logic (CropRegion/
apply_crop_region/compute_crop_bbox) has its own thorough tests in
test_scale_core.py; this covers the GUI integration: settings round-trip,
marker-mode visibility, and the live preview reflecting a changed region.
"""
import cv2
import pytest
from PyQt6.QtWidgets import QApplication

from segmetric.scale.core.model import ScaleSettings
from segmetric.scale.gui.main_window import MainWindow

from test_scale_core import make_square_marker_image


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_default_crop_region_matches_scale_settings_defaults(qapp):
    window = MainWindow()
    settings = window._current_settings()
    defaults = ScaleSettings()
    assert settings.crop_v_anchor == defaults.crop_v_anchor == "center"
    assert settings.crop_v_size_pct == defaults.crop_v_size_pct == 50
    assert settings.crop_h_anchor == defaults.crop_h_anchor == "center"
    assert settings.crop_h_size_pct == defaults.crop_h_size_pct == 100


def test_crop_region_controls_round_trip_through_current_settings(qapp):
    window = MainWindow()

    window.crop_v_top_radio.setChecked(True)
    window.crop_v_size_spin.setValue(25)
    window.crop_h_right_radio.setChecked(True)
    window.crop_h_size_spin.setValue(60)

    settings = window._current_settings()
    assert settings.crop_v_anchor == "top"
    assert settings.crop_v_size_pct == 25
    assert settings.crop_h_anchor == "right"
    assert settings.crop_h_size_pct == 60


def test_apply_settings_to_controls_sets_crop_radios_and_spins(qapp):
    window = MainWindow()
    settings = ScaleSettings(
        crop_v_anchor="bottom", crop_v_size_pct=35, crop_h_anchor="left", crop_h_size_pct=45
    )

    window._apply_settings_to_controls(settings)

    assert window.crop_v_bottom_radio.isChecked() is True
    assert window.crop_v_size_spin.value() == 35
    assert window.crop_h_left_radio.isChecked() is True
    assert window.crop_h_size_spin.value() == 45

    # Round-trips back out the same way.
    assert window._current_settings().crop_v_anchor == "bottom"
    assert window._current_settings().crop_h_anchor == "left"


def test_default_group_size_is_off(qapp):
    window = MainWindow()
    assert window.group_size_spin.value() == 0
    assert window._current_settings().group_size == 0


def test_group_size_control_round_trips_through_current_settings(qapp):
    window = MainWindow()
    window.group_size_spin.setValue(16)
    assert window._current_settings().group_size == 16


def test_apply_settings_to_controls_sets_group_size(qapp):
    window = MainWindow()
    window._apply_settings_to_controls(ScaleSettings(group_size=8))
    assert window.group_size_spin.value() == 8
    assert window._current_settings().group_size == 8


def test_group_size_off_is_passed_to_the_worker_as_none(qapp, monkeypatch):
    """0 ("Off" in the spinbox) must reach run_scale_job as group_size=None
    -- today's unchanged whole-batch-median behavior -- not literally 0
    (which run_scale_job would also treat as "off" per its own `not
    group_size` check, but the explicit None is what the docstring/tests
    for run_scale_job itself are written against).
    """
    from segmetric.scale.gui.worker import ScaleJobWorker

    captured = {}

    def fake_run_scale_job(*args, **kwargs):
        captured.update(kwargs)
        raise SystemExit  # stop before actually touching any files

    monkeypatch.setattr("segmetric.scale.gui.worker.run_scale_job", fake_run_scale_job)

    worker = ScaleJobWorker("in", "out", settings=ScaleSettings(group_size=0))
    try:
        worker.run()
    except SystemExit:
        pass
    assert captured["group_size"] is None

    worker = ScaleJobWorker("in", "out", settings=ScaleSettings(group_size=16))
    try:
        worker.run()
    except SystemExit:
        pass
    assert captured["group_size"] == 16


def test_crop_region_group_hidden_in_no_markers_mode(qapp):
    window = MainWindow()
    assert window.crop_region_group.isVisibleTo(window) is True

    window.no_markers_radio.setChecked(True)
    assert window.crop_region_group.isVisibleTo(window) is False

    window.markers_present_radio.setChecked(True)
    assert window.crop_region_group.isVisibleTo(window) is True


def test_preview_status_reflects_detected_markers_and_settings_changes(qapp, tmp_path):
    image = make_square_marker_image(spacing_px=400)
    path = tmp_path / "markers.png"
    cv2.imwrite(str(path), image)

    window = MainWindow()
    window.preview_image_bgr = image
    window.first_input_file = str(path)
    window.input_folder = str(tmp_path)
    window._update_preview()

    assert "4 marker(s) found" in window.preview_status_label.text()

    # Changing a crop-region control re-renders the preview without error
    # and without changing the detected-marker count (only the crop box).
    window.crop_v_size_spin.setValue(20)
    window.on_settings_changed()
    assert "4 marker(s) found" in window.preview_status_label.text()


def test_preview_pixmap_changes_when_crop_region_shrinks(qapp, tmp_path):
    image = make_square_marker_image(spacing_px=400)
    path = tmp_path / "markers.png"
    cv2.imwrite(str(path), image)

    window = MainWindow()
    window.preview_image_bgr = image
    window.first_input_file = str(path)
    window.input_folder = str(tmp_path)
    window._update_preview()
    default_pixmap = window.preview_label.pixmap()
    default_image = default_pixmap.toImage()

    window.crop_v_size_spin.setValue(10)
    window.crop_h_size_spin.setValue(10)
    window._update_preview()
    shrunk_pixmap = window.preview_label.pixmap()
    shrunk_image = shrunk_pixmap.toImage()

    # Same overall preview size (still fit to the label), but the drawn
    # content differs now that the orange crop box is much smaller.
    assert default_image != shrunk_image
