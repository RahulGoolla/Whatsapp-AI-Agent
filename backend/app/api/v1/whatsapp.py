import re
import uuid
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.config import settings
from app.core.logging import logger
from app.db.session import get_db
from app.models.conversation import Conversation, Message
from app.models.customer import CustomerProfile, UrgentLead
from app.models.workspace import Workspace
from app.services.rag import execute_rag_sync
from app.services.sales_rules import (
    SALES_TEAM_EMAIL,
    SALES_TEAM_NAME,
)
from app.services.state_manager import (
    detect_customer_signals,
    get_or_create_customer,
    register_urgent_lead,
    update_customer_profile,
)

router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])


class InteractiveButton(BaseModel):
    id: str
    title: str
    query: str


class WhatsAppMessageRequest(BaseModel):
    message: str = Field(..., description="Incoming customer message from WhatsApp")
    sender_phone: str | None = Field(default=None, description="Customer WhatsApp phone number or Session ID")
    sender_name: str | None = Field(default=None, description="Customer display name")
    workspace_id: uuid.UUID | None = Field(default=None, description="Workspace ID")
    conversation_id: uuid.UUID | None = Field(default=None, description="Specific Conversation ID")


class WhatsAppMessageResponse(BaseModel):
    reply: str
    is_escalated: bool = False
    escalation_reason: str | None = None
    is_ignored: bool = False
    citations: list[dict[str, Any]] = []
    sales_rep: dict[str, str] = {
        "name": SALES_TEAM_NAME,
        "email": SALES_TEAM_EMAIL,
    }
    conversation_id: str
    customer_name: str | None = None
    customer_phone: str = "Client"
    active_track: str = "unassigned"
    interactive_buttons: list[InteractiveButton] = []


class UrgentLeadResponse(BaseModel):
    id: str
    customer_phone: str
    customer_name: str | None
    business_name: str | None
    active_track: str
    requirement_summary: str
    status: str
    created_at: str


async def _get_or_create_default_workspace(db: AsyncSession) -> Workspace:
    """Finds or creates default AI Vastra WhatsApp FAQ workspace."""
    query = select(Workspace).order_by(Workspace.created_at.asc()).limit(1)
    res = await db.execute(query)
    workspace = res.scalar_one_or_none()
    if not workspace:
        workspace = Workspace(name="Whatsapp_FAQ")
        db.add(workspace)
        await db.commit()
        await db.refresh(workspace)
    return workspace


@router.post("/message", response_model=WhatsAppMessageResponse)
async def handle_whatsapp_message(
    payload: WhatsAppMessageRequest,
    db: AsyncSession = Depends(get_db),
) -> WhatsAppMessageResponse:
    """
    Stateful WhatsApp Sales Chat Endpoint with Isolated Cross-Session Memory & Lead Tracking.
    Guarantees Section 10 Greeting with 3 Main Options (AI Catalogue, Virtual Try-On, AI Kiosk) on any hi/hello.
    """
    logger.info(f"Received WhatsApp message from {payload.sender_phone}: '{payload.message}'")

    if not payload.message or not payload.message.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Message content cannot be empty.",
        )

    workspace = await _get_or_create_default_workspace(db)

    # 1. Generate or use unique customer phone key per chat session
    phone_key = payload.sender_phone.strip() if (payload.sender_phone and payload.sender_phone.strip()) else f"session_{uuid.uuid4().hex[:8]}"
    customer = await get_or_create_customer(db, phone_key, payload.sender_name)

    # 2. Extract Customer Signals (Strict Name, Track, Purchase/Buy Intent)
    signals = detect_customer_signals(payload.message, customer.active_track, customer.name)
    customer = await update_customer_profile(db, customer, signals)

    # 3. Retrieve or Create Conversation
    conversation = None
    if payload.conversation_id:
        conv_query = select(Conversation).where(Conversation.id == payload.conversation_id)
        conv_res = await db.execute(conv_query)
        conversation = conv_res.scalar_one_or_none()
    else:
        conv_query = (
            select(Conversation)
            .where(Conversation.title.like(f"%{phone_key}%"))
            .order_by(Conversation.created_at.desc())
            .limit(1)
        )
        conv_res = await db.execute(conv_query)
        conversation = conv_res.scalar_one_or_none()

    if not conversation:
        title_snippet = f"[{phone_key}] - {payload.message[:25]}"
        conversation = Conversation(
            title=title_snippet,
            workspace_id=workspace.id,
        )
        db.add(conversation)
        await db.commit()
        await db.refresh(conversation)

    # 4. Load Complete Conversation History (Up to 50 recent messages)
    hist_query = (
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.created_at.asc())
        .limit(50)
    )
    hist_res = await db.execute(hist_query)
    history_records = hist_res.scalars().all()

    is_initial_turn = len(history_records) == 0
    clean_msg = payload.message.lower().strip()
    is_greeting = is_initial_turn and bool(re.search(r"^(hi|hello|hey|start|namaste|good\s+(morning|afternoon|evening))\b", clean_msg))

    messages_history = [
        {"role": msg.role, "content": msg.content} for msg in history_records
    ]
    messages_history.append({"role": "user", "content": payload.message})

    # Save incoming user message
    user_msg = Message(
        role="user",
        content=payload.message,
        conversation_id=conversation.id,
    )
    db.add(user_msg)
    await db.commit()

    # 5. Check if we should register an Urgent CRM Lead Ticket
    if signals.get("intent_state") in ["ready_to_buy", "human_handoff", "demo_requested", "managed_service_requested"]:
        lead_status = "demo_scheduled" if signals.get("intent_state") == "demo_requested" else "urgent"
        await register_urgent_lead(
            db=db,
            customer=customer,
            requirement_summary=f"Customer expressed intent: '{signals.get('intent_state')}'. Message: '{payload.message}' (Track: {customer.active_track})",
            status=lead_status,
        )

    # 6. Execute AI Vastra RAG or Official Section 10 Greeting
    is_hindi_greeting = is_initial_turn and bool(re.search(r"^(namaste|pranam|namaskar|shubh\s+sandhya|shubh\s+prabhat|नमस्ते|प्रणाम|नमस्कार)\b", clean_msg))
    if is_hindi_greeting:
        rag_result = {
            "response": "नमस्ते! 👋 AI Vastra में आपका स्वागत है। हम फैशन बिज़नेस के लिए AI Catalogue Photo Creation और AI Virtual Try-On सेवाएं प्रदान करते हैं। आप किसमें रुचि रखते हैं — Catalogue Creation, Virtual Try-On, या दोनों?",
            "citations": [
                {
                    "index": 1,
                    "filename": "AI_Vastra_WhatsApp_AI_FAQ.pdf",
                    "page": 5,
                    "text_snippet": "Section 10. Recommended WhatsApp Replies - Q: Hi / Hello / Namaste",
                }
            ],
            "is_escalated": False,
            "escalation_reason": None,
            "is_ignored": False,
        }
    elif is_greeting:
        rag_result = {
            "response": "Hello! 👋 Welcome to AI Vastra. We provide AI Catalogue Photo Creation and AI Virtual Try-On for fashion businesses. What are you interested in — Catalogue Creation, Virtual Try-On, or Both?",
            "citations": [
                {
                    "index": 1,
                    "filename": "AI_Vastra_WhatsApp_AI_FAQ.pdf",
                    "page": 5,
                    "text_snippet": "Section 10. Recommended WhatsApp Replies - Q: Hi / Hello - A: Hello! Welcome to AI Vastra...",
                }
            ],
            "is_escalated": False,
            "escalation_reason": None,
            "is_ignored": False,
        }
    else:
        rag_result = await execute_rag_sync(
            workspace_id=workspace.id,
            query_text=payload.message,
            messages=messages_history,
            db=db,
            customer=customer,
        )

    # If message was not ignored, record response in conversation
    if not rag_result.get("is_ignored"):
        assistant_msg = Message(
            role="assistant",
            content=rag_result["response"],
            conversation_id=conversation.id,
        )
        db.add(assistant_msg)
        await db.commit()

    # 7. Formulate Contextual Interactive Buttons
    interactive_buttons = []
    
    # Detect product categories across the user's message
    is_kiosk_query = bool(re.search(r"\b(kiosk|standee|touchscreen)\b", clean_msg))
    is_catalogue_query = bool(re.search(r"\b(catalogue|catalog|flat[\s-]?lay)\b", clean_msg))
    is_vto_query = bool(re.search(r"\b(virtual[\s-]?try[\s-]?on|try[\s-]?on|vto)\b", clean_msg))
    is_both_query = (is_catalogue_query and is_vto_query) or bool(re.search(r"\b(both|all\s+three|all\s+3)\b", clean_msg))
    
    if is_greeting:
        # Fixed 3 core main options on welcome greeting
        interactive_buttons = [
            InteractiveButton(
                id="btn_catalogue",
                title="📸 AI Catalogue",
                query="I want catalogue",
            ),
            InteractiveButton(
                id="btn_vto",
                title="👗 Virtual Try-On",
                query="I want virtual try-on",
            ),
            InteractiveButton(
                id="btn_kiosk",
                title="🖥️ AI Kiosk",
                query="Tell me about AI Kiosk",
            ),
        ]
    elif is_kiosk_query:
        # AI Kiosk sub-options
        interactive_buttons = [
            InteractiveButton(
                id="btn_kiosk_cost",
                title="💰 Hardware & Setup Cost",
                query="What is the hardware and setup cost for AI Kiosk?",
            ),
            InteractiveButton(
                id="btn_kiosk_delivery",
                title="🚚 Delivery & Installation",
                query="How long does AI Kiosk delivery and setup take?",
            ),
        ]
    elif is_both_query:
        # Both services sub-options
        interactive_buttons = [
            InteractiveButton(
                id="btn_cat_details",
                title="📸 AI Catalogue Details",
                query="What are the catalogue pricing and package plans?",
            ),
            InteractiveButton(
                id="btn_vto_details",
                title="👗 Virtual Try-On Details",
                query="What are the Virtual Try-On pricing plans?",
            ),
            InteractiveButton(
                id="btn_live_demo",
                title="📅 Book a Live Demo",
                query="I want a live demo",
            ),
        ]
    elif is_catalogue_query:
        # AI Catalogue sub-options
        interactive_buttons = [
            InteractiveButton(
                id="btn_cat_buy",
                title="💳 Pricing & Plans",
                query="What are the catalogue pricing and package plans?",
            ),
            InteractiveButton(
                id="btn_cat_sample",
                title="🎁 Free Sample Info",
                query="How can I try a free sample catalogue photo?",
            ),
        ]
    elif is_vto_query:
        # Virtual Try-On sub-options
        interactive_buttons = [
            InteractiveButton(
                id="btn_vto_buy",
                title="💳 Pricing & Plans",
                query="What are the Virtual Try-On pricing plans?",
            ),
            InteractiveButton(
                id="btn_vto_demo",
                title="🎬 Demo Videos",
                query="Send me live demo videos for Virtual Try-On",
            ),
            InteractiveButton(
                id="btn_vto_shopify",
                title="🛍️ Shopify & Website",
                query="Does Virtual Try-On support Shopify integration?",
            ),
        ]
    else:
        interactive_buttons = []

    return WhatsAppMessageResponse(
        reply=rag_result["response"],
        is_escalated=rag_result["is_escalated"],
        escalation_reason=rag_result["escalation_reason"],
        is_ignored=rag_result.get("is_ignored", False),
        citations=rag_result["citations"],
        conversation_id=str(conversation.id),
        customer_name=customer.name,
        customer_phone=customer.phone_number,
        active_track=customer.active_track,
        interactive_buttons=interactive_buttons,
    )


@router.get("/leads", response_model=list[UrgentLeadResponse])
async def list_urgent_leads(
    db: AsyncSession = Depends(get_db),
) -> list[UrgentLeadResponse]:
    """
    CRM Lead Box Endpoint for sales team & developer CRM sync.
    Returns all urgent leads captured from WhatsApp chats with customer name, phone, track & requirement summary.
    """
    query = select(UrgentLead).order_by(UrgentLead.created_at.desc()).limit(50)
    res = await db.execute(query)
    leads = res.scalars().all()

    return [
        UrgentLeadResponse(
            id=str(lead.id),
            customer_phone=lead.customer_phone,
            customer_name=lead.customer_name,
            business_name=lead.business_name,
            active_track=lead.active_track,
            requirement_summary=lead.requirement_summary,
            status=lead.status,
            created_at=lead.created_at.strftime("%Y-%m-%d %H:%M:%S UTC"),
        )
        for lead in leads
    ]


@router.get("/customers")
async def list_customer_profiles(
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """Lists all persistent customer profiles and active memory state."""
    query = select(CustomerProfile).order_by(CustomerProfile.last_seen_at.desc()).limit(50)
    res = await db.execute(query)
    customers = res.scalars().all()

    return [
        {
            "id": str(c.id),
            "phone_number": c.phone_number,
            "name": c.name,
            "business_name": c.business_name,
            "active_track": c.active_track,
            "intent_state": c.intent_state,
            "session_count": c.session_count,
            "last_seen_at": c.last_seen_at.strftime("%Y-%m-%d %H:%M:%S UTC"),
        }
        for c in customers
    ]


@router.get("/webhook")
async def verify_meta_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
) -> Response:
    """Meta WhatsApp Cloud API Webhook verification endpoint."""
    verify_token = settings.WHATSAPP_VERIFY_TOKEN or "aivastra_whatsapp_verify_token_2026"
    if hub_mode == "subscribe" and hub_verify_token == verify_token:
        logger.info("Meta WhatsApp Cloud Webhook verified successfully!")
        return Response(content=hub_challenge, media_type="text/plain")
    return Response(content="Forbidden", status_code=403)


@router.post("/webhook")
async def handle_meta_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Handles live incoming Meta WhatsApp Cloud API Webhook events with stateful customer tracking.
    """
    try:
        body = await request.json()
        logger.info(f"Incoming Meta Webhook Payload: {body}")

        entries = body.get("entry", [])
        if not entries:
            return {"status": "ignored", "reason": "no_entries"}

        for entry in entries:
            for change in entry.get("changes", []):
                value = change.get("value", {})
                messages = value.get("messages", [])
                metadata = value.get("metadata", {})
                contacts = value.get("contacts", [])
                phone_number_id = metadata.get("phone_number_id", settings.WHATSAPP_PHONE_NUMBER_ID)

                contact_name = None
                if contacts and len(contacts) > 0:
                    contact_name = contacts[0].get("profile", {}).get("name")

                for msg in messages:
                    sender_phone = msg.get("from")
                    msg_type = msg.get("type")

                    incoming_text = ""
                    if msg_type == "text":
                        incoming_text = msg.get("text", {}).get("body", "")
                    elif msg_type == "interactive":
                        interactive = msg.get("interactive", {})
                        if interactive.get("type") == "button_reply":
                            incoming_text = interactive.get("button_reply", {}).get("title", "")
                        elif interactive.get("type") == "list_reply":
                            incoming_text = interactive.get("list_reply", {}).get("title", "")
                    elif msg_type == "button":
                        incoming_text = msg.get("button", {}).get("text", "")

                    if not incoming_text:
                        continue

                    logger.info(f"Processing Meta message from {sender_phone}: '{incoming_text}'")

                    req_obj = WhatsAppMessageRequest(
                        message=incoming_text,
                        sender_phone=sender_phone,
                        sender_name=contact_name,
                    )
                    rag_res = await handle_whatsapp_message(req_obj, db)

                    if rag_res.is_ignored:
                        logger.info(f"Message from {sender_phone} is irrelevant. Silence policy applied.")
                        continue

                    if settings.WHATSAPP_ACCESS_TOKEN and phone_number_id:
                        await _send_meta_whatsapp_reply(
                            phone_number_id=phone_number_id,
                            to_phone=sender_phone,
                            reply_text=rag_res.reply,
                            interactive_buttons=rag_res.interactive_buttons,
                        )

        return {"status": "success"}
    except Exception as e:
        logger.error(f"Error handling Meta Webhook: {e}")
        return {"status": "error", "detail": str(e)}


async def _send_meta_whatsapp_reply(
    phone_number_id: str,
    to_phone: str,
    reply_text: str,
    interactive_buttons: list[InteractiveButton],
) -> None:
    """Dispatches a response back to customer's WhatsApp via Meta Graph API."""
    url = f"https://graph.facebook.com/v19.0/{phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }

    if interactive_buttons:
        payload = {
            "messaging_product": "whatsapp",
            "to": to_phone,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": reply_text},
                "action": {
                    "buttons": [
                        {
                            "type": "reply",
                            "reply": {"id": btn.id, "title": btn.title[:20]},
                        }
                        for btn in interactive_buttons[:3]
                    ]
                },
            },
        }
    else:
        payload = {
            "messaging_product": "whatsapp",
            "to": to_phone,
            "type": "text",
            "text": {"body": reply_text},
        }

    async with httpx.AsyncClient() as client:
        resp = await client.post(url, headers=headers, json=payload, timeout=10.0)
        logger.info(f"Meta WhatsApp Send Status: {resp.status_code} - {resp.text}")
