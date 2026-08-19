/*
 * ndtiff_index_to_tileconfig.ijm
 * ---------------------------------------------------------------------------
 * Converts an NDTiff "NDTiff.index" file (Micro-Manager / Micro-Magellan /
 * Pycro-Manager NDTiffStorage v2-v3) into a TileConfiguration.txt for the
 * Fiji "Grid/Collection stitching" plugin (Preibisch et al.).
 *
 * Workflow this is meant for:
 *   1. Open the NDTiff dataset in ImageJ/Fiji and
 *      File > Save As > Image Sequence...   ->  0000.tif, 0001.tif, ...
 *   2. Run this macro on the NDTiff.index of the same dataset.
 *   3. Plugins > Stitching > Grid/Collection stitching
 *        Type: "Positions from file"
 *        Order: "Defined by TileConfiguration"
 *        Directory: the image-sequence folder, Layout file: TileConfiguration.txt
 *
 * OVERLAP IS A PER-RUN INPUT
 *   The index stores grid indices only, never the overlap, so you must supply
 *   it. Enter it either as a percentage of the tile or as an absolute number
 *   of pixels (Micro-Magellan records it in pixels, as GridPixelOverlapX/Y in
 *   the acquisition summary metadata). X and Y are separate. Whatever you type
 *   is remembered and pre-filled the next time the macro runs, and the macro
 *   shows you the resulting step size and final mosaic dimensions for
 *   confirmation before it writes anything - so you can dial the number in
 *   without re-running.
 *
 * WHY THE FILENAME MAPPING WORKS
 *   Every record in the index is appended in acquisition order, and the pixel
 *   offsets are strictly increasing within each .tif file. So record N of the
 *   index == slice N of the stack == image N of the exported sequence. The
 *   macro walks the index in file order and emits one line per record.
 *
 * INDEX BINARY FORMAT (little-endian) - one record per image, no header:
 *   int32  keyLength
 *   char[] key                (JSON axes, e.g. {"column":0,"z":0,"row":3})
 *   int32  filenameLength
 *   char[] filename           (e.g. new_NDTiffStack.tif)
 *   int32  pixelOffset        (unsigned)
 *   int32  imageWidth
 *   int32  imageHeight
 *   int32  pixelType          (4 = 16-bit mono)
 *   int32  pixelCompression
 *   int32  metadataOffset     (unsigned)
 *   int32  metadataLength
 *   int32  metadataCompression
 *
 * LIMITATION
 *   Tile positions here are a regular grid reconstructed from row/column plus
 *   the overlap you enter. The true stage coordinates live in the per-image
 *   JSON metadata inside the .tif files; if you need those, use
 *   ndtiff_index_to_tileconfig.py --use-metadata instead.
 *
 * Author: generated for the vrushali tile-stitching project.
 */

var B;          // byte values of the index file, 0..255
var pos = 0;    // read cursor

// ---------------------------------------------------------------------------
// 0. Pick the index file
// ---------------------------------------------------------------------------
indexPath = File.openDialog("Select the NDTiff index file (NDTiff.index)");
if (indexPath == "") exit("No file selected.");
outDir = File.getDirectory(indexPath);

// ---------------------------------------------------------------------------
// 1. Slurp the file as exact bytes.
//    File.openAsRawString() mangles bytes >127, so import as an 8-bit raw
//    image of width = filesize, height = 1, and read the intensity profile.
// ---------------------------------------------------------------------------
nBytes = File.length(indexPath);
if (nBytes <= 0) exit("Index file is empty: " + indexPath);
setBatchMode(true);
run("Raw...", "open=[" + indexPath + "] image=[8-bit] width=" + nBytes + " height=1 number=1");
rawID = getImageID();
makeRectangle(0, 0, nBytes, 1);
B = getProfile();
selectImage(rawID);
close();
setBatchMode(false);

// ---------------------------------------------------------------------------
// 2. Parse every record
// ---------------------------------------------------------------------------
maxRecords = 200000;
cols  = newArray(maxRecords);
rows  = newArray(maxRecords);
zs    = newArray(maxRecords);
files = newArray(maxRecords);
n = 0;
tileW = 0; tileH = 0;

pos = 0;
while (pos < nBytes - 4) {
    keyLen = readInt();
    if (keyLen <= 0 || pos + keyLen > nBytes) break;      // truncated / corrupt
    key = readString(keyLen);
    fnLen = readInt();
    if (fnLen <= 0 || pos + fnLen > nBytes) break;
    fname = readString(fnLen);
    readInt();                 // pixelOffset
    w = readInt();             // imageWidth
    h = readInt();             // imageHeight
    readInt();                 // pixelType
    readInt();                 // pixelCompression
    readInt();                 // metadataOffset
    readInt();                 // metadataLength
    readInt();                 // metadataCompression

    cols[n]  = jsonInt(key, "column");
    rows[n]  = jsonInt(key, "row");
    zs[n]    = jsonInt(key, "z");
    files[n] = fname;
    if (w > tileW) tileW = w;
    if (h > tileH) tileH = h;
    n++;
    if (n >= maxRecords) break;
}
if (n == 0) exit("No records parsed - is this really an NDTiff.index?");

cols  = Array.trim(cols, n);
rows  = Array.trim(rows, n);
zs    = Array.trim(zs, n);
files = Array.trim(files, n);

Array.getStatistics(cols, colMin, colMax, dummy1, dummy2);
Array.getStatistics(rows, rowMin, rowMax, dummy1, dummy2);
Array.getStatistics(zs,   zMin,   zMax,   dummy1, dummy2);
nZ    = zMax - zMin + 1;
nCols = colMax - colMin + 1;
nRows = rowMax - rowMin + 1;

summary = n + " tiles    |    columns " + colMin + ".." + colMax + "  (" + nCols + ")"
        + "    rows " + rowMin + ".." + rowMax + "  (" + nRows + ")"
        + "    z " + zMin + ".." + zMax
        + "\ntile " + tileW + " x " + tileH + " px    |    "
        + nUnique(files) + " NDTiff data file(s)";
full = nCols * nRows * nZ;
if (n < full)
    summary = summary + "\nSPARSE acquisition: " + n + " of " + full
            + " grid slots are filled - a positions file is required, no grid preset will do.";

// ---------------------------------------------------------------------------
// 3. Settings dialog. Defaults come from the last run (ImageJ prefs), so a
//    dataset-specific overlap only has to be typed once per dataset.
// ---------------------------------------------------------------------------
PCT = "percent of tile (%)";
PX  = "pixels";

ovUnits  = prefGet("ndtiff.ovUnits", PCT);
ovX      = prefNum("ndtiff.ovX",     10);
ovY      = prefNum("ndtiff.ovY",     10);
prefix   = prefGet("ndtiff.prefix",  "");
digits   = prefNum("ndtiff.digits",  4);
first    = prefNum("ndtiff.first",   0);
ext      = prefGet("ndtiff.ext",     ".tif");
invX     = prefNum("ndtiff.invX",    0);
invY     = prefNum("ndtiff.invY",    0);
swapAx   = prefNum("ndtiff.swapAx",  0);
zStep    = prefNum("ndtiff.zStep",   1);
writeCsv = prefNum("ndtiff.csv",     1);
if (ovUnits != PCT && ovUnits != PX) ovUnits = PCT;

confirmed = false;
while (!confirmed) {

    Dialog.create("NDTiff index -> TileConfiguration");
    Dialog.addMessage(summary);

    Dialog.addMessage("---- tile size ----");
    Dialog.addNumber("Tile width:",  tileW, 0, 8, "px");
    Dialog.addNumber("Tile height:", tileH, 0, 8, "px");

    Dialog.addMessage("---- overlap (not stored in the index - enter it per dataset) ----");
    Dialog.addChoice("Overlap given in:", newArray(PCT, PX), ovUnits);
    Dialog.addNumber("Overlap X:", ovX, 3, 8, "");
    Dialog.addNumber("Overlap Y:", ovY, 3, 8, "");

    Dialog.addMessage("---- exported image-sequence naming ----");
    Dialog.addString("Filename prefix:", prefix);
    Dialog.addNumber("Number of digits:", digits, 0, 8, "");
    Dialog.addNumber("First index:", first, 0, 8, "");
    Dialog.addString("Extension:", ext);

    Dialog.addMessage("---- geometry ----");
    Dialog.addCheckbox("Invert X (column increases to the left)", invX);
    Dialog.addCheckbox("Invert Y (row increases upward)", invY);
    Dialog.addCheckbox("Swap row/column axes", swapAx);
    if (nZ > 1) Dialog.addNumber("Z step:", zStep, 3, 8, "px  (writes dim=3)");
    Dialog.addCheckbox("Also write tiles.csv (sequence index <-> row/column)", writeCsv);
    Dialog.show();

    tileW    = Dialog.getNumber();
    tileH    = Dialog.getNumber();
    ovX      = Dialog.getNumber();
    ovY      = Dialog.getNumber();
    digits   = round(Dialog.getNumber());
    first    = round(Dialog.getNumber());
    if (nZ > 1) zStep = Dialog.getNumber();
    prefix   = Dialog.getString();
    ext      = Dialog.getString();
    ovUnits  = Dialog.getChoice();
    invX     = Dialog.getCheckbox();
    invY     = Dialog.getCheckbox();
    swapAx   = Dialog.getCheckbox();
    writeCsv = Dialog.getCheckbox();

    // ---- resolve the overlap into a step, in pixels --------------------------
    if (ovUnits == PCT) {
        stepX = tileW * (1.0 - ovX / 100.0);
        stepY = tileH * (1.0 - ovY / 100.0);
        ovPxX = tileW - stepX;
        ovPxY = tileH - stepY;
    } else {
        ovPxX = ovX;
        ovPxY = ovY;
        stepX = tileW - ovPxX;
        stepY = tileH - ovPxY;
    }

    bad = "";
    if (tileW <= 0 || tileH <= 0)
        bad = "Tile size must be positive.";
    else if (stepX <= 0 || stepY <= 0)
        bad = "Overlap is >= the tile size, so tiles would not advance.\n"
            + "step = " + d2s(stepX, 1) + " x " + d2s(stepY, 1) + " px";
    else if (ovPxX < 0 || ovPxY < 0)
        bad = "Negative overlap - tiles would have gaps between them.\n"
            + "That is legal but almost certainly a typo. Use 0 if you really mean no overlap.";
    else if (digits < 1 || digits > 12)
        bad = "Number of digits must be between 1 and 12.";

    if (bad != "") {
        showMessage("Check the settings", bad);     // loop repeats, dialog reopens
    } else {
        // ---- show the consequences of that overlap, then confirm -------------
        mosaicW = (nCols - 1) * stepX + tileW;
        mosaicH = (nRows - 1) * stepY + tileH;
        bytes   = mosaicW * mosaicH * 2;            // assumes 16-bit

        check = "Overlap  X " + d2s(ovPxX, 1) + " px  (" + d2s(100 * ovPxX / tileW, 2) + " %)\n"
              + "         Y " + d2s(ovPxY, 1) + " px  (" + d2s(100 * ovPxY / tileH, 2) + " %)\n"
              + "\n"
              + "Step between tiles   " + d2s(stepX, 1) + " x " + d2s(stepY, 1) + " px\n"
              + "Fused mosaic         " + d2s(mosaicW, 0) + " x " + d2s(mosaicH, 0) + " px"
              + "   (~" + d2s(bytes / 1073741824, 2) + " GiB at 16-bit)\n"
              + "\n"
              + n + " lines, named " + prefix + IJ.pad(first, digits) + ext
              + " .. " + prefix + IJ.pad(first + n - 1, digits) + ext + "\n"
              + "\n"
              + "Write TileConfiguration.txt to\n" + outDir + " ?";

        confirmed = getBoolean(check, "Write it", "Change settings");
    }
}

// remember for next time
prefSet("ndtiff.ovUnits", ovUnits);
prefSet("ndtiff.ovX",     ovX);
prefSet("ndtiff.ovY",     ovY);
prefSet("ndtiff.prefix",  prefix);
prefSet("ndtiff.digits",  digits);
prefSet("ndtiff.first",   first);
prefSet("ndtiff.ext",     ext);
prefSet("ndtiff.invX",    invX);
prefSet("ndtiff.invY",    invY);
prefSet("ndtiff.swapAx",  swapAx);
prefSet("ndtiff.zStep",   zStep);
prefSet("ndtiff.csv",     writeCsv);

// ---------------------------------------------------------------------------
// 4. Write TileConfiguration.txt (and the verification CSV)
// ---------------------------------------------------------------------------
dim = 2;
if (nZ > 1) dim = 3;

tcPath  = outDir + "TileConfiguration.txt";
csvPath = outDir + "tiles.csv";
if (File.exists(tcPath)) File.delete(tcPath);
if (writeCsv && File.exists(csvPath)) File.delete(csvPath);

ftc = File.open(tcPath);
print(ftc, "# Define the number of dimensions we are working on");
print(ftc, "dim = " + dim);
print(ftc, "");
print(ftc, "# Define the image coordinates");

if (writeCsv) {
    fcsv = File.open(csvPath);
    print(fcsv, "seq_index,filename,ndtiff_file,column,row,z,x_px,y_px");
}

for (i = 0; i < n; i++) {
    c = cols[i] - colMin;
    r = rows[i] - rowMin;
    if (swapAx) { t = c; c = r; r = t; }
    x = c * stepX;
    y = r * stepY;
    if (invX) x = (nCols - 1) * stepX - x;
    if (invY) y = (nRows - 1) * stepY - y;

    name = prefix + IJ.pad(first + i, digits) + ext;

    if (dim == 3) {
        z = (zs[i] - zMin) * zStep;
        print(ftc, name + "; ; (" + d2s(x, 3) + ", " + d2s(y, 3) + ", " + d2s(z, 3) + ")");
    } else {
        print(ftc, name + "; ; (" + d2s(x, 3) + ", " + d2s(y, 3) + ")");
    }

    if (writeCsv)
        print(fcsv, i + "," + name + "," + files[i] + "," + cols[i] + "," + rows[i]
                  + "," + zs[i] + "," + d2s(x, 3) + "," + d2s(y, 3));
}

File.close(ftc);
if (writeCsv) File.close(fcsv);

// ---------------------------------------------------------------------------
// 5. Report
// ---------------------------------------------------------------------------
print("\\Clear");
print("NDTiff index -> TileConfiguration");
print("  source     : " + indexPath);
print("  tiles      : " + n + " of " + full + " grid slots");
print("  tile size  : " + tileW + " x " + tileH + " px");
print("  overlap    : X " + d2s(ovPxX, 1) + " px / " + d2s(100 * ovPxX / tileW, 2) + " %"
                 + "   Y " + d2s(ovPxY, 1) + " px / " + d2s(100 * ovPxY / tileH, 2) + " %");
print("  step       : " + d2s(stepX, 1) + " x " + d2s(stepY, 1) + " px");
print("  mosaic     : " + d2s(mosaicW, 0) + " x " + d2s(mosaicH, 0) + " px");
print("  names      : " + prefix + IJ.pad(first, digits) + ext
                 + " .. " + prefix + IJ.pad(first + n - 1, digits) + ext);
print("  wrote      : " + tcPath);
if (writeCsv) print("  wrote      : " + csvPath);
print("");
print("Next: Plugins > Stitching > Grid/Collection stitching");
print("      Type  = 'Positions from file'");
print("      Order = 'Defined by TileConfiguration'");
print("      Point Directory at the image-sequence folder and tick 'Compute overlap'");
print("      so it can refine these nominal positions by cross-correlation.");

// ---------------------------------------------------------------------------
// helpers
// ---------------------------------------------------------------------------

// little-endian int32 (returned unsigned; the lengths we use are always small)
function readInt() {
    v = B[pos] + B[pos + 1] * 256 + B[pos + 2] * 65536 + B[pos + 3] * 16777216;
    pos = pos + 4;
    return v;
}

function readString(len) {
    s = "";
    for (k = 0; k < len; k++) s = s + fromCharCode(B[pos + k]);
    pos = pos + len;
    return s;
}

// pull an integer out of a flat JSON object: {"column":0,"z":0,"row":3}
function jsonInt(json, field) {
    tag = "\"" + field + "\"";
    p = indexOf(json, tag);
    if (p < 0) return 0;
    p = indexOf(json, ":", p);
    if (p < 0) return 0;
    p++;
    num = "";
    done = false;
    while (p < lengthOf(json) && !done) {
        ch = substring(json, p, p + 1);
        if (ch == " ")
            p++;
        else if (ch == "-" || indexOf("0123456789", ch) >= 0) {
            num = num + ch;
            p++;
        } else
            done = true;
    }
    if (num == "" || num == "-") return 0;
    return parseInt(num);
}

// NDTiff appends to one data file until it nears the 4 GB TIFF limit, then rolls
// over and never returns to it - so distinct names == run transitions + 1.
function nUnique(arr) {
    c = 1;
    for (i = 1; i < lengthOf(arr); i++)
        if (arr[i] != arr[i - 1]) c++;
    return c;
}

// ---- persisted settings ---------------------------------------------------
function prefGet(key, def) {
    return call("ij.Prefs.get", key, def);
}

function prefSet(key, val) {
    call("ij.Prefs.set", key, "" + val);
}

function prefNum(key, def) {
    v = parseFloat(call("ij.Prefs.get", key, "" + def));
    if (isNaN(v)) return def;
    return v;
}
