import csv
import os

import cv2
import numpy as np
import pytest

from segmetric.errors import SegMetricError
from segmetric.segment.core.matching import match_crops


def _write_image(path):
    cv2.imwrite(str(path), np.full((20, 20, 3), 200, dtype=np.uint8))


def _write_scale_csv(path, stems):
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["file_name", "mm_per_pixel", "scale_source"])
        for stem in stems:
            writer.writerow([f"{stem}.png", "0.02", "measured"])


def test_matches_crop_to_scale_row_with_no_masks_dir(tmp_path):
    crops_dir = tmp_path / "crops"
    crops_dir.mkdir()
    _write_image(crops_dir / "panel_01_cropped.tiff")
    scale_csv = tmp_path / "scales.csv"
    _write_scale_csv(scale_csv, ["panel_01"])

    matched, unmatched, no_mask = match_crops(str(crops_dir), str(scale_csv))

    assert unmatched == []
    assert no_mask == []
    assert len(matched) == 1
    assert matched[0].original_stem == "panel_01"
    assert matched[0].mm_per_pixel == pytest.approx(0.02)
    assert matched[0].mask_path is None
    assert matched[0].mask_tag == ""


def test_matches_untagged_mask(tmp_path):
    crops_dir = tmp_path / "crops"
    crops_dir.mkdir()
    _write_image(crops_dir / "panel_01_cropped.png")
    scale_csv = tmp_path / "scales.csv"
    _write_scale_csv(scale_csv, ["panel_01"])
    masks_dir = tmp_path / "masks"
    masks_dir.mkdir()
    mask_path = masks_dir / "panel_01_mask.png"
    mask_path.write_bytes(b"x")

    matched, unmatched, no_mask = match_crops(str(crops_dir), str(scale_csv), str(masks_dir))

    assert len(matched) == 1
    assert matched[0].mask_path == str(mask_path)
    assert matched[0].mask_tag == ""
    assert no_mask == []


def test_damage_tagged_mask_is_used_as_is(tmp_path):
    crops_dir = tmp_path / "crops"
    crops_dir.mkdir()
    _write_image(crops_dir / "panel_01_cropped.png")
    scale_csv = tmp_path / "scales.csv"
    _write_scale_csv(scale_csv, ["panel_01"])
    masks_dir = tmp_path / "masks"
    masks_dir.mkdir()
    mask_path = masks_dir / "panel_01_damage_mask.png"
    mask_path.write_bytes(b"x")

    matched, _unmatched, no_mask = match_crops(str(crops_dir), str(scale_csv), str(masks_dir))

    assert len(matched) == 1
    assert matched[0].mask_path == str(mask_path)
    assert matched[0].mask_tag == "damage"
    assert no_mask == []


def test_blank_tagged_mask_excluded_by_default(tmp_path):
    crops_dir = tmp_path / "crops"
    crops_dir.mkdir()
    _write_image(crops_dir / "panel_01_cropped.png")
    _write_image(crops_dir / "panel_02_cropped.png")
    scale_csv = tmp_path / "scales.csv"
    _write_scale_csv(scale_csv, ["panel_01", "panel_02"])
    masks_dir = tmp_path / "masks"
    masks_dir.mkdir()
    (masks_dir / "panel_01_blank_mask.png").write_bytes(b"x")
    (masks_dir / "panel_02_mask.png").write_bytes(b"x")

    matched, _unmatched, _no_mask = match_crops(str(crops_dir), str(scale_csv), str(masks_dir))

    stems = {item.original_stem for item in matched}
    assert stems == {"panel_02"}


def test_blank_tagged_mask_includable_via_toggle(tmp_path):
    crops_dir = tmp_path / "crops"
    crops_dir.mkdir()
    _write_image(crops_dir / "panel_01_cropped.png")
    scale_csv = tmp_path / "scales.csv"
    _write_scale_csv(scale_csv, ["panel_01"])
    masks_dir = tmp_path / "masks"
    masks_dir.mkdir()
    mask_path = masks_dir / "panel_01_blank_mask.png"
    mask_path.write_bytes(b"x")

    matched, _unmatched, no_mask = match_crops(
        str(crops_dir), str(scale_csv), str(masks_dir), exclude_blank_tagged=False
    )

    assert len(matched) == 1
    assert matched[0].mask_path == str(mask_path)
    assert matched[0].mask_tag == "blank"
    assert no_mask == []


def test_no_mask_available_is_flagged_not_dropped(tmp_path):
    crops_dir = tmp_path / "crops"
    crops_dir.mkdir()
    _write_image(crops_dir / "panel_01_cropped.png")
    scale_csv = tmp_path / "scales.csv"
    _write_scale_csv(scale_csv, ["panel_01"])
    masks_dir = tmp_path / "masks"
    masks_dir.mkdir()  # empty -- no mask for panel_01

    matched, _unmatched, no_mask = match_crops(str(crops_dir), str(scale_csv), str(masks_dir))

    assert len(matched) == 1
    assert matched[0].mask_path is None
    assert no_mask == ["panel_01_cropped.png"]


def test_unmatched_crop_flagged_when_no_scale_row(tmp_path):
    crops_dir = tmp_path / "crops"
    crops_dir.mkdir()
    _write_image(crops_dir / "no_scale_cropped.png")
    scale_csv = tmp_path / "scales.csv"
    _write_scale_csv(scale_csv, ["something_else"])

    matched, unmatched, _no_mask = match_crops(str(crops_dir), str(scale_csv))

    assert matched == []
    assert unmatched == ["no_scale_cropped.png"]


def test_scale_csv_missing_columns_raises(tmp_path):
    crops_dir = tmp_path / "crops"
    crops_dir.mkdir()
    _write_image(crops_dir / "a_cropped.png")
    scale_csv = tmp_path / "bad.csv"
    with open(scale_csv, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["nope", "nada"])
        writer.writerow(["a", "0.02"])

    with pytest.raises(SegMetricError):
        match_crops(str(crops_dir), str(scale_csv))
