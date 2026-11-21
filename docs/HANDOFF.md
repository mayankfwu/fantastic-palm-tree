# Contributor handoff

This hackathon project simulates satellite–debris encounters. The Streamlit dashboard integrates the orbit backend with the collision risk and maneuver models on `main`.

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
- Owner A hardening rejects non-finite SGP4 positions or velocities during both grid propagation and refinement. HTTP 200 responses must contain usable orbital elements before replacing the local catalog cache. The orbit view uses a spherical Earth in the same TEME coordinates as the trajectories.
- When a refresh fails, the loader logs a warning and uses an expired cache that still contains usable elements, preserving its timestamp. A non-JSON response without a usable cache raises a group-specific error. This SGP4 integration supports NORAD catalog IDs from 1 to 339999.
- Concurrent sessions in one process now serialize downloads per group. Closest-approach refinement uses time relative to the nearby grid sample so the solver retains precision late in a long window. An independent 5-second scan with local millisecond refinement confirmed both saved encounters across all 581 debris objects.

## Owner B — Collision risk and maneuvers

- Start with [fake_conjunction.json](../data/fixtures/fake_conjunction.json). Parse `tca` with `datetime.fromisoformat()` before constructing a `Conjunction`. The offline replay returns real-data `Conjunction` objects for integration.
- `b-risk-maneuver` implements `collision_probability`, `plan_maneuver`, and `fuel_used` with the signatures in [AGENTS.md](../AGENTS.md). The current planner is a linear along-track estimate. The dashboard uses the scenario's lead time for an archived encounter because the planner expects a future TCA relative to its wall clock.
- The selected encounter panel shows probability in percent using 1 km assumed isotropic uncertainty and a 0.01 km assumed combined collision radius. Demo risk bands are Low below 0.001%, Elevated from 0.001% to below 0.01%, and High at or above 0.01%. These bands are display conventions for the hackathon.
- The planner recommendation gives the UTC burn time, signed Δv, and estimated post-burn miss against a 5 km target. The linear recommendation is for demonstration only. Its inputs are the primary and conjunction, and orbit propagation for an illustrative burn is handled separately in the replay. Fuel uses adjustable defaults of 500 kg and 220 s. A zero-Δv recommendation displays 0 kg without calling the fuel model.
- Use the agreed demo assumptions, including 1 km isotropic position uncertainty and a 5 km safe miss threshold. Return the [shared dataclasses](../src/contracts.py) with the documented units.

## Owner C — Streamlit and visualization

- The Streamlit app shows the frozen SCD 2 scenario and a ranked encounter table. The selected encounter drives a slow-motion 3D animation in satellite-relative km, a zoomed-out orbit view with a solid Earth in TEME km, and a separation chart in seconds from closest approach.
- The 3D orbit view opens first. Both objects move in both views. The close-up draws a shaded Earth backdrop behind the encounter paths while the grid retains its local km scale. The illustrative impact option shifts the debris path to meet the satellite at closest approach and stops playback there. The ranked table always shows the orbital predictions.
- The close-up updates the object positions and the separation graph marker together while the camera remains interactive.
- The full orbit uses the same drag and arrow-key controls during playback. Earth is shaded and hides objects on its far side.
- The player advances by simulated seconds at the selected rate and interpolates between propagation samples. Dense samples around a burn improve resolution while the playback clock keeps its rate. Contact uses the exact saved sample. Large debris sets use fewer background path points and a lower redraw rate.
- **Slow near encounters** temporarily slows playback around catalog passes within 5 km and staged debris passes, then restores the chosen speed. Around a successfully avoided staged impact, the right-side **Avoidance close-up** and the lower **3D encounter** window appear together. The lower window shows a gridded close-up and a separation graph that follows the same playback time.
- The full-orbit player has a **Follow satellite** selector and two tracking cameras. **Follow** keeps the satellite and Earth in view. **3D close-up** uses adaptive local zoom and a 10 km scale. Both show bottom-left TEME velocity and trajectory. Playback speed can be adjusted from 0.01× to 2×, including in Live mode. Offline avoidance adds one-second samples near each affected satellite's first staged encounter and draws its original path as a reference while followed.
- The app caches ranked screening results across sessions with `st.cache_data` and keeps mutable SGP4 models in session state. It shows the count of debris element sets older than three days at the window start and the age of both selected objects' elements at closest approach. All snapshot records remain in the replay.
- Turn off **Demo mode** for live CelesTrak catalogs. Search by satellite name or NORAD ID, add multiple satellites to the 3D scene, and choose a debris group and a random sample size. Resampling changes the session seed. The scene shows short debris trails when full debris orbits are hidden. Live screening uses one selected primary against the sampled debris.
- In **Demo mode**, **Offline catalog** uses the SCD 2 and COSMOS 2251 fixtures plus bundled ISS and Tianhe records from the CelesTrak stations group. The selectable catalog and screening use the frozen scenario start and require no network or local download cache.
- Full-orbit playback auto-starts in the guided, offline catalog, and live modes. A local Streamlit component streams successive SGP4 windows without resetting the scene or requesting fresh GP data. It stops at the earliest screened closest approach within an assumed 10 m combined radius. The guided close-up loops the selected near miss and stops on a scripted impact.
- Live mode shows elapsed time and Play/Pause controls. The time slider is available in the demo views.
- The 3D orbit offers up to 15 seed-randomized, pink simulated debris objects with staged contacts. Each follows an independent two-body ellipse with a randomized orbital plane and speed. The objects are kept out of catalog screening. Playback stops at the first staged or predicted contact.
- Offline catalog and Live mode enable staged-debris avoidance by default. Both apply an illustrative +10 m/s burn over 60 seconds before each affected satellite's first staged contact, then recheck separation within two minutes of the original contact times. Five minutes after the satellite's last staged contact, a 30-minute guided recovery returns it to the nominal position and velocity. The toggle can restore the collision snapshot.
- Catalog views default to 10 sampled debris objects when available and 0 simulated debris objects.
- The rolling scene reads avoidance from scene-keyed session state. Its fragment call uses the original arguments so a cached fragment does not receive an unexpected avoidance keyword.
- **Apply avoidance maneuver** replays a selected catalog or guided encounter with a signed along-track velocity change. The preview defaults to +10 m/s and begins the finite burn 20 minutes before closest approach when the scenario allows it. It overlays the original path and shows burn, coast, recovery, and rejoin phases. Recovery is an idealized guidance profile separate from the Part B fuel estimate. Contact pauses playback on the contact snapshot.
- User-uploaded debris remains deferred. For that workflow, call `import_user_omm(upload.getvalue(), kind)`, surface validation errors, and place preferred elements first when a NORAD ID appears more than once.
- Codex completed the evaluator README and added regressions for failed catalog retries, co-orbiting objects in close-up, and delayed playback windows. The dashboard waits 60 seconds between attempts for an unavailable group. Closest-pass previews now propagate the coarse samples in a batch. The suite passed 57 tests and 3 subtests. Firefox exercised guided impact and avoidance, both staged encounter panels, and tracking beyond the first 100-minute window. Live mode screened SCD 2 against 50 debris using the CelesTrak download cache and displayed the risk and fuel results.

### Future continuous simulation

- Offer a real-time playback speed. Continuous full-orbit playback currently runs at accelerated speed.
- Screen a rolling window ahead of the clock. Recheck projected approaches after each avoidance maneuver using the updated satellite trajectory.
- Use Owner B's risk and maneuver models to trigger and apply simulated avoidance burns. Display the predicted encounter, commanded burn, and updated miss distance. Keep this workflow in the simulator.

## Next three tasks

1. Coordinate with Owner B on direct API validation. The risk, fuel, and planning functions can accept non-finite inputs, and the planner accepts a timezone-naive TCA.
2. Review post-burn screening for previously distant debris entering the 5 km candidate set after a maneuver.
3. Rehearse the offline walkthrough and explain the linear burn model and its lead-time assumption.

Codex implemented the Owner A backend, fixtures, and validation tests, then added the Streamlit interface and plots. The demo reproduced the published SOCRATES miss distance to its displayed precision when screened using the same reference elements. The Part B tests cover both guided encounters, safe encounters, adjustable fuel inputs, and planner errors.
