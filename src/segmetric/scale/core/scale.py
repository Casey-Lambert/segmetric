import numpy as np

from .detection import (
    BLOB_MAX_AREA,
    BLOB_MAX_ASPECT,
    BLOB_MIN_AREA,
    BLOB_MIN_ASPECT,
    compute_marker_centers,
    detect_markers,
)

MIN_MARKERS_FOR_SCALE = 4


def compute_image_scale(
    image_bgr,
    detector,
    marker_spacing_mm,
    use_blob_fallback=True,
    blob_min_area=BLOB_MIN_AREA,
    blob_max_area=BLOB_MAX_AREA,
    blob_min_aspect=BLOB_MIN_ASPECT,
    blob_max_aspect=BLOB_MAX_ASPECT,
):
    """Compute mm/pixel scale for one image via ArUco marker spacing.

    Matches the notebook's pass-1 logic exactly: requires >=4 markers, and
    only ever looks at the first 4 detected marker centers (not all of them,
    even if more were found) -- takes every pairwise distance among those
    4, sorts them, and averages the two smallest as the "adjacent" marker
    spacing in pixels.

    Called on the already-prepared (cropped + upscaled) image -- detector
    should be built with build_detector (the "final" pass), and the blob
    defaults here match that pass's area range.

    Returns mm_per_pixel (float), or None if fewer than 4 markers were found.
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
    if ids is None or len(ids) < MIN_MARKERS_FOR_SCALE:
        return None

    centers = compute_marker_centers(corners)

    dists = []
    for i in range(4):
        for j in range(i + 1, 4):
            dists.append(float(np.linalg.norm(centers[i] - centers[j])))

    dists_sorted = sorted(dists)
    avg_adjacent_px = (dists_sorted[0] + dists_sorted[1]) / 2.0
    if avg_adjacent_px <= 0:
        return None

    return marker_spacing_mm / avg_adjacent_px
