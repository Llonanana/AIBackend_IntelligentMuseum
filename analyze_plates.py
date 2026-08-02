"""
One-off analysis script: derives ground-truth gap angles for the real pseudo-isochromatic
plate images (from 學姊's Google Drive folders, based on Wenzel & Samu 2012's methodology)
by detecting the two hue clusters (background vs Landolt-C) and finding the angular gap in
the ring, since no answer-key file came with the images.

Confidence is hue-separation between the two clusters — plates where the difference has
been designed to be nearly imperceptible (highest difficulty) don't cluster reliably and
are excluded rather than guessed at, per instruction: don't include ones where the
difference is too small to trust.

Series -> QR type mapping (per ColorVisionQRScanner.cs's A/B/C/D format):
  R-G  : general red-green deficiency detector (severity only, not type)
  P    : protan confusion line  -> contributes to B (Protanomalous)
  D    : deutan confusion line  -> contributes to C (Deuteranomalous)
         (NOT tritan - the paper's "D series" = deutan, a false-friend against the QR
         format's D=Tritanomalous. Tri-10 is a separate, non-paper source for D=Tritanomalous.)
  Tri  : tritan (blue-yellow)   -> contributes to D (Tritanomalous)
"""
import io
import json
import os
import shutil

import numpy as np
from PIL import Image
import matplotlib.colors as mcolors

BASE = r"C:\Unity_Safe\UnityMR\丟給AI看"
FOLDERS = {
    "RG": os.path.join(BASE, "RG14-20260802T094510Z-1-001", "RG14"),
    "P":  os.path.join(BASE, "P9-20260802T094508Z-1-001", "P9"),
    "D":  os.path.join(BASE, "D9-20260802T094503Z-1-001", "D9"),
    "Tri": os.path.join(BASE, "Tri-10-20260802T094512Z-1-001", "Tri-10"),
}
OUT_DIR = r"C:\Unity_Safe\AIBackend_IntelligentMuseum\plates"
MIN_HUE_SEPARATION = 20.0  # below this, treat the plate as "too subtle to trust" and drop it

# The automatic confidence heuristics above kept producing false positives (confidently
# "detecting" a gap in plates that have no real signal at all — visually confirmed on a
# rendered grid of every plate in order). Gating on these human-verified minimum codes is
# the trustworthy cutoff; the hue-separation/bimodality checks above still run as a second
# safety net on top, but code cutoff is what actually decides inclusion now.
MIN_CODE = {"RG": 160, "P": 140, "D": 100, "Tri": 1}  # Tri filenames are T01..T10, not coded
MAX_CODE = {"Tri": 3}  # Tri numbering runs the opposite direction (T01 = easiest, unlike RG/P/D)

DIRECTIONS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


def analyze(path):
    img = Image.open(path).convert("RGB")
    arr = np.array(img).astype(float) / 255.0
    h, w, _ = arr.shape
    cx, cy = w / 2, h / 2
    mask = arr.sum(axis=2) < 2.8
    hsv = mcolors.rgb_to_hsv(arr)
    hue = hsv[:, :, 0] * 360
    sat = hsv[:, :, 1]
    dotpix = mask & (sat > 0.05)
    if dotpix.sum() < 1000:
        return None

    ys, xs = np.mgrid[0:h, 0:w]
    hues = hue[dotpix]
    xs_d, ys_d = xs[dotpix], ys[dotpix]

    h_folded = np.where(hues > 180, hues - 360, hues)
    c1, c2 = np.percentile(h_folded, 10), np.percentile(h_folded, 90)
    for _ in range(20):
        d1, d2 = np.abs(h_folded - c1), np.abs(h_folded - c2)
        g1 = d1 < d2
        if g1.sum() == 0 or (~g1).sum() == 0:
            return None
        c1, c2 = h_folded[g1].mean(), h_folded[~g1].mean()
    sep = abs(c1 - c2)
    if sep < MIN_HUE_SEPARATION:
        return None
    # A percentile split of a single unimodal hue cloud (e.g. an all-green plate where the
    # "difference" has become imperceptible) still reports some c1/c2 separation just from
    # spread, without the two groups actually being tight, distinct colors — reject unless
    # BOTH sides are themselves tightly clustered (low internal std), which only genuine
    # two-colour plates have.
    # Paper: each region (background / Landolt-C) is drawn from 3 shades of the same hue,
    # so genuine clusters aren't perfectly tight either — just tighter than a false split
    # of one continuous colour cloud (which is what produced an earlier false positive here).
    std1, std2 = h_folded[g1].std(), h_folded[~g1].std()
    if std1 > 20 or std2 > 20:
        return None
    # Bimodality check: a real two-colour plate has a sparse VALLEY between the two peaks;
    # a false split of one continuous colour cloud (e.g. a plate whose difference has become
    # imperceptible) has no such valley — density at the midpoint stays high. This is what
    # actually catches the near-imperceptible/hardest plates, not the std check above.
    mid = (c1 + c2) / 2
    band = 6  # degrees either side of the midpoint and of each peak, for density comparison
    valley_density = np.sum(np.abs(h_folded - mid) < band)
    peak_density = max(np.sum(np.abs(h_folded - c1) < band), np.sum(np.abs(h_folded - c2) < band))
    if peak_density == 0 or valley_density > peak_density * 0.25:
        return None

    n1, n2 = g1.sum(), (~g1).sum()
    target_grp = g1 if n1 < n2 else ~g1
    tx, ty = xs_d[target_grp], ys_d[target_grp]
    ang = (450 - np.degrees(np.arctan2(-(ty - cy), tx - cx))) % 360

    dist = np.sqrt((tx - cx) ** 2 + (ty - cy) ** 2) / (min(w, h) / 2)
    ring_band = (dist > 0.25) & (dist < 0.9)
    ang_ring = ang[ring_band]
    if len(ang_ring) < 200:
        return None
    histo, _ = np.histogram(ang_ring, bins=36, range=(0, 360))
    if histo.max() < 300 or histo.min() > histo.max() * 0.15:
        return None  # no clean gap — background/ring not confidently separable

    gap_bin = int(np.argmin(histo))
    gap_angle = gap_bin * 10 + 5
    direction = DIRECTIONS[round(gap_angle / 45) % 8]
    return {"gapAngleDeg": gap_angle, "direction": direction, "hueSeparation": round(sep, 1)}


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    manifest = {"RG": [], "P": [], "D": [], "Tri": []}
    kept, dropped = 0, 0

    for series, folder in FOLDERS.items():
        if not os.path.isdir(folder):
            print(f"[skip] {series}: folder not found: {folder}")
            continue
        for fname in sorted(os.listdir(folder)):
            if not fname.lower().endswith((".jpg", ".jpeg", ".png")):
                continue
            digits = "".join(c for c in fname.split("_")[0] if c.isdigit())
            code = int(digits) if digits else None
            if code is None or code < MIN_CODE[series]:
                dropped += 1
                continue
            if series in MAX_CODE and code > MAX_CODE[series]:
                dropped += 1
                continue

            path = os.path.join(folder, fname)
            result = analyze(path)
            if result is None:
                dropped += 1
                continue
            kept += 1
            out_name = f"{series}_{fname}"
            shutil.copyfile(path, os.path.join(OUT_DIR, out_name))
            manifest[series].append({
                "file": out_name,
                "code": code,
                **result,
            })

    for series in manifest:
        manifest[series].sort(key=lambda p: p["code"] if p["code"] is not None else 0)

    with io.open(os.path.join(OUT_DIR, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(f"kept={kept} dropped(too-subtle-or-unreadable)={dropped}")
    for series, items in manifest.items():
        print(f"  {series}: {len(items)} usable plates, codes = {[p['code'] for p in items]}")


if __name__ == "__main__":
    main()
