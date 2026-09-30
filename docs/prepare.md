---
layout: page
title: segmetric.prepare
permalink: /prepare.html
---

# segmetric.prepare

Combines `tag` and `scale` into one streamlined process with one input
folder and one output folder. It works by calling `tag`'s and `scale`'s
pipelines back to back, and optionally applies a `set` preset to each
panel's own filename to add metadata columns to a combined
`<output>/summary.csv`. It does not change how `tag` and `scale` work —
it's a convenience process calling existing pipelines as a library.

Manual scaling is not available in `segmetric.prepare`. If there are no
markers present, run `tag` and `scale` separately.

Output panels are saved as `<output>/panels`. Output crops are saved in
`<output>/scales` and scale information is saved as
`<output>/scales/scales.csv` as mm/pixel.

## Run it

```bash
segmetric-prepare
```

[← Back to all tools](index.html)
