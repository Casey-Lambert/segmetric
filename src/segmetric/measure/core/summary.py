
"""Combins mask/segment/landmark results
in a segmetric.measure output folder into one measure_summary.csv.
"""


import csv
import os

MASK_CSV = "mask_measurements.csv"
SEGMENT_CSV = "segment_measurements.csv"
LANDMARK_CSV = "landmark_measurements.csv"
SUMMARY_FILENAME = "measure_summary.csv"


# Fixed order mask -> segment -> landmark p
# stage-column prefixing/shared-column per-row fallback lookup.

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
    
    """Outer-join by file_name across mask_measurements.csv /
    segment_measurements.csv / landmark_measurements.csv exist directly in
    output_folder. 

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


