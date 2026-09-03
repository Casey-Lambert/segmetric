import math


def compute_manual_scale(p1, p2, distance_mm):
    """mm_per_pixel from two clicked image-space points and the known
    real-world distance between them, in mm -- the no-marker analog of
    core.scale.compute_image_scale. Returns None if the two points
    coincide (nothing to measure) or distance_mm isn't positive.
    """
    if distance_mm is None or distance_mm <= 0:
        return None
    pixel_dist = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
    if pixel_dist <= 0:
        return None
    return distance_mm / pixel_dist


def clamp_bbox(bbox, width, height):
    """Normalize a user-drawn rectangle: order the corners regardless of
    which direction it was dragged, clamp to the image bounds, and
    guarantee at least a 1px box (never zero-area, which would make a
    saved crop an empty image).

    bbox: (x1, y1, x2, y2) in image-space pixels, any corner order.
    Returns (x1, y1, x2, y2) with x1<x2, y1<y2, both within [0, width]/
    [0, height].
    """
    x1, y1, x2, y2 = bbox
    x1, x2 = sorted((x1, x2))
    y1, y2 = sorted((y1, y2))

    x1 = min(max(int(round(x1)), 0), width)
    x2 = min(max(int(round(x2)), 0), width)
    y1 = min(max(int(round(y1)), 0), height)
    y2 = min(max(int(round(y2)), 0), height)

    if x2 <= x1:
        x2 = min(x1 + 1, width)
        x1 = max(x2 - 1, 0)
    if y2 <= y1:
        y2 = min(y1 + 1, height)
        y1 = max(y2 - 1, 0)

    return x1, y1, x2, y2


def crop_to_region(image_bgr, bbox):
    """Plain slice to bbox = (x1, y1, x2, y2) -- the no-marker analog of
    cropping.py's crop_to_markers. Callers are expected to have already
    clamped bbox (see clamp_bbox) against this exact image's dimensions.
    """
    x1, y1, x2, y2 = bbox
    return image_bgr[y1:y2, x1:x2]
