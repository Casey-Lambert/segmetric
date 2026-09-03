import cv2
import numpy as np
import pytest

from segmetric.mask.core.measurement import (
    measure_object,
    measure_wing,
    orient_base_left,
    rotate_mask_long_axis,
)


def make_rotated_rect_mask(length=200, width=50, angle_deg=30, canvas_size=400):
    mask = np.zeros((canvas_size, canvas_size), dtype=np.uint8)
    center = (canvas_size // 2, canvas_size // 2)
    box = cv2.boxPoints((center, (length, width), angle_deg)).astype(np.int32)
    cv2.fillPoly(mask, [box], 1)
    return mask


def make_trapezoid_mask(canvas_size=300):
    """Narrower on the left, wider on the right -- for orient_base_left,
    which should flip this so the wider ("base") end ends up on the left.
    """
    mask = np.zeros((canvas_size, canvas_size), dtype=np.uint8)
    pts = np.array(
        [[50, 140], [50, 160], [250, 100], [250, 200]], dtype=np.int32
    )
    cv2.fillPoly(mask, [pts], 1)
    return mask


def test_rotate_mask_long_axis_straightens_a_rotated_rectangle():
    mask = make_rotated_rect_mask(length=200, width=50, angle_deg=30)
    rotated = rotate_mask_long_axis(mask)

    ys, xs = np.nonzero(rotated)
    width_span = xs.max() - xs.min() + 1
    height_span = ys.max() - ys.min() + 1
    # After straightening, the long axis (200) should be horizontal.
    assert width_span == pytest.approx(200, rel=0.1)
    assert height_span == pytest.approx(50, rel=0.2)


def test_rotate_mask_long_axis_empty_mask_is_a_noop():
    empty = np.zeros((100, 100), dtype=np.uint8)
    assert np.array_equal(rotate_mask_long_axis(empty), empty)


def test_measure_wing_length_and_width_on_axis_aligned_rect():
    mask = np.zeros((200, 300), dtype=np.uint8)
    mask[75:125, 20:220] = 1  # 200 wide, 50 tall, axis-aligned already

    length_px, width_px, _col = measure_wing(mask)
    assert length_px == 200
    assert width_px == 50


def test_measure_object_recovers_length_and_width_after_rotation():
    mask = make_rotated_rect_mask(length=200, width=50, angle_deg=30)
    result = measure_object(mask, mm_per_pixel=1.0)

    assert result["length_px"] == pytest.approx(200, rel=0.1)
    assert result["width_px"] == pytest.approx(50, rel=0.2)
    assert result["length_mm"] == pytest.approx(result["length_px"])
    assert result["width_mm"] == pytest.approx(result["width_px"])
    assert result["area_px"] > 0
    assert result["area_mm2"] == pytest.approx(result["area_px"], rel=0.01)


def test_measure_object_scales_mm_with_marker_spacing():
    mask = make_rotated_rect_mask(length=200, width=50, angle_deg=0)
    result_1x = measure_object(mask, mm_per_pixel=1.0)
    result_2x = measure_object(mask, mm_per_pixel=2.0)

    assert result_2x["length_mm"] == pytest.approx(result_1x["length_mm"] * 2, rel=0.01)
    assert result_2x["area_mm2"] == pytest.approx(result_1x["area_mm2"] * 4, rel=0.01)


def test_measure_object_empty_mask_returns_zeros():
    empty = np.zeros((100, 100), dtype=np.uint8)
    result = measure_object(empty, mm_per_pixel=1.0)
    assert result["length_px"] == 0
    assert result["width_px"] == 0
    assert result["area_px"] == 0


def test_orient_base_left_flips_so_the_wider_end_is_on_the_left():
    mask = make_trapezoid_mask()
    # Confirm the fixture is actually wider on the right before orienting,
    # so the flip is meaningfully tested.
    ys, xs = np.nonzero(mask)
    x_min, x_max = xs.min(), xs.max()
    strip = max(int((x_max - x_min) * 0.2), 1)

    def strip_height(x0, x1):
        sy = ys[(xs >= x0) & (xs <= x1)]
        return sy.max() - sy.min()

    assert strip_height(x_max - strip, x_max) > strip_height(x_min, x_min + strip)

    oriented = orient_base_left(mask)
    oys, oxs = np.nonzero(oriented)
    ox_min, ox_max = oxs.min(), oxs.max()
    ostrip = max(int((ox_max - ox_min) * 0.2), 1)

    def ostrip_height(x0, x1):
        sy = oys[(oxs >= x0) & (oxs <= x1)]
        return sy.max() - sy.min()

    # After orienting, the left strip should now be the taller ("base") one.
    assert ostrip_height(ox_min, ox_min + ostrip) >= ostrip_height(ox_max - ostrip, ox_max)
