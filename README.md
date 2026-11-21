# Satellite Conjunction Explorer

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

Use **Add simulated debris** in the sidebar to add up to 15 illustrative objects to the 3D orbit. **Randomize simulated debris** changes their orbital paths and staged contact times. They appear in pink. These staged contacts affect playback only.

- The demo uses public CelesTrak GP elements propagated with SGP4. Positions and velocities are in TEME, times are UTC, and miss distances are in km.
- The demo window is 48 hours with a 5 km screening threshold. Refined times and miss distances are predictions for the saved elements.
- Public GP elements provide no covariance. The planned risk model assumes 1 km isotropic position uncertainty and a 2D Gaussian encounter plane. The planned maneuver model uses one along-track impulse before closest approach and the rocket equation, with demo defaults of 500 kg and 220 s of specific impulse.
