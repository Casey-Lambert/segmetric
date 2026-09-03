"""Crop <-> scale-row <-> optional-mask matching is identical to
segmetric.segment's -- same inputs (crops dir, scale CSV, optional masks
dir with a _blank-tag exclusion toggle), same MatchedItem shape. Reused
directly rather than duplicated, mirroring how segment/core/correction.py
re-exports segmetric.mask's apply_brush_stroke instead of copying it.
"""
from segmetric.segment.core.matching import MatchedItem, match_crops  # noqa: F401 -- re-exported
