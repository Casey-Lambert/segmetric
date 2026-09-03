import numpy as np

from segmetric.mask.core.correction import ADD, REMOVE, apply_brush_stroke


def test_add_stroke_paints_a_filled_circle():
    mask = np.zeros((100, 100), dtype=np.uint8)
    result = apply_brush_stroke(mask, None, None, 50, 50, radius=10, mode=ADD)

    assert result[50, 50] == 1
    assert result[50, 65] == 0  # outside the radius
    # Original left untouched.
    assert mask.sum() == 0


def test_remove_stroke_erases_from_a_filled_mask():
    mask = np.ones((100, 100), dtype=np.uint8)
    result = apply_brush_stroke(mask, None, None, 50, 50, radius=10, mode=REMOVE)

    assert result[50, 50] == 0
    assert result[10, 10] == 1  # untouched, far from the stroke


def test_stroke_between_two_points_connects_them():
    mask = np.zeros((100, 100), dtype=np.uint8)
    result = apply_brush_stroke(mask, 10, 50, 90, 50, radius=5, mode=ADD)

    # Midpoint of the line should be painted.
    assert result[50, 50] == 1
    # Both endpoints too.
    assert result[50, 10] == 1
    assert result[50, 90] == 1


def test_out_of_bounds_endpoint_is_a_noop():
    mask = np.zeros((50, 50), dtype=np.uint8)
    result = apply_brush_stroke(mask, None, None, 500, 500, radius=5, mode=ADD)
    assert result.sum() == 0


def test_result_is_a_copy_not_a_mutation():
    mask = np.zeros((50, 50), dtype=np.uint8)
    apply_brush_stroke(mask, None, None, 25, 25, radius=5, mode=ADD)
    assert mask.sum() == 0
