# 🚦 GRIDGUARD AI

### Vision-Driven Cascading Gridlock Prediction, Accident Detection & Adaptive Traffic Recovery

**GridGuard AI** is an intelligent traffic monitoring and simulation platform that combines computer vision, vehicle detection, cascading congestion risk analysis, and adaptive traffic intervention experiments. The updated system also supports accident and ambulance detection notifications to mobile devices through **ntfy**, enabling faster awareness of potentially critical road situations.

The platform brings real-time video analytics, traffic risk assessment, operator recommendations, network-level congestion analysis, SUMO-based simulation, and mobile alerts together in one command center.

> **Important:** GridGuard AI is a monitoring and decision-support prototype. Notifications provide situational awareness; the system does not automatically control real-world traffic signals or replace emergency services.

---

## 📌 Table of Contents

- [Overview](#-overview)
- [Key Features](#-key-features)
- [Accident Detection & Mobile Alerts](#-accident-detection--mobile-alerts)
- [Ambulance Detection & Mobile Alerts](#-ambulance-detection--mobile-alerts)
- [System Architecture](#-system-architecture)
- [Command Center](#-command-center)
- [Intervention Lab](#-intervention-lab)
- [Technology Stack](#-technology-stack)
- [Installation](#-installation)
- [Running the Application](#-running-the-application)
- [Performance Metrics](#-performance-metrics)
- [Project Structure](#-project-structure)
- [Limitations](#-limitations)
- [Troubleshooting](#-troubleshooting)
- [Future Enhancements](#-future-enhancements)

---

## 🌍 Overview

Urban traffic congestion, road accidents, and delayed awareness of emergency vehicles can affect road safety and traffic efficiency.

GridGuard AI explores how computer vision and simulation can help operators:

- Monitor vehicle movement from supported video sources.
- Identify vehicles and estimate traffic conditions.
- Analyze growing queues and potential cascading gridlock.
- Detect potential accident and ambulance events using the configured detection pipeline.
- Send mobile notifications through ntfy when supported alert conditions are met.
- Explore adaptive traffic interventions in a controlled simulation environment.
- Review traffic risk, system performance, and exported detection data.

The goal is to make traffic monitoring more understandable, responsive, and measurable.

## ✨ Key Features

### 1. 🎥 Live Traffic Detection

Monitor supported video sources using OpenCV and YOLO.

- Upload a video or select a supported camera source.
- Process videos from the `data/videos` directory.
- Configure a file path or RTSP/HTTP stream URL.
- Display vehicle bounding boxes, class labels, and confidence scores.
- Configure a queue region of interest.
- Monitor live FPS, inference latency, frame processing time, CPU and RAM usage.
- Track vehicle counts, occupancy, queue growth, and risk score.
- Optionally use ByteTrack IDs for object tracking.
- Export available detection records to CSV.

### 2. 🚨 Accident Detection

GridGuard AI includes an accident-detection feature intended to identify potential road accident events from supported video input.

Depending on the configured detection logic, accident alerts can help operators identify situations requiring closer attention.

- Analyze supported traffic footage for configured accident indicators.
- Surface detected events in the application when implemented.
- Trigger ntfy mobile notifications when the configured alert conditions are satisfied.
- Support quicker operator awareness of potential road incidents.

**Safety note:** Vision-based accident detection can produce false positives and false negatives. A detected event should be treated as an alert for verification, not as definitive confirmation that an accident occurred.

### 3. 🚑 Ambulance Detection

The updated system also supports ambulance detection through its configured vision pipeline.

- Identify ambulance detections when supported by the trained model and detection configuration.
- Make emergency-vehicle observations available to the monitoring workflow.
- Send mobile notifications through ntfy when configured detection and notification conditions are met.
- Help operators become aware of possible emergency-vehicle presence in monitored footage.

**Important:** Ambulance detection does not automatically grant traffic-signal priority or guarantee a clear route. The system does not dispatch ambulances or contact emergency services unless a separately configured integration explicitly provides that functionality.

### 4. 📱 Mobile Notifications with ntfy

GridGuard AI integrates with **ntfy**, a notification service that can deliver messages to subscribed devices.

The notification workflow is intended to provide mobile awareness of configured accident and ambulance events without requiring the operator to watch the dashboard continuously.

**Typical workflow:**

1. The video detection pipeline processes a frame.
2. The configured detection logic identifies a potential accident or ambulance event.
3. The event is checked against the application's alert conditions.
4. A notification is published to the configured ntfy topic.
5. A subscribed phone receives the notification through ntfy.

The exact notification content, deduplication behavior, event cooldown, and delivery status depend on the implementation.

#### Setting up ntfy

1. Install the ntfy app on your phone from the official [ntfy website](https://ntfy.sh/).
2. Create or choose a topic supported by your notification configuration.
3. Subscribe to that topic in the mobile app.
4. Configure GridGuard AI to publish to the same topic.
5. Start the application and test notifications using permitted sample footage.
6. Verify that the correct event generates a notification and that repeated detections behave as intended.

**Configuration and security**

- Follow the environment-variable names or configuration keys actually used by your code.
- Keep private topic names, access tokens, and other credentials out of public source control.
- Use a private or access-controlled topic when alerts contain sensitive operational information.
- Treat delivery as best-effort unless the application explicitly implements and verifies retries and delivery handling.

Official documentation: [ntfy](https://docs.ntfy.sh/)

---

## 🧠 Cascading Gridlock Risk Analysis

The Risk Network tab presents an illustrative five-junction graph for examining how congestion at one junction may affect connected junctions.

The configured heuristic risk score is:

\[
R = 0.35Q + 0.25O + 0.20G + 0.20D
\]

Where:

- **Q — Queue:** Estimated queue severity.
- **O — Occupancy:** Estimated road-region occupancy.
- **G — Growth:** Queue growth indicator.
- **D — Downstream risk:** Congestion or saturation affecting downstream traffic.

The application uses configured thresholds of **0.40** and **0.70** to distinguish risk levels in the risk timeline.

The dashboard includes bottleneck ranking, risk components, and a live risk timeline.

> The score is a heuristic, not a statistically calibrated probability of gridlock. Its accuracy depends on video quality, detection reliability, normalization, and the configured risk logic.

## 🖥️ Command Center

The web dashboard organizes the application's monitoring and simulation capabilities into tabs.

| Tab | Purpose |
|---|---|
| **Live Detection** | Video analysis, vehicle detections, performance metrics, queue monitoring, and configured event alerts. |
| **Risk Network** | Five-junction cascade graph, bottleneck ranking, risk components, and risk timeline. |
| **Suggestions to Avoid Traffic** | Risk-aware advice for operators and travellers, including lower-risk routes through the illustrative graph. |
| **Intervention Lab** | Traffic-control strategy experiments using SUMO and TraCI, with a built-in fallback queue model. |
| **ARGOS ATLAS** | Source discovery checklist, source and licence notes, and permitted stream testing. |
| **Requirements** | Mapping of requirements F1–F10 to their documented application locations. |

The accident and ambulance notification features are intended to complement traffic monitoring rather than replace operator judgement.

## 🔄 System Architecture

The overall conceptual workflow is:

```text
Video / Camera / Stream
          |
          v
   OpenCV Video Pipeline
          |
          v
    YOLO Detection
          |
          +-----------------------+
          |                       |
          v                       v
   Vehicle Analytics       Configured Event
          |                Detection Logic
          v                       |
   Queue and Occupancy            +----------------+
          |                       |                |
          v                       v                v
   Risk Engine              Accident Alert   Ambulance Alert
          |                       |                |
          v                       +-------+--------+
   Cascade Analysis                      |
          |                              v
          v                       ntfy Notification
   Risk Suggestions                       |
          |                              v
          v                         Mobile Phone
   Command Center
          |
          v
   CSV / Risk Timeline

Separate simulation workflow:
Traffic Scenarios -> SUMO / TraCI -> Controller Comparison
                                  -> Performance Results
```

This diagram describes the intended workflow. The exact processing order, event-detection model, and notification implementation should be checked against the current source code.

## 🚦 Intervention Lab

The Intervention Lab evaluates traffic-management strategies using a simulated six-junction, 3×2 signalized grid.

### Simulation environment

- SUMO and TraCI when the required simulation components are available.
- A built-in queue-model fallback when SUMO is unavailable.
- A generated road network and synthetic traffic demand.
- Repeated runs using identical seeded demand for comparable scenarios.

### Configured traffic scenarios

1. Normal traffic.
2. Peak traffic.
3. Road blockage.
4. Downstream saturation.
5. Intervention failure.

### Controller comparison

The lab compares:

- Fixed-time traffic control.
- Local queue-based control.
- GRIDGUARD adaptive control.

Candidate interventions A, B, and C are evaluated using the configured objective score \(J\). The workflow also provides a closed-loop reassessment log and per-junction risk heatmap.

**Interpret results carefully:** The simulated network is not a real-city deployment. In blockage scenarios, adaptive rerouting contributes substantially to the reported GRIDGUARD gain, while the baseline controllers do not have the same rerouting capability. In peak traffic, performance has been approximately comparable to fixed-time control in the observed experiments. These are measured prototype results, not universal performance guarantees.

## 🛠️ Technology Stack

| Technology | Role |
|---|---|
| Python | Backend logic, analytics, and orchestration |
| OpenCV | Video capture and image processing |
| YOLO11 | Object detection, using the configured model |
| ByteTrack | Optional object tracking |
| Flask or configured web framework | Web server and API, depending on the implementation |
| SUMO | Microscopic traffic simulation |
| TraCI | Communication with SUMO simulations |
| HTML, CSS, JavaScript | Browser-based command center |
| ntfy | Mobile push-notification workflow |
| CSV | Export of available detection records |

Verify the actual imports, framework, and dependency versions in the current project before publishing this table.

## 💻 Installation

### Prerequisites

- Windows 11.
- Python 3.11 recommended.
- Git, if cloning the repository.
- SUMO for the full simulation workflow.
- A compatible environment for OpenCV and the configured YOLO model.
- The ntfy mobile app if you want to receive notifications on your phone.

### 1. Clone the repository

```bat
git clone https://github.com/raghulrams2207/GridGuard-AI---AI-Traffic-Flow-Management-System.git
cd GridGuard-AI---AI-Traffic-Flow-Management-System
```

### 2. Create a virtual environment

```bat
python -m venv .venv
.venv\Scripts\activate.bat
```

### 3. Install dependencies

```bat
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Configure notifications

Configure ntfy according to the keys and settings expected by the current application. Use a topic that matches the one subscribed to on your phone.

Do not publish access tokens or private notification credentials in your README or repository.

### 5. Start the application

```bat
python server.py
```

Alternatively, double-click:

```text
run_windows.bat
```

Open the command center:

**http://127.0.0.1:8000**

On the first run, the application downloads `yolo11n.pt` if it is not already present and if the model-loading configuration uses that filename. An internet connection may be required for the initial download.

## 📊 Performance Metrics

GridGuard AI exposes or uses several metrics to evaluate the monitoring and simulation workflow.

| Metric | Meaning |
|---|---|
| FPS | Frames processed per second. |
| Inference time (ms) | Time spent running the configured model inference. |
| Frame time (ms) | Time required for the measured frame-processing pipeline. |
| CPU usage | Processor utilization during application execution. |
| RAM usage | Memory consumption during execution. |
| Vehicle count | Number of detections in a frame, unless tracking-based counts are explicitly used. |
| Occupancy | Estimated fraction of the configured region occupied by detected objects. |
| Queue growth | Change in the estimated queue indicator over time. |
| Risk score | Weighted heuristic derived from the configured risk components. |
| Simulation objective \(J\) | Configured score for comparing intervention candidates. |

Detection counts are generally per frame. Enable ByteTrack when tracking IDs are needed; unique-vehicle counts still depend on tracking continuity and counting logic.

Report performance results with the test video, input resolution, hardware, simulation duration, and metric definitions so comparisons are meaningful.

## 📁 Project Structure

```text
GridGuard-AI---AI-Traffic-Flow-Management-System/
├── server.py                  # Web server, YOLO worker, and API
├── sumo_sim.py                # SUMO and TraCI integration
├── simulation/
│   └── grid.net.xml           # Configured SUMO road network
├── advisor.py                 # Risk-level recommendations
├── sim.py                     # Fallback queue simulator
├── web/
│   └── index.html             # Web command center
├── risk_engine.py             # Traffic risk calculations
├── cascade_analysis.py        # Junction-level cascade analysis
├── intervention.py             # Intervention evaluation
├── detect_vehicles.py         # Vehicle detection module
├── app.py                     # Legacy Streamlit application
├── run_windows.bat             # Windows startup script
├── run_streamlit_legacy.bat    # Legacy application launcher
├── requirements.txt           # Python dependencies
└── tests/                     # Automated tests
```

This is the documented project structure from the existing README. Add any new accident-detection, ambulance-detection, or ntfy-specific modules and configuration files that are actually present in the updated repository.

## ⚠️ Honest Limitations

- The risk score is a heuristic, not a calibrated probability.
- Image-space occupancy and queue-growth estimates can be noisy.
- The five-junction cascade graph is illustrative and is not inferred directly from the input video.
- The Intervention Lab uses a generated grid and synthetic demand, not a real city network.
- SUMO experiments are simulations; they do not prove real-world traffic improvements.
- Detection accuracy depends on model training, video quality, lighting, camera angle, occlusion, and configuration.
- Accident detection may miss incidents or generate false alarms. It should not be treated as verified emergency information.
- Ambulance detection does not automatically grant signal priority or guarantee a safe passage.
- ntfy delivery depends on connectivity, topic configuration, service availability, and notification settings.
- ARGOS ATLAS cannot guarantee that a discovered stream is accessible or authorized for use.
- Only use footage and camera streams you are legally permitted to access.
- The project does not perform face recognition or license-plate recognition as part of the documented workflow.
- No feature should be represented as controlling real traffic infrastructure unless a separate, authorized, tested integration actually exists.

## 🧰 Troubleshooting

### Application is slow

- Lower the input resolution to 320 or 416.
- Test with a short video clip.
- Close unnecessary applications.
- Check the displayed FPS, inference time, CPU usage, and RAM usage.

### Video does not open

- Try an MP4 file.
- Verify the file path and codec.
- Check that the source is supported by OpenCV.
- Confirm that the camera or stream is accessible.

### ntfy notifications are not arriving

1. Confirm that the phone is subscribed to the correct topic.
2. Check that the application is configured with the same topic.
3. Verify that the phone and server have network access.
4. Check application logs for notification-publishing errors.
5. Verify that the event-detection conditions were actually satisfied.
6. Check notification permissions and battery restrictions on the phone.
7. Test using a permitted sample clip that should trigger the configured alert logic.

Avoid posting private topic names, access tokens, or sensitive stream URLs in public bug reports.

### Python package installation fails

- Use Python 3.11 as the recommended environment.
- Create a fresh virtual environment.
- Upgrade pip.
- Reinstall dependencies from `requirements.txt`.
- Review the error output for incompatible package versions or missing system libraries.

### SUMO is unavailable

- Verify that SUMO is installed.
- Check the SUMO executable and environment configuration.
- Confirm that the network and configuration files exist.
- Use the built-in fallback simulator if the application supports it.

## 🔮 Future Enhancements

Potential improvements include:

- More robust accident-event classification and validation.
- Configurable alert cooldowns and duplicate-event suppression.
- Event timestamps, severity levels, and structured incident logs.
- Notification history and delivery-error reporting.
- Improved ambulance detection and emergency-route awareness.
- More realistic road networks and traffic-demand scenarios.
- Better calibration of congestion-risk indicators against observed traffic.
- Baseline comparisons using equivalent routing capabilities.
- Live dashboards for incident history and performance trends.
- Evaluation on diverse, authorized video datasets.

These are potential enhancements, not claims that the functionality is already implemented.

## 🤝 Contributing

Contributions, testing, and improvement suggestions are welcome.

1. Fork the repository.
2. Create a feature branch.
3. Make your changes.
4. Run the available tests.
5. Document configuration changes and new dependencies.
6. Submit a pull request describing the implementation and test results.


**GridGuard AI — AI Traffic Flow Management System**

[View the project on GitHub](https://github.com/raghulrams2207/GridGuard-AI---AI-Traffic-Flow-Management-System)

Built to explore vision-driven traffic monitoring, cascading gridlock analysis, emergency-event awareness, and adaptive traffic simulation.
