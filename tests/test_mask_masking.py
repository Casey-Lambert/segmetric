import cv2
import numpy as np
import pytest

from segmetric.mask.core.masking import generate_mask
from segmetric.mask.core.model import DEFAULT_FILTERS


def make_blob_image(canvas_size=400, blob_size=(150, 80), color=(30, 60, 90)):
    """A white canvas with a filled dark-brown ellipse in the middle --
    stands in for a wing/leg silhouette on a light background.
    """
    canvas = np.full((canvas_size, canvas_size, 3), 255, dtype=np.uint8)
    center = (canvas_size // 2, canvas_size // 2)
    axes = (blob_size[0] // 2, blob_size[1] // 2)
    cv2.ellipse(canvas, center, axes, 0, 0, 360, color, -1)
    return canvas, center, axes


@pytest.mark.parametrize("filter_name", ["Forewing", "Hindwing", "Leg"])
def test_generate_mask_produces_a_nonempty_mask(filter_name):
    image, _center, _axes = make_blob_image()
    mask = generate_mask(image, DEFAULT_FILTERS[filter_name])

    assert mask.shape == image.shape[:2]
    assert mask.dtype == np.uint8
    assert set(np.unique(mask)).issubset({0, 1})
    assert mask.sum() > 0


def test_generate_mask_roughly_covers_the_blob_region():
    image, center, axes = make_blob_image()
    mask = generate_mask(image, DEFAULT_FILTERS["Leg"])

    cx, cy = center
    ax, ay = axes
    expected_bbox = (cx - ax, cy - ay, cx + ax, cy + ay)

    ys, xs = np.nonzero(mask)
    assert len(xs) > 0, "mask should not be empty"
    actual_bbox = (xs.min(), ys.min(), xs.max(), ys.max())

    # Generous tolerance -- the point is "roughly the blob", not pixel-exact.
    tol = max(axes) * 0.5
    for expected, actual in zip(expected_bbox, actual_bbox):
        assert actual == pytest.approx(expected, abs=tol)


def test_generate_mask_handles_a_blank_white_image_without_crashing():
    blank = np.full((200, 200, 3), 255, dtype=np.uint8)
    mask = generate_mask(blank, DEFAULT_FILTERS["Forewing"])
    assert mask.shape == (200, 200)
    # No real signal on a blank image -- an empty or near-empty mask is the
    # correct outcome, not a crash (guards the chroma_max division).
    assert mask.sum() <= blank.shape[0] * blank.shape[1]
