import csv
import os

import cv2
import pytest

from segmetric.mask.core.matching import match_crops_to_scale_rows
from segmetric.mask.core.model import DEFAULT_FILTERS
from segmetric.mask.core.pipeline import run_mask_job
from segmetric.set.core.model import Preset, Segment

from test_mask_masking import make_blob_image


def _write_crop(path):
    image, _center, _axes = make_blob_image()
    cv2.imwrite(str(path), image)


def _write_scale_csv(path, stems, mm_per_pixel=0.02):
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["file_name", "mm_per_pixel", "scale_source"])
        for stem in stems:
            writer.writerow([f"{stem}.png", mm_per_pixel, "measured"])


def _object_id_preset():
    # Stem "H6_120HR_34C_NR_1004_AA" -> ["H6","120HR","34C","NR","1004","AA"]
    return Preset(
        name="test",
        segments=[
            Segment(index=0, raw_value="", column_name="Colony", include=True),
            Segment(index=5, raw_value="", column_name="ObjectID", include=True),
        ],
        object_id_column="ObjectID",
    )


def _setup_batch(tmp_path, stems):
    crops_dir = tmp_path / "crops"
    crops_dir.mkdir()
    for stem in stems:
        _write_crop(crops_dir / f"{stem}_cropped.png")

    scale_csv = tmp_path / "scales.csv"
    _write_scale_csv(scale_csv, stems)

    matched, unmatched = match_crops_to_scale_rows(str(crops_dir), str(scale_csv))
    assert unmatched == []
    return matched


def test_single_filter_batch_with_no_preset_writes_base_columns_only(tmp_path):
    matched = _setup_batch(tmp_path, ["H6_120HR_34C_NR_1004_AA", "H6_120HR_34C_NR_1004_AB"])
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    result = run_mask_job(
        matched, DEFAULT_FILTERS["Forewing"], str(output_dir), metadata_preset=None
    )

    assert result.masks_saved == 2
    assert result.skipped == []
    assert os.path.isdir(result.masks_dir)
    assert os.path.exists(result.csv_path)

    with open(result.csv_path) as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 2
    assert set(rows[0].keys()) == {
        "file_name", "length_px", "width_px", "length_mm", "width_mm",
        "area_px", "area_mm2", "mask_status", "tag",
    }
    assert all(row["mask_status"] == "auto" for row in rows)
    assert all(row["tag"] == "" for row in rows)


def test_single_filter_batch_with_preset_adds_metadata_object_id_and_filter_used(tmp_path):
    matched = _setup_batch(tmp_path, ["H6_120HR_34C_NR_1004_AA"])
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    result = run_mask_job(
        matched, DEFAULT_FILTERS["Leg"], str(output_dir), metadata_preset=_object_id_preset()
    )

    with open(result.csv_path) as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1
    row = rows[0]
    assert row["Colony"] == "H6"
    assert row["ObjectID"] == "AA"
    assert row["object_id"] == "AA"
    assert row["filter_used"] == "Leg"


def test_mixed_anatomy_batch_resolves_filter_per_object_id(tmp_path):
    matched = _setup_batch(
        tmp_path, ["H6_120HR_34C_NR_1004_AA", "H6_120HR_34C_NR_1004_AB"]
    )
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    filter_resolver = {"AA": DEFAULT_FILTERS["Forewing"], "AB": DEFAULT_FILTERS["Hindwing"]}
    result = run_mask_job(
        matched, filter_resolver, str(output_dir), metadata_preset=_object_id_preset()
    )

    assert result.masks_saved == 2
    assert result.skipped == []

    with open(result.csv_path) as f:
        rows_by_id = {row["object_id"]: row for row in csv.DictReader(f)}
    assert rows_by_id["AA"]["filter_used"] == "Forewing"
    assert rows_by_id["AB"]["filter_used"] == "Hindwing"


def test_mixed_anatomy_batch_flags_unassigned_object_id_instead_of_crashing(tmp_path):
    matched = _setup_batch(
        tmp_path, ["H6_120HR_34C_NR_1004_AA", "H6_120HR_34C_NR_1004_AC"]
    )
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    filter_resolver = {"AA": DEFAULT_FILTERS["Forewing"]}  # "AC" has no entry
    result = run_mask_job(
        matched, filter_resolver, str(output_dir), metadata_preset=_object_id_preset()
    )

    assert result.masks_saved == 1
    assert len(result.skipped) == 1
    skipped_name, reason = result.skipped[0]
    assert "AC" in skipped_name
    assert "AC" in reason


def test_mixed_anatomy_batch_without_preset_skips_everything(tmp_path):
    matched = _setup_batch(tmp_path, ["H6_120HR_34C_NR_1004_AA"])
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    filter_resolver = {"AA": DEFAULT_FILTERS["Forewing"]}
    result = run_mask_job(matched, filter_resolver, str(output_dir), metadata_preset=None)

    assert result.masks_saved == 0
    assert len(result.skipped) == 1


def test_stop_after_first_item_writes_partial_csv(tmp_path):
    matched = _setup_batch(
        tmp_path, ["H6_120HR_34C_NR_1004_AA", "H6_120HR_34C_NR_1004_AB"]
    )
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    calls = {"n": 0}

    def stop_after_first():
        calls["n"] += 1
        return calls["n"] > 1

    result = run_mask_job(
        matched, DEFAULT_FILTERS["Forewing"], str(output_dir),
        metadata_preset=None, should_stop=stop_after_first,
    )

    assert result.interrupted is True
    assert result.masks_saved == 1
    assert os.path.exists(result.csv_path)
