from segmetric.tag.core.naming import (
    OcrRegion,
    compute_search_bbox,
    cv_filename,
    sequential_filename,
)


def test_default_region_matches_notebooks_bottom_half():
    # Original notebook: img[int(H * 0.5):, :] -- bottom half, full width.
    bbox = compute_search_bbox((200, 100, 3), OcrRegion())
    assert bbox == (0, 100, 100, 200)


def test_top_anchor():
    bbox = compute_search_bbox((200, 100, 3), OcrRegion(v_anchor="top", v_size_pct=25))
    assert bbox == (0, 0, 100, 50)


def test_bottom_anchor_smaller_band():
    bbox = compute_search_bbox((200, 100, 3), OcrRegion(v_anchor="bottom", v_size_pct=10))
    assert bbox == (0, 180, 100, 200)


def test_horizontal_right_anchor():
    bbox = compute_search_bbox(
        (200, 100, 3), OcrRegion(h_anchor="right", h_size_pct=20)
    )
    assert bbox[0] == 80  # x1
    assert bbox[2] == 100  # x2 reaches the right edge


def test_horizontal_left_anchor_default_full_width():
    bbox = compute_search_bbox((200, 100, 3), OcrRegion())
    assert bbox[0] == 0
    assert bbox[2] == 100


def test_full_region_covers_whole_panel():
    bbox = compute_search_bbox(
        (200, 100, 3), OcrRegion(v_anchor="top", v_size_pct=100, h_anchor="left", h_size_pct=100)
    )
    assert bbox == (0, 0, 100, 200)


def test_sequential_filename_defaults_to_tiff():
    assert sequential_filename(1, "20260101_000000") == "panel_01_20260101_000000.tiff"


def test_sequential_filename_png():
    assert (
        sequential_filename(3, "20260101_000000", output_format="png")
        == "panel_03_20260101_000000.png"
    )


def test_sequential_filename_jpeg_uses_jpg_extension():
    assert (
        sequential_filename(3, "20260101_000000", output_format="jpeg")
        == "panel_03_20260101_000000.jpg"
    )


def test_cv_filename_defaults_to_tiff():
    assert cv_filename(2, "20260101_000000", "H11_72HR") == "H11_72HR_p02_20260101_000000.tiff"


def test_cv_filename_fallback_label_respects_output_format():
    name = cv_filename(5, "20260101_000000", "", output_format="png")
    assert name == "panel_05_RENAME_ME_p05_20260101_000000.png"
