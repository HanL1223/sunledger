"""Static reference data: battery products, data sources, installers and locations.
Battery brands/models, installers, insurers and owners are fictional; real names appear only as data-source APIs."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Access(StrEnum):
    OWNER_OAUTH = "owner_oauth"  # owner authorises SunLedger directly
    DEVELOPER_PORTAL = "developer_portal"  # official developer API, not owner OAuth (app review or device binding)
    PARTNER_GATED = "partner_gated"  # needs a commercial agreement with the OEM
    CDR = "cdr"  # Consumer Data Right, via a CDR representative arrangement


@dataclass(frozen=True)
class Product:
    brand: str
    model: str
    usable_kwh: float  # per unit
    max_units: int
    inverter_kw: tuple[float, ...]
    warranty_years: int = 10
    warranty_eol_soh: float = 0.70  # retained capacity at end of warranty
    rte_spec: float = 0.90


# Fictional products, independent of data platform; capacities deliberately match no real product.
PRODUCTS: tuple[Product, ...] = (
    Product("Corvane", "CV Home", 14.6, 1, (5.0, 10.0)),
    Product("Halvora", "HB Series 2", 9.2, 2, (5.0, 6.0, 8.0)),
    Product("Mirrow", "M-Stack", 4.4, 3, (5.0, 6.0, 7.0)),
    Product("Tessark", "TS HV", 10.8, 1, (5.0, 6.0)),
    Product("Ondelle", "OS Stack", 7.4, 2, (5.0, 6.0, 8.0)),
    Product("Zentrel", "ZR Home", 11.4, 1, (5.0, 8.0)),
    Product("Brevane", "BV Home", 10.6, 1, (5.0,)),
    Product("Pellard", "PH HV", 12.2, 1, (5.0, 6.0, 8.0)),
)

# Shares of new installs per product and per data platform (illustrative, not market data).
PRODUCT_WEIGHTS = (0.17, 0.11, 0.10, 0.08, 0.19, 0.16, 0.10, 0.09)
SOURCE_WEIGHTS = {"tesla": 0.17, "solaredge": 0.11, "enphase": 0.10, "sma": 0.08, "sigenergy": 0.19,
                  "sungrow": 0.16, "alphaess": 0.10, "fronius": 0.09}

SOURCE_ACCESS: dict[str, Access] = {
    "tesla": Access.OWNER_OAUTH,
    "solaredge": Access.OWNER_OAUTH,
    "enphase": Access.OWNER_OAUTH,
    "sma": Access.OWNER_OAUTH,
    "sigenergy": Access.PARTNER_GATED,
    "sungrow": Access.DEVELOPER_PORTAL,
    "alphaess": Access.DEVELOPER_PORTAL,
    "fronius": Access.PARTNER_GATED,
    "cdr": Access.CDR,
}

# Display names of the real integrations, shown only where integrations are described (never per site).
SOURCE_NAMES = {
    "tesla": "Tesla", "solaredge": "SolarEdge", "enphase": "Enphase", "sma": "SMA", "sigenergy": "Sigenergy",
    "sungrow": "Sungrow", "alphaess": "Alpha ESS", "fronius": "Fronius", "cdr": "Energy CDR",
}


@dataclass(frozen=True)
class Installer:
    installer_id: str
    name: str
    state: str
    quality: float  # 0..1, lower means more install-related faults
    weight: float  # share of sites within its state


INSTALLERS: tuple[Installer, ...] = (
    Installer("INS-IRB", "Varrowen Solar", "VIC", 0.62, 0.50),
    Installer("INS-BLG", "Teralune Solar", "VIC", 0.92, 0.28),
    Installer("INS-WAV", "Morrisk Electrical", "VIC", 0.40, 0.22),
    Installer("INS-CST", "Quellby Solar", "NSW", 0.85, 0.55),
    Installer("INS-HBR", "Halsmere Renewables", "NSW", 0.45, 0.45),
    Installer("INS-RDG", "Yarrowby Energy", "QLD", 0.78, 0.75),
    Installer("INS-KES", "Dunvoy Solar", "QLD", 0.55, 0.25),
    Installer("INS-SLT", "Calvenny Power", "SA", 0.86, 1.00),
)

STATE_WEIGHTS = {"VIC": 0.45, "NSW": 0.25, "QLD": 0.20, "SA": 0.10}


@dataclass(frozen=True)
class Locality:
    suburb: str
    postcode: str
    state: str
    lat: float
    region: str  # shares day-to-day cloud cover
    timezone: str


LOCALITIES: tuple[Locality, ...] = (
    Locality("Werribee", "3030", "VIC", -37.90, "MEL", "Australia/Melbourne"),
    Locality("Tarneit", "3029", "VIC", -37.83, "MEL", "Australia/Melbourne"),
    Locality("Craigieburn", "3064", "VIC", -37.60, "MEL", "Australia/Melbourne"),
    Locality("Preston", "3072", "VIC", -37.74, "MEL", "Australia/Melbourne"),
    Locality("Cranbourne", "3977", "VIC", -38.10, "MEL", "Australia/Melbourne"),
    Locality("Frankston", "3199", "VIC", -38.14, "MEL", "Australia/Melbourne"),
    Locality("Pakenham", "3810", "VIC", -38.07, "MEL", "Australia/Melbourne"),
    Locality("Geelong", "3220", "VIC", -38.15, "VIC_W", "Australia/Melbourne"),
    Locality("Ballarat", "3350", "VIC", -37.56, "VIC_W", "Australia/Melbourne"),
    Locality("Bendigo", "3550", "VIC", -36.76, "VIC_N", "Australia/Melbourne"),
    Locality("Penrith", "2750", "NSW", -33.75, "SYD", "Australia/Sydney"),
    Locality("Blacktown", "2148", "NSW", -33.77, "SYD", "Australia/Sydney"),
    Locality("Campbelltown", "2560", "NSW", -34.07, "SYD", "Australia/Sydney"),
    Locality("Hornsby", "2077", "NSW", -33.70, "SYD", "Australia/Sydney"),
    Locality("Newcastle", "2300", "NSW", -32.93, "HUN", "Australia/Sydney"),
    Locality("Wollongong", "2500", "NSW", -34.42, "SYD", "Australia/Sydney"),
    Locality("Ipswich", "4305", "QLD", -27.61, "BNE", "Australia/Brisbane"),
    Locality("Logan", "4114", "QLD", -27.64, "BNE", "Australia/Brisbane"),
    Locality("Caboolture", "4510", "QLD", -27.07, "BNE", "Australia/Brisbane"),
    Locality("Toowoomba", "4350", "QLD", -27.56, "DDS", "Australia/Brisbane"),
    Locality("Southport", "4215", "QLD", -27.97, "BNE", "Australia/Brisbane"),
    Locality("Salisbury", "5108", "SA", -34.76, "ADL", "Australia/Adelaide"),
    Locality("Morphett Vale", "5162", "SA", -35.13, "ADL", "Australia/Adelaide"),
    Locality("Mount Barker", "5251", "SA", -35.07, "ADL", "Australia/Adelaide"),
    Locality("Gawler", "5118", "SA", -34.60, "ADL", "Australia/Adelaide"),
)

# Mean cloudiness offset per region (negative = cloudier).
REGION_CLIMATE = {
    "MEL": -0.05, "VIC_W": -0.07, "VIC_N": 0.02, "SYD": -0.02, "HUN": -0.01,
    "BNE": 0.01, "DDS": 0.04, "ADL": 0.04,
}

INSURERS = ("Harbourline Home Insurance", "GreenNest Lending", "Southern Arc Mutual")
