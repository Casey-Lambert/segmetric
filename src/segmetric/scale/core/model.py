

from dataclasses import dataclass


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


DEFAULT_CROP_V_ANCHOR = "center"
DEFAULT_CROP_V_SIZE_PCT = 50
DEFAULT_CROP_H_ANCHOR = "center"
DEFAULT_CROP_H_SIZE_PCT = 100


DEFAULT_GROUP_SIZE = 0


@dataclass
class ScaleSettings:
    """Marker spacing + ArUco detector thresholds, savable as a preset to use latter."""

    marker_spacing_mm: float = DEFAULT_MARKER_SPACING_MM

    # Shared between the prepare and final detection passes.
    adaptive_thresh_constant: int = DEFAULT_ADAPTIVE_THRESH_CONSTANT
    adaptive_thresh_win_size_min: int = DEFAULT_ADAPTIVE_THRESH_WIN_SIZE_MIN

    # Final pass only 
    adaptive_thresh_win_size_max: int = DEFAULT_ADAPTIVE_THRESH_WIN_SIZE_MAX
    adaptive_thresh_win_size_step: int = DEFAULT_ADAPTIVE_THRESH_WIN_SIZE_STEP

    # Prepare pass only: decides where to crop.
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
