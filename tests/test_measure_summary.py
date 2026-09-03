import csv
import os

from segmetric.measure.core.summary import (
    SUMMARY_FILENAME,
    summary_path_for,
    write_measure_summary_csv,
)


def _write_csv(path, fieldnames, rows):
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def test_summary_with_only_one_stage_csv_present(tmp_path):
    _write_csv(
        tmp_path / "mask_measurements.csv",
        ["file_name", "length_mm", "mask_status", "tag"],
        [{"file_name": "a.png", "length_mm": "3.1", "mask_status": "auto", "tag": ""}],
    )

    write_measure_summary_csv(str(tmp_path))

    with open(tmp_path / SUMMARY_FILENAME) as f:
        header = next(csv.reader(f))
    with open(tmp_path / SUMMARY_FILENAME) as f:
        rows = list(csv.DictReader(f))

    assert header == ["file_name", "mask_length_mm", "mask_mask_status", "mask_tag"]
    assert rows == [
        {"file_name": "a.png", "mask_length_mm": "3.1", "mask_mask_status": "auto", "mask_tag": ""}
    ]


def test_summary_outer_joins_by_file_name_with_blank_missing_side(tmp_path):
    _write_csv(
        tmp_path / "mask_measurements.csv",
        ["file_name", "length_mm"],
        [{"file_name": "a.png", "length_mm": "3.1"}, {"file_name": "b.png", "length_mm": "2.0"}],
    )
    _write_csv(
        tmp_path / "segment_measurements.csv",
        ["file_name", "radial_area_mm2"],
        [{"file_name": "a.png", "radial_area_mm2": "0.9"}, {"file_name": "c.png", "radial_area_mm2": "1.1"}],
    )

    write_measure_summary_csv(str(tmp_path))

    with open(tmp_path / SUMMARY_FILENAME) as f:
        rows = list(csv.DictReader(f))

    by_name = {r["file_name"]: r for r in rows}
    assert set(by_name) == {"a.png", "b.png", "c.png"}
    assert by_name["a.png"]["mask_length_mm"] == "3.1"
    assert by_name["a.png"]["segment_radial_area_mm2"] == "0.9"
    # b.png has no segment row -> blank, not missing/KeyError
    assert by_name["b.png"]["segment_radial_area_mm2"] == ""
    # c.png has no mask row -> blank
    assert by_name["c.png"]["mask_length_mm"] == ""


def test_summary_prefixes_colliding_status_column_per_stage(tmp_path):
    _write_csv(
        tmp_path / "segment_measurements.csv",
        ["file_name", "status"],
        [{"file_name": "a.png", "status": "measured"}],
    )
    _write_csv(
        tmp_path / "landmark_measurements.csv",
        ["file_name", "status"],
        [{"file_name": "a.png", "status": "blank"}],
    )

    write_measure_summary_csv(str(tmp_path))

    with open(tmp_path / SUMMARY_FILENAME) as f:
        rows = list(csv.DictReader(f))

    assert len(rows) == 1
    # Neither stage's status silently overwrote the other's.
    assert rows[0]["segment_status"] == "measured"
    assert rows[0]["landmark_status"] == "blank"
    assert "status" not in rows[0]


def test_summary_pulls_shared_metadata_and_object_id_columns_unprefixed_once(tmp_path):
    common = {"file_name": "a.png", "hive_id": "H6", "object_id": "Forewing"}
    _write_csv(
        tmp_path / "mask_measurements.csv",
        ["file_name", "hive_id", "object_id", "length_mm"],
        [{**common, "length_mm": "3.1"}],
    )
    _write_csv(
        tmp_path / "segment_measurements.csv",
        ["file_name", "hive_id", "object_id", "status"],
        [{**common, "status": "measured"}],
    )

    write_measure_summary_csv(str(tmp_path), metadata_columns=["hive_id"])

    with open(tmp_path / SUMMARY_FILENAME) as f:
        header = next(csv.reader(f))
    with open(tmp_path / SUMMARY_FILENAME) as f:
        rows = list(csv.DictReader(f))

    # exactly one unprefixed hive_id and one unprefixed object_id column
    assert header.count("hive_id") == 1
    assert header.count("object_id") == 1
    assert "mask_hive_id" not in header
    assert "segment_hive_id" not in header
    assert rows[0]["hive_id"] == "H6"
    assert rows[0]["object_id"] == "Forewing"


def test_summary_returns_none_and_writes_nothing_when_no_stage_csv_exists(tmp_path):
    result = write_measure_summary_csv(str(tmp_path))
    assert result is None
    assert not (tmp_path / SUMMARY_FILENAME).exists()


def test_summary_column_order_is_metadata_then_object_id_then_mask_then_segment_then_landmark(tmp_path):
    common = {"file_name": "a.png", "hive_id": "H6", "object_id": "Forewing"}
    _write_csv(
        tmp_path / "mask_measurements.csv",
        ["file_name", "hive_id", "object_id", "length_mm"],
        [{**common, "length_mm": "3.1"}],
    )
    _write_csv(
        tmp_path / "segment_measurements.csv",
        ["file_name", "hive_id", "object_id", "status"],
        [{**common, "status": "measured"}],
    )
    _write_csv(
        tmp_path / "landmark_measurements.csv",
        ["file_name", "hive_id", "object_id", "n_landmarks"],
        [{**common, "n_landmarks": "5"}],
    )

    write_measure_summary_csv(str(tmp_path), metadata_columns=["hive_id"])

    with open(tmp_path / SUMMARY_FILENAME) as f:
        header = next(csv.reader(f))

    assert header == [
        "file_name",
        "hive_id",
        "object_id",
        "mask_length_mm",
        "segment_status",
        "landmark_n_landmarks",
    ]


def test_summary_path_for(tmp_path):
    assert summary_path_for(str(tmp_path)) == os.path.join(str(tmp_path), "measure_summary.csv")
