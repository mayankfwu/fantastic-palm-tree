"""Import and persist user-submitted satellite and debris orbital elements."""

import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from math import isfinite
from pathlib import Path
from typing import Literal

from sgp4 import omm
from sgp4.api import Satrec

ObjectKind = Literal["satellite", "debris"]
DEFAULT_CATALOG = Path(__file__).resolve().parents[2] / "data" / "user_catalog.sqlite3"

_METADATA = {
    "CENTER_NAME": "EARTH",
    "REF_FRAME": "TEME",
    "TIME_SYSTEM": "UTC",
    "MEAN_ELEMENT_THEORY": "SGP4",
}
_NUMERIC_FIELDS = (
    "MEAN_MOTION", "ECCENTRICITY", "INCLINATION", "RA_OF_ASC_NODE",
    "ARG_OF_PERICENTER", "MEAN_ANOMALY", "BSTAR", "MEAN_MOTION_DOT",
    "MEAN_MOTION_DDOT",
)


def _satellite_from_omm(record: dict) -> Satrec:
    """Build an SGP4 model from OMM units (degrees, revolutions/day, UTC epoch)."""
    for field, expected in _METADATA.items():
        if record.get(field, expected) != expected:
            raise ValueError(f"{field} must be {expected}")

    fields = record.copy()
    # The SGP4 OMM initializer expects a UTC timestamp with fractional seconds.
    epoch_text = fields["EPOCH"]
    if not isinstance(epoch_text, str) or "T" not in epoch_text:
        raise ValueError("EPOCH must be an ISO 8601 timestamp")
    epoch = datetime.fromisoformat(epoch_text)
    if epoch.tzinfo is not None:
        if epoch.utcoffset().total_seconds() != 0:
            raise ValueError("EPOCH must be UTC")
        epoch = epoch.astimezone(UTC).replace(tzinfo=None)
    fields["EPOCH"] = epoch.isoformat(timespec="microseconds")

    for field in _NUMERIC_FIELDS:
        value = float(fields[field])
        if isinstance(fields[field], bool) or not isfinite(value):
            raise ValueError(f"{field} must be a finite number")
        fields[field] = value

    catalog_id = fields["NORAD_CAT_ID"]
    if not str(catalog_id).isascii() or not str(catalog_id).isdecimal():
        raise ValueError("NORAD_CAT_ID must be a positive integer")
    if not 0 < int(catalog_id) <= 339_999:
        raise ValueError("NORAD_CAT_ID must be between 1 and 339999 for SGP4")
    if fields["MEAN_MOTION"] <= 0 or not 0 <= fields["ECCENTRICITY"] < 1:
        raise ValueError("MEAN_MOTION must be positive and ECCENTRICITY must be in [0, 1)")
    if not 0 <= fields["INCLINATION"] <= 180:
        raise ValueError("INCLINATION must be between 0 and 180 degrees")

    # CelesTrak can omit a blank international designator.
    fields["OBJECT_ID"] = fields.get("OBJECT_ID") or ""
    satellite = Satrec()
    omm.initialize(satellite, fields)
    error, position, velocity = satellite.sgp4(satellite.jdsatepoch, satellite.jdsatepochF)
    if error or not all(isfinite(value) for value in (*position, *velocity)):
        raise ValueError(f"SGP4 failed at the OMM epoch (error code {error})")
    return satellite


def _check_kind(kind: ObjectKind) -> None:
    """Check the unitless catalog category."""
    if kind not in ("satellite", "debris"):
        raise ValueError("kind must be 'satellite' or 'debris'")


def import_user_omm(
    payload: str | bytes, kind: ObjectKind, *, catalog_path: Path = DEFAULT_CATALOG
) -> list[int]:
    """Save JSON OMM data (UTC epochs, degrees, rev/day) and return NORAD IDs.

    Accept one record or a non-empty array. Reimporting an ID in the same
    category replaces its elements. Validate the entire upload before saving.
    """
    _check_kind(kind)
    records = json.loads(payload)
    if isinstance(records, dict):
        records = [records]
    if not isinstance(records, list) or not records:
        raise ValueError("Expected an OMM object or a non-empty array of objects")

    entries = {}
    for index, record in enumerate(records, start=1):
        if not isinstance(record, dict):
            raise ValueError(f"OMM record {index} must be an object")
        try:
            satellite = _satellite_from_omm(record)
            entries[satellite.satnum] = json.dumps(record, allow_nan=False)
        except (AttributeError, KeyError, OverflowError, TypeError, ValueError) as exc:
            raise ValueError(f"Invalid OMM record {index}: {exc}") from exc

    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(catalog_path)) as database, database:
        database.execute("""
            CREATE TABLE IF NOT EXISTS user_objects (
                kind TEXT NOT NULL,
                norad_id INTEGER NOT NULL,
                omm_json TEXT NOT NULL,
                PRIMARY KEY (kind, norad_id)
            )
        """)
        database.executemany("""
            INSERT INTO user_objects (kind, norad_id, omm_json) VALUES (?, ?, ?)
            ON CONFLICT (kind, norad_id) DO UPDATE SET omm_json = excluded.omm_json
        """, [(kind, catalog_id, record) for catalog_id, record in entries.items()])
    return list(entries)


def load_user_catalog(
    kind: ObjectKind, *, catalog_path: Path = DEFAULT_CATALOG
) -> list[Satrec]:
    """Load a category as SGP4 models (TEME km and km/s, UTC epochs)."""
    _check_kind(kind)
    if not catalog_path.exists():
        return []
    with closing(sqlite3.connect(catalog_path)) as database:
        # An importer can be initializing the database in another session.
        table = database.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'user_objects'"
        ).fetchone()
        if table is None:
            return []
        rows = database.execute(
            "SELECT omm_json FROM user_objects WHERE kind = ? ORDER BY norad_id", (kind,)
        )
        return [_satellite_from_omm(json.loads(payload)) for (payload,) in rows]
