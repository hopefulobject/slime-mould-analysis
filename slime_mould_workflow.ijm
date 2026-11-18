// Slime mould plate analysis — guided workflow for Analyze/raw (units: mm)
//
// YOU:   1) draw the scale line on the ruler and enter its length
//        2) draw an oval around the dish with the slime mould
//        3) threshold the mould LIVE in Fiji's Color Threshold window, then click Select
//        4) check the result (rim margin / small pieces / fitted circles) and confirm
// MACRO: sets the scale, crops to the dish, clears outside, keeps an untouched copy
//        of the dish, trims the rim band (reflections) and tiny specks from your
//        selection, fits circles to the spread around the food, measures, and saves
//        results + overlay + mask for every plate.
//
// Circle fit: from the food centre, the macro finds how far the mould reaches in
// each of 360 directions. Food-centred fit = mean reach (radius), RMS error and
// relative error (RMS / radius). Best-fit circle = least-squares circle through
// those edge points: radius, RMS error, R2, and how far its centre is from the food.

var rawDir = "/Users/ibrahim/Desktop/projects/SP2274/Analyze/raw/";
var out    = "/Users/ibrahim/Desktop/projects/SP2274/Analyze/fiji analysis/";
var label  = "";
var OPACITY = 45;              // overlay strength (%)
var H1 = 30;  var H2 = 56;     // hue range used only to find the food (yellow)
var MARGIN = 1.5;              // mm trimmed off the inside of your oval (dish wall reflections)
var MINPIECE = 0.5;            // mm2 - pieces smaller than this are ignored
var NRAYS = 360;               // directions used for the circle fit (1 per degree)
// Saved scales: a CSV in the Analyze folder (next to raw/) with a "Label" column
// (e.g. "Glucose 1") and a "Pixels per mm" column - an old results.csv works as is.
// Plates listed there skip Step 1; any plate not listed asks you to draw the line.
var SCALEFILE = "scales.csv";
// Dish circle: drawn by hand once, then reused (same size in mm, same place in the
// photo) on every plate - you only drag it into position. It is saved to DISHFILE
// (next to raw/) each time you confirm it, so new runs start with it too.
// Delete that file to draw the circle from scratch again.
var DISHFILE = "dish_circle.txt";
var dishWmm = 0; var dishHmm = 0; var dishCx = 0; var dishCy = 0;
var scaleLabels = newArray(0); var scaleVals = newArray(0);

// food centre (pixels in the cropped dish image) and circle-fit results
var FX = 0; var FY = 0;
var cfR = 0; var cfRMS = 0; var cfRel = 0; var cfMax = 0; var cfDir = 0;
var ffX = 0; var ffY = 0; var ffR = 0; var ffRMS = 0; var ffR2 = 0; var ffOff = 0;
// hue / saturation / brightness of the pixels you selected (recorded per plate)
var hsbMin = newArray(3); var hsbMean = newArray(3); var hsbMax = newArray(3);

File.makeDirectory(out);
csv = out + "results.csv";
cleanPath = getDirectory("temp") + "slime_mould_clean_dish.tif";

// ---- list photos and tidy their names ----
files = getFileList(rawDir);
pairs = newArray(0);
for (k = 0; k < files.length; k++) {
    f = files[k];
    lf = toLowerCase(f);
    if (endsWith(lf, ".jpg") || endsWith(lf, ".jpeg") || endsWith(lf, ".png") || endsWith(lf, ".tif")) {
        nm = cleanName(f);
        pairs = Array.concat(pairs, nm + "|" + f);
    }
}
Array.sort(pairs);
n = pairs.length;
if (n == 0) exit("No photos found in " + rawDir);
labels = newArray(n);
fnames = newArray(n);
for (k = 0; k < n; k++) {
    p = indexOf(pairs[k], "|");
    labels[k] = substring(pairs[k], 0, p);
    fnames[k] = substring(pairs[k], p + 1);
}

Dialog.create("Slime mould workflow");
Dialog.addMessage(n + " photos found in Analyze/raw.");
Dialog.addChoice("Start from:", labels, labels[0]);
Dialog.addNumber("Default scale-line length (mm):", 60);
Dialog.show();
startLabel = Dialog.getChoice();
known = Dialog.getNumber();
start = 0;
for (k = 0; k < n; k++) if (labels[k] == startLabel) start = k;
scalePath = File.getParent(rawDir) + File.separator + SCALEFILE;
loadScales(scalePath);
if (scaleLabels.length > 0) print("Loaded saved scales for " + scaleLabels.length + " plates from " + scalePath);
else print("No saved scales found at " + scalePath + " - you will draw the scale line for every plate.");
dishPath = File.getParent(rawDir) + File.separator + DISHFILE;
loadDish(dishPath);
if (dishWmm > 0) print("Loaded saved dish circle from " + dishPath + " (" + d2s(dishWmm, 1) + " x " + d2s(dishHmm, 1) + " mm)");
else print("No saved dish circle at " + dishPath + " - draw it on the first plate.");

run("Set Measurements...", "area perimeter shape display redirect=None decimal=3");
// Fiji can't reload results.csv as the Results table, so when starting partway the
// earlier rows are kept as text and written back in front of the new ones on every save.
prevResults = "";
if (start > 0 && File.exists(csv)) prevResults = File.openAsString(csv);
run("Clear Results");

margin = MARGIN; minPiece = MINPIECE;   // carry over from plate to plate

for (i = start; i < n; i++) {
    label = labels[i];
    open(rawDir + fnames[i]);
    id = getImageID();
    rename(label);
    tag = "[" + (i + 1) + "/" + n + "] " + label;

    // ---- 1. Scale: use the saved pixels/mm if this plate has one, else draw the line ----
    ppmm = savedScale(label);
    if (!isNaN(ppmm)) {
        run("Set Scale...", "distance=" + ppmm + " known=1 unit=mm");
        scaleSrc = "saved"; scaleLine = NaN;
    } else {
        run("Select None");
        setTool("line");
        waitForUser(tag + " - Step 1 of 4: scale",
            "Draw a straight line between two marks on the ruler\n(e.g. 20 to 26 = 60 mm). Zoom in with + for accuracy.\n\nThen click OK.");
        while (selectionType() != 5) {
            setTool("line");
            waitForUser(tag + " - Step 1 of 4: scale", "No straight line found.\nDraw a line between two ruler marks, then click OK.");
        }
        Dialog.create(tag + " - scale");
        Dialog.addNumber("Length of the line you drew (mm):", known);
        Dialog.show();
        known = Dialog.getNumber();
        run("Set Scale...", "known=" + known + " unit=mm");
        getPixelSize(unit, pw, ph);
        ppmm = 1 / pw;
        scaleSrc = "drawn"; scaleLine = known;
    }

    // ---- 2. Dish: draw the circle on the first plate, reuse it on the rest ----
    run("Select None");
    setTool("oval");
    if (dishWmm > 0) {
        // put the saved circle back whenever it is lost (a click outside it removes it)
        dw = dishWmm * ppmm; dh = dishHmm * ppmm;
        placed = false;
        while (!placed) {
            selectImage(id);
            if (selectionType() != 1)
                makeOval(dishCx * getWidth() - dw / 2, dishCy * getHeight() - dh / 2, dw, dh);
            Dialog.createNonBlocking(tag + " - Step 2 of 4: dish");
            Dialog.addMessage("The dish circle from the previous plate is shown.\nDrag it from the INSIDE so it sits on the inner edge of this dish\n(don't resize it unless it really doesn't fit).\n\nLost the circle? Just click OK and it comes back.");
            Dialog.addCheckbox("Start over from the saved circle", false);
            Dialog.show();
            selectImage(id);
            if (Dialog.getCheckbox()) run("Select None");
            else if (selectionType() == 1) placed = true;
        }
    } else {
        waitForUser(tag + " - Step 2 of 4: dish",
            "Draw an oval along the INNER edge of the dish with the slime mould\n(hold Shift for a circle, drag the handles to adjust).\nThis circle will be reused on the next plates.\n\nThen click OK.");
    }
    while (selectionType() != 1) {
        setTool("oval");
        waitForUser(tag + " - Step 2 of 4: dish", "No oval found.\nDraw an oval around the dish, then click OK.");
    }
    dishArea = getValue("Area");
    getSelectionBounds(ox, oy, ow, oh);
    // remember this circle (size in mm, centre as a fraction of the photo) for the next plate
    dishWmm = ow / ppmm; dishHmm = oh / ppmm;
    dishCx = (ox + ow / 2) / getWidth(); dishCy = (oy + oh / 2) / getHeight();
    File.saveString("width_mm=" + dishWmm + "\nheight_mm=" + dishHmm + "\ncentre_x=" + dishCx + "\ncentre_y=" + dishCy + "\n", dishPath);
    run("Crop");
    makeOval(0, 0, ow, oh);
    setBackgroundColor(255, 255, 255);
    run("Clear Outside");
    run("Select None");
    run("Original Scale");
    findFood(id, ow, oh);

    // keep an untouched copy: the Color Threshold window recolours the image it works on
    run("Duplicate...", "title=tmp_clean");
    saveAs("Tiff", cleanPath);
    close();
    selectImage(id);

    done = false;
    while (!done) {
        // ---- 3. Colour threshold, live (you) ----
        selectImage(id);
        run("Select None");
        run("Remove Overlay");
        run("Color Threshold...");
        selectImage(id);
        waitForUser(tag + " - Step 3 of 4: colour threshold",
            "Adjust the sliders in the Color Threshold window - the photo updates live.\n(Color space: HSB, Threshold color: Red makes it easy to see.)\n\nWhen only the slime mould is marked, click 'Select'\nin the Color Threshold window, then click OK here.");
        selectImage(id);
        while (selectionType() == -1) {
            waitForUser(tag + " - Step 3 of 4: colour threshold", "No selection found.\nClick 'Select' in the Color Threshold window, then click OK here.");
            selectImage(id);
        }
        roiManager("reset");
        roiManager("add");                 // your colour selection = ROI 0

        // swap in the untouched copy of the dish
        selectImage(id);
        close();
        open(cleanPath);
        id = getImageID();
        rename(label);
        run("Set Scale...", "distance=" + ppmm + " known=1 unit=mm");

        // ---- 4. Check rim margin / small pieces / circles (you) ----
        checking = true;
        while (checking) {
            analysedArea = analyse(id, margin, minPiece, ppmm, ow, oh, false);
            Dialog.createNonBlocking(tag + " - Step 4 of 4: check");
            Dialog.addMessage("Red = slime mould. Green = area analysed. White + = food centre.\nCyan = food-centred circle fit. Blue = best-fit circle.");
            Dialog.addMessage("Radius " + d2s(cfR, 2) + " mm, RMS error " + d2s(cfRMS, 2) + " mm, relative error " + d2s(cfRel, 3) + "\nBest-fit circle: radius " + d2s(ffR, 2) + " mm, R2 " + d2s(ffR2, 3) + ", centre offset " + d2s(ffOff, 2) + " mm");
            Dialog.addNumber("Rim margin (mm) - trims wall reflections:", margin);
            Dialog.addNumber("Ignore pieces smaller than (mm2):", minPiece);
            Dialog.addCheckbox("Click the food centre myself", false);
            Dialog.addCheckbox("Redo the colour threshold", false);
            Dialog.addCheckbox("Looks right - measure this plate", false);
            Dialog.show();
            margin = Dialog.getNumber();
            minPiece = Dialog.getNumber();
            doFood = Dialog.getCheckbox();
            redo = Dialog.getCheckbox();
            ok = Dialog.getCheckbox();
            if (doFood) {
                selectImage(id);
                run("Remove Overlay");
                run("Select None");
                setTool("point");
                waitForUser(tag + " - food centre", "Click the centre of the food, then click OK.");
                if (selectionType() == 10) {
                    getSelectionCoordinates(px, py);
                    FX = px[0]; FY = py[0];
                }
                run("Select None");
            } else if (redo) {
                checking = false;
            } else if (ok) {
                checking = false;
                done = true;
            }
        }
    }

    // ---- 5. Measure, save results / overlay / mask ----
    analysedArea = analyse(id, margin, minPiece, ppmm, ow, oh, true);
    row = nResults - 1;
    group = replace(label, "\\s*\\d+$", "");
    rep = replace(label, "^.*?(\\d+)$", "$1");
    setResult("Label", row, label);
    setResult("Group", row, group);
    setResult("Replicate", row, rep);
    setResult("Dish area (mm2)", row, dishArea);
    setResult("Analysed area (mm2)", row, analysedArea);
    setResult("Coverage (%)", row, 100 * getResult("Area", row) / analysedArea);
    setResult("Fit radius food-centred (mm)", row, cfR);
    setResult("Fit RMS error (mm)", row, cfRMS);
    setResult("Fit relative error", row, cfRel);
    setResult("Max reach (mm)", row, cfMax);
    setResult("Directions with growth (%)", row, cfDir);
    setResult("Best-fit radius (mm)", row, ffR);
    setResult("Best-fit RMS error (mm)", row, ffRMS);
    setResult("Best-fit R2", row, ffR2);
    setResult("Best-fit centre offset from food (mm)", row, ffOff);
    setResult("Food X (px)", row, FX);
    setResult("Food Y (px)", row, FY);
    setResult("Rim margin (mm)", row, margin);
    setResult("Min piece (mm2)", row, minPiece);
    setResult("Selected hue min", row, hsbMin[0]);  setResult("Selected hue mean", row, hsbMean[0]);  setResult("Selected hue max", row, hsbMax[0]);
    setResult("Selected sat min", row, hsbMin[1]);  setResult("Selected sat mean", row, hsbMean[1]);  setResult("Selected sat max", row, hsbMax[1]);
    setResult("Selected bri min", row, hsbMin[2]);  setResult("Selected bri mean", row, hsbMean[2]);  setResult("Selected bri max", row, hsbMax[2]);
    setResult("Scale line (mm)", row, scaleLine);
    setResult("Scale source", row, scaleSrc);
    setResult("Pixels per mm", row, ppmm);
    setResult("File", row, fnames[i]);
    updateResults();
    saveResults(csv, prevResults);
    File.copy(cleanPath, out + label + " dish.tif");   // cropped dish photo, aligned with the mask

    selectImage(id);
    run("Select None");
    run("Flatten");
    saveAs("PNG", out + label + " overlay.png");
    close();
    selectImage(id);
    close();
}
roiManager("reset");
showMessage("Done", "All plates measured.\nResults, overlays and masks are in Analyze/fiji analysis.");

// Turns your colour selection (ROI 0) into a mask on the clean dish, trims the rim
// band and small pieces, fits circles, and draws the overlay on the photo.
// Returns the analysed area in mm2. If isFinal, also measures, records the
// hue/saturation/brightness of the selected pixels, and saves the mask.
function analyse(id, margin, minPiece, ppmm, ow, oh, isFinal) {
    m = margin * ppmm;
    selectImage(id);
    w = getWidth(); h = getHeight();
    setBatchMode(true);
    run("Select None");
    run("Remove Overlay");
    newImage("tmp_sel", "8-bit black", w, h, 1);
    roiManager("select", 0);
    run("Set...", "value=255");
    run("Select None");
    makeOval(m, m, ow - 2 * m, oh - 2 * m);
    area = PI * (ow - 2 * m) * (oh - 2 * m) / 4 / (ppmm * ppmm);
    run("Make Inverse");
    run("Set...", "value=0");
    run("Select None");

    if (minPiece > 0) {
        setThreshold(255, 255);
        run("Analyze Particles...", "size=" + (minPiece * ppmm * ppmm) + "-Infinity pixel show=Masks");
        rename("tmp_clean_mask");
        if (is("Inverting LUT")) run("Invert LUT");
        if (getPixel(0, 0) == 255) run("Invert");
        close("tmp_sel");
        selectWindow("tmp_clean_mask");
        rename("tmp_sel");
    }

    circleFit("tmp_sel", ppmm);

    // overlay: red mould + green analysed-area outline + fitted circles + food centre
    selectWindow("tmp_sel");
    run("Duplicate...", "title=tmp_ov");
    run("Red");
    run("RGB Color");
    selectImage(id);
    run("Add Image...", "image=tmp_ov x=0 y=0 opacity=" + OPACITY + " zero");
    lw = maxOf(2, round(ow / 400));
    makeOval(m, m, ow - 2 * m, oh - 2 * m);
    Overlay.addSelection("#00ff00", lw);
    if (cfR > 0) {
        rp = cfR * ppmm;
        makeOval(FX - rp, FY - rp, 2 * rp, 2 * rp);
        Overlay.addSelection("#00ffff", lw);
    }
    if (ffR > 0) {
        rp = ffR * ppmm;
        makeOval(ffX - rp, ffY - rp, 2 * rp, 2 * rp);
        Overlay.addSelection("#3366ff", lw);
    }
    cs = 6 * lw;
    makeLine(FX - cs, FY, FX + cs, FY);  Overlay.addSelection("#ffffff", lw);
    makeLine(FX, FY - cs, FX, FY + cs);  Overlay.addSelection("#ffffff", lw);
    run("Select None");

    if (isFinal) {
        // measure the trimmed mould
        selectWindow("tmp_sel");
        run("Set Scale...", "distance=" + ppmm + " known=1 unit=mm");
        setThreshold(255, 255);
        run("Create Selection");
        run("Measure");
        hasSel = (selectionType() != -1);
        if (hasSel) roiManager("add");          // ROI 1 = trimmed mould

        // hue / saturation / brightness of the selected pixels
        for (c = 0; c < 3; c++) { hsbMin[c] = NaN; hsbMean[c] = NaN; hsbMax[c] = NaN; }
        if (hasSel) {
            selectImage(id);
            run("Select None");
            run("Duplicate...", "title=tmp_hsb");
            run("Remove Overlay");
            run("HSB Stack");
            for (c = 0; c < 3; c++) {
                setSlice(c + 1);
                roiManager("select", 1);
                getStatistics(a, mean, mn, mx);
                hsbMin[c] = mn; hsbMean[c] = mean; hsbMax[c] = mx;
            }
            roiManager("select", 1);
            roiManager("delete");
        }

        // black-and-white mask file (mould black on white)
        selectWindow("tmp_sel");
        run("Select None");
        resetThreshold();
        run("Grays");
        run("Invert");
        saveAs("PNG", out + label + " mask.png");
        close();
    }
    close("tmp_*");
    setBatchMode(false);
    selectImage(id);
    return area;
}

// ---------- helpers ----------
// Reads Label + "Pixels per mm" columns from a CSV into scaleLabels / scaleVals.
function loadScales(path) {
    if (!File.exists(path)) return;
    lines = split(File.openAsString(path), "\n");
    if (lines.length < 2) return;
    hdr = split(lines[0], "(,)");
    iL = -1; iP = -1;
    for (c = 0; c < hdr.length; c++) {
        hname = String.trim(replace(hdr[c], "\"", ""));
        if (hname == "Label") iL = c;
        if (hname == "Pixels per mm") iP = c;
    }
    if (iL < 0 || iP < 0) {
        print("Scale file " + path + " needs 'Label' and 'Pixels per mm' columns - ignoring it.");
        return;
    }
    for (r = 1; r < lines.length; r++) {
        parts = split(lines[r], "(,)");
        if (parts.length > maxOf(iL, iP)) {
            lab = String.trim(replace(parts[iL], "\"", ""));
            v = parseFloat(parts[iP]);
            if (lab != "" && !isNaN(v) && v > 0) {
                scaleLabels = Array.concat(scaleLabels, lab);
                scaleVals = Array.concat(scaleVals, v);
            }
        }
    }
}

// Reads the saved dish circle (size in mm, centre as a fraction of the photo) into dishWmm etc.
function loadDish(path) {
    if (!File.exists(path)) return;
    lines = split(File.openAsString(path), "\n");
    for (r = 0; r < lines.length; r++) {
        kv = split(lines[r], "=");
        if (kv.length == 2) {
            key = String.trim(kv[0]); v = parseFloat(kv[1]);
            if (!isNaN(v)) {
                if (key == "width_mm") dishWmm = v;
                if (key == "height_mm") dishHmm = v;
                if (key == "centre_x") dishCx = v;
                if (key == "centre_y") dishCy = v;
            }
        }
    }
    if (dishWmm <= 0 || dishHmm <= 0) { dishWmm = 0; dishHmm = 0; }
}

// Saves the Results table to path, after the earlier rows in prev (text of the old CSV).
// If the columns changed, the old file is left alone and the new rows go to a second file.
function saveResults(path, prev) {
    if (prev == "") { saveAs("Results", path); return; }
    tmp = getDirectory("temp") + "slime_mould_new_rows.csv";
    saveAs("Results", tmp);
    newLines = split(File.openAsString(tmp), "\n");
    oldLines = split(prev, "\n");
    if (newLines[0] != oldLines[0]) {
        alt = File.getParent(path) + File.separator + "results (continued).csv";
        File.copy(tmp, alt);
        print("Columns differ from " + path + " - new rows saved to " + alt + " instead.");
        return;
    }
    text = String.join(oldLines, "\n");
    num = oldLines.length - 1;
    for (r = 1; r < newLines.length; r++) {
        num++;
        text = text + "\n" + num + substring(newLines[r], indexOf(newLines[r], ","));
    }
    File.saveString(text + "\n", path);
}

// Saved pixels/mm for a plate label, or NaN if none.
function savedScale(lab) {
    for (q = 0; q < scaleLabels.length; q++)
        if (toLowerCase(scaleLabels[q]) == toLowerCase(lab)) return scaleVals[q];
    return NaN;
}

function cleanName(f) {
    s = substring(f, 0, lastIndexOf(f, "."));
    s = replace(s, "^\\s+|\\s+$", "");          // trim spaces
    s = replace(s, "\\s+", " ");
    s = replace(s, "(?i)^nacl", "NaCl");
    s = replace(s, "([A-Za-z])(\\d+)$", "$1 $2"); // "Glucose1" -> "Glucose 1"
    return s;
}

// Finds the food (strongly saturated yellow blob) and sets FX, FY (pixels).
function findFood(id, ow, oh) {
    setBatchMode(true);
    selectImage(id);
    run("Select None");
    run("Duplicate...", "title=tmp_f");
    run("Remove Overlay");
    run("HSB Stack");
    setSlice(1);
    run("Duplicate...", "title=tmp_fh");
    run("Macro...", "code=v=(v>=" + H1 + "&&v<=" + H2 + ")*255");
    selectWindow("tmp_f");
    setSlice(2);
    run("Duplicate...", "title=tmp_fs");
    run("Macro...", "code=v=(v>=130)*255");
    imageCalculator("AND create", "tmp_fh", "tmp_fs");
    rename("tmp_ff");
    run("Set Scale...", "distance=0 known=0 unit=pixel");
    setThreshold(255, 255);
    run("Create Selection");
    FX = ow / 2; FY = oh / 2;
    if (selectionType() != -1) {
        if (getValue("Area") > 0.002 * ow * oh) { FX = getValue("X"); FY = getValue("Y"); }
    }
    run("Select None");
    close("tmp_f*");
    setBatchMode(false);
    selectImage(id);
}

// Casts NRAYS rays from the food centre over a 0/255 mask and fits circles.
function circleFit(title, ppmm) {
    selectWindow(title);
    w = getWidth(); h = getHeight();
    rmax = sqrt(w * w + h * h);
    r = newArray(NRAYS);
    n = 0; sum = 0; mx = 0;
    Sx = 0; Sy = 0; Sxx = 0; Syy = 0; Sxy = 0; Sz = 0; Sxz = 0; Syz = 0; Szz = 0;
    for (k = 0; k < NRAYS; k++) {
        a = 2 * PI * k / NRAYS;
        ca = cos(a); sa = sin(a);
        last = 0;
        for (d = 0; d < rmax; d++) {
            x = FX + d * ca; y = FY + d * sa;
            if (x < 0 || y < 0 || x >= w || y >= h) d = rmax;
            else if (getPixel(floor(x), floor(y)) == 255) last = d;
        }
        r[k] = last / ppmm;               // mm
        sum += r[k];
        if (r[k] > mx) mx = r[k];
        if (r[k] > 0) {
            n++;
            xm = r[k] * ca; ym = r[k] * sa; z = xm * xm + ym * ym;   // mm, relative to food
            Sx += xm; Sy += ym; Sxx += xm * xm; Syy += ym * ym; Sxy += xm * ym;
            Sz += z; Sxz += xm * z; Syz += ym * z; Szz += z * z;
        }
    }
    // food-centred circle: radius = mean reach
    cfR = sum / NRAYS;
    ss = 0;
    for (k = 0; k < NRAYS; k++) ss += (r[k] - cfR) * (r[k] - cfR);
    cfRMS = sqrt(ss / NRAYS);
    if (cfR > 0) cfRel = cfRMS / cfR; else cfRel = NaN;
    cfMax = mx;
    cfDir = 100 * n / NRAYS;

    // best-fit circle (least squares, Kasa): x2 + y2 = A x + B y + C
    ffR = 0; ffRMS = NaN; ffR2 = NaN; ffOff = NaN; ffX = FX; ffY = FY;
    if (n >= 3) {
        D  = det3(Sxx, Sxy, Sx,  Sxy, Syy, Sy,  Sx, Sy, n);
        if (D != 0) {
            A = det3(Sxz, Sxy, Sx,  Syz, Syy, Sy,  Sz, Sy, n) / D;
            B = det3(Sxx, Sxz, Sx,  Sxy, Syz, Sy,  Sx, Sz, n) / D;
            C = det3(Sxx, Sxy, Sxz, Sxy, Syy, Syz, Sx, Sy, Sz) / D;
            cx = A / 2; cy = B / 2;
            ffR = sqrt(C + cx * cx + cy * cy);
            ffOff = sqrt(cx * cx + cy * cy);
            ffX = FX + cx * ppmm; ffY = FY + cy * ppmm;
            ssg = 0; ssr = 0; zmean = Sz / n; sst = 0;
            for (k = 0; k < NRAYS; k++) {
                if (r[k] > 0) {
                    a = 2 * PI * k / NRAYS;
                    xm = r[k] * cos(a); ym = r[k] * sin(a); z = xm * xm + ym * ym;
                    g = sqrt((xm - cx) * (xm - cx) + (ym - cy) * (ym - cy)) - ffR;
                    ssg += g * g;
                    e = z - (A * xm + B * ym + C);
                    ssr += e * e;
                    sst += (z - zmean) * (z - zmean);
                }
            }
            ffRMS = sqrt(ssg / n);
            if (sst > 0) ffR2 = 1 - ssr / sst;
        }
    }
}

function det3(a, b, c, d, e, f, g, h, i) {
    return a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g);
}
