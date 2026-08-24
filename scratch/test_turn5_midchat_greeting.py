import urllib.request
import json
import sys
import uuid

sys.stdout.reconfigure(encoding='utf-8')

session_id = "test_user_flow_v2_" + uuid.uuid4().hex[:8]
conv_id = None

convo = [
    "hello",
    "I want virtual try-on",
    "I want to go with the enterprise plan",
    "yes",
    "hello"
]

for idx, msg in enumerate(convo, 1):
    payload = {"message": msg, "sender_phone": session_id}
    if conv_id:
        payload["conversation_id"] = conv_id

    req = urllib.request.Request(
        "http://127.0.0.1:8000/api/v1/whatsapp/message",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        conv_id = data.get("conversation_id")
        buttons = [b["title"] for b in data.get("interactive_buttons", [])]
        print(f"=== Turn {idx}: '{msg}' ===")
        print("🤖 Reply:\n", data.get("reply"))
        print(f"   Buttons: {buttons}")
        print("-" * 60)
