

import json
from dataclasses import asdict, fields

from segmetric.errors import SegMetricError

from .model import FilterGroup, FilterSettings

_NUMERIC_FILTER_FIELDS = [f.name for f in fields(FilterSettings) if f.name != "name"]




def filter_to_dict(settings: FilterSettings) -> dict:
    return asdict(settings)


def filter_from_dict(data: dict) -> FilterSettings:
    numeric = {name: data[name] for name in _NUMERIC_FILTER_FIELDS}
    return FilterSettings(**numeric, name=data.get("name", ""))


def save_filter_preset(path, settings: FilterSettings):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(filter_to_dict(settings), f, indent=2)
    except OSError as exc:
        raise SegMetricError(
            f"Could not save the filter preset to '{path}': {exc.strerror}."
        ) from exc


def load_filter_preset(path) -> FilterSettings:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except OSError as exc:
        raise SegMetricError(
            f"Could not read the filter preset file '{path}': {exc.strerror}."
        ) from exc
    except json.JSONDecodeError as exc:
        raise SegMetricError(
            f"'{path}' is not a valid filter preset file (invalid JSON)."
        ) from exc

    try:
        return filter_from_dict(data)
    except (KeyError, TypeError) as exc:
        raise SegMetricError(
            f"'{path}' doesn't look like a SegMetric.Mask filter preset file."
        ) from exc




def save_object_id_mapping(path, groups):
    """Save a mixed-anatomy filter mapping template: a list of
    FilterGroup(object_ids, filter), each filter embedded inline so the template is fully self-contained.
    """
    data = [
        {"object_ids": list(group.object_ids), "filter": filter_to_dict(group.filter)}
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
            FilterGroup(object_ids=list(entry["object_ids"]), filter=filter_from_dict(entry["filter"]))
            for entry in data
        ]
    except (KeyError, TypeError) as exc:
        raise SegMetricError(
            f"'{path}' doesn't look like a SegMetric.Mask mapping template file."
        ) from exc
