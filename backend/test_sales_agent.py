import asyncio
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(__file__))

from app.db.base import Base
from app.db.session import AsyncSessionLocal, engine
from app.models.workspace import Workspace
from app.services.rag import execute_rag_sync
from app.services.sales_rules import check_escalation_triggers
from app.services.seeder import seed_default_knowledge_base
from sqlalchemy.future import select


async def run_tests():
    print("=" * 60)
    print("🧪 STARTING AI VASTRA WHATSAPP SALES AGENT TEST SUITE")
    print("=" * 60)

    # 1. Initialize Database
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("✅ Step 1: Database tables initialized.")

    # 2. Seed Knowledge Base with AI_Vastra_WhatsApp_AI_FAQ.pdf
    await seed_default_knowledge_base()
    print("✅ Step 2: Knowledge base auto-seeded into ChromaDB.")

    # 3. Retrieve Workspace
    async with AsyncSessionLocal() as db:
        ws_res = await db.execute(select(Workspace).where(Workspace.name == "Whatsapp_FAQ").limit(1))
        workspace = ws_res.scalar_one_or_none()
        assert workspace is not None, "Workspace Whatsapp_FAQ not found!"
        ws_id = workspace.id
        print(f"✅ Step 3: Workspace verified (ID: {ws_id})")

        # 4. Test Escalation Trigger Check
        print("\n--- TEST: Escalation Triggers ---")
        escalation_queries = [
            "I want a live demo",
            "Give me custom enterprise pricing and API access",
            "Can I speak to someone?",
            "Do you provide reseller discount?",
            "I need custom AI model training",
        ]
        for q in escalation_queries:
            res = check_escalation_triggers(q)
            assert res["is_escalated"] is True, f"Failed to escalate query: {q}"
            print(f"  ✓ Escalated '{q}' -> Reason: {res['reason']}")

        # 5. Test Live RAG Queries
        print("\n--- TEST: Live RAG Queries & Deliverability ---")
        test_cases = [
            {
                "query": "hello",
                "expected_keywords": ["Welcome to AI Vastra", "Catalogue Creation", "Virtual Try-On"],
            },
            {
                "query": "catalogue",
                "expected_keywords": ["professional catalogue photos", "₹10", "aivastra.com"],
            },
            {
                "query": "what about the gst plans",
                "expected_keywords": ["GST", "extra as applicable"],
            },
            {
                "query": "how much does virtual try-on cost?",
                "expected_keywords": ["₹5", "successful"],
            },
            {
                "query": "do credits expire?",
                "expected_keywords": ["credits do not expire"],
            },
            {
                "query": "Can I speak to someone from your sales team?",
                "expected_keywords": ["our team will contact you"],
            }
        ]

        for tc in test_cases:
            query = tc["query"]
            print(f"\n👉 Query: '{query}'")
            res = await execute_rag_sync(
                workspace_id=ws_id,
                query_text=query,
                messages=[{"role": "user", "content": query}],
                db=db,
            )
            reply = res["response"]
            print(f"🤖 Response:\n{reply}\n")
            print(f"   [Escalated: {res['is_escalated']} | Citations: {len(res['citations'])}]")

            for kw in tc["expected_keywords"]:
                assert kw.lower() in reply.lower(), f"Expected keyword '{kw}' not found in reply: '{reply}'"
            print(f"   ✅ Verified expected keywords for: '{query}'")

    print("\n" + "=" * 60)
    print("🎉 ALL AI VASTRA SALES AGENT TESTS PASSED 100% SUCCESSFULLY!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_tests())
