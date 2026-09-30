

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class FilterSettings:
    """The 7 tunable parameters behind core.masking.generate_mask.
    """

    first_pass_factor: float
    normal_thresh: float
    vein_thresh: float
    erode_px: int
    close_px: int
    fourier_freq: float
    min_blob: int
    name: str = ""


# Selectable as-is or as starting point to customize to whatever is being processed 

DEFAULT_FILTERS = {
    "Forewing": FilterSettings(
        first_pass_factor=0.40,
        normal_thresh=0.60,
        vein_thresh=0.18,
        erode_px=8,
        close_px=60,
        fourier_freq=0.01,
        min_blob=500,
        name="Forewing",
    ),
    "Hindwing": FilterSettings(
        first_pass_factor=0.30,
        normal_thresh=0.60,
        vein_thresh=0.12,
        erode_px=8,
        close_px=40,
        fourier_freq=0.01,
        min_blob=200,
        name="Hindwing",
    ),
    "Leg": FilterSettings(
        first_pass_factor=0.25,
        normal_thresh=0.40,
        vein_thresh=0.15,
        erode_px=8,
        close_px=20,
        fourier_freq=0.02,
        min_blob=50,
        name="Leg",
    ),
}


@dataclass
class FilterGroup:
    """A mixed-anatomy object-id -> filter assignment: one filter applies
    to every id in `object_ids`
    """

    object_ids: list = field(default_factory=list)  # list[str], ensures no leading '_'
    filter: Optional[FilterSettings] = None


# A zeroed starting point for "create a new filter from scratch" 
# Not a usable masking configuration on its own, flagged placeholder to change before running.
BLANK_FILTER = FilterSettings(
    first_pass_factor=0.0,
    normal_thresh=0.0,
    vein_thresh=0.0,
    erode_px=0,
    close_px=0,
    fourier_freq=0.0,
    min_blob=0,
    name="Blank",
)


