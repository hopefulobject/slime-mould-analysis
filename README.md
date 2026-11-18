# Slime mould image analysis (SP2274, Group 10)

Scripts used to measure *Physarum polycephalum* growth on agar plates.

| File | What it does |
|---|---|
| `slime_mould_workflow.ijm` | Fiji macro for the final experiment plates: scale, dish crop, colour threshold, rim trim, circle fits, measurements, masks and overlays. |
| `pilot_workflow.ijm` | Same macro for the pilot plates (20 h and 24 h). |
| `closing_and_stats.py` | Morphological closing (dilation then erosion) of the masks at 0.2 mm and 1 mm, re-measurement, and group statistics (Kruskal-Wallis, ANOVA, Welch ANOVA, Dunn, Tukey, Dunnett). |
| `pilot_closing.py` | Closing and measurements for the pilot plates (no group statistics). |
| `retrim_pea_protein_3.py` | Re-trims Pea protein 3 from a 1.5 mm to a 5 mm rim margin using its saved mask, so it matches the other plates. |
| `ijperim.py` | ImageJ-style perimeter, used by the re-trim script. |

## Order

1. Run `slime_mould_workflow.ijm` / `pilot_workflow.ijm` in Fiji.
2. Run `retrim_pea_protein_3.py --write` (final experiment only).
3. Run `closing_and_stats.py` and `pilot_closing.py "20 hours" "24 hours"`.

Python scripts need numpy, scipy, scikit-image, pandas and pillow. File paths in the macros point to the original analysis folder and need changing to run elsewhere.

Code written with assistance from Claude (Anthropic).
