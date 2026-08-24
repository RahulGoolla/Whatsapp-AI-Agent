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
    Extracts high-precision Q&A chunks and section blocks from knowledge base.
    """
    chunks = []
    splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=100)
    for page_num, text in pages:
        for chunk in splitter.split_text(text):
            clean = chunk.strip()
            if len(clean) > 30:
                chunks.append({"text": clean, "page": page_num})

    return chunks


async def seed_default_knowledge_base(force_reindex: bool = False) -> None:
    """
    Auto-seeds the default 'Whatsapp_FAQ' workspace with:
    1. 'AI_Vastra_WhatsApp_AI_FAQ.pdf'
    2. 'AI_VASTRA_SALES_GUIDELINES.md'
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

        base_dir = os.path.dirname(__file__)

        # Documents to index
        target_files = [
            {
                "filename": "AI_Vastra_WhatsApp_AI_FAQ.pdf",
                "paths": [
                    os.path.abspath(os.path.join(base_dir, "..", "..", "..", "AI_Vastra_WhatsApp_AI_FAQ.pdf")),
                    os.path.abspath(os.path.join(base_dir, "..", "..", "assets", "AI_Vastra_WhatsApp_AI_FAQ.pdf")),
                    os.path.abspath(os.path.join(base_dir, "..", "..", "uploads", "AI_Vastra_WhatsApp_AI_FAQ.pdf")),
                ],
                "mime": "application/pdf"
            },
            {
                "filename": "AI_VASTRA_SALES_GUIDELINES.md",
                "paths": [
                    os.path.abspath(os.path.join(base_dir, "..", "..", "..", "AI_VASTRA_SALES_GUIDELINES.md")),
                    os.path.abspath(os.path.join(base_dir, "..", "..", "assets", "AI_VASTRA_SALES_GUIDELINES.md")),
                ],
                "mime": "text/markdown"
            }
        ]

        all_chunk_texts = []
        all_metadatas = []
        all_ids = []

        for target in target_files:
            fname = target["filename"]
            fpath = None
            for p in target["paths"]:
                if os.path.exists(p):
                    fpath = p
                    break

            if not fpath:
                logger.warning(f"File '{fname}' not found in search paths.")
                continue

            # Check DB record
            doc_query = (
                select(Document)
                .where(Document.workspace_id == workspace.id)
                .where(Document.filename == fname)
                .limit(1)
            )
            doc_res = await db.execute(doc_query)
            existing_doc = doc_res.scalar_one_or_none()

            with open(fpath, "rb") as f:
                file_bytes = f.read()

            if not existing_doc:
                document = Document(
                    filename=fname,
                    storage_key=f"{workspace.id}/{fname}",
                    file_size=len(file_bytes),
                    mime_type=target["mime"],
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

            # Extract chunks
            text_pages = []
            if fname.endswith(".pdf"):
                reader = PdfReader(io.BytesIO(file_bytes))
                for idx, page in enumerate(reader.pages):
                    page_text = page.extract_text() or ""
                    text_pages.append((idx + 1, page_text))
            else:
                text_content = file_bytes.decode("utf-8", errors="ignore")
                text_pages.append((1, text_content))

            chunks_data = extract_semantic_qa_chunks(text_pages)
            for idx, c in enumerate(chunks_data):
                all_chunk_texts.append(c["text"])
                all_ids.append(f"{document.id}_{idx}")
                all_metadatas.append({
                    "document_id": str(document.id),
                    "workspace_id": str(workspace.id),
                    "filename": fname,
                    "page": c["page"],
                })

            document.status = "completed"
            await db.commit()

        if all_chunk_texts:
            logger.info(f"Generating vector embeddings for {len(all_chunk_texts)} chunks across knowledge base files...")
            vectors = await embedding_provider.get_embeddings(all_chunk_texts)

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

            collection.add(
                ids=all_ids,
                documents=all_chunk_texts,
                embeddings=vectors,
                metadatas=all_metadatas,
            )
            logger.info(f"Successfully indexed {len(all_chunk_texts)} chunks into ChromaDB for workspace '{workspace.name}'!")
