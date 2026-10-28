# GRIDGUARD AI
**Vision-driven cascading gridlock prediction and adaptive traffic recovery**

## Quick start (Windows 11)
```bat
python -m venv .venv
.venv\Scripts\activate.bat
pip install -r requirements.txt
python server.py
```
Or double-click `run_windows.bat`. The command center opens at http://127.0.0.1:8000. The first run downloads `yolo11n.pt`.

## Command center tabs
- **Live detection** (sources: upload, scan and pick a connected camera, video library in `data/videos`, a file path, or an rtsp/http stream URL): real-time OpenCV + YOLO stream with boxes, class labels and confidence, an adjustable queue region, live FPS, inference ms, frame ms, CPU and RAM charts, vehicle counts, occupancy, queue growth, optional ByteTrack IDs, risk score R = 0.35Q + 0.25O + 0.20G + 0.20D with its components, and CSV export.
- **Risk network**: five-junction cascade graph and bottleneck ranking, plus a live risk timeline with the 0.40 / 0.70 thresholds.
- **Suggestions to avoid traffic** (Live and Risk network tabs): advice for operators and travellers that changes with the risk level (low, medium, high) and with which risk component is driving it, plus a lower-risk route through the junction graph. Advice only; nothing controls real signals.
- **Intervention lab** (real SUMO + TraCI on a 6-junction 3x2 signalised grid in `simulation/grid.net.xml`; falls back to the built-in `sim.py` queue model if SUMO is missing): five scenarios (normal, peak, blockage, downstream saturation, intervention failure). Fixed-time vs local queue-based vs GRIDGUARD on identical seeded demand, repeated runs, candidate actions A/B/C scored by J, closed-loop reassessment log, per-junction risk heatmap.
- **ARGOS ATLAS**: discovery checklist, source and licence notes, and a button to test a permitted stream URL.
- **Requirements**: F1 to F10 mapped to where each is shown.

## Honest limits
- Risk is a heuristic score, not a calibrated probability. Occupancy and queue growth come from image-space boxes and are noisy.
- The Intervention lab runs real SUMO, but on a generated grid with synthetic demand, not a real city. Each run takes about 10 to 40 s per controller. In blockage runs most of GRIDGUARD's gain comes from adaptive rerouting (action C), which the baselines do not have. In peak traffic it is about equal to fixed-time. Report these as measured.
- The five-junction graph is illustrative and not inferred from the video. Nothing here controls real traffic lights.
- ARGOS ATLAS does not guarantee a stream a program can read. Use only video you are permitted to use. No face or plate recognition.
- Detection counts are per frame. Turn on ByteTrack for unique IDs.

## Files
`server.py` (web server, YOLO worker, API) · `sumo_sim.py` (SUMO + TraCI), `simulation/` (SUMO network), `advisor.py` (risk-level suggestions), `sim.py` (fallback simulator) · `web/index.html` (dashboard) · `risk_engine.py`, `cascade_analysis.py`, `intervention.py`, `detect_vehicles.py`, `app.py` (earlier modules, Streamlit app kept as `run_streamlit_legacy.bat`) · `tests/`

## Troubleshooting
Slow: lower image size to 320 or 416 and use a short clip. Video will not open: try MP4. Package fails: use Python 3.11.
