import base64
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Dict, List

DATA_FILE = Path(__file__).resolve().parent / "data.json"
TEMPLATE_FILE = Path(__file__).resolve().parent / "index.html"

DEFAULT_DATA = {
    "current_balance": 0.0,
    "total_earned_lifetime": 0.0,
    "last_activity_id": "",
    "weight_history": [],
    "redeemed_count": 0,
    "collectibles_list": [
        {"id": 1, "name": "Coffee Mug", "cost": 25.0, "status": "locked"},
        {"id": 2, "name": "Desk Plant", "cost": 50.0, "status": "locked"},
        {"id": 3, "name": "Massage Gift Card", "cost": 100.0, "status": "locked"},
    ],
    "budget_a_spend": 0.0,
    "budget_b_unlocked": False,
    "max_allowed_redeems": 0,
}

WEIGHT_MILESTONES = [220, 215, 210, 205, 200, 195, 190, 185, 180, 175, 170]


def ensure_data_file() -> None:
    if not DATA_FILE.exists():
        save_data(DEFAULT_DATA.copy())


def load_data() -> Dict[str, Any]:
    ensure_data_file()
    with DATA_FILE.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    for key, value in DEFAULT_DATA.items():
        if key not in data:
            data[key] = value
    return data


def save_data(data: Dict[str, Any]) -> None:
    with DATA_FILE.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)


def get_rolling_average(weight_history: List[Dict[str, Any]]) -> float:
    if not weight_history:
        return 0.0
    recent = weight_history[-7:]
    values = [item["weight"] for item in recent if "weight" in item]
    if not values:
        return 0.0
    return round(sum(values) / len(values), 2)


def next_milestone(weight_history: List[Dict[str, Any]]) -> float:
    average = get_rolling_average(weight_history)
    for milestone in sorted(WEIGHT_MILESTONES, reverse=True):
        if milestone <= average:
            return float(milestone)
    return float(WEIGHT_MILESTONES[-1])


def update_collectible_status(data: Dict[str, Any]) -> None:
    average = get_rolling_average(data.get("weight_history", []))
    next_gate = next_milestone(data.get("weight_history", []))
    for item in data.get("collectibles_list", []):
        if item.get("status") == "redeemed":
            continue
        if average <= next_gate and item.get("cost", 0) <= data.get("current_balance", 0.0):
            item["status"] = "affordable"
        else:
            item["status"] = "locked"


def is_biking_meal_fund_unlocked(activity: Dict[str, Any]) -> bool:
    name = (activity.get("name") or "").lower()
    commute = str(activity.get("commute") or "").lower() == "true"
    near_food = any(token in name for token in ["food", "restaurant", "cafe", "coffee"])
    return commute or near_food


def handle_weight_data(payload: Dict[str, Any], send_sms: bool = False) -> Dict[str, Any]:
    data = load_data()
    date_value = payload.get("date") or datetime.utcnow().strftime("%Y-%m-%d")
    weight_value = float(payload.get("weight", 0.0))

    history = data.get("weight_history", [])
    if not any(entry.get("date") == date_value for entry in history):
        history.append({"date": date_value, "weight": weight_value})
    else:
        for entry in history:
            if entry.get("date") == date_value:
                entry["weight"] = weight_value
                break
    data["weight_history"] = history

    average = get_rolling_average(data.get("weight_history", []))
    next_gate = next_milestone(data.get("weight_history", []))
    redeemable = average <= next_gate
    if len(data.get("weight_history", [])) >= 2:
        data["max_allowed_redeems"] = data.get("max_allowed_redeems", 0) + 1

    update_collectible_status(data)
    save_data(data)

    if send_sms and redeemable:
        send_sms_message(
            f"You have reached your threshold, you can redeem up to 1 gift! Click here to choose your collectible: {os.getenv('SITE_URL', 'https://example.com')}"
        )
        send_telegram_message(
            f"You have reached your threshold, you can redeem up to 1 gift! Visit {os.getenv('SITE_URL', 'https://example.com')}"
        )

    return {
        "rolling_average": average,
        "next_gate": next_gate,
        "redeemable": redeemable,
        "current_balance": data.get("current_balance", 0.0),
        "max_allowed_redeems": data.get("max_allowed_redeems", 0),
    }


def handle_activity_data(activity: Dict[str, Any], send_sms: bool = False) -> Dict[str, Any]:
    data = load_data()

    activity_type = (activity.get("type") or "").lower()
    distance = float(activity.get("distance") or 0.0)
    earnings = 0.0
    budget_a_remaining = 0.0
    budget_b_unlocked = False

    if activity_type == "ride":
        earnings = round(distance * 0.81, 2)
        budget_a_remaining = max(200.0 - (data.get("budget_a_spend", 0.0) + earnings), 0.0)
        budget_b_unlocked = is_biking_meal_fund_unlocked(activity)
        if budget_b_unlocked:
            data["budget_b_unlocked"] = True
    elif activity_type == "walk":
        earnings = round(distance * 2.43, 2)
        budget_a_remaining = max(200.0 - (data.get("budget_a_spend", 0.0) + earnings), 0.0)
    elif activity_type in {"strength", "hevy"}:
        earnings = 5.0
        budget_a_remaining = max(200.0 - (data.get("budget_a_spend", 0.0) + earnings), 0.0)
    else:
        budget_a_remaining = max(200.0 - data.get("budget_a_spend", 0.0), 0.0)

    data["budget_a_spend"] = round(data.get("budget_a_spend", 0.0) + earnings, 2)
    data["current_balance"] = round(data.get("current_balance", 0.0) + earnings, 2)
    data["total_earned_lifetime"] = round(data.get("total_earned_lifetime", 0.0) + earnings, 2)
    data["last_activity_id"] = str(activity.get("id") or "")

    update_collectible_status(data)
    save_data(data)

    if send_sms and earnings > 0:
        send_sms_message(
            f"Congrats! ${earnings:.2f} has been put toward your total. Click here for more info: {os.getenv('SITE_URL', 'https://example.com')}"
        )
        send_telegram_message(
            f"Congrats! ${earnings:.2f} has been put toward your total. Visit {os.getenv('SITE_URL', 'https://example.com')}"
        )

    return {
        "earnings": earnings,
        "budget_a_remaining": budget_a_remaining,
        "budget_b_unlocked": budget_b_unlocked,
        "current_balance": data.get("current_balance", 0.0),
    }


def send_sms_message(message: str) -> None:
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    from_number = os.getenv("TWILIO_FROM_NUMBER")
    to_number = os.getenv("TWILIO_TO_NUMBER")
    if not all([account_sid, auth_token, from_number, to_number]):
        print(f"SMS skipped; message: {message}")
        return

    data = urllib.parse.urlencode({
        "To": to_number,
        "From": from_number,
        "Body": message,
    }).encode("utf-8")
    url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    req.add_header(
        "Authorization",
        "Basic " + base64.b64encode(f"{account_sid}:{auth_token}".encode("utf-8")).decode("ascii"),
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            response.read()
    except Exception as exc:  # pragma: no cover
        print(f"SMS failed: {exc}")


def get_daily_prompt_message() -> str:
    today = datetime.utcnow().strftime("%A")
    if today in {"Monday", "Wednesday", "Friday", "Sunday"}:
        return "Today is Day A: Power & Posture (Squats/Glute Bridges/Planks)"
    return "Today is Day B: Balance & Armor (Lunges/Calf Raises/Lateral Raises)"


def build_telegram_payload(message: str, chat_id: str) -> Dict[str, Any]:
    return {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
    }


def send_telegram_message(message: str) -> None:
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not bot_token or not chat_id:
        print(f"Telegram skipped; message: {message}")
        return

    payload = json.dumps(build_telegram_payload(message, chat_id)).encode("utf-8")
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    req = urllib.request.Request(url, data=payload, method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            response.read()
    except Exception as exc:  # pragma: no cover
        print(f"Telegram failed: {exc}")


def build_dashboard_html() -> str:
    data = load_data()
    average = get_rolling_average(data.get("weight_history", []))
    next_gate = next_milestone(data.get("weight_history", []))
    collectibles = data.get("collectibles_list", [])
    items_html = []
    for item in collectibles:
        status = item.get("status", "locked")
        color = "#f87171" if status == "locked" else "#4ade80" if status == "affordable" else "#60a5fa"
        items_html.append(
            f'<li style="margin: 0.35rem 0; padding: 0.5rem; border-left: 5px solid {color};">{item.get("name")} — ${item.get("cost", 0):.2f} ({status})</li>'
        )
    items_html = "".join(items_html) or "<li>No collectibles configured yet.</li>"
    meal_status = "Unlocked for use" if data.get("budget_b_unlocked", False) else "Awaiting a bike meal activity"
    return f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>Collectables Earner Dashboard</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 0; background: #f7f7fb; color: #111827; }}
    .card {{ max-width: 960px; margin: 2rem auto; padding: 1.25rem; background: white; border-radius: 16px; box-shadow: 0 10px 25px rgba(0,0,0,.08); }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 1rem; }}
    .metric {{ padding: 1rem; background: #f9fafb; border-radius: 12px; }}
    .pill {{ display: inline-block; padding: 0.25rem 0.6rem; border-radius: 999px; background: #e0e7ff; font-weight: 700; }}
    @media (max-width: 640px) {{ .card {{ margin: 0.5rem; padding: 1rem; }} }}
  </style>
</head>
<body>
  <div class=\"card\">
    <h1>Collectables Earner Dashboard</h1>
    <p>Free automation for fitness rewards, milestone tracking, and SMS alerts.</p>
    <div class=\"grid\">
      <div class=\"metric\"><strong>Current Balance</strong><br>${data.get('current_balance', 0.0):.2f}</div>
      <div class=\"metric\"><strong>7-Day Weight Average</strong><br>{average:.2f} lbs</div>
      <div class=\"metric\"><strong>Next Weight Gate</strong><br>{next_gate:.0f} lbs</div>
      <div class=\"metric\"><strong>Meal Fund Status</strong><br>{'Unlocked' if data.get('budget_b_unlocked', False) else 'Locked'}</div>
    </div>
    <h2>Collectibles</h2>
    <ul>{items_html}</ul>
    <p><span class=\"pill\">Remaining Biking Meal Fund</span> {meal_status}</p>
  </div>
</body>
</html>
"""


def write_dashboard() -> None:
    TEMPLATE_FILE.write_text(build_dashboard_html(), encoding="utf-8")


def process_payload(payload: Dict[str, Any], send_sms: bool = False) -> Dict[str, Any]:
    if payload.get("kind") == "weight":
        return handle_weight_data(payload, send_sms=send_sms)
    if payload.get("kind") == "activity":
        return handle_activity_data(payload, send_sms=send_sms)
    if payload.get("kind") == "render":
        write_dashboard()
        return {"status": "rendered"}
    return {"status": "ignored"}


class TrackerHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # pragma: no cover
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok"}).encode("utf-8"))
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(build_dashboard_html().encode("utf-8"))

    def do_POST(self) -> None:  # pragma: no cover
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8")
        try:
            payload = json.loads(body) if body else {}
        except json.JSONDecodeError:
            payload = {}
        result = process_payload(payload, send_sms=True)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(result).encode("utf-8"))


def serve_http(port: int = 8000) -> None:
    server = HTTPServer(("0.0.0.0", port), TrackerHandler)
    print(f"Serving tracker on port {port}")
    server.serve_forever()


def main() -> None:
    if len(sys.argv) > 1:
        action = sys.argv[1]
        if action == "render":
            write_dashboard()
            return
        if action == "seed":
            save_data(DEFAULT_DATA.copy())
            return
        if action == "daily-prompt":
            send_sms_message(get_daily_prompt_message())
            return
        if action == "serve":
            port = int(os.getenv("PORT", "8000"))
            serve_http(port)
            return
        if action == "webhook":
            payload = {}
            if len(sys.argv) > 2:
                payload = json.loads(sys.argv[2])
            else:
                raw = sys.stdin.read().strip()
                if raw:
                    payload = json.loads(raw)
            process_payload(payload, send_sms=True)
            return
    ensure_data_file()
    write_dashboard()


if __name__ == "__main__":
    main()
