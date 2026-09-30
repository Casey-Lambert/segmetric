
"""segmetric.measure calls other core processes, operates as a shell that 
groups other processes together 
"""

import os

from segmetric.mask.core.matching import MatchedCrop, match_crops_to_scale_rows
from segmetric.mask.core.pipeline import MASKS_SUBDIR
from segmetric.segment.core.matching import MatchedItem, match_crops

__all__ = [
    "MatchedCrop",
    "MatchedItem",
    "build_mask_batch",
    "build_segment_or_landmark_batch",
    "resolve_masks_dir",
    "enabled_stage_order",
]


def build_mask_batch(scales_file, crops_folder):
    """-> (matched: list[MatchedCrop], unmatched_names: list[str]).
    """
    return match_crops_to_scale_rows(crops_folder, scales_file)


def build_segment_or_landmark_batch(scales_file, crops_folder, masks_dir, exclude_blank_tagged):
    """-> (matched: list[MatchedItem], unmatched_names, no_mask_names).
    Both the Segment and Landmark stages call this identically
    """
    return match_crops(crops_folder, scales_file, masks_dir, exclude_blank_tagged=exclude_blank_tagged)


def resolve_masks_dir(output_folder, mask_stage_enabled, explicit_masks_folder):
    """Looking for masks. If the Mask stage is enabled for this run, always read the runs own
    output location 
    """
    if mask_stage_enabled:
        return os.path.join(output_folder, MASKS_SUBDIR)
    return explicit_masks_folder or None


def enabled_stage_order(mask_enabled, segment_enabled, landmark_enabled):
    """Fixed Mask -> Segment -> Landmark order, skipping disabled stages.
    Mask goes first, other two processes sting togther after mask.
    """
    order = []
    if mask_enabled:
        order.append("mask")
    if segment_enabled:
        order.append("segment")
    if landmark_enabled:
        order.append("landmark")
    return order

