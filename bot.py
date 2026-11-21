import os
import sys
import time
import requests

TOKEN = os.environ.get("BALE_BOT_TOKEN")
if not TOKEN:
    print("ERROR: BALE_BOT_TOKEN secret is missing.")
    sys.exit(1)

BASE = f"https://tapi.bale.ai/bot{TOKEN}"
deadline = time.monotonic() + 180
offset = None
seen = set()

print("Diagnostic started. Send a normal text message in the Bale group now.")
print("The bot will listen for up to 3 minutes. Message text is never printed.")

while time.monotonic() < deadline:
    params = {"timeout": 10}
    if offset is not None:
        params["offset"] = offset

    try:
        response = requests.get(f"{BASE}/getUpdates", params=params, timeout=15)
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        print(f"API request failed: {type(exc).__name__}: {exc}")
        time.sleep(3)
        continue

    if not payload.get("ok", False):
        print("Bale API returned ok=false:", payload)
        time.sleep(3)
        continue

    for update in payload.get("result", []):
        update_id = update.get("update_id")
        if update_id is not None:
            offset = update_id + 1
        if update_id in seen:
            continue
        seen.add(update_id)

        message = update.get("message") or update.get("edited_message")
        if not message:
            print("Received a non-message update.")
            continue

        chat = message.get("chat", {})
        sender = message.get("from", {})
        text = message.get("text", "")
        print(
            "MESSAGE RECEIVED | "
            f"chat_id={chat.get('id')} | "
            f"chat_type={chat.get('type')} | "
            f"sender_id={sender.get('id')} | "
            f"text_present={bool(text)}"
        )

print("Diagnostic finished.")
