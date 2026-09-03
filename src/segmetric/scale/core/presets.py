import json

from segmetric.errors import SegMetricError

from .model import ScaleSettings

_FIELDS = [
    "marker_spacing_mm",
    "adaptive_thresh_constant",
    "adaptive_thresh_win_size_min",
    "adaptive_thresh_win_size_max",
    "adaptive_thresh_win_size_step",
    "prepare_win_size_max",
    "prepare_win_size_step",
    "prepare_error_correction_rate",
    "prepare_perspective_remove_pixel_per_cell",
    "use_blob_fallback",
    "blob_min_aspect",
    "blob_max_aspect",
    "prepare_blob_min_area",
    "prepare_blob_max_area",
    "final_blob_min_area",
    "final_blob_max_area",
    "crop_v_anchor",
    "crop_v_size_pct",
    "crop_h_anchor",
    "crop_h_size_pct",
]


def settings_to_dict(settings: ScaleSettings) -> dict:
    return {field: getattr(settings, field) for field in _FIELDS}


def settings_from_dict(data: dict) -> ScaleSettings:
    defaults = ScaleSettings()
    return ScaleSettings(
        **{field: data.get(field, getattr(defaults, field)) for field in _FIELDS}
    )


def save_scale_preset(path, settings: ScaleSettings):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(settings_to_dict(settings), f, indent=2)
    except OSError as exc:
        raise SegMetricError(
            f"Could not save the preset to '{path}': {exc.strerror}."
        ) from exc


def load_scale_preset(path) -> ScaleSettings:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except OSError as exc:
        raise SegMetricError(
            f"Could not read the preset file '{path}': {exc.strerror}."
        ) from exc
    except json.JSONDecodeError as exc:
        raise SegMetricError(
            f"'{path}' is not a valid preset file (invalid JSON)."
        ) from exc

    try:
        return settings_from_dict(data)
    except (TypeError, AttributeError) as exc:
        raise SegMetricError(
            f"'{path}' doesn't look like a SegMetric.Scale preset file."
        ) from exc
