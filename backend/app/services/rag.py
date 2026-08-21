import uuid
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.ai.llm import llm_provider
from app.core.logging import logger
from app.models.customer import CustomerProfile
from app.models.document import Document
from app.services.sales_rules import (
    AI_VASTRA_SYSTEM_PROMPT,
    check_escalation_triggers,
)
from app.services.state_manager import build_contextual_prompt
from app.vector_db.operations import query_vector_db


async def execute_rag_stream(
    workspace_id: uuid.UUID,
    query_text: str,
    messages: list[dict],
    db: AsyncSession,
    document_id: uuid.UUID | None = None,
    customer: CustomerProfile | None = None,
) -> tuple[list[dict], AsyncGenerator[str, None], dict]:
    """
    Orchestrates the AI Vastra WhatsApp Sales RAG flow with Customer Memory & Anti-Looping:
    1. Checks escalation/handoff triggers (e.g. demo, custom pricing, human agent).
    2. Builds search query guided by customer's active product track.
    3. Retrieves matching chunks from ChromaDB.
    4. Synthesizes dynamic contextual system prompt tailored to customer state.
    5. Streams the response with citations.
    """
    logger.info(f"Initiating AI Vastra RAG stream pipeline for query in workspace {workspace_id}: '{query_text}' (Track: {customer.active_track if customer else 'none'})")

    # 1. Check for escalation flag (for metadata / CRM tagging)
    escalation_check = check_escalation_triggers(query_text)
    is_escalated = escalation_check["is_escalated"]
    escalation_reason = escalation_check["reason"]

    # 2. Build track-aware search query to retrieve exact relevant sections
    search_query = query_text
    if customer and customer.active_track == "catalogue":
        search_query = f"Catalogue Photo Creation {query_text}"
    elif customer and customer.active_track == "virtual_tryon":
        search_query = f"Virtual Try-On {query_text}"
    elif customer and customer.active_track == "ai_kiosk":
        search_query = f"AI Kiosk Standee {query_text}"

    # Retrieve context chunks from ChromaDB
    raw_chunks = await query_vector_db(
        workspace_id=workspace_id,
        query_text=search_query,
        n_results=5,
        document_id=document_id,
    )

    citations = []
    context_blocks = []

    if raw_chunks:
        doc_uuids = list({chunk["document_id"] for chunk in raw_chunks})
        doc_query = select(Document.id, Document.filename).where(Document.id.in_(doc_uuids))
        doc_result = await db.execute(doc_query)
        doc_mapping = {row[0]: row[1] for row in doc_result.all()}

        for idx, chunk in enumerate(raw_chunks, 1):
            doc_id = chunk["document_id"]
            filename = doc_mapping.get(doc_id, "AI_Vastra_WhatsApp_AI_FAQ.pdf")

            citations.append(
                {
                    "index": idx,
                    "document_id": str(doc_id),
                    "filename": filename,
                    "page": chunk.get("page"),
                    "score": chunk.get("score"),
                    "text_snippet": chunk.get("text", "")[:400],
                }
            )

            page_info = f" (Page {chunk['page']})" if chunk.get("page") else ""
            context_blocks.append(
                f"Source [{idx}]: Document '{filename}'{page_info}\n"
                f"Content: {chunk['text']}\n"
            )

    # 3. Synthesize the dynamic, state-aware AI Vastra WhatsApp sales prompt
    context_str = "\n---\n".join(context_blocks) if context_blocks else "Use official AI Vastra verified knowledge base."
    
    if customer:
        base_prompt = build_contextual_prompt(customer)
    else:
        base_prompt = AI_VASTRA_SYSTEM_PROMPT

    system_prompt = (
        f"{base_prompt}\n\n"
        f"--- VERIFIED DOCUMENT SOURCES (AI_Vastra_WhatsApp_AI_FAQ.pdf) ---\n{context_str}\n"
        "---------------------------------\n"
        "Generate a clear, natural, friendly WhatsApp reply adhering strictly to the above facts. Cite source brackets [1], [2] where appropriate. NEVER re-ask questions already answered in chat history. If the query is completely off-topic from Ai Vastra services, respond ONLY with [NO_REPLY]."
    )

    # 4. Get the LLM stream generator
    logger.info("Triggering LLM streaming generation for WhatsApp response...")
    token_stream = llm_provider.stream_response(
        messages=messages, system_prompt=system_prompt
    )

    return citations, token_stream, {"is_escalated": is_escalated, "escalation_reason": escalation_reason, "is_ignored": False}


async def execute_rag_sync(
    workspace_id: uuid.UUID,
    query_text: str,
    messages: list[dict],
    db: AsyncSession,
    document_id: uuid.UUID | None = None,
    customer: CustomerProfile | None = None,
) -> dict:
    """
    Synchronous execution of the AI Vastra WhatsApp RAG flow.
    """
    citations, token_stream, meta = await execute_rag_stream(
        workspace_id=workspace_id,
        query_text=query_text,
        messages=messages,
        db=db,
        document_id=document_id,
        customer=customer,
    )

    tokens = []
    async for token in token_stream:
        tokens.append(token)

    response_text = "".join(tokens).strip()
    response_text = response_text.replace("**", "")
    is_ignored = False

    if "[NO_REPLY]" in response_text or response_text == "":
        is_ignored = True
        response_text = "[No reply sent - Query is unrelated to AI Vastra]"

    return {
        "response": response_text,
        "citations": citations,
        "is_escalated": meta.get("is_escalated", False),
        "escalation_reason": meta.get("escalation_reason"),
        "is_ignored": is_ignored,
    }
