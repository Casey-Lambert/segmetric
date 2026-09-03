"""Headless (QT_QPA_PLATFORM=offscreen) smoke tests for segmetric.segment's
GUI wiring -- core logic has its own thorough tests; this covers the
integration points: setup gating, the lazy per-crop detection worker, the
select-mode click-to-toggle canvas, paint-mode brush correction, and the
Next/Previous/Close save-and-navigate cycle.
"""
import csv
import json
import os
import time

import cv2
import numpy as np
import pytest
from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt
from PyQt6.QtGui import QKeyEvent, QMouseEvent, QWheelEvent
from PyQt6.QtWidgets import QApplication, QMessageBox

from segmetric.segment.gui.main_window import MainWindow
from segmetric.segment.gui.review_window import MAX_ZOOM, MIN_ZOOM, _CellCanvas
from segmetric.segment.gui.setup_window import SetupPage
from segmetric.set.core.model import Preset, Segment
from segmetric.set.core.presets import save_preset

from test_segment_detection import make_two_cell_image


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    QMessageBox.information = staticmethod(lambda *a, **k: None)
    QMessageBox.critical = staticmethod(lambda *a, **k: None)
    QMessageBox.warning = staticmethod(lambda *a, **k: None)
    return app


def _write_crop(path):
    cv2.imwrite(str(path), make_two_cell_image())


def _write_scale_csv(path, stems, mm_per_pixel="0.02"):
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["file_name", "mm_per_pixel", "scale_source"])
        for stem in stems:
            writer.writerow([f"{stem}.png", mm_per_pixel, "measured"])


def _wait_for_detection(qapp, review_window, index, timeout=20):
    deadline = time.time() + timeout
    while index not in review_window._detection_cache and time.time() < deadline:
        qapp.processEvents()
        time.sleep(0.02)
    assert index in review_window._detection_cache, "detection did not finish in time"


def _send_mouse(canvas, event_type, x, y):
    pos = QPointF(x, y)
    button = Qt.MouseButton.LeftButton if event_type != QEvent.Type.MouseMove else Qt.MouseButton.NoButton
    buttons = Qt.MouseButton.LeftButton if event_type == QEvent.Type.MouseMove else button
    event = QMouseEvent(event_type, pos, pos, button, buttons, Qt.KeyboardModifier.NoModifier)
    if event_type == QEvent.Type.MouseButtonPress:
        canvas.mousePressEvent(event)
    elif event_type == QEvent.Type.MouseButtonRelease:
        canvas.mouseReleaseEvent(event)
    elif event_type == QEvent.Type.MouseMove:
        canvas.mouseMoveEvent(event)


def _send_wheel(canvas, x, y, angle_delta_y):
    pos = QPointF(x, y)
    event = QWheelEvent(
        pos, pos, QPoint(0, 0), QPoint(0, angle_delta_y),
        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase, False,
    )
    canvas.wheelEvent(event)


def _send_key(canvas, event_type, key):
    event = QKeyEvent(event_type, key, Qt.KeyboardModifier.NoModifier)
    if event_type == QEvent.Type.KeyPress:
        canvas.keyPressEvent(event)
    else:
        canvas.keyReleaseEvent(event)


def _widget_point_for_image_point(canvas, ix, iy):
    rect = canvas._display_rect
    h, w = canvas.image_rgb.shape[:2]
    wx = rect.x() + (ix / w) * rect.width()
    wy = rect.y() + (iy / h) * rect.height()
    return wx, wy


def test_setup_page_gates_mixed_batch_on_object_id_preset(qapp):
    page = SetupPage()
    page.scales_file = "/tmp/fake_scales.csv"
    page.crops_folder = "/tmp/fake_crops"

    page.mixed_radio.setChecked(True)
    page._on_inputs_changed()
    assert page.is_ready() is False
    assert page.mixed_warning_label.isVisibleTo(page) is True

    page.metadata_preset = Preset(
        name="p", segments=[Segment(index=0, raw_value="", column_name="X")], object_id_column="X"
    )
    page._on_inputs_changed()
    assert page.is_ready() is True

    page.single_radio.setChecked(True)
    page._on_inputs_changed()
    assert page.is_ready() is True


def test_single_batch_review_select_correct_measure_and_navigate(qapp, tmp_path):
    crops_dir = tmp_path / "crops"
    crops_dir.mkdir()
    stems = ["panel_01", "panel_02"]
    for stem in stems:
        _write_crop(crops_dir / f"{stem}_cropped.png")
    scale_csv = tmp_path / "scales.csv"
    _write_scale_csv(scale_csv, stems)
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    window = MainWindow()
    window.setup_page.scales_file = str(scale_csv)
    window.setup_page.crops_folder = str(crops_dir)
    window.setup_page.single_radio.setChecked(True)
    window.setup_page._on_inputs_changed()
    assert window.setup_page.is_ready() is True

    window.on_next()
    assert window.stack.currentIndex() == 1  # preset page
    assert len(window.matched_crops) == 2

    window.preset_editor.name_edit.setText("My Preset")
    window.preset_editor._set_steps(["radial"])

    window.on_next()
    assert window.stack.currentIndex() == 3  # output page

    window.output_folder = str(output_dir)
    window.on_begin_review()
    assert window.stack.currentIndex() == 4  # review page

    rw = window.review_window
    _wait_for_detection(qapp, rw, 0)
    assert rw._current_step == "radial"
    assert rw._detection_cache[0][3] >= 2  # n_cells -- the vein split it in two

    canvas = rw.canvas
    canvas.resize(400, 400)
    canvas._recompute_geometry()

    ys, xs = np.where(canvas.labeled == 1)
    iy, ix = int(ys[len(ys) // 2]), int(xs[len(xs) // 2])
    wx, wy = _widget_point_for_image_point(canvas, ix, iy)
    _send_mouse(canvas, QEvent.Type.MouseButtonPress, wx, wy)
    _send_mouse(canvas, QEvent.Type.MouseButtonRelease, wx, wy)

    assert 1 in canvas.selected_labels
    assert canvas.step_mask.sum() > 0
    assert "radial" in rw.measure_label.text()

    # Switch to Correct mode and paint-erase a chunk of the selection.
    rw.paint_radio.setChecked(True)
    canvas.mode = "paint"
    canvas.paint_mode = "remove"
    before_sum = int(canvas.step_mask.sum())
    rect = canvas._display_rect
    _send_mouse(canvas, QEvent.Type.MouseButtonPress, rect.x() + 5, rect.y() + 5)
    _send_mouse(canvas, QEvent.Type.MouseButtonRelease, rect.x() + 5, rect.y() + 5)
    assert int(canvas.step_mask.sum()) <= before_sum

    # Next must save panel_01's measurement and load panel_02.
    rw.on_next()
    _wait_for_detection(qapp, rw, 1)
    assert rw.index == 1
    row0 = rw.rows[0]
    assert row0["status"] == "measured"
    assert row0["radial_area_px"] > 0
    mask_path = os.path.join(rw.masks_dir, "panel_01_radial.png")
    assert os.path.exists(mask_path)

    # Mark panel_02 blank, then Close -- must save it too.
    rw.blank_btn.setChecked(True)
    rw.on_mark_blank(True)
    rw.on_close()

    with open(rw.csv_path) as f:
        rows_by_name = {row["file_name"]: row for row in csv.DictReader(f)}
    assert rows_by_name["panel_01_cropped.png"]["status"] == "measured"
    assert rows_by_name["panel_02_cropped.png"]["status"] == "blank"
    assert rows_by_name["panel_02_cropped.png"]["radial_area_px"] == ""


def test_mixed_batch_resolves_preset_per_object_id(qapp, tmp_path):
    crops_dir = tmp_path / "crops"
    crops_dir.mkdir()
    stems = ["H6_120HR_AA", "H6_120HR_AB"]
    for stem in stems:
        _write_crop(crops_dir / f"{stem}_cropped.png")
    scale_csv = tmp_path / "scales.csv"
    _write_scale_csv(scale_csv, stems)
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    preset_path = tmp_path / "preset.json"
    save_preset(
        str(preset_path),
        Preset(
            name="p",
            segments=[Segment(index=2, raw_value="", column_name="ObjectID", include=True)],
            object_id_column="ObjectID",
        ),
    )

    window = MainWindow()
    window.setup_page.scales_file = str(scale_csv)
    window.setup_page.crops_folder = str(crops_dir)
    from segmetric.set.core.presets import load_preset

    window.setup_page.metadata_preset = load_preset(str(preset_path))
    window.setup_page.mixed_radio.setChecked(True)
    window.setup_page._on_inputs_changed()
    assert window.setup_page.is_ready() is True

    window.on_next()
    assert window.stack.currentIndex() == 2  # object-id page
    assert window.object_id_widget.is_ready() is False

    row = window.object_id_widget.add_group()
    row.set_object_ids(["AA", "AB"])
    row.preset_editor.name_edit.setText("Shared Preset")
    row.preset_editor._set_steps(["radial"])
    window.object_id_widget._update_coverage()
    assert window.object_id_widget.is_ready() is True

    window.on_next()
    assert window.stack.currentIndex() == 3
    window.output_folder = str(output_dir)
    window.on_begin_review()

    rw = window.review_window
    _wait_for_detection(qapp, rw, 0)
    assert rw._current_step == "radial"
    preset, object_id, reason = rw._resolved_preset()
    assert preset.name == "Shared Preset"
    assert object_id == "AA"
    assert reason is None


def _make_loaded_canvas(width=400, height=400):
    from segmetric.segment.core.detection import segment_cells
    from segmetric.segment.core.model import DetectionSettings

    image = make_two_cell_image()
    wing_mask = np.ones(image.shape[:2], dtype=np.uint8)
    labeled, n_cells, vein_mask = segment_cells(image, wing_mask, DetectionSettings())
    canvas = _CellCanvas()
    canvas.resize(width, height)
    canvas.load(image, labeled, n_cells, vein_mask, np.zeros(labeled.shape, dtype=np.uint8), set())
    canvas._recompute_geometry()
    return canvas


def test_zoom_clamped_to_min_and_max(qapp):
    canvas = _make_loaded_canvas()
    assert canvas.zoom == MIN_ZOOM

    # Can't zoom out past "fit" (MIN_ZOOM).
    _send_wheel(canvas, 200, 200, -1000)
    assert canvas.zoom == MIN_ZOOM

    # Zooming in repeatedly approaches but never exceeds MAX_ZOOM.
    for _ in range(60):
        _send_wheel(canvas, 200, 200, 120)
    assert canvas.zoom == pytest.approx(MAX_ZOOM)


def test_zoom_to_cursor_keeps_the_same_image_point_under_the_cursor(qapp):
    canvas = _make_loaded_canvas()
    canvas._recompute_geometry()

    cursor_x, cursor_y = 300, 150
    image_pt_before = canvas._image_point_at(cursor_x, cursor_y)

    _send_wheel(canvas, cursor_x, cursor_y, 120)
    canvas._recompute_geometry()
    image_pt_after = canvas._image_point_at(cursor_x, cursor_y)

    assert canvas.zoom > MIN_ZOOM
    assert image_pt_after[0] == pytest.approx(image_pt_before[0], abs=1.0)
    assert image_pt_after[1] == pytest.approx(image_pt_before[1], abs=1.0)


def test_space_drag_pans_the_view(qapp):
    canvas = _make_loaded_canvas()
    # Zoom in first -- at zoom=1.0 ("fit") the whole image is already
    # visible, so panning has nowhere new to reveal.
    _send_wheel(canvas, 200, 200, 120)
    _send_wheel(canvas, 200, 200, 120)
    canvas._recompute_geometry()
    pan_before = canvas.pan_center

    _send_key(canvas, QEvent.Type.KeyPress, Qt.Key.Key_Space)
    assert canvas._space_held is True

    _send_mouse(canvas, QEvent.Type.MouseButtonPress, 200, 200)
    assert canvas._panning is True
    _send_mouse(canvas, QEvent.Type.MouseMove, 260, 240)
    _send_mouse(canvas, QEvent.Type.MouseButtonRelease, 260, 240)
    assert canvas._panning is False

    _send_key(canvas, QEvent.Type.KeyRelease, Qt.Key.Key_Space)
    assert canvas._space_held is False

    assert canvas.pan_center != pan_before
    # Dragging right+down should move the view so the pan center (the image
    # point at the widget's center) shifts left+up.
    assert canvas.pan_center[0] < pan_before[0]
    assert canvas.pan_center[1] < pan_before[1]


def test_pan_stays_clamped_within_image_bounds(qapp):
    canvas = _make_loaded_canvas()
    _send_wheel(canvas, 200, 200, 120)
    _send_wheel(canvas, 200, 200, 120)

    _send_key(canvas, QEvent.Type.KeyPress, Qt.Key.Key_Space)
    _send_mouse(canvas, QEvent.Type.MouseButtonPress, 200, 200)
    # A huge drag should still leave pan_center within the image's own bounds.
    _send_mouse(canvas, QEvent.Type.MouseMove, 5000, 5000)
    _send_mouse(canvas, QEvent.Type.MouseButtonRelease, 5000, 5000)
    _send_key(canvas, QEvent.Type.KeyRelease, Qt.Key.Key_Space)

    h, w = canvas.image_rgb.shape[:2]
    assert 0 <= canvas.pan_center[0] <= w
    assert 0 <= canvas.pan_center[1] <= h


def test_reset_zoom_returns_to_fit_and_center(qapp):
    canvas = _make_loaded_canvas()
    _send_wheel(canvas, 200, 200, 120)
    assert canvas.zoom > MIN_ZOOM

    canvas.reset_zoom()

    assert canvas.zoom == MIN_ZOOM
    h, w = canvas.image_rgb.shape[:2]
    assert canvas.pan_center == (w / 2, h / 2)


def test_load_reset_view_true_resets_zoom_false_preserves_it(qapp):
    canvas = _make_loaded_canvas()
    _send_wheel(canvas, 200, 200, 120)
    zoomed = canvas.zoom
    assert zoomed > MIN_ZOOM

    empty = np.zeros(canvas.labeled.shape, dtype=np.uint8)
    canvas.load(
        canvas.image_rgb, canvas.labeled, canvas.n_cells, canvas.vein_mask, empty, set(), reset_view=False
    )
    assert canvas.zoom == zoomed  # preserved -- e.g. switching step tabs

    canvas.load(
        canvas.image_rgb, canvas.labeled, canvas.n_cells, canvas.vein_mask, empty, set(), reset_view=True
    )
    assert canvas.zoom == MIN_ZOOM  # reset -- e.g. a genuinely new crop


def test_paint_stroke_lands_correctly_while_zoomed_in(qapp):
    canvas = _make_loaded_canvas()
    canvas.mode = "paint"
    _send_wheel(canvas, 200, 200, 240)  # zoom in a couple of notches
    canvas._recompute_geometry()

    before_sum = int(canvas.step_mask.sum())
    _send_mouse(canvas, QEvent.Type.MouseButtonPress, 200, 200)
    _send_mouse(canvas, QEvent.Type.MouseButtonRelease, 200, 200)
    assert int(canvas.step_mask.sum()) > before_sum
