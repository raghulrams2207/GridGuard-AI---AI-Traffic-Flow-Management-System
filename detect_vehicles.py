# GRIDGUARD-AI/detect_vehicles.py
import cv2
import numpy as np
from pathlib import Path
from emergency_extensions import emergency_mgr

try:
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
except ImportError:
    YOLO_AVAILABLE = False

# Standard COCO vehicle class IDs: 2=car, 3=motorcycle, 5=bus, 7=truck
VEHICLE_CLASSES = {2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}

class VehicleDetector:
    def __init__(self, model_path="yolov8n.pt", conf_threshold=0.40):
        self.conf_threshold = conf_threshold
        self.model = YOLO(model_path) if YOLO_AVAILABLE else None
        self.prev_boxes = []

    def _compute_iou(self, boxA, boxB):
        """Computes Intersection over Union (IoU) between two bounding boxes to detect collisions."""
        xA = max(boxA[0], boxB[0])
        yA = max(boxA[1], boxB[1])
        xB = min(boxA[2], boxB[2])
        yB = min(boxA[3], boxB[3])

        interArea = max(0, xB - xA) * max(0, yB - yA)
        if interArea == 0:
            return 0.0

        boxAArea = (boxA[2] - boxA[0]) * (boxA[3] - boxA[1])
        boxBArea = (boxB[2] - boxB[0]) * (boxB[3] - boxB[1])
        return interArea / float(boxAArea + boxBArea - interArea + 1e-6)

    def detect_frame(self, frame, zone_id="Sector-1"):
        """
        Runs vehicle detection on a single frame and triggers non-invasive hooks
        for ambulance SMS and accident updates.
        """
        detections = []
        vehicle_counts = {"car": 0, "motorcycle": 0, "bus": 0, "truck": 0, "ambulance": 0}
        ambulance_detected = False
        accident_detected = False

        if self.model is not None and frame is not None:
            results = self.model(frame, conf=self.conf_threshold, verbose=False)
            boxes_list = []

            for r in results:
                names = r.names
                for box in r.boxes:
                    cls_id = int(box.cls[0])
                    conf = float(box.conf[0])
                    label = names.get(cls_id, str(cls_id)).lower()
                    xyxy = box.xyxy[0].cpu().numpy().tolist()

                    # 1. Standard vehicle counting
                    if cls_id in VEHICLE_CLASSES:
                        v_type = VEHICLE_CLASSES[cls_id]
                        vehicle_counts[v_type] += 1
                        boxes_list.append(xyxy)
                    elif label in vehicle_counts:
                        vehicle_counts[label] += 1
                        boxes_list.append(xyxy)

                    # 2. Ambulance detection (Custom YOLO class or label match)
                    if "ambulance" in label or "emergency" in label:
                        vehicle_counts["ambulance"] += 1
                        ambulance_detected = True
                        emergency_mgr.notify_ambulance(zone_id=zone_id, confidence=conf)

                    # 3. Direct Accident class detection (if using custom-trained weights)
                    if "accident" in label or "crash" in label or "collision" in label:
                        accident_detected = True
                        emergency_mgr.update_or_add_accident(
                            zone_id=zone_id,
                            severity="CRITICAL",
                            details=f"Visual crash detected ({conf:.0%} confidence)"
                        )

                    detections.append({
                        "label": label,
                        "confidence": round(conf, 3),
                        "bbox": [round(x, 1) for x in xyxy]
                    })

            # 4. Heuristic Accident Detection (High IoU overlap between multiple vehicles)
            for i in range(len(boxes_list)):
                for j in range(i + 1, len(boxes_list)):
                    iou = self._compute_iou(boxes_list[i], boxes_list[j])
                    if iou > 0.65:  # Severe bounding box overlap threshold
                        accident_detected = True
                        emergency_mgr.update_or_add_accident(
                            zone_id=zone_id,
                            severity="HIGH",
                            details=f"Vehicle overlap/collision anomaly (IoU={iou:.2f})"
                        )

        total_vehicles = sum(vehicle_counts.values())

        # Return structure compatible with existing GRIDGUARD-AI pipelines + new flags
        return {
            "zone_id": zone_id,
            "total_vehicles": total_vehicles,
            "counts": vehicle_counts,
            "detections": detections,
            "ambulance_detected": ambulance_detected,
            "accident_detected": accident_detected,
        }


def detect_vehicles_from_video(video_path: str, zone_id="Sector-1", max_frames=100):
    """Helper function if your existing pipeline calls a function instead of a class."""
    detector = VehicleDetector()
    cap = cv2.VideoCapture(video_path)
    summary = []
    frame_idx = 0

    while cap.isOpened() and frame_idx < max_frames:
        ret, frame = cap.read()
        if not ret:
            break
        res = detector.detect_frame(frame, zone_id=zone_id)
        summary.append(res)
        frame_idx += 1

    cap.release()
    return summary[-1] if summary else {
        "zone_id": zone_id,
        "total_vehicles": 0,
        "counts": {"car": 0, "motorcycle": 0, "bus": 0, "truck": 0, "ambulance": 0},
        "detections": [],
        "ambulance_detected": False,
        "accident_detected": False
    }