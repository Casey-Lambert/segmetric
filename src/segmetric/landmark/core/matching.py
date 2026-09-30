

"""Crop <-> scale-row <-> optional-mask
Data matching is identical to segmetric.segment's system
Reused directly (not duplicated), then it mirrors how segment/core/correction.py
re-exports data with segmetric.mask's apply_brush_stroke instead of copying it.
"""
from segmetric.segment.core.matching import MatchedItem, match_crops  # noqa: F401 -- re-exported
