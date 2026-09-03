import numpy as np
import pytest

from segmetric.segment.core.measurement import measure_cell


def test_measure_cell_axis_aligned_bbox():
    mask = np.zeros((100, 200), dtype=np.uint8)
    mask[20:50, 30:130] = 1  # 100 wide (30..129), 30 tall (20..49)

    m = measure_cell(mask, mm_per_pixel=1.0)

    assert m["bbox_w_px"] == 100
    assert m["bbox_h_px"] == 30
    assert m["area_px"] == 100 * 30


def test_measure_cell_scales_mm_with_marker_spacing():
    mask = np.zeros((100, 200), dtype=np.uint8)
    mask[20:50, 30:130] = 1

    m1 = measure_cell(mask, mm_per_pixel=1.0)
    m2 = measure_cell(mask, mm_per_pixel=2.0)

    assert m2["bbox_w_mm"] == pytest.approx(m1["bbox_w_mm"] * 2)
    assert m2["bbox_h_mm"] == pytest.approx(m1["bbox_h_mm"] * 2)
    assert m2["area_mm2"] == pytest.approx(m1["area_mm2"] * 4)


def test_measure_cell_empty_mask_returns_zeros():
    mask = np.zeros((50, 50), dtype=np.uint8)
    m = measure_cell(mask, mm_per_pixel=1.0)
    assert m == dict(area_px=0, area_mm2=0.0, bbox_w_px=0, bbox_h_px=0, bbox_w_mm=0.0, bbox_h_mm=0.0)


def test_measure_cell_single_pixel():
    mask = np.zeros((50, 50), dtype=np.uint8)
    mask[10, 20] = 1
    m = measure_cell(mask, mm_per_pixel=0.5)
    assert m["bbox_w_px"] == 1
    assert m["bbox_h_px"] == 1
    assert m["area_px"] == 1
    assert m["area_mm2"] == pytest.approx(0.25)
