"""Headless (QT_QPA_PLATFORM=offscreen) smoke tests for segmetric-measure's
GUI wiring -- the underlying tools' own core/GUI logic already has thorough
tests; this covers what's unique to the combined shell: Run validation
across whichever stages are enabled, the Mask stage actually completing
and advancing, masks-dir auto-chaining into Segment/Landmark when Mask
also ran, and the combined measure_summary.csv.
"""
import csv
import os
import time

import cv2
import numpy as np
import pytest
from PyQt6.QtWidgets import QApplication, QMessageBox

from segmetric.measure.gui.main_window import PAGE_MASK_RUN, PAGE_SETUP, PAGE_SUMMARY, MainWindow

from test_mask_masking import make_blob_image


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
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


def _run_mask_stage_to_completion(qapp, window, timeout=20):
    deadline = time.time() + timeout
    while window.mask_stage_page.mask_result is None and time.time() < deadline:
        qapp.processEvents()
        time.sleep(0.02)
    assert window.mask_stage_page.mask_result is not None, "mask worker did not finish in time"


def _make_dataset(tmp_path, stems=("H6_120HR_AA", "H6_120HR_AB")):
    crops_dir = tmp_path / "crops"
    crops_dir.mkdir()
    for stem in stems:
        _write_crop(crops_dir / f"{stem}_cropped.png")
    scale_csv = tmp_path / "scales.csv"
    _write_scale_csv(scale_csv, stems)
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    return crops_dir, scale_csv, output_dir


def test_run_button_requires_at_least_one_stage_enabled(qapp, tmp_path):
    _crops_dir, scale_csv, output_dir = _make_dataset(tmp_path)
    window = MainWindow()
    window.scales_file = str(scale_csv)
    window.crops_folder = str(_crops_dir)
    window.output_folder = str(output_dir)

    window.on_run()

    assert window.stack.currentIndex() == PAGE_SETUP  # never advanced


def test_mask_only_run_completes_and_advances_to_summary(qapp, tmp_path):
    crops_dir, scale_csv, output_dir = _make_dataset(tmp_path)
    window = MainWindow()
    window.scales_file = str(scale_csv)
    window.crops_folder = str(crops_dir)
    window.output_folder = str(output_dir)
    window.mask_tab.enabled_checkbox.setChecked(True)

    window.on_run()
    assert window.stack.currentIndex() == PAGE_MASK_RUN
    _run_mask_stage_to_completion(qapp, window)

    assert window.mask_stage_page.mask_result.masks_saved == 2
    window.mask_stage_page.on_continue()

    assert window.stack.currentIndex() == PAGE_SUMMARY
    summary_path = os.path.join(output_dir, "measure_summary.csv")
    assert os.path.exists(summary_path)
    with open(summary_path) as f:
        header = next(csv.reader(f))
    assert header[0] == "file_name"
    assert all(col.startswith("mask_") for col in header[1:])


def test_mask_stage_page_satisfies_review_dialog_contract(qapp, tmp_path):
    """Directly proves the duck-typed contract ReviewDialog/CorrectionDialog
    rely on (main_window.mask_result / ._crop_by_filename / .save_corrected_row)
    holds for MaskStagePage, without needing to drive either dialog's UI.
    """
    crops_dir, scale_csv, output_dir = _make_dataset(tmp_path, stems=("only_one",))
    window = MainWindow()
    window.scales_file = str(scale_csv)
    window.crops_folder = str(crops_dir)
    window.output_folder = str(output_dir)
    window.mask_tab.enabled_checkbox.setChecked(True)

    window.on_run()
    _run_mask_stage_to_completion(qapp, window)

    page = window.mask_stage_page
    assert page.mask_result.rows[0]["file_name"] == "only_one_cropped.png"
    crop = page._crop_by_filename["only_one_cropped.png"]
    assert crop is not None

    mask = np.zeros((10, 10), dtype=np.uint8)
    mask[2:8, 2:8] = 1
    page.save_corrected_row(0, crop, mask, {"length_mm": 1.0, "width_mm": 1.0}, "damage")

    assert page.mask_result.rows[0]["mask_status"] == "corrected"
    assert page.mask_result.rows[0]["tag"] == "damage"
    with open(page.mask_result.csv_path) as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["tag"] == "damage"


def test_all_three_enabled_auto_chains_masks_dir_from_mask_stage_output(qapp, tmp_path):
    crops_dir, scale_csv, output_dir = _make_dataset(tmp_path, stems=("H6_120HR_AA",))
    window = MainWindow()
    window.scales_file = str(scale_csv)
    window.crops_folder = str(crops_dir)
    window.output_folder = str(output_dir)
    window.mask_tab.enabled_checkbox.setChecked(True)
    window.segment_tab.enabled_checkbox.setChecked(True)
    window.landmark_tab.enabled_checkbox.setChecked(True)

    window.on_run()
    _run_mask_stage_to_completion(qapp, window)
    window.mask_stage_page.on_continue()

    # advanced into Segment's review with matched_items pointing at Mask's
    # own output folder -- proves auto-chaining actually happened, not
    # just got configured.
    assert window.segment_review.matched_items, "segment review never started"
    expected_masks_dir = os.path.join(str(output_dir), "masks")
    for item in window.segment_review.matched_items:
        assert item.mask_path is None or item.mask_path.startswith(expected_masks_dir)

    window.segment_review.on_close()
    assert window.landmark_review.matched_items, "landmark review never started"
    for item in window.landmark_review.matched_items:
        assert item.mask_path is None or item.mask_path.startswith(expected_masks_dir)

    window.landmark_review.on_close()
    assert window.stack.currentIndex() == PAGE_SUMMARY

    summary_path = os.path.join(output_dir, "measure_summary.csv")
    with open(summary_path) as f:
        header = next(csv.reader(f))
    assert any(col.startswith("mask_") for col in header)
    assert any(col.startswith("segment_") for col in header)
    assert any(col.startswith("landmark_") for col in header)


def test_mixed_batch_validation_blocks_run_until_every_object_id_assigned(qapp, tmp_path):
    crops_dir, scale_csv, output_dir = _make_dataset(tmp_path)
    window = MainWindow()
    window.scales_file = str(scale_csv)
    window.crops_folder = str(crops_dir)
    window.output_folder = str(output_dir)
    window.mask_tab.enabled_checkbox.setChecked(True)
    window.mask_tab.mixed_radio.setChecked(True)

    from segmetric.set.core.model import Preset, Segment

    window.metadata_preset = Preset(
        name="p", segments=[Segment(index=0, raw_value="", column_name="hive")], object_id_column="hive"
    )

    window.on_run()

    # blocked: mixed mode needs every discovered object id assigned to a
    # filter, which hasn't happened yet.
    assert window.stack.currentIndex() == PAGE_SETUP


def test_object_id_filter_checklist_refreshes_reactively_on_shared_folder_change(qapp, tmp_path):
    crops_dir, scale_csv, output_dir = _make_dataset(tmp_path, stems=("H6_120HR_AA", "H7_130HR_AB"))
    window = MainWindow()

    from segmetric.set.core.model import Preset, Segment

    window.metadata_preset = Preset(
        name="p",
        segments=[Segment(index=0, raw_value="", column_name="hive")],
        object_id_column="hive",
    )

    assert window.segment_tab.object_id_filter_group.isVisibleTo(window.segment_tab) is False

    window.scales_file = str(scale_csv)
    window.crops_folder = str(crops_dir)
    window._refresh_object_id_widgets()

    assert window.segment_tab.object_id_filter_group.isVisibleTo(window.segment_tab) is True
    assert set(window.segment_tab._object_id_checkboxes.keys()) == {"H6", "H7"}


def test_mask_and_segment_assignment_widgets_recognize_ids_before_run_is_clicked(qapp, tmp_path):
    """Regression test for the bug report: typing a real, discovered
    object id into Mask's (or Segment's) Mixed-mode ObjectIdAssignmentWidget
    used to be rejected as "not among the discovered object ids" unless
    Run had already been clicked once, because set_discovered_object_ids
    was only ever called from on_run(). It should now be recognized as
    soon as Folders/Metadata are set, with no Run click at all.
    """
    crops_dir, scale_csv, output_dir = _make_dataset(tmp_path, stems=("H6_120HR_AA", "H6_120HR_AB"))
    window = MainWindow()

    from segmetric.set.core.model import Preset, Segment

    window.metadata_preset = Preset(
        name="p", segments=[Segment(index=0, raw_value="", column_name="hive")], object_id_column="hive"
    )
    window.scales_file = str(scale_csv)
    window.crops_folder = str(crops_dir)
    window._refresh_object_id_widgets()

    window.mask_tab.mixed_radio.setChecked(True)
    mask_row = window.mask_tab.object_id_widget.add_group()
    mask_row.set_object_ids(["H6"])
    window.mask_tab.object_id_widget._update_coverage()
    assert window.mask_tab.object_id_widget.is_ready() is True
    assert "Not among the discovered object ids" not in window.mask_tab.object_id_widget.coverage_label.text()

    window.segment_tab.mixed_radio.setChecked(True)
    segment_row = window.segment_tab.object_id_widget.add_group()
    segment_row.set_object_ids(["H6"])
    window.segment_tab.object_id_widget._update_coverage()
    assert window.segment_tab.object_id_widget.is_ready() is True
    assert (
        "Not among the discovered object ids"
        not in window.segment_tab.object_id_widget.coverage_label.text()
    )
