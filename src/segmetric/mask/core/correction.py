import cv2

ADD = "add"
REMOVE = "remove"


def apply_brush_stroke(mask, x0, y0, x1, y1, radius, mode=ADD):
    """Paint a brush stroke onto mask (uint8, values 0/1) and return the
    result as a new array (the input is left unmodified).

    Matches the notebook's WingMaskEditor._paint exactly: draws a thick line
    (2*radius wide) from (x0, y0) to (x1, y1), plus a filled circle of
    `radius` at the endpoint -- the circle alone covers the very first point
    of a stroke, where there's no previous point to draw a line from yet
    (pass x0=y0=None for that case). mode=ADD paints 1s in; mode=REMOVE
    paints 0s (erases).

    (x1, y1) outside the mask is a no-op (returns an unchanged copy);
    (x0, y0) outside the mask is fine -- cv2.line clips to the image bounds.
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
