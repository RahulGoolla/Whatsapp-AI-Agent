import asyncio
import io
import uuid

from pypdf import PdfReader
from sqlalchemy.future import select

from app.ai.embedding import embedding_provider
from app.core.logging import logger
from app.db.session import AsyncSessionLocal
from app.models.document import Document
from app.services.text_splitter import RecursiveCharacterTextSplitter
from app.storage.manager import storage_client
from app.tasks.worker import celery_app
from app.vector_db.client import chroma_manager


def _extract_text_pages(filename: str, file_bytes: bytes) -> list[tuple[int, str]]:
    """
    Parses document bytes depending on file extension.
    Returns a list of tuples containing (page_number, text_content).
    """
    text_pages: list[tuple[int, str]] = []
    filename_lower = filename.lower()

    if filename_lower.endswith(".pdf"):
        logger.info(f"Parsing PDF document: {filename}")
        reader = PdfReader(io.BytesIO(file_bytes))
        for idx, page in enumerate(reader.pages):
            page_text = page.extract_text() or ""
            text_pages.append((idx + 1, page_text))
    elif filename_lower.endswith((".txt", ".md")):
        logger.info(f"Parsing Text/Markdown document: {filename}")
        text_content = file_bytes.decode("utf-8", errors="ignore")
        text_pages.append((1, text_content))
    else:
        raise ValueError(
            "Unsupported file format. Only PDF, TXT, and MD are supported."
        )

    return text_pages


def _index_chunks_in_chroma(
    document: Document, chunks_data: list[dict], vectors: list[list[float]]
) -> None:
    """
    Indexes the text chunks and generated embedding vectors inside the ChromaDB collection.
    """
    logger.info("Initializing vector indexing in ChromaDB...")
    chroma_client = chroma_manager.get_client()

    # Collection name is based on the workspace ID (hex format is clean and safe)
    collection_name = f"workspace_{document.workspace_id.hex}"
    collection = chroma_client.get_or_create_collection(name=collection_name)

    # Prepare batch inputs
    ids = [f"{document.id}_{i}" for i in range(len(chunks_data))]
    chunk_texts = [c["text"] for c in chunks_data]
    metadatas = [
        {
            "document_id": str(document.id),
            "workspace_id": str(document.workspace_id),
            "page": chunk["page"],
        }
        for chunk in chunks_data
    ]

    # Upsert into ChromaDB
    collection.add(
        ids=ids,
        documents=chunk_texts,
        embeddings=vectors,
        metadatas=metadatas,
    )
    logger.info(
        f"Vector indexing complete. Saved {len(ids)} vectors to collection: {collection_name}"
    )


async def process_document_async(document_id_str: str) -> None:
    """
    Asynchronous runner for document ingestion.
    Parses document, chunks text, generates embeddings, and indexes in ChromaDB.
    """
    logger.info(f"Background task starting: Ingestion for document {document_id_str}")

    try:
        doc_uuid = uuid.UUID(document_id_str)
    except ValueError:
        logger.error(f"Invalid document UUID: {document_id_str}")
        return

    async with AsyncSessionLocal() as db:
        # Fetch document record
        query = select(Document).where(Document.id == doc_uuid)
        result = await db.execute(query)
        document = result.scalar_one_or_none()

        if not document:
            logger.error(f"Document {doc_uuid} not found in database. Aborting.")
            return

        # Update status to processing
        document.status = "processing"
        document.error_message = None
        await db.commit()

        try:
            # Download file from storage provider
            logger.info(f"Downloading file from storage key: {document.storage_key}")
            file_bytes = await storage_client.download_file(document.storage_key)

            # Parse text based on format
            text_pages = _extract_text_pages(document.filename, file_bytes)

            # Chunk text recursively (preserving page numbers for PDF citations)
            logger.info("Splitting parsed text into logical chunks (overlap active)...")
            splitter = RecursiveCharacterTextSplitter(
                chunk_size=1000, chunk_overlap=200
            )
            chunks_data = []

            for page_num, page_text in text_pages:
                page_chunks = splitter.split_text(page_text)
                for chunk in page_chunks:
                    if chunk.strip():
                        chunks_data.append({"text": chunk, "page": page_num})

            if not chunks_data:
                raise ValueError("No text could be extracted from this document.")

            logger.info(f"Extracted {len(chunks_data)} text chunks for indexing.")

            # Generate embeddings in batches
            chunk_texts = [c["text"] for c in chunks_data]
            logger.info("Generating vector embeddings via AI provider...")
            vectors = await embedding_provider.get_embeddings(chunk_texts)

            # Index into ChromaDB
            _index_chunks_in_chroma(document, chunks_data, vectors)

            # Complete Task
            document.status = "completed"
            await db.commit()
            logger.info(
                f"Ingestion pipeline completed successfully for document: {document.id}"
            )

        except Exception as e:
            logger.exception(
                f"Ingestion pipeline failed for document {document.id}: {e}"
            )
            document.status = "failed"
            document.error_message = str(e)
            await db.commit()


@celery_app.task(name="app.tasks.ingestion_tasks.process_document_task")
def process_document_task(document_id_str: str) -> None:
    """
    Synchronous Celery entry point. Launches the async process runner.
    """
    asyncio.run(process_document_async(document_id_str))
