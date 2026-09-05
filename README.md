# 👗 Ai Vastra — WhatsApp Real-Time AI Sales Agent & RAG Backend

Production-grade, verified **WhatsApp AI Sales Agent** and **RAG (Retrieval-Augmented Generation)** backend service built for **Ai Vastra / Nice Digitals**.

The agent is strictly grounded in the official knowledge base document (`AI_Vastra_WhatsApp_AI_FAQ.pdf`), delivers accurate answers, handles Pay-As-You-Go pricing and full package tiers (Starter, Growth, Pro, Enterprise), stays silent on irrelevant topics, schedules live demos, and provides seamless escalation to the **Ai Vastra Sales Team**.

---

## ⚡ Quick Start (Run Locally)

### 1. Prerequisites
- Python 3.10+
- OpenAI API Key

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure Environment
Copy `.env.example` to `.env`:
```env
OPENAI_API_KEY=sk-proj-your-openai-api-key-here
ENV=development
```

### 4. Launch the Server
```bash
python run_server.py
```
The server will start at **`http://localhost:8000`** and automatically auto-seed the knowledge base vector index from `AI_Vastra_WhatsApp_AI_FAQ.pdf`.

---

## 📱 WhatsApp Integration Methods

This backend supports **two flexible integration methods** for WhatsApp:

### Method A: Direct REST API (For Node.js, Python, Baileys, Twilio, WATI, Gupshup)

Send incoming customer messages directly via JSON POST request:

- **Endpoint**: `POST http://localhost:8000/api/v1/whatsapp/message`
- **Headers**: `Content-Type: application/json`
- **Request Body**:
```json
{
  "message": "Can I know the cost of Virtual Try-On?",
  "sender_phone": "+919876543210",
  "conversation_id": "optional-uuid-to-maintain-session"
}
```

- **Response Body**:
```json
{
  "reply": "Thank you for showing interest in AI Vastra Virtual Try-On. Please find our Virtual Try-On pricing details ( each try on cost Rs. 5* )\nFor demo videos, please visit our YouTube channel: https://www.youtube.com/@ai.vastra_tryon/videos",
  "is_escalated": false,
  "is_ignored": false,
  "citations": [
    {
      "index": 1,
      "filename": "AI_Vastra_WhatsApp_AI_FAQ.pdf",
      "page": 6,
      "text_snippet": "..."
    }
  ],
  "sales_rep": {
    "name": "Ai Vastra Sales Team",
    "email": "support@aivastra.com"
  },
  "interactive_buttons": [
    {
      "id": "btn_catalogue",
      "title": "📸 AI Catalogue",
      "query": "I want catalogue"
    },
    {
      "id": "btn_vto",
      "title": "👗 Virtual Try-On",
      "query": "I want virtual try-on"
    },
    {
      "id": "btn_kiosk",
      "title": "🖥️ AI Kiosk",
      "query": "Tell me about AI Kiosk"
    }
  ],
  "conversation_id": "3e4832be-619f-431f-bc87-73d706509f6b"
}
```

---

### Method B: Meta WhatsApp Cloud API (Direct Webhook)

To connect directly to **Meta WhatsApp Cloud API**:

1. In your Meta WhatsApp Cloud API developer portal, configure the Webhook URL:
   - **Callback URL**: `https://your-public-domain.com/api/v1/whatsapp/webhook`
   - **Verify Token**: `aivastra_whatsapp_verify_token_2026` (or set `WHATSAPP_VERIFY_TOKEN` in `.env`)
2. In `.env`, provide:
```env
WHATSAPP_PHONE_NUMBER_ID=your_meta_phone_number_id
WHATSAPP_ACCESS_TOKEN=your_meta_system_user_access_token
WHATSAPP_VERIFY_TOKEN=aivastra_whatsapp_verify_token_2026
```
3. The backend will automatically receive incoming webhooks, execute RAG intent matching, and dispatch replies (including interactive quick reply buttons) straight to the customer's WhatsApp chat.

---

## 🧠 Core Features & Sales Engine Rules

1. **Exact Verbatim Knowledge Base Delivery**:
   - Primary Knowledge Base: `AI_Vastra_WhatsApp_AI_FAQ.pdf` (All 7 Pages).
   - Vector Embedding Model: `text-embedding-3-small` (OpenAI).
   - LLM Reasoning Model: `gpt-4o` (`temperature=0.2`).
   - Vector DB: Embedded persistent ChromaDB with cosine similarity.

2. **Full Pricing & Package Plans**:
   - **Pay-As-You-Go**: ₹10 per catalogue photo, ₹5 per successful Virtual Try-On.
   - **Virtual Try-On Packages**:
     - *Starter*: ₹999 (180 Try-Ons | ₹5.55/try-on)
     - *Growth*: ₹2,500 (455 Try-Ons | ₹5.49/try-on)
     - *Pro*: ₹10,000 (2,105 Try-Ons | ₹4.75/try-on)
     - *Enterprise*: ₹25,000 (6,000 Try-Ons | ₹4.17/try-on)
   - **Catalogue Packages**:
     - *Starter*: ₹1,000 (80 Images | ₹12.50/photo)
     - *Growth*: ₹5,000 (450 Images | ₹11.11/photo)
     - *Pro*: ₹10,000 (1,000 Images | ₹10.00/photo)

3. **Live Demo Scheduling Flow**:
   - When a client asks for a live demo, the agent asks for their name, business name, and website.
   - Once provided, the agent confirms: *"Thank you! Your demo request has been received. Our team will schedule it and update you with the confirmed time after checking with our team."*
   - Automatically flags a demo lead in the CRM Lead Box.

4. **Strict Silence on Major Irrelevant Topics**:
   - If a customer message is completely unrelated to Ai Vastra / fashion services, the agent stays **completely silent** (`is_ignored: true`) and does not send spam.

5. **Sales Team Handoff & Escalation**:
   - When explicit live assistance or custom contracts are requested: *"Our team will contact you shortly to assist you directly."*

6. **WhatsApp Simulator & Web Dashboard**:
   - Access `http://localhost:8000` for an interactive sales simulator equipped with:
     - **Dark & Light Mode Switcher** (Ai Vastra Studio Obsidian Dark / Clean Light)
     - **WhatsApp Interactive Quick Reply Buttons**
     - **Full text copyability & 1-click Copy buttons**
     - **Real-time Urgent Leads & CRM Inbox**
