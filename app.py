from pathlib import Path
import os
import tempfile
import time

import cv2
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from ultralytics import YOLO

from risk_engine import calculate_risk, risk_label
from cascade_analysis import build_intersection_graph, propagate_cascade_risk
from intervention import compare_interventions

st.set_page_config(page_title="GRIDGUARD AI", page_icon="🚦", layout="wide")
VEHICLE_CLASSES = {2: "Car", 3: "Motorcycle", 5: "Bus", 7: "Truck"}

@st.cache_resource(show_spinner="Loading YOLO model (first run downloads weights)...")
def load_model(model_name):
    return YOLO(model_name)

def resize_frame(frame, target_width=640):
    h, w = frame.shape[:2]
    if w <= target_width:
        return frame
    return cv2.resize(frame, (target_width, max(2, int(h * target_width / w))))

def analyze_video(video_path, model, max_frames, confidence, image_size):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError("Could not open video. Try an MP4 file.")
    fps = cap.get(cv2.CAP_PROP_FPS)
    if not fps or fps <= 0 or fps > 120:
        fps = 25.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    original_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 640)
    original_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 360)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
    output_path = tmp.name
    tmp.close()
    rows = []
    totals = {name: 0 for name in VEHICLE_CLASSES.values()}
    writer = None
    progress = st.progress(0, text="Starting YOLO detection...")
    status = st.empty()
    start = time.time()
    try:
        while len(rows) < max_frames:
            ok, frame = cap.read()
            if not ok:
                break
            frame = resize_frame(frame, 640)
            h, w = frame.shape[:2]
            w -= w % 2
            h -= h % 2
            frame = cv2.resize(frame, (w, h))
            if writer is None:
                writer = cv2.VideoWriter(output_path, cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
                if not writer.isOpened():
                    raise RuntimeError("Could not create output MP4. Check disk space/codecs.")
            result = model.predict(frame, imgsz=image_size, conf=confidence,
                                    classes=list(VEHICLE_CLASSES), device="cpu", verbose=False)[0]
            count = 0
            queue_proxy = 0
            bbox_area = 0
            per_class = {name: 0 for name in VEHICLE_CLASSES.values()}
            for box in result.boxes:
                cls_id = int(box.cls.item())
                if cls_id not in VEHICLE_CLASSES:
                    continue
                label = VEHICLE_CLASSES[cls_id]
                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy().astype(int).tolist()
                x1, y1 = max(0, x1), max(0, y1)
                x2, y2 = min(w - 1, x2), min(h - 1, y2)
                count += 1
                per_class[label] += 1
                bbox_area += max(0, x2-x1) * max(0, y2-y1)
                if (y1+y2)/2 >= h * 0.55:
                    queue_proxy += 1
                cv2.rectangle(frame, (x1, y1), (x2, y2), (40, 220, 80), 2)
                cv2.putText(frame, f"{label} {float(box.conf.item()):.2f}",
                            (x1, max(18, y1-6)), cv2.FONT_HERSHEY_SIMPLEX, .48,
                            (40, 220, 80), 2, cv2.LINE_AA)
            occupancy = min(1.0, bbox_area / max(w*h, 1))
            previous = rows[-1]["vehicle_count"] if rows else count
            risk = calculate_risk(count, occupancy, queue_proxy, previous, .35)
            cv2.rectangle(frame, (8, 8), (min(w-8, 370), 72), (18, 25, 38), -1)
            cv2.putText(frame, f"GRIDGUARD AI | Vehicles: {count}", (16, 32),
                        cv2.FONT_HERSHEY_SIMPLEX, .58, (255,255,255), 2)
            cv2.putText(frame, f"Risk: {risk_label(risk)} ({risk:.0f}/100)", (16, 57),
                        cv2.FONT_HERSHEY_SIMPLEX, .55, (80,220,255), 2)
            writer.write(frame)
            row = {
                "frame": len(rows)+1, "time_seconds": (len(rows)+1)/fps,
                "vehicle_count": count, "queue_proxy": queue_proxy,
                "occupancy_proxy_pct": occupancy*100, "risk_score": risk,
                "risk_level": risk_label(risk)
            }
            row.update({f"{name.lower()}_count": n for name, n in per_class.items()})
            rows.append(row)
            for name, n in per_class.items():
                totals[name] += n
            pct = min(100, int(len(rows)/min(total_frames or max_frames, max_frames)*100))
            progress.progress(pct, text=f"YOLO processing: {len(rows)} frames")
            if len(rows) % 10 == 0:
                elapsed = max(time.time()-start, .1)
                status.caption(f"{len(rows)} frames · {len(rows)/elapsed:.1f} frames/sec · CPU inference")
    finally:
        cap.release()
        if writer is not None:
            writer.release()
    progress.progress(100, text="Detection complete")
    status.empty()
    if not rows:
        raise RuntimeError("No readable video frames were found.")
    meta = {
        "frames_processed": len(rows), "fps": fps,
        "original_width": original_w, "original_height": original_h,
        "elapsed_seconds": time.time()-start, "total_frames": total_frames
    }
    return output_path, pd.DataFrame(rows), totals, meta

def network_figure(risks):
    graph = build_intersection_graph()
    pos = {"J1": (0,1), "J2": (1,1), "J3": (2,1), "J4": (1,0), "J5": (3,1)}
    ex, ey = [], []
    for u, v in graph.edges():
        ex += [pos[u][0], pos[v][0], None]
        ey += [pos[u][1], pos[v][1], None]
    edges = go.Scatter(x=ex, y=ey, mode="lines", line=dict(width=3, color="#8295ab"),
                       hoverinfo="none", showlegend=False)
    nodes = list(graph.nodes())
    node = go.Scatter(
        x=[pos[n][0] for n in nodes], y=[pos[n][1] for n in nodes],
        mode="markers+text", text=nodes, textposition="bottom center",
        hovertext=[f"{n}: {risks.get(n, 10):.1f}/100" for n in nodes],
        hoverinfo="text", showlegend=False,
        marker=dict(size=[28+risks.get(n,10)*.25 for n in nodes],
                    color=[risks.get(n,10) for n in nodes], colorscale="RdYlGn_r",
                    cmin=0, cmax=100, showscale=True, colorbar=dict(title="Risk"),
                    line=dict(width=2, color="white")))
    fig = go.Figure([edges, node])
    fig.update_layout(title="Illustrative connected-intersection risk map", template="plotly_dark",
                      height=370, margin=dict(l=10,r=10,t=50,b=10),
                      xaxis=dict(visible=False), yaxis=dict(visible=False))
    return fig

st.title("🚦 GRIDGUARD AI")
st.subheader("Vision-Driven Cascading Gridlock Prediction and Adaptive Traffic Recovery")
st.write("Upload a traffic video to run real pretrained YOLO detection, inspect congestion indicators, and explore illustrative cascading-risk and intervention scenarios.")

with st.sidebar:
    st.header("Detection settings")
    model_name = st.selectbox("YOLO model", ["yolo11n.pt"])
    confidence = st.slider("Detection confidence", .10, .80, .35, .05)
    image_size = st.select_slider("Inference image size", options=[320, 416, 512, 640], value=416)
    max_frames = st.slider("Maximum frames to analyze", 50, 1200, 300, 50)
    st.caption("CPU inference is used for laptops with integrated graphics. First run downloads model weights.")

uploaded = st.file_uploader("Upload traffic video", type=["mp4", "avi", "mov", "mkv", "mpeg", "mpg"])
st.info("Tip: start with a 10–30 second clip. The frame limit keeps CPU processing manageable.")

if uploaded is None:
    a,b,c = st.columns(3)
    a.metric("Vehicle detection", "YOLO")
    b.metric("Risk score", "0–100")
    c.metric("Network", "5 junctions")
    st.markdown("""
    **Prototype features**
    - Detect cars, motorcycles, buses and trucks with pretrained YOLO.
    - Play/download an annotated video and export frame metrics as CSV.
    - View vehicle-count and risk trends.
    - Explore risk propagation over a five-junction illustrative network.
    - Compare heuristic intervention choices.
    """)
    st.stop()

if st.button("🚀 Analyze video with GRIDGUARD AI", type="primary", use_container_width=True):
    input_path = None
    try:
        suffix = Path(uploaded.name).suffix or ".mp4"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(uploaded.getbuffer())
            input_path = tmp.name
        model = load_model(model_name)
        with st.spinner("Running YOLO inference on CPU..."):
            out, df, totals, meta = analyze_video(input_path, model, max_frames, confidence, image_size)
        st.session_state["analysis"] = {"output": out, "df": df, "totals": totals, "meta": meta, "name": uploaded.name}
    except Exception as exc:
        st.error(f"Analysis failed: {exc}")
        st.exception(exc)
    finally:
        if input_path and os.path.exists(input_path):
            os.remove(input_path)

if "analysis" in st.session_state:
    result = st.session_state["analysis"]
    df, totals, meta = result["df"], result["totals"], result["meta"]
    avg_risk = float(df.risk_score.mean())
    peak_risk = float(df.risk_score.max())
    st.success(f"Analysis complete: {result['name']}")
    a,b,c,d = st.columns(4)
    a.metric("Frames analyzed", f"{meta['frames_processed']:,}")
    b.metric("Avg. vehicles/frame", f"{df.vehicle_count.mean():.1f}")
    c.metric("Average risk", f"{avg_risk:.0f}/100", risk_label(avg_risk))
    d.metric("Peak risk", f"{peak_risk:.0f}/100", risk_label(peak_risk))

    tab1, tab2, tab3, tab4 = st.tabs(["🎥 YOLO detection", "📈 Risk analysis", "🕸️ Cascade network", "🛠️ Interventions"])
    with tab1:
        st.subheader("Annotated output from YOLO inference")
        st.video(result["output"])
        with open(result["output"], "rb") as f:
            st.download_button("Download annotated video", f, file_name="gridguard_annotated.mp4", mime="video/mp4")
        class_df = pd.DataFrame({"Vehicle type": list(totals.keys()), "Detections across frames": list(totals.values())})
        st.plotly_chart(px.bar(class_df, x="Vehicle type", y="Detections across frames",
                               template="plotly_dark", title="Vehicle detections summed across processed frames"),
                        use_container_width=True)
        st.json({"source_resolution": f"{meta['original_width']} × {meta['original_height']}",
                 "source_fps": round(meta["fps"],2), "elapsed_seconds": round(meta["elapsed_seconds"],2),
                 "inference_device": "CPU"})
        st.caption("Counts are per-frame detections summed across the clip, not unique tracked vehicles.")
    with tab2:
        fig = px.line(df, x="time_seconds", y="risk_score", template="plotly_dark",
                      title="Heuristic congestion-risk score over video time",
                      labels={"time_seconds":"Video time (seconds)", "risk_score":"Risk score (0–100)"})
        fig.add_hline(y=35, line_dash="dash", annotation_text="Medium threshold")
        fig.add_hline(y=70, line_dash="dash", annotation_text="High threshold")
        st.plotly_chart(fig, use_container_width=True)
        left,right = st.columns(2)
        left.plotly_chart(px.line(df, x="time_seconds", y="vehicle_count", title="Vehicles detected per frame",
                                  template="plotly_dark"), use_container_width=True)
        right.plotly_chart(px.line(df, x="time_seconds", y="occupancy_proxy_pct",
                                   title="Bounding-box area proxy (%)", template="plotly_dark"), use_container_width=True)
        st.warning("Risk is a heuristic score, not a calibrated probability. Image-space area is not physical road occupancy.")
        st.download_button("Download frame metrics CSV", df.to_csv(index=False).encode(), "gridguard_frame_metrics.csv", "text/csv")
    with tab3:
        last_risk = float(df.iloc[-1]["risk_score"])
        initial = {"J1": last_risk, "J2": max(10,last_risk*.72), "J3": max(8,last_risk*.48),
                   "J4": max(8,last_risk*.40), "J5": max(5,last_risk*.32)}
        risks = propagate_cascade_risk(build_intersection_graph(), initial)
        st.plotly_chart(network_figure(risks), use_container_width=True)
        risk_df = pd.DataFrame([{"Intersection": n, "Risk score": round(v,1), "Level": risk_label(v)} for n,v in risks.items()])
        st.dataframe(risk_df, hide_index=True, use_container_width=True)
        st.caption("Illustrative network topology; not inferred from the video or a real road map.")
    with tab4:
        last = df.iloc[-1]
        options = compare_interventions({"risk": last.risk_score, "vehicle_count": last.vehicle_count,
                                         "occupancy": last.occupancy_proxy_pct/100, "queue_proxy": last.queue_proxy})
        options_df = pd.DataFrame(options)
        st.dataframe(options_df, hide_index=True, use_container_width=True)
        best = min(options, key=lambda x: x["estimated_objective_score"])
        st.success(f"Recommended prototype action: {best['action']}")
        st.caption("Intervention values are heuristic estimates, not SUMO simulation results. The app does not control real traffic lights.")
        st.download_button("Download intervention comparison CSV", options_df.to_csv(index=False).encode(),
                           "gridguard_interventions.csv", "text/csv")
    with st.expander("View frame-level data"):
        st.dataframe(df, use_container_width=True)
