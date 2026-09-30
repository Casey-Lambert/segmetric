from segmetric.set.core.model import Preset
from segmetric.set.core.splitting import split_filename_to_segments


def apply_preset_to_filename(file_path, preset: Preset) -> dict:
    """Split file_path the same way it is split in segmetric.set, then 
    maps the resulting segments onto the image

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
    """Included column names in the original oreder, keeps it consistant."""
    ordered_segments = sorted(preset.segments, key=lambda segment: segment.index)
    return [segment.column_name for segment in ordered_segments if segment.include]
