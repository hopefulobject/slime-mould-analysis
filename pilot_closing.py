"""Morphological closing (0.2 mm and 1 mm) and measurements for the pilot plates.

Uses the same closing and measurements as closing_and_stats.py. No group statistics: the pilot
has one plate per condition.

Usage: python pilot_closing.py "20 hours" ["24 hours"]
Inputs : fiji analysis/pilot/<time>/results.csv and <plate> mask.png (from pilot_workflow.ijm)
Outputs: fiji analysis/pilot/<time>/closed masks/<plate> closed <r>mm.png
         fiji analysis/pilot/<time>/all_rows.csv   one row per plate and morphology
"""
import sys

import pandas as pd

from closing_and_stats import FIJI, build_rows

PILOT = FIJI / "pilot"


def main(times):
    for time in times:
        folder = PILOT / time
        results = pd.read_csv(folder / "results.csv")
        # ImageJ writes the commas in the plate names as ";" in the CSV
        results["Label"] = results["Label"].str.replace(";", ",")
        results["Group"] = results["Group"].str.replace(";", ",")
        # a plate redone after an aborted run has two rows: keep the later one
        results = results.drop_duplicates("Label", keep="last")
        rows = build_rows(results, folder, folder / "closed masks")
        rows.to_csv(folder / "all_rows.csv", index=False)
        print(f"{time}: {len(results)} plates -> {len(rows)} rows")


if __name__ == "__main__":
    main(sys.argv[1:])
