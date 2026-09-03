import csv
import os

from segmetric.segment.core.matching import MatchedItem
from segmetric.segment.core.model import DEFAULT_PRESETS
from segmetric.segment.core.pipeline import (
    apply_step_measurement,
    new_row,
    resolve_preset,
    step_field_names,
    write_csv,
)
from segmetric.set.core.model import Preset, Segment


def test_step_field_names():
    assert step_field_names("radial") == [
        "radial_area_px", "radial_area_mm2", "radial_bbox_w_px",
        "radial_bbox_h_px", "radial_bbox_w_mm", "radial_bbox_h_mm",
    ]


def test_apply_step_measurement_prefixes_columns():
    row = new_row("panel_01_cropped.png")
    measurement = dict(
        area_px=100, area_mm2=0.5, bbox_w_px=10, bbox_h_px=10, bbox_w_mm=1.0, bbox_h_mm=1.0
    )
    apply_step_measurement(row, "radial", measurement)

    assert row["radial_area_px"] == 100
    assert row["radial_bbox_w_mm"] == 1.0
    assert row["file_name"] == "panel_01_cropped.png"
    assert row["status"] == ""


def test_resolve_preset_single_batch_returns_preset_directly():
    item = MatchedItem(path="x", original_stem="panel_01", mm_per_pixel=0.02, scale_source="measured")
    preset, object_id, reason = resolve_preset(item, DEFAULT_PRESETS["Forewing Cell"], None)
    assert preset == DEFAULT_PRESETS["Forewing Cell"]
    assert object_id is None
    assert reason is None


def _object_id_preset():
    return Preset(
        name="test",
        segments=[Segment(index=1, raw_value="", column_name="ObjectID", include=True)],
        object_id_column="ObjectID",
    )


def test_resolve_preset_mixed_batch_resolves_by_object_id():
    item = MatchedItem(path="x", original_stem="H6_AA", mm_per_pixel=0.02, scale_source="measured")
    resolver = {"AA": DEFAULT_PRESETS["Forewing Cell"]}
    preset, object_id, reason = resolve_preset(item, resolver, _object_id_preset())
    assert preset == DEFAULT_PRESETS["Forewing Cell"]
    assert object_id == "AA"
    assert reason is None


def test_resolve_preset_mixed_batch_unassigned_object_id_is_flagged():
    item = MatchedItem(path="x", original_stem="H6_AC", mm_per_pixel=0.02, scale_source="measured")
    resolver = {"AA": DEFAULT_PRESETS["Forewing Cell"]}
    preset, object_id, reason = resolve_preset(item, resolver, _object_id_preset())
    assert preset is None
    assert object_id == "AC"
    assert "AC" in reason


def test_resolve_preset_mixed_batch_without_metadata_preset_is_flagged():
    item = MatchedItem(path="x", original_stem="H6_AA", mm_per_pixel=0.02, scale_source="measured")
    resolver = {"AA": DEFAULT_PRESETS["Forewing Cell"]}
    preset, object_id, reason = resolve_preset(item, resolver, None)
    assert preset is None
    assert object_id is None
    assert reason is not None


def test_write_csv_single_step_shape(tmp_path):
    row1 = new_row("a.png")
    apply_step_measurement(
        row1, "radial",
        dict(area_px=1, area_mm2=1.0, bbox_w_px=1, bbox_h_px=1, bbox_w_mm=1.0, bbox_h_mm=1.0),
    )
    row1["status"] = "measured"
    row2 = new_row("b.png")
    row2["status"] = "blank"

    out_path = os.path.join(tmp_path, "out.csv")
    write_csv(out_path, [row1, row2], all_steps=["radial"])

    with open(out_path) as f:
        rows = list(csv.DictReader(f))

    assert set(rows[0].keys()) == {"file_name", "status", *step_field_names("radial")}
    assert rows[0]["status"] == "measured"
    assert rows[1]["status"] == "blank"
    assert rows[1]["radial_area_px"] == ""  # blank crop never reached this step


def test_write_csv_multi_step_and_extra_columns(tmp_path):
    row = new_row("leg.png")
    apply_step_measurement(
        row, "femur",
        dict(area_px=1, area_mm2=1.0, bbox_w_px=1, bbox_h_px=1, bbox_w_mm=1.0, bbox_h_mm=1.0),
    )
    # "tibia" step never reached for this row -- should still appear, blank.
    row["Colony"] = "H6"
    row["object_id"] = "LG"
    row["preset_used"] = "Leg Segments"

    out_path = os.path.join(tmp_path, "out.csv")
    write_csv(
        out_path, [row], all_steps=["femur", "tibia"],
        extra_columns=["Colony"], include_object_id=True, include_preset_used=True,
    )

    with open(out_path) as f:
        rows = list(csv.DictReader(f))

    row_out = rows[0]
    assert row_out["femur_area_px"] == "1"
    assert row_out["tibia_area_px"] == ""
    assert row_out["Colony"] == "H6"
    assert row_out["object_id"] == "LG"
    assert row_out["preset_used"] == "Leg Segments"
