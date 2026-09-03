import csv
import os

from segmetric.landmark.core.measurement import landmark_field_names, landmark_row_fields
from segmetric.landmark.core.pipeline import new_row, write_csv


def test_write_csv_single_label_shape(tmp_path):
    row1 = new_row("a.png")
    row1.update(landmark_row_fields({"1": (1.0, 2.0)}, ["1"], mm_per_pixel=1.0))
    row1["status"] = "measured"
    row2 = new_row("b.png")
    row2["status"] = "blank"

    out_path = os.path.join(tmp_path, "out.csv")
    write_csv(out_path, [row1, row2], all_labels=["1"])

    with open(out_path) as f:
        rows = list(csv.DictReader(f))

    expected_cols = {"file_name", "status", "n_landmarks", "centroid_size_mm", *landmark_field_names("1")}
    assert set(rows[0].keys()) == expected_cols
    assert rows[0]["status"] == "measured"
    assert rows[0]["1_x_px"] == "1.0"
    assert rows[1]["status"] == "blank"
    assert rows[1]["1_x_px"] == ""  # blank crop never got a point


def test_write_csv_multi_label_and_extra_columns(tmp_path):
    row = new_row("leg.png")
    # "2" never placed for this row -- should still appear as a column, blank.
    row.update(landmark_row_fields({"1": (5.0, 5.0)}, ["1", "2"], mm_per_pixel=2.0))
    row["Colony"] = "H6"
    row["object_id"] = "LG"

    out_path = os.path.join(tmp_path, "out.csv")
    write_csv(
        out_path, [row], all_labels=["1", "2"],
        extra_columns=["Colony"], include_object_id=True,
    )

    with open(out_path) as f:
        rows = list(csv.DictReader(f))

    row_out = rows[0]
    assert row_out["1_x_mm"] == "10.0"
    assert row_out["2_x_px"] == ""
    assert row_out["n_landmarks"] == "1"
    assert row_out["Colony"] == "H6"
    assert row_out["object_id"] == "LG"


def test_write_csv_freeform_labels_are_whatever_the_batch_actually_used(tmp_path):
    # Placement is freeform per crop -- rows can use entirely different
    # label sets (e.g. one crop renamed a point, another left it numbered).
    row1 = new_row("a.png")
    row1.update(landmark_row_fields({"tip": (1.0, 1.0), "2": (2.0, 2.0)}, ["tip", "2"], mm_per_pixel=1.0))
    row1["status"] = "measured"
    row2 = new_row("b.png")
    row2.update(landmark_row_fields({"1": (3.0, 3.0)}, ["1"], mm_per_pixel=1.0))
    row2["status"] = "measured"

    out_path = os.path.join(tmp_path, "out.csv")
    write_csv(out_path, [row1, row2], all_labels=["tip", "2", "1"])

    with open(out_path) as f:
        rows = list(csv.DictReader(f))

    assert rows[0]["tip_x_px"] == "1.0"
    assert rows[0]["1_x_px"] == ""  # row1 never used label "1"
    assert rows[1]["1_x_px"] == "3.0"
    assert rows[1]["tip_x_px"] == ""  # row2 never used label "tip"
