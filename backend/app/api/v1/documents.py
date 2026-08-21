import asyncio
import uuid

from fastapi import APIRouter, Depends, File, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.api.v1.auth import get_current_user
from app.core.exceptions import IngestionError, NotFoundError
from app.core.logging import logger
from app.db.session import get_db
from app.models.document import Document
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.document import DocumentResponse, DocumentStatusResponse
from app.storage.manager import storage_client
from app.tasks.ingestion_tasks import process_document_async, process_document_task
from app.vector_db.client import chroma_manager

router = APIRouter(tags=["documents"])

# Background task set to prevent Python asyncio garbage collection
_background_ingestion_tasks: set[asyncio.Task] = set()


async def _verify_workspace_access(
    workspace_id: uuid.UUID, user: User, db: AsyncSession
) -> Workspace:
    """Verifies that the workspace exists."""
    query = select(Workspace).where(Workspace.id == workspace_id)
    res = await db.execute(query)
    workspace = res.scalar_one_or_none()
    if not workspace:
        raise NotFoundError(message="Workspace not found")
    return workspace


@router.post(
    "/workspaces/{workspace_id}/documents",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    workspace_id: uuid.UUID,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DocumentResponse:
    """
    Uploads a document file to the specified workspace and triggers ingestion.
    Supports both Celery task dispatch and inline async task execution fallback.
    """
    await _verify_workspace_access(workspace_id, current_user, db)

    # Validate file format
    if not file.filename:
        raise IngestionError(message="Uploaded file is missing a filename.")

    filename_lower = file.filename.lower()
    if not filename_lower.endswith((".pdf", ".txt", ".md")):
        raise IngestionError(
            message="Invalid file format. Only PDF, TXT, and MD files are supported."
        )

    # Read content bytes
    file_bytes = await file.read()
    file_size = len(file_bytes)

    if file_size == 0:
        raise IngestionError(message="Uploaded file is empty.")

    # 1. Save file to storage provider
    storage_key = await storage_client.upload_file(
        file_content=file_bytes,
        filename=file.filename,
        path_prefix=str(workspace_id),
    )

    # 2. Insert document record into DB
    document = Document(
        filename=file.filename,
        storage_key=storage_key,
        file_size=file_size,
        mime_type=file.content_type,
        status="pending",
        workspace_id=workspace_id,
        user_id=current_user.id if current_user else None,
    )
    db.add(document)
    await db.commit()
    await db.refresh(document)

    logger.info(f"Document record created: {document.id} for file '{file.filename}'")

    # 3. Trigger Ingestion task (Celery first; inline async fallback if Celery is off)
    try:
        process_document_task.delay(str(document.id))
        logger.info(
            f"Triggered Celery task process_document_task for document {document.id}"
        )
    except Exception as e:
        logger.warning(
            f"Celery task dispatch unavailable ({e}). Launching inline async ingestion task..."
        )
        task = asyncio.create_task(process_document_async(str(document.id)))
        _background_ingestion_tasks.add(task)
        task.add_done_callback(_background_ingestion_tasks.discard)

    return DocumentResponse.model_validate(document)


@router.get(
    "/workspaces/{workspace_id}/documents", response_model=list[DocumentResponse]
)
async def list_workspace_documents(
    workspace_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[DocumentResponse]:
    """Lists all documents uploaded to a workspace."""
    await _verify_workspace_access(workspace_id, current_user, db)

    query = (
        select(Document)
        .where(Document.workspace_id == workspace_id)
        .order_by(Document.created_at.desc())
    )
    result = await db.execute(query)
    documents = result.scalars().all()
    return [DocumentResponse.model_validate(doc) for doc in documents]


@router.get("/documents/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DocumentResponse:
    """Retrieves metadata and current ingestion status of a single document."""
    query = select(Document).where(Document.id == document_id)
    res = await db.execute(query)
    document = res.scalar_one_or_none()

    if not document:
        raise NotFoundError(message="Document not found")

    return DocumentResponse.model_validate(document)


@router.get("/documents/{document_id}/status", response_model=DocumentStatusResponse)
async def get_document_status(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DocumentStatusResponse:
    """Lightweight polling endpoint for real-time document ingestion status."""
    query = select(Document).where(Document.id == document_id)
    res = await db.execute(query)
    document = res.scalar_one_or_none()

    if not document:
        raise NotFoundError(message="Document not found")

    return DocumentStatusResponse(
        id=document.id,
        status=document.status,
        error_message=document.error_message,
    )


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Deletes a document, purges its storage file, and deletes its vector chunks from ChromaDB."""
    query = select(Document).where(Document.id == document_id)
    res = await db.execute(query)
    document = res.scalar_one_or_none()

    if not document:
        raise NotFoundError(message="Document not found")

    # 1. Remove physical file from storage provider
    try:
        await storage_client.delete_file(document.storage_key)
    except Exception as e:
        logger.warning(
            f"Error removing physical storage file {document.storage_key}: {e}"
        )

    # 2. Delete vector chunks from ChromaDB collection
    try:
        chroma_client = chroma_manager.get_client()
        collection_name = f"workspace_{document.workspace_id.hex}"
        existing_cols = [col.name for col in chroma_client.list_collections()]
        if collection_name in existing_cols:
            collection = chroma_client.get_collection(name=collection_name)
            # Delete chunks matching this document_id
            collection.delete(where={"document_id": str(document.id)})
            logger.info(
                f"Deleted vector chunks for document {document_id} from ChromaDB"
            )
    except Exception as e:
        logger.warning(
            f"Error removing ChromaDB vector chunks for document {document_id}: {e}"
        )

    # 3. Delete database record
    await db.delete(document)
    await db.commit()
    logger.info(f"Deleted document record {document_id}")
