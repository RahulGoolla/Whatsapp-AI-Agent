import urllib.request
import json
import sys
import uuid

sys.stdout.reconfigure(encoding='utf-8')

session_id = "test_hello_" + uuid.uuid4().hex[:8]

greetings = ["hello", "hi", "hey", "namaste"]

for g in greetings:
    req = urllib.request.Request(
        "http://127.0.0.1:8000/api/v1/whatsapp/message",
        data=json.dumps({"message": g, "sender_phone": session_id}).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        buttons = [b["title"] for b in data.get("interactive_buttons", [])]
        print(f"👉 Query: '{g}'")
        print(f"   Buttons Count: {len(buttons)} -> {buttons}")
        print("-" * 60)
