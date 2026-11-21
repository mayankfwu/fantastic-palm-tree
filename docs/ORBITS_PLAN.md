# Owner A implementation plan

Deliver a CelesTrak catalog loader, SGP4 positions and velocities over time, and a ranked list of real conjunctions for the demo satellite. Keep the interfaces and units in `AGENTS.md`.

## Step 0 — Shared contract and fake fixture

- Create `src/contracts.py` with the `Conjunction` and `Maneuver` dataclasses defined in `AGENTS.md`.
- Create `data/fixtures/fake_conjunction.json` with matching `Conjunction` fields, an ISO 8601 UTC TCA, and clearly synthetic values. Give it to Owners B and C so they can start independently.

## Step 1 — Catalog loader

- Implement `load_catalog(group)`. Request `https://celestrak.org/NORAD/elements/gp.php?GROUP=cosmos-2251-debris&FORMAT=JSON` with the requested group substituted. The other starting groups are `iridium-33-debris` and `fengyun-1c-debris`. JSON uses OMM field names and supports catalog IDs beyond the five-digit TLE range. [CelesTrak GP data formats](https://celestrak.org/NORAD/documentation/gp-data-formats.php)
- Use `sgp4.omm` to build `Satrec` objects. Reuse the existing OMM conversion in `src/orbits/user_catalog.py` where appropriate. Skip and log individual invalid records. [SGP4 package documentation](https://pypi.org/project/sgp4/)
- Store successful downloads with a timestamp in gitignored `data/cache/`. Reuse cached data for two hours. Set a timeout and require HTTP 200. Limit retries to transient connection or server failures, with at most two retries. Stop on redirects, blocked requests, invalid groups, and rate limits. [CelesTrak usage policy](https://celestrak.org/usage-policy.php)
- Save a small JSON sample under `tests/`. Test successful conversion, malformed records, cache freshness, and request failures offline.

## Step 2 — Propagation

- Implement `propagate(sat, times)` using split Julian dates and the SGP4 array API. Accept timezone-aware UTC times. Return TEME position and velocity arrays of shape `(N, 3)` in km and km/s.
- Set both rows to NaN whenever SGP4 returns an error for that time. Warn when requested propagation times are more than about three days from the elements' epoch.
- Test dimensions, error handling, and an ISS-like orbit with radius around 6,780 km and speed around 7.7 km/s.

## Step 3 — Conjunction screening

- Implement `find_conjunctions` with the signature in `AGENTS.md`. Skip objects with the primary's NORAD ID. Apply a cheap, conservative radial-range filter using mean motion and eccentricity before propagating the remaining debris.
- Compute distances over the requested time grid with NumPy. Start demo tuning around 30-second steps over 24–72 hours.
- Identify local minima and check the search-window endpoints. Use 100–200 km as an initial coarse threshold for suitable step sizes. At 10–15 km/s relative speed, a close approach can be hundreds of km from a sampled point. Scale the candidate threshold with grid spacing and verify that a between-sample encounter survives candidate selection.
- Refine candidates with bounded `scipy.optimize.minimize_scalar` on squared separation between neighboring samples. Evaluate the state vectors at refined TCA, calculate relative speed, and keep encounters with `miss_km < screen_km`. Rank by increasing miss distance.
- Test a between-sample encounter, self-pair exclusion, and invalid propagation. Keep KD-trees for a future all-vs-all search.

## Step 4 — Freeze a demo scenario

- Screen candidate satellites near the debris altitude range, roughly 700–850 km. Choose a satellite with a real predicted close approach in the next few days.
- Save the exact input OMM records, screening start in UTC, search settings, and ranked output. Replay from the saved inputs without network access.
- Make the local user catalog available alongside downloaded objects so Owner C can offer imported satellites in the primary picker and imported debris in screening.

## Step 5 — Validate and deliver

- Compare a matching pair against [CelesTrak SOCRATES Plus](https://celestrak.org/SOCRATES/), which is available. Record the compared input epochs and any differences in TCA and miss distance.
- Check that distance varies smoothly near the minimum and that an interior refined TCA lands within its grid bracket. Time the offline demo replay.
- Give Owners B and C the frozen scenario, ranked conjunctions, runtime, and integration notes. Provide Owner C with the assumptions and limitations for the README.

## Session order

1. Create the shared contract and synthetic fixture.
2. Implement and test the offline-backed catalog loader and cache.
3. Implement and test vectorized propagation.
4. Implement and test conjunction screening and TCA refinement.
5. Freeze and validate the demo case.

Review the diff and commit each task separately so it can be explained at the demo.

## Definition of done

- All three functions match the signatures in `AGENTS.md`.
- `pytest` passes offline.
- The saved demo produces a ranked conjunction list in a few seconds.
- Docstrings state km, km/s, and UTC where applicable and label position and velocity vectors as TEME.

## Implemented demo and validation

Run the offline replay from the repository root with the project interpreter.

```bash
venv/bin/python -c 'from src.orbits.demo import replay_demo; print(*replay_demo(), sep="\n")'
venv/bin/pytest
```

The fixture screens SCD 2 (NORAD 25504, approximately 745 km mean altitude) against 581 COSMOS 2251 debris objects for 48 hours from **2026-11-21 19:00 UTC**, using a 30-second grid and a 5 km screen. The snapshot consists of `data/fixtures/demo_scd2.json` and `data/fixtures/demo_cosmos_2251.json`. A fixed start makes the result reproducible after the encounter date.

| Secondary NORAD ID | Refined TCA (UTC) | Miss (km) | Relative speed (km/s) |
| --- | --- | ---: | ---: |
| 34387 | 2026-11-23 14:02:52.912 | 0.662 | 10.327 |
| 36048 | 2026-11-23 04:30:43.085 | 3.517 | 11.074 |

SOCRATES Plus reported **2026-11-23 14:02:52.908 UTC**, **0.625 km**, and **10.327 km/s** for the closest pair in its November 20 run. The newer demo elements shift the TCA by about 4 milliseconds and the miss by about 37 meters. Screening the exact SOCRATES input elements reproduces its published TCA and miss to the displayed precision. The offline test suite checks both the frozen demo and the published comparison. [SOCRATES pair report](https://celestrak.org/SOCRATES/table-socrates.php?CATNR=25504,34387&ORDER=TCA&MAX=10)

| Object | Demo GP epoch (UTC) | SOCRATES GP epoch (UTC) |
| --- | --- | --- |
| 25504 | 2026-11-21 07:32:36.948192 | 2026-11-20 08:20:55.847040 |
| 34387 | 2026-11-21 00:46:07.850784 | 2026-11-20 08:31:21.197280 |

Owner B can consume the ranked `Conjunction` objects from `replay_demo()`. For the live workflow, Owner C can use the result of `load_user_catalog("satellite")` in the picker and include `load_user_catalog("debris")` in the screening catalog. For a duplicate NORAD ID, put the preferred elements first. Screening uses the first occurrence. Public GP elements provide predictions without covariance. The radial filter and coarse time grid are approximations, and the demo miss distances depend on the saved orbit epochs.
