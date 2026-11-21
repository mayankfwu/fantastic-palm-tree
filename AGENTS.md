# AGENTS.md

## Project
Satellite–debris collision avoidance simulator (hackathon project, team of 3).

For a chosen satellite, the app finds predicted close approaches with debris, estimates collision probability, plans an avoidance burn that uses the minimum Δv (fuel), and shows everything in a Streamlit demo.

**Read first:** this file, then `docs/HANDOFF.md` (current status and next tasks). The full plan is in `docs/PLAN.md`.

## Stack and commands
- Python 3.12, virtual environment at `./venv` (never commit it)
- Libraries: `sgp4`, `requests`, `numpy`, `pandas`, `plotly`, `streamlit`, `scipy`, `pytest`
- Setup: `python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt`
- Run the app: `streamlit run app.py`
- Run tests: `pytest`

## Folder ownership
One owner per folder. Do not edit another owner's folder; ask the owner instead.

| Owner | Folders | Responsibility |
|---|---|---|
| A | `src/orbits/` | CelesTrak loader, SGP4 propagation, conjunction screening, TCA and miss distance |
| B | `src/risk/`, `src/maneuver/` | Collision probability, burn optimizer, fuel (rocket equation), burn-now vs burn-later |
| C | `app.py`, `src/viz/`, `docs/`, `README.md` | Streamlit app, Plotly charts and 3D orbits, docs, demo |

Shared file `src/contracts.py` holds the data classes and function signatures below. Change it only by agreement of all three owners, and update this file in the same commit.

## Shared contract
```python
from dataclasses import dataclass
from datetime import datetime

@dataclass
class Conjunction:
    primary_id: int        # NORAD catalog number
    secondary_id: int
    tca: datetime          # time of closest approach, UTC
    miss_km: float         # miss distance at TCA
    rel_speed_kms: float   # relative speed at TCA

@dataclass
class Maneuver:
    burn_time: datetime    # UTC
    dv_mps: float          # along-track impulsive burn, positive = prograde
    new_miss_km: float     # miss distance after the burn
```

Function signatures (implement exactly these; return types matter):
```python
# Owner A  (src/orbits/)
def load_catalog(group: str) -> list:                      # list of sgp4 Satrec objects
def propagate(sat, times: list[datetime]):                 # -> (positions (N,3) km, velocities (N,3) km/s), TEME frame
def find_conjunctions(primary, catalog: list, start: datetime, hours: float,
                      step_s: float = 60.0, screen_km: float = 50.0) -> list[Conjunction]

# Owner B  (src/risk/, src/maneuver/)
def collision_probability(miss_km: float, sigma_km: float, combined_radius_km: float) -> float
def plan_maneuver(primary, conjunction: Conjunction, threshold_km: float = 5.0) -> Maneuver
def fuel_used(dv_mps: float, mass_kg: float, isp_s: float) -> float   # kg of propellant
```

## Units and conventions
- Distances in **km**, velocities in **km/s**, Δv in **m/s**, mass in **kg**, Isp in **s**.
- All times are timezone-aware **UTC** datetimes.
- SGP4 output frame is TEME. Do not mix frames without converting.
- Every function gets a docstring that states its units.

## Data
- Source: CelesTrak GP data, requested in **JSON/OMM format** (not raw TLE text; TLE format is being retired for new catalog numbers). Check CelesTrak's GP data-formats documentation for the exact request URL.
- Debris groups to start with: `cosmos-2251-debris`, `iridium-33-debris`, `fengyun-1c-debris`.
- Use `requests` with a timeout. Cache downloads in `data/cache/` (gitignored) so the server is not hit repeatedly.
- A fixed fake conjunction for development lives in `data/fixtures/fake_conjunction.json`, so B and C are never blocked on A.

## Modeling assumptions (placeholders, state them openly in the README and pitch)
- Public GP/TLE data has no covariance. Use an assumed isotropic position uncertainty `SIGMA_KM = 1.0` for Pc.
- Safe miss-distance threshold `THRESHOLD_KM = 5.0`.
- MVP maneuver: a single impulsive along-track burn before TCA. A Clohessy-Wiltshire model is a stretch goal.
- Fuel from the rocket equation. Demo defaults (adjustable in the UI): mass 500 kg, Isp 220 s.
- Pc uses a simple 2D Gaussian approach in the encounter plane. Document the simplifications.

## Rules for AI assistants
1. **No copied code.** Do not copy or adapt code from other collision-avoidance or conjunction-analysis projects, tutorials, or repositories. Use libraries (`sgp4`, `numpy`, `scipy`, etc.) and standard published equations only, written from scratch.
2. Keep functions small, readable, and commented, so a student can explain every line to judges.
3. Stay inside your owner's folders and keep the shared contract unchanged unless told otherwise.
4. Ask before adding a new dependency. If one is added, update `requirements.txt`.
5. Never commit secrets, `.env`, `venv/`, or `.idea/`. Never put API keys in code.
6. Write or update a test for every function you add (`tests/`). Run `pytest` before finishing.
7. Do not run destructive commands (`rm -rf`, `git reset --hard`, force push) without explicit approval.
8. At the end of each session, update your section of `docs/HANDOFF.md` (done, in progress, blocked, next 3 tasks, decisions, what the AI wrote).

## Folder layout
```
AGENTS.md
README.md
app.py
requirements.txt
src/
  contracts.py
  orbits/
  risk/
  maneuver/
  viz/
tests/
data/
  fixtures/fake_conjunction.json
  cache/            (gitignored)
docs/
  PLAN.md
  HANDOFF.md
```