"""Rebuild data/oil_tanks/cushing_tank_shadows.csv from the free Sentinel-2 archive on AWS.

One-off research script, not part of the daily run. Needs: pip install rasterio scipy pyproj.
No keys: the sentinel-cogs bucket is public. About a minute and ~1 GB of range requests.

Steps:
1. List every Sentinel-2 L2A scene on tile 14SQE (Cushing sits near its western edge) and keep
   those whose footprint covers the tank farm and whose tile cloud is under 70%.
2. Read a small window (red, NIR, blue, scene classification) over the farm.
3. Keep scenes with <0.5% cloud, cloud shadow or no-data and no snow inside the window.
4. Find tanks once: bright, roughly round blobs of 12-200 pixels in the median red band of the
   high-sun (summer) scenes, ignoring the town to the north.
5. Per scene and tank: share of pixels (tank grown by one pixel) darker than 45% of that tank's
   summer brightness. That is the shadow share the study models.

EIA Cushing stocks (data/oil_tanks/cushing_weekly.csv) were copied from
https://www.eia.gov/dnav/pet/hist/LeafHandler.ashx?n=PET&s=W_EPC0_SAX_YCUOK_MBBL&f=W
"""
import concurrent.futures as cf
import os
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import requests

BUCKET = "https://sentinel-cogs.s3.us-west-2.amazonaws.com/"
PREFIX = "sentinel-s2-l2a-cogs/14/S/QE/"
BOUNDS = (-96.79, 35.905, -96.705, 35.985)  # lon/lat box over the Cushing tank farm
CACHE = Path(os.environ.get("OIL_TANK_CACHE", "/tmp/oil_tank_windows"))
OUT = Path("data/oil_tanks/cushing_tank_shadows.csv")
BAD_SCL = [0, 1, 3, 8, 9, 10]  # no data, saturated, cloud shadow, cloud (med, high), cirrus
SNOW_SCL = 11
TOWN_ROWS = 240  # window rows north of this are Cushing town, not tank farm


def list_scenes(first=2017, last=2026):
    def month(ym):
        y, m = ym
        r = requests.get(BUCKET, params={"list-type": "2", "prefix": f"{PREFIX}{y}/{m}/", "delimiter": "/"}, timeout=60)
        return re.findall(r"<Prefix>[^<]*/(S2[^<]*)/</Prefix>", r.text)
    with cf.ThreadPoolExecutor(16) as ex:
        return sorted(s for chunk in ex.map(month, [(y, m) for y in range(first, last + 1) for m in range(1, 13)]) for s in chunk)


def scene_url(s):
    d = s.split("_")[2]
    return f"{BUCKET}{PREFIX}{d[:4]}/{int(d[4:6])}/{s}/"


def scene_meta(s):
    try:
        p = requests.get(scene_url(s) + s + ".json", timeout=60).json()
        return dict(scene=s, west=p["bbox"][0], cloud=p["properties"]["eo:cloud_cover"],
                    sun_el=p["properties"]["view:sun_elevation"])
    except Exception:
        return None


def read_window(s):
    import rasterio
    from pyproj import Transformer
    from rasterio.enums import Resampling
    from rasterio.windows import from_bounds
    out = CACHE / f"{s}.npz"
    if out.exists():
        return out
    t = Transformer.from_crs(4326, 32614, always_xy=True)
    x0, y0 = t.transform(BOUNDS[0], BOUNDS[1])
    x1, y1 = t.transform(BOUNDS[2], BOUNDS[3])
    arr = {}
    for band in ("B04", "B08", "B02", "SCL"):
        with rasterio.open("/vsicurl/" + scene_url(s) + band + ".tif") as src:
            w = from_bounds(x0, y0, x1, y1, src.transform).round_offsets().round_lengths()
            shape = arr["B04"].shape if band == "SCL" else None
            arr[band] = src.read(1, window=w, out_shape=shape, resampling=Resampling.nearest)
    np.savez_compressed(out, **arr)
    return out


def find_tanks(summer_median, threshold=3000):
    from scipy import ndimage as ndi
    m = ndi.binary_opening(summer_median > threshold, iterations=1)
    lab, n = ndi.label(m)
    keep = np.zeros(n + 1, bool)
    for i, sl in enumerate(ndi.find_objects(lab), 1):
        area = (lab[sl] == i).sum()
        h, w = sl[0].stop - sl[0].start, sl[1].stop - sl[1].start
        if 12 <= area <= 200 and 0.5 <= h / w <= 2 and area / (h * w) > 0.55 and sl[0].start > TOWN_ROWS:
            keep[i] = True
    lab, _ = ndi.label(keep[lab])
    return lab


def main():
    from scipy import ndimage as ndi
    os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
    CACHE.mkdir(parents=True, exist_ok=True)
    scenes = list_scenes()
    with cf.ThreadPoolExecutor(32) as ex:
        meta = pd.DataFrame([m for m in ex.map(scene_meta, scenes) if m])
    meta["date"] = meta.scene.str[10:18]
    meta = meta[(meta.west < -96.79) & (meta.cloud < 70)].sort_values("scene").drop_duplicates("date", keep="last")
    with cf.ThreadPoolExecutor(24) as ex:
        list(ex.map(read_window, meta.scene))
    clear = []
    for _, r in meta.iterrows():
        scl = np.load(CACHE / f"{r.scene}.npz")["SCL"]
        if np.isin(scl, BAD_SCL).mean() < 0.005 and (scl == SNOW_SCL).mean() < 0.001:
            clear.append(r)
    clear = pd.DataFrame(clear)
    summer = clear[clear.sun_el > 62].scene
    median = np.median(np.stack([np.load(CACHE / f"{s}.npz")["B04"] for s in summer]).astype(float), 0)
    lab = find_tanks(median)
    ids = range(1, lab.max() + 1)
    px = {i: np.where(ndi.binary_dilation(lab == i, iterations=1)) for i in ids}
    ref = {i: median[lab == i].mean() for i in ids}
    rows = []
    for _, r in clear.iterrows():
        b = np.load(CACHE / f"{r.scene}.npz")["B04"].astype(float)
        rows.append({"scene": r.scene, "date": r.date, "sun_el": r.sun_el,
                     **{f"t{i}": round(float((b[px[i]] < 0.45 * ref[i]).mean()), 4) for i in ids}})
    pd.DataFrame(rows).to_csv(OUT, index=False)
    print(f"{len(rows)} clear scenes, {lab.max()} tanks -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
