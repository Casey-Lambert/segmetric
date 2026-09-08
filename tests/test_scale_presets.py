import os

import pytest

from segmetric.errors import SegMetricError
from segmetric.scale.core.model import ScaleSettings
from segmetric.scale.core.presets import load_scale_preset, save_scale_preset


def test_save_and_load_round_trip(tmp_path):
    settings = ScaleSettings(
        marker_spacing_mm=25.5,
        adaptive_thresh_constant=9,
        adaptive_thresh_win_size_min=5,
        adaptive_thresh_win_size_max=61,
        adaptive_thresh_win_size_step=8,
        prepare_win_size_max=251,
        prepare_win_size_step=15,
        prepare_error_correction_rate=0.8,
        prepare_perspective_remove_pixel_per_cell=8,
        use_blob_fallback=False,
        blob_min_aspect=0.6,
        blob_max_aspect=1.6,
        prepare_blob_min_area=30000,
        prepare_blob_max_area=140000,
        final_blob_min_area=140000,
        final_blob_max_area=500000,
        crop_v_anchor="top",
        crop_v_size_pct=30,
        crop_h_anchor="right",
        crop_h_size_pct=70,
    )
    path = os.path.join(tmp_path, "preset.json")

    save_scale_preset(path, settings)
    loaded = load_scale_preset(path)

    assert loaded == settings


def test_use_blob_fallback_round_trips(tmp_path):
    path = os.path.join(tmp_path, "preset.json")
    save_scale_preset(path, ScaleSettings(use_blob_fallback=False))
    assert load_scale_preset(path).use_blob_fallback is False


def test_group_size_round_trips(tmp_path):
    path = os.path.join(tmp_path, "preset.json")
    save_scale_preset(path, ScaleSettings(group_size=16))
    assert load_scale_preset(path).group_size == 16

    save_scale_preset(path, ScaleSettings())
    assert load_scale_preset(path).group_size == 0


def test_load_missing_fields_falls_back_to_defaults(tmp_path):
    path = os.path.join(tmp_path, "partial.json")
    with open(path, "w") as f:
        f.write('{"marker_spacing_mm": 15.0}')

    loaded = load_scale_preset(path)

    defaults = ScaleSettings()
    assert loaded.marker_spacing_mm == 15.0
    assert loaded.adaptive_thresh_constant == defaults.adaptive_thresh_constant
    assert loaded.adaptive_thresh_win_size_max == defaults.adaptive_thresh_win_size_max
    assert loaded.use_blob_fallback == defaults.use_blob_fallback
    assert loaded.prepare_win_size_max == defaults.prepare_win_size_max
    assert loaded.blob_min_aspect == defaults.blob_min_aspect
    assert loaded.prepare_blob_min_area == defaults.prepare_blob_min_area
    assert loaded.final_blob_max_area == defaults.final_blob_max_area
    assert loaded.crop_v_anchor == defaults.crop_v_anchor
    assert loaded.crop_v_size_pct == defaults.crop_v_size_pct
    assert loaded.crop_h_anchor == defaults.crop_h_anchor
    assert loaded.crop_h_size_pct == defaults.crop_h_size_pct
    assert loaded.group_size == defaults.group_size


def test_load_missing_file_raises_segmetric_error(tmp_path):
    with pytest.raises(SegMetricError):
        load_scale_preset(os.path.join(tmp_path, "does_not_exist.json"))


def test_load_invalid_json_raises_segmetric_error(tmp_path):
    path = os.path.join(tmp_path, "bad.json")
    with open(path, "w") as f:
        f.write("{not valid json")
    with pytest.raises(SegMetricError):
        load_scale_preset(path)
