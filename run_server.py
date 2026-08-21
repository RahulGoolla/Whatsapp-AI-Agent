import os
import sys

# Configure UTF-8 for console output on Windows
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import uvicorn

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

if __name__ == "__main__":
    print("=" * 65)
    print("STARTING AI VASTRA WHATSAPP SALES AGENT PLATFORM")
    print("=" * 65)
    print("Web UI & WhatsApp Simulator: http://localhost:8000")
    print("API Documentation:          http://localhost:8000/docs")
    print("WhatsApp Message API:       POST http://localhost:8000/api/v1/whatsapp/message")
    print("WhatsApp Cloud Webhook:     http://localhost:8000/api/v1/whatsapp/webhook")
    print("=" * 65)
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        app_dir=os.path.join(os.path.dirname(__file__), "backend"),
    )
