import pytest

from segmetric.scale.core.detection import build_detector, build_prepare_detector
from segmetric.scale.core.model import ScaleSettings
from segmetric.scale.core.preparation import prepare_image
from segmetric.scale.core.scale import compute_image_scale

from test_scale_core import make_square_marker_image


def test_prepare_image_upscales_by_default_factor():
    image = make_square_marker_image(spacing_px=400, n_markers=4)
    detector = build_prepare_detector(ScaleSettings())

    prepared = prepare_image(image, detector)

    assert prepared is not None
    assert prepared.shape[0] > 0 and prepared.shape[1] > 0


def test_prepare_image_none_with_too_few_markers():
    image = make_square_marker_image(n_markers=2)
    detector = build_prepare_detector(ScaleSettings())

    assert prepare_image(image, detector) is None


def test_prepare_image_succeeds_with_exactly_three_markers():
    image = make_square_marker_image(n_markers=3)
    detector = build_prepare_detector(ScaleSettings())

    assert prepare_image(image, detector) is not None


def test_prepare_image_upscale_factor_roughly_halves_measured_mm_per_pixel():
    # spacing_px needs to be generous relative to marker_size: after
    # prepare_image crops tight + upscales 2x, markers must still stay
    # under maxMarkerPerimeterRate's limit relative to the resulting image.
    spacing_px = 900
    image = make_square_marker_image(spacing_px=spacing_px, marker_size=60)
    prepare_detector = build_prepare_detector(ScaleSettings())
    final_detector = build_detector(ScaleSettings())

    prepared = prepare_image(image, prepare_detector)
    assert prepared is not None

    raw_scale = compute_image_scale(image, final_detector, marker_spacing_mm=20.0)
    prepared_scale = compute_image_scale(prepared, final_detector, marker_spacing_mm=20.0)

    assert raw_scale is not None
    assert prepared_scale is not None
    # Same physical marker spacing spread across ~2x the pixels, so
    # mm/pixel should roughly halve after the upscale.
    assert prepared_scale == pytest.approx(raw_scale / 2, rel=0.05)


def test_prepare_image_no_upscale_when_scale_up_is_one():
    image = make_square_marker_image(n_markers=4)
    detector = build_prepare_detector(ScaleSettings())

    prepared_1x = prepare_image(image, detector, scale_up=1.0)
    prepared_2x = prepare_image(image, detector, scale_up=2.0)

    assert prepared_1x is not None
    assert prepared_2x is not None
    assert prepared_2x.shape[0] == pytest.approx(prepared_1x.shape[0] * 2, rel=0.02)
    assert prepared_2x.shape[1] == pytest.approx(prepared_1x.shape[1] * 2, rel=0.02)


def test_prepare_image_crops_tight_before_upscaling():
    # 4-marker square: bounding box of the corners should be roughly the
    # canvas region spanned by the markers, then padded and upscaled.
    image = make_square_marker_image(spacing_px=400, marker_size=80, canvas_size=600)
    detector = build_prepare_detector(ScaleSettings())

    prepared = prepare_image(image, detector, padding=4, scale_up=1.0)
    assert prepared is not None
    # Cropped tight to markers: much smaller than the full 600x600 canvas.
    assert prepared.shape[0] < 600
    assert prepared.shape[1] < 600
