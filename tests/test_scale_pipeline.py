import csv
import os

import cv2
import numpy as np
import pytest

from segmetric.errors import SegMetricError
from segmetric.scale.core.model import ScaleSettings
from segmetric.scale.core.pipeline import (
    SCALE_SOURCE_BATCH_MEDIAN,
    SCALE_SOURCE_MEASURED,
    SCALE_SOURCE_PAGE_MEDIAN,
    run_scale_job,
)

from test_scale_core import make_square_marker_image


def _write(path, image):
    cv2.imwrite(str(path), image)


def test_batch_median_fallback_is_flagged_in_csv(tmp_path):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    output_dir.mkdir()

    # Two images with a clean, detectable 4-marker square (scale computable).
    _write(input_dir / "good_a.png", make_square_marker_image(spacing_px=900))
    _write(input_dir / "good_b.png", make_square_marker_image(spacing_px=950))
    # 3 markers: enough to prepare (needs 3) but not enough to measure
    # directly (needs 4) -- scale must fall back to the median.
    _write(input_dir / "bad_c.png", make_square_marker_image(n_markers=3))

    result = run_scale_job(str(input_dir), str(output_dir), settings=ScaleSettings())

    rows_by_name = {name: (mm, source) for name, mm, source in result.scale_rows}

    assert rows_by_name["good_a.png"][1] == SCALE_SOURCE_MEASURED
    assert rows_by_name["good_b.png"][1] == SCALE_SOURCE_MEASURED
    assert rows_by_name["bad_c.png"][1] == SCALE_SOURCE_BATCH_MEDIAN

    expected_median = np.median([rows_by_name["good_a.png"][0], rows_by_name["good_b.png"][0]])
    assert rows_by_name["bad_c.png"][0] == pytest.approx(expected_median)

    # scales.csv on disk matches result.scale_rows
    csv_path = os.path.join(result.output_dir, "scales.csv")
    with open(csv_path) as f:
        reader = csv.DictReader(f)
        csv_rows = {row["file_name"]: row["scale_source"] for row in reader}
    assert csv_rows["bad_c.png"] == SCALE_SOURCE_BATCH_MEDIAN
    assert csv_rows["good_a.png"] == SCALE_SOURCE_MEASURED


def test_bad_image_still_gets_cropped_using_fallback_scale(tmp_path):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    output_dir.mkdir()

    _write(input_dir / "good_a.png", make_square_marker_image(spacing_px=900))
    # 3 markers: enough to prepare (needs 3) and crop (needs 2), but not
    # enough to measure scale directly (needs 4).
    _write(input_dir / "bad_b.png", make_square_marker_image(n_markers=3))

    result = run_scale_job(str(input_dir), str(output_dir), settings=ScaleSettings())

    assert "bad_b.png" in result.files_processed
    assert result.panels_cropped == 2


def test_cropped_output_defaults_to_tiff(tmp_path):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    output_dir.mkdir()

    _write(input_dir / "good_a.png", make_square_marker_image(spacing_px=900))

    result = run_scale_job(str(input_dir), str(output_dir), settings=ScaleSettings())

    saved = os.listdir(result.output_dir)
    assert any(name.endswith("_cropped.tiff") for name in saved)
    assert not any(name.endswith("_cropped.png") for name in saved)


def test_cropped_output_format_can_be_png(tmp_path):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    output_dir.mkdir()

    _write(input_dir / "good_a.png", make_square_marker_image(spacing_px=900))

    result = run_scale_job(
        str(input_dir), str(output_dir), settings=ScaleSettings(), output_format="png"
    )

    saved = os.listdir(result.output_dir)
    assert any(name.endswith("_cropped.png") for name in saved)
    assert not any(name.endswith("_cropped.tiff") for name in saved)


def test_no_valid_scales_raises_segmetric_error(tmp_path):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    output_dir.mkdir()

    _write(input_dir / "bad_a.png", make_square_marker_image(n_markers=1))

    with pytest.raises(SegMetricError):
        run_scale_job(str(input_dir), str(output_dir), settings=ScaleSettings())


def test_group_size_none_matches_flat_whole_batch_behavior(tmp_path):
    """Default (group_size=None) must be byte-for-byte the notebook's
    original whole-batch median -- the standalone segmetric-scale path.
    """
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    output_dir.mkdir()

    _write(input_dir / "good_a.png", make_square_marker_image(spacing_px=900))
    _write(input_dir / "good_b.png", make_square_marker_image(spacing_px=950))
    _write(input_dir / "bad_c.png", make_square_marker_image(n_markers=3))

    result = run_scale_job(str(input_dir), str(output_dir), settings=ScaleSettings(), group_size=None)
    rows_by_name = {name: (mm, source) for name, mm, source in result.scale_rows}
    assert rows_by_name["bad_c.png"][1] == SCALE_SOURCE_BATCH_MEDIAN


def test_grouped_median_uses_own_page_not_whole_batch(tmp_path):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    output_dir.mkdir()

    # Page 1 (group of 2): one measurable (spacing 400), one that fails
    # (3 markers -- enough to prepare, not enough to measure directly).
    _write(input_dir / "page1_a.png", make_square_marker_image(spacing_px=900))
    _write(input_dir / "page1_b.png", make_square_marker_image(n_markers=3))
    # Page 2 (group of 2): one measurable at a deliberately different
    # spacing (200, roughly double the scale of page 1), one that fails.
    _write(input_dir / "page2_a.png", make_square_marker_image(spacing_px=1800))
    _write(input_dir / "page2_b.png", make_square_marker_image(n_markers=3))

    result = run_scale_job(
        str(input_dir), str(output_dir), settings=ScaleSettings(), group_size=2
    )
    rows_by_name = {name: (mm, source) for name, mm, source in result.scale_rows}

    # Each failed image gets its OWN page's measured value, not a median
    # blended across both pages.
    assert rows_by_name["page1_b.png"][1] == SCALE_SOURCE_PAGE_MEDIAN
    assert rows_by_name["page1_b.png"][0] == pytest.approx(rows_by_name["page1_a.png"][0])
    assert rows_by_name["page2_b.png"][1] == SCALE_SOURCE_PAGE_MEDIAN
    assert rows_by_name["page2_b.png"][0] == pytest.approx(rows_by_name["page2_a.png"][0])

    # The two pages' fallback values are meaningfully different from each
    # other -- proof grouping actually happened, not a flat batch median.
    assert rows_by_name["page1_b.png"][0] != pytest.approx(rows_by_name["page2_b.png"][0], rel=0.05)


def test_grouped_median_falls_back_to_batch_when_whole_page_fails(tmp_path):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    output_dir.mkdir()

    # Page 1 (group of 2): both measurable.
    _write(input_dir / "page1_a.png", make_square_marker_image(spacing_px=900))
    _write(input_dir / "page1_b.png", make_square_marker_image(spacing_px=920))
    # Page 2 (group of 2): both fail -- no measurement anywhere on this
    # page (3 markers -- enough to prepare, not enough to measure directly).
    _write(input_dir / "page2_a.png", make_square_marker_image(n_markers=3))
    _write(input_dir / "page2_b.png", make_square_marker_image(n_markers=3))

    result = run_scale_job(
        str(input_dir), str(output_dir), settings=ScaleSettings(), group_size=2
    )
    rows_by_name = {name: (mm, source) for name, mm, source in result.scale_rows}

    whole_batch_median = np.median([rows_by_name["page1_a.png"][0], rows_by_name["page1_b.png"][0]])
    assert rows_by_name["page2_a.png"][1] == SCALE_SOURCE_BATCH_MEDIAN
    assert rows_by_name["page2_b.png"][1] == SCALE_SOURCE_BATCH_MEDIAN
    assert rows_by_name["page2_a.png"][0] == pytest.approx(whole_batch_median)


def test_stop_during_pass_one_writes_partial_csv_and_skips_pass_two(tmp_path):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    output_dir.mkdir()

    _write(input_dir / "a.png", make_square_marker_image(spacing_px=900))
    _write(input_dir / "b.png", make_square_marker_image(spacing_px=940))

    calls = {"n": 0}

    def stop_after_first_file():
        calls["n"] += 1
        return calls["n"] > 1

    result = run_scale_job(
        str(input_dir), str(output_dir), settings=ScaleSettings(), should_stop=stop_after_first_file
    )

    assert result.interrupted is True
    assert result.panels_cropped == 0
    assert len(result.scale_rows) == 1
