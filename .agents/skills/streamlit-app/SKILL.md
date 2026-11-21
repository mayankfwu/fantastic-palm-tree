---
name: streamlit-app
description: Build or change the Streamlit dashboard (app.py, src/viz/) for the satellite-debris project. Use for UI layout, charts, caching and session state. Do not use for orbit, risk or maneuver math.
---

- Call only the functions in AGENTS.md (load_catalog, find_conjunctions, collision_probability, plan_maneuver, fuel_used). Put no orbit or maneuver math in the app.
- Set st.set_page_config(layout="wide") at the top of app.py.
- Sidebar inputs: satellite, debris group, miss-distance threshold, mass, Isp.
- Main page: conjunction table, 3D orbit plot, risk metrics (st.metric), burn-now vs burn-later chart.
- Wrap slow calls (catalog load, conjunction search) in @st.cache_data and show st.spinner.
- Keep selected satellite, conjunction and maneuver in st.session_state.
- Add a "demo mode" toggle that loads data/fixtures instead of the network.
- The app must always start with `streamlit run app.py`.
