from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from segmetric.errors import SegMetricError
from segmetric.prepare.core.metadata import apply_preset_to_filename

from ..core.matching import match_crops
from .review_window import ReviewWindow
from .setup_window import SetupPage

PAGE_SETUP = 0
PAGE_OUTPUT = 1
PAGE_REVIEW = 2


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SegMetric.Landmark — Geometric-Morphometric Landmarking")
        self.resize(1150, 860)

        self.matched_crops = []
        self.output_folder = None

        self._build_ui()
        self._update_nav_state()

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        central = QWidget()
        outer = QVBoxLayout(central)

        self.stack = QStackedWidget()

        self.setup_page = SetupPage()
        self.setup_page.ready_changed.connect(self._update_nav_state)
        self.stack.addWidget(self.setup_page)

        self.output_page = self._build_output_page()
        self.stack.addWidget(self.output_page)

        self.review_window = ReviewWindow()
        self.review_window.finished.connect(self._on_review_finished)
        self.stack.addWidget(self.review_window)

        outer.addWidget(self.stack, stretch=1)

        nav_row = QHBoxLayout()
        self.back_btn = QPushButton("← Back")
        self.back_btn.clicked.connect(self.on_back)
        self.next_btn = QPushButton("Next →")
        self.next_btn.clicked.connect(self.on_next)
        nav_row.addWidget(self.back_btn)
        nav_row.addStretch(1)
        nav_row.addWidget(self.next_btn)
        outer.addLayout(nav_row)

        self.setCentralWidget(central)

    def _build_output_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        output_row = QHBoxLayout()
        output_row.addWidget(QLabel("Output folder:"))
        self.output_line = QLineEdit()
        self.output_line.setReadOnly(True)
        output_row.addWidget(self.output_line)
        output_browse = QPushButton("Browse…")
        output_browse.clicked.connect(self.on_browse_output)
        output_row.addWidget(output_browse)
        layout.addLayout(output_row)

        output_hint = QLabel("Measurements → <output>/landmark_measurements.csv")
        output_hint.setStyleSheet("color: gray;")
        layout.addWidget(output_hint)

        self.summary_label = QLabel("")
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)

        self.begin_review_btn = QPushButton("Begin Review →")
        self.begin_review_btn.setMinimumHeight(36)
        self.begin_review_btn.clicked.connect(self.on_begin_review)
        layout.addWidget(self.begin_review_btn)

        layout.addStretch(1)
        return page

    # ------------------------------------------------------------- logging
    def _show_error(self, message):
        QMessageBox.critical(self, "SegMetric.Landmark — Error", message)

    # --------------------------------------------------------- navigation
    def _update_nav_state(self, *_args):
        idx = self.stack.currentIndex()
        self.back_btn.setVisible(idx not in (PAGE_SETUP, PAGE_REVIEW))
        self.next_btn.setVisible(idx == PAGE_SETUP)
        if idx == PAGE_SETUP:
            self.next_btn.setEnabled(self.setup_page.is_ready())

    def on_next(self):
        idx = self.stack.currentIndex()
        if idx == PAGE_SETUP:
            if not self._begin_matching():
                return
            self._update_output_summary()
            self.stack.setCurrentIndex(PAGE_OUTPUT)
        self._update_nav_state()

    def on_back(self):
        idx = self.stack.currentIndex()
        if idx == PAGE_OUTPUT:
            self.stack.setCurrentIndex(PAGE_SETUP)
        self._update_nav_state()

    # ----------------------------------------------------------- matching
    def _begin_matching(self):
        try:
            matched, unmatched, no_mask = match_crops(
                self.setup_page.crops_folder,
                self.setup_page.scales_file,
                self.setup_page.masks_folder,
                exclude_blank_tagged=self.setup_page.remove_blank_checkbox.isChecked(),
            )
        except SegMetricError as exc:
            self._show_error(str(exc))
            return False

        selected_object_ids = self.setup_page.selected_object_ids()
        if selected_object_ids is not None:
            preset = self.setup_page.metadata_preset
            matched = [
                item
                for item in matched
                if apply_preset_to_filename(item.original_stem, preset).get(
                    preset.object_id_column
                )
                in selected_object_ids
            ]

        self.matched_crops = matched

        if not matched:
            self._show_error("No crops matched a scale row -- nothing to process.")
            return False

        if unmatched:
            preview = "\n".join(unmatched[:10])
            more = f"\n… and {len(unmatched) - 10} more" if len(unmatched) > 10 else ""
            QMessageBox.warning(
                self,
                "SegMetric.Landmark",
                f"{len(unmatched)} crop(s) had no matching scale row and will "
                f"be excluded:\n{preview}{more}",
            )
        if no_mask:
            QMessageBox.warning(
                self,
                "SegMetric.Landmark",
                f"{len(no_mask)} matched crop(s) have no usable mask -- "
                "no dimming reference will be shown for those.",
            )
        return True

    def _update_output_summary(self):
        self.summary_label.setText(f"{len(self.matched_crops)} crop(s) ready to review.")

    # -------------------------------------------------------------- output
    def on_browse_output(self):
        folder = QFileDialog.getExistingDirectory(self, "Select output folder")
        if not folder:
            return
        self.output_folder = folder
        self.output_line.setText(folder)

    def on_begin_review(self):
        if not self.output_folder:
            QMessageBox.warning(self, "SegMetric.Landmark", "Choose an output folder first.")
            return

        self.review_window.start(
            self.matched_crops, self.setup_page.metadata_preset, self.output_folder
        )
        self.stack.setCurrentIndex(PAGE_REVIEW)
        self._update_nav_state()

    def _on_review_finished(self):
        QMessageBox.information(
            self,
            "SegMetric.Landmark",
            f"Saved. CSV: {self.review_window.csv_path}",
        )
        self.stack.setCurrentIndex(PAGE_OUTPUT)
        self._update_nav_state()
