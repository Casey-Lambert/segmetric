"""Headless (QT_QPA_PLATFORM=offscreen) smoke tests for segmetric.mask's GUI
wiring -- the core logic already has its own thorough tests; this covers the
integration points that are easy to get wrong: page navigation gating,
worker-thread completion, and the correction dialog's mouse-driven paint
canvas (including its widget<->image coordinate mapping).
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

from segmetric.mask.core.masking import generate_mask
from segmetric.mask.core.model import DEFAULT_FILTERS
from segmetric.mask.gui.correction_dialog import MAX_ZOOM, MIN_ZOOM, CorrectionDialog, ReviewDialog, _MaskCanvas
from segmetric.mask.gui.main_window import MainWindow
from segmetric.mask.gui.setup_window import SetupPage
from segmetric.set.core.model import Preset, Segment
from segmetric.set.core.presets import load_preset, save_preset

from test_mask_masking import make_blob_image


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    # Modal QMessageBox.exec() would hang headless -- no-op them for these tests.
    QMessageBox.information = staticmethod(lambda *a, **k: None)
    QMessageBox.critical = staticmethod(lambda *a, **k: None)
    QMessageBox.warning = staticmethod(lambda *a, **k: None)
    return app


def _write_crop(path):
    image, _center, _axes = make_blob_image()
    cv2.imwrite(str(path), image)


def _write_scale_csv(path, stems, mm_per_pixel="0.02"):
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["file_name", "mm_per_pixel", "scale_source"])
        for stem in stems:
            writer.writerow([f"{stem}.png", mm_per_pixel, "measured"])


def _run_worker_to_completion(qapp, window, timeout=20):
    deadline = time.time() + timeout
    while window.mask_result is None and time.time() < deadline:
        qapp.processEvents()
        time.sleep(0.02)
    assert window.mask_result is not None, "worker did not finish in time"


def test_setup_page_gates_mixed_anatomy_on_object_id_preset(qapp):
    page = SetupPage()
    page.scales_file = "/tmp/fake_scales.csv"
    page.crops_folder = "/tmp/fake_crops"

    page.mixed_radio.setChecked(True)
    page._emit_ready()
    assert page.is_ready() is False
    assert page.mixed_warning_label.isVisibleTo(page) is True

    page.metadata_preset = Preset(
        name="p", segments=[Segment(index=0, raw_value="", column_name="X")], object_id_column="X"
    )
    page._emit_ready()
    assert page.is_ready() is True
    assert page.mixed_warning_label.isVisibleTo(page) is False

    page.metadata_preset = Preset(name="p2", segments=[], object_id_column=None)
    page._emit_ready()
    assert page.is_ready() is False

    page.single_radio.setChecked(True)
    page._emit_ready()
    assert page.is_ready() is True


def test_single_type_batch_runs_end_to_end(qapp, tmp_path):
    crops_dir = tmp_path / "crops"
    crops_dir.mkdir()
    stems = ["H6_120HR_34C_NR_1004_AA", "H6_120HR_34C_NR_1004_AB"]
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
    window.setup_page._emit_ready()

    window.on_next()
    assert window.stack.currentIndex() == 1  # filter page
    window.on_next()
    assert window.stack.currentIndex() == 3  # results page

    window.output_folder = str(output_dir)
    window.on_run()
    _run_worker_to_completion(qapp, window)

    assert window.mask_result.masks_saved == 2
    assert window.mask_result.skipped == []
    assert window.results_table.rowCount() == 2
    with open(window.mask_result.csv_path) as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 2
    assert all(row["mask_status"] == "auto" for row in rows)


def test_mixed_anatomy_batch_runs_end_to_end(qapp, tmp_path):
    crops_dir = tmp_path / "crops"
    crops_dir.mkdir()
    stems = [
        "H6_120HR_34C_NR_1004_AA",
        "H6_120HR_34C_NR_1004_AB",
        "H6_120HR_34C_NR_1004_AC",
    ]
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
            name="test-preset",
            segments=[
                Segment(index=0, raw_value="", column_name="Colony", include=True),
                Segment(index=5, raw_value="", column_name="ObjectID", include=True),
            ],
            object_id_column="ObjectID",
        ),
    )

    window = MainWindow()
    window.setup_page.scales_file = str(scale_csv)
    window.setup_page.crops_folder = str(crops_dir)
    window.setup_page.metadata_preset = load_preset(str(preset_path))
    window.setup_page.mixed_radio.setChecked(True)
    window.setup_page._emit_ready()
    assert window.setup_page.is_ready() is True

    window.on_next()
    assert window.stack.currentIndex() == 2  # object-id-assignment page
    assert window.object_id_widget.is_ready() is False  # no groups yet

    row1 = window.object_id_widget.add_group()
    row1.set_object_ids(["AA", "AB"])
    row1.filter_editor.start_buttons["Forewing"].setChecked(True)
    window.object_id_widget._update_coverage()
    assert window.object_id_widget.is_ready() is False  # "AC" still unassigned

    row2 = window.object_id_widget.add_group()
    row2.set_object_ids(["AC"])
    row2.filter_editor.start_buttons["Leg"].setChecked(True)
    window.object_id_widget._update_coverage()
    assert window.object_id_widget.is_ready() is True

    resolver = window.object_id_widget.filter_resolver()
    assert resolver["AA"].name == "Forewing"
    assert resolver["AC"].name == "Leg"

    window.on_next()
    assert window.stack.currentIndex() == 3
    window.output_folder = str(output_dir)
    window.on_run()
    _run_worker_to_completion(qapp, window)

    assert window.mask_result.masks_saved == 3
    with open(window.mask_result.csv_path) as f:
        rows_by_id = {row["object_id"]: row for row in csv.DictReader(f)}
    assert rows_by_id["AA"]["filter_used"] == "Forewing"
    assert rows_by_id["AC"]["filter_used"] == "Leg"


def _send_mouse(canvas, event_type, x, y):
    pos = QPointF(x, y)
    event = QMouseEvent(
        event_type, pos, pos, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier
    )
    if event_type == QEvent.Type.MouseButtonPress:
        canvas.mousePressEvent(event)
    elif event_type == QEvent.Type.MouseMove:
        canvas.mouseMoveEvent(event)
    elif event_type == QEvent.Type.MouseButtonRelease:
        canvas.mouseReleaseEvent(event)


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


def test_correction_dialog_paint_reset_and_remeasure(qapp):
    image, _center, _axes = make_blob_image()
    mask = generate_mask(image, DEFAULT_FILTERS["Leg"])
    original_sum = int(mask.sum())

    dialog = CorrectionDialog(image, mask, mm_per_pixel=0.02, file_name="test.png")
    dialog.resize(500, 400)
    canvas = dialog.panel.canvas
    canvas.resize(460, 320)
    canvas._recompute_geometry()
    rect = canvas._display_rect
    assert rect.width() > 0

    # ADD stroke near the display rect's own corner (accounting for letterboxing).
    x0, y0 = rect.x() + 10, rect.y() + 10
    x1, y1 = rect.x() + 30, rect.y() + 30
    _send_mouse(canvas, QEvent.Type.MouseButtonPress, x0, y0)
    _send_mouse(canvas, QEvent.Type.MouseMove, x1, y1)
    _send_mouse(canvas, QEvent.Type.MouseButtonRelease, x1, y1)
    assert canvas.mask.sum() > original_sum

    dialog.panel.on_reset()
    assert int(canvas.mask.sum()) == original_sum

    dialog.panel.remove_radio.setChecked(True)
    cx, cy = rect.x() + rect.width() // 2, rect.y() + rect.height() // 2
    _send_mouse(canvas, QEvent.Type.MouseButtonPress, cx, cy)
    _send_mouse(canvas, QEvent.Type.MouseButtonRelease, cx, cy)
    assert canvas.mask.sum() < original_sum

    dialog.on_save()
    assert dialog.result_measurement is not None
    assert dialog.result_tag == ""
    assert int(dialog.result_mask.sum()) == int(canvas.mask.sum())


def test_tag_controls_are_mutually_exclusive_and_toggle(qapp):
    image, _center, _axes = make_blob_image()
    mask = generate_mask(image, DEFAULT_FILTERS["Leg"])
    dialog = CorrectionDialog(image, mask, mm_per_pixel=0.02, file_name="t.png")
    tags = dialog.panel.tag_controls

    assert tags.current_tag() == ""

    tags.damage_btn.click()
    assert tags.current_tag() == "damage"
    assert tags.damage_btn.isChecked() is True
    assert tags.blank_btn.isChecked() is False

    tags.blank_btn.click()
    assert tags.current_tag() == "blank"
    assert tags.damage_btn.isChecked() is False
    assert tags.blank_btn.isChecked() is True

    tags.blank_btn.click()  # clicking the active one again clears it
    assert tags.current_tag() == ""
    assert tags.blank_btn.isChecked() is False

    tags.custom_edit.setText("reshoot")
    tags.apply_custom_btn.click()
    assert tags.current_tag() == "reshoot"
    assert tags.custom_edit.text() == "reshoot"  # text stays loaded for reuse

    tags.apply_custom_btn.click()  # same text again -> clears
    assert tags.current_tag() == ""
    assert tags.custom_edit.text() == "reshoot"  # field itself is untouched

    dialog.on_save()
    assert dialog.result_tag == ""


def test_review_all_navigates_saves_and_tags_each_file(qapp, tmp_path):
    crops_dir = tmp_path / "crops"
    crops_dir.mkdir()
    stems = ["H6_120HR_34C_NR_1004_AA", "H6_120HR_34C_NR_1004_AB"]
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
    window.setup_page._emit_ready()
    window.on_next()
    window.on_next()
    window.output_folder = str(output_dir)
    window.on_run()
    _run_worker_to_completion(qapp, window)
    assert window.mask_result.masks_saved == 2
    assert window.review_all_btn.isEnabled() is True

    review = ReviewDialog(window, start_index=0)
    assert review.position_label.text().startswith("Object 1 of 2")
    assert review.prev_btn.isEnabled() is False
    assert review.next_btn.isEnabled() is True

    # Tag the first object as damaged, then advance -- Next must save it.
    review.panel.tag_controls.damage_btn.click()
    review.on_next()

    first_row = window.mask_result.rows[0]
    assert first_row["mask_status"] == "corrected"
    assert first_row["tag"] == "damage"
    tagged_mask_path = os.path.join(window.mask_result.masks_dir, "H6_120HR_34C_NR_1004_AA_damage_mask.png")
    assert os.path.exists(tagged_mask_path)
    untagged_mask_path = os.path.join(window.mask_result.masks_dir, "H6_120HR_34C_NR_1004_AA_mask.png")
    assert not os.path.exists(untagged_mask_path)

    assert review.position_label.text().startswith("Object 2 of 2")
    assert review.prev_btn.isEnabled() is True
    assert review.next_btn.isEnabled() is False

    # Apply a custom tag to the second object, then Close -- must also save.
    review.panel.tag_controls.custom_edit.setText("reshoot")
    review.panel.tag_controls.apply_custom_btn.click()
    review.on_close()

    second_row = window.mask_result.rows[1]
    assert second_row["tag"] == "reshoot"
    assert os.path.exists(
        os.path.join(window.mask_result.masks_dir, "H6_120HR_34C_NR_1004_AB_reshoot_mask.png")
    )

    # Table and CSV both reflect the tags.
    assert window.results_table.item(0, 5).text() == "damage"
    assert window.results_table.item(1, 5).text() == "reshoot"
    with open(window.mask_result.csv_path) as f:
        rows = {row["file_name"]: row for row in csv.DictReader(f)}
    assert rows["H6_120HR_34C_NR_1004_AA_cropped.png"]["tag"] == "damage"
    assert rows["H6_120HR_34C_NR_1004_AB_cropped.png"]["tag"] == "reshoot"


def _make_loaded_canvas(width=400, height=400):
    image, _center, _axes = make_blob_image()
    mask = generate_mask(image, DEFAULT_FILTERS["Leg"])
    canvas = _MaskCanvas()
    canvas.resize(width, height)
    canvas.set_image_and_mask(image, mask, reset_view=True)
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

    h, w = canvas.image_bgr.shape[:2]
    assert 0 <= canvas.pan_center[0] <= w
    assert 0 <= canvas.pan_center[1] <= h


def test_reset_zoom_returns_to_fit_and_center(qapp):
    canvas = _make_loaded_canvas()
    _send_wheel(canvas, 200, 200, 120)
    assert canvas.zoom > MIN_ZOOM

    canvas.reset_zoom()

    assert canvas.zoom == MIN_ZOOM
    h, w = canvas.image_bgr.shape[:2]
    assert canvas.pan_center == (w / 2, h / 2)


def test_load_reset_view_true_resets_zoom_false_preserves_it(qapp):
    canvas = _make_loaded_canvas()
    _send_wheel(canvas, 200, 200, 120)
    zoomed = canvas.zoom
    assert zoomed > MIN_ZOOM

    empty = np.zeros(canvas.mask.shape, dtype=np.uint8)
    canvas.set_image_and_mask(canvas.image_bgr, empty, reset_view=False)
    assert canvas.zoom == zoomed  # preserved -- e.g. the "Reset" brush button

    canvas.set_image_and_mask(canvas.image_bgr, empty, reset_view=True)
    assert canvas.zoom == MIN_ZOOM  # reset -- e.g. loading a genuinely new object


def test_paint_stroke_lands_correctly_while_zoomed_in(qapp):
    canvas = _make_loaded_canvas()
    # Zoom in near a corner (make_blob_image centers its blob, so a corner
    # is outside the existing mask -- an ADD stroke there must grow it).
    _send_wheel(canvas, 20, 20, 240)
    canvas._recompute_geometry()

    before_sum = int(canvas.mask.sum())
    _send_mouse(canvas, QEvent.Type.MouseButtonPress, 20, 20)
    _send_mouse(canvas, QEvent.Type.MouseButtonRelease, 20, 20)
    assert int(canvas.mask.sum()) > before_sum
