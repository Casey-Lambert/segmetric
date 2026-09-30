---
layout: page
title: segmetric.landmark
permalink: /landmark.html
---

# segmetric.landmark

Load in image scale, and complete classic geometric landmarking, ready
to translate into morphometric analysis. Click anywhere on a crop to
place a landmark and double-click on any landmark to rename it. Drag to
adjust the landmark, scroll to zoom and drag to pan the image. An
optional integration with a `segmetric.mask` mask will load the dimmed
out mask as a reference but does not constrain where you click.

Output saved to `landmark_measurements.csv`, one row per crop, with each
landmark's pixel and mm coordinates, along with number of landmarks
placed, centroid size in mm, and any carried-over "blank", "damaged" or
custom flags.

## Run it

```bash
segmetric-landmark
```

[← Back to all tools](index.html)
