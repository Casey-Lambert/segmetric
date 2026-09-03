import csv
import os

from segmetric.set.core.model import Preset

from .metadata import apply_preset_to_filename, preset_column_order

SUMMARY_FILENAME = "summary.csv"
SCALE_BASE_FIELDS = ["file_name", "mm_per_pixel", "scale_source"]


def write_summary_csv(scale_csv_path, output_path, preset: Preset = None):
    """Read scale's scales.csv and write output_path with the same rows,
    plus preset's columns (applied to each row's file_name) if given.

    With no preset, this is effectively a copy of scale_csv_path under
    SCALE_BASE_FIELDS -- always one predictable summary file to check,
    whether or not a preset was used.
    """
    with open(scale_csv_path, newline="", encoding="utf-8") as f:
        scale_rows = list(csv.DictReader(f))

    extra_columns = preset_column_order(preset) if preset is not None else []
    fieldnames = SCALE_BASE_FIELDS + extra_columns

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in scale_rows:
            out_row = {field: row.get(field, "") for field in SCALE_BASE_FIELDS}
            if preset is not None:
                metadata = apply_preset_to_filename(row["file_name"], preset)
                for column in extra_columns:
                    out_row[column] = metadata.get(column, "")
            writer.writerow(out_row)

    return output_path


def summary_path_for(output_folder):
    return os.path.join(output_folder, SUMMARY_FILENAME)
