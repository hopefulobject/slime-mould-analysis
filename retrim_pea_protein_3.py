"""Re-trim Pea protein 3 from a 1.5 mm to a 5 mm rim margin, using its saved mask, and
re-measure it the way slime_mould_workflow.ijm does. Pass --write to save the changes."""
import shutil, sys
import numpy as np, pandas as pd
from PIL import Image, ImageDraw
from skimage import measure
from closing_and_stats import FIJI, circle_fit
from ijperim import ij_perimeter

LABEL, NEW_MARGIN = "Pea protein 3", 5.0
WRITE = "--write" in sys.argv

res = pd.read_csv(FIJI / "results_all.csv")
p = res[res.Label == LABEL].iloc[0]
ppmm, fx, fy = p["Pixels per mm"], p["Food X (px)"], p["Food Y (px)"]
old = np.array(Image.open(FIJI / f"{LABEL} mask.png")) == 0
oh, ow = old.shape
rgb = np.array(Image.open(FIJI / f"{LABEL} dish.tif").convert("RGB"))

def oval(margin):
    m = margin * ppmm
    yy, xx = np.mgrid[0:oh, 0:ow] + 0.5
    a, b = (ow - 2 * m) / 2, (oh - 2 * m) / 2
    return ((xx - ow / 2) / a) ** 2 + ((yy - oh / 2) / b) ** 2 <= 1, np.pi * a * b / ppmm ** 2

def hsb(mask):
    # java.awt.Color.RGBtoHSB scaled to 0-255, as ImageJ's HSB Stack
    c = rgb[mask].astype(float) / 255
    mx, mn = c.max(1), c.min(1); d = mx - mn
    s = np.where(mx > 0, d / np.where(mx > 0, mx, 1), 0)
    r, g, b = c.T
    dd = np.where(d > 0, d, 1)
    rc, gc, bc = (mx - r) / dd, (mx - g) / dd, (mx - b) / dd
    h = np.where(r == mx, bc - gc, np.where(g == mx, 2 + rc - bc, 4 + gc - rc)) / 6
    h = np.where(d > 0, h % 1, 0)
    out = {}
    for name, v in (("hue", h), ("sat", s), ("bri", mx)):
        v = np.floor(v * 255)
        out |= {f"Selected {name} min": v.min(), f"Selected {name} mean": v.mean(), f"Selected {name} max": v.max()}
    return out

def measure_all(mask, analysed):
    area_px = mask.sum(); area = area_px / ppmm ** 2
    props = measure.regionprops(mask.astype(np.uint8))[0]
    perim = ij_perimeter(mask) / ppmm
    ar = props.axis_major_length / props.axis_minor_length
    c = circle_fit(mask, fx, fy, ppmm)
    return {"Area": area, "Perim.": perim, "Circ.": min(4 * np.pi * area / perim ** 2, 1.0),
            "AR": ar, "Round": 1 / ar, "Solidity": props.solidity,
            "Analysed area (mm2)": analysed, "Coverage (%)": 100 * area / analysed,
            "Fit radius food-centred (mm)": c["Fit radius, food-centred (mm)"],
            "Fit RMS error (mm)": c["Fit RMS error (mm)"], "Fit relative error": c["Fit relative error"],
            "Max reach (mm)": c["Max reach (mm)"], "Directions with growth (%)": c["Directions with growth (%)"],
            "Best-fit radius (mm)": c["Best-fit radius (mm)"], "Best-fit RMS error (mm)": c["Best-fit RMS error (mm)"],
            "Best-fit R2": c["Best-fit R2"],
            "Best-fit centre offset from food (mm)": c["Best-fit centre offset from food (mm)"],
            **hsb(mask), "_fit": c}

# check: the old mask re-measured with its old 1.5 mm oval should reproduce the CSV row
ov15, an15 = oval(1.5)
print("old mask pixels outside the 1.5 mm oval:", int((old & ~ov15).sum()))
chk = measure_all(old, an15)
ov5, an5 = oval(NEW_MARGIN)
new = old & ov5
nw = measure_all(new, an5)
print(f"{'column':40s} {'csv (1.5)':>10s} {'recalc 1.5':>10s} {'new 5 mm':>10s}")
for k in [k for k in nw if not k.startswith("_")]:
    print(f"{k:40s} {p[k]:10.3f} {chk[k]:10.3f} {nw[k]:10.3f}")
print("pieces removed by the extra trim (px):", int(old.sum() - new.sum()))

if WRITE:
    bak = FIJI / "before Pea protein 3 5mm rim"
    bak.mkdir(exist_ok=True)
    for f in ["results_all.csv", "results.csv", f"{LABEL} mask.png", f"{LABEL} overlay.png"]:
        shutil.copy2(FIJI / f, bak / f)
    shutil.copytree(FIJI / "stats", bak / "stats", dirs_exist_ok=True)
    for r in ["0.2", "1"]:
        shutil.copy2(FIJI / "closed masks current" / f"{LABEL} closed {r}mm.png", bak / f"{LABEL} closed {r}mm.png")
    # edit only the Pea protein 3 row in both CSVs, keeping ImageJ's 3-decimal format
    vals = {k: v for k, v in nw.items() if not k.startswith("_")} | {"Rim margin (mm)": NEW_MARGIN}
    for name in ["results_all.csv", "results.csv"]:
        lines = (FIJI / name).read_text().split("\n")
        hdr = lines[0].split(",")
        for i, line in enumerate(lines):
            cells = line.split(",")
            if len(cells) == len(hdr) and cells[hdr.index("Label")] == LABEL:
                for k, v in vals.items():
                    cells[hdr.index(k)] = f"{v:.3f}" if not float(v).is_integer() or k == "Rim margin (mm)" else str(int(v))
                lines[i] = ",".join(cells)
        (FIJI / name).write_text("\n".join(lines))
    Image.fromarray(np.where(new, 0, 255).astype(np.uint8)).save(FIJI / f"{LABEL} mask.png")
    # overlay as in analyse(): red mould at 45 %, green analysed oval, cyan / blue circles, white food cross
    base = rgb.astype(float)
    base[new] = base[new] * 0.55 + np.array([255, 0, 0]) * 0.45
    im = Image.fromarray(base.astype(np.uint8)); d = ImageDraw.Draw(im)
    lw = max(2, round(ow / 400)); m = NEW_MARGIN * ppmm
    d.ellipse([m, m, ow - m, oh - m], outline="#00ff00", width=lw)
    c = nw["_fit"]
    rp = c["Fit radius, food-centred (mm)"] * ppmm
    d.ellipse([fx - rp, fy - rp, fx + rp, fy + rp], outline="#00ffff", width=lw)
    # best-fit centre: refit to get cx, cy (circle_fit returns only the offset)
    r = np.zeros(360); dd = np.arange(int(np.hypot(ow, oh)))
    for k in range(360):
        a = 2 * np.pi * k / 360; x, y = fx + dd * np.cos(a), fy + dd * np.sin(a)
        ins = (x >= 0) & (y >= 0) & (x < ow) & (y < oh)
        hit = new[np.floor(y[ins]).astype(int), np.floor(x[ins]).astype(int)]
        r[k] = dd[ins][hit].max() / ppmm if hit.any() else 0
    a = 2 * np.pi * np.arange(360) / 360; ok = r > 0
    xm, ym = r[ok] * np.cos(a[ok]), r[ok] * np.sin(a[ok])
    (A, B, C), *_ = np.linalg.lstsq(np.column_stack([xm, ym, np.ones_like(xm)]), xm**2 + ym**2, rcond=None)
    bx, by, br = fx + A / 2 * ppmm, fy + B / 2 * ppmm, c["Best-fit radius (mm)"] * ppmm
    d.ellipse([bx - br, by - br, bx + br, by + br], outline="#3366ff", width=lw)
    cs = 6 * lw
    d.line([fx - cs, fy, fx + cs, fy], fill="#ffffff", width=lw); d.line([fx, fy - cs, fx, fy + cs], fill="#ffffff", width=lw)
    im.save(FIJI / f"{LABEL} overlay.png")
    print("written; backups in", bak)
