import os

import pytest

from segmetric.tag.core.discovery import find_input_files
from segmetric.tag.core.errors import SegMetricError


def test_finds_all_supported_extensions(tmp_path):
    names = ["a.pdf", "b.png", "c.jpg", "d.jpeg", "e.tif", "f.tiff", "g.txt"]
    for name in names:
        (tmp_path / name).write_bytes(b"x")

    found = {os.path.basename(p) for p in find_input_files(str(tmp_path))}
    assert found == {"a.pdf", "b.png", "c.jpg", "d.jpeg", "e.tif", "f.tiff"}


def test_missing_folder_raises_segmetric_error(tmp_path):
    with pytest.raises(SegMetricError):
        find_input_files(str(tmp_path / "does_not_exist"))


def test_empty_folder_raises_segmetric_error(tmp_path):
    with pytest.raises(SegMetricError):
        find_input_files(str(tmp_path))
