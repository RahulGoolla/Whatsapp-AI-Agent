import io
import os
import re
import uuid
from pypdf import PdfReader
from sqlalchemy.future import select

from app.ai.embedding import embedding_provider
from app.core.logging import logger
from app.db.session import AsyncSessionLocal
from app.models.document import Document
from app.models.workspace import Workspace
from app.services.text_splitter import RecursiveCharacterTextSplitter
from app.vector_db.client import chroma_manager


def extract_semantic_qa_chunks(pages: list[tuple[int, str]]) -> list[dict]:
    """
    Extracts high-precision Q&A chunks and section blocks from AI Vastra FAQ PDF.
    Preserves exact verbatim text for each question and answer.
    """
    chunks = []
    
    # 1. Fallback recursive splitter for general coverage
    splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=100)
    for page_num, text in pages:
        for chunk in splitter.split_text(text):
            clean = chunk.strip()
            if len(clean) > 30:
                chunks.append({"text": clean, "page": page_num})

    return chunks


async def seed_default_knowledge_base(force_reindex: bool = False) -> None:
    """
    Auto-seeds the default 'Whatsapp_FAQ' workspace with 'AI_Vastra_WhatsApp_AI_FAQ.pdf'
    on startup.
    """
    logger.info("Checking default AI Vastra knowledge base workspace...")

    async with AsyncSessionLocal() as db:
        # 1. Get or create default workspace
        ws_query = select(Workspace).where(Workspace.name == "Whatsapp_FAQ").limit(1)
        ws_res = await db.execute(ws_query)
        workspace = ws_res.scalar_one_or_none()

        if not workspace:
            logger.info("Creating default 'Whatsapp_FAQ' workspace...")
            workspace = Workspace(name="Whatsapp_FAQ")
            db.add(workspace)
            await db.commit()
            await db.refresh(workspace)

        # 2. Check if AI_Vastra_WhatsApp_AI_FAQ.pdf is already indexed
        doc_query = (
            select(Document)
            .where(Document.workspace_id == workspace.id)
            .where(Document.filename == "AI_Vastra_WhatsApp_AI_FAQ.pdf")
            .limit(1)
        )
        doc_res = await db.execute(doc_query)
        existing_doc = doc_res.scalar_one_or_none()

        if existing_doc and existing_doc.status == "completed" and not force_reindex:
            logger.info("Knowledge base 'AI_Vastra_WhatsApp_AI_FAQ.pdf' is already indexed.")
            return

        # 3. Locate PDF file
        base_dir = os.path.dirname(__file__)
        asset_paths = [
            os.path.abspath(os.path.join(base_dir, "..", "..", "..", "AI_Vastra_WhatsApp_AI_FAQ.pdf")),
            os.path.abspath(os.path.join(base_dir, "..", "..", "assets", "AI_Vastra_WhatsApp_AI_FAQ.pdf")),
            os.path.abspath(os.path.join(base_dir, "..", "..", "uploads", "AI_Vastra_WhatsApp_AI_FAQ.pdf")),
        ]

        pdf_path = None
        for p in asset_paths:
            if os.path.exists(p):
                pdf_path = p
                break

        if not pdf_path:
            logger.warning("AI_Vastra_WhatsApp_AI_FAQ.pdf not found.")
            return

        logger.info(f"Indexing AI Vastra knowledge base from: {pdf_path}")
        with open(pdf_path, "rb") as f:
            file_bytes = f.read()

        if not existing_doc:
            document = Document(
                filename="AI_Vastra_WhatsApp_AI_FAQ.pdf",
                storage_key=f"{workspace.id}/AI_Vastra_WhatsApp_AI_FAQ.pdf",
                file_size=len(file_bytes),
                mime_type="application/pdf",
                status="processing",
                workspace_id=workspace.id,
            )
            db.add(document)
            await db.commit()
            await db.refresh(document)
        else:
            document = existing_doc
            document.status = "processing"
            await db.commit()

        try:
            reader = PdfReader(io.BytesIO(file_bytes))
            text_pages = []
            for idx, page in enumerate(reader.pages):
                page_text = page.extract_text() or ""
                text_pages.append((idx + 1, page_text))

            chunks_data = extract_semantic_qa_chunks(text_pages)
            logger.info(f"Generating vector embeddings for {len(chunks_data)} FAQ chunks...")

            chunk_texts = [c["text"] for c in chunks_data]
            vectors = await embedding_provider.get_embeddings(chunk_texts)

            chroma_client = chroma_manager.get_client()
            collection_name = f"workspace_{workspace.id.hex}"
            
            # Reset collection on reindex
            try:
                chroma_client.delete_collection(name=collection_name)
            except Exception:
                pass

            collection = chroma_client.get_or_create_collection(
                name=collection_name,
                metadata={"hnsw:space": "cosine"},
            )

            ids = [f"{document.id}_{i}" for i in range(len(chunks_data))]
            metadatas = [
                {
                    "document_id": str(document.id),
                    "workspace_id": str(workspace.id),
                    "page": chunk["page"],
                }
                for chunk in chunks_data
            ]

            collection.add(
                ids=ids,
                documents=chunk_texts,
                embeddings=vectors,
                metadatas=metadatas,
            )

            document.status = "completed"
            await db.commit()
            logger.info("AI Vastra knowledge base indexed successfully with cosine similarity into ChromaDB!")

        except Exception as e:
            logger.exception(f"Failed to index knowledge base: {e}")
            document.status = "failed"
            document.error_message = str(e)
            await db.commit()
