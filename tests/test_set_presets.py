import os

import pytest

from segmetric.errors import SegMetricError
from segmetric.set.core.model import Preset, Segment
from segmetric.set.core.presets import apply_preset, load_preset, save_preset


def make_segments():
    return [
        Segment(index=0, raw_value="H6", column_name="col_1"),
        Segment(index=1, raw_value="120HR", column_name="col_2"),
        Segment(index=2, raw_value="RH", column_name="col_3"),
    ]


def test_save_and_load_round_trip(tmp_path):
    preset = Preset(
        name="RH_protocol",
        segments=[
            Segment(index=0, raw_value="H6", column_name="hive_id", include=True),
            Segment(index=1, raw_value="120HR", column_name="duration", include=False),
            Segment(index=2, raw_value="RH", column_name="code", include=True),
        ],
        object_id_column="code",
    )
    path = os.path.join(tmp_path, "preset.json")

    save_preset(path, preset)
    loaded = load_preset(path)

    assert loaded.name == "RH_protocol"
    assert loaded.object_id_column == "code"
    assert [s.column_name for s in loaded.segments] == ["hive_id", "duration", "code"]
    assert [s.include for s in loaded.segments] == [True, False, True]
    # raw_value is never persisted -- round trip always comes back blank
    assert all(s.raw_value == "" for s in loaded.segments)


def test_loading_a_minimal_preset_json_works(tmp_path):
    path = os.path.join(tmp_path, "old_preset.json")
    with open(path, "w") as f:
        f.write(
            '{"name": "old", "segments": [{"index": 0, "column_name": "a", '
            '"include": true}], "object_id_column": null}'
        )
    loaded = load_preset(path)
    assert loaded.name == "old"


def test_saved_json_has_no_merge_fields(tmp_path):
    preset = Preset(name="p", segments=make_segments(), object_id_column="col_3")
    path = os.path.join(tmp_path, "preset.json")
    save_preset(path, preset)

    with open(path) as f:
        raw = f.read()

    assert "merge" not in raw.lower()
    assert "raw_value" not in raw


def test_load_missing_file_raises_segmetric_error(tmp_path):
    with pytest.raises(SegMetricError):
        load_preset(os.path.join(tmp_path, "does_not_exist.json"))


def test_load_invalid_json_raises_segmetric_error(tmp_path):
    path = os.path.join(tmp_path, "bad.json")
    with open(path, "w") as f:
        f.write("{not valid json")
    with pytest.raises(SegMetricError):
        load_preset(path)


def test_apply_preset_matches_by_index():
    current = make_segments()
    preset = Preset(
        name="p",
        segments=[
            Segment(index=0, raw_value="", column_name="hive_id", include=True),
            Segment(index=1, raw_value="", column_name="duration", include=False),
            Segment(index=2, raw_value="", column_name="code", include=True),
        ],
        object_id_column="code",
    )

    updated, object_id_column, warnings = apply_preset(current, preset)

    assert [s.column_name for s in updated] == ["hive_id", "duration", "code"]
    assert [s.include for s in updated] == [True, False, True]
    # raw_value from the live sample is preserved, not overwritten
    assert [s.raw_value for s in updated] == ["H6", "120HR", "RH"]
    assert object_id_column == "code"
    assert warnings == []


def test_apply_preset_with_fewer_current_segments_warns_about_extras():
    current = make_segments()[:2]  # only 2 segments this time
    preset = Preset(
        name="p",
        segments=[
            Segment(index=0, raw_value="", column_name="hive_id"),
            Segment(index=1, raw_value="", column_name="duration"),
            Segment(index=2, raw_value="", column_name="code"),
        ],
        object_id_column="code",
    )

    updated, object_id_column, warnings = apply_preset(current, preset)

    assert len(updated) == 2
    assert object_id_column is None  # "code" segment doesn't exist in current
    assert any("extra segment" in w.lower() for w in warnings)
    assert any("code" in w for w in warnings)  # object-id column not found, warned


def test_apply_preset_with_more_current_segments_warns_about_missing():
    current = make_segments()  # 3 segments
    preset = Preset(
        name="p",
        segments=[Segment(index=0, raw_value="", column_name="hive_id")],
        object_id_column=None,
    )

    updated, object_id_column, warnings = apply_preset(current, preset)

    assert len(updated) == 3
    assert updated[0].column_name == "hive_id"
    # segments 1 and 2 had no matching preset entry, left at their defaults
    assert updated[1].column_name == "col_2"
    assert updated[2].column_name == "col_3"
    assert len(warnings) == 2
