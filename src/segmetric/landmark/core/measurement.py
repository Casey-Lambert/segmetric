
import math


def centroid_size(points_mm):
    """Root-sum-of-squared deviations from centroid. centroid_size(). Not used 
    for fewer than 2 points detected.
    """
    n = len(points_mm)
    cx = sum(p[0] for p in points_mm) / n
    cy = sum(p[1] for p in points_mm) / n
    return math.sqrt(sum((x - cx) ** 2 + (y - cy) ** 2 for x, y in points_mm))




def landmark_field_names(label):
    return [f"{label}_x_px", f"{label}_y_px", f"{label}_x_mm", f"{label}_y_mm"]


def landmark_row_fields(points_px, labels, mm_per_pixel):
    """points_px: dict[label -> (x, y) | absent-if-unplaced]. Returns a
    dict with "{label}_x_px/_y_px/_x_mm/_y_mm" for every label detected, "" for missing info in CSV
    "n_landmarks" for number of landmarks the user placed on the image
    "centroid_size_mm" defults to 0.0 if fewer than 2 points are placed and centriod cannot be calculated
    """
    fields = {}
    placed_mm = []
    n_placed = 0
    for label in labels:
        pt = points_px.get(label)
        if pt is None:
            continue
        x_px, y_px = pt
        x_mm, y_mm = x_px * mm_per_pixel, y_px * mm_per_pixel
        fields[f"{label}_x_px"] = round(x_px, 2)
        fields[f"{label}_y_px"] = round(y_px, 2)
        fields[f"{label}_x_mm"] = round(x_mm, 4)
        fields[f"{label}_y_mm"] = round(y_mm, 4)
        placed_mm.append((x_mm, y_mm))
        n_placed += 1

    fields["n_landmarks"] = n_placed
    fields["centroid_size_mm"] = round(centroid_size(placed_mm), 4) if n_placed >= 2 else 0.0
    return fields


