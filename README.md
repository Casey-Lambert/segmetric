# SegMetric

Tools for turning scanned insect wing/leg panel scans into measurements.

- **`segmetric.tag`** — splits scanned PDFs, PNGs, JPEGs, or TIFFs into
  individually named panel images (saved as TIFF by default, PNG or JPEG
  optional).
- **`segmetric.set`** — builds and saves reusable presets that map the
  underscore-separated tokens in a panel's filename (e.g.
  `H6_120HR_34C_NR_1004_RH`) to named CSV columns, with one column flagged
  as the reference "object id." No example file is required — a sample
  name can be typed in by hand instead of browsing to a real folder.
- **`segmetric.scale`** — detects ArUco markers to compute a real-world
  scale (mm/pixel) for each image, crops each to the marker region, and
  saves both the cropped images and a `scales.csv` (file name, mm/pixel,
  and whether that value was directly measured or filled in from the
  batch median because too few markers were found). How the crop relates
  to the detected markers is tunable — vertical/horizontal size as a
  percentage of the marker bounding box, anchored from either edge or
  centered (defaults reproduce the original fixed "middle 50% height,
  full width" trim) — the same anchor+percentage pattern
  `segmetric.tag`'s OCR search region uses, with a live preview showing
  the resulting crop box on the current image. **No markers present**
  is a separate, explicitly-opted-into mode for image sets with no ArUco
  markers at all: an ImageJ-style tool lets you click two points and enter
  the known distance between them to set `mm_per_pixel` by hand (applied
  either once to the whole batch or individually per image), and a
  click-drag rectangle tool sets the crop region the same two ways, or
  skips cropping entirely. Output lands in the same `scales.csv`/
  `*_cropped.<ext>` shape either way, so `segmetric.mask`/`segment`/
  `landmark` read it unchanged. Not available through `segmetric.prepare` —
  a no-markers batch runs `tag`, this, then `mask`/`segment`/`landmark` as
  separate steps.
- **`segmetric.prepare`** — combines the three tools above into one
  streamlined run: one input folder, one output folder, one Run button.
  Internally calls `tag`'s and `scale`'s pipelines back to back (`tag`'s
  `panels/` output feeds straight into `scale`), and optionally applies a
  `set` preset to each panel's own filename to add metadata columns to a
  combined `summary.csv`. Doesn't change how `tag`, `set`, or `scale` work
  standalone — it's an additional, convenience entry point that calls their
  existing pipelines as a library.
- **`segmetric.mask`** — takes the cropped images + scale CSV from
  `segmetric.scale`/`segmetric.prepare` and, per object, generates a binary
  mask, measures its axis-corrected length and width, and lets you manually
  repaint the mask (ADD/REMOVE brush) when auto-detection gets it wrong.
  Masking uses a 7-parameter "filter" per anatomy type (three defaults
  ship built-in: Forewing, Hindwing, Leg), savable/loadable as JSON
  presets. Single-type batches use one filter for the whole run;
  mixed-anatomy batches assign a filter per object id (read from an
  optionally-loaded `segmetric.set` preset's flagged object-id column),
  with the id-to-filter mapping itself savable as a reusable template.
  Output: `<output>/masks/*.png` plus one `mask_measurements.csv` row per
  object.
- **`segmetric.segment`** — the click-select follow-up to `segmetric.mask`:
  detects candidate cell regions inside a crop (a vein-ridge filter +
  watershed, constrained to a `segmetric.mask` wing mask when one's
  available), then walks you through clicking the regions that form a
  target anatomical structure ("Forewing Cell" — a single step you name,
  e.g. "radial" — or "Leg Segments" — femur then tibia), correcting the
  result by brush, and measuring it. Detection thresholds and the step
  sequence are both tunable, savable/loadable as JSON presets; mixed
  batches assign a preset per object id the same way `segmetric.mask`
  does. Masks tagged `_blank` by `segmetric.mask` are excluded by default
  (toggle-able); `_damage`-tagged ones are used as-is. Output:
  `<output>/segment_masks/*.png` plus one `segment_measurements.csv` row
  per crop, with per-step columns (`<step>_bbox_w_mm`, etc.) and a
  Blank/Damaged status flag.
- **`segmetric.landmark`** — geometric-morphometric landmarking: click
  anywhere on a crop to place a landmark (it defaults to the next plain
  number -- "1", "2", "3", ...), double-click any placed landmark to
  rename it, drag to adjust, zoom/pan while you work. Fully freeform --
  any number of landmarks, in any order, no preset or pre-typed name list
  needed. An optional `segmetric.mask` mask is shown as a dimmed-outside-
  mask reference only, never a constraint on where you can click. Output:
  one `landmark_measurements.csv` row per crop, with each landmark's pixel
  and mm coordinates (columns named after whatever you clicked/renamed
  them to), a placed-count, centroid size (mm), and a Blank/Damaged status
  flag.
- **`segmetric.measure`** — a shared shell over `mask`, `segment`, and
  `landmark`: one Scales file / Crops folder / Output folder and one
  optionally-loaded `set` preset, entered once, with a tab per measurement
  type (each with its own checkbox — run any subset, not necessarily all
  three). Unlike `segmetric.prepare`, this can't be one fully unattended
  Run button: `mask` is a real background batch job, but `segment` and
  `landmark` have no batch mode at all — their entire purpose is a human
  clicking which regions form a structure, or placing landmark points,
  crop by crop. Run validates everything up front, then walks whichever
  stages are enabled in a fixed Mask → Segment → Landmark order, each
  handing off to that tool's own existing interface (Mask's results table
  with optional correction; Segment's and Landmark's normal interactive
  review) embedded directly in the same window. If Mask is enabled
  alongside Segment/Landmark, its output masks are picked up automatically
  by the later stages — no need to browse to them again. Output: each
  enabled stage's usual files, plus one `measure_summary.csv` outer-joining
  whichever of `mask_measurements.csv` / `segment_measurements.csv` /
  `landmark_measurements.csv` exist, by file name, with every column
  besides `file_name`/`object_id`/preset-metadata prefixed by stage
  (`mask_length_mm`, `segment_status`, `landmark_status`, …) so nothing
  collides. Doesn't change how `mask`, `segment`, or `landmark` work
  standalone.

## Install (conda)

```bash
conda env create -f environment.yml
conda activate segmetric
```

This installs SegMetric itself in editable mode via the `pip:` section of
`environment.yml`. If you already have a `segmetric` environment and just
pulled new code, re-run:

```bash
conda activate segmetric
pip install -e .
```

## Run

```bash
segmetric-tag       # panel splitter
segmetric-set       # filename preset builder
segmetric-scale     # ArUco scale + crop
segmetric-prepare   # combined tag + set + scale
segmetric-mask      # mask generation, measurement & manual correction
segmetric-segment   # cell detection, click-select & measurement
segmetric-landmark  # geometric-morphometric landmarking
segmetric-measure   # combined mask + segment + landmark shell
```

(equivalently: `python -m segmetric.tag` / `python -m segmetric.set` /
`python -m segmetric.scale` / `python -m segmetric.prepare` /
`python -m segmetric.mask` / `python -m segmetric.segment` /
`python -m segmetric.landmark` / `python -m segmetric.measure`)

## Development

```bash
pip install -e ".[dev]"
pytest
```

## Project layout

- `src/segmetric/errors.py` — `SegMetricError`, shared across every
  SegMetric tool.
- `src/segmetric/tag/core/`, `src/segmetric/set/core/`,
  `src/segmetric/scale/core/`, `src/segmetric/prepare/core/`,
  `src/segmetric/mask/core/`, `src/segmetric/segment/core/`,
  `src/segmetric/landmark/core/`, `src/segmetric/measure/core/` —
  processing logic only, no PyQt imports. Each can be imported and tested
  standalone, or reused in a non-GUI script. `prepare/core/pipeline.py`
  calls `tag`'s and `scale`'s `run_*_job` functions directly rather than
  reimplementing them; `mask/core/pipeline.py`, `segment/core/pipeline.py`,
  and `landmark/core/pipeline.py` all call `prepare/core/metadata.py`'s
  `apply_preset_to_filename` for their own metadata/object-id handling;
  `segment/core/matching.py` calls `mask/core/tagging.py`'s
  `find_tagged_mask` to locate a crop's mask regardless of what tag (if
  any) `segmetric.mask` gave it, and `landmark/core/matching.py` reuses
  `segment/core/matching.py`'s `match_crops` directly rather than
  duplicating it. `measure/core/pipeline.py` calls `mask`'s and
  `segment`'s matching functions directly (no reimplementation) and has
  no `run_measure_job` — unlike `prepare`, mask/segment/landmark can't be
  chained by one top-to-bottom function, since segment/landmark are
  interactive with no batch entry point at all; `measure/core/summary.py`
  does a real multi-CSV outer join (unlike `prepare/core/summary.py`,
  which has only one real CSV to begin with).
- `src/segmetric/tag/gui/`, `src/segmetric/set/gui/`,
  `src/segmetric/scale/gui/`, `src/segmetric/prepare/gui/`,
  `src/segmetric/mask/gui/`, `src/segmetric/segment/gui/`,
  `src/segmetric/landmark/gui/`, `src/segmetric/measure/gui/` — the PyQt6
  desktop apps. Each imports its own `core`, never the reverse.
  `measure/gui/main_window.py` embeds `segment`'s and `landmark`'s own
  `ReviewWindow` widgets directly (the same widgets those tools' own
  standalone `MainWindow`s already embed) rather than reimplementing the
  interactive review; `measure/gui/mask_stage_page.py` reuses `mask`'s
  `MaskJobWorker`/`CorrectionDialog`/`ReviewDialog` the same way.

Future SegMetric steps are expected to land as further sibling subpackages
under `segmetric/`, alongside `tag/`, `set/`, `scale/`, `prepare/`,
`mask/`, `segment/`, `landmark/`, and `measure/`.
