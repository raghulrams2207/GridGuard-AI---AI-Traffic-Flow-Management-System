# GRIDGUARD-AI/emergency_extensions.py
import os
import time
import requests
from datetime import datetime

class EmergencyManager:
    def __init__(self, cooldown_seconds=1):
        self.ntfy_topic = os.getenv("NTFY_TOPIC", "gridguard_alert_999")
        self.target_phone = os.getenv("ALERT_PHONE_NUMBER", "+918012866114")

        self.cooldown_seconds = cooldown_seconds
        self.last_ambulance_sms_time = 0
        self.ambulance_events = []
        self.accident_log = []

    def send_phone_alert(self, message: str, title: str = "GRIDGUARD-AI ALERT", priority: str = "urgent") -> bool:
        print(f"\n🚨 [EMERGENCY NOTIFICATION] {title} 🚨\n-> {message}\n")
        url = f"https://ntfy.sh/{self.ntfy_topic}"
        headers = {
            "Title": title,
            "Priority": priority,
            "Tags": "rotating_light,ambulance"
        }
        try:
            resp = requests.post(
                url,
                data=message.encode("utf-8"),
                headers=headers,
                timeout=3
            )
            if resp.status_code == 200:
                print(f"[PHONE ALERT SENT via ntfy.sh] Topic: '{self.ntfy_topic}'")
                return True
        except Exception:
            pass
        return False

    def notify_ambulance(self, zone_id="Sector-1", confidence=0.85):
        """Triggers a distinct ambulance push notification with emergency tags."""
        now = time.time()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        event = {
            "zone_id": zone_id,
            "confidence": round(float(confidence), 2),
            "phone_number": self.target_phone,
            "ntfy_topic": self.ntfy_topic,
            "timestamp": timestamp,
            "alert_sent": False
        }

        if now - self.last_ambulance_sms_time >= self.cooldown_seconds:
            self.last_ambulance_sms_time = now
            
            # Distinct message format specifically for ambulances
            msg = (
                f"🚑 EMERGENCY AMBULANCE DETECTED!\n"
                f"• Zone / Location: {zone_id}\n"
                f"• Confidence: {confidence:.0%}\n"
                f"• Time: {timestamp}\n"
                f"Action Required: Clear Green Corridor immediately!"
            )
            
            # Send using dedicated ambulance title and urgent siren tags
            url = f"https://ntfy.sh/{self.ntfy_topic}"
            headers = {
                "Title": "🚨 AMBULANCE - GREEN CORRIDOR REQUIRED",
                "Priority": "urgent",
                "Tags": "ambulance,rotating_light,fire"
            }
            try:
                resp = requests.post(
                    url,
                    data=msg.encode("utf-8"),
                    headers=headers,
                    timeout=3
                )
                print(f"\n🚨 [AMBULANCE ALERT] Sent to topic '{self.ntfy_topic}'\n-> {msg}\n")
                event["alert_sent"] = (resp.status_code == 200)
            except Exception:
                print(f"\n🚨 [AMBULANCE ALERT (Offline)]\n-> {msg}\n")

        self.ambulance_events.append(event)
        return event
    
    def update_or_add_accident(self, zone_id="Sector-1", severity="HIGH", details="Vehicle collision / Stationary block"):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Check if an active accident exists in this zone
        for acc in self.accident_log:
            if acc["zone_id"] == zone_id and acc["status"] == "ACTIVE":
                acc["severity"] = severity
                acc["details"] = details
                acc["last_updated"] = timestamp
                acc["update_count"] += 1
                
                # <--- ADDED: Send a notification on updates too if desired --->
                self.send_phone_alert(
                    message=f"Updated Accident ({acc['accident_id']}) at {zone_id} | Count: {acc['update_count']} | {details}",
                    title="ACCIDENT UPDATED - GRIDGUARD-AI",
                    priority="high"
                )
                return acc

        # Otherwise create a new accident record
        new_accident = {
            "accident_id": f"ACC-{len(self.accident_log) + 1:03d}",
            "zone_id": zone_id,
            "severity": severity,
            "details": details,
            "reported_at": timestamp,
            "last_updated": timestamp,
            "update_count": 1,
            "status": "ACTIVE"
        }
        self.accident_log.append(new_accident)

        self.send_phone_alert(
            message=f"New Accident ({new_accident['accident_id']}) at {zone_id} | Severity: {severity} | {details}",
            title="ACCIDENT DETECTED - GRIDGUARD-AI",
            priority="high"
        )
        return new_accident

    def resolve_accident(self, accident_id: str):
        for acc in self.accident_log:
            if acc["accident_id"] == accident_id:
                acc["status"] = "RESOLVED"
                acc["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                return acc
        return None

    def enrich_payload(self, existing_payload: dict) -> dict:
        updated = dict(existing_payload)
        updated["emergency_extensions"] = {
            "active_accidents": [a for a in self.accident_log if a["status"] == "ACTIVE"],
            "all_accidents": self.accident_log,
            "recent_ambulances": self.ambulance_events[-10:],
            "last_alert_epoch": self.last_ambulance_sms_time,
            "ntfy_topic": self.ntfy_topic
        }
        return updated

emergency_mgr = EmergencyManager()