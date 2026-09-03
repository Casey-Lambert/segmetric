import os

from segmetric.mask.core.tagging import find_tagged_mask, retag_mask_file, tagged_mask_filename


def test_tagged_mask_filename_with_no_tag():
    assert tagged_mask_filename("panel_01", "") == "panel_01_mask.png"
    assert tagged_mask_filename("panel_01", None) == "panel_01_mask.png"


def test_tagged_mask_filename_with_tag():
    assert tagged_mask_filename("panel_01", "damage") == "panel_01_damage_mask.png"
    assert tagged_mask_filename("panel_01", "reshoot") == "panel_01_reshoot_mask.png"


def test_retag_mask_file_renames_on_disk(tmp_path):
    masks_dir = str(tmp_path)
    original = os.path.join(masks_dir, "panel_01_mask.png")
    with open(original, "wb") as f:
        f.write(b"fake png bytes")

    new_path = retag_mask_file(masks_dir, "panel_01", old_tag="", new_tag="damage")

    assert new_path == os.path.join(masks_dir, "panel_01_damage_mask.png")
    assert os.path.exists(new_path)
    assert not os.path.exists(original)


def test_retag_mask_file_clears_tag(tmp_path):
    masks_dir = str(tmp_path)
    tagged = os.path.join(masks_dir, "panel_01_damage_mask.png")
    with open(tagged, "wb") as f:
        f.write(b"fake png bytes")

    new_path = retag_mask_file(masks_dir, "panel_01", old_tag="damage", new_tag="")

    assert new_path == os.path.join(masks_dir, "panel_01_mask.png")
    assert os.path.exists(new_path)
    assert not os.path.exists(tagged)


def test_retag_mask_file_switches_tags(tmp_path):
    masks_dir = str(tmp_path)
    blank_path = os.path.join(masks_dir, "panel_01_blank_mask.png")
    with open(blank_path, "wb") as f:
        f.write(b"fake png bytes")

    new_path = retag_mask_file(masks_dir, "panel_01", old_tag="blank", new_tag="damage")

    assert new_path == os.path.join(masks_dir, "panel_01_damage_mask.png")
    assert os.path.exists(new_path)
    assert not os.path.exists(blank_path)


def test_retag_mask_file_same_tag_is_a_noop(tmp_path):
    masks_dir = str(tmp_path)
    path = os.path.join(masks_dir, "panel_01_damage_mask.png")
    with open(path, "wb") as f:
        f.write(b"fake png bytes")

    new_path = retag_mask_file(masks_dir, "panel_01", old_tag="damage", new_tag="damage")

    assert new_path == path
    assert os.path.exists(path)


def test_retag_mask_file_missing_old_file_just_returns_new_path(tmp_path):
    masks_dir = str(tmp_path)
    # Nothing on disk yet -- caller is about to write it fresh.
    new_path = retag_mask_file(masks_dir, "panel_01", old_tag="", new_tag="damage")
    assert new_path == os.path.join(masks_dir, "panel_01_damage_mask.png")
    assert not os.path.exists(new_path)


def test_find_tagged_mask_returns_none_when_nothing_exists(tmp_path):
    assert find_tagged_mask(str(tmp_path), "panel_01") == (None, None)


def test_find_tagged_mask_finds_untagged(tmp_path):
    masks_dir = str(tmp_path)
    path = os.path.join(masks_dir, "panel_01_mask.png")
    with open(path, "wb") as f:
        f.write(b"x")

    found_path, tag = find_tagged_mask(masks_dir, "panel_01")
    assert found_path == path
    assert tag == ""


def test_find_tagged_mask_finds_damage_tagged(tmp_path):
    masks_dir = str(tmp_path)
    path = os.path.join(masks_dir, "panel_01_damage_mask.png")
    with open(path, "wb") as f:
        f.write(b"x")

    found_path, tag = find_tagged_mask(masks_dir, "panel_01")
    assert found_path == path
    assert tag == "damage"


def test_find_tagged_mask_finds_custom_tagged(tmp_path):
    masks_dir = str(tmp_path)
    path = os.path.join(masks_dir, "panel_01_reshoot_mask.png")
    with open(path, "wb") as f:
        f.write(b"x")

    found_path, tag = find_tagged_mask(masks_dir, "panel_01")
    assert found_path == path
    assert tag == "reshoot"


def test_find_tagged_mask_prefers_untagged_over_a_stale_tagged_file(tmp_path):
    masks_dir = str(tmp_path)
    untagged = os.path.join(masks_dir, "panel_01_mask.png")
    tagged = os.path.join(masks_dir, "panel_01_damage_mask.png")
    for p in (untagged, tagged):
        with open(p, "wb") as f:
            f.write(b"x")

    found_path, tag = find_tagged_mask(masks_dir, "panel_01")
    assert found_path == untagged
    assert tag == ""


def test_find_tagged_mask_does_not_confuse_similar_stems(tmp_path):
    masks_dir = str(tmp_path)
    # "panel_1" is a prefix of "panel_10" -- must not cross-match.
    with open(os.path.join(masks_dir, "panel_10_damage_mask.png"), "wb") as f:
        f.write(b"x")

    assert find_tagged_mask(masks_dir, "panel_1") == (None, None)
