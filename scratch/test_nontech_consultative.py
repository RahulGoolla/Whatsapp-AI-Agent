import urllib.request
import json
import sys
import uuid

sys.stdout.reconfigure(encoding='utf-8')

session_id = "test_nontech_" + uuid.uuid4().hex[:8]

query = "and the main thing is i don't much tech and all i will pay and i want all the services to be managed by you, can you do that"

req = urllib.request.Request(
    "http://127.0.0.1:8000/api/v1/whatsapp/message",
    data=json.dumps({"message": query, "sender_phone": session_id}).encode("utf-8"),
    headers={"Content-Type": "application/json"}
)
with urllib.request.urlopen(req) as resp:
    data = json.loads(resp.read().decode("utf-8"))
    print("👉 Query:\n", query)
    print("\n🤖 Reply:\n", data.get("reply"))
    print("\n🔘 Buttons:", [b["title"] for b in data.get("interactive_buttons", [])])
