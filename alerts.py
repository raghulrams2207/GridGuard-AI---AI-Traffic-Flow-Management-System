"""Demo alert delivery to a teammate's phone: ntfy.sh, Twilio SMS, and/or Telegram.
This is NOT a link to real emergency services. In a real emergency call your local number (108 in India)."""
import base64, os, urllib.parse, urllib.request
from pathlib import Path

def load_env(path):
    p = Path(path)
    if p.is_file():
        for line in p.read_text(encoding="utf8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"'))

def providers():
    e = os.environ.get
    ntfy_topic = e("NTFY_TOPIC", "gridguard_alert_999")
    return dict(
        twilio=bool((e("TWILIO_ACCOUNT_SID") and e("TWILIO_AUTH_TOKEN") and e("TWILIO_FROM")) or ntfy_topic),
        telegram=bool(e("TELEGRAM_BOT_TOKEN") and e("TELEGRAM_CHAT_ID")),
        ntfy_topic=ntfy_topic
    )

def send(to, text, title="GRIDGUARD-AI ALERT", tags="warning,car", priority="urgent"):
    """Sends distinct notifications via ntfy.sh, Twilio, and/or Telegram."""
    res, e = [], os.environ.get
    ntfy_topic = e("NTFY_TOPIC", "gridguard_alert_999")

    # 1. Instant Phone Push Notification via ntfy.sh (with distinct Ambulance vs Accident headers)
    if ntfy_topic:
        try:
            req = urllib.request.Request(
                f"https://ntfy.sh/{ntfy_topic}",
                data=text.encode("utf-8"),
                headers={
                    "Title": title,
                    "Priority": priority,
                    "Tags": tags
                },
                method="POST"
            )
            urllib.request.urlopen(req, timeout=4)
            phone_tag = f" ({to})" if to else ""
            res.append(f"Phone notification sent via ntfy/{ntfy_topic}{phone_tag}")
        except Exception as x:
            print(f"[NTFY OFFLINE FALLBACK] {title}: {text}")
            res.append(f"Shown on console/UI (ntfy offline: {str(x)[:40]})")

    # 2. Twilio SMS (if configured in .env)
    if e("TWILIO_ACCOUNT_SID") and e("TWILIO_AUTH_TOKEN") and e("TWILIO_FROM") and to:
        try:
            sid = e("TWILIO_ACCOUNT_SID")
            req = urllib.request.Request(
                f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
                data=urllib.parse.urlencode({"To": to, "From": e("TWILIO_FROM"), "Body": text}).encode()
            )
            req.add_header("Authorization", "Basic " + base64.b64encode(f"{sid}:{e('TWILIO_AUTH_TOKEN')}".encode()).decode())
            urllib.request.urlopen(req, timeout=15)
            res.append(f"SMS sent to {to[:3]}******{to[-3:]}")
        except Exception as x:
            res.append(f"SMS failed: {str(x)[:80]}")

    # 3. Telegram (if configured in .env)
    if e("TELEGRAM_BOT_TOKEN") and e("TELEGRAM_CHAT_ID"):
        try:
            tok = e("TELEGRAM_BOT_TOKEN")
            req = urllib.request.Request(
                f"https://api.telegram.org/bot{tok}/sendMessage",
                data=urllib.parse.urlencode({"chat_id": e("TELEGRAM_CHAT_ID"), "text": f"{title}\n{text}"}).encode()
            )
            urllib.request.urlopen(req, timeout=15)
            res.append("Telegram message sent")
        except Exception as x:
            res.append(f"Telegram failed: {str(x)[:80]}")

    return res or ["Alert logged on screen"]