from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import OptimizationMemoryModel
from app.schemas.optimization import (
    MemoryListItem,
    MemorySearchResponse,
    OptimizationMemory,
    OptimizationOutcome,
    SimilarCase,
)
from app.services.embedding_service import EmbeddingService


class MemoryService:
    """Persistence and semantic retrieval service for optimization memories."""

    def __init__(self, db: Session):
        self.db = db
        self.embedding_service = EmbeddingService()

    def create_memory(
        self,
        *,
        incident_type: str,
        query_text: str,
        diagnosis: Dict[str, Any],
        recommendation: Dict[str, Any],
        validation: Optional[Dict[str, Any]] = None,
        benchmark: Optional[Dict[str, Any]] = None,
        outcome: Optional[OptimizationOutcome] = None,
        outcome_summary: Optional[str] = None,
        query_fingerprint: Optional[str] = None,
    ) -> OptimizationMemory:
        """Create and persist a historical optimization memory."""

        if query_fingerprint is None:
            query_fingerprint = self._fingerprint(query_text)

        # Benchmark evidence is authoritative for the stored outcome.
        # A caller-supplied outcome is only used when no benchmark evidence
        # exists, preserving support for manually recorded historical cases.
        derived_outcome = self.determine_outcome(
            benchmark=benchmark,
            validation=validation,
        )

        if benchmark is not None:
            outcome = derived_outcome
        elif outcome is None:
            outcome = derived_outcome

        embedding_text = self._build_embedding_text(
            incident_type=incident_type,
            query_text=query_text,
            diagnosis=diagnosis,
            recommendation=recommendation,
            outcome=outcome,
        )

        embedding = self.embedding_service.embed(embedding_text)

        model = OptimizationMemoryModel(
            incident_type=incident_type,
            query_fingerprint=query_fingerprint,
            query_text=query_text,
            diagnosis=diagnosis,
            recommendation=recommendation,
            validation=validation,
            benchmark=benchmark,
            outcome=outcome.value,
            outcome_summary=outcome_summary,
            embedding=embedding,
        )

        self.db.add(model)
        self.db.commit()
        self.db.refresh(model)

        return self._to_memory(model)

    def get_memory(self, memory_id: int) -> Optional[OptimizationMemory]:
        """Retrieve one historical optimization memory by ID."""

        model = self.db.get(OptimizationMemoryModel, memory_id)

        if model is None:
            return None

        return self._to_memory(model)

    def list_memories(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> List[MemoryListItem]:
        """List stored memories in newest-first order."""

        statement = (
            select(OptimizationMemoryModel)
            .order_by(OptimizationMemoryModel.created_at.desc())
            .offset(offset)
            .limit(limit)
        )

        models = self.db.scalars(statement).all()

        return [
            MemoryListItem(
                id=model.id,
                incident_type=model.incident_type,
                query_fingerprint=model.query_fingerprint,
                query_text=model.query_text,
                outcome=OptimizationOutcome(model.outcome),
                outcome_summary=model.outcome_summary,
                created_at=model.created_at,
            )
            for model in models
        ]

    def search_similar(
        self,
        *,
        query: str,
        incident_type: Optional[str] = None,
        limit: int = 5,
        similarity_threshold: float = 0.0,
    ) -> List[SimilarCase]:
        """
        Search historical memories using cosine similarity.

        Incident type is a ranking preference rather than a hard filter.
        This allows semantically similar cases to be retrieved even when
        the current deterministic incident type is unknown.
        """

        query_embedding = self.embedding_service.embed(query)

        statement = select(OptimizationMemoryModel)
        models = self.db.scalars(statement).all()

        scored: List[tuple[float, OptimizationMemoryModel]] = []

        for model in models:
            similarity = self.embedding_service.cosine_similarity(
                query_embedding,
                model.embedding,
            )

            if similarity >= similarity_threshold:
                type_bonus = (
                    0.05
                    if incident_type
                    and incident_type != "unknown"
                    and model.incident_type == incident_type
                    else 0.0
                )

                ranked_score = min(similarity + type_bonus, 1.0)
                scored.append((ranked_score, model))

        scored.sort(key=lambda item: item[0], reverse=True)

        return [
            self._to_similar_case(
                model=model,
                similarity=similarity,
            )
            for similarity, model in scored[:limit]
        ]

    def search(
        self,
        request,
    ) -> MemorySearchResponse:
        """Execute a semantic memory search from a request model."""

        results = self.search_similar(
            query=request.query,
            incident_type=request.incident_type,
            limit=request.limit,
            similarity_threshold=request.similarity_threshold,
        )

        return MemorySearchResponse(
            query=request.query,
            results=results,
            total=len(results),
        )

    @staticmethod
    @staticmethod
    def determine_outcome(
        *,
        benchmark: Optional[Dict[str, Any]],
        validation: Optional[Dict[str, Any]],
    ) -> OptimizationOutcome:
        """Determine optimization outcome from authoritative benchmark evidence.

        Outcome rules:
          - No benchmark evidence -> NOT_BENCHMARKED
          - Explicit benchmark failure -> FAILED
          - Negative runtime improvement -> REGRESSION
          - Zero runtime improvement -> NO_IMPROVEMENT
          - Positive runtime improvement -> SUCCESS

        Validation evidence is only used to detect an explicit validation
        failure when no completed benchmark result is available.
        """
        if not benchmark:
            if validation and validation.get("hypopg_validated") is False:
                return OptimizationOutcome.FAILED
            return OptimizationOutcome.NOT_BENCHMARKED

        status = str(benchmark.get("status", "")).lower()
        if status in {"failed", "blocked"}:
            return OptimizationOutcome.FAILED

        runtime_improvement = benchmark.get("runtime_improvement_percent")

        if runtime_improvement is None:
            return OptimizationOutcome.NOT_BENCHMARKED

        if runtime_improvement < 0:
            return OptimizationOutcome.REGRESSION

        if runtime_improvement == 0:
            return OptimizationOutcome.NO_IMPROVEMENT

        return OptimizationOutcome.SUCCESS

    @staticmethod
    def _fingerprint(query_text: str) -> str:
        normalized = " ".join(query_text.strip().lower().split())
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    @staticmethod
    def _build_embedding_text(
        *,
        incident_type: str,
        query_text: str,
        diagnosis: Dict[str, Any],
        recommendation: Dict[str, Any],
        outcome: OptimizationOutcome,
    ) -> str:
        return "\n".join(
            [
                f"incident_type: {incident_type}",
                f"query: {query_text}",
                f"diagnosis: {diagnosis}",
                f"recommendation: {recommendation}",
                f"outcome: {outcome.value}",
            ]
        )

    @staticmethod
    def _to_memory(
        model: OptimizationMemoryModel,
    ) -> OptimizationMemory:
        return OptimizationMemory(
            id=model.id,
            incident_type=model.incident_type,
            query_fingerprint=model.query_fingerprint,
            query_text=model.query_text,
            diagnosis=model.diagnosis,
            recommendation=model.recommendation,
            validation=model.validation,
            benchmark=model.benchmark,
            outcome=OptimizationOutcome(model.outcome),
            outcome_summary=model.outcome_summary,
            embedding=model.embedding,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def _to_similar_case(
        *,
        model: OptimizationMemoryModel,
        similarity: float,
    ) -> SimilarCase:
        return SimilarCase(
            memory_id=model.id,
            incident_type=model.incident_type,
            query_text=model.query_text,
            outcome=OptimizationOutcome(model.outcome),
            outcome_summary=model.outcome_summary,
            similarity=max(0.0, min(float(similarity), 1.0)),
            diagnosis=model.diagnosis,
            recommendation=model.recommendation,
            benchmark=model.benchmark,
        )


def get_memory_service(db: Session) -> MemoryService:
    return MemoryService(db)
