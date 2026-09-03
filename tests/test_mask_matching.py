import csv
import os

import cv2
import numpy as np
import pytest

from segmetric.errors import SegMetricError
from segmetric.mask.core.matching import match_crops_to_scale_rows


def _write_image(path):
    cv2.imwrite(str(path), np.full((20, 20, 3), 200, dtype=np.uint8))


def _write_scale_csv(path, rows):
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["file_name", "mm_per_pixel", "scale_source"])
        for row in rows:
            writer.writerow(row)


def test_matches_a_cropped_file_to_its_original_scale_row(tmp_path):
    crops_dir = tmp_path / "crops"
    crops_dir.mkdir()
    _write_image(crops_dir / "panel_01_20260101_000000_cropped.tiff")

    scale_csv = tmp_path / "scales.csv"
    _write_scale_csv(scale_csv, [("panel_01_20260101_000000.png", "0.0118", "measured")])

    matched, unmatched = match_crops_to_scale_rows(str(crops_dir), str(scale_csv))

    assert unmatched == []
    assert len(matched) == 1
    item = matched[0]
    assert item.original_stem == "panel_01_20260101_000000"
    assert item.mm_per_pixel == pytest.approx(0.0118)
    assert item.scale_source == "measured"


def test_accepts_summary_csv_with_extra_metadata_columns(tmp_path):
    crops_dir = tmp_path / "crops"
    crops_dir.mkdir()
    _write_image(crops_dir / "H6_120HR_AA_cropped.png")

    scale_csv = tmp_path / "summary.csv"
    with open(scale_csv, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["file_name", "mm_per_pixel", "scale_source", "Colony"])
        writer.writerow(["H6_120HR_AA.png", "0.02", "measured", "H6"])

    matched, unmatched = match_crops_to_scale_rows(str(crops_dir), str(scale_csv))
    assert len(matched) == 1
    assert unmatched == []


def test_unmatched_crop_is_flagged_not_dropped_silently(tmp_path):
    crops_dir = tmp_path / "crops"
    crops_dir.mkdir()
    _write_image(crops_dir / "no_scale_row_cropped.png")

    scale_csv = tmp_path / "scales.csv"
    _write_scale_csv(scale_csv, [("something_else.png", "0.02", "measured")])

    matched, unmatched = match_crops_to_scale_rows(str(crops_dir), str(scale_csv))
    assert matched == []
    assert unmatched == ["no_scale_row_cropped.png"]


def test_crop_without_cropped_suffix_still_matches_by_stem(tmp_path):
    crops_dir = tmp_path / "crops"
    crops_dir.mkdir()
    _write_image(crops_dir / "panel_02.png")

    scale_csv = tmp_path / "scales.csv"
    _write_scale_csv(scale_csv, [("panel_02.png", "0.015", "measured")])

    matched, unmatched = match_crops_to_scale_rows(str(crops_dir), str(scale_csv))
    assert len(matched) == 1
    assert matched[0].original_stem == "panel_02"


def test_scale_csv_missing_required_columns_raises_segmetric_error(tmp_path):
    crops_dir = tmp_path / "crops"
    crops_dir.mkdir()
    _write_image(crops_dir / "a_cropped.png")

    scale_csv = tmp_path / "bad.csv"
    with open(scale_csv, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["not_file_name", "not_mm_per_pixel"])
        writer.writerow(["a.png", "0.02"])

    with pytest.raises(SegMetricError):
        match_crops_to_scale_rows(str(crops_dir), str(scale_csv))


def test_empty_crops_folder_raises_segmetric_error(tmp_path):
    crops_dir = tmp_path / "crops"
    crops_dir.mkdir()
    scale_csv = tmp_path / "scales.csv"
    _write_scale_csv(scale_csv, [])

    with pytest.raises(SegMetricError):
        match_crops_to_scale_rows(str(crops_dir), str(scale_csv))
