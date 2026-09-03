"""Headless (QT_QPA_PLATFORM=offscreen) smoke tests for segmetric.scale's
no-markers manual scale/crop workflow -- core logic has its own thorough
tests (test_scale_manual.py); this covers the integration points: the two
new canvases, the dialogs built on them, and MainWindow's marker-mode
toggle + end-to-end manual run.
"""
import csv
import os
import time

import cv2
import numpy as np
import pytest
from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt
from PyQt6.QtGui import QMouseEvent, QWheelEvent
from PyQt6.QtWidgets import QApplication, QDialog, QMessageBox

from segmetric.scale.gui import main_window as main_window_module
from segmetric.scale.gui.main_window import MainWindow
from segmetric.scale.gui.manual_canvas import MAX_ZOOM, MIN_ZOOM, _RectCanvas, _TwoPointCanvas
from segmetric.scale.gui.manual_crop_dialog import CropReviewDialog, SetCropDialog
from segmetric.scale.gui.manual_scale_dialog import ScaleReviewDialog, SetScaleDialog
from segmetric.scale.gui.preview import load_preview_image


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    QMessageBox.information = staticmethod(lambda *a, **k: None)
    QMessageBox.critical = staticmethod(lambda *a, **k: None)
    QMessageBox.warning = staticmethod(lambda *a, **k: None)
    return app


def _make_image(width=300, height=200):
    return np.full((height, width, 3), 180, dtype=np.uint8)


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


def _prep_canvas(canvas, width=300, height=200):
    """Dialog canvases never actually get painted in a headless test (no
    real show()/paintEvent), so _display_rect is never computed on its
    own -- force it, the same way the standalone-canvas tests above do,
    or every widget-point calculation reads a zeroed rect.
    """
    canvas.resize(width, height)
    canvas._recompute_geometry()


def _widget_point_for_image_point(canvas, ix, iy):
    rect = canvas._display_rect
    h, w = canvas.image_bgr.shape[:2]
    wx = rect.x() + (ix / w) * rect.width()
    wy = rect.y() + (iy / h) * rect.height()
    return wx, wy


# ------------------------------------------------------------------ canvases
def test_two_point_canvas_two_clicks_compute_distance(qapp):
    canvas = _TwoPointCanvas()
    canvas.resize(300, 200)
    canvas.load(_make_image(300, 200))
    canvas._recompute_geometry()

    p1 = _widget_point_for_image_point(canvas, 50, 100)
    p2 = _widget_point_for_image_point(canvas, 150, 100)
    _send_mouse(canvas, QEvent.Type.MouseButtonPress, *p1)
    _send_mouse(canvas, QEvent.Type.MouseButtonPress, *p2)

    assert len(canvas.points) == 2
    assert canvas.pixel_distance() == pytest.approx(100, abs=1.0)


def test_two_point_canvas_third_click_starts_over(qapp):
    canvas = _TwoPointCanvas()
    canvas.resize(300, 200)
    canvas.load(_make_image(300, 200))
    canvas._recompute_geometry()

    for ix, iy in [(50, 100), (150, 100), (200, 50)]:
        wx, wy = _widget_point_for_image_point(canvas, ix, iy)
        _send_mouse(canvas, QEvent.Type.MouseButtonPress, wx, wy)

    assert len(canvas.points) == 1  # the third click cleared and started a new one


def test_two_point_canvas_zoom_clamped(qapp):
    canvas = _TwoPointCanvas()
    canvas.resize(300, 200)
    canvas.load(_make_image(300, 200))
    canvas._recompute_geometry()
    assert canvas.zoom == MIN_ZOOM

    for _ in range(60):
        _send_wheel(canvas, 150, 100, 120)
    assert canvas.zoom == pytest.approx(MAX_ZOOM)


def test_rect_canvas_drag_defines_bbox(qapp):
    canvas = _RectCanvas()
    canvas.resize(300, 200)
    canvas.load(_make_image(300, 200))
    canvas._recompute_geometry()

    p1 = _widget_point_for_image_point(canvas, 20, 30)
    p2 = _widget_point_for_image_point(canvas, 120, 90)
    _send_mouse(canvas, QEvent.Type.MouseButtonPress, *p1)
    _send_mouse(canvas, QEvent.Type.MouseMove, *p2)
    _send_mouse(canvas, QEvent.Type.MouseButtonRelease, *p2)

    assert canvas.bbox is not None
    x1, y1, x2, y2 = canvas.bbox
    assert x1 == pytest.approx(20, abs=1) and y1 == pytest.approx(30, abs=1)
    assert x2 == pytest.approx(120, abs=1) and y2 == pytest.approx(90, abs=1)


def test_rect_canvas_clamps_to_image_bounds(qapp):
    canvas = _RectCanvas()
    canvas.resize(300, 200)
    canvas.load(_make_image(300, 200))
    canvas._recompute_geometry()

    p1 = _widget_point_for_image_point(canvas, 10, 10)
    _send_mouse(canvas, QEvent.Type.MouseButtonPress, *p1)
    _send_mouse(canvas, QEvent.Type.MouseMove, 5000, 5000)  # way outside the widget
    _send_mouse(canvas, QEvent.Type.MouseButtonRelease, 5000, 5000)

    x1, y1, x2, y2 = canvas.bbox
    assert 0 <= x1 <= 300 and 0 <= x2 <= 300
    assert 0 <= y1 <= 200 and 0 <= y2 <= 200


# ------------------------------------------------------------------- dialogs
def test_set_scale_dialog_ok_disabled_until_ready(qapp):
    dialog = SetScaleDialog(_make_image(), "test.png")
    _prep_canvas(dialog.panel.canvas)
    ok_button = dialog.buttons.button(dialog.buttons.StandardButton.Ok)
    assert ok_button.isEnabled() is False

    p1 = _widget_point_for_image_point(dialog.panel.canvas, 50, 100)
    p2 = _widget_point_for_image_point(dialog.panel.canvas, 150, 100)
    _send_mouse(dialog.panel.canvas, QEvent.Type.MouseButtonPress, *p1)
    _send_mouse(dialog.panel.canvas, QEvent.Type.MouseButtonPress, *p2)
    dialog.panel.distance_spin.setValue(10.0)

    assert ok_button.isEnabled() is True
    dialog.on_accept()
    assert dialog.result_scale == pytest.approx(0.1, abs=1e-3)


def test_scale_review_dialog_requires_every_image_before_close(qapp, tmp_path):
    paths = []
    for i in range(2):
        p = tmp_path / f"img{i}.png"
        cv2.imwrite(str(p), _make_image())
        paths.append(str(p))

    dialog = ScaleReviewDialog(paths)
    _prep_canvas(dialog.panel.canvas)
    dialog.on_close()  # nothing set yet -- must refuse
    assert dialog.result() != QDialog.DialogCode.Accepted

    p1 = _widget_point_for_image_point(dialog.panel.canvas, 50, 100)
    p2 = _widget_point_for_image_point(dialog.panel.canvas, 150, 100)
    _send_mouse(dialog.panel.canvas, QEvent.Type.MouseButtonPress, *p1)
    _send_mouse(dialog.panel.canvas, QEvent.Type.MouseButtonPress, *p2)
    dialog.panel.distance_spin.setValue(20.0)
    dialog.on_next()
    _prep_canvas(dialog.panel.canvas)
    _send_mouse(dialog.panel.canvas, QEvent.Type.MouseButtonPress, *p1)
    _send_mouse(dialog.panel.canvas, QEvent.Type.MouseButtonPress, *p2)
    dialog.panel.distance_spin.setValue(20.0)

    dialog.on_close()
    assert len(dialog.results) == 2


def test_crop_review_dialog_revisit_preserves_previous_value(qapp, tmp_path):
    paths = []
    for i in range(2):
        p = tmp_path / f"img{i}.png"
        cv2.imwrite(str(p), _make_image())
        paths.append(str(p))

    dialog = CropReviewDialog(paths)
    _prep_canvas(dialog.panel.canvas)
    p1 = _widget_point_for_image_point(dialog.panel.canvas, 10, 10)
    p2 = _widget_point_for_image_point(dialog.panel.canvas, 100, 80)
    _send_mouse(dialog.panel.canvas, QEvent.Type.MouseButtonPress, *p1)
    _send_mouse(dialog.panel.canvas, QEvent.Type.MouseMove, *p2)
    _send_mouse(dialog.panel.canvas, QEvent.Type.MouseButtonRelease, *p2)
    dialog.on_next()  # saves image 0's bbox, loads image 1 (blank canvas)

    assert "img0.png" in dialog.results
    assert dialog.panel.canvas.bbox is None  # revisit starts blank, doesn't show the old drag

    dialog.on_previous()  # nothing drawn on image 1 -- must not clobber image 0
    assert "img0.png" in dialog.results


# ---------------------------------------------------------------- MainWindow
def test_marker_mode_toggle_swaps_visible_control_groups(qapp):
    window = MainWindow()
    assert window.scale_group.isVisibleTo(window) is True
    assert window.manual_group.isVisibleTo(window) is False

    window.no_markers_radio.setChecked(True)
    assert window.scale_group.isVisibleTo(window) is False
    assert window.manual_group.isVisibleTo(window) is True

    window.markers_present_radio.setChecked(True)
    assert window.scale_group.isVisibleTo(window) is True
    assert window.manual_group.isVisibleTo(window) is False


def test_changing_scale_mode_clears_a_previously_set_scale(qapp):
    window = MainWindow()
    window.no_markers_radio.setChecked(True)
    window._manual_scale_by_name = {"a.png": 0.1}
    window.scale_status_label.setText("✓ something")

    window.scale_per_image_radio.setChecked(True)

    assert window._manual_scale_by_name == {}
    assert "No scale set yet" in window.scale_status_label.text()


def test_new_input_folder_invalidates_stale_manual_config(qapp, tmp_path):
    window = MainWindow()
    window.no_markers_radio.setChecked(True)
    window._manual_scale_by_name = {"old.png": 0.1}
    window._manual_scale_source_by_name = {"old.png": "manual_batch"}

    crops_dir = tmp_path / "crops"
    crops_dir.mkdir()
    cv2.imwrite(str(crops_dir / "new.png"), _make_image())

    # Bypass the QFileDialog folder picker directly, same as other tests in
    # this suite do for browse handlers.
    from segmetric.tag.core.discovery import find_input_files

    files = find_input_files(str(crops_dir))
    window.input_folder = str(crops_dir)
    window.input_line.setText(str(crops_dir))
    window.first_input_file = files[0]
    window._manual_scale_by_name = {}
    window._manual_scale_source_by_name = {}
    window._manual_crop_bbox_by_name = None
    window.scale_status_label.setText("⚠ No scale set yet.")

    assert window._manual_scale_by_name == {}
    assert window._is_ready() is False  # scale still needs to be set for "new.png"


def test_full_no_markers_run_end_to_end(qapp, tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    stems = ["a", "b"]
    for stem in stems:
        cv2.imwrite(str(input_dir / f"{stem}.png"), _make_image())
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    window = MainWindow()
    window.input_folder = str(input_dir)
    window.input_line.setText(str(input_dir))
    window.first_input_file = str(input_dir / "a.png")
    window.preview_image_bgr = load_preview_image(window.first_input_file)
    window.output_folder = str(output_dir)
    window.output_line.setText(str(output_dir))

    window.no_markers_radio.setChecked(True)
    window.scale_batch_radio.setChecked(True)
    window.no_crop_radio.setChecked(True)

    class _FakeScaleDialog:
        def __init__(self, image, name, parent=None):
            self.result_scale = 0.05

        def exec(self):
            return QDialog.DialogCode.Accepted

    main_window_module.SetScaleDialog = _FakeScaleDialog
    try:
        window.on_set_scale()
    finally:
        main_window_module.SetScaleDialog = SetScaleDialog

    assert window._is_ready() is True

    result_holder = {}
    original_finished = window.on_job_finished

    def capture(result):
        result_holder["result"] = result
        original_finished(result)

    window.on_job_finished = capture
    window.on_run()

    deadline = time.time() + 10
    while "result" not in result_holder and time.time() < deadline:
        qapp.processEvents()
        time.sleep(0.02)
    assert "result" in result_holder, "manual scale job did not finish in time"

    csv_path = os.path.join(str(output_dir), "scale", "scales.csv")
    with open(csv_path) as f:
        rows = {row["file_name"]: row for row in csv.DictReader(f)}
    assert rows["a.png"]["scale_source"] == "manual_batch"
    assert float(rows["a.png"]["mm_per_pixel"]) == pytest.approx(0.05)
    assert os.path.exists(os.path.join(str(output_dir), "scale", "a_cropped.tiff"))
