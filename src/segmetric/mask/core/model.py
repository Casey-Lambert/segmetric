from dataclasses import dataclass, field
from typing import Optional


@dataclass
class FilterSettings:
    """The 7 tunable parameters behind core.masking.generate_mask -- matches
    the notebook's WING_PARAMS dict exactly (per-anatomy masking presets).

    `name` is a display-only label (e.g. "Forewing", "Custom: femur_v2") --
    it plays no part in generate_mask's math, but round-trips through
    save/load so the "filter used" output column (§7) can report something
    meaningful instead of a raw parameter dump.
    """

    first_pass_factor: float
    normal_thresh: float
    vein_thresh: float
    erode_px: int
    close_px: int
    fourier_freq: float
    min_blob: int
    name: str = ""


# The notebook's WING_PARAMS values, unaltered. Selectable as-is or as a
# starting point to customize (segmetric.mask GUI's filter picker, options 1/2).
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
    to every id in `object_ids` (e.g. object_ids=["AA", "AB"] sharing one
    filter).
    """

    object_ids: list = field(default_factory=list)  # list[str], no leading '_'
    filter: Optional[FilterSettings] = None


# A zeroed starting point for "create a new filter from scratch" (§3 item 4).
# Not a usable masking configuration on its own -- the GUI flags it as a
# placeholder to tune before running.
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
