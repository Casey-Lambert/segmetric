"""Headless (QT_QPA_PLATFORM=offscreen) smoke tests for segmetric.landmark's
GUI wiring -- core logic has its own thorough tests; this covers the
integration points: setup gating, the freeform click-to-place/select/drag/
double-click-to-rename canvas, zoom/pan (ported from segmetric.segment/
segmetric.mask), and the Next/Previous/Close save-and-navigate cycle.
"""
import csv
import os

import cv2
import numpy as np
import pytest
from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt
from PyQt6.QtGui import QKeyEvent, QMouseEvent, QWheelEvent
from PyQt6.QtWidgets import QApplication, QInputDialog, QMessageBox

from segmetric.landmark.gui.main_window import MainWindow
from segmetric.landmark.gui.review_window import MAX_ZOOM, MIN_ZOOM, _LandmarkCanvas
from segmetric.landmark.gui.setup_window import SetupPage


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    QMessageBox.information = staticmethod(lambda *a, **k: None)
    QMessageBox.critical = staticmethod(lambda *a, **k: None)
    QMessageBox.warning = staticmethod(lambda *a, **k: None)
    # Cancelled by default -- tests that need a rename set this explicitly
    # right before sending the double-click.
    QInputDialog.getText = staticmethod(lambda *a, **k: ("", False))
    return app


def _make_crop_image(width=400, height=300):
    image = np.full((height, width, 3), 220, dtype=np.uint8)
    cv2.rectangle(image, (50, 40), (350, 260), (120, 90, 60), -1)
    return image


def _write_crop(path):
    cv2.imwrite(str(path), _make_crop_image())


def _write_scale_csv(path, stems, mm_per_pixel="0.02"):
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["file_name", "mm_per_pixel", "scale_source"])
        for stem in stems:
            writer.writerow([f"{stem}.png", mm_per_pixel, "measured"])


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


def _send_double_click(canvas, x, y):
    pos = QPointF(x, y)
    event = QMouseEvent(
        QEvent.Type.MouseButtonDblClick, pos, pos,
        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
    )
    canvas.mouseDoubleClickEvent(event)


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


def test_setup_page_ready_requires_scales_and_crops_only(qapp):
    page = SetupPage()
    assert page.is_ready() is False

    page.scales_file = "/tmp/fake_scales.csv"
    assert page.is_ready() is False  # crops folder still missing

    page.crops_folder = "/tmp/fake_crops"
    assert page.is_ready() is True  # no preset/batch-type choice needed


def test_full_review_freeform_place_rename_delete_measure_and_navigate(qapp, tmp_path):
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
    window.setup_page._on_inputs_changed()
    assert window.setup_page.is_ready() is True

    window.on_next()
    assert window.stack.currentIndex() == 1  # output page (no preset step)
    assert len(window.matched_crops) == 2

    window.output_folder = str(output_dir)
    window.on_begin_review()
    assert window.stack.currentIndex() == 2  # review page

    rw = window.review_window
    canvas = rw.canvas
    canvas.resize(400, 300)
    canvas._recompute_geometry()
    assert canvas.points == {}

    # Click-place the first landmark -- defaults to "1".
    wx, wy = _widget_point_for_image_point(canvas, 120, 100)
    _send_mouse(canvas, QEvent.Type.MouseButtonPress, wx, wy)
    _send_mouse(canvas, QEvent.Type.MouseButtonRelease, wx, wy)
    assert "1" in canvas.points
    assert canvas.selected_label == "1"
    assert "1 placed" in rw.measure_label.text()

    # Click-place a second landmark elsewhere -- defaults to "2".
    wx2, wy2 = _widget_point_for_image_point(canvas, 250, 180)
    _send_mouse(canvas, QEvent.Type.MouseButtonPress, wx2, wy2)
    _send_mouse(canvas, QEvent.Type.MouseButtonRelease, wx2, wy2)
    assert "2" in canvas.points
    assert "2 placed" in rw.measure_label.text()
    assert "Centroid size" in rw.measure_label.text()

    # Clicking near "1" selects it (not a new point) and dragging moves it.
    before = canvas.points["1"]
    twx, twy = _widget_point_for_image_point(canvas, before[0], before[1])
    _send_mouse(canvas, QEvent.Type.MouseButtonPress, twx, twy)
    assert canvas.selected_label == "1"
    assert canvas._dragging is True
    _send_mouse(canvas, QEvent.Type.MouseMove, twx + 15, twy + 5)
    _send_mouse(canvas, QEvent.Type.MouseButtonRelease, twx + 15, twy + 5)
    assert canvas.points["1"] != before
    assert len(canvas.points) == 2  # dragging never adds a new point

    # Double-click "2" to rename it to "tip".
    QInputDialog.getText = staticmethod(lambda *a, **k: ("tip", True))
    _send_double_click(canvas, wx2, wy2)
    assert "tip" in canvas.points
    assert "2" not in canvas.points
    assert canvas.order == ["1", "tip"]  # stable order, not moved to the end

    # Delete "1" -- frees exactly that label, "tip" untouched.
    canvas.selected_label = "1"
    rw.on_delete_landmark()
    assert "1" not in canvas.points
    assert "tip" in canvas.points
    assert "1 placed" in rw.measure_label.text()

    # A further click on empty space reuses the freed default "1".
    _send_mouse(canvas, QEvent.Type.MouseButtonPress, wx, wy)
    _send_mouse(canvas, QEvent.Type.MouseButtonRelease, wx, wy)
    assert "1" in canvas.points
    assert "2 placed" in rw.measure_label.text()

    # Next must save panel_01's measurement and load panel_02.
    rw.on_next()
    assert rw.index == 1
    row0 = rw.rows[0]
    assert row0["status"] == "measured"
    assert row0["n_landmarks"] == 2
    assert row0["tip_x_px"] != ""

    # Mark panel_02 blank, then Close -- must save it too.
    rw.blank_btn.setChecked(True)
    rw.on_mark_blank(True)
    rw.on_close()

    with open(rw.csv_path) as f:
        rows_by_name = {row["file_name"]: row for row in csv.DictReader(f)}
    assert rows_by_name["panel_01_cropped.png"]["status"] == "measured"
    assert rows_by_name["panel_02_cropped.png"]["status"] == "blank"
    assert rows_by_name["panel_02_cropped.png"]["tip_x_px"] == ""


def test_rename_rejects_a_name_already_used_on_the_same_crop(qapp):
    canvas = _LandmarkCanvas()
    canvas.resize(400, 300)
    canvas.load(_make_crop_image(), None, {}, [], reset_view=True)
    canvas._recompute_geometry()

    p1 = _widget_point_for_image_point(canvas, 100, 100)
    p2 = _widget_point_for_image_point(canvas, 200, 150)
    for p in (p1, p2):
        _send_mouse(canvas, QEvent.Type.MouseButtonPress, *p)
        _send_mouse(canvas, QEvent.Type.MouseButtonRelease, *p)
    assert set(canvas.points) == {"1", "2"}

    QInputDialog.getText = staticmethod(lambda *a, **k: ("2", True))
    _send_double_click(canvas, *p1)  # try to rename "1" to "2", already taken

    assert set(canvas.points) == {"1", "2"}  # unchanged
    assert canvas.order == ["1", "2"]


def test_rename_cancelled_or_blank_is_a_no_op(qapp):
    canvas = _LandmarkCanvas()
    canvas.resize(400, 300)
    canvas.load(_make_crop_image(), None, {}, [], reset_view=True)
    canvas._recompute_geometry()

    p1 = _widget_point_for_image_point(canvas, 100, 100)
    _send_mouse(canvas, QEvent.Type.MouseButtonPress, *p1)
    _send_mouse(canvas, QEvent.Type.MouseButtonRelease, *p1)
    assert set(canvas.points) == {"1"}

    QInputDialog.getText = staticmethod(lambda *a, **k: ("whatever", False))  # cancelled
    _send_double_click(canvas, *p1)
    assert set(canvas.points) == {"1"}

    QInputDialog.getText = staticmethod(lambda *a, **k: ("   ", True))  # blank after strip
    _send_double_click(canvas, *p1)
    assert set(canvas.points) == {"1"}


def _make_loaded_canvas(width=400, height=400):
    image = _make_crop_image(width, height)
    canvas = _LandmarkCanvas()
    canvas.resize(width, height)
    canvas.load(image, None, {}, [])
    canvas._recompute_geometry()
    return canvas


def test_click_always_adds_a_new_landmark_numbered_by_default(qapp):
    canvas = _make_loaded_canvas()
    for ix, iy in [(100, 100), (150, 150), (200, 200)]:
        wx, wy = _widget_point_for_image_point(canvas, ix, iy)
        _send_mouse(canvas, QEvent.Type.MouseButtonPress, wx, wy)
        _send_mouse(canvas, QEvent.Type.MouseButtonRelease, wx, wy)
    assert set(canvas.points) == {"1", "2", "3"}
    assert canvas.order == ["1", "2", "3"]


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
    assert canvas.pan_center[0] < pan_before[0]
    assert canvas.pan_center[1] < pan_before[1]


def test_pan_stays_clamped_within_image_bounds(qapp):
    canvas = _make_loaded_canvas()
    _send_wheel(canvas, 200, 200, 120)
    _send_wheel(canvas, 200, 200, 120)

    _send_key(canvas, QEvent.Type.KeyPress, Qt.Key.Key_Space)
    _send_mouse(canvas, QEvent.Type.MouseButtonPress, 200, 200)
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

    canvas.load(canvas.image_rgb, None, dict(canvas.points), list(canvas.order), reset_view=False)
    assert canvas.zoom == zoomed  # preserved

    canvas.load(canvas.image_rgb, None, dict(canvas.points), list(canvas.order), reset_view=True)
    assert canvas.zoom == MIN_ZOOM  # reset -- e.g. a genuinely new crop


def test_place_lands_correctly_while_zoomed_in(qapp):
    canvas = _make_loaded_canvas()
    _send_wheel(canvas, 200, 200, 240)  # zoom in a couple of notches
    canvas._recompute_geometry()

    assert len(canvas.points) == 0
    _send_mouse(canvas, QEvent.Type.MouseButtonPress, 200, 200)
    _send_mouse(canvas, QEvent.Type.MouseButtonRelease, 200, 200)
    assert len(canvas.points) == 1

    # The placed point's image-space coordinate should round-trip back to
    # (approximately) the same widget point we clicked, confirming the
    # zoomed display-rect math (not just the un-zoomed "fit" case) is used.
    label = next(iter(canvas.points))
    ix, iy = canvas.points[label]
    wx, wy = canvas._widget_point_from_image(ix, iy)
    assert wx == pytest.approx(200, abs=1.0)
    assert wy == pytest.approx(200, abs=1.0)
