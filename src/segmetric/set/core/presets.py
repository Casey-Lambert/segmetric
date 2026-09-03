import json

from segmetric.errors import SegMetricError

from .model import Preset, Segment


def preset_to_dict(preset: Preset) -> dict:
    return {
        "name": preset.name,
        "segments": [
            {
                "index": segment.index,
                "column_name": segment.column_name,
                "include": segment.include,
            }
            for segment in preset.segments
        ],
        "object_id_column": preset.object_id_column,
    }


def preset_from_dict(data: dict) -> Preset:
    segments = [
        Segment(
            index=entry["index"],
            raw_value="",
            column_name=entry["column_name"],
            include=entry.get("include", True),
        )
        for entry in data.get("segments", [])
    ]
    return Preset(
        name=data.get("name", ""),
        segments=segments,
        object_id_column=data.get("object_id_column"),
    )


def save_preset(path, preset: Preset):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(preset_to_dict(preset), f, indent=2)
    except OSError as exc:
        raise SegMetricError(
            f"Could not save the preset to '{path}': {exc.strerror}."
        ) from exc


def load_preset(path) -> Preset:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except OSError as exc:
        raise SegMetricError(
            f"Could not read the preset file '{path}': {exc.strerror}."
        ) from exc
    except json.JSONDecodeError as exc:
        raise SegMetricError(
            f"'{path}' is not a valid preset file (invalid JSON)."
        ) from exc

    try:
        return preset_from_dict(data)
    except (KeyError, TypeError) as exc:
        raise SegMetricError(
            f"'{path}' doesn't look like a SegMetric.Set preset file."
        ) from exc


def apply_preset(current_segments, preset: Preset):
    """Apply a loaded preset's column_name/include (matched by index) onto
    current_segments -- segments freshly split from a live sample file, so
    they carry real raw_value.

    Returns (updated_segments, object_id_column, warnings):
    - updated_segments: current_segments with column_name/include overwritten
      wherever the preset has a matching index; segments the preset has no
      entry for are left at their defaults.
    - object_id_column: the preset's flagged column name, if a segment with
      that column_name still exists after applying; otherwise None.
    - warnings: human-readable strings describing any index mismatch between
      the preset and the current sample file.
    """
    by_index = {segment.index: segment for segment in preset.segments}
    updated = []
    warnings = []

    for segment in current_segments:
        saved = by_index.pop(segment.index, None)
        if saved is not None:
            updated.append(
                Segment(
                    index=segment.index,
                    raw_value=segment.raw_value,
                    column_name=saved.column_name,
                    include=saved.include,
                )
            )
        else:
            updated.append(segment)
            warnings.append(
                f"Segment {segment.index + 1} ('{segment.raw_value}') has no "
                "matching entry in the loaded preset -- left at its default."
            )

    if by_index:
        extra = ", ".join(str(i + 1) for i in sorted(by_index))
        warnings.append(
            f"The loaded preset has extra segment(s) ({extra}) that don't "
            "exist in the current sample file -- ignored."
        )

    object_id_column = None
    updated_names = {segment.column_name for segment in updated}
    if preset.object_id_column in updated_names:
        object_id_column = preset.object_id_column
    elif preset.object_id_column is not None:
        warnings.append(
            f"The preset's object-id column ('{preset.object_id_column}') "
            "wasn't found among the current segments -- no row is flagged."
        )

    return updated, object_id_column, warnings
