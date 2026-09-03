import csv
import os

import cv2
import numpy as np
import pytest

from segmetric.scale.core.manual import clamp_bbox, compute_manual_scale, crop_to_region
from segmetric.scale.core.pipeline import (
    SCALE_SOURCE_MANUAL,
    SCALE_SOURCE_MANUAL_BATCH,
    run_manual_scale_job,
)


def test_compute_manual_scale_known_points_and_distance():
    # (0,0) to (100,0): 100px apart, told that's 20mm -> 0.2 mm/px.
    mm_per_pixel = compute_manual_scale((0, 0), (100, 0), 20.0)
    assert mm_per_pixel == pytest.approx(0.2)


def test_compute_manual_scale_diagonal_distance():
    # 3-4-5 triangle -- 5px apart.
    mm_per_pixel = compute_manual_scale((0, 0), (3, 4), 10.0)
    assert mm_per_pixel == pytest.approx(2.0)


def test_compute_manual_scale_coincident_points_returns_none():
    assert compute_manual_scale((10, 10), (10, 10), 20.0) is None


def test_compute_manual_scale_nonpositive_distance_returns_none():
    assert compute_manual_scale((0, 0), (100, 0), 0.0) is None
    assert compute_manual_scale((0, 0), (100, 0), -5.0) is None
    assert compute_manual_scale((0, 0), (100, 0), None) is None


def test_clamp_bbox_orders_reversed_corners():
    assert clamp_bbox((50, 60, 10, 20), width=200, height=200) == (10, 20, 50, 60)


def test_clamp_bbox_clamps_to_image_bounds():
    assert clamp_bbox((-10, -10, 300, 300), width=200, height=150) == (0, 0, 200, 150)


def test_clamp_bbox_never_returns_degenerate_box():
    # Grows forward by 1px when there's room.
    assert clamp_bbox((50, 50, 50, 50), width=200, height=200) == (50, 50, 51, 51)
    # Degenerate right at the image edge has no room to grow forward, so it
    # grows backward instead -- still a 1px box, still within bounds.
    assert clamp_bbox((200, 200, 200, 200), width=200, height=200) == (199, 199, 200, 200)


def test_crop_to_region_slices_expected_area():
    image = np.arange(100 * 100 * 3, dtype=np.uint8).reshape(100, 100, 3)
    cropped = crop_to_region(image, (10, 20, 40, 60))
    assert cropped.shape == (40, 30, 3)
    assert np.array_equal(cropped, image[20:60, 10:40])


def _write_image(path, width=100, height=80):
    image = np.full((height, width, 3), 200, dtype=np.uint8)
    cv2.imwrite(str(path), image)


def test_run_manual_scale_job_batch_broadcast_scale_and_shared_crop(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    stems = ["a", "b"]
    for stem in stems:
        _write_image(input_dir / f"{stem}.png")
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    scale_by_name = {f"{stem}.png": 0.05 for stem in stems}
    scale_source_by_name = {f"{stem}.png": SCALE_SOURCE_MANUAL_BATCH for stem in stems}
    crop_bbox_by_name = {f"{stem}.png": (10, 10, 60, 50) for stem in stems}

    result = run_manual_scale_job(
        str(input_dir), str(output_dir), scale_by_name, scale_source_by_name, crop_bbox_by_name,
    )

    assert result.files_skipped == []
    assert set(result.files_processed) == {"a.png", "b.png"}
    assert result.panels_cropped == 2

    for stem in stems:
        cropped = cv2.imread(os.path.join(result.output_dir, f"{stem}_cropped.tiff"))
        assert cropped.shape == (40, 50, 3)  # (60-10) wide, (50-10) tall

    with open(os.path.join(result.output_dir, "scales.csv")) as f:
        rows = {row["file_name"]: row for row in csv.DictReader(f)}
    assert rows["a.png"]["scale_source"] == "manual_batch"
    assert float(rows["a.png"]["mm_per_pixel"]) == pytest.approx(0.05)


def test_run_manual_scale_job_per_image_scale_and_no_crop(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    _write_image(input_dir / "a.png", width=100, height=80)
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    scale_by_name = {"a.png": 0.03}
    scale_source_by_name = {"a.png": SCALE_SOURCE_MANUAL}

    result = run_manual_scale_job(
        str(input_dir), str(output_dir), scale_by_name, scale_source_by_name, None,
    )

    assert result.files_processed == ["a.png"]
    cropped = cv2.imread(os.path.join(result.output_dir, "a_cropped.tiff"))
    assert cropped.shape == (80, 100, 3)  # unchanged -- no crop at all

    with open(os.path.join(result.output_dir, "scales.csv")) as f:
        rows = {row["file_name"]: row for row in csv.DictReader(f)}
    assert rows["a.png"]["scale_source"] == "manual"


def test_run_manual_scale_job_file_missing_scale_is_skipped_not_fatal(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    _write_image(input_dir / "a.png")
    _write_image(input_dir / "b.png")
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    # Only "a.png" has a scale -- "b.png" should be skipped, not crash the batch.
    scale_by_name = {"a.png": 0.05}
    scale_source_by_name = {"a.png": SCALE_SOURCE_MANUAL}

    result = run_manual_scale_job(
        str(input_dir), str(output_dir), scale_by_name, scale_source_by_name, None,
    )

    assert result.files_processed == ["a.png"]
    assert len(result.files_skipped) == 1
    assert result.files_skipped[0][0] == "b.png"
