

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class DetectionSettings:

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
    name: str = "Custom"
    steps: List[str] = field(default_factory=lambda: ["cell"])
    detection: DetectionSettings = field(default_factory=DetectionSettings)


DEFAULT_PRESETS = {
    "Forewing Cell": SegmentPreset(
        name="Forewing Cell", steps=["cell"], detection=DetectionSettings()
    ),
    "Leg Segments": SegmentPreset(
        name="Leg Segments", steps=["femur", "tibia"], detection=DetectionSettings()
    ),
}


BLANK_PRESET = SegmentPreset(
    name="New Preset", steps=["step_1"], detection=DetectionSettings()
)


@dataclass
class PresetGroup:
    """A mixed-batch object-id -> preset assignment"""

    object_ids: List[str] = field(default_factory=list)  # no leading '_'
    preset: Optional[SegmentPreset] = None



#