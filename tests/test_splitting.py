import numpy as np
import pytest

from segmetric.tag.core.errors import SegMetricError
from segmetric.tag.core.splitting import split_into_grid


def make_image(height, width):
    return np.arange(height * width * 3, dtype=np.uint8).reshape(height, width, 3)


def test_4x4_matches_notebook_behavior():
    image = make_image(400, 800)
    panels = split_into_grid(image, rows=4, cols=4)

    assert len(panels) == 16
    assert [p["index"] for p in panels] == list(range(1, 17))

    # row-major order: row 0's four columns first, then row 1, etc.
    assert [(p["row"], p["col"]) for p in panels[:4]] == [(0, 0), (0, 1), (0, 2), (0, 3)]

    first = panels[0]
    assert first["bbox"] == (0, 0, 200, 100)
    assert first["panel"].shape == (100, 200, 3)


def test_1x1_returns_whole_image():
    image = make_image(50, 60)
    panels = split_into_grid(image, rows=1, cols=1)
    assert len(panels) == 1
    assert panels[0]["bbox"] == (0, 0, 60, 50)


def test_8x8_grid_covers_full_image_with_no_gaps():
    image = make_image(801, 803)  # deliberately not evenly divisible
    panels = split_into_grid(image, rows=8, cols=8)
    assert len(panels) == 64

    # last row/col of each must reach the true image edge (remainder absorbed)
    bottom_right = panels[-1]
    assert bottom_right["bbox"][2] == 803
    assert bottom_right["bbox"][3] == 801


def test_non_square_rows_and_cols():
    image = make_image(300, 800)
    panels = split_into_grid(image, rows=3, cols=5)
    assert len(panels) == 15
    assert [(p["row"], p["col"]) for p in panels[:5]] == [
        (0, 0), (0, 1), (0, 2), (0, 3), (0, 4)
    ]


def test_invalid_grid_raises_segmetric_error():
    image = make_image(100, 100)
    with pytest.raises(SegMetricError):
        split_into_grid(image, rows=0, cols=4)
