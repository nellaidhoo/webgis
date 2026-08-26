import os
import math
import subprocess
import shutil
import sys


def find_gdal2tiles():
    """Resolve the gdal2tiles executable, trying common names/roots."""
    candidates = [
        "gdal2tiles.py",
        "gdal2tiles",
        os.path.join(sys.prefix, "Scripts", "gdal2tiles.py"),
        os.path.join(sys.prefix, "Scripts", "gdal2tiles"),
    ]
    for name in candidates:
        found = shutil.which(name)
        if found:
            return found
    return candidates[0]


def _gdal_cli_available():
    """True when the external GDAL command-line tools can be used."""
    return (
        shutil.which("gdaladdo") is not None
        and shutil.which("gdal_translate") is not None
        and shutil.which(find_gdal2tiles()) is not None
    )


def _tile_with_rasterio(tif_path, output_dir, min_zoom, max_zoom):
    """
    Pure-Python XYZ tiler used when the GDAL CLI tools are not installed.
    Produces {output_dir}/{z}/{x}/{y}.png compatible with Leaflet/MapLibre.
    """
    import numpy as np
    import rasterio
    from rasterio.warp import transform as warp_transform
    from rasterio.windows import Window
    from rasterio.enums import Resampling
    from PIL import Image

    def _pixel_to_lonlat(src_transform, col, row):
        xs, ys = rasterio.transform.xy(src_transform, row, col)
        return xs, ys

    def _lonlat_to_tile(lon, lat, zoom):
        n = 2 ** zoom
        xt = (lon + 180.0) / 360.0 * n
        lat_rad = math.radians(lat)
        yt = (1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n
        return xt, yt

    with rasterio.open(tif_path) as src:
        # Corner coordinates of the source raster in geographic terms
        rows, cols = src.height, src.width
        corners = [(0, 0), (0, cols), (rows, 0), (rows, cols)]
        lonlat = [
            warp_transform(src.crs, "EPSG:4326", *zip(*[
                _pixel_to_lonlat(src.transform, c, r) for c, r in corners
            ]))
        ]
        lons = lonlat[0][0]
        lats = lonlat[0][1]
        lon_min, lon_max = min(lons), max(lons)
        lat_min, lat_max = min(lats), max(lats)

        count = min(src.count, 3)
        band_idx = [src.read(band) for band in range(1, count + 1)]

        for zoom in range(min_zoom, max_zoom + 1):
            x0f, y1f = _lonlat_to_tile(lon_min, lat_max, zoom)
            x1f, y0f = _lonlat_to_tile(lon_max, lat_min, zoom)
            x0, x1 = int(math.floor(x0f)), int(math.floor(x1f))
            y0, y1 = int(math.floor(y0f)), int(math.floor(y1f))
            n = 2 ** zoom
            for tx in range(max(0, x0), min(n - 1, x1) + 1):
                for ty in range(max(0, y0), min(n - 1, y1) + 1):
                    # Tile bounds back to geographic coords
                    w_lon = tx / n * 360.0 - 180.0
                    e_lon = (tx + 1) / n * 360.0 - 180.0
                    n_lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * ty / n))))
                    s_lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (ty + 1) / n))))

                    # Geographic bounds -> source pixel window
                    src_w = warp_transform("EPSG:4326", src.crs,
                                           [w_lon, e_lon, e_lon, w_lon],
                                           [s_lat, s_lat, n_lat, n_lat])
                    px = [rasterio.transform.rowcol(src.transform, lon, lat)
                          for lon, lat in zip(src_w[0], src_w[1])]
                    r0 = max(0, min(min(p[0] for p in px), rows - 1))
                    r1 = max(0, min(max(p[0] for p in px), rows))
                    c0 = max(0, min(min(p[1] for p in px), cols - 1))
                    c1 = max(0, min(max(p[1] for p in px), cols))
                    if r1 <= r0 or c1 <= c0:
                        continue

                    height, width = 256, 256
                    channels = []
                    for band in band_idx:
                        window_band = band[r0:r1, c0:c1]
                        img = Image.fromarray(window_band.astype(np.uint8) if band.dtype == np.uint8 else window_band)
                        img = img.resize((width, height), Image.BILINEAR)
                        channels.append(np.asarray(img))

                    rgb = np.dstack(channels) if len(channels) == 3 else np.repeat(np.dstack(channels), 3, axis=2) if len(channels) == 1 else np.dstack([*channels, channels[0]])
                    if rgb.shape[2] < 4:
                        alpha = np.full((height, width, 1), 255, dtype=np.uint8)
                        rgb = np.concatenate([rgb[:, :, :3], alpha], axis=2)
                    rgba = rgb[:, :, :4]

                    tile_dir = os.path.join(output_dir, str(zoom), str(tx))
                    os.makedirs(tile_dir, exist_ok=True)
                    Image.fromarray(rgba, mode="RGBA").save(
                        os.path.join(tile_dir, f"{ty}.png"), format="PNG"
                    )


def process_orthophoto(tif_path, output_dir, min_zoom=15, max_zoom=21):
    """
    Ingests drone GeoTIFF and generates a directory of XYZ raster tiles.
    Uses the GDAL CLI toolchain (overviews -> COG -> gdal2tiles) when
    available; otherwise falls back to an internal rasterio-based tiler so
    the pipeline stays portable.

    Args:
        tif_path (str): Path to input GeoTIFF file.
        output_dir (str): Destination directory for generated tiles (/opt/webgis/tiles/<session_id>).
        min_zoom (int): Minimum zoom level.
        max_zoom (int): Maximum zoom level.
    """
    if not os.path.exists(tif_path):
        raise FileNotFoundError(f"Input imagery file not found: {tif_path}")

    if not _gdal_cli_available():
        print("GDAL CLI tools not found; using built-in rasterio XYZ tiler.")
        os.makedirs(output_dir, exist_ok=True)
        _tile_with_rasterio(tif_path, output_dir, min_zoom, max_zoom)
        print(f"Orthophoto tile pipeline completed successfully! Tiles exported to: {output_dir}")
        return

    # Prepare temp directory
    temp_dir = os.path.join(os.path.dirname(tif_path), "temp_cog")
    os.makedirs(temp_dir, exist_ok=True)

    cog_path = os.path.join(temp_dir, "ortho_cog.tif")

    try:
        # Step 1: Create Overviews (pyramids) on original imagery for COG rendering
        overviews_cmd = [
            "gdaladdo",
            "-r", "average",
            tif_path,
            "2", "4", "8", "16", "32", "64"
        ]
        print(f"Executing: {' '.join(overviews_cmd)}")
        subprocess.run(overviews_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        # Step 2: Convert to Cloud Optimized GeoTIFF (COG)
        # Using LZW compression to keep quality high and file size balanced
        cog_cmd = [
            "gdal_translate",
            tif_path,
            cog_path,
            "-co", "TILED=YES",
            "-co", "COPY_SRC_OVERVIEWS=YES",
            "-co", "COMPRESS=LZW"
        ]
        print(f"Executing: {' '.join(cog_cmd)}")
        subprocess.run(cog_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        # Step 3: Generate XYZ tile directory
        # --xyz: Leaflet/MapLibre standard format
        # -z: Zoom levels (e.g. 15-21 for high-res building-level accuracy)
        # -w: Web viewer standard format (none means just export files, no map html file needed)
        tiles_cmd = [
            find_gdal2tiles(),
            "--xyz",
            "-z", f"{min_zoom}-{max_zoom}",
            "-w", "none",
            cog_path,
            output_dir
        ]
        print(f"Executing: {' '.join(tiles_cmd)}")
        os.makedirs(output_dir, exist_ok=True)
        subprocess.run(tiles_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        print(f"Orthophoto tile pipeline completed successfully! Tiles exported to: {output_dir}")

    finally:
        # Clean up temporary files
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
