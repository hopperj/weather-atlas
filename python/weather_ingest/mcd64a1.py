"""Independent MCD64A1 burned-area observations for frozen smoke events."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter, deque
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import yaml
from pyhdf.SD import SD, SDC
from pyproj import Geod

GRANULE_PATTERN = re.compile(
    r"^(?P<product>MCD64A1|VNP64A1)\.A(?P<year>\d{4})(?P<doy>\d{3})\."
    r"h(?P<horizontal>\d{2})v(?P<vertical>\d{2})\."
    r"(?P<collection>\d{3})\.\d+\.hdf$"
)
UPPER_LEFT_PATTERN = re.compile(
    r"UpperLeftPointMtrs=\((?P<x>-?\d+(?:\.\d+)?),(?P<y>-?\d+(?:\.\d+)?)\)"
)
REQUIRED_DATASETS = {
    "Burn Date",
    "Burn Date Uncertainty",
    "QA",
    "First Day",
    "Last Day",
}
BurnOccurrenceKey = tuple[int, int, date]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _date_from_ordinal(year: int, ordinal: int) -> date:
    if not 1 <= ordinal <= (366 if _is_leap_year(year) else 365):
        raise ValueError(f"invalid ordinal day {ordinal} for {year}")
    return date(year, 1, 1) + timedelta(days=ordinal - 1)


def _is_leap_year(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


@dataclass(frozen=True, slots=True)
class MCD64AreaConfig:
    operator_version: str
    product: str
    collection: str
    sphere_radius_m: float
    global_upper_left_x_m: float
    global_upper_left_y_m: float
    tile_pixels: int
    pixel_size_m: float
    connectivity: int
    seed_radius_m: float
    event_time_padding_days: int
    use_burn_date_uncertainty: bool
    overlapping_pixel_policy: str
    cross_month_duplicate_policy: str
    minimum_assigned_pixel_count: int
    require_at_least_one_high_confidence_pixel: bool

    @classmethod
    def from_yaml(cls, path: Path) -> MCD64AreaConfig:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("schema_version") != 1:
            raise ValueError("unsupported MCD64A1 area configuration")
        grid = payload["grid"]
        matching = payload["matching"]
        eligibility = payload["eligibility"]
        quality = payload["quality"]
        required_true = (
            "require_land_bit",
            "require_valid_data_bit",
            "require_burn_date_in_reliable_window",
        )
        if not all(quality.get(name) is True for name in required_true):
            raise ValueError("MCD64A1 central QA requirements may not be disabled")
        if quality.get("include_shortened_mapping_period") is not True:
            raise ValueError("unsupported shortened-mapping central policy")
        if quality.get("include_contextually_relabeled") is not True:
            raise ValueError("unsupported contextual-relabelling central policy")
        if quality.get("high_confidence_excludes_shortened_mapping_period") is not True:
            raise ValueError("unsupported shortened-mapping sensitivity policy")
        if quality.get("high_confidence_excludes_contextually_relabeled") is not True:
            raise ValueError("unsupported contextual-relabelling sensitivity policy")
        if grid["connectivity"] != 8:
            raise ValueError("only eight-connected scar growth is supported")
        if matching["overlapping_pixel_policy"] != "exclude_from_all_events":
            raise ValueError("unsupported overlapping-pixel policy")
        supported_duplicate_policies = {
            "require_identical_then_deduplicate",
            "retain_distinct_burn_dates_deduplicate_identical_occurrences",
        }
        if matching["cross_month_duplicate_policy"] not in supported_duplicate_policies:
            raise ValueError("unsupported cross-month duplicate policy")
        return cls(
            operator_version=str(payload["operator_version"]),
            product=str(payload["product"]),
            collection=str(payload["collection"]),
            sphere_radius_m=float(grid["sphere_radius_m"]),
            global_upper_left_x_m=float(grid["global_upper_left_x_m"]),
            global_upper_left_y_m=float(grid["global_upper_left_y_m"]),
            tile_pixels=int(grid["tile_pixels"]),
            pixel_size_m=float(grid["pixel_size_m"]),
            connectivity=int(grid["connectivity"]),
            seed_radius_m=float(matching["seed_radius_m"]),
            event_time_padding_days=int(matching["event_time_padding_days"]),
            use_burn_date_uncertainty=bool(matching["use_burn_date_uncertainty"]),
            overlapping_pixel_policy=str(matching["overlapping_pixel_policy"]),
            cross_month_duplicate_policy=str(matching["cross_month_duplicate_policy"]),
            minimum_assigned_pixel_count=int(eligibility["minimum_assigned_pixel_count"]),
            require_at_least_one_high_confidence_pixel=bool(
                eligibility["require_at_least_one_high_confidence_pixel"]
            ),
        )

    @property
    def pixel_area_hectares(self) -> float:
        return self.pixel_size_m**2 * 0.0001

    @property
    def tile_width_m(self) -> float:
        return self.tile_pixels * self.pixel_size_m


@dataclass(frozen=True, slots=True)
class BurnPixel:
    global_row: int
    global_column: int
    burn_date: date
    uncertainty_days: int
    qa: int
    first_reliable_day: int
    last_reliable_day: int
    granule_names: tuple[str, ...]

    @property
    def coordinate(self) -> tuple[int, int]:
        return self.global_row, self.global_column

    @property
    def occurrence(self) -> BurnOccurrenceKey:
        return self.global_row, self.global_column, self.burn_date

    @property
    def shortened_mapping_period(self) -> bool:
        return bool(self.qa & (1 << 2))

    @property
    def contextually_relabeled(self) -> bool:
        return bool(self.qa & (1 << 3))

    @property
    def high_confidence(self) -> bool:
        return not self.shortened_mapping_period and not self.contextually_relabeled


@dataclass(frozen=True, slots=True)
class FrozenEvent:
    event_id: str
    first_date: date
    last_date: date
    detections: tuple[tuple[float, float, date], ...]
    payload: dict[str, Any]


def _parse_granule(path: Path) -> tuple[str, str, int, int, int, int]:
    match = GRANULE_PATTERN.fullmatch(path.name)
    if match is None:
        raise ValueError(f"unexpected burned-area granule name: {path.name}")
    return (
        str(match.group("product")),
        str(match.group("collection")),
        int(match.group("year")),
        int(match.group("doy")),
        int(match.group("horizontal")),
        int(match.group("vertical")),
    )


def _read_dataset(hdf: SD, name: str, expected_shape: tuple[int, int]) -> np.ndarray:
    dataset = hdf.select(name)
    try:
        _, rank, dimensions, _, _ = dataset.info()
        if rank != 2 or tuple(dimensions) != expected_shape:
            raise ValueError(f"{name} has unexpected dimensions {dimensions}")
        return np.asarray(dataset[:])
    finally:
        dataset.endaccess()


def _validate_grid_metadata(
    attributes: dict[str, Any],
    *,
    horizontal: int,
    vertical: int,
    config: MCD64AreaConfig,
) -> None:
    metadata = str(attributes.get("StructMetadata.0", ""))
    if "Projection=GCTP_SNSOID" not in metadata:
        raise ValueError("MCD64A1 granule is not on the MODIS sinusoidal grid")
    if f"XDim={config.tile_pixels}" not in metadata or f"YDim={config.tile_pixels}" not in metadata:
        raise ValueError("MCD64A1 grid dimensions do not match configuration")
    match = UPPER_LEFT_PATTERN.search(metadata)
    if match is None:
        raise ValueError("MCD64A1 grid metadata lacks its upper-left coordinate")
    actual_x = float(match.group("x"))
    actual_y = float(match.group("y"))
    expected_x = config.global_upper_left_x_m + horizontal * config.tile_width_m
    expected_y = config.global_upper_left_y_m - vertical * config.tile_width_m
    if not math.isclose(actual_x, expected_x, abs_tol=0.01):
        raise ValueError(f"MCD64A1 tile x origin differs: {actual_x} != {expected_x}")
    if not math.isclose(actual_y, expected_y, abs_tol=0.01):
        raise ValueError(f"MCD64A1 tile y origin differs: {actual_y} != {expected_y}")


def _load_granule_pixels(
    path: Path,
    *,
    start: date,
    end: date,
    config: MCD64AreaConfig,
) -> tuple[list[BurnPixel], dict[str, int]]:
    product, collection, year, _, horizontal, vertical = _parse_granule(path)
    if product != config.product or collection != config.collection:
        raise ValueError(
            f"granule product/collection differs: {product}.{collection} "
            f"!= {config.product}.{config.collection}"
        )
    if year != start.year or year != end.year:
        raise ValueError("cross-year MCD64A1 experiments are not yet supported")
    hdf = SD(path.as_posix(), SDC.READ)
    try:
        datasets = set(hdf.datasets())
        if datasets != REQUIRED_DATASETS:
            raise ValueError(
                f"{path.name} has unexpected datasets: "
                f"missing={sorted(REQUIRED_DATASETS - datasets)}, "
                f"extra={sorted(datasets - REQUIRED_DATASETS)}"
            )
        _validate_grid_metadata(
            hdf.attributes(),
            horizontal=horizontal,
            vertical=vertical,
            config=config,
        )
        shape = (config.tile_pixels, config.tile_pixels)
        burn_date = _read_dataset(hdf, "Burn Date", shape).astype(np.int16, copy=False)
        uncertainty = _read_dataset(hdf, "Burn Date Uncertainty", shape).astype(
            np.uint8, copy=False
        )
        qa = _read_dataset(hdf, "QA", shape).astype(np.uint8, copy=False)
        first_day = _read_dataset(hdf, "First Day", shape).astype(np.int16, copy=False)
        last_day = _read_dataset(hdf, "Last Day", shape).astype(np.int16, copy=False)
    finally:
        hdf.end()

    start_ordinal = start.timetuple().tm_yday
    end_ordinal = end.timetuple().tm_yday
    in_interval = (burn_date >= start_ordinal) & (burn_date <= end_ordinal)
    land = (qa & 1) != 0
    valid = (qa & 2) != 0
    reliable = (first_day <= burn_date) & (burn_date <= last_day)
    accepted = in_interval & land & valid & reliable
    counts = {
        "reported_burn_pixels_in_interval": int(np.count_nonzero(in_interval)),
        "excluded_water_pixels": int(np.count_nonzero(in_interval & ~land)),
        "excluded_invalid_data_pixels": int(np.count_nonzero(in_interval & land & ~valid)),
        "excluded_outside_reliable_window_pixels": int(
            np.count_nonzero(in_interval & land & valid & ~reliable)
        ),
        "accepted_pixels": int(np.count_nonzero(accepted)),
        "accepted_shortened_mapping_pixels": int(
            np.count_nonzero(accepted & ((qa & (1 << 2)) != 0))
        ),
        "accepted_contextually_relabeled_pixels": int(
            np.count_nonzero(accepted & ((qa & (1 << 3)) != 0))
        ),
    }
    pixels: list[BurnPixel] = []
    for local_row, local_column in np.argwhere(accepted):
        ordinal = int(burn_date[local_row, local_column])
        pixels.append(
            BurnPixel(
                global_row=vertical * config.tile_pixels + int(local_row),
                global_column=horizontal * config.tile_pixels + int(local_column),
                burn_date=_date_from_ordinal(year, ordinal),
                uncertainty_days=(
                    int(uncertainty[local_row, local_column])
                    if config.use_burn_date_uncertainty
                    else 0
                ),
                qa=int(qa[local_row, local_column]),
                first_reliable_day=int(first_day[local_row, local_column]),
                last_reliable_day=int(last_day[local_row, local_column]),
                granule_names=(path.name,),
            )
        )
    return pixels, counts


def _cmr_granule_paths(
    root: Path,
    cmr_path: Path,
    config: MCD64AreaConfig,
) -> list[Path]:
    payload = json.loads(cmr_path.read_text(encoding="utf-8"))
    feed = payload.get("feed")
    if not isinstance(feed, dict):
        feed = payload.get("response", {}).get("feed")
    entries = feed.get("entry", []) if isinstance(feed, dict) else []
    identifiers = sorted({str(item["producer_granule_id"]) for item in entries})
    if not identifiers:
        raise ValueError("CMR response contains no producer granule IDs")
    paths: list[Path] = []
    for identifier in identifiers:
        match = re.match(
            rf"^{re.escape(config.product)}\.A"
            r"(?P<year>\d{4})(?P<doy>\d{3})\.",
            identifier,
        )
        if match is None:
            raise ValueError(f"unexpected CMR granule ID: {identifier}")
        product_date = _date_from_ordinal(int(match.group("year")), int(match.group("doy")))
        path = (
            root / f"{product_date.year:04d}" / f"{product_date.month:02d}" / (identifier + ".hdf")
        )
        if not path.is_file():
            raise FileNotFoundError(f"CMR-selected granule is missing: {path}")
        paths.append(path)
    return paths


def _load_pixels(
    paths: list[Path],
    *,
    start: date,
    end: date,
    config: MCD64AreaConfig,
) -> tuple[dict[BurnOccurrenceKey, BurnPixel], dict[str, Any]]:
    pixels: dict[BurnOccurrenceKey, BurnPixel] = {}
    occurrences_by_coordinate: dict[tuple[int, int], set[BurnOccurrenceKey]] = {}
    totals: Counter[str] = Counter()
    duplicate_count = 0
    granules: list[dict[str, Any]] = []
    for path in paths:
        candidates, counts = _load_granule_pixels(
            path,
            start=start,
            end=end,
            config=config,
        )
        totals.update(counts)
        granules.append(
            {
                "path": path.as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": _sha256(path),
                **counts,
            }
        )
        for pixel in candidates:
            existing = pixels.get(pixel.occurrence)
            comparable_existing = (
                (
                    existing.burn_date,
                    existing.uncertainty_days,
                    existing.qa,
                    existing.first_reliable_day,
                    existing.last_reliable_day,
                )
                if existing is not None
                else None
            )
            comparable_pixel = (
                pixel.burn_date,
                pixel.uncertainty_days,
                pixel.qa,
                pixel.first_reliable_day,
                pixel.last_reliable_day,
            )
            if existing is not None and comparable_existing != comparable_pixel:
                raise ValueError(
                    "conflicting cross-month MCD64A1 classifications for burn "
                    f"occurrence {pixel.occurrence}: "
                    f"{comparable_existing} != {comparable_pixel}"
                )
            prior_keys = occurrences_by_coordinate.get(pixel.coordinate, set())
            if (
                existing is None
                and prior_keys
                and config.cross_month_duplicate_policy == "require_identical_then_deduplicate"
            ):
                prior = pixels[sorted(prior_keys)[0]]
                comparable_prior = (
                    prior.burn_date,
                    prior.uncertainty_days,
                    prior.qa,
                    prior.first_reliable_day,
                    prior.last_reliable_day,
                )
                raise ValueError(
                    "conflicting cross-month MCD64A1 classifications at "
                    f"{pixel.coordinate}: {comparable_prior} != {comparable_pixel}"
                )
            if existing is None:
                pixels[pixel.occurrence] = pixel
                occurrences_by_coordinate.setdefault(pixel.coordinate, set()).add(pixel.occurrence)
            else:
                duplicate_count += 1
                pixels[pixel.occurrence] = BurnPixel(
                    global_row=pixel.global_row,
                    global_column=pixel.global_column,
                    burn_date=pixel.burn_date,
                    uncertainty_days=pixel.uncertainty_days,
                    qa=pixel.qa,
                    first_reliable_day=pixel.first_reliable_day,
                    last_reliable_day=pixel.last_reliable_day,
                    granule_names=tuple(sorted(existing.granule_names + pixel.granule_names)),
                )
    repeat_coordinates = {
        coordinate: keys for coordinate, keys in occurrences_by_coordinate.items() if len(keys) > 1
    }
    return pixels, {
        "granule_count": len(paths),
        "granules": granules,
        "qa_counts": dict(sorted(totals.items())),
        "cross_month_identical_duplicate_count": duplicate_count,
        "distinct_repeat_burn_coordinate_count": len(repeat_coordinates),
        "distinct_repeat_burn_occurrence_count": sum(
            len(keys) for keys in repeat_coordinates.values()
        ),
        "unique_spatial_pixel_count": len(occurrences_by_coordinate),
        "unique_burn_occurrence_count": len(pixels),
        "unique_accepted_pixel_count": len(pixels),
    }


def _load_events(path: Path) -> tuple[list[FrozenEvent], dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    events: list[FrozenEvent] = []
    for item in payload.get("events", []):
        detections: list[tuple[float, float, date]] = []
        for detection in item["detections"]:
            observed = datetime.fromisoformat(
                str(detection["observed_at"]).replace("Z", "+00:00")
            ).astimezone(UTC)
            detections.append(
                (
                    float(detection["longitude"]),
                    float(detection["latitude"]),
                    observed.date(),
                )
            )
        if not detections:
            raise ValueError(f"frozen event {item['event_id']} has no detections")
        events.append(
            FrozenEvent(
                event_id=str(item["event_id"]),
                first_date=min(value[2] for value in detections),
                last_date=max(value[2] for value in detections),
                detections=tuple(detections),
                payload=dict(item),
            )
        )
    if len(events) != payload.get("event_count"):
        raise ValueError("frozen event count does not match its payload")
    return sorted(events, key=lambda item: item.event_id), {
        "path": path.as_posix(),
        "sha256": _sha256(path),
        "event_count": len(events),
        "detection_count": int(payload["detection_count"]),
        "algorithm_version": str(payload["algorithm_version"]),
    }


def _cell_for_lonlat(
    longitude: float,
    latitude: float,
    config: MCD64AreaConfig,
) -> tuple[int, int]:
    latitude_radians = math.radians(latitude)
    x = config.sphere_radius_m * math.radians(longitude) * math.cos(latitude_radians)
    y = config.sphere_radius_m * latitude_radians
    column = math.floor((x - config.global_upper_left_x_m) / config.pixel_size_m)
    row = math.floor((config.global_upper_left_y_m - y) / config.pixel_size_m)
    return row, column


def _lonlat_for_cell(
    row: int,
    column: int,
    config: MCD64AreaConfig,
) -> tuple[float, float]:
    x = config.global_upper_left_x_m + (column + 0.5) * config.pixel_size_m
    y = config.global_upper_left_y_m - (row + 0.5) * config.pixel_size_m
    latitude_radians = y / config.sphere_radius_m
    cosine = math.cos(latitude_radians)
    if abs(cosine) < 1e-12:
        raise ValueError("cannot invert a sinusoidal cell at the pole")
    longitude = math.degrees(x / (config.sphere_radius_m * cosine))
    latitude = math.degrees(latitude_radians)
    return longitude, latitude


def _temporally_compatible(
    pixel: BurnPixel,
    event: FrozenEvent,
    config: MCD64AreaConfig,
) -> bool:
    pixel_first = pixel.burn_date - timedelta(days=pixel.uncertainty_days)
    pixel_last = pixel.burn_date + timedelta(days=pixel.uncertainty_days)
    event_first = event.first_date - timedelta(days=config.event_time_padding_days)
    event_last = event.last_date + timedelta(days=config.event_time_padding_days)
    return pixel_first <= event_last and pixel_last >= event_first


def _seed_pixels(
    event: FrozenEvent,
    pixels: dict[BurnOccurrenceKey, BurnPixel],
    occurrences_by_coordinate: dict[tuple[int, int], tuple[BurnOccurrenceKey, ...]],
    config: MCD64AreaConfig,
    geod: Geod,
) -> set[BurnOccurrenceKey]:
    seeds: set[BurnOccurrenceKey] = set()
    cell_radius = math.ceil(config.seed_radius_m / config.pixel_size_m) + 2
    for detection_longitude, detection_latitude, _ in event.detections:
        centre_row, centre_column = _cell_for_lonlat(
            detection_longitude,
            detection_latitude,
            config,
        )
        for row in range(centre_row - cell_radius, centre_row + cell_radius + 1):
            for column in range(centre_column - cell_radius, centre_column + cell_radius + 1):
                coordinate = (row, column)
                occurrence_keys = occurrences_by_coordinate.get(coordinate, ())
                compatible_keys = [
                    key
                    for key in occurrence_keys
                    if _temporally_compatible(pixels[key], event, config)
                ]
                if not compatible_keys:
                    continue
                longitude, latitude = _lonlat_for_cell(row, column, config)
                _, _, distance = geod.inv(
                    detection_longitude,
                    detection_latitude,
                    longitude,
                    latitude,
                )
                if distance <= config.seed_radius_m:
                    seeds.update(compatible_keys)
    return seeds


def _grow_claim(
    seeds: set[BurnOccurrenceKey],
    *,
    event: FrozenEvent,
    pixels: dict[BurnOccurrenceKey, BurnPixel],
    occurrences_by_coordinate: dict[tuple[int, int], tuple[BurnOccurrenceKey, ...]],
    config: MCD64AreaConfig,
) -> set[BurnOccurrenceKey]:
    claim = set(seeds)
    queue: deque[BurnOccurrenceKey] = deque(sorted(seeds))
    while queue:
        row, column, _ = queue.popleft()
        for row_offset in (-1, 0, 1):
            for column_offset in (-1, 0, 1):
                coordinate = row + row_offset, column + column_offset
                for occurrence_key in occurrences_by_coordinate.get(coordinate, ()):
                    if occurrence_key in claim:
                        continue
                    pixel = pixels[occurrence_key]
                    if not _temporally_compatible(pixel, event, config):
                        continue
                    claim.add(occurrence_key)
                    queue.append(occurrence_key)
    return claim


def _daily_area(
    occurrence_keys: set[BurnOccurrenceKey],
    pixels: dict[BurnOccurrenceKey, BurnPixel],
    config: MCD64AreaConfig,
) -> dict[str, Any]:
    central: Counter[str] = Counter()
    earliest: Counter[str] = Counter()
    latest: Counter[str] = Counter()
    high_confidence: Counter[str] = Counter()
    for occurrence_key in sorted(occurrence_keys):
        pixel = pixels[occurrence_key]
        central[pixel.burn_date.isoformat()] += 1
        earliest[(pixel.burn_date - timedelta(days=pixel.uncertainty_days)).isoformat()] += 1
        latest[(pixel.burn_date + timedelta(days=pixel.uncertainty_days)).isoformat()] += 1
        if pixel.high_confidence:
            high_confidence[pixel.burn_date.isoformat()] += 1

    def area_map(values: Counter[str]) -> dict[str, float]:
        return {day: count * config.pixel_area_hectares for day, count in sorted(values.items())}

    cumulative = 0.0
    cumulative_map: dict[str, float] = {}
    for day, area in area_map(central).items():
        cumulative += area
        cumulative_map[day] = cumulative
    return {
        "central_daily_increment_ha": area_map(central),
        "central_cumulative_ha": cumulative_map,
        "earliest_timing_daily_increment_ha": area_map(earliest),
        "latest_timing_daily_increment_ha": area_map(latest),
        "high_confidence_daily_increment_ha": area_map(high_confidence),
    }


def _area_stratum(area_hectares: float) -> str:
    if area_hectares < 100:
        return "weak"
    if area_hectares <= 1000:
        return "moderate"
    return "major"


def build_mcd64a1_event_areas(
    *,
    mcd64_root: Path,
    cmr_path: Path,
    events_path: Path,
    config_path: Path,
    start: date,
    end: date,
    support_event_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Build QA-screened, non-overlapping MCD64A1 area curves for frozen events."""
    if end < start:
        raise ValueError("MCD64A1 experiment end precedes start")
    config = MCD64AreaConfig.from_yaml(config_path)
    granule_paths = _cmr_granule_paths(mcd64_root, cmr_path, config)
    pixels, pixel_provenance = _load_pixels(
        granule_paths,
        start=start,
        end=end,
        config=config,
    )
    events, event_provenance = _load_events(events_path)
    geod = Geod(ellps="WGS84")
    occurrences_by_coordinate: dict[tuple[int, int], tuple[BurnOccurrenceKey, ...]] = {}
    for occurrence_key, pixel in pixels.items():
        occurrences_by_coordinate.setdefault(pixel.coordinate, ())
        occurrences_by_coordinate[pixel.coordinate] = tuple(
            sorted((*occurrences_by_coordinate[pixel.coordinate], occurrence_key))
        )

    raw_claims: dict[str, set[BurnOccurrenceKey]] = {}
    seed_counts: dict[str, int] = {}
    claims_by_occurrence: dict[BurnOccurrenceKey, set[str]] = {}
    for event in events:
        seeds = _seed_pixels(
            event,
            pixels,
            occurrences_by_coordinate,
            config,
            geod,
        )
        claim = _grow_claim(
            seeds,
            event=event,
            pixels=pixels,
            occurrences_by_coordinate=occurrences_by_coordinate,
            config=config,
        )
        seed_counts[event.event_id] = len(seeds)
        raw_claims[event.event_id] = claim
        for occurrence_key in claim:
            claims_by_occurrence.setdefault(occurrence_key, set()).add(event.event_id)

    ambiguous_occurrences = {
        occurrence_key: event_ids
        for occurrence_key, event_ids in claims_by_occurrence.items()
        if len(event_ids) > 1
    }
    ambiguous_spatial_coordinates = {(row, column) for row, column, _ in ambiguous_occurrences}
    assigned: dict[str, set[BurnOccurrenceKey]] = {
        event.event_id: {
            occurrence_key
            for occurrence_key in raw_claims[event.event_id]
            if occurrence_key not in ambiguous_occurrences
        }
        for event in events
    }

    event_results: list[dict[str, Any]] = []
    eligible_strata: Counter[str] = Counter()
    for event in events:
        occurrence_keys = assigned[event.event_id]
        high_confidence_count = sum(pixels[value].high_confidence for value in occurrence_keys)
        reasons: list[str] = []
        if seed_counts[event.event_id] == 0:
            reasons.append("no_spatiotemporally_matched_burn_seed")
        if len(occurrence_keys) < config.minimum_assigned_pixel_count:
            reasons.append("insufficient_unambiguous_burn_pixels")
        if config.require_at_least_one_high_confidence_pixel and high_confidence_count == 0:
            reasons.append("no_high_confidence_burn_pixel")
        area_hectares = len(occurrence_keys) * config.pixel_area_hectares
        area_eligible = not reasons
        stratum = _area_stratum(area_hectares) if area_eligible else None
        if stratum is not None:
            eligible_strata[stratum] += 1
        result = {
            "event_id": event.event_id,
            "first_observed_date": event.first_date.isoformat(),
            "last_observed_date": event.last_date.isoformat(),
            "latitude": event.payload["latitude"],
            "longitude": event.payload["longitude"],
            "fuel_types": event.payload["fuel_types"],
            "member_detection_count": len(event.detections),
            "seed_pixel_count": seed_counts[event.event_id],
            "seed_burn_occurrence_count": seed_counts[event.event_id],
            "raw_claim_pixel_count": len(raw_claims[event.event_id]),
            "raw_claim_burn_occurrence_count": len(raw_claims[event.event_id]),
            "ambiguous_claim_pixel_count": sum(
                occurrence_key in ambiguous_occurrences
                for occurrence_key in raw_claims[event.event_id]
            ),
            "ambiguous_claim_burn_occurrence_count": sum(
                occurrence_key in ambiguous_occurrences
                for occurrence_key in raw_claims[event.event_id]
            ),
            "assigned_pixel_count": len(occurrence_keys),
            "assigned_burn_occurrence_count": len(occurrence_keys),
            "assigned_spatial_pixel_count": len(
                {(row, column) for row, column, _ in occurrence_keys}
            ),
            "high_confidence_pixel_count": high_confidence_count,
            "high_confidence_burn_occurrence_count": high_confidence_count,
            "central_area_ha": area_hectares,
            "high_confidence_area_ha": (high_confidence_count * config.pixel_area_hectares),
            "area_stratum": stratum,
            "burned_area_eligible": area_eligible,
            "ineligibility_reasons": reasons,
            "daily_area": _daily_area(occurrence_keys, pixels, config),
        }
        if support_event_ids is not None and event.event_id in support_event_ids:
            support_occurrences = []
            for occurrence_key in sorted(occurrence_keys):
                pixel = pixels[occurrence_key]
                longitude, latitude = _lonlat_for_cell(
                    pixel.global_row,
                    pixel.global_column,
                    config,
                )
                support_occurrences.append(
                    {
                        "global_row": pixel.global_row,
                        "global_column": pixel.global_column,
                        "longitude": longitude,
                        "latitude": latitude,
                        "burn_date": pixel.burn_date.isoformat(),
                        "burn_date_uncertainty_days": pixel.uncertainty_days,
                        "high_confidence": pixel.high_confidence,
                        "granule_names": list(pixel.granule_names),
                    }
                )
            if len(support_occurrences) != len(occurrence_keys):
                raise AssertionError("MCD64A1 support occurrence count changed")
            result["support_occurrences"] = support_occurrences
        event_results.append(result)

    eligible_count = sum(item["burned_area_eligible"] for item in event_results)
    target_per_stratum = 3
    strata_design_passed = all(
        eligible_strata.get(name, 0) >= target_per_stratum for name in ("weak", "moderate", "major")
    )
    return {
        "schema_version": 1,
        "operator_version": config.operator_version,
        "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "experiment_interval": {
            "start": start.isoformat(),
            "end_inclusive": end.isoformat(),
        },
        "configuration": {
            "path": config_path.as_posix(),
            "sha256": _sha256(config_path),
            "pixel_area_hectares": config.pixel_area_hectares,
            "seed_radius_m": config.seed_radius_m,
            "connectivity": config.connectivity,
            "event_time_padding_days": config.event_time_padding_days,
            "overlapping_pixel_policy": config.overlapping_pixel_policy,
            "cross_month_duplicate_policy": config.cross_month_duplicate_policy,
        },
        "sources": {
            "mcd64_root": mcd64_root.as_posix(),
            "burned_area_root": mcd64_root.as_posix(),
            "cmr": {
                "path": cmr_path.as_posix(),
                "sha256": _sha256(cmr_path),
            },
            "frozen_events": event_provenance,
            config.product.lower(): pixel_provenance,
            "burned_area_product": {
                "short_name": config.product,
                "collection": config.collection,
                **pixel_provenance,
            },
        },
        "summary": {
            "frozen_event_count": len(events),
            "event_with_seed_count": sum(value > 0 for value in seed_counts.values()),
            "burned_area_eligible_event_count": eligible_count,
            "ambiguous_pixel_count": len(ambiguous_occurrences),
            "ambiguous_burn_occurrence_count": len(ambiguous_occurrences),
            "ambiguous_spatial_pixel_count": len(ambiguous_spatial_coordinates),
            "eligible_strata_counts": {
                name: eligible_strata.get(name, 0) for name in ("weak", "moderate", "major")
            },
            "minimum_events_per_stratum": target_per_stratum,
            "area_strata_design_passed": strata_design_passed,
            "independent_daily_burned_area_available": eligible_count > 0,
            "support_event_count": len(support_event_ids or set()),
        },
        "events": event_results,
    }
