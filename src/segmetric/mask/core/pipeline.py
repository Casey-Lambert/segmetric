
import csv
import os
from dataclasses import dataclass, field

import cv2
from PIL import Image

from segmetric.errors import SegMetricError
from segmetric.prepare.core.metadata import apply_preset_to_filename, preset_column_order
from segmetric.set.core.model import Preset

from .masking import generate_mask
from .measurement import measure_object
from .model import FilterSettings
from .tagging import tagged_mask_filename



MASKS_SUBDIR = "masks"
CSV_FILENAME = "mask_measurements.csv"
MASK_STATUS_AUTO = "auto"
MASK_STATUS_CORRECTED = "corrected"

BASE_FIELDS = [
    "file_name",
    "length_px",
    "width_px",
    "length_mm",
    "width_mm",
    "area_px",
    "area_mm2",
    "mask_status",
    "tag",
]


@dataclass
class MaskJobResult:
    output_dir: str
    masks_dir: str = ""
    csv_path: str = ""
    masks_saved: int = 0
    rows: list = field(default_factory=list)  # dicts, one per successfully-masked crop
    skipped: list = field(default_factory=list)  # (file_name, reason)
    interrupted: bool = False


def _resolve_filter(item, filter_resolver, metadata_preset: Preset):
    """Return (FilterSettings_or_None, object_id_or_None, error_reason_or_None).

    filter_resolver is a single FilterSettings (applied to every
    item) or a dict[object_id -> FilterSettings] (mixed-anatomy batches --
    each item's own object id, sourced from metadata_preset and assigns
    filter).
    """
    if isinstance(filter_resolver, FilterSettings):
        return filter_resolver, None, None

    if metadata_preset is None or metadata_preset.object_id_column is None:
        return None, None, "No object-id column available to resolve a filter."

    metadata_row = apply_preset_to_filename(item.original_stem, metadata_preset)
    object_id = metadata_row.get(metadata_preset.object_id_column)
    if not object_id:
        return None, None, "Could not read an object id from the filename."

    settings = filter_resolver.get(object_id)
    if settings is None:
        return None, object_id, f"Object id '{object_id}' has no assigned filter."
    return settings, object_id, None


def _save_mask(mask, out_path):
    Image.fromarray((mask * 255).astype("uint8")).save(out_path, dpi=(1200, 1200))


def _write_csv(output_folder, rows, extra_columns, include_object_id, include_filter_used):
    fieldnames = list(BASE_FIELDS) + list(extra_columns)
    if include_object_id:
        fieldnames.append("object_id")
    if include_filter_used:
        fieldnames.append("filter_used")

    csv_path = os.path.join(output_folder, CSV_FILENAME)
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return csv_path



def run_mask_job(
    matched_crops,
    filter_resolver,
    output_folder,
    metadata_preset: Preset = None,
    progress_cb=None,
    should_stop=None,
):
    """Generate a mask + length/width measurement for every image in the batch
    """
    masks_dir = os.path.join(output_folder, MASKS_SUBDIR)
    try:
        os.makedirs(masks_dir, exist_ok=True)
    except OSError as exc:
        raise SegMetricError(
            f"Could not create the output folder '{masks_dir}': {exc.strerror}."
        ) from exc

    result = MaskJobResult(output_dir=output_folder, masks_dir=masks_dir)

    def stop_requested():
        return should_stop is not None and should_stop()

    def report(fraction, message):
        if progress_cb is not None:
            progress_cb(fraction, message)

    total = len(matched_crops)
    report(0.0, f"Found {total} matched crop(s).")

    extra_columns = preset_column_order(metadata_preset) if metadata_preset is not None else []
    include_object_id = metadata_preset is not None and metadata_preset.object_id_column is not None
    include_filter_used = metadata_preset is not None

    for i, item in enumerate(matched_crops, start=1):
        if stop_requested():
            result.interrupted = True
            break

        file_name = os.path.basename(item.path)
        report((i - 1) / max(total, 1), f"Processing {i} of {total}: {file_name}")

        settings, object_id, error_reason = _resolve_filter(item, filter_resolver, metadata_preset)
        if settings is None:
            result.skipped.append((file_name, error_reason))
            continue

        image_bgr = cv2.imread(item.path)
        if image_bgr is None:
            result.skipped.append((file_name, "Could not read the image."))
            continue

        mask = generate_mask(image_bgr, settings)
        measurement = measure_object(mask, item.mm_per_pixel)

        mask_out_path = os.path.join(masks_dir, tagged_mask_filename(item.original_stem, ""))
        _save_mask(mask, mask_out_path)
        result.masks_saved += 1

        row = {
            "file_name": file_name,
            **measurement,
            "mask_status": MASK_STATUS_AUTO,
            "tag": "",
        }

        metadata_row = {}
        if metadata_preset is not None:
            metadata_row = apply_preset_to_filename(item.original_stem, metadata_preset)
        for column in extra_columns:
            row[column] = metadata_row.get(column, "")

        if include_object_id:
            row["object_id"] = object_id or metadata_row.get(metadata_preset.object_id_column, "")
        if include_filter_used:
            row["filter_used"] = settings.name or "(unnamed)"

        result.rows.append(row)

    csv_path = _write_csv(output_folder, result.rows, extra_columns, include_object_id, include_filter_used)
    result.csv_path = csv_path

    if result.interrupted:
        report(
            len(result.rows) / max(total, 1),
            f"Stopped — {result.masks_saved} mask(s) saved to {masks_dir}.",
        )
    else:
        report(1.0, f"Done — {result.masks_saved} mask(s) saved, CSV at {csv_path}.")

    return result
