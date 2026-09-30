
from PyQt6.QtCore import QThread, pyqtSignal

from ..core.errors import SegMetricError
from ..core.naming import DEFAULT_OUTPUT_FORMAT, OcrRegion
from ..core.pipeline import run_panel_split_job



class SplitJobWorker(QThread):
    """Runs the full panel-split job off the GUI thread."""

    progress = pyqtSignal(float, str)
    error = pyqtSignal(str)
    finished_ok = pyqtSignal(object)  # JobResult

    def __init__(
        self,
        input_folder,
        output_folder,
        rows,
        cols,
        use_cv_naming,
        ocr_region: OcrRegion = OcrRegion(),
        gpu=True,
        output_format=DEFAULT_OUTPUT_FORMAT,
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


    def run(self):
        try:
            result = run_panel_split_job(
                self.input_folder,
                self.output_folder,
                self.rows,
                self.cols,
                self.use_cv_naming,
                progress_cb=lambda frac, msg: self.progress.emit(frac, msg),
                gpu=self.gpu,
                ocr_region=self.ocr_region,
                should_stop=self.isInterruptionRequested,
                output_format=self.output_format,
            )
            self.finished_ok.emit(result)
        except SegMetricError as exc:
            self.error.emit(str(exc))
        except Exception:
            self.error.emit(
                "An unexpected error occurred. See segmetric_tag.log in the output "
                "folder for details."
            )




