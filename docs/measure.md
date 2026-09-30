---
layout: page
title: segmetric.measure
permalink: /measure.html
---

# segmetric.measure

A convenience shell similar to `segmetric.prepare`, consolidating
`mask`, `segment`, and `landmark`. Load in scale, crops, an optional
metadata preset, and then set an output folder. Then tab through the
measurement types, selecting the combination of tools you want to run.
Load in or create the various .JSON presets.

Runs will always progress in the order Mask → Segment → Landmark. If
Mask is run, downstream processes automatically pick up and apply the
results. All processes work identically to the `mask`, `segment`, and
`landmark` standalone processes.

Output: each enabled stage's usual files, plus one `measure_summary.csv`
outer-joining `mask_measurements.csv` / `segment_measurements.csv` /
`landmark_measurements.csv`, by file name.

## Run it

```bash
segmetric-measure
```

[← Back to all tools](index.html)
