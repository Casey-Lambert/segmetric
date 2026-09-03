import os

import pytest

from segmetric.errors import SegMetricError
from segmetric.mask.core.model import DEFAULT_FILTERS, FilterGroup, FilterSettings
from segmetric.mask.core.presets import (
    load_filter_preset,
    load_object_id_mapping,
    save_filter_preset,
    save_object_id_mapping,
)


def test_filter_preset_round_trips(tmp_path):
    settings = FilterSettings(
        first_pass_factor=0.33,
        normal_thresh=0.55,
        vein_thresh=0.20,
        erode_px=6,
        close_px=30,
        fourier_freq=0.015,
        min_blob=100,
        name="My Custom Filter",
    )
    path = os.path.join(tmp_path, "filter.json")

    save_filter_preset(path, settings)
    loaded = load_filter_preset(path)

    assert loaded == settings


def test_default_filter_round_trips(tmp_path):
    path = os.path.join(tmp_path, "forewing.json")
    save_filter_preset(path, DEFAULT_FILTERS["Forewing"])
    assert load_filter_preset(path) == DEFAULT_FILTERS["Forewing"]


def test_load_missing_filter_preset_raises_segmetric_error(tmp_path):
    with pytest.raises(SegMetricError):
        load_filter_preset(os.path.join(tmp_path, "nope.json"))


def test_load_invalid_json_filter_preset_raises_segmetric_error(tmp_path):
    path = os.path.join(tmp_path, "bad.json")
    with open(path, "w") as f:
        f.write("{not valid json")
    with pytest.raises(SegMetricError):
        load_filter_preset(path)


def test_load_filter_preset_missing_fields_raises_segmetric_error(tmp_path):
    path = os.path.join(tmp_path, "partial.json")
    with open(path, "w") as f:
        f.write('{"first_pass_factor": 0.4}')
    with pytest.raises(SegMetricError):
        load_filter_preset(path)


def test_object_id_mapping_round_trips(tmp_path):
    groups = [
        FilterGroup(object_ids=["AA", "AB"], filter=DEFAULT_FILTERS["Forewing"]),
        FilterGroup(object_ids=["BA"], filter=DEFAULT_FILTERS["Leg"]),
    ]
    path = os.path.join(tmp_path, "mapping.json")

    save_object_id_mapping(path, groups)
    loaded = load_object_id_mapping(path)

    assert len(loaded) == 2
    assert loaded[0].object_ids == ["AA", "AB"]
    assert loaded[0].filter == DEFAULT_FILTERS["Forewing"]
    assert loaded[1].object_ids == ["BA"]
    assert loaded[1].filter == DEFAULT_FILTERS["Leg"]


def test_load_invalid_mapping_raises_segmetric_error(tmp_path):
    path = os.path.join(tmp_path, "bad_mapping.json")
    with open(path, "w") as f:
        f.write('[{"object_ids": ["AA"]}]')  # missing "filter"
    with pytest.raises(SegMetricError):
        load_object_id_mapping(path)
