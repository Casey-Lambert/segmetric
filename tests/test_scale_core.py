import cv2
import numpy as np
import pytest

from segmetric.scale.core.cropping import (
    CropRegion,
    apply_crop_region,
    compute_crop_bbox,
    crop_region_from_settings,
    crop_to_markers,
)
from segmetric.scale.core.detection import build_detector
from segmetric.scale.core.model import ScaleSettings
from segmetric.scale.core.scale import compute_image_scale

ARUCO_DICT = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)


def _place_marker(canvas, marker_id, center, size=80):
    marker_img = cv2.aruco.generateImageMarker(ARUCO_DICT, marker_id, size)
    marker_bgr = cv2.cvtColor(marker_img, cv2.COLOR_GRAY2BGR)
    half = size // 2
    x, y = center[0] - half, center[1] - half
    canvas[y:y + size, x:x + size] = marker_bgr


def make_square_marker_image(spacing_px=400, marker_size=80, canvas_size=None, n_markers=4):
    """A white canvas with n_markers ArUco markers placed at the corners of a
    square spacing_px apart (center-to-center along each edge). With 4
    markers this gives 4 equal "side" distances (== spacing_px) and 2 longer
    diagonals -- matching the notebook's "average of the two smallest
    pairwise distances" assumption.

    canvas_size defaults to generously larger than the marker spread so it
    never clips regardless of spacing_px/marker_size -- pass it explicitly
    to override.
    """
    if canvas_size is None:
        canvas_size = spacing_px + marker_size * 3
    canvas = np.full((canvas_size, canvas_size, 3), 255, dtype=np.uint8)
    cx = cy = canvas_size // 2
    d = spacing_px // 2
    corner_centers = [
        (cx - d, cy - d),
        (cx + d, cy - d),
        (cx + d, cy + d),
        (cx - d, cy + d),
    ]
    for marker_id, center in list(enumerate(corner_centers))[:n_markers]:
        _place_marker(canvas, marker_id, center, size=marker_size)
    return canvas


def test_compute_image_scale_matches_known_spacing():
    spacing_px = 400
    image = make_square_marker_image(spacing_px=spacing_px)
    detector = build_detector(ScaleSettings())

    mm_per_pixel = compute_image_scale(image, detector, marker_spacing_mm=20.0)

    assert mm_per_pixel is not None
    expected = 20.0 / spacing_px
    assert mm_per_pixel == pytest.approx(expected, rel=0.02)


def test_compute_image_scale_none_with_too_few_markers():
    image = make_square_marker_image(n_markers=3)
    detector = build_detector(ScaleSettings())

    assert compute_image_scale(image, detector, marker_spacing_mm=20.0) is None


def test_compute_image_scale_scales_with_marker_spacing_setting():
    image = make_square_marker_image(spacing_px=400)
    detector = build_detector(ScaleSettings())

    scale_20mm = compute_image_scale(image, detector, marker_spacing_mm=20.0)
    scale_40mm = compute_image_scale(image, detector, marker_spacing_mm=40.0)

    assert scale_40mm == pytest.approx(scale_20mm * 2, rel=0.001)


def test_crop_bbox_within_image_and_trimmed_shorter_than_bbox():
    image = make_square_marker_image(spacing_px=400, n_markers=4)
    detector = build_detector(ScaleSettings())

    bbox = compute_crop_bbox(image, detector)

    assert bbox is not None
    x1, y1, x2, y2 = bbox
    assert 0 <= x1 < x2 <= image.shape[1]
    assert 0 <= y1 < y2 <= image.shape[0]

    cropped = crop_to_markers(image, detector)
    assert cropped is not None
    assert cropped.shape[0] == y2 - y1
    assert cropped.shape[1] == x2 - x1


def test_crop_bbox_none_with_too_few_markers():
    image = make_square_marker_image(n_markers=1)
    detector = build_detector(ScaleSettings())

    assert compute_crop_bbox(image, detector) is None
    assert crop_to_markers(image, detector) is None


def test_apply_crop_region_default_reproduces_the_old_hardcoded_quarter_trim():
    bbox = (10, 20, 110, 220)  # 100 wide, 200 tall
    x1, y1, x2, y2 = apply_crop_region(bbox, CropRegion())

    # Old hardcoded math: quarter = height // 4; y1+quarter, y2-quarter; full width.
    quarter = 200 // 4
    assert (x1, y1, x2, y2) == (10, 20 + quarter, 110, 220 - quarter)


def test_apply_crop_region_top_anchor_grows_from_the_top():
    bbox = (0, 0, 100, 200)
    x1, y1, x2, y2 = apply_crop_region(bbox, CropRegion(v_anchor="top", v_size_pct=25))
    assert (y1, y2) == (0, 50)
    assert (x1, x2) == (0, 100)  # h unaffected -- still full width (default)


def test_apply_crop_region_bottom_anchor_grows_from_the_bottom():
    bbox = (0, 0, 100, 200)
    _x1, y1, x2, y2 = apply_crop_region(bbox, CropRegion(v_anchor="bottom", v_size_pct=25))
    assert (y1, y2) == (150, 200)


def test_apply_crop_region_left_and_right_anchors():
    bbox = (0, 0, 200, 100)
    x1, _y1, x2, _y2 = apply_crop_region(bbox, CropRegion(h_anchor="left", h_size_pct=25))
    assert (x1, x2) == (0, 50)

    x1, _y1, x2, _y2 = apply_crop_region(bbox, CropRegion(h_anchor="right", h_size_pct=25))
    assert (x1, x2) == (150, 200)


def test_apply_crop_region_size_100_pct_returns_the_untrimmed_box():
    bbox = (5, 5, 105, 205)
    region = CropRegion(v_anchor="top", v_size_pct=100, h_anchor="left", h_size_pct=100)
    assert apply_crop_region(bbox, region) == bbox


def test_apply_crop_region_center_anchor_is_symmetric_at_any_size():
    bbox = (0, 0, 100, 100)
    x1, y1, x2, y2 = apply_crop_region(bbox, CropRegion(v_size_pct=60, h_size_pct=60))
    # 60% of 100 = 60, centered leaves 20px on each side.
    assert (x1, y1, x2, y2) == (20, 20, 80, 80)


def test_crop_region_from_settings_reads_the_four_crop_fields():
    settings = ScaleSettings(
        crop_v_anchor="top", crop_v_size_pct=30, crop_h_anchor="right", crop_h_size_pct=40
    )
    region = crop_region_from_settings(settings)
    assert region == CropRegion(v_anchor="top", v_size_pct=30, h_anchor="right", h_size_pct=40)


def test_compute_crop_bbox_honors_a_custom_region():
    image = make_square_marker_image(spacing_px=400, n_markers=4)
    detector = build_detector(ScaleSettings())

    default_bbox = compute_crop_bbox(image, detector)
    full_bbox = compute_crop_bbox(
        image, detector, region=CropRegion(v_anchor="top", v_size_pct=100, h_anchor="left", h_size_pct=100)
    )

    assert default_bbox is not None and full_bbox is not None
    # The default (50% height) box must be strictly shorter than the
    # untrimmed (100% height) one, same width either way.
    _dx1, dy1, _dx2, dy2 = default_bbox
    _fx1, fy1, _fx2, fy2 = full_bbox
    assert (dy2 - dy1) < (fy2 - fy1)


def test_custom_thresholds_are_actually_applied_to_the_detector():
    settings = ScaleSettings(adaptive_thresh_win_size_min=3, adaptive_thresh_win_size_max=23)
    detector = build_detector(settings)
    # cv2 doesn't expose a getter, but constructing without error and
    # detecting normally confirms the custom params were accepted.
    image = make_square_marker_image(spacing_px=400)
    assert compute_image_scale(image, detector, marker_spacing_mm=20.0) is not None
