from dataclasses import dataclass

import numpy as np

from .detection import (
    BLOB_MAX_AREA,
    BLOB_MAX_ASPECT,
    BLOB_MIN_AREA,
    BLOB_MIN_ASPECT,
    compute_marker_centers,
    detect_markers,
)

MIN_MARKERS_FOR_CROP = 2
CROP_PADDING = 4


@dataclass(frozen=True)
class CropRegion:
  

    v_anchor: str = "center"
    v_size_pct: int = 50
    h_anchor: str = "center"
    h_size_pct: int = 100


def crop_region_from_settings(settings):
    
    return CropRegion(
        v_anchor=settings.crop_v_anchor,
        v_size_pct=settings.crop_v_size_pct,
        h_anchor=settings.crop_h_anchor,
        h_size_pct=settings.crop_h_size_pct,
    )


def apply_crop_region(bbox, region: CropRegion = CropRegion()):
    """Trim bbox = (x1, y1, x2, y2) 
    """
    x1, y1, x2, y2 = bbox
    width = x2 - x1
    height = y2 - y1

    band_h = min(height, max(1, round(height * region.v_size_pct / 100)))
    band_w = min(width, max(1, round(width * region.h_size_pct / 100)))

    if region.v_anchor == "top":
        ny1, ny2 = y1, y1 + band_h
    elif region.v_anchor == "bottom":
        ny1, ny2 = y2 - band_h, y2
    else:  # "center"
        pad = (height - band_h) // 2
        ny1, ny2 = y1 + pad, y1 + pad + band_h

    if region.h_anchor == "left":
        nx1, nx2 = x1, x1 + band_w
    elif region.h_anchor == "right":
        nx1, nx2 = x2 - band_w, x2
    else:  # "center"
        pad = (width - band_w) // 2
        nx1, nx2 = x1 + pad, x1 + pad + band_w

    return nx1, ny1, nx2, ny2


def compute_crop_bbox(
    image_bgr,
    detector,
    region: CropRegion = CropRegion(),
    padding=CROP_PADDING,
    use_blob_fallback=True,
    blob_min_area=BLOB_MIN_AREA,
    blob_max_area=BLOB_MAX_AREA,
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
    if ids is None or len(ids) < MIN_MARKERS_FOR_CROP:
        return None

    centers = compute_marker_centers(corners)

    x_min = max(int(np.min(centers[:, 0])) - padding, 0)
    y_min = max(int(np.min(centers[:, 1])) - padding, 0)
    x_max = min(int(np.max(centers[:, 0])) + padding, image_bgr.shape[1])
    y_max = min(int(np.max(centers[:, 1])) + padding, image_bgr.shape[0])

    return apply_crop_region((x_min, y_min, x_max, y_max), region)


def crop_to_markers(
    image_bgr,
    detector,
    region: CropRegion = CropRegion(),
    padding=CROP_PADDING,
    use_blob_fallback=True,
    blob_min_area=BLOB_MIN_AREA,
    blob_max_area=BLOB_MAX_AREA,
    blob_min_aspect=BLOB_MIN_ASPECT,
    blob_max_aspect=BLOB_MAX_ASPECT,
):
    """Crop image to marker bounding box, then trim per
    """
    bbox = compute_crop_bbox(
        image_bgr,
        detector,
        region,
        padding,
        use_blob_fallback=use_blob_fallback,
        blob_min_area=blob_min_area,
        blob_max_area=blob_max_area,
        blob_min_aspect=blob_min_aspect,
        blob_max_aspect=blob_max_aspect,
    )
    if bbox is None:
        return None

    x1, y1, x2, y2 = bbox
    return image_bgr[y1:y2, x1:x2]
