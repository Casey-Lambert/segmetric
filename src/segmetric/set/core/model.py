from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Segment:
    """One underscore-separated token from a filename, as shown/edited in the
    preset builder. raw_value is a live-preview convenience only -- it is
    never written into a saved Preset.
    """

    index: int
    raw_value: str
    column_name: str
    include: bool = True


@dataclass
class Preset:
    """A saved, position-keyed mapping from filename segments to CSV columns."""

    name: str
    segments: list = field(default_factory=list)  # list[Segment]
    object_id_column: Optional[str] = None
