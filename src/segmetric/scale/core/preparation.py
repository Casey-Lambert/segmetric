
import cv2
import numpy as np

from .detection import BLOB_MAX_ASPECT, BLOB_MIN_ASPECT, PREPARE_BLOB_MAX_AREA, PREPARE_BLOB_MIN_AREA, detect_markers


MIN_MARKERS_FOR_PREPARE = 3
PREPARE_PADDING = 4
PREPARE_SCALE_UP = 2.0


def prepare_image(
    image_bgr,
    detector,
    padding=PREPARE_PADDING,
    scale_up=PREPARE_SCALE_UP,
    use_blob_fallback=True,
    blob_min_area=PREPARE_BLOB_MIN_AREA,
    blob_max_area=PREPARE_BLOB_MAX_AREA,
    blob_min_aspect=BLOB_MIN_ASPECT,
    blob_max_aspect=BLOB_MAX_ASPECT,
):
    
    corners, ids = detect_markers(
        image_bgr,
        detector,
        use_blob_fallback=use_blob_fallback,
        blob_min_area=blob_min_area,
        blob_max_area=blob_max_area,
        blob_min_aspect=blob_min_aspect,
        blob_max_aspect=blob_max_aspect,
    )
    n_found = 0 if ids is None else len(ids)
    if n_found < MIN_MARKERS_FOR_PREPARE:
        return None

    pts = np.concatenate([c[0] for c in corners[:4]])
    x, y, w, h = cv2.boundingRect(pts.astype(np.int32))
    x1 = max(x - padding, 0)
    y1 = max(y - padding, 0)
    x2 = min(x + w + padding, image_bgr.shape[1])
    y2 = min(y + h + padding, image_bgr.shape[0])
    cropped = image_bgr[y1:y2, x1:x2]

    if scale_up and scale_up != 1.0:
        cropped = cv2.resize(
            cropped, None, fx=scale_up, fy=scale_up, interpolation=cv2.INTER_CUBIC
        )

    return cropped


