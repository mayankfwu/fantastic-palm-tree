# ORBITGUARD · Satellite Conjunction Explorer

ORBITGUARD is a Streamlit simulator built for the ASTRA 2026 hackathon. It predicts close approaches between satellites and debris, estimates collision probability, and compares avoidance maneuvers and their estimated propellant cost. The interactive 3D player lets you inspect a predicted pass or watch a satellite maneuver around staged debris. The bundled demo runs offline after setup.

## Reviewer quick start

Install **Python 3.12**, download or clone this repository, and extract it if you downloaded a ZIP. Open a terminal in the folder containing `run_demo.py` and run the command for your system.

| System | Launch the demo |
| --- | --- |
| Windows (PowerShell or Command Prompt) | `py -3.12 run_demo.py` |
| macOS or Linux | `python3.12 run_demo.py` |

The [launcher](run_demo.py) creates the project environment, installs any missing dependencies, and opens **Offline catalog** with bundled data. Run it once with internet access before an offline review. Subsequent launches reuse the installed packages.

Open the local URL printed in the terminal if your browser does not open automatically. Leave the terminal running while you review, then press **Ctrl+C** to stop. To see a satellite avoid debris, follow the [three-step evaluator walkthrough](#quick-demo-for-evaluators).

## Manual setup

Use Python 3.12 and run these commands from the repository root.

**Linux or macOS**

```bash
python3.12 -m venv venv
./venv/bin/python -m pip install -r requirements.txt
./venv/bin/python -m streamlit run app.py
```

**Windows PowerShell**

```powershell
py -3.12 -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe -m streamlit run app.py
```

Open [localhost:8501](http://localhost:8501) if Streamlit does not open your browser automatically. Install the dependencies before going offline.

## Quick demo for evaluators

1. Leave **Demo mode** on and select **Guided replay**. Under **Encounter to inspect**, choose debris **34387**, the closest predicted pass. Select **3D close-up** to watch the objects move and see the separation graph update.
2. Turn on **Simulate an impact** to stage a collision and pause on contact. Keep it on and enable **Apply avoidance maneuver** to replay the staged encounter with a burn that changes the satellite’s trajectory. The replay overlays its original path for comparison.
3. Scroll to **Risk Assessment & Avoidance Planning** below the visualization. Compare the estimated collision probability, suggested burn time, Δv, and propellant cost for the two catalog encounters. The panel uses the selected catalog prediction when the illustrative impact is enabled.

The frozen scenario screens **SCD 2** (NORAD **25504**) against **581 COSMOS 2251 debris records** over 48 hours starting **2026-11-21 19:00 UTC**. The screening radius is 5 km. The table is ranked by predicted miss distance.

| Debris NORAD ID | Closest approach (UTC) | Miss distance (km) | Relative speed (km/s) |
| --- | --- | ---: | ---: |
| 34387 | 2026-11-23 14:02:52.912 | 0.662 | 10.327 |
| 36048 | 2026-11-23 04:30:43.085 | 3.517 | 11.074 |

## Explore the catalogs

| Mode | How to start | Data |
| --- | --- | --- |
| **Offline catalog** | Opens by default with **Demo mode** on | SCD 2, ISS (ZARYA), CSS (TIANHE), and the bundled COSMOS 2251 debris snapshot |
| **Guided replay** | Leave **Demo mode** on and choose **Guided replay** | The two frozen SCD 2 encounters |
| **Live catalog** | Turn off **Demo mode** and choose a satellite catalog and debris group | CelesTrak GP data for space stations, Earth resources, or active satellites, with debris from COSMOS 2251, IRIDIUM 33, or FENGYUN 1C |

In either catalog mode, search **Add satellites** by name or NORAD ID and select one or more satellites. Set **Number of debris objects** to sample the chosen group. The default is 10 when enough records are available. Click **Resample debris** to draw a new set. To look for predicted encounters, choose **Satellite to screen** and click **Screen next 24 hours**. This checks one primary against the sampled catalog debris. The **Screening radius (km)** controls which predicted passes appear in the results and defaults to 50 km in catalog mode.

The full-orbit player runs at an accelerated rate through successive simulation windows and pauses at detected contact within the assumed **10 m** combined radius. Drag to rotate during playback. Use **Follow satellite** to select a satellite and show its TEME velocity and local trajectory. **Follow** keeps Earth in view, and **3D close-up** zooms in on the satellite. Debris starts with short trails. Turn on **Show full debris orbits** to see the full paths. **Slow near encounters** starts on and returns playback to your selected speed after the pass.

To demonstrate an avoidance event in either catalog mode, set **Add simulated debris** to 1–15. It defaults to 0. The pink objects follow staged trajectories and are excluded from catalog screening. **Avoid simulated debris** is enabled by default. The simulator tries a burn for each affected satellite and checks its closest approach to each staged object. The **Avoidance close-up** and **3D encounter** windows show the result and separation graph during the pass. Turn avoidance off to replay the staged contact.

**Successful avoidance requires at least 5 km of separation at closest approach.** A pass above 10 m but below 5 km is an unsafe close pass and playback continues. At or below 10 m the simulator registers contact and pauses. These rules also apply when you change the burn manually in Guided replay. The catalog screening radius controls which passes are listed and can be adjusted independently.

Live catalog downloads are cached for two hours in `data/cache/`. Concurrent sessions in one app process share the download for a group. If a refresh fails, the loader can reuse a valid older cache. When a group is unavailable, the dashboard waits 60 seconds before another attempt for that group in the same session. Both demo views use bundled fixtures and require no catalog download.

## Models and limitations

- **Orbit prediction.** Public CelesTrak GP elements use JSON with OMM fields. SGP4 propagates them in TEME (True Equator, Mean Equinox) with positions in km, velocities in km/s, and times in UTC. Screening filters by radial range, searches for candidate minima on a time grid, and refines their times and separations between samples. The demo flags elements older than three days because predictions become less reliable farther from the element epoch. [Orbit screening and validation notes](docs/ORBITS_PLAN.md)
- **Collision probability.** The 2D Gaussian encounter-plane model uses an assumed isotropic position uncertainty of **1 km** and an assumed combined collision radius of **0.01 km**. Public GP elements provide no covariance. The display labels probabilities **Low** below 0.001%, **Elevated** from 0.001% to below 0.01%, and **High** at 0.01% or higher. With the current assumptions, even a zero predicted miss gives about **0.005%**, in the Elevated band.
- **Maneuver planning and fuel.** The planner estimates an along-track burn and a post-burn miss distance with a linear model and a **5 km** target. For archived encounters it uses the scenario’s lead time. Propellant cost comes from the rocket equation with adjustable defaults of **500 kg** spacecraft mass and **220 s** specific impulse. The panel shows **0 kg** when no burn is required.
- **Avoidance visualization.** The burn replay applies a separate illustrative velocity change along the flight path. The default **+10 m/s** is applied over **60 simulated seconds**, followed later by an idealized **30-minute** recovery toward the original trajectory. The fuel panel estimates the planner’s burn only. During continuous playback, the simulator rechecks staged encounters and catalog passes found within 5 km of the original trajectory. A burn could introduce an encounter outside that candidate set. These models are for demonstration and lack the validation required for operational flight decisions.

## Tests and repository layout

Run the offline test suite from the repository root after installing dependencies.

```bash
./venv/bin/python -m pytest -q
```

On Windows, use `.\venv\Scripts\python.exe -m pytest -q`. The suite covers catalog loading and caching, propagation, screening and frozen replay, risk and fuel estimates, and the Streamlit integration. With Node.js 18 or newer on the path, pytest also exercises the JavaScript playback clock.

| Path | Purpose |
| --- | --- |
| [`app.py`](app.py) and [`src/viz/`](src/viz/) | Streamlit dashboard and interactive 3D player |
| [`src/orbits/`](src/orbits/) | Catalogs, SGP4 propagation, screening, and simulated trajectories |
| [`src/risk/`](src/risk/) and [`src/maneuver/`](src/maneuver/) | Collision probability, maneuver planning, and propellant estimates |
| [`src/contracts.py`](src/contracts.py) | Shared conjunction and maneuver data classes |
| [`data/fixtures/`](data/fixtures/) | Frozen catalog snapshots and development fixtures |
| [`tests/`](tests/) | Offline regression and integration tests |

See the [contributor handoff](docs/HANDOFF.md) for implementation status and [AGENTS.md](AGENTS.md) for ownership and shared interfaces.
