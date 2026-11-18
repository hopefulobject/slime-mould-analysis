"""Morphological closing (dilate then erode) of the masks at 0.2 mm and 1 mm, the same shape
and circle-fit measurements as slime_mould_workflow.ijm on the closed masks, and group
statistics for each batch (A = archive, B = current) and each closing radius.

Inputs : A - Analyze_Archive/fiji analysis/slime_mould_results.xlsx, <plate> mask.png, and the
             overlays (for the food centre, which the archive results don't record)
         B - fiji analysis/results_all.csv and fiji analysis/<plate> mask.png (mould black on white)
Outputs: fiji analysis/closed masks archive|current/<plate> closed <r>mm.png
         fiji analysis/stats/all_rows.csv        one row per batch, plate and morphology (none, 0.2, 1 mm)
         fiji analysis/stats/tests_overview.csv  one row per batch, morphology and metric: normality,
                                                 Levene, Kruskal-Wallis, one-way ANOVA, Welch ANOVA
         fiji analysis/stats/posthoc.csv         Dunn (Holm), Tukey HSD, Dunnett vs Neg
"""
import itertools
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image
from scipy import ndimage, stats
from skimage import measure, morphology

HERE = Path(__file__).parent
FIJI = HERE / "fiji analysis"
ARCHIVE = HERE.parent / "Analyze_Archive" / "fiji analysis"
STATS_DIR = FIJI / "stats"
RADII_MM = [0.2, 1.0]
NRAYS = 360                      # same as slime_mould_workflow.ijm
CONTROL = "Neg"
ALPHA = 0.05
GROUP_ORDER = ["Neg", "Glucose", "NaCl", "Pea protein", "Rice bran", "Whey"]

# results_all.csv column -> sheet column, for the unclosed rows
FIJI_COLS = {
    "Area": "Mould area (mm2)", "Perim.": "Perimeter (mm)", "Circ.": "Circularity",
    "AR": "Aspect ratio", "Round": "Roundness", "Solidity": "Solidity",
    "Dish area (mm2)": "Dish area (mm2)", "Analysed area (mm2)": "Analysed area (mm2)",
    "Coverage (%)": "Coverage (%)", "Fit radius food-centred (mm)": "Fit radius, food-centred (mm)",
    "Fit RMS error (mm)": "Fit RMS error (mm)", "Fit relative error": "Fit relative error",
    "Max reach (mm)": "Max reach (mm)", "Directions with growth (%)": "Directions with growth (%)",
    "Best-fit radius (mm)": "Best-fit radius (mm)", "Best-fit RMS error (mm)": "Best-fit RMS error (mm)",
    "Best-fit R2": "Best-fit R2", "Best-fit centre offset from food (mm)": "Best-fit centre offset from food (mm)",
}
SETTINGS_COLS = {
    "Rim margin (mm)": "Rim margin (mm)", "Min piece (mm2)": "Min piece (mm2)",
    "Selected hue min": "Hue min", "Selected hue max": "Hue max",
    "Selected sat min": "Sat min", "Selected sat max": "Sat max",
    "Selected bri min": "Bri min", "Selected bri max": "Bri max",
    "Scale line (mm)": "Scale line (mm)", "Pixels per mm": "Pixels per mm",
}
TESTED = ["Mould area (mm2)", "Perimeter (mm)", "Circularity", "Aspect ratio", "Roundness",
          "Solidity", "Coverage (%)", "Fit radius, food-centred (mm)", "Fit relative error",
          "Max reach (mm)", "Best-fit radius (mm)", "Best-fit R2",
          "Best-fit centre offset from food (mm)", "Fill fraction", "Pieces"]


def morph_name(r_mm):
    return "None" if r_mm == 0 else f"Closed {r_mm:g}mm"


def circle_fit(mask, fx, fy, ppmm):
    """Rays from the food centre and circle fits, as circleFit() in slime_mould_workflow.ijm."""
    h, w = mask.shape
    d = np.arange(int(np.hypot(w, h)))
    r = np.zeros(NRAYS)
    for k in range(NRAYS):
        a = 2 * np.pi * k / NRAYS
        x, y = fx + d * np.cos(a), fy + d * np.sin(a)
        inside = (x >= 0) & (y >= 0) & (x < w) & (y < h)
        hit = mask[np.floor(y[inside]).astype(int), np.floor(x[inside]).astype(int)]
        r[k] = d[inside][hit].max() / ppmm if hit.any() else 0.0
    out = {"Fit radius, food-centred (mm)": r.mean(),
           "Fit RMS error (mm)": np.sqrt(((r - r.mean()) ** 2).mean()),
           "Max reach (mm)": r.max(),
           "Directions with growth (%)": 100 * (r > 0).mean()}
    out["Fit relative error"] = out["Fit RMS error (mm)"] / r.mean() if r.mean() > 0 else np.nan
    a = 2 * np.pi * np.arange(NRAYS) / NRAYS
    ok = r > 0
    xm, ym = r[ok] * np.cos(a[ok]), r[ok] * np.sin(a[ok])
    z = xm ** 2 + ym ** 2
    out.update(dict.fromkeys(["Best-fit radius (mm)", "Best-fit RMS error (mm)", "Best-fit R2",
                              "Best-fit centre offset from food (mm)"], np.nan))
    if ok.sum() >= 3:
        (A, B, C), *_ = np.linalg.lstsq(np.column_stack([xm, ym, np.ones_like(xm)]), z, rcond=None)
        cx, cy = A / 2, B / 2
        rad = np.sqrt(C + cx ** 2 + cy ** 2)
        g = np.hypot(xm - cx, ym - cy) - rad
        e = z - (A * xm + B * ym + C)
        sst = ((z - z.mean()) ** 2).sum()
        out.update({"Best-fit radius (mm)": rad, "Best-fit RMS error (mm)": np.sqrt((g ** 2).mean()),
                    "Best-fit R2": 1 - (e ** 2).sum() / sst if sst > 0 else np.nan,
                    "Best-fit centre offset from food (mm)": np.hypot(cx, cy)})
    return out


def shape(mask, ppmm):
    props = measure.regionprops(mask.astype(np.uint8))[0]       # whole mask as one region
    area_px = mask.sum()
    area = area_px / ppmm ** 2
    perim = measure.perimeter(mask) / ppmm
    major, minor = props.axis_major_length, props.axis_minor_length
    return {"Mould area (mm2)": area, "Perimeter (mm)": perim,
            "Circularity": min(4 * np.pi * area / perim ** 2, 1.0),
            "Aspect ratio": major / minor if minor > 0 else np.nan,
            "Roundness": 4 * area_px / (np.pi * major ** 2),      # ImageJ "Round"
            "Solidity": props.solidity}


def find_plus(path):
    """Food centre of an archive plate: the white + that the macro drew on the overlay."""
    o = np.array(Image.open(path).convert("RGB")).astype(int)
    white = (o.min(axis=2) >= 235) & (np.ptp(o, axis=2) <= 25)
    lab = measure.label(white, connectivity=2)
    border = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))) - {0}
    white &= ~np.isin(lab, list(border))             # drop the white background outside the dish
    arm = np.ones((1, 25))                            # the + has 12 px arms
    score = np.minimum(ndimage.convolve(white.astype(float), arm, mode="constant"),
                       ndimage.convolve(white.astype(float), arm.T, mode="constant"))
    y, x = np.unravel_index(score.argmax(), score.shape)
    return float(x), float(y)


def load_archive():
    """Archive Data sheet in results_all.csv column names, with food centres from the overlays."""
    data = pd.read_excel(ARCHIVE / "slime_mould_results.xlsx", sheet_name="Data")
    data = data.rename(columns={new: old for old, new in {**FIJI_COLS, **SETTINGS_COLS}.items()})
    data = data.rename(columns={"Mould area (mm2)": "Area"})
    food = []
    for label in data["Label"]:
        # Glucose 1's mask was overwritten by a later rerun; its matching overlay is next to it
        ov = ARCHIVE / f"{label} overlay.png"
        food.append(find_plus(ov if ov.exists() else ARCHIVE.parent / "overlays" / f"{label} overlay.png"))
    data["Food X (px)"], data["Food Y (px)"] = zip(*food)
    return data


def build_rows(results, mask_dir, closed_dir):
    closed_dir.mkdir(exist_ok=True)
    rows = []
    for _, plate in results.iterrows():
        label, ppmm = plate["Label"], plate["Pixels per mm"]
        fx, fy = plate["Food X (px)"], plate["Food Y (px)"]
        mask = np.array(Image.open(mask_dir / f"{label} mask.png")) == 0      # mould = True
        common = {"Label": label, "Group": plate["Group"], "Replicate": plate["Replicate"],
                  **{new: plate[old] for old, new in SETTINGS_COLS.items()}}
        mould_area = mask.sum() / ppmm ** 2
        rows.append({**common, **{new: plate[old] for old, new in FIJI_COLS.items()},
                     "Morphology": morph_name(0), "Closing radius (px)": 0,
                     "Fill fraction": 1.0, "Pieces": measure.label(mask, connectivity=2).max()})
        for r_mm in RADII_MM:
            r_px = max(int(round(r_mm * ppmm)), 1)
            padded = np.pad(mask, r_px + 1)        # so the dilation isn't clipped at the image edge
            closed = ndimage.binary_closing(padded, morphology.disk(r_px))
            closed = closed[r_px + 1:-(r_px + 1), r_px + 1:-(r_px + 1)] | mask
            Image.fromarray(np.where(closed, 0, 255).astype(np.uint8)).save(
                closed_dir / f"{label} closed {r_mm:g}mm.png")
            row = {**common, "Dish area (mm2)": plate["Dish area (mm2)"],
                   "Analysed area (mm2)": plate["Analysed area (mm2)"],
                   **shape(closed, ppmm), **circle_fit(closed, fx, fy, ppmm),
                   "Morphology": morph_name(r_mm), "Closing radius (px)": r_px,
                   "Pieces": measure.label(closed, connectivity=2).max()}
            row["Coverage (%)"] = 100 * row["Mould area (mm2)"] / plate["Analysed area (mm2)"]
            row["Fill fraction"] = mould_area / row["Mould area (mm2)"]
            rows.append(row)
    return pd.DataFrame(rows)


def holm(p):
    p = np.asarray(p, dtype=float)
    order = np.argsort(p)
    adj = np.empty(len(p))
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, (len(p) - rank) * p[i])
        adj[i] = min(running, 1.0)
    return adj


def dunn(values, groups, names):
    ranks = stats.rankdata(values)
    n = len(values)
    _, ties = np.unique(values, return_counts=True)
    tie_term = (ties ** 3 - ties).sum() / (12 * (n - 1))
    rows = []
    for a, b in itertools.combinations(names, 2):
        ia, ib = groups == a, groups == b
        se = np.sqrt((n * (n + 1) / 12 - tie_term) * (1 / ia.sum() + 1 / ib.sum()))
        z = (ranks[ia].mean() - ranks[ib].mean()) / se
        rows.append({"test": "Dunn (Holm)", "group A": a, "group B": b, "statistic": z,
                     "p": 2 * stats.norm.sf(abs(z))})
    for row, p_adj in zip(rows, holm([r["p"] for r in rows])):
        row["p adjusted"] = p_adj
    return rows


def welch_anova(samples):
    k = len(samples)
    n = np.array([len(s) for s in samples])
    m = np.array([np.mean(s) for s in samples])
    v = np.array([np.var(s, ddof=1) for s in samples])
    if np.any(v == 0):
        return np.nan, np.nan
    w = n / v
    mw = (w * m).sum() / w.sum()
    a = (w * (m - mw) ** 2).sum() / (k - 1)
    tmp = ((1 - w / w.sum()) ** 2 / (n - 1)).sum()
    f = a / (1 + 2 * (k - 2) / (k ** 2 - 1) * tmp)
    return f, stats.f.sf(f, k - 1, (k ** 2 - 1) / (3 * tmp))


def test_metric(morph, metric, values, groups, names):
    samples = [values[groups == g] for g in names]
    n, k = len(values), len(names)
    row = {"Morphology": morph, "Metric": metric}
    if np.ptp(values) == 0:
        row["Note"] = "all values identical - not tested"
        return row, []
    resid = np.concatenate([s - s.mean() for s in samples])
    row["Shapiro-Wilk p (residuals)"] = stats.shapiro(resid).pvalue
    row["Levene p"] = stats.levene(*samples, center="median").pvalue
    h, p_kw = stats.kruskal(*samples)
    row.update({"Kruskal-Wallis H": h, "Kruskal-Wallis p": p_kw,
                "Kruskal-Wallis epsilon2": h * (n + 1) / (n ** 2 - 1)})
    f, p_f = stats.f_oneway(*samples)
    ss_between = sum(len(s) * (s.mean() - values.mean()) ** 2 for s in samples)
    row.update({"ANOVA F": f, "ANOVA p": p_f,
                "ANOVA eta2": ss_between / ((values - values.mean()) ** 2).sum()})
    row["Welch ANOVA F"], row["Welch ANOVA p"] = welch_anova(samples)

    post = dunn(values, groups, names)
    tukey = stats.tukey_hsd(*samples)
    for i, j in itertools.combinations(range(k), 2):
        post.append({"test": "Tukey HSD", "group A": names[i], "group B": names[j],
                     "statistic": samples[i].mean() - samples[j].mean(),
                     "p": tukey.pvalue[i, j], "p adjusted": tukey.pvalue[i, j]})
    ci = names.index(CONTROL)
    others = [i for i in range(k) if i != ci]
    dn = stats.dunnett(*[samples[i] for i in others], control=samples[ci])
    for idx, i in enumerate(others):
        post.append({"test": "Dunnett vs Neg", "group A": names[i], "group B": CONTROL,
                     "statistic": dn.statistic[idx], "p": dn.pvalue[idx], "p adjusted": dn.pvalue[idx]})
    for r in post:
        r.update({"Morphology": morph, "Metric": metric, "significant": r["p adjusted"] < ALPHA})
    return row, post


def main():
    batches = {
        "A": (load_archive(), ARCHIVE, FIJI / "closed masks archive"),
        "B": (pd.read_csv(FIJI / "results_all.csv"), FIJI, FIJI / "closed masks current"),
    }
    rows = []
    for batch, (results, mask_dir, closed_dir) in batches.items():
        rows.append(build_rows(results, mask_dir, closed_dir).assign(Batch=batch))
    rows = pd.concat(rows, ignore_index=True)
    STATS_DIR.mkdir(exist_ok=True)
    rows.to_csv(STATS_DIR / "all_rows.csv", index=False)

    names = [g for g in GROUP_ORDER if g in set(rows["Group"])]
    overview, post = [], []
    for (batch, morph), df in rows.groupby(["Batch", "Morphology"], sort=False):
        groups = df["Group"].to_numpy()
        for metric in TESTED:
            if morph == "None" and metric == "Fill fraction":
                continue
            row, p = test_metric(morph, metric, df[metric].to_numpy(dtype=float), groups, names)
            overview.append({"Batch": batch, **row})
            post.extend({"Batch": batch, **r} for r in p)
    overview = pd.DataFrame(overview)
    for col in ["Kruskal-Wallis p", "ANOVA p", "Welch ANOVA p"]:
        adj = col + " (Holm)"
        overview[adj] = np.nan
        for _, idx in overview.groupby(["Batch", "Morphology"]).groups.items():
            vals = overview.loc[idx, col].dropna()
            overview.loc[vals.index, adj] = holm(vals)
    overview.to_csv(STATS_DIR / "tests_overview.csv", index=False)
    pd.DataFrame(post).to_csv(STATS_DIR / "posthoc.csv", index=False)

    pd.set_option("display.width", 220)
    print(overview[["Batch", "Morphology", "Metric", "Kruskal-Wallis p", "Kruskal-Wallis p (Holm)",
                    "ANOVA p", "ANOVA p (Holm)", "Welch ANOVA p"]].round(4).to_string(index=False))


if __name__ == "__main__":
    main()
