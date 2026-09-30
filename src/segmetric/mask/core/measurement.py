

import cv2
import numpy as np


def rotate_mask_long_axis(mask):
    """Rotate mask (uint8 0/1) so its largest contour's long axis is
    horizontal.
    """
    contours, _ = cv2.findContours(
        (mask * 255).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE
    )
    if not contours:
        return mask
    largest = max(contours, key=cv2.contourArea)
    rect = cv2.minAreaRect(largest)
    _center, (w, h), angle = rect
    if w < h:
        angle += 90
    cy, cx = mask.shape[0] / 2, mask.shape[1] / 2
    m = cv2.getRotationMatrix2D((cx, cy), angle, 1.0)
    return cv2.warpAffine(mask, m, (mask.shape[1], mask.shape[0]), flags=cv2.INTER_NEAREST)


def orient_base_left(mask):
    """Flip mask horizontally so wider end sits on
    the left . compares mask height in the left vs. right 20% strips.
    Matches the notebook's orient_base_left exactly.
    """
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return mask
    x_min, x_max = int(xs.min()), int(xs.max())
    strip = max(int((x_max - x_min) * 0.2), 1)

    def strip_height(x0, x1):
        sy = ys[(xs >= x0) & (xs <= x1)]
        return int(sy.max() - sy.min()) if len(sy) > 0 else 0

    right_h = strip_height(x_max - strip, x_max)
    left_h = strip_height(x_min, x_min + strip)
    return np.fliplr(mask) if right_h > left_h else mask



def measure_wing(mask):
    """Length = horizontal extent; width = the tallest vertical span at any
    single column, assuming mask is already axis-aligned.

    Returns (length_px, width_px, width_col).
    """
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return 0, 0, 0
    length_px = int(xs.max() - xs.min() + 1)
    max_span, max_col = 0, int(xs.mean())
    for col in range(int(xs.min()), int(xs.max()) + 1):
        col_ys = ys[xs == col]
        if len(col_ys) > 1:
            span = int(col_ys.max() - col_ys.min() + 1)
            if span > max_span:
                max_span, max_col = span, col
    return length_px, max_span, max_col


def measure_object(mask, mm_per_pixel):
    """Axis-corrected length/width plus raw area.
    Returns dict(length_px, width_px, length_mm, width_mm, area_px, area_mm2).
    """
    area_px = int(np.sum(mask > 0))
    mask_rot = rotate_mask_long_axis(mask)
    mask_ori = orient_base_left(mask_rot)
    length_px, width_px, _width_col = measure_wing(mask_ori)

    return dict(
        length_px=length_px,
        width_px=width_px,
        length_mm=round(length_px * mm_per_pixel, 3),
        width_mm=round(width_px * mm_per_pixel, 3),
        area_px=area_px,
        area_mm2=round(area_px * (mm_per_pixel ** 2), 4),
    )
