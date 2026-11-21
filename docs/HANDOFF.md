# Contributor handoff

This hackathon project simulates satellite–debris encounters. Owner A's orbit and data backend is ready for integration. Collision risk, avoidance maneuvers, and the Streamlit app are the next pieces.

Read [AGENTS.md](../AGENTS.md) for folder ownership and the shared interfaces. The [orbit plan and validation notes](ORBITS_PLAN.md) explain the screening approach and the comparison against CelesTrak SOCRATES Plus.

## Run the offline demo

From the repository root, use Python 3.12. For a fresh checkout, install the dependencies needed by the orbit backend and its tests.

```bash
python3.12 -m venv venv
source venv/bin/activate
python -m pip install numpy requests scipy sgp4 pytest
python -m pytest -q
python -c 'from src.orbits.demo import replay_demo; print(*replay_demo(), sep="\n")'
```

The [frozen scenario](../data/fixtures/demo_scd2.json) uses SCD 2 and [581 COSMOS 2251 debris records](../data/fixtures/demo_cosmos_2251.json). It replays a fixed 48-hour window beginning on 2026-11-21 at 19:00 UTC. Both the demo and the test suite run offline after dependency installation.

| Secondary NORAD ID | Time of closest approach (UTC) | Miss distance (km) |
| --- | --- | ---: |
| 34387 | 2026-11-23 14:02:52.912 | 0.662 |
| 36048 | 2026-11-23 04:30:43.085 | 3.517 |

## Owner A — Orbits and data

- `from src.orbits import load_catalog, propagate, find_conjunctions`. The loader fetches CelesTrak GP JSON and caches each group locally for two hours. Propagation accepts timezone-aware UTC times and returns TEME positions in km and velocities in km/s. Failed samples become NaN. Screening sorts encounters by increasing miss distance.
- `from src.orbits.user_catalog import import_user_omm, load_user_catalog`. Import a JSON OMM object or array as `"satellite"` or `"debris"`. Import validates the whole batch before saving to SQLite. Reimporting the same NORAD ID in the same category replaces its orbital elements. Loading returns a list of SGP4 `Satrec` objects.
- The local SQLite catalog and CelesTrak download cache are gitignored. The demo fixtures and offline test inputs belong in Git. The radial filter and time grid approximate continuous screening. Public GP data provides no covariance.

## Owner B — Collision risk and maneuvers

- Start with [fake_conjunction.json](../data/fixtures/fake_conjunction.json). Parse `tca` with `datetime.fromisoformat()` before constructing a `Conjunction`. The offline replay returns real-data `Conjunction` objects for integration.
- Implement `collision_probability`, `plan_maneuver`, and `fuel_used` under `src/risk/` and `src/maneuver/` using the signatures in [AGENTS.md](../AGENTS.md). The maneuver planner needs the primary's `Satrec` along with the conjunction. The frozen primary OMM record is in the scenario fixture.
- Use the agreed demo assumptions, including 1 km isotropic position uncertainty and a 5 km safe miss threshold. Return the [shared dataclasses](../src/contracts.py) with the documented units.

## Owner C — Streamlit and visualization

- Start the demo view with `replay_demo()` so it can show ranked encounters without a network connection. Use the frozen scenario start and label times UTC and propagated vectors TEME.
- Connect the upload control to `import_user_omm(upload.getvalue(), kind)`. Show validation errors and confirm the imported NORAD IDs on success. Load imported satellites into the primary picker and imported debris into the screening catalog.
- When combining live and imported debris, put the preferred elements first for any duplicate NORAD ID. Screening uses the first occurrence. Wire in Owner B's risk, burn, and fuel outputs when they are ready.

## Next three tasks

1. Owner B implements risk and maneuver calculations against the fake fixture.
2. Owner C renders the frozen demo and connects local OMM uploads.
3. Owners A, B, and C verify that a selected encounter flows from screening through the risk and maneuver calculations to the app, then rehearse the offline demo.

Codex implemented the Owner A backend, fixtures, and validation tests. The demo reproduced the published SOCRATES miss distance to its displayed precision when screened using the same reference elements.
