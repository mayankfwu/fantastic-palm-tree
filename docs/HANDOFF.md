# Contributor handoff

This hackathon project simulates satellite–debris encounters. Owner A's backend and Owner C's single-satellite Streamlit demo are working. Collision risk and avoidance maneuvers are the next pieces.

Read [AGENTS.md](../AGENTS.md) for folder ownership and the shared interfaces. The [orbit plan and validation notes](ORBITS_PLAN.md) explain the screening approach and the comparison against CelesTrak SOCRATES Plus.

## Run the offline demo

From the repository root, use Python 3.12. Set up the environment and start Streamlit.

```bash
python3.12 -m venv venv
source venv/bin/activate
python -m pip install -r requirements.txt
python -m pytest -q
streamlit run app.py
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

- The Streamlit app shows the frozen SCD 2 scenario and a ranked encounter table. The selected encounter drives a slow-motion 3D animation in satellite-relative km, a zoomed-out orbit view with a solid Earth in TEME km, and a separation chart in seconds from closest approach.
- The 3D orbit view opens first. Both objects move in both views. Both 3D views hide background axes and grids. The illustrative impact option shifts the debris path to meet the satellite at closest approach and stops playback there. The ranked table always shows the orbital predictions.
- The close-up updates the object positions and the separation graph marker together while the camera remains interactive.
- The full orbit uses the same drag and arrow-key controls during playback. Earth is shaded and hides objects on its far side.
- The app keeps the propagated models and ranked results in Streamlit session state so selecting a different encounter avoids rerunning screening. `load_demo_scenario()` exposes the snapshot settings and models for reuse.
- Multi-satellite selection and user-uploaded debris are deferred. For that future workflow, call `import_user_omm(upload.getvalue(), kind)`, surface validation errors, and place preferred elements first when a NORAD ID appears more than once.

### Future continuous simulation

- Advance a continuous simulation clock at real-time speed by default. Live views should follow that clock without requiring a time slider.
- Screen a rolling window ahead of the clock. Recheck projected approaches after each avoidance maneuver using the updated satellite trajectory.
- Use Owner B's risk and maneuver models to trigger and apply simulated avoidance burns. Display the predicted encounter, commanded burn, and updated miss distance. Keep this workflow in the simulator.

## Next three tasks

1. Owner B implements risk and maneuver calculations against the fake fixture.
2. Owner C adds collision probability, maneuver, and fuel results to the selected encounter after Owner B's interfaces are available.
3. Owners A, B, and C verify the integrated flow and rehearse the offline demo.

Codex implemented the Owner A backend, fixtures, and validation tests, then added the Streamlit interface, Plotly visualizations, and a test that switches between both encounters. The demo reproduced the published SOCRATES miss distance to its displayed precision when screened using the same reference elements.
