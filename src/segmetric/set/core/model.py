from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Segment:
    """ _  (underscore) seperated parts of the file name. Spaces are autoconverted to _ by CV dectection
    """

    index: int
    raw_value: str
    column_name: str
    include: bool = True


@dataclass
class Preset:
    """position-keyed map from filename converting to CSV columns."""

    name: str
    segments: list = field(default_factory=list)  # list[Segment]
    object_id_column: Optional[str] = None
