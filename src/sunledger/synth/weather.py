"""Seeded daily plane-of-array irradiance per postcode (stand-in for BOM / satellite data)."""

from __future__ import annotations

import math
import random
from datetime import date, timedelta

from sunledger.catalog import LOCALITIES, REGION_CLIMATE, Locality


def season(day: date, peak_doy: int) -> float:
    """Cosine weight in [-1, 1] peaking on `peak_doy`."""
    return math.cos(2 * math.pi * (day.timetuple().tm_yday - peak_doy) / 365.25)


def clear_sky(lat: float, day: date) -> float:
    """Approximate clear-sky irradiance on a tilted array, kWh/m2/day (summer solstice ~ day 355)."""
    amplitude = 0.13 * abs(lat) - 2.5
    return 7.6 - 0.04 * abs(lat) + amplitude * season(day, 355)


def irradiance_by_postcode(seed: int, start: date, end: date) -> dict[str, dict[date, float]]:
    rng = random.Random(seed)
    days = [start + timedelta(n) for n in range((end - start).days + 1)]

    clouds: dict[str, list[float]] = {}
    for region, bias in REGION_CLIMATE.items():
        z, series = 0.0, []
        for day in days:
            z = 0.65 * z + rng.gauss(0, 0.76)
            winter = max(0.0, season(day, 172)) * 0.08  # cloudier winters in the south
            series.append(min(1.0, max(0.22, 0.80 + bias - winter + 0.17 * z)))
        clouds[region] = series

    result: dict[str, dict[date, float]] = {}
    for loc in LOCALITIES:
        result[loc.postcode] = {
            day: round(clear_sky(loc.lat, day) * min(1.0, clouds[loc.region][i] * rng.gauss(1, 0.03)), 3)
            for i, day in enumerate(days)
        }
    return result


def locality(postcode: str) -> Locality:
    return next(loc for loc in LOCALITIES if loc.postcode == postcode)
