import csv

from .measurement import landmark_field_names

STATUS_MEASURED = "measured"
STATUS_BLANK = "blank"
STATUS_DAMAGED = "damaged"

BASE_FIELDS = ["file_name", "status"]
SUMMARY_FIELDS = ["n_landmarks", "centroid_size_mm"]

CSV_FILENAME = "landmark_measurements.csv"


def new_row(file_name):
    return {"file_name": file_name, "status": ""}


def write_csv(
    output_path,
    rows,
    all_labels,
    extra_columns=(),
    include_object_id=False,
):
    """Write rows (list of dicts, one per crop -- see new_row/
    landmark_row_fields) to output_path.

    Placement is freeform (see gui/review_window.py's _LandmarkCanvas), so
    all_labels is whatever union of labels the batch's crops actually ended
    up using -- not a fixed preset list.

    Column order: file_name, status, then every label's 4 columns (in
    all_labels' order -- pass the union of every label actually used across
    the batch), then n_landmarks, centroid_size_mm, then extra metadata
    columns, then object_id if requested. A row missing a column (a crop
    that's blank/damaged, or a label that crop never placed) is written
    as "".
    """
    fieldnames = list(BASE_FIELDS)
    for label in all_labels:
        fieldnames.extend(landmark_field_names(label))
    fieldnames.extend(SUMMARY_FIELDS)
    fieldnames.extend(extra_columns)
    if include_object_id:
        fieldnames.append("object_id")

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, restval="")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return output_path
