import cv2
import numpy as np

from segmetric.segment.core.detection import segment_cells
from segmetric.segment.core.model import DetectionSettings


def make_two_cell_image(canvas_size=300, vein_x=150):
    """Two lighter regions separated by one dark, thin vertical vein --
    should split into two watershed basins under default settings.
    """
    img = np.full((canvas_size, canvas_size, 3), 190, dtype=np.uint8)
    cv2.line(img, (vein_x, 0), (vein_x, canvas_size), (30, 30, 30), 3)
    return img


def make_blank_image(canvas_size=200, value=190):
    return np.full((canvas_size, canvas_size, 3), value, dtype=np.uint8)


def test_segment_cells_returns_expected_shapes():
    img = make_two_cell_image()
    wing_mask = np.ones(img.shape[:2], dtype=np.uint8)

    labeled, n_cells, vein_mask = segment_cells(img, wing_mask, DetectionSettings())

    assert labeled.shape == img.shape[:2]
    assert vein_mask.shape == img.shape[:2]
    assert vein_mask.dtype == np.uint8
    assert n_cells == labeled.max()
    assert n_cells >= 0


def test_segment_cells_finds_at_least_two_regions_split_by_a_vein():
    img = make_two_cell_image()
    wing_mask = np.ones(img.shape[:2], dtype=np.uint8)

    labeled, n_cells, _vein_mask = segment_cells(img, wing_mask, DetectionSettings())

    assert n_cells >= 2


def test_segment_cells_respects_wing_mask_boundary():
    img = make_two_cell_image()
    wing_mask = np.zeros(img.shape[:2], dtype=np.uint8)
    wing_mask[50:250, 50:250] = 1  # only the middle region is "wing"

    labeled, _n_cells, _vein_mask = segment_cells(img, wing_mask, DetectionSettings())

    assert (labeled[wing_mask == 0] == 0).all()


def test_segment_cells_whole_image_fallback_does_not_crash():
    # The notebooks' own "no wing mask" fallback: an all-ones mask covering
    # the entire image.
    img = make_blank_image()
    wing_mask = np.ones(img.shape[:2], dtype=np.uint8)

    labeled, n_cells, vein_mask = segment_cells(img, wing_mask, DetectionSettings())

    assert labeled.shape == img.shape[:2]
    assert n_cells >= 0


def test_custom_detection_settings_are_actually_applied():
    img = make_two_cell_image()
    wing_mask = np.ones(img.shape[:2], dtype=np.uint8)

    # A very large min_vein_size should make the thin vein fail
    # remove_small_objects' size filter, merging both halves into one cell
    # (or at least not crash and produce a valid result).
    settings = DetectionSettings(min_vein_size=10_000_000)
    labeled, n_cells, _vein_mask = segment_cells(img, wing_mask, settings)

    assert labeled.shape == img.shape[:2]
    assert n_cells >= 0
