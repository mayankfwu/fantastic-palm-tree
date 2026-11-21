1. Problem statement

Low Earth orbit is crowded with working satellites and with fragments from past breakups. A close approach (a conjunction) between two objects can destroy a satellite and create thousands of new fragments, which raises the risk for every other object.

Operators face three connected questions:

Which predicted close approaches actually matter?
How risky is each one (probability of collision)?
What is the smallest burn that makes it safe, given that every burn uses fuel and shortens the satellite's working life?

Today these decisions are often made one alert at a time, by hand, with no shared tool that links prediction, risk and fuel cost.

2. Objective

For a chosen satellite, build a simulator that:

loads real orbital data and propagates the satellite and a debris catalog,
finds predicted close approaches within a time window,
estimates the collision probability (Pc) for each,
plans an avoidance burn that uses the minimum delta-v (fuel) to get below a safe miss distance,
shows everything in an interactive Streamlit demo with 3D orbits.

3. Proposed solution

Stage	What it does	Module	Output
Load	Fetch CelesTrak GP data (JSON/OMM), cache locally	src/orbits/	list of SGP4 satellite objects
Propagate	SGP4 orbit propagation in the TEME frame	src/orbits/	positions (km), velocities (km/s)
Screen	Find close approaches, time of closest approach (TCA), miss distance	src/orbits/	Conjunction records
Risk	2D Gaussian collision probability in the encounter plane	src/risk/	Pc value
Maneuver	Single impulsive along-track burn before TCA, minimum delta-v above the safe threshold	src/maneuver/	Maneuver record
Fuel	Rocket equation: delta-v to propellant mass	src/maneuver/	kg of propellant
Visualise	Streamlit app, Plotly charts and 3D orbits	app.py, src/viz/	interactive demo

The three owners share a fixed data contract (Conjunction, Maneuver) in src/contracts.py, so each part can be built and tested independently.

4. Scope

In scope (MVP)

One chosen primary satellite screened against selected debris groups (cosmos-2251-debris, iridium-33-debris, fengyun-1c-debris)
Pc using an assumed position uncertainty
One impulsive along-track burn, with burn-now versus burn-later comparison
Fuel estimate with adjustable mass and Isp
Interactive demo

Stretch

Clohessy-Wiltshire relative-motion maneuver model
Real covariance data if it can be obtained

Not in the current design

Planning for several satellites at once so that one satellite's maneuver never creates a new conflict for another. The project idea mentions coordinated planning, but the current spec plans one satellite at a time. Say this openly in the pitch, or build it.

5. Key assumptions

Assumption	Value	Note
Position uncertainty (isotropic)	SIGMA_KM = 1.0	Public GP/TLE data has no covariance, so this is a placeholder
Safe miss distance	THRESHOLD_KM = 5.0	Chosen threshold, not an operational standard
Maneuver	Single impulsive along-track burn	Real burns take time and may be in other directions
Spacecraft (demo defaults)	500 kg, Isp 220 s	Adjustable in the UI
Reference frame	TEME (SGP4 output)	Do not mix frames without converting
Units	km, km/s, m/s (delta-v), kg, s; UTC datetimes	

6. Data

Source: CelesTrak GP data, requested in JSON/OMM format (not raw TLE text).
Debris sets: three well-known breakup debris clouds.
Caching: downloads saved under data/cache/ (git-ignored) to avoid repeated requests.
Development fixture: data/fixtures/fake_conjunction.json lets the risk, maneuver and app work proceed without the real screening code.

7. Critical analysis

Basis: this analysis uses the repository's AGENTS.md spec and its file layout. It is not a code review: the source files were not readable when this was written. Items marked to verify should be checked against the real code.


7.1 Strengths:

Clear contract. Fixed data classes and function signatures let three people work in parallel without blocking each other.
Honest modelling. Assumptions (sigma, threshold, burn type) are written down, not hidden.
Right data format. Using OMM/JSON avoids the retiring TLE format for new catalog numbers.
Explainable by design. Small, commented functions and a test for every function make it easy to defend in front of judges.
Real, recognisable data. Using famous breakup debris makes the demo concrete.

7.2 Limitations:

Limitation	Why it matters	Mitigation
Assumed 1 km uncertainty, no covariance	Pc depends strongly on sigma, so absolute Pc values are not trustworthy	Present Pc as relative risk; show a sensitivity slider for sigma
SGP4 accuracy is limited, and worse for old element sets	Predicted miss distances can be off by kilometres, similar to the 5 km threshold	State the epoch age; warn when data is old
Single impulsive along-track burn	Ignores burn duration, other directions and operational limits	Label as MVP; compare with the Clohessy-Wiltshire stretch goal
One satellite at a time	Does not deliver coordination between satellites	Say so in the pitch, or add a multi-satellite check
Fixed 5 km threshold	Arbitrary; real operators use risk-based thresholds	Make it adjustable in the UI
Pc is not monotonic in miss distance	A smaller miss can sometimes give a lower Pc (dilution region), which confuses audiences	Plot Pc against miss distance and explain it

7.3 Technical risks and likely bugs (to verify in code)

Missed conjunctions from coarse time steps. At relative speeds near 14 km/s, 60-second steps are hundreds of kilometres apart. A 50 km screen can miss real approaches unless the screen is widened and the TCA is refined (interpolation or minimisation).
SGP4 error codes ignored. Decayed or invalid objects return error codes and bad values; unchecked NaNs spread into later results.
Naive vs timezone-aware datetimes. Mixing them causes crashes or silent offsets.
Frame mix-ups. TEME positions plotted on a rotating Earth, or mixed with Earth-fixed data, shift everything.
Data fetching. Rate limits, blocked requests, wrong JSON field names, or a broken cache.

Risk and maneuver:

Wrong geometry for Pc. The relative position must be projected onto the plane perpendicular to the relative velocity, not the plain 3D miss distance.
Unit slips. km versus m in the combined radius, km/s versus m/s in delta-v.
Applying the burn. SGP4 objects cannot simply take a delta-v. The burn has to be applied to a state vector and propagated again. If new_miss_km is estimated by formula instead of recomputed, it will not match the physics.
Edge cases in the search for delta-v. A conjunction already above the threshold (the answer should be 0), a burn that cannot reach the threshold, and burning too late.
Fuel formula. Check m_prop = m0 * (1 - exp(-dv / (Isp * 9.80665))), with delta-v in m/s and mass before the burn. For the demo defaults (500 kg, 220 s), 1 m/s is about 0.23 kg of propellant, which makes a good unit test.

App and tests:

Slow reruns. Streamlit re-runs the script on every click. Without caching, each interaction refetches and recomputes.
Heavy 3D plots. Thousands of debris points in Plotly 3D will lag.
Fixture hiding integration bugs. The fake conjunction works, but real screening output may differ in units or time format. Add a test that runs real output through risk and maneuver.

7.4 Gaps to close before presenting

README is a one-line title. AGENTS.md says it should state the modelling assumptions and how to run the project. To verify.
Setup files. requirements.txt and app.py were not visible in the repo listing. If they are missing, the documented setup commands fail for anyone who clones it. To verify.
Claim vs build. Align the slides and pitch with what the code really does (single satellite, impulsive burn).

8. Evaluation plan

Check	Pass condition
Fuel formula	1 m/s with 500 kg and Isp 220 s gives about 0.23 kg
Burn effectiveness	New miss distance after the burn is at or above the threshold, confirmed by re-propagating
Minimality	A slightly smaller delta-v fails to reach the threshold
Pc behaviour	Pc responds sensibly to sigma, radius and miss distance, and stays between 0 and 1
Invalid objects	Decayed or errored SGP4 objects are skipped, not turned into NaNs
Screening recall	A known fixture conjunction is found at the right TCA
Demo	Full run from satellite choice to burn plan in the app, within an acceptable wait

Measured results: [to be filled in after testing]


9. Future work

Several satellites planned together so that one avoidance burn never creates a new conflict
Clohessy-Wiltshire relative-motion model for more realistic burns
Real covariance data and uncertainty-aware risk
Finite-duration burns and operational constraints
Larger catalogs with faster screening
Automatic alerts as new data arrives

10. Team and ownership

Owner	Folders	Responsibility
A	src/orbits/	Data loader, propagation, screening, TCA, miss distance
B	src/risk/, src/maneuver/	Pc, burn optimiser, fuel
C	app.py, src/viz/, docs/, README.md	App, charts, 3D orbits, docs, demo

11. References

CelesTrak, GP data in JSON/OMM format (celestrak.org)
Vallado, Crawford, Hujsak, Kelso, "Revisiting Spacetrack Report #3", AIAA 2006-6753 (SGP4)
Foster and Estes, "A Parametric Analysis of Orbital Debris Collision Probability and Maneuver Rate for Space Vehicles", NASA/JSC-25898 (1992)
Tsiolkovsky rocket equation 
