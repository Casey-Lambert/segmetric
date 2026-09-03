from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class DetectionSettings:
    """The 8 tunable parameters behind core.detection.segment_cells --
    matches the notebooks' hardcoded segment_cells() constants exactly.
    """

    sato_sigma_min: float = 2.0
    sato_sigma_max: float = 4.0
    local_thresh_block_size: int = 71
    local_thresh_offset: float = -0.02
    vein_close_px: int = 5
    min_vein_size: int = 400
    distance_gaussian_sigma: float = 1.5
    h_maxima_h: float = 6.5


@dataclass
class SegmentPreset:
    """A named, ordered sequence of click-select steps (e.g. ["radial"] or
    ["femur", "tibia"]) plus the detection settings used to segment
    candidate cells before any step's selection happens. One DetectionSettings
    covers every step in the preset -- segment_cells runs once per crop,
    each step just selects different labeled regions from the same result.
    """

    name: str = "Custom"
    steps: List[str] = field(default_factory=lambda: ["cell"])
    detection: DetectionSettings = field(default_factory=DetectionSettings)


# The two reference-notebook workflows, as starting templates in one general
# system -- both use the notebooks' identical segment_cells() constants;
# only the step sequence differs. "Forewing Cell" ships with one placeholder
# step ("cell") for you to rename (e.g. to "radial"); "Leg Segments" ships
# with its own two named steps as-is, though those are renamable too.
DEFAULT_PRESETS = {
    "Forewing Cell": SegmentPreset(
        name="Forewing Cell", steps=["cell"], detection=DetectionSettings()
    ),
    "Leg Segments": SegmentPreset(
        name="Leg Segments", steps=["femur", "tibia"], detection=DetectionSettings()
    ),
}

# A starting point for "create a new preset from scratch" (mirrors
# segmetric.mask's BLANK_FILTER) -- detection settings stay at the tuned
# notebook defaults (zeroing them would just break skimage's calls), only
# the step list is a blank placeholder for the user to define.
BLANK_PRESET = SegmentPreset(
    name="New Preset", steps=["step_1"], detection=DetectionSettings()
)


@dataclass
class PresetGroup:
    """A mixed-batch object-id -> preset assignment: one SegmentPreset
    applies to every id in `object_ids`.
    """

    object_ids: List[str] = field(default_factory=list)  # no leading '_'
    preset: Optional[SegmentPreset] = None
