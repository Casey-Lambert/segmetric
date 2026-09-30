
import json
from dataclasses import asdict, fields

from segmetric.errors import SegMetricError

from .model import DetectionSettings, PresetGroup, SegmentPreset

_DETECTION_FIELDS = [f.name for f in fields(DetectionSettings)]


def detection_to_dict(settings: DetectionSettings) -> dict:
    return asdict(settings)


def detection_from_dict(data: dict) -> DetectionSettings:
    return DetectionSettings(**{name: data[name] for name in _DETECTION_FIELDS})


def preset_to_dict(preset: SegmentPreset) -> dict:
    return {
        "name": preset.name,
        "steps": list(preset.steps),
        "detection": detection_to_dict(preset.detection),
    }


def preset_from_dict(data: dict) -> SegmentPreset:
    return SegmentPreset(
        name=data.get("name", "Custom"),
        steps=list(data.get("steps", [])),
        detection=detection_from_dict(data["detection"]),
    )


def save_segment_preset(path, preset: SegmentPreset):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(preset_to_dict(preset), f, indent=2)
    except OSError as exc:
        raise SegMetricError(
            f"Could not save the preset to '{path}': {exc.strerror}."
        ) from exc


def load_segment_preset(path) -> SegmentPreset:
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
            f"'{path}' doesn't look like a SegMetric.Segment preset file."
        ) from exc


def save_object_id_mapping(path, groups):
    """Save a mixed-batch object-id -> preset mapping template: a list of
    PresetGroup(object_ids, preset), each preset embedded inline so the
    template is fully self-contained.
    """
    data = [
        {"object_ids": list(group.object_ids), "preset": preset_to_dict(group.preset)}
        for group in groups
    ]
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except OSError as exc:
        raise SegMetricError(
            f"Could not save the mapping template to '{path}': {exc.strerror}."
        ) from exc


def load_object_id_mapping(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except OSError as exc:
        raise SegMetricError(
            f"Could not read the mapping template file '{path}': {exc.strerror}."
        ) from exc
    except json.JSONDecodeError as exc:
        raise SegMetricError(
            f"'{path}' is not a valid mapping template file (invalid JSON)."
        ) from exc

    try:
        return [
            PresetGroup(object_ids=list(entry["object_ids"]), preset=preset_from_dict(entry["preset"]))
            for entry in data
        ]
    except (KeyError, TypeError) as exc:
        raise SegMetricError(
            f"'{path}' doesn't look like a SegMetric.Segment mapping template file."
        ) from exc
