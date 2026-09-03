import os
from glob import glob

from .errors import SegMetricError

SUPPORTED_EXTENSIONS = (
    "*.pdf",
    "*.png",
    "*.jpg",
    "*.jpeg",
    "*.tif",
    "*.tiff",
)


def find_input_files(input_folder):
    """Return a sorted list of PDF/PNG/JPG/JPEG/TIFF paths directly inside
    input_folder.

    Raises SegMetricError with a researcher-readable message if the folder is
    missing or contains none of the supported file types.
    """
    if not input_folder or not os.path.isdir(input_folder):
        raise SegMetricError(
            f"The input folder '{input_folder}' does not exist or is not a folder."
        )

    files = sorted(
        path
        for pattern in SUPPORTED_EXTENSIONS
        for path in glob(os.path.join(input_folder, pattern))
    )

    if not files:
        raise SegMetricError(
            f"No PDF, PNG, JPG, or TIFF files were found in '{input_folder}'."
        )

    return files
