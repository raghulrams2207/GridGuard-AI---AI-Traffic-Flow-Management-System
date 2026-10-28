
import csv, io, json, os, re, shutil, threading, time, webbrowser, datetime
from collections import deque
from pathlib import Path
import cv2, psutil, uvicorn
from fastapi import Body, FastAPI, File, UploadFile
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, StreamingResponse
import sim, alerts
from accident import AccidentDetector
from advisor import advise
from cascade_analysis import build_intersection_graph, propagate_cascade_risk
from emergency_extensions import emergency_mgr

ROOT = Path(__file__).parent
VDIR = ROOT / "data" / "videos"; VEXT = {".mp4", ".avi", ".mov", ".mkv", ".mpg", ".mpeg"}
BACKEND = cv2.CAP_DSHOW if os.name == "nt" else cv2.CAP_ANY
opencap = lambda src: cv2.VideoCapture(src, BACKEND) if isinstance(src, int) else cv2.VideoCapture(src)
CLS = {2: "Car", 3: "Motorcycle", 5: "Bus", 7: "Truck"}
app = FastAPI(title="GRIDGUARD AI")
S = dict(conf=.35, imgsz=416, roi=[.05, .45, .9, .5], cap=12, downstream=.3, track=True, realtime=True, run=True)
ST = dict(source=None, label="No source", error=None, status="Waiting for a video source", fps=0, infer_ms=0,
          latency_ms=0, count=0, roi_count=0, occ=0, growth=0, classes={}, comp=dict(Q=0, O=0, G=0, D=0), R=0, frames=0, unique=0)

ALERTS = deque(maxlen=50)
AL = dict(enabled=True, to=os.getenv("ALERT_PHONE_NUMBER", "+919876543210"), cooldown=20, stall_s=8)
AFILE = ROOT / "data" / "alerts.json"; ADIR = ROOT / "data" / "alerts"
alerts.load_env(ROOT / ".env")
if AFILE.is_file():
    try:
        saved_to = json.loads(AFILE.read_text()).get("to", "")
        if saved_to: AL.update(to=saved_to)
    except Exception:
        pass

LOG = deque(maxlen=5000); JPEG = (None, 0); NOSRC = object()
clamp = lambda v, a=0.0, b=1.0: max(a, min(b, float(v)))
label = lambda r: "high" if r >= .70 else "medium" if r >= .40 else "low"


def _is_ambulance_visual(frame, x1, y1, x2, y2, cls_name, source_label=""):
    """Detects ambulance from custom class label, video context, or white+red emergency vehicle markings."""
    if "ambulance" in cls_name.lower():
        return True
    if cls_name not in ("Truck", "Bus", "Car"):
        return False
    crop = frame[max(0, y1):max(1, y2), max(0, x1):max(1, x2)]
    if crop.size == 0:
        return False
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    white_mask = cv2.inRange(hsv, (0, 0, 180), (180, 50, 255))
    red_mask1 = cv2.inRange(hsv, (0, 110, 90), (10, 255, 255))
    red_mask2 = cv2.inRange(hsv, (165, 110, 90), (180, 255, 255))
    total_px = float(crop.shape[0] * crop.shape[1])
    white_ratio = cv2.countNonZero(white_mask) / total_px
    red_ratio = (cv2.countNonZero(red_mask1) + cv2.countNonZero(red_mask2)) / total_px
    # Slightly more sensitive if the video itself is an ambulance clip, strict otherwise
    if "ambulance" in source_label.lower():
        return cls_name in ("Truck", "Bus") or (white_ratio > 0.30 and red_ratio > 0.015)
    return cls_name in ("Truck", "Bus") and white_ratio > 0.42 and 0.025 <= red_ratio <= 0.25


def fire(kind, frame, test=False, category="accident"):
    """
    Handles distinct notifications:
    - category='ambulance' -> Sends AMBULANCE IN EMERGENCY notification.
    - category='accident'  -> Updates existing accident in-place (without erasing old ones) and sends ACCIDENT notification.
    """
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    zone = ST.get("label") or "J1"
    name = None
    if frame is not None:
        ADIR.mkdir(parents=True, exist_ok=True)
        name = f"alert_{int(time.time())}.jpg"
        cv2.imwrite(str(ADIR / name), frame)

    target_phone = AL["to"] or emergency_mgr.target_phone

    # 1. TEST ALERT
    if test:
        title = "GRIDGUARD-AI TEST ALERT"
        text = f"Test alert from GRIDGUARD-AI at {ts} for phone {target_phone}. Ambulance & Accident alerts are active!"
        entry = dict(kind="test alert", time=ts, img=name, results=["Sending..."])
        ALERTS.append(entry)
        def go_test():
            entry["results"] = alerts.send(target_phone, text, title=title, tags="loudspeaker,white_check_mark", priority="high")
        threading.Thread(target=go_test, daemon=True).start()
        return

    # 2. AMBULANCE EMERGENCY NOTIFICATION (Completely distinct message & title)
    if category == "ambulance":
        title = "AMBULANCE IN EMERGENCY - GREEN CORRIDOR"
        text = (
            f"AMBULANCE IN EMERGENCY detected at {zone} ({ts})! "
            f"Phone: {target_phone}. Clear Green Corridor immediately!"
        )
        emergency_mgr.target_phone = target_phone
        emergency_mgr.notify_ambulance(zone_id=zone, confidence=0.92)
        entry = dict(kind=f"AMBULANCE IN EMERGENCY ({zone})", time=ts, img=name, results=["Sending ambulance alert..."])
        ALERTS.append(entry)
        def go_amb():
            entry["results"] = alerts.send(target_phone, text, title=title, tags="ambulance,rotating_light,hospital", priority="urgent")
        threading.Thread(target=go_amb, daemon=True).start()
        return

    # 3. ACCIDENT DETECTION & IN-PLACE UPDATE (Updates existing record without overwriting others)
    acc_rec = emergency_mgr.update_or_add_accident(zone_id=zone, severity="HIGH", details=f"{kind} detected")
    acc_id = acc_rec["accident_id"]
    upd_cnt = acc_rec["update_count"]

    # Check if this accident ID is already in the UI ALERTS list; if so, update it in-place!
    existing_entry = next((e for e in ALERTS if e.get("accident_id") == acc_id), None)
    if existing_entry is not None:
        existing_entry["kind"] = f"ACCIDENT {acc_id} ({kind} - Update #{upd_cnt} at {zone})"
        existing_entry["time"] = ts
        if name:
            existing_entry["img"] = name
        title = f"ACCIDENT UPDATED [{acc_id}]"
        text = f"ACCIDENT UPDATE #{upd_cnt} ({acc_id}): {kind} still active at {zone} ({ts}). Phone: {target_phone}."
        def go_upd():
            existing_entry["results"] = alerts.send(target_phone, text, title=title, tags="warning,car", priority="high")
        threading.Thread(target=go_upd, daemon=True).start()
    else:
        entry = dict(
            accident_id=acc_id,
            kind=f"NEW ACCIDENT {acc_id} ({kind} at {zone})",
            time=ts,
            img=name,
            results=["Sending accident alert..."]
        )
        ALERTS.append(entry)
        title = f"ACCIDENT DETECTED [{acc_id}]"
        text = f"NEW ACCIDENT ({acc_id}): Possible {kind} detected at {zone} ({ts}). Phone: {target_phone}."
        def go_new():
            entry["results"] = alerts.send(target_phone, text, title=title, tags="collision,car,police_car", priority="urgent")
        threading.Thread(target=go_new, daemon=True).start()


def worker():
    global JPEG
    model = cap = None; seen = NOSRC; ema = None; eh = deque(maxlen=400); ts = deque(maxlen=25); ids = set(); last = 0; fid = 0
    acc = AccidentDetector(stall_s=AL["stall_s"], hold_s=0.6)
    lastalert = 0; last_amb_alert = 0
    while True:
        try:
            if ST["source"] is not seen:
                if cap: cap.release()
                seen = ST["source"]; cap = None; ema = None; eh.clear(); ids.clear()
                if seen is not NOSRC and seen is not None:
                    cap = opencap(seen)
                    if not cap.isOpened():
                        cap = None; ST["error"] = f"Could not open {ST['label']}. Use an MP4 file or a stream URL you are permitted to use."
                    else: ST["error"] = None
            if cap is None or not S["run"]: time.sleep(.1); continue
            if model is None:
                ST["status"] = "Loading YOLO model (first run downloads yolo11n.pt)"
                from ultralytics import YOLO
                model = YOLO("yolo11n.pt")
            t0 = time.time(); ok, frame = cap.read()
            if not ok:
                if isinstance(seen, str) and Path(seen).exists(): cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                else: cap.release(); cap = opencap(seen)
                time.sleep(.05); continue
            h, w = frame.shape[:2]
            if w > 640: frame = cv2.resize(frame, (640, max(2, int(h * 640 / w)))); h, w = frame.shape[:2]
            kw = dict(imgsz=S["imgsz"], conf=S["conf"], classes=list(CLS), device="cpu", verbose=False)
            t1 = time.time()
            if S["track"] or AL["enabled"]:
                try: r = model.track(frame, persist=True, tracker="bytetrack.yaml", **kw)[0]
                except Exception as e: S["track"] = False; AL["enabled"] = False; ST["error"] = f"Tracking unavailable ({e}). Using detection only; accident alerts are off."; r = model.predict(frame, **kw)[0]
            else: r = model.predict(frame, **kw)[0]
            infer = (time.time() - t1) * 1000
            rx, ry, rw, rh = S["roi"]; X1, Y1, X2, Y2 = int(rx * w), int(ry * h), int((rx + rw) * w), int((ry + rh) * h)
            roi_area = max(1, (X2 - X1) * (Y2 - Y1)); cnt = rc = 0; inter = 0; per = {v: 0 for v in CLS.values()}
            bx = r.boxes; tid = bx.id.cpu().numpy().astype(int) if bx.id is not None else None; bl, il = [], []
            now = time.time()
            amb_box = None

            for i, b in enumerate(bx):
                c = int(b.cls.item())
                if c not in CLS: continue
                x1, y1, x2, y2 = b.xyxy[0].cpu().numpy().astype(int).tolist(); cnt += 1; per[CLS[c]] += 1
                conf_val = float(b.conf.item())
                inside = X1 <= (x1 + x2) / 2 <= X2 and Y1 <= (y1 + y2) / 2 <= Y2
                if inside:
                    rc += 1; inter += max(0, min(x2, X2) - max(x1, X1)) * max(0, min(y2, Y2) - max(y1, Y1))
                if tid is not None: ids.add(int(tid[i])); bl.append((x1, y1, x2, y2)); il.append(int(tid[i]))
                else: bl.append((x1, y1, x2, y2)); il.append(i + 1)

                # Check for Ambulance
                raw_name = r.names.get(c, CLS[c]) if hasattr(r, "names") else CLS[c]
                if _is_ambulance_visual(frame, x1, y1, x2, y2, raw_name, ST.get("label", "")):
                    amb_box = (x1, y1, x2, y2)
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 215, 255), 3)
                    cv2.putText(frame, f"AMBULANCE {conf_val:.2f}", (x1, max(14, y1 - 20)),
                                cv2.FONT_HERSHEY_SIMPLEX, .55, (0, 215, 255), 2, cv2.LINE_AA)

                col = (52, 177, 242) if inside else (180, 190, 60)
                cv2.rectangle(frame, (x1, y1), (x2, y2), col, 2)
                cv2.putText(frame, f"{CLS[c]} {conf_val:.2f}" + (f" #{tid[i]}" if tid is not None else ""),
                            (x1, max(14, y1 - 5)), cv2.FONT_HERSHEY_SIMPLEX, .45, col, 1, cv2.LINE_AA)

            # Trigger Ambulance Alert if detected and cooldown elapsed
            if amb_box and AL["enabled"] and (now - last_amb_alert > AL["cooldown"]):
                last_amb_alert = now
                ST["amb_t"] = now
                fire("ambulance in emergency", frame, category="ambulance")

            ov = frame.copy(); cv2.rectangle(ov, (X1, Y1), (X2, Y2), (52, 177, 242), -1)
            frame = cv2.addWeighted(ov, .10, frame, .90, 0); cv2.rectangle(frame, (X1, Y1), (X2, Y2), (52, 177, 242), 2)
            ema = rc if ema is None else .8 * ema + .2 * rc; eh.append((now, ema))
            old = next((v for tt, v in eh if now - tt <= 5), ema); growth = ema - old
            Q, O, G, D = clamp(ema / S["cap"]), clamp(inter / roi_area / .35), clamp(growth / 4), clamp(S["downstream"])
            R = .35 * Q + .25 * O + .20 * G + .20 * D
            ts.append(now); fps = (len(ts) - 1) / (ts[-1] - ts[0]) if len(ts) > 1 else 0

            # Trigger Accident Detection (Tracked motion or severe multi-car collision IoU)
            acc.stall_s = AL["stall_s"]
            ev = acc.update(now, bl, il, w) if AL["enabled"] and il else None
            if ev is None and AL["enabled"] and len(bl) >= 2:
                from accident import iou as calc_iou
                for idx_a in range(len(bl)):
                    for idx_b in range(idx_a + 1, len(bl)):
                        if calc_iou(bl[idx_a], bl[idx_b]) > 0.68:
                            A, B = bl[idx_a], bl[idx_b]
                            ev = dict(kind="collision", ids=[idx_a, idx_b], box=[min(A[0], B[0]), min(A[1], B[1]), max(A[2], B[2]), max(A[3], B[3])])
                            break
                    if ev: break

            if ev and now - lastalert > AL["cooldown"]:
                lastalert = now; x1, y1, x2, y2 = [int(v) for v in ev["box"]]
                cv2.rectangle(frame, (x1, y1), (x2, y2), (60, 60, 255), 3)
                ST["acc_t"] = now
                fire(ev["kind"], frame, category="accident")

            if now - ST.get("amb_t", 0) < 6:
                cv2.rectangle(frame, (0, 0), (w, 30), (0, 140, 255), -1)
                cv2.putText(frame, "AMBULANCE IN EMERGENCY - GREEN CORRIDOR ALERT SENT", (10, 21), cv2.FONT_HERSHEY_SIMPLEX, .55, (255, 255, 255), 2, cv2.LINE_AA)
            elif now - ST.get("acc_t", 0) < 6:
                cv2.rectangle(frame, (0, 0), (w, 30), (40, 40, 220), -1)
                cv2.putText(frame, "POSSIBLE ACCIDENT - ALERT UPDATED & SENT", (10, 21), cv2.FONT_HERSHEY_SIMPLEX, .6, (255, 255, 255), 2, cv2.LINE_AA)

            ok2, jb = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80]); fid += 1; JPEG = (jb.tobytes(), fid)
            ST.update(fps=fps, infer_ms=infer, latency_ms=(time.time() - t0) * 1000, count=cnt, roi_count=rc, occ=inter / roi_area,
                      growth=growth, classes=per, comp=dict(Q=Q, O=O, G=G, D=D), R=R, frames=ST["frames"] + 1, unique=len(ids), status="Running")
            if now - last > .2:
                last = now; LOG.append(dict(t=round(now, 2), fps=round(fps, 2), infer_ms=round(infer, 1), vehicles=cnt, roi_count=rc,
                                            occupancy=round(inter / roi_area, 3), queue_growth=round(growth, 2), Q=round(Q, 3), O=round(O, 3),
                                            G=round(G, 3), D=round(D, 3), risk=round(R, 3), level=label(R)))
            fp = cap.get(cv2.CAP_PROP_FPS) or 25
            if S["realtime"] and isinstance(seen, str) and Path(seen).exists(): time.sleep(max(0, 1 / min(fp, 60) - (time.time() - t0)))
        except Exception as e:
            ST["error"] = f"{type(e).__name__}: {e}"; ST["status"] = "Error"; time.sleep(1)

threading.Thread(target=worker, daemon=True).start()

@app.get("/")
def index(): return FileResponse(ROOT / "web" / "index.html", headers={"Cache-Control": "no-store"})

@app.get("/api/stream")
def stream():
    def gen():
        last = -1
        while True:
            b, i = JPEG
            if b and i != last:
                last = i; yield b"--f\r\nContent-Type: image/jpeg\r\nContent-Length: %d\r\n\r\n" % len(b) + b + b"\r\n"
            else: time.sleep(.01)
    return StreamingResponse(gen(), media_type="multipart/x-mixed-replace; boundary=f")

@app.get("/api/state")
def state():
    r = ST["R"] * 100; g = build_intersection_graph()
    init = {"J1": r, "J2": max(10, r * .72), "J3": max(8, r * .48), "J4": max(8, r * .40), "J5": max(5, r * .32)}
    for acc in emergency_mgr.accident_log:
        if acc["status"] == "ACTIVE" and acc["zone_id"] in init:
            init[acc["zone_id"]] = max(init[acc["zone_id"]], 88.0)
    risks = propagate_cascade_risk(g, init)
    adv = advise(ST["R"], ST["comp"], risks, [[u, v, d["weight"]] for u, v, d in g.edges(data=True)])
    base = dict(
        al=dict(cfg=AL, providers=alerts.providers(), log=list(ALERTS)[-8:], active=(time.time() - max(ST.get("acc_t", 0), ST.get("amb_t", 0)) < 6)),
        advice=adv, st=ST, s=S, hist=list(LOG)[-150:],
        sys=dict(cpu=psutil.cpu_percent(None), ram=psutil.virtual_memory().percent),
        graph=dict(risks=risks, edges=[[u, v, d["weight"]] for u, v, d in g.edges(data=True)])
    )
    return emergency_mgr.enrich_payload(base)

@app.post("/api/settings")
def settings(p: dict = Body(...)):
    for k in S:
        if k in p: S[k] = p[k]
    S["roi"] = [clamp(v, 0, 1) for v in S["roi"]]; S["conf"] = clamp(S["conf"], .05, .95); S["imgsz"] = int(S["imgsz"])
    return S

def setsrc(src, name): ST.update(source=src, label=name, frames=0, error=None, status="Opening source")

@app.post("/api/source/upload")
async def upload(file: UploadFile = File(...)):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in VEXT:
        return JSONResponse({"error": f"Unsupported file type '{ext or 'none'}'. Use MP4, AVI, MOV, MKV or MPG."}, 400)
    dest = VDIR / Path(file.filename).name; dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "wb") as f: shutil.copyfileobj(file.file, f)
    setsrc(str(dest), file.filename); return {"ok": True}

@app.post("/api/source/url")
def url(p: dict = Body(...)):
    u = str(p.get("url", "")).strip()
    if not u.startswith(("http://", "https://", "rtsp://")): return JSONResponse({"error": "Enter an http(s) or rtsp URL you are permitted to use."}, 400)
    setsrc(u, u); return {"ok": True}

@app.post("/api/source/camera")
def camera(p: dict = Body(...)):
    i = int(p.get("index", 0)); setsrc(i, f"Camera {i}"); return {"ok": True}

@app.get("/api/cameras")
def cameras():
    found = []
    for i in range(5):
        if ST["source"] is not NOSRC and isinstance(ST["source"], int) and ST["source"] == i: found.append(i); continue
        c = opencap(i); ok = c.isOpened(); c.release()
        if ok: found.append(i)
    return dict(cameras=found)

@app.get("/api/videos")
def videos():
    VDIR.mkdir(parents=True, exist_ok=True)
    return dict(videos=[dict(name=f.name, mb=round(f.stat().st_size / 1e6, 1)) for f in sorted(VDIR.iterdir()) if f.suffix.lower() in VEXT])

@app.post("/api/source/video")
def video(p: dict = Body(...)):
    f = VDIR / Path(str(p.get("name", ""))).name
    if not f.is_file(): return JSONResponse({"error": "That video is no longer in data/videos."}, 404)
    setsrc(str(f), f.name); return {"ok": True}

@app.post("/api/source/path")
def path(p: dict = Body(...)):
    f = Path(str(p.get("path", "")).strip().strip('"'))
    if not f.is_file() or f.suffix.lower() not in VEXT: return JSONResponse({"error": "File not found or not a video (MP4, AVI, MOV, MKV, MPG). Check the full path."}, 400)
    setsrc(str(f), f.name); return {"ok": True}

@app.get("/api/sumo")
def sumo_status():
    try:
        import shutil, sumolib, traci
        b = sumolib.checkBinary("sumo")
        if not (os.path.exists(b) or shutil.which(b)): raise RuntimeError("SUMO program not found")
        return dict(ok=True, binary=b)
    except Exception as e: return dict(ok=False, reason=str(e)[:200])

@app.post("/api/alerts/config")
def alert_cfg(p: dict = Body(...)):
    to = str(p.get("to", "")).strip()
    if to and not re.fullmatch(r"\+\d{8,15}", to): return JSONResponse({"error": "Enter the number with country code and no spaces, like +919876543210."}, 400)
    AL.update(enabled=bool(p.get("enabled")), to=to, cooldown=max(5, min(600, int(p.get("cooldown", 20)))))
    emergency_mgr.target_phone = to or emergency_mgr.target_phone
    AFILE.parent.mkdir(parents=True, exist_ok=True); AFILE.write_text(json.dumps({"to": to})); return AL

@app.post("/api/alerts/test")
def alert_test():
    fire("test", None, test=True)
    return {"ok": True}

@app.get("/alerts/{name}")
def alert_img(name: str):
    f = ADIR / Path(name).name
    return FileResponse(f) if f.is_file() else JSONResponse({"error": "not found"}, 404)

@app.post("/api/emergency/ambulance")
def trigger_ambulance(p: dict = Body(default={"zone_id": "J1", "confidence": 0.95})):
    if p.get("phone_number"): AL["to"] = str(p["phone_number"])
    fire("ambulance in emergency", None, category="ambulance")
    return {"ok": True, "message": "Ambulance emergency notification triggered"}

@app.post("/api/emergency/accident")
def update_accident(p: dict = Body(default={"zone_id": "J1", "severity": "HIGH", "details": "collision"})):
    fire(str(p.get("details", "collision")), None, category="accident")
    return {"ok": True, "message": "Accident updated without overwriting existing records"}

@app.post("/api/sim")
def run_sim(p: dict = Body(...)):
    name = p.get("scenario") if p.get("scenario") in sim.SCEN else "blockage"; seed = int(p.get("seed", 1)); runs = max(1, min(20, int(p.get("runs", 3))))
    try:
        import sumo_sim
        return sumo_sim.run_all(name, seed, runs)
    except Exception as e:
        r = sim.run_all(name, seed, runs); r["engine"] = f"Built-in queue model (SUMO not available: {str(e)[:90]})"; return r

@app.get("/api/export.csv")
def export():
    rows = list(LOG); buf = io.StringIO()
    if rows: w = csv.DictWriter(buf, rows[0].keys()); w.writeheader(); w.writerows(rows)
    return PlainTextResponse(buf.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=gridguard_live_metrics.csv"})

def free_port(start=8000):
    import socket
    for q in range(start, start + 20):
        with socket.socket() as k:
            if k.connect_ex(("127.0.0.1", q)) != 0: return q
    return start

if __name__ == "__main__":
    port = free_port(); url = f"http://127.0.0.1:{port}"
    print(f"\nGRIDGUARD AI v5 (landing page + ambulance & accident alerts)\nRunning from: {ROOT}\nOpen: {url}\n")
    threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")