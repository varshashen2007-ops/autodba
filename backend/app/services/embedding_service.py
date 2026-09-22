"""
Phase 4.1: Embedding Service

Provides a provider-independent interface for generating embeddings.

Current MVP behavior:
- Uses deterministic local embeddings by default.
- No external API calls are required.
- The interface is intentionally provider-agnostic so OpenAI/Gemini
  embeddings can be added later without changing the RAG layer.
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import List


class EmbeddingService:
    """
    Generate deterministic vector embeddings for AutoDBA memory retrieval.

    The MVP implementation uses a lightweight deterministic hashing approach.
    It is NOT intended to match the semantic quality of a production embedding
    model. Its purpose is to establish the RAG architecture without requiring
    an external API key.

    Later providers can implement the same `embed()` interface.
    """

    def __init__(self, dimensions: int = 128) -> None:
        if dimensions <= 0:
            raise ValueError("Embedding dimensions must be positive")

        self.dimensions = dimensions

    def embed(self, text: str) -> List[float]:
        """
        Convert text into a deterministic normalized vector.

        The same input always produces the same embedding.
        """

        if not isinstance(text, str):
            raise TypeError("Embedding input must be a string")

        text = text.strip().lower()

        if not text:
            return [0.0] * self.dimensions

        tokens = self._tokenize(text)

        vector = [0.0] * self.dimensions

        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()

            index = int.from_bytes(digest[:4], "big") % self.dimensions

            # Deterministically choose positive or negative contribution.
            sign = 1.0 if digest[4] % 2 == 0 else -1.0

            vector[index] += sign

        return self._normalize(vector)

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        """
        Tokenize text into simple alphanumeric terms.

        PostgreSQL identifiers, SQL keywords, numbers, and diagnostic terms
        are intentionally retained because they can be useful retrieval signals.
        """

        return re.findall(r"[a-zA-Z0-9_]+", text)

    @staticmethod
    def _normalize(vector: List[float]) -> List[float]:
        """Normalize a vector to unit length."""

        magnitude = math.sqrt(sum(value * value for value in vector))

        if magnitude == 0.0:
            return vector

        return [value / magnitude for value in vector]

    @staticmethod
    def cosine_similarity(
        vector_a: List[float],
        vector_b: List[float],
    ) -> float:
        """
        Calculate cosine similarity between two vectors.

        Returns a value in approximately [-1, 1].
        """

        if len(vector_a) != len(vector_b):
            raise ValueError("Vectors must have the same dimensions")

        magnitude_a = math.sqrt(sum(value * value for value in vector_a))
        magnitude_b = math.sqrt(sum(value * value for value in vector_b))

        if magnitude_a == 0.0 or magnitude_b == 0.0:
            return 0.0

        dot_product = sum(
            a * b for a, b in zip(vector_a, vector_b)
        )

        return dot_product / (magnitude_a * magnitude_b)


def get_embedding_service() -> EmbeddingService:
    """
    Return the default embedding service.

    Kept as a factory so the implementation can later be selected through
    application configuration.
    """

    return EmbeddingService()