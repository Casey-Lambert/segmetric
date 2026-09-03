import csv

from segmetric.prepare.core.metadata import apply_preset_to_filename
from segmetric.set.core.model import Preset

from .model import SegmentPreset

STATUS_MEASURED = "measured"
STATUS_BLANK = "blank"
STATUS_DAMAGED = "damaged"

BASE_FIELDS = ["file_name", "status"]
STEP_FIELD_SUFFIXES = ["area_px", "area_mm2", "bbox_w_px", "bbox_h_px", "bbox_w_mm", "bbox_h_mm"]

CSV_FILENAME = "segment_measurements.csv"


def step_field_names(step):
    return [f"{step}_{suffix}" for suffix in STEP_FIELD_SUFFIXES]


def new_row(file_name):
    return {"file_name": file_name, "status": ""}


def apply_step_measurement(row, step, measurement):
    """Write one step's measure_cell() result into row under that step's
    prefixed column names (e.g. "radial_area_px", "femur_bbox_w_mm").
    Mutates and returns row.
    """
    for suffix in STEP_FIELD_SUFFIXES:
        row[f"{step}_{suffix}"] = measurement[suffix]
    return row


def resolve_preset(item, preset_resolver, metadata_preset: Preset):
    """Return (SegmentPreset_or_None, object_id_or_None, error_reason_or_None).

    preset_resolver is either a single SegmentPreset (applied to every
    item -- single-batch) or a dict[object_id -> SegmentPreset]
    (mixed-batch -- each item's own object id, read via metadata_preset,
    selects its preset). Mirrors segmetric.mask.core.pipeline._resolve_filter.
    """
    if isinstance(preset_resolver, SegmentPreset):
        return preset_resolver, None, None

    if metadata_preset is None or metadata_preset.object_id_column is None:
        return None, None, "No object-id column available to resolve a preset."

    metadata_row = apply_preset_to_filename(item.original_stem, metadata_preset)
    object_id = metadata_row.get(metadata_preset.object_id_column)
    if not object_id:
        return None, None, "Could not read an object id from the filename."

    preset = preset_resolver.get(object_id)
    if preset is None:
        return None, object_id, f"Object id '{object_id}' has no assigned preset."
    return preset, object_id, None


def write_csv(
    output_path,
    rows,
    all_steps,
    extra_columns=(),
    include_object_id=False,
    include_preset_used=False,
):
    """Write rows (list of dicts, one per crop -- see new_row/
    apply_step_measurement) to output_path.

    Column order: file_name, status, then every step's 6 columns (in
    all_steps' order -- pass the union of every step across every preset
    actually used in this batch), then extra metadata columns, then
    object_id/preset_used if requested. A row missing a column (a crop
    that hasn't reached a given step yet, is blank/damaged, or wasn't in a
    mixed-batch's preset) is written as "".
    """
    fieldnames = list(BASE_FIELDS)
    for step in all_steps:
        fieldnames.extend(step_field_names(step))
    fieldnames.extend(extra_columns)
    if include_object_id:
        fieldnames.append("object_id")
    if include_preset_used:
        fieldnames.append("preset_used")

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, restval="")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return output_path
