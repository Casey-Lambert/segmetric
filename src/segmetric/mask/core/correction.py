
import cv2

ADD = "add"
REMOVE = "remove"


def apply_brush_stroke(mask, x0, y0, x1, y1, radius, mode=ADD):
    """Add/Remove brush stroke mask editor(uint8, values 0/1); return the
    result as a new arrays.
    """
    result = mask.copy()
    h, w = result.shape[:2]
    ix1, iy1 = int(round(x1)), int(round(y1))
    if not (0 <= ix1 < w and 0 <= iy1 < h):
        return result

    value = 1 if mode == ADD else 0
    if x0 is not None and y0 is not None:
        ix0, iy0 = int(round(x0)), int(round(y0))
        cv2.line(result, (ix0, iy0), (ix1, iy1), value, radius * 2)
    cv2.circle(result, (ix1, iy1), radius, value, -1)
    return result
