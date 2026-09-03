import csv
import os

import cv2
import numpy as np
import pytest

from segmetric.prepare.core.pipeline import run_prepare_job
from segmetric.scale.core.model import ScaleSettings
from segmetric.tag.core.naming import OcrRegion

from test_scale_core import make_square_marker_image


def _write(path, image):
    cv2.imwrite(str(path), image)


def make_split_source_image(good_spacing_px, marker_size=80, half_size=None):
    """A (2*half_size) x half_size canvas: left half has a detectable
    4-marker square at good_spacing_px (measurable directly), right half
    has only 3 markers -- enough to pass the prepare step (needs 3) but not
    enough to measure scale directly (needs 4) -- so splitting this 1 row x
    2 cols produces one measurable panel (left, index 1) and one that needs
    the page-median fallback (right, index 2).

    half_size defaults to generously larger than the marker spread (same
    rule as make_square_marker_image's own auto-sizing) so markers stay
    comfortably under maxMarkerPerimeterRate's limit after prepare_image
    crops tight and upscales 2x.
    """
    if half_size is None:
        half_size = good_spacing_px + marker_size * 3
    left = make_square_marker_image(
        spacing_px=good_spacing_px, marker_size=marker_size, canvas_size=half_size
    )
    right = make_square_marker_image(
        spacing_px=good_spacing_px, marker_size=marker_size, canvas_size=half_size, n_markers=3
    )
    return np.hstack([left, right])


def default_kwargs():
    return dict(
        rows=1,
        cols=1,
        use_cv_naming=False,
        ocr_region=OcrRegion(),
        gpu=True,
        output_format="png",
        scale_settings=ScaleSettings(),
    )


def test_full_run_produces_panels_scale_and_summary(tmp_path):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    output_dir.mkdir()

    _write(input_dir / "scan_a.png", make_square_marker_image(spacing_px=900))
    _write(input_dir / "scan_b.png", make_square_marker_image(spacing_px=950))

    result = run_prepare_job(str(input_dir), str(output_dir), **default_kwargs())

    assert result.interrupted is False
    assert result.panels_saved == 2
    assert result.panels_cropped == 2
    assert os.path.isdir(os.path.join(output_dir, "panels"))
    assert os.path.isdir(os.path.join(output_dir, "scale"))
    assert os.path.exists(result.summary_csv_path)

    with open(result.summary_csv_path) as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 2
    assert {row["scale_source"] for row in rows} == {"measured"}


def test_cropped_output_defaults_to_tiff_and_can_be_png(tmp_path):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    output_dir.mkdir()
    _write(input_dir / "scan_a.png", make_square_marker_image(spacing_px=900))

    result = run_prepare_job(str(input_dir), str(output_dir), **default_kwargs())
    saved = os.listdir(os.path.join(output_dir, "scale"))
    assert any(name.endswith("_cropped.tiff") for name in saved)

    output_dir_2 = tmp_path / "output_png"
    output_dir_2.mkdir()
    result = run_prepare_job(
        str(input_dir), str(output_dir_2), crop_output_format="png", **default_kwargs()
    )
    saved_2 = os.listdir(os.path.join(output_dir_2, "scale"))
    assert any(name.endswith("_cropped.png") for name in saved_2)


def test_stop_during_tag_stage_skips_scale_entirely(tmp_path):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    output_dir.mkdir()

    _write(input_dir / "scan_a.png", make_square_marker_image(spacing_px=900))

    result = run_prepare_job(
        str(input_dir), str(output_dir), should_stop=lambda: True, **default_kwargs()
    )

    assert result.interrupted is True
    assert result.interrupted_during == "tag"
    assert result.panels_cropped == 0
    assert not os.path.isdir(os.path.join(output_dir, "scale"))
    assert result.summary_csv_path == ""


def test_stop_during_scale_stage_still_reports_correctly(tmp_path):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    output_dir.mkdir()

    _write(input_dir / "scan_a.png", make_square_marker_image(spacing_px=900))

    # Robust stop trigger: scale's pipeline creates <output>/scale/ before its
    # own first per-file check, so tag always finishes untouched, and scale
    # is interrupted right at its first checkpoint -- independent of exactly
    # how many times should_stop happens to get called internally.
    scale_dir = os.path.join(str(output_dir), "scale")

    def stop_once_scale_starts():
        return os.path.isdir(scale_dir)

    result = run_prepare_job(
        str(input_dir), str(output_dir), should_stop=stop_once_scale_starts, **default_kwargs()
    )

    assert result.panels_saved == 1  # tag stage completed normally
    assert result.interrupted is True
    assert result.interrupted_during == "scale"


def test_prepare_uses_grouped_median_per_source_page(tmp_path):
    """Each source page's own fallback should come from THAT page's own
    measured panel, not blended with the other page in the batch -- the
    behavior confirmed with the user for segmetric.prepare specifically.
    """
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    output_dir.mkdir()

    # Two source pages, deliberately different marker spacing so their
    # fallback values are distinguishable from one another.
    _write(input_dir / "scan_a.png", make_split_source_image(good_spacing_px=900))
    _write(input_dir / "scan_b.png", make_split_source_image(good_spacing_px=1800))

    result = run_prepare_job(
        str(input_dir),
        str(output_dir),
        rows=1,
        cols=2,
        use_cv_naming=False,
        ocr_region=OcrRegion(),
        gpu=True,
        output_format="png",
        scale_settings=ScaleSettings(),
    )

    assert result.panels_saved == 4  # 2 pages x 2 panels/page

    with open(result.summary_csv_path) as f:
        rows_by_name = {row["file_name"]: row for row in csv.DictReader(f)}

    def find_row(prefix):
        matches = [row for name, row in rows_by_name.items() if name.startswith(prefix)]
        assert len(matches) == 1, f"expected exactly one panel named {prefix}*, found {matches}"
        return matches[0]

    panel1 = find_row("panel_01_")  # scan_a, left half -- measurable
    panel2 = find_row("panel_02_")  # scan_a, right half -- fails
    panel3 = find_row("panel_03_")  # scan_b, left half -- measurable
    panel4 = find_row("panel_04_")  # scan_b, right half -- fails

    assert panel1["scale_source"] == "measured"
    assert panel2["scale_source"] == "page_median"
    assert float(panel2["mm_per_pixel"]) == pytest.approx(float(panel1["mm_per_pixel"]))

    assert panel3["scale_source"] == "measured"
    assert panel4["scale_source"] == "page_median"
    assert float(panel4["mm_per_pixel"]) == pytest.approx(float(panel3["mm_per_pixel"]))

    # The two pages' fallback values differ from each other -- proof this
    # used its own page's median, not a single value blended across pages.
    assert float(panel2["mm_per_pixel"]) != pytest.approx(
        float(panel4["mm_per_pixel"]), rel=0.05
    )
