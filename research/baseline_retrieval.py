"""
Baseline retrieval methods for the AutoDBA research evaluation harness.

Implements deterministic retrieval baselines operating strictly on a provided
historical (TRAIN) case corpus:
1. Current AutoDBA token-hash retrieval (deterministic bag-of-words token hashing)
2. Lexical retrieval (TF-IDF vector matching)
3. Dense token-hash retrieval (unthresholded)
4. Hybrid retrieval (lexical + dense)
5. Outcome-aware historical re-ranking (ranks retrieved history by past benchmark outcomes)

LEAKAGE SAFETY GUARANTEE:
The retriever searches EXCLUSIVELY within the provided historical corpus.
Test cases are NEVER indexed in the retrieval pool.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import hashlib
import math
import re
from typing import Any, Dict, List, Optional, Tuple

from .case_schema import OptimizationCase, QueryInfo, IncidentType


def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """Compute cosine similarity between two float vectors."""
    if len(vec1) != len(vec2):
        raise ValueError("Vectors must have the same length")

    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    magnitude1 = math.sqrt(sum(a * a for a in vec1))
    magnitude2 = math.sqrt(sum(b * b for b in vec2))

    if magnitude1 == 0.0 or magnitude2 == 0.0:
        return 0.0

    return dot_product / (magnitude1 * magnitude2)


def simple_tokenize(text: str) -> List[str]:
    """Simple alphanumeric tokenizer."""
    return re.findall(r'[a-zA-Z0-9_]+', text.lower())


def compute_tfidf_vector(
    text: str,
    vocabulary: Dict[str, int],
    idf_weights: Dict[str, float],
) -> List[float]:
    """Compute a TF-IDF vector for a text string against a fixed vocabulary."""
    tokens = simple_tokenize(text)
    tf_counts = Counter(tokens)
    total_terms = len(tokens)

    vector = [0.0] * len(vocabulary)
    for term, count in tf_counts.items():
        if term in vocabulary:
            idx = vocabulary[term]
            tf = count / total_terms if total_terms > 0 else 0.0
            vector[idx] = tf * idf_weights.get(term, 1.0)

    mag = math.sqrt(sum(v * v for v in vector))
    return [v / mag for v in vector] if mag > 0 else vector


@dataclass
class RetrievalResult:
    """A historical optimization case retrieved for a query."""
    case_id: str
    similarity_score: float
    case: OptimizationCase
    retrieval_method: str
    rank: int


class BaselineRetrievalMethods:
    """
    Retrieval engine indexing strictly historical (TRAIN) cases.
    """

    def __init__(self, history_cases: List[OptimizationCase]):
        """
        Initialize the retrieval index with historical (TRAIN) cases only.
        """
        self.history_cases = list(history_cases)
        self.case_by_id = {c.case_id: c for c in self.history_cases}
        self._build_vocabulary()
        self._compute_case_vectors()

    def _build_vocabulary(self) -> None:
        """Build vocabulary from the training history corpus only."""
        all_tokens = []
        for case in self.history_cases:
            all_tokens.extend(simple_tokenize(case.query.text))
        word_counts = Counter(all_tokens)
        self.vocabulary = {
            word: idx for idx, (word, _) in enumerate(word_counts.most_common(1000))
        }
        total_docs = max(len(self.history_cases), 1)
        self.idf_weights = {}
        for word in self.vocabulary:
            doc_count = sum(1 for c in self.history_cases if word in simple_tokenize(c.query.text))
            self.idf_weights[word] = math.log(total_docs / (doc_count + 1)) + 1.0

    def _compute_case_vectors(self) -> None:
        """Pre-compute TF-IDF vectors for the training history corpus."""
        self.case_tfidf_vectors = {}
        for case in self.history_cases:
            self.case_tfidf_vectors[case.case_id] = compute_tfidf_vector(
                case.query.text, self.vocabulary, self.idf_weights
            )

    def _get_token_hash_vector(self, text: str) -> List[float]:
        """
        Deterministic 128-dimensional token-hash vector representation.

        Note: This is a deterministic bag-of-words token-hash baseline, NOT a
        semantic neural/LLM embedding. Uses SHA-256 token hashing for cross-process
        reproducibility.
        """
        if not text:
            return [0.0] * 128
        dims = 128
        vector = [0.0] * dims
        for token in simple_tokenize(text):
            token_hash = int(hashlib.sha256(token.encode("utf-8")).hexdigest()[:8], 16)
            vector[token_hash % dims] += 1.0 if (token_hash & 1) == 0 else -1.0
        mag = math.sqrt(sum(v * v for v in vector))
        return [v / mag for v in vector] if mag > 0 else vector

    def current_autodba_retrieval(
        self,
        query_case: OptimizationCase,
        limit: int = 5,
        similarity_threshold: float = 0.2,
    ) -> List[RetrievalResult]:
        """
        Simulate AutoDBA's embedding-based retrieval against the training history.
        Enforces strict target-case exclusion and template isolation.
        """
        query_vector = self._get_token_hash_vector(query_case.query.text)
        results = []

        for case in self.history_cases:
            # Safety guards: Never retrieve self, and never retrieve same template
            if case.case_id == query_case.case_id:
                continue
            if case.template_hash == query_case.template_hash:
                continue

            case_vector = self._get_token_hash_vector(case.embedding_text)
            sim = cosine_similarity(query_vector, case_vector)

            # Boost if incident types match (matching application logic)
            if case.incident_type == query_case.incident_type:
                sim = min(1.0, sim + 0.05)

            if sim >= similarity_threshold:
                results.append(
                    RetrievalResult(
                        case_id=case.case_id,
                        similarity_score=sim,
                        case=case,
                        retrieval_method="current_autodba",
                        rank=0,
                    )
                )

        results.sort(key=lambda x: x.similarity_score, reverse=True)
        for i, r in enumerate(results[:limit]):
            r.rank = i + 1
        return results[:limit]

    def lexical_retrieval(
        self,
        query_case: OptimizationCase,
        limit: int = 5,
    ) -> List[RetrievalResult]:
        """Lexical TF-IDF retrieval against the training history."""
        qv = compute_tfidf_vector(query_case.query.text, self.vocabulary, self.idf_weights)
        results = []

        for case in self.history_cases:
            if case.case_id == query_case.case_id:
                continue
            if case.template_hash == query_case.template_hash:
                continue

            cv = self.case_tfidf_vectors[case.case_id]
            sim = cosine_similarity(qv, cv)
            results.append(
                RetrievalResult(
                    case_id=case.case_id,
                    similarity_score=sim,
                    case=case,
                    retrieval_method="lexical",
                    rank=0,
                )
            )

        results.sort(key=lambda x: x.similarity_score, reverse=True)
        for i, r in enumerate(results[:limit]):
            r.rank = i + 1
        return results[:limit]

    def dense_retrieval(
        self,
        query_case: OptimizationCase,
        limit: int = 5,
    ) -> List[RetrievalResult]:
        """Dense token-hash retrieval with threshold = 0.0."""
        return self.current_autodba_retrieval(query_case, limit=limit, similarity_threshold=0.0)

    def hybrid_retrieval(
        self,
        query_case: OptimizationCase,
        limit: int = 5,
        alpha: float = 0.5,
    ) -> List[RetrievalResult]:
        """Hybrid combination of dense token-hash and lexical TF-IDF scores."""
        dr = self.dense_retrieval(query_case, limit=len(self.history_cases))
        lr = self.lexical_retrieval(query_case, limit=len(self.history_cases))

        scores: Dict[str, float] = defaultdict(float)
        for r in dr:
            scores[r.case_id] += alpha * r.similarity_score
        for r in lr:
            scores[r.case_id] += (1.0 - alpha) * r.similarity_score

        results = []
        for cid, sc in scores.items():
            case = self.case_by_id[cid]
            results.append(
                RetrievalResult(
                    case_id=cid,
                    similarity_score=sc,
                    case=case,
                    retrieval_method="hybrid",
                    rank=0,
                )
            )

        results.sort(key=lambda x: x.similarity_score, reverse=True)
        for i, r in enumerate(results[:limit]):
            r.rank = i + 1
        return results[:limit]

    def outcome_aware_reranking(
        self,
        base_results: List[RetrievalResult],
        query_case: OptimizationCase,
        limit: int = 5,
    ) -> List[RetrievalResult]:
        """
        Re-rank retrieved historical cases based on their verified historical outcomes.
        Only operates on historical cases retrieved from the training pool.
        """
        reranked = []
        for r in base_results:
            bonus = 0.0
            if r.case.measured_outcome.success:
                bonus = 0.2
            elif r.case.measured_outcome.regression:
                bonus = -0.2

            reranked.append(
                RetrievalResult(
                    case_id=r.case_id,
                    similarity_score=r.similarity_score + bonus,
                    case=r.case,
                    retrieval_method="outcome_aware_reranking",
                    rank=0,
                )
            )

        reranked.sort(key=lambda x: x.similarity_score, reverse=True)
        for i, r in enumerate(reranked[:limit]):
            r.rank = i + 1
        return reranked[:limit]


def retrieve_with_baseline(
    method_name: str,
    query_case: OptimizationCase,
    history_cases: List[OptimizationCase],
    limit: int = 5,
    **kwargs,
) -> List[RetrievalResult]:
    """Functional interface to retrieve historical cases using a baseline method."""
    retriever = BaselineRetrievalMethods(history_cases)
    if method_name == "current_autodba":
        return retriever.current_autodba_retrieval(
            query_case, limit, kwargs.get("similarity_threshold", 0.2)
        )
    elif method_name == "lexical":
        return retriever.lexical_retrieval(query_case, limit)
    elif method_name == "dense":
        return retriever.dense_retrieval(query_case, limit)
    elif method_name == "hybrid":
        return retriever.hybrid_retrieval(query_case, limit, kwargs.get("alpha", 0.5))
    elif method_name == "outcome_aware_reranking":
        base = retriever.current_autodba_retrieval(query_case, limit * 2, similarity_threshold=0.0)
        return retriever.outcome_aware_reranking(base, query_case, limit)
    else:
        raise ValueError(f"Unknown retrieval method: {method_name}")
