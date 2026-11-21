# Satellite Conjunction Explorer

A hackathon simulator for satellite–debris close approaches. The offline Streamlit demo screens SCD 2 against a frozen set of 581 COSMOS 2251 debris objects. Choose an encounter and press **Play** to watch both objects move. Switch between the **3D orbit** and **3D close-up** views. Drag to rotate the close-up while the separation graph tracks playback. Turn on **Simulate an impact** to see an illustrative contact at closest approach.

## Run locally

Use Python 3.12 from the repository root.

```bash
python3.12 -m venv venv
source venv/bin/activate
python -m pip install -r requirements.txt
streamlit run app.py
```

Run `pytest` for the offline tests. See the [contributor handoff](docs/HANDOFF.md) and [orbit validation notes](docs/ORBITS_PLAN.md).

## Modeling assumptions

- The demo uses public CelesTrak GP elements propagated with SGP4. Positions and velocities are in TEME, times are UTC, and miss distances are in km.
- The demo window is 48 hours with a 5 km screening threshold. Refined times and miss distances are predictions for the saved elements.
- Public GP elements provide no covariance. The planned risk model assumes 1 km isotropic position uncertainty and a 2D Gaussian encounter plane. The planned maneuver model uses one along-track impulse before closest approach and the rocket equation, with demo defaults of 500 kg and 220 s of specific impulse.
