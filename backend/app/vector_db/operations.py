import uuid

from app.ai.embedding import embedding_provider
from app.core.logging import logger
from app.vector_db.client import chroma_manager


async def query_vector_db(
    workspace_id: uuid.UUID,
    query_text: str,
    n_results: int = 5,
    document_id: uuid.UUID | None = None,
) -> list[dict]:
    """
    Queries ChromaDB for semantically similar text chunks in a workspace.
    Optionally filters search results to a specific document.
    """
    logger.info(
        f"Performing vector search in workspace {workspace_id} for query: '{query_text}'"
    )

    try:
        # 1. Embed query
        query_vector = await embedding_provider.get_embedding(query_text)

        # 2. Get Chroma DB collection
        chroma_client = chroma_manager.get_client()
        collection_name = f"workspace_{workspace_id.hex}"

        # If collection doesn't exist, return empty list (no documents uploaded yet)
        existing_collections = [col.name for col in chroma_client.list_collections()]
        if collection_name not in existing_collections:
            logger.warning(
                f"Vector collection {collection_name} does not exist yet. Returning 0 matches."
            )
            return []

        collection = chroma_client.get_collection(name=collection_name)

        # 3. Formulate filters
        metadata_filter = {}
        if document_id:
            metadata_filter["document_id"] = str(document_id)

        # 4. Execute query
        results = collection.query(
            query_embeddings=[query_vector],
            n_results=n_results,
            where=metadata_filter if metadata_filter else None,
        )

        # 5. Parse results into structured response
        formatted_matches = []
        if not results or "ids" not in results or not results["ids"]:
            return []

        # Chroma returns lists of lists since it supports batch queries
        ids = results["ids"][0]
        documents = results["documents"][0]
        metadatas = results["metadatas"][0]
        # Distances list can be missing if there are no matches
        distances = results.get("distances", [[]])[0]

        for i in range(len(ids)):
            distance = distances[i] if i < len(distances) else 0.0
            # Convert L2 distance to a normalized similarity score: 1 / (1 + distance)
            # Higher distance = lower score
            similarity_score = 1.0 / (1.0 + distance)

            formatted_matches.append(
                {
                    "chunk_id": ids[i],
                    "text": documents[i],
                    "document_id": uuid.UUID(metadatas[i]["document_id"]),
                    "workspace_id": uuid.UUID(metadatas[i]["workspace_id"]),
                    "page": metadatas[i].get("page"),
                    "score": round(similarity_score, 4),
                }
            )

        logger.info(
            f"Vector search returned {len(formatted_matches)} semantic matches."
        )
        return formatted_matches

    except Exception as e:
        logger.exception(f"Semantic search query failed: {e}")
        # Return empty list on failure to prevent system crash
        return []
