

import math


def compute_manual_scale(p1, p2, distance_mm):
    """mm_per_pixel from two clicked image-space points and the known
    real-world distance between them
    """
    if distance_mm is None or distance_mm <= 0:
        return None
    pixel_dist = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
    if pixel_dist <= 0:
        return None
    return distance_mm / pixel_dist


def clamp_bbox(bbox, width, height):
    """makes sence of the a user-drawn rectangle crop"
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

    x1, y1, x2, y2 = bbox
    return image_bgr[y1:y2, x1:x2]



