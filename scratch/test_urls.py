import urllib.request
import json
import sys
import uuid

sys.stdout.reconfigure(encoding='utf-8')

for q in ["give me payment link", "login ai vastra"]:
    session_id = "test_url_" + uuid.uuid4().hex[:8]
    req = urllib.request.Request(
        "http://127.0.0.1:8000/api/v1/whatsapp/message",
        data=json.dumps({"message": q, "sender_phone": session_id}).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        print(f"=== Query: '{q}' ===")
        print("🤖 Reply:\n", data.get("reply"))
        print("-" * 60)
