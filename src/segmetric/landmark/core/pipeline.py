
import csv

from .measurement import landmark_field_names


STATUS_MEASURED = "measured"
STATUS_BLANK = "blank"
STATUS_DAMAGED = "damaged"

BASE_FIELDS = ["file_name", "status"]
SUMMARY_FIELDS = ["n_landmarks", "centroid_size_mm"]

CSV_FILENAME = "landmark_measurements.csv" #change with caution, make sure you do not need to call the file back 


def new_row(file_name):
    return {"file_name": file_name, "status": ""}


def write_csv(
    output_path,
    rows,
    all_labels,
    extra_columns=(),
    include_object_id=False,
):
    """One row in CSV per crop to output_path.

    If data is missing such as if the image was labled 
    blank/damaged, or no landmarks were place, CSV if filled in as "" 
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
