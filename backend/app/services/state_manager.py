"""
AI Vastra - Customer State, Memory & Track Manager.
Maintains persistent customer profiles across WhatsApp sessions, prevents repetitive loops,
tracks product tracks (Catalogue, Virtual Try-On, AI Kiosk, Both), detects customer details (Name, Company, Purchase Intent),
and auto-creates urgent CRM leads.
"""

import re
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.logging import logger
from app.models.customer import CustomerProfile, UrgentLead


async def get_or_create_customer(
    db: AsyncSession,
    phone_number: str,
    name: str | None = None,
) -> CustomerProfile:
    """Retrieves or creates a CustomerProfile for persistent cross-session memory."""
    cleaned_phone = phone_number.strip() if phone_number else f"anon_{uuid.uuid4().hex[:8]}"
    query = select(CustomerProfile).where(CustomerProfile.phone_number == cleaned_phone)
    res = await db.execute(query)
    customer = res.scalar_one_or_none()

    if not customer:
        customer = CustomerProfile(
            phone_number=cleaned_phone,
            name=name if (name and name not in ["WhatsApp Customer", "Client"]) else None,
            active_track="unassigned",
            intent_state="greeting",
            session_count=1,
            last_seen_at=datetime.now(UTC),
        )
        db.add(customer)
        await db.commit()
        await db.refresh(customer)
        logger.info(f"Created new CustomerProfile for {cleaned_phone} (Name: {customer.name})")
    else:
        customer.session_count += 1
        customer.last_seen_at = datetime.now(UTC)
        if name and name not in ["WhatsApp Customer", "Client"] and not customer.name:
            customer.name = name
        await db.commit()
        await db.refresh(customer)
        logger.info(f"Loaded existing CustomerProfile for {cleaned_phone} (Name: {customer.name}, Track: {customer.active_track})")

    return customer


def detect_customer_signals(text: str, current_track: str, current_name: str | None) -> dict[str, Any]:
    """
    Analyzes incoming customer message for Name, Track Preference, and Purchase/Buy intent.
    Strictly extracts names ONLY on explicit introductions (e.g. 'my name is X', 'I am X').
    """
    cleaned = text.strip()
    lower = cleaned.lower()
    signals: dict[str, Any] = {}

    # Greeting check: resets track so user gets full greeting & 3 options
    is_greeting = bool(re.search(r"^(hi|hello|hey|start|namaste|good\s+(morning|afternoon|evening)|menu)\b", lower))
    if is_greeting and len(cleaned.split()) <= 4:
        signals["detected_track"] = "unassigned"
        signals["intent_state"] = "greeting"

    # 1. STRICT Name Extraction (Only on explicit introductions)
    if not current_name:
        name_match = re.search(
            r"\b(?:my name is|i am called|i'm|i am|this is|myself)\s+([A-Z][a-zA-Z]{1,20}|[a-z]{2,20})\b",
            cleaned,
            re.IGNORECASE,
        )
        if name_match:
            candidate = name_match.group(1).capitalize()
            blacklist = {
                "interested", "here", "ready", "buying", "looking", "wanting",
                "fine", "good", "new", "vastra", "customer", "sure", "ok", "okay",
                "hello", "hi", "hey", "catalogue", "virtual", "kiosk", "trying", "user"
            }
            if candidate.lower() not in blacklist and len(candidate) >= 2:
                signals["detected_name"] = candidate
                logger.info(f"Explicit customer name detected: {candidate}")

    # 2. Business / Company / Website Extraction
    comp_match = re.search(
        r"\b(?:company|business|brand|store|shop)(?:\s+name)?(?:\s+is|\s*:)?\s+([A-Za-z0-9\s&]{2,35})\b",
        cleaned,
        re.IGNORECASE,
    )
    if comp_match:
        signals["detected_business"] = comp_match.group(1).strip()

    web_match = re.search(r"\b(?:website|site)(?:\s+is|\s*:)?\s+([a-zA-Z0-9.\-_/:]+\.[a-zA-Z]{2,10})\b", cleaned, re.IGNORECASE)
    if web_match:
        signals["detected_website"] = web_match.group(1).strip()

    # 3. Product Track Detection (Catalogue, Virtual Try-On, AI Kiosk, Both / All Three)
    if re.search(r"\b(both|all\s+services|all\s+three|all\s+3|all\s+of\s+them|all\s+products|everything|buy\s+both|want\s+both|three\s+comined|three\s+combined)\b", lower):
        signals["detected_track"] = "both"
    elif re.search(r"\b(catalogue|catalog)\b", lower) and re.search(r"\b(virtual|try[\s-]?on|kiosk)\b", lower):
        signals["detected_track"] = "both"
    elif re.search(r"\b(ai\s+kiosk|kiosk|standee|touchscreen|offline\s+store\s+standee)\b", lower) and not re.search(r"\b(catalogue|catalog|virtual|try[\s-]?on)\b", lower):
        signals["detected_track"] = "ai_kiosk"
    elif re.search(r"\b(virtual[\s-]?try[\s-]?on|try[\s-]?on|vto|shopify\s+try[\s-]?on)\b", lower) and not re.search(r"\b(catalogue|catalog|kiosk)\b", lower):
        signals["detected_track"] = "virtual_tryon"
    elif re.search(r"\b(catalogue|catalog|flat[\s-]?lay|garment\s+photo|product\s+images?|catalogue\s+creation|ai\s+catalogue)\b", lower) and not re.search(r"\b(virtual|try[\s-]?on|kiosk)\b", lower):
        signals["detected_track"] = "catalogue"

    # 4. Intent Detection (Ready to Buy / Live Demo / Managed Service / Human)
    if re.search(r"\b(want\s+to\s+buy|wanna\s+buy|i\s+want\s+buy|how\s+to\s+buy|how\s+can\s+i\s+buy|purchase|pay|order|how\s+to\s+get\s+started|start\s+using|buy\s+now|checkout)\b", lower):
        signals["intent_state"] = "ready_to_buy"
    elif re.search(r"\b(don't\s+know\s+tech|do\s+not\s+know\s+tech|manage\s+(it|everything|for\s+us)|operate\s+for\s+us|just\s+send\s+photos|send\s+you\s+photos|you\s+manage|full\s+service)\b", lower):
        signals["intent_state"] = "managed_service_requested"
    elif re.search(r"\b(live\s+demo|schedule\s+demo|book\s+demo|want\s+a\s+demo|need\s+demo|arrange\s+demo|want\s+demo)\b", lower):
        signals["intent_state"] = "demo_requested"
    elif re.search(r"\b(talk\s+to\s+human|speak\s+with\s+someone|call\s+me|contact\s+someone|contact\s+the\s+person|human\s+agent|talk\s+directly)\b", lower):
        signals["intent_state"] = "human_handoff"
    elif re.search(r"\b(price|pricing|cost|how\s+much|package|packages|plans|starter|growth|pro|rate)\b", lower):
        signals["intent_state"] = "evaluating_pricing"

    return signals


async def update_customer_profile(
    db: AsyncSession,
    customer: CustomerProfile,
    signals: dict[str, Any],
) -> CustomerProfile:
    """Applies detected signals to customer memory."""
    if signals.get("detected_name") and not customer.name:
        customer.name = signals["detected_name"]
        logger.info(f"Updated customer name to {customer.name}")

    if signals.get("detected_business") and not customer.business_name:
        customer.business_name = signals["detected_business"]

    if signals.get("detected_website") and not customer.website:
        customer.website = signals["detected_website"]

    if "detected_track" in signals:
        customer.active_track = signals["detected_track"]
        logger.info(f"Updated customer active track to {customer.active_track}")

    if signals.get("intent_state"):
        customer.intent_state = signals["intent_state"]

    await db.commit()
    await db.refresh(customer)
    return customer


async def register_urgent_lead(
    db: AsyncSession,
    customer: CustomerProfile,
    requirement_summary: str,
    status: str = "urgent",
) -> UrgentLead:
    """Registers an urgent lead entry in the CRM Lead Box table."""
    lead = UrgentLead(
        customer_id=customer.id,
        customer_phone=customer.phone_number,
        customer_name=customer.name,
        business_name=customer.business_name,
        website=customer.website,
        active_track=customer.active_track if customer.active_track != "unassigned" else "catalogue",
        requirement_summary=requirement_summary,
        status=status,
    )
    db.add(lead)
    await db.commit()
    await db.refresh(lead)
    logger.info(f"🚨 Registered Urgent Lead for {customer.phone_number} (Name: {customer.name}, Track: {lead.active_track})")
    return lead


def build_contextual_prompt(customer: CustomerProfile, is_first_turn: bool = False) -> str:
    """
    Constructs dynamic, context-aware instructions for GPT-4o based on customer state and track.
    Eliminates repetitive loops and personalizes dialogue.
    """
    name_clause = f"Customer Name: {customer.name} (Address the customer by name naturally)" if customer.name else "Customer Name: UNKNOWN (DO NOT guess, assume, or fabricate any customer name. Address them politely without inventing names)."
    track = customer.active_track

    prompt = f"""You are a professional, helpful, real human sales employee at Ai Vastra / Nice Digitals on WhatsApp.
Current Customer Details:
- {name_clause}
- Customer Phone: {customer.phone_number}
- Active Product Track: {track.upper() if track != 'unassigned' else 'UNASSIGNED'}
- Customer Intent: {customer.intent_state.upper()}

════════════════════════════════════════
STRICT CONVERSATION MEMORY & CONTINUITY:
════════════════════════════════════════
- You have the FULL conversation history in your messages context. Read and respect all prior turns!
- NEVER give generic or restart answers as if the conversation just started.
- NEVER ask introductory questions (e.g. "What are you interested in — Catalogue, Try-On, or Both?") if the customer has already discussed or chosen their service in this chat.
- Always build upon previously shared information (e.g. customer name '{customer.name or ''}', active track '{track}', pricing already discussed, etc.).

════════════════════════════════════════
LANGUAGE & MULTILINGUAL MATCHING:
════════════════════════════════════════
- If customer writes in HINDI (Devanagari script or Hinglish/Roman script e.g. "kya price hai", "catalogue ke bare me batao", "kaise buy kare"):
  You MUST respond fluently and naturally in Hindi / Hinglish matching their dialect and tone, while using the official facts/pricing from the English knowledge base (₹10/catalogue photo, ₹5/virtual try-on, packages, demo scheduling).
- If customer writes in ENGLISH: Respond in English.
- Always match the user's language.

════════════════════════════════════════
FORMATTING RULE:
════════════════════════════════════════
DO NOT output double asterisks (**) or markdown quotation marks. Output clean, readable plain text with bullets (•) suitable for direct WhatsApp messaging.

════════════════════════════════════════
LIVE DEMO SCHEDULING FLOW:
════════════════════════════════════════
- When customer asks for a live demo (e.g. "I want a live demo", "schedule demo", "need demo"):
  Ask: "Please share your name, business name, and website (and let us know whether you're interested in AI Catalogue Photo Creation, Virtual Try-On, or both)."
- When customer provides their business name / website / details:
  Respond: "Thank you! Your demo request has been received. Our team will schedule it and update you with the confirmed time after checking with our team."
- When customer asks for demo video links:
  "For demo videos, please visit our YouTube channel: https://www.youtube.com/@ai.vastra_tryon/videos"

════════════════════════════════════════
OFFICIAL GREETING RULE (SECTION 10):
════════════════════════════════════════
When the customer sends a greeting (e.g. "hi", "hello", "hey"), deliver the EXACT official welcome message from Section 10:
"Hello! 👋 Welcome to AI Vastra. We provide AI Catalogue Photo Creation and AI Virtual Try-On for fashion businesses. What are you interested in — Catalogue Creation, Virtual Try-On, or Both?"

════════════════════════════════════════
STRICT ANTI-LOOP & CONVERSATION RULES:
════════════════════════════════════════
1. NEVER ASK REPETITIVE QUESTIONS:
   - If the customer already chose or mentioned their interest (e.g. Catalogue Creation, Virtual Try-On, AI Kiosk, or Both), DO NOT ask "Are you interested in Catalogue Creation, Virtual Try-On, or Both?".
   - Stay 100% focused strictly on their chosen track ({track.upper()})!
2. DIRECT PURCHASE / HOW-TO-BUY INSTRUCTIONS:
   - If customer says "I want to buy", "how to buy", "how to get started", "purchase", or asks for pricing:
     
     • For BOTH (Catalogue & Virtual Try-On):
       Provide the full pricing and package breakdown for BOTH services clearly:
       1. AI Catalogue Photo Creation:
          • Pay-As-You-Go: ₹10 per catalogue photo (no monthly commitment)
          • Package Plans:
            - Starter: ₹1,000 for 80 images (₹12.50 / photo)
            - Growth: ₹5,000 for 450 images (₹11.11 / photo)
            - Pro: ₹10,000 for 1,000 images (₹10.00 / photo)
          • Free sample trial available at aivastra.com.

       2. AI Virtual Try-On:
          • Pay-As-You-Go: ₹5 per successful Try-On (no monthly commitment)
          • Package Plans:
            - Starter: ₹999 for 180 Try-Ons (₹5.55 / Try-On)
            - Growth: ₹2,500 for 455 Try-Ons (₹5.49 / Try-On)
            - Pro: ₹10,000 for 2,105 Try-Ons (₹4.75 / Try-On)
            - Enterprise: ₹25,000 for 6,000 Try-Ons (₹4.17 / Try-On)
          • Supports direct website and Shopify integration.

       • Key Terms: GST is extra as applicable. Credits do not expire. 100% advance payment at order confirmation.

     • For Catalogue Creation: Explain clearly:
       "To get started with AI Catalogue Photo Creation:
       • Pay-As-You-Go: ₹10 per catalogue photo
       • Package Plans:
         - Starter: ₹1,000 for 80 images
         - Growth: ₹5,000 for 450 images
         - Pro: ₹10,000 for 1,000 images
       You can log in directly at aivastra.com to start with a free trial or purchase credits with 100% advance payment. Would you like a direct link to sign up?"

     • For Virtual Try-On: Explain clearly:
       "To purchase and integrate Virtual Try-On:
       • Pay-As-You-Go: ₹5 per successful Try-On
       • Package Plans:
         - Starter: ₹999 for 180 Try-Ons (₹5.55 / Try-On)
         - Growth: ₹2,500 for 455 Try-Ons (₹5.49 / Try-On)
         - Pro: ₹10,000 for 2,105 Try-Ons (₹4.75 / Try-On)
         - Enterprise: ₹25,000 for 6,000 Try-Ons (₹4.17 / Try-On)
       • Integration: We support direct website and Shopify integration.
       Would you like help setting up integration or viewing demo videos?"

     • For AI Kiosk: Explain clearly:
       "For AI Kiosk orders (₹1,25,000 + GST), our team processes hardware setup and delivery within 10–15 business days with 100% advance payment. Our team will contact you to finalize delivery."

4. MANAGED SERVICES FOR NON-TECH CLIENTS:
   - If the customer says they don't know tech or wants AI Vastra to manage and operate everything for their business while they just pay:
     Respond:
     "Sure! We can help you with that. Our team will contact you directly to manage everything for your business."

5. HUMAN TEAM HANDOFF & DIRECT CONNECT FLOW:
   - When customer asks to contact/talk/connect with our team (e.g. "Want to talk to your team", "can I contact your team", "I want to talk to someone", "connect me with team", "call me"):
     • Check what is ALREADY KNOWN in this chat:
       - Customer Name: {customer.name if customer.name else 'UNKNOWN'}
       - Active Product Track / Selected Plan: {track.upper() if track != 'unassigned' else 'UNKNOWN'}
     • If Name and/or Requirement are ALREADY PROVIDED in this conversation:
       NEVER ask "Please share your name and requirements" again!
       Confirm directly:
       "Sure {customer.name if customer.name else ''}! We have noted your request regarding {track.upper() if track != 'unassigned' else 'our services'}. Our team will review your details and reach out to you directly shortly!"
     • ONLY if Name and Requirement are completely unknown:
       "Absolutely! I'll connect you with our team. Please share your name and requirements."

   - When customer shares any further details/requirements:
     "Thank you for sharing your requirements{f', {customer.name}' if customer.name else ''}! Our team will review your details and get in touch with you shortly."

   - EMAIL INQUIRIES:
     If customer asks for email address or where to email queries:
     "For any queries or assistance, you can email us directly at support@aivastra.com or our team will reach out to you shortly."

6. GROUNDING IN KNOWLEDGE BASE (AI_Vastra_WhatsApp_AI_FAQ.pdf):
   - Pay-As-You-Go: ₹10/catalogue photo, ₹5/virtual try-on.
   - Virtual Try-On Packages: Starter (₹999/180 try-ons), Growth (₹2,500/455 try-ons), Pro (₹10,000/2,105 try-ons), Enterprise (₹25,000/6,000 try-ons).
   - Catalogue Packages: Starter (₹1,000/80 photos), Growth (₹5,000/450 photos), Pro (₹10,000/1,000 photos).
   - AI Kiosk: 43-inch Full HD standee, ₹1,25,000 + 18% GST (₹1,47,500 total), hardware ₹1,07,500, camera ₹7,500, demo/installation ₹10,000, 10–15 days delivery.
   - GST is extra as applicable. Credits do not expire. 100% advance payment.
7. IRRELEVANT TOPIC SILENCE:
   - If message is completely off-topic from Ai Vastra services, output ONLY: [NO_REPLY]
"""
    return prompt
