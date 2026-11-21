# ORBITGUARD · Satellite Conjunction Explorer

A hackathon simulator for satellite–debris close approaches. The offline Streamlit demo screens SCD 2 against a frozen set of 581 COSMOS 2251 debris objects. The **3D orbit** starts automatically and advances through successive propagation windows. Drag to rotate during playback. The **3D close-up** replays the selected encounter with a separation graph. Turn on **Simulate an impact** to see an illustrative contact that stops playback.

## Run locally

Use Python 3.12 from the repository root.

```bash
python3.12 -m venv venv
source venv/bin/activate
python -m pip install -r requirements.txt
streamlit run app.py
```

Run `pytest` for the offline tests. See the [contributor handoff](docs/HANDOFF.md) and [orbit validation notes](docs/ORBITS_PLAN.md).

## Choose an offline or live catalog

For evaluation without a connection, keep **Demo mode** on and select **Offline catalog**. It bundles SCD 2, ISS (ZARYA), CSS (TIANHE), and 581 COSMOS 2251 debris objects from CelesTrak. Select one or more satellites and sample the debris as usual. The bundled elements replay from a fixed UTC start. **Guided replay** opens the two saved SCD 2 encounters directly.

Turn off **Demo mode** in the sidebar. Search **Add satellites** by name or NORAD ID and select one or more. Pick a debris group and a count, then use **Resample debris** to draw another random sample. The 3D player shows all selected objects. Turn off **Show full debris orbits** in the player to see only short debris trails. To screen ahead, choose one of your satellites and click **Screen next 24 hours**. Playback advances at accelerated speed from the UTC scenario start. It stops at a predicted contact using an assumed 10 m combined radius.

## Modeling assumptions

To preview avoidance, select an encounter and turn on **Apply avoidance maneuver**. The default +10 m/s along-track change is applied gradually over 60 seconds. A negative Δv slows the satellite. After passing the debris, a 30-minute guided recovery brings the satellite back to the nominal SGP4 position and velocity. The gray dashed line shows the original path. The app recomputes the miss within two minutes of the original closest approach. This illustrative recovery uses idealized guidance, and the Part B fuel estimate covers its separate linear maneuver recommendation.

Use **Add simulated debris** in the sidebar to add up to 15 pink objects to the 3D orbit. **Avoid simulated debris** is on by default in **Offline catalog** and **Live mode**. The replay applies a +10 m/s along-track burn before the first staged encounter for each affected satellite and rechecks separation near the original contact times. Turn avoidance off to show the staged impact. These settings affect playback only.

- The demo uses public CelesTrak GP elements propagated with SGP4. Positions and velocities are in TEME, times are UTC, and miss distances are in km.
- The demo window is 48 hours with a 5 km screening threshold. Refined times and miss distances are predictions for the saved elements.
- **Risk Assessment & Avoidance Planning** uses Part B once `b-risk-maneuver` is merged. Collision probability uses a 2D Gaussian encounter-plane model with assumed isotropic uncertainty of **1 km** and an assumed combined collision radius of **0.01 km**. Public GP elements provide no covariance. Demo risk bands are **Low** below 0.001%, **Elevated** from 0.001% to below 0.01%, and **High** at or above 0.01%.
- The Part B planner estimates one along-track burn with a **5 km** target miss. It accepts the primary and conjunction and gives a linear miss estimate for demonstration only. The separate **Apply avoidance maneuver** replay propagates a user-selected illustrative burn. Archived events use the scenario start as their planning clock.
- Fuel estimation uses the rocket equation with adjustable defaults of **500 kg** spacecraft mass and **220 s** specific impulse. When no maneuver is required, the dashboard shows **0 kg**.
