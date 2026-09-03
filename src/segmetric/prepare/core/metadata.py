from segmetric.set.core.model import Preset
from segmetric.set.core.splitting import split_filename_to_segments


def apply_preset_to_filename(file_path, preset: Preset) -> dict:
    """Split file_path's name the same way segmetric.set does, then map the
    resulting segments through preset.segments by position.

    Returns an ordered {column_name: raw_value} dict of only the segments
    the preset marked included. Positions the preset has no entry for (or
    that don't exist in file_path's own filename) are simply omitted -- this
    is expected to run against panel filenames the preset wasn't built from
    directly, so a loose, best-effort match is more useful than an error.
    """
    segments = split_filename_to_segments(file_path)
    by_index = {segment.index: segment for segment in preset.segments}

    row = {}
    for segment in segments:
        saved = by_index.get(segment.index)
        if saved is not None and saved.include:
            row[saved.column_name] = segment.raw_value
    return row


def preset_column_order(preset: Preset) -> list:
    """Included column names, in the preset's original segment order."""
    ordered_segments = sorted(preset.segments, key=lambda segment: segment.index)
    return [segment.column_name for segment in ordered_segments if segment.include]
