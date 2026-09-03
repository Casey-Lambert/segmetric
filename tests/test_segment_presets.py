import os

import pytest

from segmetric.errors import SegMetricError
from segmetric.segment.core.model import DEFAULT_PRESETS, DetectionSettings, PresetGroup, SegmentPreset
from segmetric.segment.core.presets import (
    load_object_id_mapping,
    load_segment_preset,
    save_object_id_mapping,
    save_segment_preset,
)


def test_segment_preset_round_trips(tmp_path):
    preset = SegmentPreset(
        name="My Preset",
        steps=["radial"],
        detection=DetectionSettings(
            sato_sigma_min=1.5,
            sato_sigma_max=5.0,
            local_thresh_block_size=51,
            local_thresh_offset=-0.05,
            vein_close_px=7,
            min_vein_size=200,
            distance_gaussian_sigma=2.0,
            h_maxima_h=4.0,
        ),
    )
    path = os.path.join(tmp_path, "preset.json")

    save_segment_preset(path, preset)
    loaded = load_segment_preset(path)

    assert loaded == preset


def test_default_presets_round_trip(tmp_path):
    for name, preset in DEFAULT_PRESETS.items():
        path = os.path.join(tmp_path, f"{name}.json")
        save_segment_preset(path, preset)
        assert load_segment_preset(path) == preset


def test_load_missing_preset_raises(tmp_path):
    with pytest.raises(SegMetricError):
        load_segment_preset(os.path.join(tmp_path, "nope.json"))


def test_load_invalid_json_preset_raises(tmp_path):
    path = os.path.join(tmp_path, "bad.json")
    with open(path, "w") as f:
        f.write("{not valid")
    with pytest.raises(SegMetricError):
        load_segment_preset(path)


def test_object_id_mapping_round_trips(tmp_path):
    groups = [
        PresetGroup(object_ids=["AA", "AB"], preset=DEFAULT_PRESETS["Forewing Cell"]),
        PresetGroup(object_ids=["LG"], preset=DEFAULT_PRESETS["Leg Segments"]),
    ]
    path = os.path.join(tmp_path, "mapping.json")

    save_object_id_mapping(path, groups)
    loaded = load_object_id_mapping(path)

    assert len(loaded) == 2
    assert loaded[0].object_ids == ["AA", "AB"]
    assert loaded[0].preset == DEFAULT_PRESETS["Forewing Cell"]
    assert loaded[1].object_ids == ["LG"]
    assert loaded[1].preset == DEFAULT_PRESETS["Leg Segments"]


def test_load_invalid_mapping_raises(tmp_path):
    path = os.path.join(tmp_path, "bad_mapping.json")
    with open(path, "w") as f:
        f.write('[{"object_ids": ["AA"]}]')  # missing "preset"
    with pytest.raises(SegMetricError):
        load_object_id_mapping(path)
