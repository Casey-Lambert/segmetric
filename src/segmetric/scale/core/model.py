from dataclasses import dataclass

# The refined detector values confirmed against the current notebooks
# (WA_Landmarks_June_26b.ipynb / WA_Landmarks_PreCropPannels.ipynb / WA_June2.ipynb),
# which superseded the original WA_April27_16pannels.ipynb's Cell 9 thresholds.
# These stay the defaults everywhere; the GUI only lets the user override
# the threshold values explicitly (blob fallback is a separate on/off toggle).
#
# The notebook actually runs detection in two distinct passes with two
# distinct configurations: a "prepare" pass on the raw, un-cropped panel
# (used to find where to crop) and a "final" pass on the already
# cropped+2x-upscaled image (used for scale measurement and the final
# crop). The prepare pass needs a much wider adaptive-threshold window
# range to find markers that are small relative to the full raw panel, and
# a correspondingly smaller blob-fallback area range (markers are ~1/4 the
# pixel area before the 2x upscale). Reusing the "final" pass's tighter
# window/blob settings for the "prepare" pass was the root cause of a
# marker-detection coverage regression on real scans.
DEFAULT_MARKER_SPACING_MM = 20.0
DEFAULT_ADAPTIVE_THRESH_CONSTANT = 5
DEFAULT_ADAPTIVE_THRESH_WIN_SIZE_MIN = 3
DEFAULT_ADAPTIVE_THRESH_WIN_SIZE_MAX = 91
DEFAULT_ADAPTIVE_THRESH_WIN_SIZE_STEP = 8
DEFAULT_USE_BLOB_FALLBACK = True

DEFAULT_PREPARE_WIN_SIZE_MAX = 301
DEFAULT_PREPARE_WIN_SIZE_STEP = 20
DEFAULT_PREPARE_ERROR_CORRECTION_RATE = 1.0
DEFAULT_PREPARE_PERSPECTIVE_REMOVE_PIXEL_PER_CELL = 16

DEFAULT_BLOB_MIN_ASPECT = 0.7
DEFAULT_BLOB_MAX_ASPECT = 1.4
DEFAULT_PREPARE_BLOB_MIN_AREA = 40000
DEFAULT_PREPARE_BLOB_MAX_AREA = 150000
DEFAULT_FINAL_BLOB_MIN_AREA = 150000
DEFAULT_FINAL_BLOB_MAX_AREA = 600000

# The crop region, relative to the padded marker bounding box (see
# core/cropping.py's CropRegion) -- these defaults reproduce the
# notebook's original hardcoded "quarter trim" exactly (vertically-
# centered middle 50% of the box's height, full width).
DEFAULT_CROP_V_ANCHOR = "center"
DEFAULT_CROP_V_SIZE_PCT = 50
DEFAULT_CROP_H_ANCHOR = "center"
DEFAULT_CROP_H_SIZE_PCT = 100

# 0 means "off" -- run_scale_job's group_size=None behavior: one flat
# median across the whole batch when markers fail. A positive value here
# is passed through as group_size=N, chunking the batch into consecutive
# groups of N (e.g. panels-per-scan) so the fallback median for a failed
# panel comes from its own scan, not blended across every scan in the
# input folder. segmetric.prepare gets this "for free" by passing
# rows*cols (it does the splitting itself, so it already knows the
# count); standalone segmetric.scale has no other way to know it, since
# it only ever receives an already-split folder of crops.
DEFAULT_GROUP_SIZE = 0


@dataclass
class ScaleSettings:
    """Marker spacing + ArUco detector thresholds, savable as a preset."""

    marker_spacing_mm: float = DEFAULT_MARKER_SPACING_MM

    # Shared between the prepare and final detection passes.
    adaptive_thresh_constant: int = DEFAULT_ADAPTIVE_THRESH_CONSTANT
    adaptive_thresh_win_size_min: int = DEFAULT_ADAPTIVE_THRESH_WIN_SIZE_MIN

    # Final pass only (post crop+upscale): scale measurement + final crop.
    adaptive_thresh_win_size_max: int = DEFAULT_ADAPTIVE_THRESH_WIN_SIZE_MAX
    adaptive_thresh_win_size_step: int = DEFAULT_ADAPTIVE_THRESH_WIN_SIZE_STEP

    # Prepare pass only (raw panel): decides where to crop.
    prepare_win_size_max: int = DEFAULT_PREPARE_WIN_SIZE_MAX
    prepare_win_size_step: int = DEFAULT_PREPARE_WIN_SIZE_STEP
    prepare_error_correction_rate: float = DEFAULT_PREPARE_ERROR_CORRECTION_RATE
    prepare_perspective_remove_pixel_per_cell: int = (
        DEFAULT_PREPARE_PERSPECTIVE_REMOVE_PIXEL_PER_CELL
    )

    use_blob_fallback: bool = DEFAULT_USE_BLOB_FALLBACK
    blob_min_aspect: float = DEFAULT_BLOB_MIN_ASPECT
    blob_max_aspect: float = DEFAULT_BLOB_MAX_ASPECT
    prepare_blob_min_area: int = DEFAULT_PREPARE_BLOB_MIN_AREA
    prepare_blob_max_area: int = DEFAULT_PREPARE_BLOB_MAX_AREA
    final_blob_min_area: int = DEFAULT_FINAL_BLOB_MIN_AREA
    final_blob_max_area: int = DEFAULT_FINAL_BLOB_MAX_AREA

    crop_v_anchor: str = DEFAULT_CROP_V_ANCHOR
    crop_v_size_pct: int = DEFAULT_CROP_V_SIZE_PCT
    crop_h_anchor: str = DEFAULT_CROP_H_ANCHOR
    crop_h_size_pct: int = DEFAULT_CROP_H_SIZE_PCT

    group_size: int = DEFAULT_GROUP_SIZE
