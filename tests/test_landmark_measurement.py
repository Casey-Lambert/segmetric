import pytest

from segmetric.landmark.core.measurement import (
    centroid_size,
    landmark_field_names,
    landmark_row_fields,
)


def test_centroid_size_of_a_square():
    # A unit square centered on the origin -- each corner is sqrt(0.5) from
    # the centroid (squared distance 0.5), so centroid size (the root of
    # the *sum* of squared deviations, across all 4 corners) = sqrt(2).
    points = [(-0.5, -0.5), (0.5, -0.5), (0.5, 0.5), (-0.5, 0.5)]
    assert centroid_size(points) == pytest.approx(2 ** 0.5, abs=1e-6)


def test_centroid_size_zero_for_coincident_points():
    points = [(3.0, 4.0), (3.0, 4.0), (3.0, 4.0)]
    assert centroid_size(points) == pytest.approx(0.0)


def test_landmark_field_names():
    assert landmark_field_names("lm_01") == [
        "lm_01_x_px", "lm_01_y_px", "lm_01_x_mm", "lm_01_y_mm",
    ]


def test_landmark_row_fields_only_placed_labels_and_scales_mm():
    points_px = {"lm_01": (10.0, 20.0), "lm_02": (30.0, 20.0)}
    labels = ["lm_01", "lm_02", "lm_03"]

    fields = landmark_row_fields(points_px, labels, mm_per_pixel=0.5)

    assert fields["lm_01_x_px"] == 10.0
    assert fields["lm_01_y_px"] == 20.0
    assert fields["lm_01_x_mm"] == 5.0
    assert fields["lm_01_y_mm"] == 10.0
    assert "lm_03_x_px" not in fields  # unplaced -- omitted, not zeroed
    assert fields["n_landmarks"] == 2
    # Points at (5,10)mm and (15,10)mm, centroid (10,10)mm: each is 5mm
    # from the centroid (squared deviation 25), so centroid size = sqrt(50).
    # (landmark_row_fields rounds to 4 decimals, hence the looser tolerance.)
    assert fields["centroid_size_mm"] == pytest.approx(50 ** 0.5, abs=1e-4)


def test_landmark_row_fields_fewer_than_two_points_has_zero_centroid_size():
    fields = landmark_row_fields({"lm_01": (1.0, 1.0)}, ["lm_01", "lm_02"], mm_per_pixel=1.0)
    assert fields["n_landmarks"] == 1
    assert fields["centroid_size_mm"] == 0.0

    fields = landmark_row_fields({}, ["lm_01"], mm_per_pixel=1.0)
    assert fields["n_landmarks"] == 0
    assert fields["centroid_size_mm"] == 0.0
