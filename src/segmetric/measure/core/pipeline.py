"""segmetric.measure's own core layer is deliberately thin. Unlike
segmetric.prepare (which has one top-to-bottom run_prepare_job because tag
and scale are both fully unattended batch pipelines), mask/segment/landmark
aren't uniform that way: mask is an unattended batch job, but segment and
landmark have no batch entry point at all -- their entire "processing" is
the interactive ReviewWindow click-through. Control has to return to the
GUI event loop between stages, so there's no single job function to write
here. Instead, this module holds the small reusable pieces the GUI layer
composes itself: building each stage's matched-crop list (delegating to
mask's/segment's own matching functions, not reimplementing them),
resolving where a "no masks folder specified" run should look for masks,
and deciding which stages run in what order.
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

    Thin call-through to mask.core.matching.match_crops_to_scale_rows --
    the Mask stage needs no masks_dir/blank-exclusion concept of its own
    (it's the tool that *produces* masks), so this exists mainly so the
    GUI layer imports one "build a batch for this stage" function per
    stage, symmetrically, rather than reaching into mask's/segment's
    matching modules directly with different call shapes.
    """
    return match_crops_to_scale_rows(crops_folder, scales_file)


def build_segment_or_landmark_batch(scales_file, crops_folder, masks_dir, exclude_blank_tagged):
    """-> (matched: list[MatchedItem], unmatched_names, no_mask_names).

    Both the Segment and Landmark stages call this identically -- only
    masks_dir/exclude_blank_tagged differ between them, and both are
    already tab-scoped GUI state by the time this is called. Thin
    call-through to segment.core.matching.match_crops (landmark reuses
    the same function via its own core.matching re-export).
    """
    return match_crops(crops_folder, scales_file, masks_dir, exclude_blank_tagged=exclude_blank_tagged)


def resolve_masks_dir(output_folder, mask_stage_enabled, explicit_masks_folder):
    """Where should the Segment/Landmark stages look for masks?

    If the Mask stage is enabled for this run, always read from its own
    output location (nothing else could have produced masks yet this
    session) -- regardless of any explicit masks-folder value a tab might
    otherwise carry. Otherwise fall back to explicit_masks_folder (or
    None, meaning "no mask reference/constraint," same as the standalone
    tools' default today).
    """
    if mask_stage_enabled:
        return os.path.join(output_folder, MASKS_SUBDIR)
    return explicit_masks_folder or None


def enabled_stage_order(mask_enabled, segment_enabled, landmark_enabled):
    """Fixed Mask -> Segment -> Landmark order, skipping disabled stages.

    Mask goes first because it's the only stage that can produce masks
    for the other two to auto-chain from (see resolve_masks_dir); Segment
    before Landmark is an arbitrary but stable tie-break.
    """
    order = []
    if mask_enabled:
        order.append("mask")
    if segment_enabled:
        order.append("segment")
    if landmark_enabled:
        order.append("landmark")
    return order
