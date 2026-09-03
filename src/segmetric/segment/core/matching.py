import csv
import os
from dataclasses import dataclass
from typing import Optional

from segmetric.errors import SegMetricError
from segmetric.mask.core.tagging import find_tagged_mask
from segmetric.tag.core.discovery import find_input_files

# segmetric.scale's pipeline saves crops as "<original_stem>_cropped.<ext>".
CROPPED_SUFFIX = "_cropped"
BLANK_TAG = "blank"


@dataclass
class MatchedItem:
    path: str
    original_stem: str
    mm_per_pixel: float
    scale_source: str
    mask_path: Optional[str] = None
    mask_tag: str = ""


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


def match_crops(crops_dir, scale_csv_path, masks_dir=None, exclude_blank_tagged=True):
    """Discover crop images (via tag's find_input_files) and join each to
    its mm_per_pixel from scale_csv_path (segmetric.scale's scales.csv or
    segmetric.prepare's summary.csv, both accepted as-is via the shared
    file_name/mm_per_pixel columns) and, if masks_dir is given, its
    segmetric.mask output mask (any tag, via find_tagged_mask).

    A crop whose only matching mask is tagged "blank" is dropped from the
    batch entirely when exclude_blank_tagged is True (the default) -- a
    blank specimen has nothing to measure. A "_damage" tag or any custom
    tag is used as-is (a damaged wing may still be partly measurable).

    Returns (matched, unmatched_names, no_mask_names):
    - matched: list[MatchedItem] -- mask_path is None for any crop with no
      usable mask; the caller falls back to segmenting the whole image
      (segment_cells' own "no wing mask" behavior) with a warning.
    - unmatched_names: crop basenames with no scale row at all (excluded
      from matched).
    - no_mask_names: matched crop basenames that had no usable mask --
      only ever populated when masks_dir was given.
    """
    crop_paths = find_input_files(crops_dir)
    scale_by_stem = _load_scale_rows_by_stem(scale_csv_path)

    matched = []
    unmatched_names = []
    no_mask_names = []

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

        mask_path, mask_tag = None, ""
        if masks_dir:
            mask_path, mask_tag = find_tagged_mask(masks_dir, original_stem)
            if mask_path is not None and mask_tag == BLANK_TAG and exclude_blank_tagged:
                continue  # dropped entirely -- not even counted as "no mask"
            if mask_path is None:
                no_mask_names.append(os.path.basename(crop_path))

        matched.append(
            MatchedItem(
                path=crop_path,
                original_stem=original_stem,
                mm_per_pixel=mm_per_pixel,
                scale_source=row.get("scale_source", ""),
                mask_path=mask_path,
                mask_tag=mask_tag,
            )
        )

    return matched, unmatched_names, no_mask_names
