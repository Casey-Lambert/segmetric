from segmetric.prepare.core.metadata import apply_preset_to_filename, preset_column_order
from segmetric.set.core.model import Preset, Segment


def make_preset():
    return Preset(
        name="test",
        segments=[
            Segment(index=0, raw_value="", column_name="hive_id", include=True),
            Segment(index=1, raw_value="", column_name="duration", include=True),
            Segment(index=2, raw_value="", column_name="internal_only", include=False),
            Segment(index=3, raw_value="", column_name="code", include=True),
        ],
        object_id_column="code",
    )


def test_apply_preset_extracts_included_columns_by_position(tmp_path):
    preset = make_preset()
    file_path = tmp_path / "H6_120HR_34C_RH.png"

    row = apply_preset_to_filename(str(file_path), preset)

    assert row == {"hive_id": "H6", "duration": "120HR", "code": "RH"}
    assert "internal_only" not in row


def test_apply_preset_omits_positions_beyond_filename_length(tmp_path):
    preset = make_preset()  # expects 4 segments
    file_path = tmp_path / "H6_120HR.png"  # only 2 tokens

    row = apply_preset_to_filename(str(file_path), preset)

    assert row == {"hive_id": "H6", "duration": "120HR"}


def test_apply_preset_omits_extra_filename_tokens_beyond_preset(tmp_path):
    preset = make_preset()  # expects 4 segments (indices 0-3)
    file_path = tmp_path / "H6_120HR_34C_RH_EXTRA.png"  # 5 tokens

    row = apply_preset_to_filename(str(file_path), preset)

    assert "EXTRA" not in row.values()
    assert row == {"hive_id": "H6", "duration": "120HR", "code": "RH"}


def test_preset_column_order_respects_segment_index_and_include():
    preset = make_preset()
    assert preset_column_order(preset) == ["hive_id", "duration", "code"]


def test_preset_column_order_empty_when_nothing_included():
    preset = Preset(
        name="none",
        segments=[Segment(index=0, raw_value="", column_name="x", include=False)],
    )
    assert preset_column_order(preset) == []
