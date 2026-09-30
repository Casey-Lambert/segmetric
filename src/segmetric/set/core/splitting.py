
import os

from .model import Segment


def split_filename_to_segments(file_path):
    """Split a file's name (without extension) on '_' into ordered Segments.
    """
    stem = os.path.splitext(os.path.basename(file_path))[0]
    parts = stem.split("_")
    return [
        Segment(index=i, raw_value=part, column_name=f"col_{i + 1}")
        for i, part in enumerate(parts)
    ]

