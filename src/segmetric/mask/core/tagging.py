import glob
import os

MASK_SUFFIX = "_mask.png"


def tagged_mask_filename(original_stem, tag):
    """Build a mask PNG's filename for original_stem, with tag (a bare word,
    e.g. "damage" -- no leading underscore) inserted before "_mask.png".
    tag="" (or None) gives the plain, untagged filename.
    """
    if tag:
        return f"{original_stem}_{tag}{MASK_SUFFIX}"
    return f"{original_stem}{MASK_SUFFIX}"


def retag_mask_file(masks_dir, original_stem, old_tag, new_tag):
    """Rename original_stem's mask PNG on disk from its old_tag name to its
    new_tag name (see tagged_mask_filename). A no-op beyond returning the
    (unchanged) path if old_tag == new_tag, or if the old file doesn't
    exist yet (nothing to rename -- the caller is about to write it fresh).

    Only ever touches segmetric.mask's own output (the mask PNG) -- never
    the original crop image.

    Returns the new mask path.
    """
    old_path = os.path.join(masks_dir, tagged_mask_filename(original_stem, old_tag))
    new_path = os.path.join(masks_dir, tagged_mask_filename(original_stem, new_tag))
    if old_path != new_path and os.path.exists(old_path):
        os.replace(old_path, new_path)
    return new_path


def find_tagged_mask(masks_dir, original_stem):
    """Find original_stem's mask PNG in masks_dir regardless of what tag (if
    any) it currently carries, and report that tag back -- for callers (like
    segmetric.segment) that need to locate a mask without knowing in advance
    whether it was ever tagged.

    Returns (path, tag): tag is "" for the plain, untagged file, or the tag
    word (e.g. "damage") for a tagged one. Returns (None, None) if no mask
    exists for this stem at all.
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
