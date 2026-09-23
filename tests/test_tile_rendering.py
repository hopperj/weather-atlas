from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_bounds
from weather_tiles.rendering import (
    TileRenderingError,
    build_colormap,
    render_registered_tile,
    resolve_asset_path,
)

PALETTE = {
    "interpolation": "linear",
    "stops": [
        {"value": -40, "color": "#32215f"},
        {"value": 0, "color": "#45c7bf"},
        {"value": 40, "color": "#a51437"},
    ],
}


def test_asset_path_cannot_escape_data_root(tmp_path: Path) -> None:
    with pytest.raises(TileRenderingError):
        resolve_asset_path(tmp_path, "../secret.tif")


def test_palette_interpolates_an_rgba_table() -> None:
    colormap = build_colormap(PALETTE)

    assert len(colormap) == 256
    assert colormap[0] == (50, 33, 95, 255)
    assert colormap[255] == (165, 20, 55, 255)


def test_render_registered_tile_returns_a_png(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    raster_path = data_root / "processed" / "fixture.tif"
    raster_path.parent.mkdir(parents=True)
    values = np.linspace(-40, 40, 64 * 64, dtype="float32").reshape((64, 64))
    with rasterio.open(
        raster_path,
        "w",
        driver="GTiff",
        width=64,
        height=64,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_bounds(-180, -85, 180, 85, 64, 64),
        tiled=True,
        blockxsize=32,
        blockysize=32,
        nodata=-9999,
    ) as dataset:
        dataset.write(values, 1)

    tile = render_registered_tile(
        resolve_asset_path(data_root, "processed/fixture.tif"),
        x=0,
        y=0,
        z=0,
        display_min=-40,
        display_max=40,
        opacity_cutoff=None,
        palette_definition=PALETTE,
        image_format="png",
        resampling_method="bilinear",
    )

    assert tile.startswith(b"\x89PNG")


def test_render_registered_tile_masks_values_below_opacity_cutoff(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    raster_path = data_root / "processed" / "cutoff.tif"
    raster_path.parent.mkdir(parents=True)
    values = np.linspace(0, 100, 64 * 64, dtype="float32").reshape((64, 64))
    with rasterio.open(
        raster_path,
        "w",
        driver="GTiff",
        width=64,
        height=64,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_bounds(-180, -85, 180, 85, 64, 64),
        tiled=True,
        blockxsize=32,
        blockysize=32,
        nodata=-9999,
    ) as dataset:
        dataset.write(values, 1)

    tile = render_registered_tile(
        resolve_asset_path(data_root, "processed/cutoff.tif"),
        x=0,
        y=0,
        z=0,
        display_min=0,
        display_max=100,
        opacity_cutoff=20,
        palette_definition=PALETTE,
        image_format="png",
        resampling_method="bilinear",
    )

    with rasterio.MemoryFile(tile) as memory_file, memory_file.open() as dataset:
        alpha = dataset.read(4)

    assert alpha.min() == 0
    assert alpha.max() == 255
    assert 0 < np.count_nonzero(alpha == 0) < alpha.size
