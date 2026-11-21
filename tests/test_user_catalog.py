"""Exercise OMM import and persistence without contacting CelesTrak."""

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.orbits.user_catalog import import_user_omm, load_user_catalog


# Synthetic OMM in the same units and shape as CelesTrak GP JSON.
OMM = {
    "OBJECT_NAME": "TEST SAT",
    "OBJECT_ID": "2026-001A",
    "EPOCH": "2026-04-01T12:00:00Z",
    "MEAN_MOTION": 15.5,
    "ECCENTRICITY": 0.0005,
    "INCLINATION": 51.6,
    "RA_OF_ASC_NODE": 100,
    "ARG_OF_PERICENTER": 30,
    "MEAN_ANOMALY": 50,
    "EPHEMERIS_TYPE": 0,
    "CLASSIFICATION_TYPE": "U",
    "NORAD_CAT_ID": 100123,
    "ELEMENT_SET_NO": 1,
    "REV_AT_EPOCH": 42,
    "BSTAR": 0.0001,
    "MEAN_MOTION_DOT": 0.00001,
    "MEAN_MOTION_DDOT": 0,
}


class UserCatalogTest(unittest.TestCase):
    def setUp(self):
        """Create an isolated catalog path without physical units."""
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.catalog = {"catalog_path": Path(directory.name) / "user_catalog.sqlite3"}

    def test_persists_satellites_and_debris(self):
        """Reload both categories as SGP4 models with TEME output in km and km/s."""
        self.assertEqual(load_user_catalog("satellite", **self.catalog), [])
        self.assertEqual(import_user_omm(json.dumps(OMM), "satellite", **self.catalog), [100123])
        debris = [
            dict(OMM, NORAD_CAT_ID=100125),
            dict(OMM, NORAD_CAT_ID=100124),
        ]
        import_user_omm(json.dumps(debris).encode(), "debris", **self.catalog)
        satellite, = load_user_catalog("satellite", **self.catalog)
        self.assertEqual(satellite.satnum, 100123)
        self.assertEqual(
            [sat.satnum for sat in load_user_catalog("debris", **self.catalog)],
            [100124, 100125],
        )
        error, _, _ = satellite.sgp4(satellite.jdsatepoch, satellite.jdsatepochF)
        self.assertEqual(error, 0)

    def test_reimport_replaces_existing_elements(self):
        """Replace a stored orbit and compare its unitless eccentricity."""
        import_user_omm(json.dumps(OMM), "satellite", **self.catalog)
        updated = dict(OMM, ECCENTRICITY=0.002)
        import_user_omm(json.dumps(updated), "satellite", **self.catalog)
        satellite, = load_user_catalog("satellite", **self.catalog)
        self.assertAlmostEqual(satellite.ecco, 0.002)

    def test_invalid_batch_leaves_catalog_unchanged(self):
        """Reject an incompatible frame and preserve the existing UTC-epoch record."""
        import_user_omm(json.dumps(OMM), "debris", **self.catalog)
        new = dict(OMM, NORAD_CAT_ID=100124)
        invalid = dict(OMM, REF_FRAME="ITRF")
        with self.assertRaisesRegex(ValueError, "record 2.*REF_FRAME"):
            import_user_omm(json.dumps([new, invalid]), "debris", **self.catalog)
        self.assertEqual(
            [sat.satnum for sat in load_user_catalog("debris", **self.catalog)], [100123]
        )

    def test_invalid_payloads(self):
        """Reject invalid JSON, category, eccentricity and non-UTC epoch."""
        invalid_records = (
            dict(OMM, EPOCH="2026-04-01T12:00:00+01:00"),
            dict(OMM, ECCENTRICITY=1),
            dict(OMM, MEAN_MOTION="NaN"),
        )
        for record in invalid_records:
            with self.subTest(record=record), self.assertRaises(ValueError):
                import_user_omm(json.dumps(record), "satellite", **self.catalog)
        with self.assertRaises(ValueError):
            import_user_omm("not JSON", "satellite", **self.catalog)
        with self.assertRaises(ValueError):
            load_user_catalog("unknown", **self.catalog)
