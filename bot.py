import os
import sys
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import requests
import jdatetime

TOKEN = os.environ.get("BALE_BOT_TOKEN", "").strip()
CHAT_ID = os.environ.get("BALE_CHAT_ID", "").strip()
TIMEZONE = os.environ.get("TIMEZONE", "Asia/Tehran")
WINDOW_MINUTES = int(os.environ.get("ATTENDANCE_WINDOW_MINUTES", "15"))

if not TOKEN:
    print("ERROR: BALE_BOT_TOKEN secret is missing.", flush=True)
    sys.exit(1)
if not CHAT_ID:
    print("ERROR: BALE_CHAT_ID is missing.", flush=True)
    sys.exit(1)

BASE = f"https://tapi.bale.ai/bot{TOKEN}"
session = requests.Session()


def api(method, **params):
    response = session.post(f"{BASE}/{method}", json=params, timeout=35)
    response.raise_for_status()
    data = response.json()
    if not data.get("ok", False):
        raise RuntimeError(f"Bale API returned ok=false for {method}")
    return data.get("result")


def send(text):
    return api("sendMessage", chat_id=CHAT_ID, text=text)


def main():
    tz = ZoneInfo(TIMEZONE)

    # Drain updates queued before this attendance session so old messages
    # cannot be counted as attendance for the new session.
    offset = None
    while True:
        params = {"timeout": 0}
        if offset is not None:
            params["offset"] = offset
        data = session.get(f"{BASE}/getUpdates", params=params, timeout=10)
        data.raise_for_status()
        payload = data.json()
        if not payload.get("ok", False):
            raise RuntimeError("Bale getUpdates returned ok=false")
        updates = payload.get("result", [])
        if not updates:
            break
        for item in updates:
            if item.get("update_id") is not None:
                offset = item["update_id"] + 1
        if len(updates) < 100:
            break

    started_at = datetime.now(timezone.utc).timestamp()
    local_start = datetime.now(tz)
    jalali_date = jdatetime.date.fromgregorian(date=local_start.date())
    date_label = jalali_date.strftime("%Y/%m/%d").translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))
    deadline = time.monotonic() + WINDOW_MINUTES * 60

    send(
        f"حاضرین کلاس - {date_label}\n"
        f"ثبت حضور به مدت {WINDOW_MINUTES} دقیقه فعال است.\n"
        "لطفاً نام خانوادگی خود را در یک پیام متنی ارسال کنید.\n"
        "برای هر شخص فقط اولین پیام معتبر ثبت می‌شود."
    )
    print(f"Attendance session started for chat_id={CHAT_ID}; window={WINDOW_MINUTES} minutes.", flush=True)

    attendees = {}
    while time.monotonic() < deadline:
        params = {"timeout": 20}
        if offset is not None:
            params["offset"] = offset
        try:
            response = session.get(f"{BASE}/getUpdates", params=params, timeout=25)
            response.raise_for_status()
            payload = response.json()
            if not payload.get("ok", False):
                print("WARNING: getUpdates returned ok=false; retrying.", flush=True)
                time.sleep(2)
                continue
        except requests.RequestException as exc:
            print(f"WARNING: polling error ({type(exc).__name__}); retrying.", flush=True)
            time.sleep(2)
            continue

        for item in payload.get("result", []):
            update_id = item.get("update_id")
            if update_id is not None:
                offset = update_id + 1

            message = item.get("message") or item.get("edited_message")
            if not message:
                continue

            chat = message.get("chat", {})
            if str(chat.get("id")) != CHAT_ID:
                continue

            sender = message.get("from", {})
            sender_id = sender.get("id")
            if sender_id is None or sender.get("is_bot"):
                continue

            message_time = message.get("date")
            if message_time is not None and message_time < started_at:
                continue

            surname = (message.get("text") or "").strip()
            if not surname or surname.startswith("/"):
                continue

            if sender_id not in attendees:
                attendees[sender_id] = surname
                print(f"ATTENDANCE RECORDED | sender_id={sender_id}", flush=True)

    if attendees:
        names = "\n".join(f"{index}. {name}" for index, name in enumerate(attendees.values(), 1))
    else:
        names = "هنوز حضوری ثبت نشده است."

    report = (
        f"گزارش نهایی حضور - {date_label}\n"
        f"تعداد حاضرین: {len(attendees)} نفر\n\n"
        f"{names}"
    )
    send(report)
    print(f"Attendance session finished. Total attendees: {len(attendees)}.", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"FATAL ERROR: {type(exc).__name__}: {exc}", flush=True)
        sys.exit(1)
