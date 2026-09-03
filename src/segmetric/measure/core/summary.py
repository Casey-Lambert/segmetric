"""Combine whichever of mask/segment/landmark's own measurement CSVs exist
in a segmetric.measure output folder into one measure_summary.csv.

Unlike segmetric.prepare's own core/summary.py (which just copies scale's
scales.csv and derives metadata columns by re-parsing each row's
file_name -- there's only ever one real data CSV in that pipeline), this
module does a genuine multi-CSV outer join: mask/segment/landmark each
already write their own metadata/object_id columns into their own CSV
(every one of them independently calls
segmetric.prepare.core.metadata.apply_preset_to_filename when saving), so
there's nothing to re-derive here -- only columns to join and, where two
stages happen to use the same column name (segment and landmark both
write a literal "status" column; mask has both "tag" and "mask_status"),
to keep unambiguous.
"""
import csv
import os

MASK_CSV = "mask_measurements.csv"
SEGMENT_CSV = "segment_measurements.csv"
LANDMARK_CSV = "landmark_measurements.csv"
SUMMARY_FILENAME = "measure_summary.csv"

# Fixed mask -> segment -> landmark priority/order, reused for both the
# stage-column prefixing and the shared-column per-row fallback lookup.
_STAGE_FILES = [
    ("mask", MASK_CSV),
    ("segment", SEGMENT_CSV),
    ("landmark", LANDMARK_CSV),
]


def _read_csv_rows(path):
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)
    return fieldnames, rows


def write_measure_summary_csv(output_folder, metadata_columns=()):
    """Outer-join by file_name across whichever of mask_measurements.csv /
    segment_measurements.csv / landmark_measurements.csv exist directly in
    output_folder. Which stages are included is decided purely by file
    presence (not by an in-memory "which stages ran this session" flag),
    so this can be regenerated later against a folder that accumulated
    stages across multiple separate segmetric-measure runs. Returns None
    (writes nothing) if none of the three exist yet.

    Column layout: file_name, then metadata_columns (in the order given)
    followed by "object_id" -- each pulled unprefixed from the first
    stage, in mask -> segment -> landmark priority, whose own CSV actually
    has that column and a row for that file_name; not repeated. Then every
    remaining column from each present stage's CSV, renamed
    f"{stage}_{original_column}" unconditionally (e.g. mask_length_mm,
    segment_status, landmark_status) -- prefixing is applied regardless of
    whether a collision would actually occur this run, so column names
    stay predictable no matter which subset of stages was used. A
    file_name missing from one stage's CSV gets "" for that stage's
    columns. Row order: the union of file_names, first-seen walking
    mask -> segment -> landmark.
    """
    stage_data = []  # [(stage_name, fieldnames, {file_name: row})]
    for stage_name, csv_filename in _STAGE_FILES:
        path = os.path.join(output_folder, csv_filename)
        if not os.path.isfile(path):
            continue
        fieldnames, rows = _read_csv_rows(path)
        rows_by_file_name = {row["file_name"]: row for row in rows}
        stage_data.append((stage_name, fieldnames, rows_by_file_name))

    if not stage_data:
        return None

    shared_columns = list(metadata_columns) + ["object_id"]
    present_shared = [
        col
        for col in shared_columns
        if any(col in fieldnames for _, fieldnames, _ in stage_data)
    ]

    stage_own_columns = {}  # stage_name -> [original column, ...] (order preserved)
    fieldnames = ["file_name"] + present_shared
    for stage_name, stage_fieldnames, _ in stage_data:
        own_columns = [
            col
            for col in stage_fieldnames
            if col != "file_name" and col not in shared_columns
        ]
        stage_own_columns[stage_name] = own_columns
        fieldnames += [f"{stage_name}_{col}" for col in own_columns]

    file_name_order = []
    seen = set()
    for _, _, rows_by_file_name in stage_data:
        for file_name in rows_by_file_name:
            if file_name not in seen:
                seen.add(file_name)
                file_name_order.append(file_name)

    output_path = summary_path_for(output_folder)
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, restval="")
        writer.writeheader()
        for file_name in file_name_order:
            out_row = {"file_name": file_name}

            for col in present_shared:
                value = ""
                for stage_name, stage_fieldnames, rows_by_file_name in stage_data:
                    if col not in stage_fieldnames:
                        continue
                    row = rows_by_file_name.get(file_name)
                    if row is None:
                        continue
                    value = row.get(col, "")
                    break
                out_row[col] = value

            for stage_name, _, rows_by_file_name in stage_data:
                row = rows_by_file_name.get(file_name)
                for col in stage_own_columns[stage_name]:
                    out_row[f"{stage_name}_{col}"] = row.get(col, "") if row is not None else ""

            writer.writerow(out_row)

    return output_path


def summary_path_for(output_folder):
    return os.path.join(output_folder, SUMMARY_FILENAME)
