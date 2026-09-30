
import csv
import os
from dataclasses import dataclass

from segmetric.errors import SegMetricError
from segmetric.tag.core.discovery import find_input_files

# preserved saving methods saves crops as "<original_stem>_cropped.<ext>"
# 


CROPPED_SUFFIX = "_cropped"


@dataclass
class MatchedCrop:
    path: str
    original_stem: str
    mm_per_pixel: float
    scale_source: str


def _original_stem(crop_path):
    stem = os.path.splitext(os.path.basename(crop_path))[0]
    return stem[: -len(CROPPED_SUFFIX)] if stem.endswith(CROPPED_SUFFIX) else stem


def _load_scale_rows_by_stem(scale_csv_path):
    try:
        with open(scale_csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames or []
            if "file_name" not in fieldnames or "mm_per_pixel" not in fieldnames:
                raise SegMetricError(
                    f"'{scale_csv_path}' doesn't look like a scale CSV -- expected "
                    "at least 'file_name' and 'mm_per_pixel' columns (accepts "
                    "either segmetric.scale's scales.csv or segmetric.prepare's "
                    "summary.csv as-is)."
                )
            rows = list(reader)
    except OSError as exc:
        raise SegMetricError(
            f"Could not read the scales file '{scale_csv_path}': {exc.strerror}."
        ) from exc

    return {os.path.splitext(row["file_name"])[0]: row for row in rows}


def match_crops_to_scale_rows(crops_dir, scale_csv_path):
    """Discover crop images in crops_dir and
    match to refrence  mm_per_pixel from scale_csv_path (generated with segmetric.scale)
     or summary.csv (generated with segmetric.prepare)

    Exact stem match:  "<stem>_cropped.<ext>"
    Scale looked up by "<stem>" against the scale CSV's file_name column

    Returns (matched, unmatched_names): matched is a list[MatchedCrop];
    unmatched_names is a list of file basenames that had no scale
    (missing entirely, or non-real value) which would be dropped if not corrected
    """
    crop_paths = find_input_files(crops_dir)
    scale_by_stem = _load_scale_rows_by_stem(scale_csv_path)

    matched = []
    unmatched_names = []
    for crop_path in crop_paths:
        original_stem = _original_stem(crop_path)
        row = scale_by_stem.get(original_stem)
        mm_per_pixel = None
        if row is not None:
            try:
                mm_per_pixel = float(row["mm_per_pixel"])
            except (KeyError, ValueError):
                mm_per_pixel = None

        if mm_per_pixel is None:
            unmatched_names.append(os.path.basename(crop_path))
            continue

        matched.append(
            MatchedCrop(
                path=crop_path,
                original_stem=original_stem,
                mm_per_pixel=mm_per_pixel,
                scale_source=row.get("scale_source", ""),
            )
        )

    return matched, unmatched_names
