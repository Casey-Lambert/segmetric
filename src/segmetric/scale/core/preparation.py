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
    """Crop image_bgr tight to its ArUco markers' corner bounding box, then
    upscale -- matching the notebook's Cell 7 step (crop_image_to_square +
    SCALE_UP=2.0, cubic interpolation).

    This step runs before both scale measurement and the final crop so that
    the measured mm/pixel and the saved cropped image are calibrated to the
    same pixel space -- exactly how the notebook's Cell 9 operated on
    Prepared_Crops (Cell 7's output), not on raw split panels.

    detector should be built with build_prepare_detector (a wider
    adaptive-threshold window than the final pass's detector -- see
    core.detection -- since markers are small relative to the full raw,
    un-cropped panel here). blob_min_area/blob_max_area default to that
    same prepare-pass range for the same reason.

    Returns the prepared image, or None if fewer than 3 markers were found
    (matching Cell 7's own n_found >= 3 requirement).
    """
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
