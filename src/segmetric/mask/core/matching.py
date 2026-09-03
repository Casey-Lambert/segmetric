import csv
import os
from dataclasses import dataclass

from segmetric.errors import SegMetricError
from segmetric.tag.core.discovery import find_input_files

# segmetric.scale's pipeline saves crops as "<original_stem>_cropped.<ext>"
# (see segmetric/scale/core/pipeline.py's out_name construction).
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
    """Discover crop images in crops_dir (via tag's find_input_files) and
    match each to its mm_per_pixel from scale_csv_path (segmetric.scale's
    scales.csv or segmetric.prepare's summary.csv -- both key rows by the
    same file_name/mm_per_pixel columns).

    Matching is an exact stem match: a crop saved as "<stem>_cropped.<ext>"
    is looked up by "<stem>" against the scale CSV's own file_name column
    (also stripped to its stem) -- see core/matching.py's module docstring
    in the plan for why this is exact, not the notebook's fuzzy heuristic.

    Returns (matched, unmatched_names): matched is a list[MatchedCrop];
    unmatched_names is a list of crop file basenames that had no scale row
    (missing entirely, or an unparseable mm_per_pixel value) -- the caller
    is expected to surface these rather than silently drop them.
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
