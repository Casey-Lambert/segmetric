import csv
import os

from segmetric.prepare.core.summary import write_summary_csv
from segmetric.set.core.model import Preset, Segment


def write_scale_csv(path, rows):
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["file_name", "mm_per_pixel", "scale_source"])
        for row in rows:
            writer.writerow(row)


def test_summary_without_preset_is_a_plain_copy(tmp_path):
    scale_csv = tmp_path / "scales.csv"
    write_scale_csv(scale_csv, [("H6_120HR_RH.png", "0.05", "measured")])
    output_path = tmp_path / "summary.csv"

    write_summary_csv(str(scale_csv), str(output_path))

    with open(output_path) as f:
        rows = list(csv.DictReader(f))

    assert rows == [{"file_name": "H6_120HR_RH.png", "mm_per_pixel": "0.05", "scale_source": "measured"}]


def test_summary_with_preset_adds_metadata_columns(tmp_path):
    scale_csv = tmp_path / "scales.csv"
    write_scale_csv(
        scale_csv,
        [
            ("H6_120HR_RH.png", "0.05", "measured"),
            ("H7_130HR_LF.png", "0.06", "batch_median"),
        ],
    )
    output_path = tmp_path / "summary.csv"

    preset = Preset(
        name="p",
        segments=[
            Segment(index=0, raw_value="", column_name="hive_id"),
            Segment(index=1, raw_value="", column_name="duration"),
            Segment(index=2, raw_value="", column_name="code"),
        ],
    )

    write_summary_csv(str(scale_csv), str(output_path), preset=preset)

    with open(output_path) as f:
        rows = list(csv.DictReader(f))

    assert rows[0]["file_name"] == "H6_120HR_RH.png"
    assert rows[0]["hive_id"] == "H6"
    assert rows[0]["duration"] == "120HR"
    assert rows[0]["code"] == "RH"
    assert rows[0]["scale_source"] == "measured"

    assert rows[1]["hive_id"] == "H7"
    assert rows[1]["scale_source"] == "batch_median"


def test_summary_preset_columns_come_after_scale_columns(tmp_path):
    scale_csv = tmp_path / "scales.csv"
    write_scale_csv(scale_csv, [("H6_120HR_RH.png", "0.05", "measured")])
    output_path = tmp_path / "summary.csv"

    preset = Preset(
        name="p", segments=[Segment(index=0, raw_value="", column_name="hive_id")]
    )
    write_summary_csv(str(scale_csv), str(output_path), preset=preset)

    with open(output_path) as f:
        header = next(csv.reader(f))

    assert header == ["file_name", "mm_per_pixel", "scale_source", "hive_id"]
