from PyQt6.QtCore import QThread, pyqtSignal

from segmetric.errors import SegMetricError
from segmetric.tag.core.naming import DEFAULT_OUTPUT_FORMAT

from ..core.model import ScaleSettings
from ..core.pipeline import run_manual_scale_job, run_scale_job


class ScaleJobWorker(QThread):
    """Runs the full scale + crop job off the GUI thread."""

    progress = pyqtSignal(float, str)
    error = pyqtSignal(str)
    finished_ok = pyqtSignal(object)  # ScaleJobResult

    def __init__(
        self,
        input_folder,
        output_folder,
        settings: ScaleSettings,
        output_format=DEFAULT_OUTPUT_FORMAT,
    ):
        super().__init__()
        self.input_folder = input_folder
        self.output_folder = output_folder
        self.settings = settings
        self.output_format = output_format

    def run(self):
        try:
            result = run_scale_job(
                self.input_folder,
                self.output_folder,
                settings=self.settings,
                progress_cb=lambda frac, msg: self.progress.emit(frac, msg),
                should_stop=self.isInterruptionRequested,
                output_format=self.output_format,
            )
            self.finished_ok.emit(result)
        except SegMetricError as exc:
            self.error.emit(str(exc))
        except Exception:
            self.error.emit(
                "An unexpected error occurred. See segmetric_scale.log in the "
                "output folder for details."
            )


class ManualScaleJobWorker(QThread):
    """Runs the no-markers manual scale/crop job off the GUI thread. Same
    signal shape as ScaleJobWorker, calling run_manual_scale_job instead.
    """

    progress = pyqtSignal(float, str)
    error = pyqtSignal(str)
    finished_ok = pyqtSignal(object)  # ScaleJobResult

    def __init__(
        self,
        input_folder,
        output_folder,
        scale_by_name,
        scale_source_by_name,
        crop_bbox_by_name,
        output_format=DEFAULT_OUTPUT_FORMAT,
    ):
        super().__init__()
        self.input_folder = input_folder
        self.output_folder = output_folder
        self.scale_by_name = scale_by_name
        self.scale_source_by_name = scale_source_by_name
        self.crop_bbox_by_name = crop_bbox_by_name
        self.output_format = output_format

    def run(self):
        try:
            result = run_manual_scale_job(
                self.input_folder,
                self.output_folder,
                self.scale_by_name,
                self.scale_source_by_name,
                self.crop_bbox_by_name,
                progress_cb=lambda frac, msg: self.progress.emit(frac, msg),
                should_stop=self.isInterruptionRequested,
                output_format=self.output_format,
            )
            self.finished_ok.emit(result)
        except SegMetricError as exc:
            self.error.emit(str(exc))
        except Exception:
            self.error.emit("An unexpected error occurred while running the manual scale job.")
