import os

from .model import Segment


def split_filename_to_segments(file_path):
    """Split a file's name (without extension) on '_' into ordered Segments.

    Matches the existing filename convention across the SegMetric suite,
    e.g. 'H6_120HR_34C_NR_1004_RH.pdf' -> 6 segments. column_name defaults to
    'col_<n>' (1-based) and is expected to be renamed by the user in the GUI.
    """
    stem = os.path.splitext(os.path.basename(file_path))[0]
    parts = stem.split("_")
    return [
        Segment(index=i, raw_value=part, column_name=f"col_{i + 1}")
        for i, part in enumerate(parts)
    ]
