import csv
import os

import cv2
import numpy as np
import pytest

from segmetric.measure.core.pipeline import (
    build_mask_batch,
    build_segment_or_landmark_batch,
    enabled_stage_order,
    resolve_masks_dir,
)


def _write_image(path):
    cv2.imwrite(str(path), np.full((20, 20, 3), 200, dtype=np.uint8))


def _write_scale_csv(path, rows):
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["file_name", "mm_per_pixel", "scale_source"])
        for row in rows:
            writer.writerow(row)


# --------------------------------------------------------- build_mask_batch
def test_build_mask_batch_delegates_to_mask_matching(tmp_path):
    crops_dir = tmp_path / "crops"
    crops_dir.mkdir()
    _write_image(crops_dir / "panel_01_cropped.tiff")

    scale_csv = tmp_path / "scales.csv"
    _write_scale_csv(scale_csv, [("panel_01.png", "0.0118", "measured")])

    matched, unmatched = build_mask_batch(str(scale_csv), str(crops_dir))

    assert unmatched == []
    assert len(matched) == 1
    assert matched[0].original_stem == "panel_01"
    assert matched[0].mm_per_pixel == pytest.approx(0.0118)


# ------------------------------------------- build_segment_or_landmark_batch
def test_build_segment_or_landmark_batch_delegates_to_segment_matching(tmp_path):
    crops_dir = tmp_path / "crops"
    crops_dir.mkdir()
    _write_image(crops_dir / "panel_01_cropped.tiff")

    scale_csv = tmp_path / "scales.csv"
    _write_scale_csv(scale_csv, [("panel_01.png", "0.02", "measured")])

    matched, unmatched, no_mask = build_segment_or_landmark_batch(
        str(scale_csv), str(crops_dir), None, True
    )

    assert unmatched == []
    assert no_mask == []  # masks_dir wasn't given, so no_mask stays empty
    assert len(matched) == 1
    assert matched[0].original_stem == "panel_01"
    assert matched[0].mask_path is None


def test_build_segment_or_landmark_batch_reports_missing_masks(tmp_path):
    crops_dir = tmp_path / "crops"
    crops_dir.mkdir()
    _write_image(crops_dir / "panel_01_cropped.tiff")
    masks_dir = tmp_path / "masks"
    masks_dir.mkdir()  # empty -- no mask for panel_01

    scale_csv = tmp_path / "scales.csv"
    _write_scale_csv(scale_csv, [("panel_01.png", "0.02", "measured")])

    matched, unmatched, no_mask = build_segment_or_landmark_batch(
        str(scale_csv), str(crops_dir), str(masks_dir), True
    )

    assert len(matched) == 1
    assert no_mask == ["panel_01_cropped.tiff"]


# ------------------------------------------------------------ resolve_masks_dir
def test_resolve_masks_dir_auto_chains_when_mask_stage_enabled(tmp_path):
    result = resolve_masks_dir(str(tmp_path), True, None)
    assert result == os.path.join(str(tmp_path), "masks")


def test_resolve_masks_dir_auto_chains_even_over_an_explicit_value(tmp_path):
    # Mask enabled this run always wins -- nothing else could have masks yet.
    result = resolve_masks_dir(str(tmp_path), True, "/some/other/folder")
    assert result == os.path.join(str(tmp_path), "masks")


def test_resolve_masks_dir_falls_back_to_explicit_when_mask_disabled(tmp_path):
    result = resolve_masks_dir(str(tmp_path), False, "/explicit/masks")
    assert result == "/explicit/masks"


def test_resolve_masks_dir_returns_none_when_disabled_and_no_explicit(tmp_path):
    assert resolve_masks_dir(str(tmp_path), False, None) is None
    assert resolve_masks_dir(str(tmp_path), False, "") is None


# ------------------------------------------------------------ enabled_stage_order
@pytest.mark.parametrize(
    "mask_on,segment_on,landmark_on,expected",
    [
        (False, False, False, []),
        (True, False, False, ["mask"]),
        (False, True, False, ["segment"]),
        (False, False, True, ["landmark"]),
        (True, True, False, ["mask", "segment"]),
        (True, False, True, ["mask", "landmark"]),
        (False, True, True, ["segment", "landmark"]),
        (True, True, True, ["mask", "segment", "landmark"]),
    ],
)
def test_enabled_stage_order_respects_fixed_order(mask_on, segment_on, landmark_on, expected):
    assert enabled_stage_order(mask_on, segment_on, landmark_on) == expected
