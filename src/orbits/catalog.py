"""Download and cache CelesTrak GP JSON element sets."""

import json
import logging
import re
import time
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import Lock

import requests
from sgp4.api import Satrec

from .user_catalog import _satellite_from_omm

GP_URL = "https://celestrak.org/NORAD/elements/gp.php"
CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "cache"
CACHE_SECONDS = 7200
_LOG = logging.getLogger(__name__)
_GROUP_LOCKS = {}


def load_catalog(group: str) -> list[Satrec]:
    """Load Earth TEME SGP4 models with UTC epochs from a CelesTrak group."""
    return [model for _, model in load_named_catalog(group)]


def load_named_catalog(group: str) -> list[tuple[str, Satrec]]:
    """Load CelesTrak names and SGP4 models with TEME km and UTC epochs."""
    if not re.fullmatch(r"[a-zA-Z0-9-]+", group):
        raise ValueError("Invalid CelesTrak group name")
    group = group.lower()
    # Streamlit sessions share a process. Let the first session finish refreshing
    # this group before another session checks the cache for it.
    with _GROUP_LOCKS.setdefault(group, Lock()):
        return _load_group(group)


def _load_group(group: str) -> list[tuple[str, Satrec]]:
    """Read or refresh one group's GP elements with UTC epochs under its lock."""
    path = CACHE_DIR / f"{group}.json"
    try:
        cached_records = json.loads(path.read_text())
        cache_age = time.time() - path.stat().st_mtime
    except (FileNotFoundError, ValueError):
        cached_records = None

    if isinstance(cached_records, list) and cache_age < CACHE_SECONDS:
        satellites = _parse_records(cached_records, group)
        if satellites:
            return satellites

    try:
        records = _download(group)
        satellites = _parse_records(records, group)
        if not satellites:
            raise ValueError(f"No usable GP records for {group}")
    except (requests.RequestException, ValueError) as exc:
        if isinstance(cached_records, list) and cache_age >= CACHE_SECONDS:
            satellites = _parse_records(cached_records, group)
            if satellites:
                _LOG.warning(
                    "Using stale CelesTrak cache for %s (%.1f hours old): %s",
                    group, cache_age / 3600, exc,
                )
                return satellites
        raise
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(mode="w", dir=CACHE_DIR, delete=False) as pending:
        temporary_path = Path(pending.name)
        try:
            json.dump(records, pending)
            pending.close()
            temporary_path.replace(path)
        finally:
            temporary_path.unlink(missing_ok=True)
    return satellites


def _parse_records(records: list, group: str) -> list[tuple[str, Satrec]]:
    """Convert JSON OMM records into SGP4 models with TEME km and km/s output."""
    satellites = []
    for index, record in enumerate(records, start=1):
        try:
            if not isinstance(record, dict):
                raise ValueError("expected an OMM record")
            model = _satellite_from_omm(record)
            name = record.get("OBJECT_NAME") or f"NORAD {model.satnum}"
            satellites.append((str(name), model))
        except (AttributeError, KeyError, OverflowError, TypeError, ValueError) as exc:
            _LOG.warning("Skipping GP record %d from %s: %s", index, group, exc)
    return satellites


def _download(group: str) -> list:
    """Fetch OMM records in standard OMM units, retrying transient failures."""
    for attempt in range(3):
        try:
            response = requests.get(
                GP_URL, params={"GROUP": group, "FORMAT": "JSON"},
                timeout=10, allow_redirects=False,
            )
        except (requests.Timeout, requests.ConnectionError):
            if attempt == 2:
                raise
        else:
            if response.status_code == 200:
                try:
                    records = response.json()
                except ValueError as exc:
                    raise ValueError(f"CelesTrak returned non-JSON GP data for group {group}") from exc
                if not isinstance(records, list):
                    raise ValueError(f"Expected a GP JSON array for {group}")
                return records
            if response.status_code not in (500, 502, 503, 504) or attempt == 2:
                raise requests.HTTPError(f"GP request for {group} returned HTTP {response.status_code}")
        time.sleep(2 ** attempt)
