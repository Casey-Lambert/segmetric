import cv2
import numpy as np

from segmetric.scale.core.detection import (
    PREPARE_BLOB_MAX_AREA,
    PREPARE_BLOB_MIN_AREA,
    build_detector,
    build_prepare_detector,
    detect_markers,
)
from segmetric.scale.core.model import ScaleSettings

from test_scale_core import make_square_marker_image


def make_blob_only_image(side=500, canvas_size=2200):
    """4 solid black squares (no real ArUco pattern inside) at the corners
    of a white canvas -- ArUco decoding must fail on these, but they sit
    squarely inside the blob-fallback's default (final-pass) area
    (150000-600000) and aspect ratio (0.7-1.4) filters, so only the
    fallback can find them.
    """
    canvas = np.full((canvas_size, canvas_size, 3), 255, dtype=np.uint8)
    margin = 100
    positions = [
        (margin, margin),
        (canvas_size - margin - side, margin),
        (margin, canvas_size - margin - side),
        (canvas_size - margin - side, canvas_size - margin - side),
    ]
    for x, y in positions:
        canvas[y:y + side, x:x + side] = 0
    return canvas


def make_small_blob_only_image(side=300, canvas_size=1400):
    """Same idea as make_blob_only_image, but sized to fall inside the
    prepare-pass's blob area range (40000-150000, area=90000 here) and
    OUTSIDE the final-pass's range (150000-600000) -- i.e. what a raw,
    un-upscaled panel's markers actually look like.
    """
    canvas = np.full((canvas_size, canvas_size, 3), 255, dtype=np.uint8)
    margin = 100
    positions = [
        (margin, margin),
        (canvas_size - margin - side, margin),
        (margin, canvas_size - margin - side),
        (canvas_size - margin - side, canvas_size - margin - side),
    ]
    for x, y in positions:
        canvas[y:y + side, x:x + side] = 0
    return canvas


def make_rect_blob_image(w=800, h=400, canvas_size=2000):
    """4 solid black rectangles, aspect ratio 2.0 -- outside the default
    blob aspect filter (0.7-1.4) but inside the default final-pass area
    range (area=320000).
    """
    canvas = np.full((canvas_size, canvas_size, 3), 255, dtype=np.uint8)
    margin = 100
    positions = [
        (margin, margin),
        (canvas_size - margin - w, margin),
        (margin, canvas_size - margin - h),
        (canvas_size - margin - w, canvas_size - margin - h),
    ]
    for x, y in positions:
        canvas[y:y + h, x:x + w] = 0
    return canvas


def test_blob_fallback_finds_markers_aruco_alone_cannot():
    image = make_blob_only_image()
    detector = build_detector(ScaleSettings())

    corners, ids = detect_markers(image, detector, use_blob_fallback=True)

    assert ids is not None
    assert len(ids) == 4


def test_blob_fallback_disabled_finds_nothing_on_blob_only_image():
    image = make_blob_only_image()
    detector = build_detector(ScaleSettings())

    corners, ids = detect_markers(image, detector, use_blob_fallback=False)

    assert ids is None or len(ids) < 4


def test_blob_fallback_does_not_override_successful_aruco_detection():
    # A normal, valid ArUco image should detect all 4 via ArUco itself --
    # blob fallback should be a no-op here (not silently substitute blobs).
    image = make_square_marker_image(spacing_px=400, n_markers=4)
    detector = build_detector(ScaleSettings())

    corners_with_fallback, ids_with_fallback = detect_markers(
        image, detector, use_blob_fallback=True
    )
    corners_without_fallback, ids_without_fallback = detect_markers(
        image, detector, use_blob_fallback=False
    )

    assert len(ids_with_fallback) == len(ids_without_fallback) == 4


def test_default_settings_have_blob_fallback_on():
    assert ScaleSettings().use_blob_fallback is True


def test_refined_defaults_match_the_notebook():
    defaults = ScaleSettings()
    assert defaults.adaptive_thresh_constant == 5
    assert defaults.adaptive_thresh_win_size_min == 3
    assert defaults.adaptive_thresh_win_size_max == 91
    assert defaults.adaptive_thresh_win_size_step == 8


def test_build_detector_still_finds_markers_with_refined_defaults():
    # Sanity check the new fixed params (perimeter rates, subpixel corner
    # refinement) don't break detection on a normal, clean marker image.
    image = make_square_marker_image(spacing_px=400, n_markers=4)
    detector = build_detector(ScaleSettings())
    corners, ids = detect_markers(image, detector)
    assert ids is not None
    assert len(ids) == 4


def test_prepare_detector_defaults_match_the_notebook():
    defaults = ScaleSettings()
    assert defaults.prepare_win_size_max == 301
    assert defaults.prepare_win_size_step == 20
    assert defaults.prepare_error_correction_rate == 1.0
    assert defaults.prepare_perspective_remove_pixel_per_cell == 16
    assert defaults.blob_min_aspect == 0.7
    assert defaults.blob_max_aspect == 1.4
    assert defaults.prepare_blob_min_area == 40000
    assert defaults.prepare_blob_max_area == 150000
    assert defaults.final_blob_min_area == 150000
    assert defaults.final_blob_max_area == 600000


def test_build_prepare_detector_still_finds_markers_normally():
    image = make_square_marker_image(spacing_px=400, n_markers=4)
    detector = build_prepare_detector(ScaleSettings())
    corners, ids = detect_markers(image, detector)
    assert ids is not None
    assert len(ids) == 4


def test_prepare_pass_blob_range_finds_small_markers_final_pass_misses():
    """This is the actual regression the two-pass fix addresses: a raw,
    un-upscaled panel's markers are small enough to fall inside the
    prepare-pass's blob area range but below the final-pass's range, so
    using the final-pass detector/params for the prepare step (as the code
    did before this fix) misses them entirely.
    """
    image = make_small_blob_only_image()

    prepare_detector = build_prepare_detector(ScaleSettings())
    corners, ids = detect_markers(
        image,
        prepare_detector,
        use_blob_fallback=True,
        blob_min_area=PREPARE_BLOB_MIN_AREA,
        blob_max_area=PREPARE_BLOB_MAX_AREA,
    )
    assert ids is not None
    assert len(ids) == 4

    final_detector = build_detector(ScaleSettings())
    corners2, ids2 = detect_markers(image, final_detector, use_blob_fallback=True)
    assert ids2 is None or len(ids2) < 4


def test_blob_aspect_ratio_is_configurable():
    image = make_rect_blob_image()
    detector = build_detector(ScaleSettings())

    # Default aspect filter (0.7-1.4) rejects these 2:1 rectangles.
    corners, ids = detect_markers(image, detector, use_blob_fallback=True)
    assert ids is None or len(ids) < 4

    # Widening the aspect range finds them.
    corners2, ids2 = detect_markers(
        image, detector, use_blob_fallback=True, blob_min_aspect=0.2, blob_max_aspect=2.5
    )
    assert ids2 is not None
    assert len(ids2) == 4


def test_blob_area_range_is_configurable():
    image = make_small_blob_only_image()
    detector = build_detector(ScaleSettings())

    # Default (final-pass) area range (150000-600000) misses these
    # smaller (area=90000) blobs.
    corners, ids = detect_markers(image, detector, use_blob_fallback=True)
    assert ids is None or len(ids) < 4

    # Explicitly widening the area range to include them finds them.
    corners2, ids2 = detect_markers(
        image, detector, use_blob_fallback=True, blob_min_area=40000, blob_max_area=150000
    )
    assert ids2 is not None
    assert len(ids2) == 4
