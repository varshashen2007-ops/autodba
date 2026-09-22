"""
Pydantic schemas for Phase 2 plan analysis results.

These models describe:
  - PlanNode       : a single node extracted from a PostgreSQL EXPLAIN JSON tree
  - BottleneckType : enumeration of detectable performance issues
  - Severity       : finding severity levels
  - Confidence     : confidence in a bottleneck finding
  - BottleneckFinding : a single detected potential issue
  - PlanAnalysisResponse : the complete output of analyzing one EXPLAIN plan
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class Severity(str, Enum):
    """Severity of a bottleneck finding."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Confidence(str, Enum):
    """Confidence level in a bottleneck finding.

    - HIGH   : strong evidence from the plan; very likely a real problem
    - MEDIUM : heuristic match; probable but requires judgment
    - LOW    : weak signal; worth noting but may not be actionable
    """
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class BottleneckType(str, Enum):
    """Categories of detectable query performance issues."""
    MISSING_INDEX = "missing_index"
    EXPENSIVE_SORT = "expensive_sort"
    EXPENSIVE_NESTED_LOOP = "expensive_nested_loop"
    LARGE_ROW_ESTIMATE = "large_row_estimate"
    FILTERED_SEQ_SCAN = "filtered_seq_scan"


class IndexMethod(str, Enum):
    """Supported PostgreSQL index access methods for HypoPG."""
    BTREE = "btree"
    HASH = "hash"
    GIN = "gin"
    GIST = "gist"
    BRIN = "brin"


class ValidationVerdict(str, Enum):
    """Verdict of HypoPG counterfactual plan validation."""
    VALIDATED = "validated"          # Hypothetical plan demonstrates meaningful cost improvement
    NO_IMPROVEMENT = "no_improvement"  # Hypothetical plan has equal cost or improvement < threshold
    REGRESSION = "regression"        # Hypothetical plan is more expensive than original plan
    INVALID_CANDIDATE = "invalid_candidate"  # Candidate index definition cannot be safely validated
    ERROR = "error"                  # Validation failed due to query execution or database error


# ---------------------------------------------------------------------------
# Plan node
# ---------------------------------------------------------------------------

class PlanNode(BaseModel):
    """Structured representation of one node in a PostgreSQL execution plan tree.

    Fields are all optional because PostgreSQL plan JSON only includes fields
    relevant to the specific node type.  Missing fields are represented as None
    rather than raising validation errors.
    """

    node_type: str = Field(..., description="PostgreSQL plan node type (e.g. 'Seq Scan', 'Sort')")
    relation_name: Optional[str] = Field(None, description="Table/relation name (for scan nodes)")
    alias: Optional[str] = Field(None, description="Alias used in the query")
    startup_cost: Optional[float] = Field(None, description="Estimated cost to return first row")
    total_cost: Optional[float] = Field(None, description="Estimated total plan cost")
    plan_rows: Optional[int] = Field(None, description="Estimated output row count")
    actual_rows: Optional[int] = Field(None, description="Actual output row count (EXPLAIN ANALYZE only)")
    filter: Optional[str] = Field(None, description="Row filter expression applied after scan")
    index_cond: Optional[str] = Field(None, description="Index condition (for index scan nodes)")
    join_type: Optional[str] = Field(None, description="Join strategy (for join nodes)")
    children: List["PlanNode"] = Field(
        default_factory=list,
        description="Child plan nodes (recursive tree structure)",
    )

    # Extensibility hook for Phase 3+ (HypoPG, actual statistics, etc.)
    extra: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional plan fields not yet promoted to first-class fields",
    )

    model_config = {"populate_by_name": True}


# Support for self-referential type
PlanNode.model_rebuild()


# ---------------------------------------------------------------------------
# Bottleneck finding
# ---------------------------------------------------------------------------

class BottleneckFinding(BaseModel):
    """A single potential performance bottleneck identified in a plan.

    A finding represents a heuristic observation with associated evidence,
    not a definitive diagnosis.  It must always include:
    - the evidence that triggered the rule
    - a confidence assessment
    - an estimated impact tier
    """

    finding_type: BottleneckType = Field(
        ..., description="Category of the detected performance concern"
    )
    severity: Severity = Field(..., description="Estimated severity tier")
    confidence: Confidence = Field(
        ..., description="Confidence in this finding given the available plan evidence"
    )
    title: str = Field(..., description="Short human-readable title for the finding")
    description: str = Field(
        ..., description="Detailed explanation of the finding and why it may be significant"
    )
    relation: Optional[str] = Field(
        None, description="Relation (table) primarily associated with this finding"
    )
    evidence: Dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Key-value evidence extracted from the plan that supports this finding "
            "(e.g. estimated rows, filter expression, total cost)"
        ),
    )
    estimated_impact: str = Field(
        ...,
        description=(
            "Human-readable description of the potential performance impact "
            "if the issue is genuine"
        ),
    )

    # Extensibility hook: HypoPG results, actual measurements, etc.
    recommendation: Optional[str] = Field(
        None,
        description="Optional hint about what might mitigate this issue (populated by later phases)",
    )


# ---------------------------------------------------------------------------
# Summary statistics
# ---------------------------------------------------------------------------

class PlanSummary(BaseModel):
    """Aggregate statistics across all nodes in the analyzed plan."""

    total_nodes: int = Field(..., description="Total number of plan nodes analyzed")
    total_estimated_cost: float = Field(
        ..., description="Total cost of the root plan node"
    )
    max_estimated_rows: int = Field(
        ..., description="Largest estimated row count across all nodes"
    )
    scan_nodes: int = Field(..., description="Number of scan-type nodes")
    join_nodes: int = Field(..., description="Number of join-type nodes")
    sort_nodes: int = Field(..., description="Number of sort-type nodes")
    has_seq_scans: bool = Field(..., description="Whether any sequential scan nodes exist")
    has_index_scans: bool = Field(..., description="Whether any index scan nodes exist")
    findings_count: int = Field(..., description="Total number of bottleneck findings")


# ---------------------------------------------------------------------------
# Top-level response
# ---------------------------------------------------------------------------

class PlanAnalysisResponse(BaseModel):
    """Complete result of analyzing a single PostgreSQL EXPLAIN (FORMAT JSON) plan.

    This is the primary output of the PlanAnalyzer + BottleneckDetector pipeline.
    The schema is intentionally extensible for upcoming HypoPG integration.
    """

    query: str = Field(..., description="The original SQL query that was analyzed")
    root_node: PlanNode = Field(..., description="Root node of the parsed execution plan tree")
    nodes_analyzed: int = Field(..., description="Total number of plan nodes traversed")
    findings: List[BottleneckFinding] = Field(
        default_factory=list,
        description="List of potential performance bottlenecks found in the plan",
    )
    summary: PlanSummary = Field(..., description="Aggregate statistics across all plan nodes")

    # Raw plan preserved for downstream consumers (HypoPG, LLM, etc.)
    raw_plan: List[Dict[str, Any]] = Field(
        ...,
        description="Original unmodified PostgreSQL EXPLAIN JSON output",
    )

    # Extensibility: HypoPG simulation results, LLM annotations, etc.
    hypopg_results: Optional[Any] = Field(
        None,
        description="Phase 2 Step 2 HypoPG simulation results",
    )


# ---------------------------------------------------------------------------
# HypoPG Validation Schemas
# ---------------------------------------------------------------------------

class HypotheticalIndexRequest(BaseModel):
    """Structured request defining a candidate index for HypoPG counterfactual validation.

    Accepts structured identifiers rather than arbitrary SQL strings to prevent
    SQL injection and ensure only safe hypothetical indexes are created.
    """

    query: str = Field(
        ...,
        min_length=6,
        description="Original read-only SQL query to test (e.g. 'SELECT * FROM orders WHERE customer_id = 42')",
    )
    table: str = Field(
        ...,
        description="Target table/relation name (e.g. 'orders')",
    )
    columns: List[str] = Field(
        default_factory=list,
        description="List of column identifiers to index in candidate (e.g. ['customer_id'])",
    )
    index_method: IndexMethod = Field(
        default=IndexMethod.BTREE,
        description="PostgreSQL index access method (default: btree)",
    )
    min_cost_improvement_percent: Optional[float] = Field(
        None,
        ge=0.0,
        description="Optional threshold override for percentage cost improvement required for VALIDATED verdict",
    )


class PlanComparison(BaseModel):
    """Detailed comparison between original execution plan and hypothetical index plan."""

    original_cost: float = Field(..., description="Estimated total cost of original plan")
    hypothetical_cost: float = Field(..., description="Estimated total cost with hypothetical index")
    cost_difference: float = Field(..., description="original_cost - hypothetical_cost (> 0 means cost reduction)")
    cost_improvement_percent: float = Field(
        ...,
        description="Percentage cost reduction: ((original_cost - hypothetical_cost) / original_cost) * 100",
    )
    original_root_node_type: str = Field(..., description="Node type of original plan root")
    hypothetical_root_node_type: str = Field(..., description="Node type of hypothetical plan root")
    original_scan_type: Optional[str] = Field(None, description="Primary scan node type in original plan")
    hypothetical_scan_type: Optional[str] = Field(None, description="Primary scan node type in hypothetical plan")
    plan_changed: bool = Field(..., description="True if planner changed plan structure or scan strategy")
    plan_change_summary: Optional[str] = Field(
        None,
        description="Human-readable summary of the plan change (e.g. 'Seq Scan on orders → Index Scan on orders')",
    )


class HypoPGValidationResult(BaseModel):
    """Structured result of HypoPG counterfactual index validation.

    Explicitly reports planner cost evidence vs. hypothetical plan choice without
    conflating planner cost improvement with actual execution-time benchmarks.
    """

    verdict: ValidationVerdict = Field(..., description="Validation outcome classification")
    candidate_index: str = Field(..., description="Generated hypothetical CREATE INDEX definition")
    hypothetical_index_name: Optional[str] = Field(
        None,
        description="Internal HypoPG identifier (e.g. '<13630>btree_orders_customer_id')",
    )
    hypothetical_index_oid: Optional[int] = Field(None, description="HypoPG internal index OID")
    original_query: str = Field(..., description="The query evaluated")
    comparison: Optional[PlanComparison] = Field(None, description="Before vs. after plan comparison")
    original_plan: Optional[PlanNode] = Field(None, description="Parsed original plan tree")
    hypothetical_plan: Optional[PlanNode] = Field(None, description="Parsed hypothetical plan tree")
    evidence: Dict[str, Any] = Field(
        default_factory=dict,
        description="Supporting planner evidence and metrics",
    )
    warnings: List[str] = Field(default_factory=list, description="Validation warnings if any")
    error_message: Optional[str] = Field(None, description="Error message if validation failed")


# ---------------------------------------------------------------------------
# Phase 2 Step 3: Recommendation Engine Schemas
# ---------------------------------------------------------------------------

class OptimizationType(str, Enum):
    """Categories of optimization recommendations."""
    MISSING_INDEX = "missing_index"
    EXPENSIVE_SORT = "expensive_sort"
    EXPENSIVE_NESTED_LOOP = "expensive_nested_loop"
    LARGE_ROW_ESTIMATE = "large_row_estimate"
    FILTERED_SEQ_SCAN = "filtered_seq_scan"


class RecommendationConfidence(str, Enum):
    """Confidence tier in an optimization recommendation."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RecommendationRisk(str, Enum):
    """Operational risk level associated with applying the recommendation."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RecommendationStatus(str, Enum):
    """Validation and lifecycle status of an optimization recommendation."""
    VALIDATED = "validated"
    UNVALIDATED = "unvalidated"
    REJECTED = "rejected"
    REQUIRES_REVIEW = "requires_review"


class OptimizationRecommendation(BaseModel):
    """Structured, deterministic, explainable database optimization recommendation.

    Represents an actionable recommendation derived from EXPLAIN plan evidence
    and counterfactual HypoPG validation.

    Guarantees:
      - Grounded strictly in PostgreSQL planner evidence and HypoPG simulation.
      - Never contains hallucinated table columns or arbitrary SQL.
      - Any proposed SQL is preview-only (safe preview, never auto-executed).
      - requires_human_approval is True on all advisory database recommendations.
    """

    optimization_type: OptimizationType = Field(
        ..., description="Category of the optimization recommendation"
    )
    title: str = Field(..., description="Short human-readable title for the recommendation")
    summary: str = Field(..., description="Executive summary of the recommendation")
    description: str = Field(
        ...,
        description="Detailed structured explanation distinguishing observed facts, validation, recommendation, and caveats",
    )
    relation: Optional[str] = Field(
        None, description="Target table or relation name associated with the recommendation"
    )
    columns: List[str] = Field(
        default_factory=list,
        description="Target column(s) identified from plan predicates without hallucination",
    )
    recommended_action: str = Field(
        ..., description="Specific recommended technical or administrative action"
    )
    sql_preview: Optional[str] = Field(
        None,
        description="Safe, non-executable preview of the SQL statement (preview only, never auto-executed)",
    )
    status: RecommendationStatus = Field(
        ..., description="Validation and lifecycle status of the recommendation"
    )
    confidence: RecommendationConfidence = Field(
        ..., description="Confidence tier derived deterministically from planner and HypoPG evidence"
    )
    risk: RecommendationRisk = Field(
        ..., description="Operational risk tier of applying the recommendation"
    )
    evidence: List[str] = Field(
        default_factory=list,
        description="Ordered list of factual evidence statements supporting this recommendation",
    )
    hypopg_validated: bool = Field(
        False, description="Whether this candidate was validated by HypoPG counterfactual simulation"
    )
    original_cost: Optional[float] = Field(
        None, description="Estimated total cost of the original execution plan"
    )
    hypothetical_cost: Optional[float] = Field(
        None, description="Estimated total cost of the hypothetical plan with optimization"
    )
    cost_improvement_percent: Optional[float] = Field(
        None, description="Percentage cost improvement demonstrated by HypoPG planner simulation"
    )
    plan_before: Optional[PlanNode] = Field(
        None, description="Normalized plan tree before optimization"
    )
    plan_after: Optional[PlanNode] = Field(
        None, description="Normalized plan tree after hypothetical optimization"
    )
    tradeoffs: List[str] = Field(
        default_factory=list,
        description="Explicit operational trade-offs (storage overhead, write amplification, maintenance)",
    )
    warnings: List[str] = Field(
        default_factory=list,
        description="Operational caveats, simulation boundaries, or planner limitations",
    )
    requires_human_approval: bool = Field(
        True,
        description="Always True: recommendations are advisory and require human approval before execution",
    )

    model_config = {"populate_by_name": True}


# ---------------------------------------------------------------------------
# Phase 3 Step 1: Safety & Approval Gate Schemas
# ---------------------------------------------------------------------------

class SafetyLevel(str, Enum):
    """Overall safety classification for an optimization recommendation."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ApprovalStatus(str, Enum):
    """Lifecycle status of an approval request."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class SafetyCheckStatus(str, Enum):
    """Outcome status of an individual safety check."""
    PASSED = "passed"
    FAILED = "failed"
    WARNING = "warning"
    NOT_EVALUATED = "not_evaluated"


class SafetyCheck(BaseModel):
    """A single deterministic safety evaluation rule outcome."""
    check_name: str = Field(..., description="Unique descriptive identifier for the safety check")
    status: SafetyCheckStatus = Field(..., description="Outcome status of the check")
    severity: SafetyLevel = Field(..., description="Severity tier of this check (low, medium, high, critical)")
    message: str = Field(..., description="Human-readable explanation of the check outcome")
    evidence: Dict[str, Any] = Field(default_factory=dict, description="Supporting evidence data for the check")

    model_config = {"populate_by_name": True}


class SafetyAssessment(BaseModel):
    """Complete safety assessment of an optimization recommendation.

    Determines whether a recommendation satisfies conservative, fail-closed safety criteria
    to be eligible for human approval.
    """
    recommendation: OptimizationRecommendation = Field(..., description="The recommendation being assessed")
    safety_level: SafetyLevel = Field(..., description="Aggregated risk and safety tier")
    checks: List[SafetyCheck] = Field(default_factory=list, description="List of all evaluated safety checks")
    overall_status: SafetyCheckStatus = Field(..., description="Aggregated check status (PASSED, WARNING, FAILED)")
    eligible_for_approval: bool = Field(..., description="True only if safe enough to present for human approval")
    requires_human_approval: bool = Field(True, description="Always True: human approval is mandatory")
    blocking_reasons: List[str] = Field(default_factory=list, description="Reasons blocking approval eligibility if any")
    warnings: List[str] = Field(default_factory=list, description="Non-blocking safety warnings and cautions")
    tradeoffs: List[str] = Field(default_factory=list, description="Operational trade-offs associated with this action")

    model_config = {"populate_by_name": True}


class ApprovalRequest(BaseModel):
    """Formal audit record and lifecycle tracker for a human approval request.

    Guarantees:
      - Newly created requests begin strictly in PENDING status.
      - Never approved automatically.
      - Expiration is strictly tracked and enforced.
    """
    approval_id: str = Field(..., description="Unique identifier for the approval request")
    recommendation: OptimizationRecommendation = Field(..., description="The underlying optimization recommendation")
    safety_assessment: SafetyAssessment = Field(..., description="The associated safety assessment")
    status: ApprovalStatus = Field(default=ApprovalStatus.PENDING, description="Current approval status")
    created_at: datetime = Field(..., description="Timestamp when the request was generated")
    expires_at: datetime = Field(..., description="Timestamp after which the request cannot be approved")
    approved_at: Optional[datetime] = Field(None, description="Timestamp when explicit approval occurred")
    rejected_at: Optional[datetime] = Field(None, description="Timestamp when explicit rejection occurred")
    approved_by: Optional[str] = Field(None, description="Actor who approved the request (cannot be anonymous)")
    rejection_reason: Optional[str] = Field(None, description="Explicit reason why the request was rejected")

    model_config = {"populate_by_name": True}


# ---------------------------------------------------------------------------
# Phase 3 Step 2: Controlled Physical Remediation Schemas
# ---------------------------------------------------------------------------

class RemediationStatus(str, Enum):
    """Lifecycle and execution status of a controlled physical remediation."""
    PENDING = "pending"
    RUNNING = "running"
    APPLIED = "applied"
    ALREADY_APPLIED = "already_applied"
    FAILED = "failed"
    BLOCKED = "blocked"
    ROLLED_BACK = "rolled_back"


class RemediationResult(BaseModel):
    """Auditable result of a controlled physical remediation operation.

    Captures before-and-after database index state, exact constructed SQL executed,
    target relation/columns, verification outcome, and timing metadata.
    """
    remediation_id: str = Field(..., description="Unique identifier for the remediation execution")
    approval_id: str = Field(..., description="Identifier of the authorizing ApprovalRequest")
    recommendation: OptimizationRecommendation = Field(..., description="Snapshot of the approved recommendation")
    status: RemediationStatus = Field(..., description="Outcome status of the remediation operation")
    target_relation: str = Field(..., description="Target database relation (table)")
    target_columns: List[str] = Field(default_factory=list, description="Columns targeted for index creation")
    sql_executed: Optional[str] = Field(None, description="Actual constructed SQL DDL executed against the database")
    index_name: Optional[str] = Field(None, description="Name of the physical index created or confirmed existing")
    started_at: datetime = Field(..., description="Timestamp when remediation execution commenced")
    completed_at: datetime = Field(..., description="Timestamp when remediation execution finalized")
    pre_remediation_indexes: List[Dict[str, Any]] = Field(
        default_factory=list, description="Existing physical indexes on target relation before execution"
    )
    post_remediation_indexes: List[Dict[str, Any]] = Field(
        default_factory=list, description="Physical indexes on target relation after execution"
    )
    error: Optional[str] = Field(None, description="Error message if remediation failed or was blocked")
    warnings: List[str] = Field(default_factory=list, description="Operational warnings or idempotency notices")
    verification_passed: bool = Field(False, description="Whether post-creation verification confirmed the index")

    model_config = {"populate_by_name": True}


# ---------------------------------------------------------------------------
# Phase 3 Step 3: Real Runtime Benchmarking Schemas
# ---------------------------------------------------------------------------

class BenchmarkStatus(str, Enum):
    """Execution status of a runtime performance benchmark."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


class ExecutionMeasurement(BaseModel):
    """Structured statistical measurement of query execution and planning performance.

    Captures repeated run samples, timing distributions, plan node characteristics,
    and PostgreSQL buffer cache statistics.
    """
    runs: int = Field(..., description="Number of measured query runs")
    warmup_runs: int = Field(default=0, description="Number of discarded warm-up runs")
    execution_times_ms: List[float] = Field(default_factory=list, description="Execution times in milliseconds")
    planning_times_ms: List[float] = Field(default_factory=list, description="Planning times in milliseconds")
    mean_execution_time_ms: float = Field(..., description="Arithmetic mean execution time in ms")
    median_execution_time_ms: float = Field(..., description="Median execution time in ms")
    min_execution_time_ms: float = Field(..., description="Minimum execution time in ms")
    max_execution_time_ms: float = Field(..., description="Maximum execution time in ms")
    stddev_execution_time_ms: float = Field(..., description="Sample standard deviation of execution times")
    coefficient_of_variation: Optional[float] = Field(
        None, description="Relative variability indicator (stddev / mean)"
    )
    rows_returned: int = Field(..., description="Actual rows returned by query execution")
    planner_cost: Optional[float] = Field(None, description="Total planner cost from EXPLAIN")
    scan_type: Optional[str] = Field(None, description="Scan node type (Seq Scan, Index Scan, Bitmap Heap Scan)")
    index_used: Optional[str] = Field(None, description="Name of the physical index used in the plan if any")
    shared_hit_blocks: Optional[int] = Field(None, description="PostgreSQL shared buffer hit blocks")
    shared_read_blocks: Optional[int] = Field(None, description="PostgreSQL shared buffer read blocks")
    plan_tree: Optional[Dict[str, Any]] = Field(None, description="Normalized plan tree metadata")

    model_config = {"populate_by_name": True}


class BenchmarkResult(BaseModel):
    """Complete, structured, and auditable runtime benchmark result comparing before/after performance.

    Guarantees:
      - Rigorously distinguishes planner cost improvement from actual measured runtime improvement.
      - Tracks before and after execution statistics across repeated runs.
      - Fully JSON-serializable for audit logs, dashboards, and reporting.
    """
    benchmark_id: str = Field(..., description="Unique identifier for this benchmark execution")
    remediation_id: Optional[str] = Field(None, description="Associated remediation execution ID if applicable")
    status: BenchmarkStatus = Field(..., description="Outcome status of the benchmark")
    query: str = Field(..., description="The validated read-only query benchmarked")
    before: ExecutionMeasurement = Field(..., description="Pre-remediation baseline measurement")
    after: ExecutionMeasurement = Field(..., description="Post-remediation measurement")
    planner_cost_improvement_percent: Optional[float] = Field(
        None, description="Planner cost improvement percentage (((before - after) / before) * 100)"
    )
    runtime_improvement_percent: Optional[float] = Field(
        None, description="Real runtime execution improvement percentage (((before - after) / before) * 100)"
    )
    plan_changed: bool = Field(..., description="Whether the scan strategy or plan structure changed")
    index_usage_changed: bool = Field(..., description="Whether index participation changed between before and after")
    started_at: datetime = Field(..., description="Timestamp when benchmarking started")
    completed_at: datetime = Field(..., description="Timestamp when benchmarking finished")
    warnings: List[str] = Field(default_factory=list, description="Non-fatal measurement warnings or caveats")
    error: Optional[str] = Field(None, description="Error message if benchmark failed")

    model_config = {"populate_by_name": True}





