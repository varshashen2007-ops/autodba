"""
Phase 4 Candidate Selector: Research Selection Policies & Outcome-Aware Ranking

Implements the three experimental candidate selection policies:
  A. Planner-Only Baseline: Selects the existing Phase 1 baseline candidate directly.
  B. Similarity-Based Selection: Ranks candidates using similarity support from TRAIN history.
  C. Outcome-Aware Selection: Ranks candidates using verified empirical benchmark outcomes.

LEAKAGE & SAFETY BOUNDARIES:
  - All three policies operate strictly on the existing Phase 1 candidate pool.
  - Historical memory NEVER creates or synthesizes new candidates.
  - Policy C only uses historical cases where provenance == MEASURED, is_verified == True,
    and verification_state == VERIFIED_MEASURED.
  - When verified evidence is absent, Policy C falls back deterministically to Policy A.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import math
import re
from typing import Any, Dict, List, Optional, Tuple

from .case_schema import OptimizationCase, CaseProvenance


class SelectionPolicy(str, Enum):
    """Candidate selection policy under evaluation."""
    PLANNER_ONLY = "planner_only"
    SIMILARITY = "similarity"
    OUTCOME_AWARE = "outcome_aware"


def canonical_candidate_key(
    table: str,
    index_method: str,
    columns: List[str],
) -> Tuple[str, str, Tuple[str, ...]]:
    """
    Constructs the canonical index identification key:
    (table_name_lower, index_method_lower, tuple_of_ordered_columns_lower)

    Scope: AutoDBA generates standard single- and multi-column B-tree secondary indexes.
    Preserves exact column ordering for B-tree index prefix semantics.
    """
    tbl = (table or "").strip().lower()
    method = (index_method or "btree").strip().lower()
    cols = tuple(c.strip().lower() for c in columns if c and c.strip())
    return (tbl, method, cols)


def extract_candidate_key(candidate: Any) -> Tuple[str, str, Tuple[str, ...]]:
    """Extracts canonical candidate key from CandidateEvaluation or dict."""
    if hasattr(candidate, "recommendation"):
        rec = candidate.recommendation
        table = getattr(rec, "target_table", getattr(rec, "table", "")) or ""
        cols = getattr(rec, "target_columns", getattr(rec, "columns", [])) or []
        method = getattr(rec, "index_method", "btree") or "btree"
    elif isinstance(candidate, dict):
        rec = candidate.get("recommendation", candidate)
        table = rec.get("table", rec.get("target_table", ""))
        cols = rec.get("columns", rec.get("target_columns", []))
        method = rec.get("index_method", "btree")
    else:
        table, cols, method = "", [], "btree"

    return canonical_candidate_key(str(table), str(method), list(cols))


def extract_case_key(case: OptimizationCase) -> Tuple[str, str, Tuple[str, ...]]:
    """Extracts canonical index key from a historical OptimizationCase."""
    rec = case.recommendation
    table = rec.table or ""
    cols = rec.columns or []
    method = rec.index_method or "btree"
    return canonical_candidate_key(table, method, cols)


def get_candidate_hypopg_improvement(candidate: Any) -> float:
    """Extracts HypoPG cost improvement percent from candidate."""
    if hasattr(candidate, "validation") and candidate.validation:
        val = candidate.validation
        if hasattr(val, "cost_improvement_percent"):
            return float(val.cost_improvement_percent or 0.0)
        if hasattr(val, "plan_comparison") and val.plan_comparison:
            return float(val.plan_comparison.cost_improvement_percent or 0.0)
    elif isinstance(candidate, dict):
        val = candidate.get("validation", {})
        if isinstance(val, dict):
            if "cost_improvement_percent" in val:
                return float(val["cost_improvement_percent"] or 0.0)
            if "improvement_pct" in val:
                return float(val["improvement_pct"] or 0.0)
    return 0.0


def compute_token_hash_similarity(text1: str, text2: str) -> float:
    """
    Computes cosine similarity between two texts using deterministic SHA-256 token hashing.
    Matches the baseline representation in BaselineRetrievalMethods.
    """
    dims = 128
    v1 = [0.0] * dims
    v2 = [0.0] * dims

    tokens1 = re.findall(r'[a-zA-Z0-9_]+', text1.lower())
    for t in tokens1:
        th = int(hashlib.sha256(t.encode("utf-8")).hexdigest()[:8], 16)
        v1[th % dims] += 1.0 if (th & 1) == 0 else -1.0

    tokens2 = re.findall(r'[a-zA-Z0-9_]+', text2.lower())
    for t in tokens2:
        th = int(hashlib.sha256(t.encode("utf-8")).hexdigest()[:8], 16)
        v2[th % dims] += 1.0 if (th & 1) == 0 else -1.0

    mag1 = math.sqrt(sum(x * x for x in v1))
    mag2 = math.sqrt(sum(x * x for x in v2))

    if mag1 == 0.0 or mag2 == 0.0:
        return 0.0

    dot = sum(a * b for a, b in zip(v1, v2))
    return max(0.0, min(1.0, dot / (mag1 * mag2)))


@dataclass
class CandidateScore:
    """Structured evaluation score for a candidate recommendation."""
    candidate_id: str
    canonical_key: Tuple[str, str, Tuple[str, ...]]
    is_baseline: bool
    hypopg_cost_improvement: float
    similarity_support: float
    outcome_support: float
    composite_score: float
    matching_history_count: int
    eligible_measured_count: int


@dataclass
class SelectionResult:
    """Auditable result of candidate selection across policies."""
    policy: SelectionPolicy
    selected_candidate_id: str
    selected_candidate: Any
    candidate_scores: List[CandidateScore]
    historical_support: Dict[str, Any]
    fallback_used: bool = False
    fallback_reason: Optional[str] = None
    lambda_reg: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "policy": self.policy.value,
            "selected_candidate_id": self.selected_candidate_id,
            "fallback_used": self.fallback_used,
            "fallback_reason": self.fallback_reason,
            "lambda_reg": self.lambda_reg,
            "historical_support": self.historical_support,
            "candidate_scores": [
                {
                    "candidate_id": cs.candidate_id,
                    "canonical_key": f"{cs.canonical_key[0]}({','.join(cs.canonical_key[2])})",
                    "is_baseline": cs.is_baseline,
                    "hypopg_cost_improvement": round(cs.hypopg_cost_improvement, 4),
                    "similarity_support": round(cs.similarity_support, 4),
                    "outcome_support": round(cs.outcome_support, 4),
                    "composite_score": round(cs.composite_score, 4),
                    "matching_history_count": cs.matching_history_count,
                    "eligible_measured_count": cs.eligible_measured_count,
                }
                for cs in self.candidate_scores
            ],
        }


class CandidateSelector:
    """
    Research candidate selection engine evaluating Policy A, B, and C.
    """

    def __init__(
        self,
        alpha: float = 1.0,
        beta: float = 1.0,
        lambda_reg: float = 1.0,
    ):
        """
        Initialize selector hyperparameters:
          alpha: Weight for similarity support in Policy B.
          beta: Weight for empirical outcome support in Policy C.
          lambda_reg: Asymmetric regression penalty multiplier (>= 1.0) in Policy C.
        """
        self.alpha = alpha
        self.beta = beta
        self.lambda_reg = lambda_reg

    def select_planner_only(
        self,
        candidates: List[Any],
    ) -> SelectionResult:
        """
        POLICY A: Planner-Only Baseline
        Selects the exact Phase 1 baseline candidate (is_baseline == True).
        Uses zero historical memory, zero historical outcomes, and zero similarity scores.
        """
        if not candidates:
            raise ValueError("Candidate pool is empty; cannot execute planner-only selection.")

        baseline_cands = []
        for c in candidates:
            is_b = getattr(c, "is_baseline", False) if hasattr(c, "is_baseline") else c.get("is_baseline", False)
            if is_b:
                baseline_cands.append(c)

        if len(baseline_cands) != 1:
            raise ValueError(
                f"Expected exactly one baseline candidate (is_baseline==True), found {len(baseline_cands)}."
            )

        chosen = baseline_cands[0]
        chosen_id = getattr(chosen, "candidate_id", chosen.get("candidate_id", "baseline") if isinstance(chosen, dict) else "baseline")

        scores = []
        for c in candidates:
            cid = getattr(c, "candidate_id", c.get("candidate_id", "unknown") if isinstance(c, dict) else "unknown")
            is_b = getattr(c, "is_baseline", False) if hasattr(c, "is_baseline") else (c.get("is_baseline", False) if isinstance(c, dict) else False)
            key = extract_candidate_key(c)
            hypo_cost = get_candidate_hypopg_improvement(c)
            scores.append(
                CandidateScore(
                    candidate_id=str(cid),
                    canonical_key=key,
                    is_baseline=bool(is_b),
                    hypopg_cost_improvement=hypo_cost,
                    similarity_support=0.0,
                    outcome_support=0.0,
                    composite_score=1.0 if is_b else 0.0,
                    matching_history_count=0,
                    eligible_measured_count=0,
                )
            )

        return SelectionResult(
            policy=SelectionPolicy.PLANNER_ONLY,
            selected_candidate_id=str(chosen_id),
            selected_candidate=chosen,
            candidate_scores=scores,
            historical_support={"source": "none", "cases_considered": 0},
            fallback_used=False,
            fallback_reason=None,
            lambda_reg=self.lambda_reg,
        )

    def select_similarity(
        self,
        query_text: str,
        candidates: List[Any],
        history_cases: List[OptimizationCase],
    ) -> SelectionResult:
        """
        POLICY B: Similarity-Based Retrieval
        Ranks candidates by combining HypoPG cost improvement with similarity support
        from matching historical cases in the TRAIN partition.
        Does NOT use historical success/regression outcomes.
        """
        if not candidates:
            raise ValueError("Candidate pool is empty; cannot execute similarity selection.")

        # If no history cases provided, fall back to Policy A
        if not history_cases:
            res = self.select_planner_only(candidates)
            res.policy = SelectionPolicy.SIMILARITY
            res.fallback_used = True
            res.fallback_reason = "No historical cases available in training corpus."
            return res

        # Map candidate keys to candidates
        cand_by_key = {}
        for c in candidates:
            k = extract_candidate_key(c)
            cand_by_key[k] = c

        # Compute similarity and aggregate support per candidate
        sim_support: Dict[Tuple[str, str, Tuple[str, ...]], float] = {k: 0.0 for k in cand_by_key}
        hist_count: Dict[Tuple[str, str, Tuple[str, ...]], int] = {k: 0 for k in cand_by_key}

        for h in history_cases:
            h_key = extract_case_key(h)
            if h_key in cand_by_key:
                sim = compute_token_hash_similarity(query_text, h.query.text)
                sim_support[h_key] += sim
                hist_count[h_key] += 1

        total_matching_cases = sum(hist_count.values())
        if total_matching_cases == 0:
            res = self.select_planner_only(candidates)
            res.policy = SelectionPolicy.SIMILARITY
            res.fallback_used = True
            res.fallback_reason = "No historical cases in training corpus matched candidate index definitions."
            return res

        scores: List[CandidateScore] = []
        for c in candidates:
            cid = getattr(c, "candidate_id", c.get("candidate_id", "unknown") if isinstance(c, dict) else "unknown")
            is_b = getattr(c, "is_baseline", False) if hasattr(c, "is_baseline") else (c.get("is_baseline", False) if isinstance(c, dict) else False)
            key = extract_candidate_key(c)
            hypo_cost = get_candidate_hypopg_improvement(c)
            s_sim = sim_support.get(key, 0.0)
            comp_score = hypo_cost + (self.alpha * s_sim)

            scores.append(
                CandidateScore(
                    candidate_id=str(cid),
                    canonical_key=key,
                    is_baseline=bool(is_b),
                    hypopg_cost_improvement=hypo_cost,
                    similarity_support=s_sim,
                    outcome_support=0.0,
                    composite_score=comp_score,
                    matching_history_count=hist_count.get(key, 0),
                    eligible_measured_count=0,
                )
            )

        # Deterministic ranking:
        # 1. Highest composite_score
        # 2. Highest hypopg_cost_improvement
        # 3. is_baseline == True
        # 4. Lexicographical candidate_id
        scores.sort(
            key=lambda x: (
                x.composite_score,
                x.hypopg_cost_improvement,
                1 if x.is_baseline else 0,
                x.candidate_id,
            ),
            reverse=True,
        )

        chosen_score = scores[0]
        chosen_cand = [c for c in candidates if str(getattr(c, "candidate_id", c.get("candidate_id") if isinstance(c, dict) else "")) == chosen_score.candidate_id][0]

        return SelectionResult(
            policy=SelectionPolicy.SIMILARITY,
            selected_candidate_id=chosen_score.candidate_id,
            selected_candidate=chosen_cand,
            candidate_scores=scores,
            historical_support={
                "source": "train_similarity",
                "total_history_cases": len(history_cases),
                "matching_history_cases": total_matching_cases,
                "alpha": self.alpha,
            },
            fallback_used=False,
            fallback_reason=None,
            lambda_reg=self.lambda_reg,
        )

    def select_outcome_aware(
        self,
        query_text: str,
        candidates: List[Any],
        history_cases: List[OptimizationCase],
    ) -> SelectionResult:
        """
        POLICY C: Outcome-Aware Selection
        Ranks candidates by combining HypoPG cost improvement with empirical outcome
        support from verified measured historical benchmark cases (provenance==MEASURED,
        is_verified==True, verification_state==VERIFIED_MEASURED).
        """
        if not candidates:
            raise ValueError("Candidate pool is empty; cannot execute outcome-aware selection.")

        # Filter strictly to eligible verified measured cases
        eligible_cases = []
        for h in (history_cases or []):
            prov = getattr(h, "provenance", "")
            prov_val = (prov.value if hasattr(prov, "value") else str(prov)).lower()
            is_v = bool(getattr(h, "is_verified", False))
            v_state = getattr(h, "verification_state", "")
            v_state_val = (v_state.value if hasattr(v_state, "value") else str(v_state)).lower()

            if (prov_val in ("measured", "real_measured")) and is_v and (v_state_val in ("verified_measured", "verified")):
                eligible_cases.append(h)

        # If no eligible measured cases exist in training history, fall back to Policy A
        if not eligible_cases:
            res = self.select_planner_only(candidates)
            res.policy = SelectionPolicy.OUTCOME_AWARE
            res.fallback_used = True
            res.fallback_reason = "No eligible verified measured historical evidence in training corpus."
            return res

        cand_by_key = {extract_candidate_key(c): c for c in candidates}

        outcome_support: Dict[Tuple[str, str, Tuple[str, ...]], float] = {k: 0.0 for k in cand_by_key}
        hist_count: Dict[Tuple[str, str, Tuple[str, ...]], int] = {k: 0 for k in cand_by_key}
        measured_count: Dict[Tuple[str, str, Tuple[str, ...]], int] = {k: 0 for k in cand_by_key}

        for h in eligible_cases:
            h_key = extract_case_key(h)
            if h_key not in cand_by_key:
                continue

            t_before = h.measured_outcome.before_runtime_ms
            t_after = h.measured_outcome.after_runtime_ms

            # Exclude invalid or missing timing measurements
            if t_before is None or t_after is None or t_before <= 0.0:
                continue

            delta = (t_before - t_after) / t_before
            sim = compute_token_hash_similarity(query_text, h.query.text)

            if delta >= 0:
                contribution = sim * delta
            else:
                contribution = sim * delta * self.lambda_reg

            outcome_support[h_key] += contribution
            hist_count[h_key] += 1
            measured_count[h_key] += 1

        total_measured_matching = sum(measured_count.values())
        if total_measured_matching == 0:
            res = self.select_planner_only(candidates)
            res.policy = SelectionPolicy.OUTCOME_AWARE
            res.fallback_used = True
            res.fallback_reason = "No verified measured historical cases matched candidate index definitions."
            return res

        scores: List[CandidateScore] = []
        for c in candidates:
            cid = getattr(c, "candidate_id", c.get("candidate_id", "unknown") if isinstance(c, dict) else "unknown")
            is_b = getattr(c, "is_baseline", False) if hasattr(c, "is_baseline") else (c.get("is_baseline", False) if isinstance(c, dict) else False)
            key = extract_candidate_key(c)
            hypo_cost = get_candidate_hypopg_improvement(c)
            s_out = outcome_support.get(key, 0.0)
            comp_score = hypo_cost + (self.beta * s_out)

            scores.append(
                CandidateScore(
                    candidate_id=str(cid),
                    canonical_key=key,
                    is_baseline=bool(is_b),
                    hypopg_cost_improvement=hypo_cost,
                    similarity_support=0.0,
                    outcome_support=s_out,
                    composite_score=comp_score,
                    matching_history_count=hist_count.get(key, 0),
                    eligible_measured_count=measured_count.get(key, 0),
                )
            )

        # Deterministic ranking:
        # 1. Highest composite_score
        # 2. Highest outcome_support
        # 3. Highest hypopg_cost_improvement
        # 4. is_baseline == True
        # 5. Lexicographical candidate_id
        scores.sort(
            key=lambda x: (
                x.composite_score,
                x.outcome_support,
                x.hypopg_cost_improvement,
                1 if x.is_baseline else 0,
                x.candidate_id,
            ),
            reverse=True,
        )

        chosen_score = scores[0]
        chosen_cand = [c for c in candidates if str(getattr(c, "candidate_id", c.get("candidate_id") if isinstance(c, dict) else "")) == chosen_score.candidate_id][0]

        return SelectionResult(
            policy=SelectionPolicy.OUTCOME_AWARE,
            selected_candidate_id=chosen_score.candidate_id,
            selected_candidate=chosen_cand,
            candidate_scores=scores,
            historical_support={
                "source": "train_verified_measured",
                "total_history_cases": len(history_cases),
                "eligible_measured_cases": len(eligible_cases),
                "matching_measured_cases": total_measured_matching,
                "beta": self.beta,
                "lambda_reg": self.lambda_reg,
            },
            fallback_used=False,
            fallback_reason=None,
            lambda_reg=self.lambda_reg,
        )
