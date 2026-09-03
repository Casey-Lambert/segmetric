from PyQt6.QtCore import QThread, pyqtSignal

from segmetric.errors import SegMetricError
from segmetric.scale.core.model import ScaleSettings
from segmetric.set.core.model import Preset
from segmetric.tag.core.naming import DEFAULT_OUTPUT_FORMAT, OcrRegion

from ..core.pipeline import run_prepare_job


class PrepareJobWorker(QThread):
    """Runs the combined tag -> scale -> summary job off the GUI thread."""

    progress = pyqtSignal(float, str)
    error = pyqtSignal(str)
    finished_ok = pyqtSignal(object)  # PrepareJobResult

    def __init__(
        self,
        input_folder,
        output_folder,
        rows,
        cols,
        use_cv_naming,
        ocr_region: OcrRegion,
        gpu,
        output_format,
        scale_settings: ScaleSettings,
        preset: Preset = None,
        crop_output_format=DEFAULT_OUTPUT_FORMAT,
    ):
        super().__init__()
        self.input_folder = input_folder
        self.output_folder = output_folder
        self.rows = rows
        self.cols = cols
        self.use_cv_naming = use_cv_naming
        self.ocr_region = ocr_region
        self.gpu = gpu
        self.output_format = output_format
        self.scale_settings = scale_settings
        self.preset = preset
        self.crop_output_format = crop_output_format

    def run(self):
        try:
            result = run_prepare_job(
                self.input_folder,
                self.output_folder,
                self.rows,
                self.cols,
                self.use_cv_naming,
                ocr_region=self.ocr_region,
                gpu=self.gpu,
                output_format=self.output_format,
                scale_settings=self.scale_settings,
                preset=self.preset,
                progress_cb=lambda frac, msg: self.progress.emit(frac, msg),
                should_stop=self.isInterruptionRequested,
                crop_output_format=self.crop_output_format,
            )
            self.finished_ok.emit(result)
        except SegMetricError as exc:
            self.error.emit(str(exc))
        except Exception:
            self.error.emit(
                "An unexpected error occurred. See the per-stage log files "
                "(segmetric_tag / segmetric_scale) in the output folder for details."
            )
