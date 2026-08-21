import asyncio
import uuid
from unittest.mock import AsyncMock, patch

from sqlalchemy.future import select

import app.models  # noqa: F401 - Register ORM models
from app.ai.embedding import embedding_provider
from app.core.logging import logger
from app.db.base import Base
from app.db.session import AsyncSessionLocal, engine
from app.models.document import Document
from app.models.user import User
from app.models.workspace import Workspace
from app.services.rag import execute_rag_stream
from app.services.text_splitter import RecursiveCharacterTextSplitter
from app.vector_db.client import chroma_manager
from app.vector_db.operations import query_vector_db


async def run_e2e_test():
    logger.info("=========================================")
    logger.info("STARTING END-TO-END RAG PIPELINE VERIFICATION")
    logger.info("=========================================")

    # Mock embedding provider to return a deterministic 1536-dim vector for testing
    deterministic_vector = [0.05] * 1536
    mock_get_embedding = AsyncMock(return_value=deterministic_vector)

    with patch.object(embedding_provider, "get_embedding", mock_get_embedding):
        # 0. Initialize database schema
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Step 0 PASSED: Database schema tables verified.")

        async with AsyncSessionLocal() as db:
            # 1. Create or get dummy test User
            user_query = select(User).limit(1)
            res = await db.execute(user_query)
            user = res.scalar_one_or_none()

            if not user:
                user = User(
                    clerk_id=f"test_clerk_{uuid.uuid4().hex[:8]}",
                    email="e2e_test@ragenius.ai",
                    first_name="E2E",
                    last_name="Tester",
                )
                db.add(user)
                await db.commit()
                await db.refresh(user)

            logger.info(f"Step 1 PASSED: User verified (ID: {user.id})")

            # 2. Create test Workspace
            workspace = Workspace(
                name="E2E Pipeline Test Workspace",
                user_id=user.id,
            )
            db.add(workspace)
            await db.commit()
            await db.refresh(workspace)
            logger.info(f"Step 2 PASSED: Workspace created (ID: {workspace.id})")

            # 3. Create test Document & text content
            sample_text = (
                "RAGenius AI quarterly revenue reached $14.5 Million in Q2 2026, "
                "registering a 42% growth rate compared to Q1. The platform active user base "
                "expanded to 150,000 enterprise accounts."
            )
            document = Document(
                filename="e2e_report.txt",
                storage_key=f"{workspace.id}/e2e_report.txt",
                file_size=len(sample_text.encode("utf-8")),
                mime_type="text/plain",
                status="completed",
                workspace_id=workspace.id,
                user_id=user.id,
            )
            db.add(document)
            await db.commit()
            await db.refresh(document)
            logger.info(f"Step 3 PASSED: Document record created (ID: {document.id})")

            # 4. Chunk & embed document text
            splitter = RecursiveCharacterTextSplitter(chunk_size=300, chunk_overlap=50)
            chunks = splitter.split_text(sample_text)

            embeddings = []
            for chunk_text in chunks:
                vector = await embedding_provider.get_embedding(chunk_text)
                embeddings.append(vector)

            # 5. Index into ChromaDB collection
            chroma_client = chroma_manager.get_client()
            collection_name = f"workspace_{workspace.id.hex}"
            collection = chroma_client.get_or_create_collection(
                name=collection_name,
                metadata={"hnsw:space": "l2"},
            )

            chunk_ids = [f"{document.id}_{i}" for i in range(len(chunks))]
            metadatas = [
                {
                    "document_id": str(document.id),
                    "workspace_id": str(workspace.id),
                    "page": 1,
                }
                for _ in chunks
            ]

            collection.add(
                ids=chunk_ids,
                embeddings=embeddings,
                documents=chunks,
                metadatas=metadatas,
            )
            logger.info(
                f"Step 4 PASSED: Embedded & indexed {len(chunks)} chunks in ChromaDB collection '{collection_name}'"
            )

            # 6. Test Semantic Search Query
            search_query = "What was the revenue in Q2 2026?"
            matches = await query_vector_db(
                workspace_id=workspace.id,
                query_text=search_query,
                n_results=3,
            )
            assert len(matches) > 0, "Vector search returned zero matches!"
            assert "14.5 Million" in matches[0]["text"], "Retrieved chunk text mismatch!"
            logger.info(
                f"Step 5 PASSED: Semantic search returned top match with score {matches[0]['score']}"
            )

            # 7. Test RAG Stream Pipeline Synthesis
            citations, _ = await execute_rag_stream(
                workspace_id=workspace.id,
                query_text=search_query,
                messages=[{"role": "user", "content": search_query}],
                db=db,
            )
            assert len(citations) > 0, "RAG pipeline returned zero citations!"
            assert citations[0]["filename"] == "e2e_report.txt", "Citation filename mismatch!"
            logger.info(
                f"Step 6 PASSED: RAG Prompt synthesized {len(citations)} source citation(s)."
            )

            # 8. Clean up test assets
            chroma_client.delete_collection(name=collection_name)
            await db.delete(document)
            await db.delete(workspace)
            await db.commit()
            logger.info("Step 7 PASSED: Cleaned up test database rows and ChromaDB collection.")

            logger.info("=========================================")
            logger.info("ALL END-TO-END RAG PIPELINE TESTS PASSED 100% SUCCESSFULLY!")
            logger.info("=========================================")


if __name__ == "__main__":
    asyncio.run(run_e2e_test())
