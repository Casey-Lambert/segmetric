---
layout: default
title: Example Images
permalink: /example-images.html
---

# Example Images

Sample scans for trying out SegMetric. Each PDF is a single page holding a
4 &times; 4 grid of 16 panels. Every panel has a wing, four ArUco markers
around it, and a printed label underneath.

## Download

| File | Size |
|---|---|
| [FFT_477_480.pdf](https://github.com/{{ site.repository }}/raw/main/Example%20Images/FFT_477_480.pdf) | about 6 MB |
| [FFT_523_526.pdf](https://github.com/{{ site.repository }}/raw/main/Example%20Images/FFT_523_526.pdf) | about 6 MB |
| [FFT_527_530.pdf](https://github.com/{{ site.repository }}/raw/main/Example%20Images/FFT_527_530.pdf) | about 6 MB |
| [FFT_539_542.pdf](https://github.com/{{ site.repository }}/raw/main/Example%20Images/FFT_539_542.pdf) | about 6 MB |
| [FFT_543_546.pdf](https://github.com/{{ site.repository }}/raw/main/Example%20Images/FFT_543_546.pdf) | about 6 MB |

You can also [browse the folder on GitHub](https://github.com/{{ site.repository }}/tree/main/Example%20Images).

## Try it

1. Download one of the PDFs above and put it in its own folder.
2. Open `segmetric-prepare` (or run `segmetric-tag`, then `segmetric-scale`, as separate steps).
3. Choose the folder with the PDF as the input folder and pick an output folder.
4. Set the grid to **4 rows &times; 4 columns** and click **Run**.

You will get 16 cropped panels, plus a `scales.csv` with the real-world scale
for each one. From there you can continue with `segmetric-mask`,
`segmetric-segment`, `segmetric-landmark`, or all three together with
`segmetric-measure`.
