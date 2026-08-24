import urllib.request
import json
import sys
import uuid

sys.stdout.reconfigure(encoding='utf-8')

session_id = "test_mini_" + uuid.uuid4().hex[:8]

req = urllib.request.Request(
    "http://127.0.0.1:8000/api/v1/whatsapp/message",
    data=json.dumps({"message": "What are the catalogue pricing plans?", "sender_phone": session_id}).encode("utf-8"),
    headers={"Content-Type": "application/json"}
)
with urllib.request.urlopen(req) as resp:
    data = json.loads(resp.read().decode("utf-8"))
    print("🤖 gpt-4o-mini Reply:\n", data.get("reply"))
    print("\n🔘 Buttons:", [b["title"] for b in data.get("interactive_buttons", [])])
