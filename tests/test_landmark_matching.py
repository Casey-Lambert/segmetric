"""segmetric.landmark.core.matching just re-exports
segmetric.segment.core.matching's match_crops/MatchedItem (see that
module's own thorough tests in test_segment_matching.py for the underlying
behavior) -- this only confirms the re-export wiring itself works.
"""
import csv

import cv2
import numpy as np

from segmetric.landmark.core.matching import MatchedItem, match_crops
from segmetric.segment.core.matching import MatchedItem as SegmentMatchedItem
from segmetric.segment.core.matching import match_crops as segment_match_crops


def test_reexports_the_same_objects_as_segment():
    assert match_crops is segment_match_crops
    assert MatchedItem is SegmentMatchedItem


def test_match_crops_works_through_the_reexport(tmp_path):
    crops_dir = tmp_path / "crops"
    crops_dir.mkdir()
    cv2.imwrite(str(crops_dir / "panel_01_cropped.png"), np.full((20, 20, 3), 200, dtype=np.uint8))
    scale_csv = tmp_path / "scales.csv"
    with open(scale_csv, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["file_name", "mm_per_pixel", "scale_source"])
        writer.writerow(["panel_01.png", "0.02", "measured"])

    matched, unmatched, no_mask = match_crops(str(crops_dir), str(scale_csv))

    assert unmatched == []
    assert no_mask == []
    assert len(matched) == 1
    assert matched[0].original_stem == "panel_01"
