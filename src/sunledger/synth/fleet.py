"""Synthetic fleet of AU home solar + battery sites, and their simulated daily ground truth."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from datetime import date, timedelta

from sunledger.catalog import (
    INSTALLERS, INSURERS, LOCALITIES, PRODUCT_WEIGHTS, PRODUCTS, SOURCE_WEIGHTS, STATE_WEIGHTS, Locality, Product,
)
from sunledger.synth.weather import season

FIRST_NAMES = (
    "Priya", "Liam", "Mei", "Oliver", "Aisha", "Jack", "Sofia", "Noah", "Chloe", "Ethan", "Zara",
    "Lucas", "Ava", "Hamish", "Leila", "Tom", "Grace", "Raj", "Ivy", "Marco", "Nina", "Sam", "Hana",
    "Ben", "Ruby", "Daniel", "Elena", "Kai", "Matilda", "Arjun", "Lily", "Finn", "Yasmin", "Josh",
)
SURNAME_INITIALS = "ABCDEFGHJKLMNPRSTVWY"


@dataclass
class Site:
    site_id: str
    owner: str
    loc: Locality
    installer_id: str
    product: Product
    source: str  # data platform, drawn independently of the (fictional) product
    units: int
    pv_kwp: float
    inverter_kw: float
    install_date: date
    data_start: date
    external_id: str
    serial: str
    base_pr: float
    fade_rate: float  # normal capacity loss per year
    rte_base: float
    load_kwh: float
    reserve: float
    faults: dict[str, dict] = field(default_factory=dict)
    consents: dict[str, bool] = field(default_factory=dict)
    certificate_recipient: str | None = None

    @property
    def usable_kwh(self) -> float:
        return self.product.usable_kwh * self.units


@dataclass
class DayTruth:
    day: date
    reporting: bool  # monitoring data reached the cloud
    pv_kwh: float
    import_kwh: float
    export_kwh: float
    charge_kwh: float
    discharge_kwh: float
    soc_peak: float  # % of usable, at ~15:00
    soc_trough: float  # % of usable, next morning ~06:00
    capacity_kwh: float


def build_fleet(seed: int, count: int, as_of: date, history_start: date) -> list[Site]:
    rng = random.Random(seed)
    sites = [_hero_site(history_start)]
    for n in range(2, count + 1):
        sites.append(_random_site(rng, n, as_of, history_start))
    _ensure_cohorts(sites)
    return sites


def _hero_site(history_start: date) -> Site:
    """The owner persona in the demo: rebate install, battery fading well beyond warranty."""
    loc = next(loc for loc in LOCALITIES if loc.suburb == "Werribee")
    product = next(p for p in PRODUCTS if p.brand == "Halvora")
    install = date(2025, 8, 14)
    return Site(
        site_id="S0001", owner="Priya N.", loc=loc, installer_id="INS-IRB", product=product, source="solaredge",
        units=1,
        pv_kwp=7.8, inverter_kw=6.0, install_date=install, data_start=max(install, history_start),
        external_id="4182736", serial="7E1C4A0F-91", base_pr=0.81, fade_rate=0.018, rte_base=0.905,
        load_kwh=19.5, reserve=0.10,
        faults={
            "capacity_fade": {"start": date(2026, 1, 12), "rate": 0.115},
            "rte_drop": {"start": date(2026, 6, 20), "to": 0.805},
        },
        consents={"monitoring": True, "installer_share": True, "benchmark": True, "cdr_meter": True,
                  "certificate": True},
        certificate_recipient=INSURERS[0],
    )


def _random_site(rng: random.Random, n: int, as_of: date, history_start: date) -> Site:
    state = rng.choices(list(STATE_WEIGHTS), weights=list(STATE_WEIGHTS.values()))[0]
    loc = rng.choice([loc for loc in LOCALITIES if loc.state == state])
    installers = [i for i in INSTALLERS if i.state == state]
    installer = rng.choices(installers, weights=[i.weight for i in installers])[0]
    product = rng.choices(PRODUCTS, weights=PRODUCT_WEIGHTS)[0]
    source = rng.choices(list(SOURCE_WEIGHTS), weights=list(SOURCE_WEIGHTS.values()))[0]
    units = rng.randint(1, product.max_units) if product.max_units > 1 else 1
    if product.usable_kwh < 6:  # small modular product: at least two units
        units = max(units, 2)

    # ~70% are Cheaper Home Batteries Program installs (Jul 2025 onwards).
    if rng.random() < 0.7:
        install = date(2025, 7, 1) + timedelta(rng.randint(0, 270))
    else:
        install = date(2021, 3, 1) + timedelta(rng.randint(0, 1550))
    inverter = rng.choice(product.inverter_kw)
    pv = round(inverter * rng.uniform(1.0, 1.33), 1)

    q = installer.quality
    faults: dict[str, dict] = {}
    start = max(install, history_start)
    span = max(1, (as_of - start).days)
    if rng.random() < 0.35 * (1 - q):
        pv = round(inverter * rng.uniform(1.55, 2.0), 1)  # oversized array: clipping + compliance issue
        faults["inverter_clipping"] = {}
    if rng.random() < 0.45 * (1 - q):
        early = rng.random() < 0.6  # install defect visible from day one, else a later failure
        faults["string_underperformance"] = {
            "start": start if early else start + timedelta(rng.randint(30, span)),
            "loss": rng.uniform(0.2, 0.42),
        }
    if rng.random() < 0.38 * (1 - q) + 0.02:
        faults["seasonal_shading"] = {"loss": rng.uniform(0.25, 0.45)}
    if rng.random() < 0.07:
        faults["capacity_fade"] = {"start": start + timedelta(rng.randint(0, span // 2)),
                                   "rate": rng.uniform(0.06, 0.12)}
    if rng.random() < 0.06:
        faults["rte_drop"] = {"start": start + timedelta(rng.randint(0, span)), "to": rng.uniform(0.74, 0.81)}
    if rng.random() < 0.10 + 0.18 * (1 - q):
        episodes = []
        for _ in range(rng.randint(1, 3)):
            begin = start + timedelta(rng.randint(0, span))
            episodes.append((begin, begin + timedelta(rng.randint(3, 18)), rng.choice(("comms", "tripped"))))
        if rng.random() < 0.35:  # currently offline
            episodes.append((as_of - timedelta(rng.randint(3, 12)), as_of, rng.choice(("comms", "tripped"))))
        faults["offline"] = {"episodes": episodes}

    consents = {
        "monitoring": True,
        "installer_share": rng.random() < 0.85,
        "benchmark": rng.random() < 0.62,
        "cdr_meter": rng.random() < 0.40,
        "certificate": rng.random() < 0.15,
    }
    return Site(
        site_id=f"S{n:04d}",
        owner=f"{rng.choice(FIRST_NAMES)} {rng.choice(SURNAME_INITIALS)}.",
        loc=loc, installer_id=installer.installer_id, product=product, source=source, units=units,
        pv_kwp=pv, inverter_kw=inverter, install_date=install, data_start=start,
        external_id=str(rng.randint(1_000_000, 9_999_999)),
        serial=f"{rng.randrange(16**8):08X}-{rng.randint(10, 99)}",
        base_pr=rng.gauss(0.80, 0.02), fade_rate=rng.uniform(0.012, 0.024), rte_base=rng.uniform(0.885, 0.92),
        load_kwh=rng.uniform(13, 26), reserve=rng.choice((0.1, 0.15, 0.2)),
        faults=faults, consents=consents,
        certificate_recipient=rng.choice(INSURERS) if consents["certificate"] else None,
    )


def _ensure_cohorts(sites: list[Site]) -> None:
    """Keep one small installer below the k=5 benchmark threshold so suppression is visible in the demo."""
    small = [s for s in sites if s.installer_id == "INS-KES" and s.consents["benchmark"]]
    for site in small[4:]:
        site.consents["benchmark"] = False


def soh(site: Site, day: date) -> float:
    age = (day - site.install_date).days / 365.25
    value = 1.0 - site.fade_rate * age
    if fade := site.faults.get("capacity_fade"):
        value -= fade["rate"] * max(0.0, (day - fade["start"]).days / 365.25)
    return value


def rte(site: Site, day: date) -> float:
    drop = site.faults.get("rte_drop")
    if not drop or day < drop["start"]:
        return site.rte_base
    progress = min(1.0, (day - drop["start"]).days / 60)
    return site.rte_base + (drop["to"] - site.rte_base) * progress


def simulate(site: Site, irradiance: dict[date, float], as_of: date, rng: random.Random) -> list[DayTruth]:
    episodes = site.faults.get("offline", {}).get("episodes", [])
    days, soc = [], 0.4
    day = site.data_start
    while day <= as_of:
        outage = next((kind for begin, end, kind in episodes if begin <= day <= end), None)
        pv = 0.0 if outage == "tripped" else _pv_kwh(site, day, irradiance[day], rng)

        summer, winter = max(0.0, season(day, 355)), max(0.0, season(day, 172))
        hot = 0.15 if site.loc.state == "QLD" else 0.05
        load = site.load_kwh * (1 + 0.22 * winter + hot * summer) * rng.gauss(1, 0.08)
        day_load, evening_load = 0.4 * load, 0.6 * load

        capacity = site.usable_kwh * soh(site, day)
        eff = math.sqrt(rte(site, day))
        direct = min(pv, day_load)
        surplus = pv - direct
        cells_in = min(surplus * eff, capacity * (1 - soc)) if outage != "tripped" else 0.0
        charge = cells_in / eff
        soc_peak = soc + cells_in / capacity
        cells_out = min(capacity * max(0.0, soc_peak - site.reserve), evening_load / eff)
        if outage == "tripped":
            cells_out = 0.0
        discharge = cells_out * eff
        soc_trough = soc_peak - cells_out / capacity

        days.append(DayTruth(
            day=day, reporting=outage is None, pv_kwh=pv,
            import_kwh=max(0.0, day_load - pv) + (evening_load - discharge),
            export_kwh=surplus - charge, charge_kwh=charge, discharge_kwh=discharge,
            soc_peak=100 * soc_peak, soc_trough=100 * soc_trough, capacity_kwh=capacity,
        ))
        soc = soc_trough
        day += timedelta(1)
    return days


def _pv_kwh(site: Site, day: date, irr: float, rng: random.Random) -> float:
    age = (day - site.install_date).days / 365.25
    temp_derate = 1 - 0.05 * max(0.0, season(day, 355))
    pv = site.pv_kwp * irr * site.base_pr * temp_derate * (1 - 0.005 * age) * rng.gauss(1, 0.02)

    if shade := site.faults.get("seasonal_shading"):
        pv *= 1 - shade["loss"] * max(0.0, season(day, 172)) ** 1.5
    if (string := site.faults.get("string_underperformance")) and day >= string["start"]:
        pv *= 1 - string["loss"]
    if "inverter_clipping" in site.faults:
        peak_kw = site.pv_kwp * irr / 7.0 * 0.85
        if peak_kw > site.inverter_kw:  # triangular power curve: clipped share of area above the cap
            pv *= 1 - ((peak_kw - site.inverter_kw) / peak_kw) ** 2
    return max(0.0, pv)
