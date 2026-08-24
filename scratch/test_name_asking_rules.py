import urllib.request
import json
import sys
import uuid

sys.stdout.reconfigure(encoding='utf-8')

print("=" * 60)
print("SCENARIO A: Name NOT given yet -> Ask name -> Confirm")
print("=" * 60)

session_a = "test_scen_a_" + uuid.uuid4().hex[:8]
conv_id_a = None

# Turn 1
req1 = urllib.request.Request(
    "http://127.0.0.1:8000/api/v1/whatsapp/message",
    data=json.dumps({"message": "I want to talk to aivastra team", "sender_phone": session_a}).encode("utf-8"),
    headers={"Content-Type": "application/json"}
)
with urllib.request.urlopen(req1) as resp:
    data1 = json.loads(resp.read().decode("utf-8"))
    conv_id_a = data1.get("conversation_id")
    print("👉 Client: 'I want to talk to aivastra team'")
    print("🤖 Agent:\n", data1.get("reply"))
    print("-" * 60)

# Turn 2
req2 = urllib.request.Request(
    "http://127.0.0.1:8000/api/v1/whatsapp/message",
    data=json.dumps({"message": "My name is Rahul", "sender_phone": session_a, "conversation_id": conv_id_a}).encode("utf-8"),
    headers={"Content-Type": "application/json"}
)
with urllib.request.urlopen(req2) as resp:
    data2 = json.loads(resp.read().decode("utf-8"))
    print("👉 Client: 'My name is Rahul'")
    print("🤖 Agent:\n", data2.get("reply"))
    print("-" * 60)

print("\n" + "=" * 60)
print("SCENARIO B: Name ALREADY given on Turn 1 -> Direct Confirm")
print("=" * 60)

session_b = "test_scen_b_" + uuid.uuid4().hex[:8]
conv_id_b = None

# Turn 1
req1_b = urllib.request.Request(
    "http://127.0.0.1:8000/api/v1/whatsapp/message",
    data=json.dumps({"message": "hi, my name is rahul", "sender_phone": session_b}).encode("utf-8"),
    headers={"Content-Type": "application/json"}
)
with urllib.request.urlopen(req1_b) as resp:
    data1_b = json.loads(resp.read().decode("utf-8"))
    conv_id_b = data1_b.get("conversation_id")
    print("👉 Client: 'hi, my name is rahul'")
    print("🤖 Agent:\n", data1_b.get("reply"))
    print("-" * 60)

# Turn 2
req2_b = urllib.request.Request(
    "http://127.0.0.1:8000/api/v1/whatsapp/message",
    data=json.dumps({"message": "I want to contact your team", "sender_phone": session_b, "conversation_id": conv_id_b}).encode("utf-8"),
    headers={"Content-Type": "application/json"}
)
with urllib.request.urlopen(req2_b) as resp:
    data2_b = json.loads(resp.read().decode("utf-8"))
    print("👉 Client: 'I want to contact your team'")
    print("🤖 Agent:\n", data2_b.get("reply"))
    print("-" * 60)
