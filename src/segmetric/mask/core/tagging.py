

import glob
import os

MASK_SUFFIX = "_mask.png"




def tagged_mask_filename(original_stem, tag):
    """Build a PNG's filename for original_stem, with tag inserted before "_mask.png".
    tag="".
    """
    if tag:
        return f"{original_stem}_{tag}{MASK_SUFFIX}"
    return f"{original_stem}{MASK_SUFFIX}"


def retag_mask_file(masks_dir, original_stem, old_tag, new_tag):
    """Rename original_stem's mask PNG 

    Only applies to segmetric.mask output, preserves
    the original crop image.

    """
    old_path = os.path.join(masks_dir, tagged_mask_filename(original_stem, old_tag))
    new_path = os.path.join(masks_dir, tagged_mask_filename(original_stem, new_tag))
    if old_path != new_path and os.path.exists(old_path):
        os.replace(old_path, new_path)
    return new_path



def find_tagged_mask(masks_dir, original_stem):
    """Find original_stem mask PNG in masks_dir regardless of tag.
    """
    untagged_path = os.path.join(masks_dir, tagged_mask_filename(original_stem, ""))
    if os.path.exists(untagged_path):
        return untagged_path, ""

    pattern = os.path.join(
        glob.escape(masks_dir), f"{glob.escape(original_stem)}_*{MASK_SUFFIX}"
    )
    matches = sorted(glob.glob(pattern))
    if not matches:
        return None, None

    path = matches[0]
    filename = os.path.basename(path)
    tag = filename[len(original_stem) + 1 : -len(MASK_SUFFIX)]
    return path, tag
