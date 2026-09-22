"""
Phase 4.1: Retrieval-Augmented Generation Service

Retrieves historically similar AutoDBA optimization cases and packages
them as structured context for the intelligence layer.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.schemas.optimization import RAGContext
from app.services.memory_service import MemoryService


class RAGService:
    """Retrieval layer for historical database optimization cases."""

    DEFAULT_LIMIT = 5
    DEFAULT_SIMILARITY_THRESHOLD = 0.20

    def __init__(
        self,
        db: Session,
        memory_service: Optional[MemoryService] = None,
    ) -> None:
        self.memory_service = memory_service or MemoryService(db)

    def retrieve(
        self,
        *,
        query: str,
        incident_type: str,
        limit: int = DEFAULT_LIMIT,
        similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
    ) -> RAGContext:
        """
        Retrieve historically similar optimization cases.

        Retrieval is advisory context only. It does not modify the database,
        approve recommendations, or execute remediation.
        """

        similar_cases = self.memory_service.search_similar(
            query=query,
            incident_type=incident_type,
            limit=limit,
            similarity_threshold=similarity_threshold,
        )

        return RAGContext(
            query=query,
            incident_type=incident_type,
            similar_cases=similar_cases,
            retrieval_count=len(similar_cases),
            retrieval_threshold=similarity_threshold,
        )