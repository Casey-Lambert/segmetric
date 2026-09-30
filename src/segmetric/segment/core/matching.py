
import csv
import os

from dataclasses import dataclass
from typing import Optional

from segmetric.errors import SegMetricError
from segmetric.mask.core.tagging import find_tagged_mask
from segmetric.tag.core.discovery import find_input_files

#------------------------------------------------------

CROPPED_SUFFIX = "_cropped" #  "<original_stem>_cropped.<ext>".
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
                    f"'{scale_csv_path}' not a scale.csv"
                    "(accepts segmetric.scale's scales.csv or segmetric.prepare's summary.csv as-is)."
                )
            rows = list(reader)
    except OSError as exc:
        raise SegMetricError(
            f"Could not read the scales file '{scale_csv_path}': {exc.strerror}."
        ) from exc

    return {os.path.splitext(row["file_name"])[0]: row for row in rows}


def match_crops(crops_dir, scale_csv_path, masks_dir=None, exclude_blank_tagged=True):
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
                continue  
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




