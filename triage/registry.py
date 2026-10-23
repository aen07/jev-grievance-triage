"""Project registry and filing-window arithmetic (ED-007). Dates never go to Jev."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

FILING_WINDOW_MONTHS = 24


@dataclass(frozen=True)
class Project:
    project_id: str
    name: str
    country: str
    location: str
    sector: str
    status: str  # "Active" | "Closed"
    closing_date: date
    works: str = ""  # plain-language description of what the project builds, for Jev questions

    def describe(self) -> str:
        return f"{self.name} ({self.sector}) in {self.location}, {self.country}"


REGISTRY: tuple[Project, ...] = (
    Project("P-1041", "Northern Corridor Road Rehabilitation", "Valdoria", "Tamsa to Orvik highway", "Transport", "Active", date(2028, 6, 30), "road rehabilitation and widening, highway works, quarry trucks, road construction camps and sites between Tamsa and Orvik"),
    Project("P-1187", "Lake Amira Water Treatment Expansion", "Valdoria", "Lake Amira", "Water", "Active", date(2027, 12, 31), "expansion of the water treatment plant at Lake Amira, its construction site, contractors and workers"),
    Project("P-1055", "Highland Irrigation Modernization", "Valdoria", "Kerro Highlands", "Agriculture", "Closed", date(2025, 9, 30), "irrigation canals, channels and water intakes in the Kerro Highlands farming areas"),
    Project("P-0932", "Coastal Towns Urban Drainage", "Kestria", "Port Selene", "Urban", "Closed", date(2022, 3, 31), "urban drains, drainage channels and sewage pipes in Port Selene"),
    Project("P-1210", "Rural Clinics Solar Electrification", "Kestria", "Belmar and Ostra districts", "Energy / Health", "Active", date(2029, 1, 31), "solar panels, batteries and generators installed at rural health clinics in Belmar and Ostra districts"),
    Project("P-1302", "Secondary Schools Digital Learning", "Kestria", "Nationwide", "Education", "Active", date(2030, 6, 30), "tablets, laptops, an e-learning platform and teacher training for secondary schools across Kestria"),
)

BY_ID = {p.project_id: p for p in REGISTRY}


def add_months(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 + months, 12)
    year, month = d.year + y, m + 1
    # clamp day for short months (e.g. Feb)
    for day in (d.day, 30, 29, 28):
        try:
            return date(year, month, day)
        except ValueError:
            continue
    raise ValueError(d)


def filing_deadline(project: Project) -> date:
    return add_months(project.closing_date, FILING_WINDOW_MONTHS)


def within_filing_window(project: Project, received_at: date) -> bool:
    """P1 condition 3: active, or received within 24 months after the closing date.

    Assumption: an "Active" project whose closing date has already passed relative to
    received_at is treated by the date rule, not the status label (status is a snapshot).
    """
    if project.status == "Active" and received_at <= project.closing_date:
        return True
    return received_at <= filing_deadline(project)
