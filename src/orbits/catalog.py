"""Download and cache CelesTrak GP JSON element sets."""

import json
import logging
import re
import time
from pathlib import Path
from tempfile import NamedTemporaryFile

import requests
from sgp4.api import Satrec

from .user_catalog import _satellite_from_omm

GP_URL = "https://celestrak.org/NORAD/elements/gp.php"
CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "cache"
CACHE_SECONDS = 7200
_LOG = logging.getLogger(__name__)


def load_catalog(group: str) -> list[Satrec]:
    """Load Earth TEME SGP4 models with UTC epochs from a CelesTrak group."""
    if not re.fullmatch(r"[a-zA-Z0-9-]+", group):
        raise ValueError("Invalid CelesTrak group name")
    group = group.lower()
    path = CACHE_DIR / f"{group}.json"
    try:
        records = json.loads(path.read_text())
        if not isinstance(records, list) or time.time() - path.stat().st_mtime >= CACHE_SECONDS:
            records = None
    except (FileNotFoundError, ValueError):
        records = None

    if records is None:
        records = _download(group)
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(mode="w", dir=CACHE_DIR, delete=False) as pending:
            temporary_path = Path(pending.name)
            try:
                json.dump(records, pending)
                pending.close()
                temporary_path.replace(path)
            finally:
                temporary_path.unlink(missing_ok=True)

    satellites = []
    for index, record in enumerate(records, start=1):
        try:
            if not isinstance(record, dict):
                raise ValueError("expected an OMM record")
            satellites.append(_satellite_from_omm(record))
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
                records = response.json()
                if not isinstance(records, list):
                    raise ValueError(f"Expected a GP JSON array for {group}")
                return records
            if response.status_code not in (500, 502, 503, 504) or attempt == 2:
                raise requests.HTTPError(f"GP request for {group} returned HTTP {response.status_code}")
        time.sleep(2 ** attempt)
