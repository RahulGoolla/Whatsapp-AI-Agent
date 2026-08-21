import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy import func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.api.v1.auth import get_current_user
from app.core.exceptions import NotFoundError
from app.core.logging import logger
from app.db.session import get_db
from app.models.document import Document
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.workspace import WorkspaceCreate, WorkspaceResponse, WorkspaceUpdate
from app.vector_db.client import chroma_manager

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


async def _get_accessible_workspace(
    workspace_id: uuid.UUID, user: User, db: AsyncSession
) -> Workspace:
    """Helper verifying that a workspace exists."""
    query = select(Workspace).where(Workspace.id == workspace_id)
    result = await db.execute(query)
    workspace = result.scalar_one_or_none()

    if not workspace:
        raise NotFoundError(message="Workspace not found")

    return workspace


@router.post("", response_model=WorkspaceResponse, status_code=status.HTTP_201_CREATED)
async def create_workspace(
    payload: WorkspaceCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceResponse:
    """Creates a new workspace."""
    workspace = Workspace(
        name=payload.name,
        user_id=current_user.id if current_user else None,
    )
    db.add(workspace)
    await db.commit()
    await db.refresh(workspace)

    logger.info(f"Workspace created: {workspace.id}")
    return WorkspaceResponse.model_validate(workspace)


@router.get("", response_model=list[WorkspaceResponse])
async def list_workspaces(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[WorkspaceResponse]:
    """Lists all active workspaces (including default AI Vastra knowledge base)."""
    user_id = current_user.id if current_user else None
    query = (
        select(Workspace, func.count(Document.id).label("doc_count"))
        .outerjoin(Document, Workspace.id == Document.workspace_id)
        .where(or_(Workspace.user_id == user_id, Workspace.user_id.is_(None)))
        .group_by(Workspace.id)
        .order_by(Workspace.created_at.desc())
    )
    result = await db.execute(query)
    rows = result.all()

    workspaces = []
    for workspace, doc_count in rows:
        resp = WorkspaceResponse.model_validate(workspace)
        resp.document_count = doc_count
        workspaces.append(resp)

    return workspaces


@router.get("/{workspace_id}", response_model=WorkspaceResponse)
async def get_workspace(
    workspace_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceResponse:
    """Retrieves details for a single workspace."""
    workspace = await _get_accessible_workspace(workspace_id, current_user, db)

    count_query = select(func.count(Document.id)).where(
        Document.workspace_id == workspace_id
    )
    count_res = await db.execute(count_query)
    doc_count = count_res.scalar() or 0

    resp = WorkspaceResponse.model_validate(workspace)
    resp.document_count = doc_count
    return resp


@router.put("/{workspace_id}", response_model=WorkspaceResponse)
async def update_workspace(
    workspace_id: uuid.UUID,
    payload: WorkspaceUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceResponse:
    """Updates a workspace's details."""
    workspace = await _get_accessible_workspace(workspace_id, current_user, db)

    if payload.name is not None:
        workspace.name = payload.name

    await db.commit()
    await db.refresh(workspace)
    return WorkspaceResponse.model_validate(workspace)


@router.delete("/{workspace_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workspace(
    workspace_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Deletes a workspace and purges its vector collection in ChromaDB."""
    workspace = await _get_accessible_workspace(workspace_id, current_user, db)

    try:
        chroma_client = chroma_manager.get_client()
        collection_name = f"workspace_{workspace_id.hex}"
        existing_cols = [col.name for col in chroma_client.list_collections()]
        if collection_name in existing_cols:
            chroma_client.delete_collection(name=collection_name)
            logger.info(f"Purged ChromaDB collection {collection_name} for deleted workspace.")
    except Exception as e:
        logger.warning(f"Error purging ChromaDB collection during workspace deletion: {e}")

    await db.delete(workspace)
    await db.commit()
    logger.info(f"Deleted workspace {workspace_id}")
