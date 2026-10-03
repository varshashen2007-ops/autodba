"""
Case schema for the AutoDBA research evaluation harness.

This module defines the canonical data structure for a historical
optimization case. A case represents one recorded optimization attempt:
a query, its execution plan, the schema/statistics state at the time,
the workload context, the recommended action, HypoPG validation
evidence, the measured outcome, and metadata about the measurement
quality and data provenance.

IMPORTANT: This module is research scaffolding only. It does not modify
the application code, database schemas, or runtime behavior of AutoDBA.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import hashlib
import re
from typing import Any, Dict, List, Optional, Tuple


class MeasurementQuality(str, Enum):
    """Quality level of a measured outcome."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


class CaseProvenance(str, Enum):
    """Where a case originated."""
    SEED = "seeded"
    SIMULATED = "simulated"
    REAL_MEASURED = "real_measured"
    MANUAL = "manual"
    UNVERIFIED = "unverified"


class IncidentType(str, Enum):
    """Incident types used by the AutoDBA diagnosis pipeline."""
    MISSING_INDEX = "missing_index"
    FILTERED_SEQ_SCAN = "filtered_seq_scan"
    EXPENSIVE_SORT = "expensive_sort"
    EXPENSIVE_NESTED_LOOP = "expensive_nested_loop"
    LARGE_ROW_ESTIMATE = "large_row_estimate"
    UNKNOWN = "unknown"


def canonicalize_sql(sql: str) -> str:
    """
    Deterministically canonicalizes SQL queries represented in the evaluation corpus.

    Scope and Limitations:
      - We define a deterministic canonicalization procedure for the SQL forms
        represented in the evaluation corpus.
      - This is NOT a universal PostgreSQL parser and does not construct a full AST.
      - Scoped to handle standard read-only query patterns in evaluation benchmarks:
        parameterizes numeric literals, single-quoted strings, booleans, positional
        markers ($1, $2), IN-list expansions, and normalizes formatting whitespace.
    """
    if not sql:
        return ""

    # 1. Strip SQL comments
    s = re.sub(r"--[^\n]*", " ", sql)
    s = re.sub(r"/\*.*?\*/", " ", s, flags=re.DOTALL)

    # 2. Normalize whitespace and lowercase
    s = re.sub(r"\s+", " ", s.strip()).lower()

    # 3. Parameterize single-quoted string literals
    s = re.sub(r"'([^']|'')*'", "?", s)

    # 4. Parameterize numeric literals (integers and floats)
    s = re.sub(r"\b\d+(?:\.\d+)?\b", "?", s)

    # 5. Parameterize positional parameter markers ($1, $2, etc.)
    s = re.sub(r"\$\d+", "?", s)

    # 6. Parameterize boolean literals
    s = re.sub(r"\b(true|false)\b", "?", s)

    # 7. Normalize IN-lists: e.g. IN (?, ?, ?) -> IN (?)
    s = re.sub(r"\bin\s*\(\s*\?(?:\s*,\s*\?)*\s*\)", "in (?)", s)

    # 8. Normalize spacing around punctuation
    s = re.sub(r"\s*([,()=<>])\s*", r" \1 ", s)
    s = re.sub(r"<\s*>", "<>", s)
    s = re.sub(r"<\s*=", "<=", s)
    s = re.sub(r">\s*=", ">=", s)
    s = re.sub(r"!\s*=", "!=", s)

    # 9. Collapse whitespace and strip trailing semicolon
    s = re.sub(r"\s+", " ", s).strip()
    s = s.rstrip(";").strip()

    return s


def compute_template_hash(sql: str) -> str:
    """Compute the SHA-256 hash of the canonicalized SQL template."""
    canonical = canonicalize_sql(sql)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass
class QueryInfo:
    """SQL query and its normalized template."""
    text: str
    template: str = ""
    normalized_sql: str = ""

    def __post_init__(self) -> None:
        if not self.template:
            self.template = canonicalize_sql(self.text)
        if not self.normalized_sql:
            self.normalized_sql = self.template

    @property
    def template_hash(self) -> str:
        return compute_template_hash(self.text)


@dataclass
class PlanInfo:
    """Execution plan evidence for a case."""
    raw_plan: Dict[str, Any] = field(default_factory=dict)
    root_node_type: str = ""
    nodes_analyzed: int = 0
    estimated_cost: Optional[float] = None
    estimated_rows: Optional[int] = None
    actual_rows: Optional[int] = None
    scan_type: str = ""
    index_used: bool = False
    findings: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class SchemaInfo:
    """Schema and statistics state when the case was recorded."""
    database_version: str = ""
    tables: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    row_counts: Dict[str, int] = field(default_factory=dict)
    statistics_freshness: Optional[str] = None

    def add_table(self, name: str, info: Dict[str, Any]) -> None:
        self.tables[name] = dict(info)
        self.row_counts[name] = int(info.get("row_count", 0))


@dataclass
class WorkloadContext:
    """Operational context surrounding a query."""
    workload_name: str = ""
    query_frequency_per_hour: float = 0.0
    concurrent_queries: int = 0
    time_of_day: str = ""
    write_load_ratio: float = 0.0
    data_skew: Dict[str, float] = field(default_factory=dict)
    conditions_group: str = ""


@dataclass
class RecommendationAction:
    """The optimization action recommended for the case."""
    action_type: str
    table: Optional[str] = None
    columns: List[str] = field(default_factory=list)
    index_method: str = "btree"
    sql_preview: str = ""
    requires_human_approval: bool = True
    confidence: str = "unknown"
    risk: str = "unknown"


@dataclass
class HypoPGValidation:
    """HypoPG counterfactual validation evidence."""
    hypopg_validated: bool = False
    original_cost: Optional[float] = None
    hypothetical_cost: Optional[float] = None
    cost_improvement_percent: Optional[float] = None
    plan_change_summary: str = ""
    verdict: str = "not_run"


@dataclass
class MeasuredOutcome:
    """Measured before/after outcome of the recommended action."""
    before_runtime_ms: Optional[float] = None
    after_runtime_ms: Optional[float] = None
    runtime_improvement_percent: Optional[float] = None
    planner_cost_improvement_percent: Optional[float] = None
    plan_changed: bool = False
    index_used_before: bool = False
    index_used_after: bool = False
    index_storage_bytes: Optional[int] = None
    write_amplification: Optional[float] = None
    p95_latency_before_ms: Optional[float] = None
    p95_latency_after_ms: Optional[float] = None
    measurement_runs: int = 0
    benchmark_status: str = "not_benchmarked"

    @property
    def success(self) -> bool:
        return (self.runtime_improvement_percent is not None
                and self.runtime_improvement_percent > 0)

    @property
    def regression(self) -> bool:
        return (self.runtime_improvement_percent is not None
                and self.runtime_improvement_percent < 0)


@dataclass
class MeasurementQualityInfo:
    """Metadata describing how trustworthy the measurement is."""
    quality: MeasurementQuality = MeasurementQuality.UNKNOWN
    runs_executed: int = 0
    warmup_runs_discarded: int = 0
    coefficient_of_variation: Optional[float] = None
    confidence_interval: Optional[Tuple[float, float]] = None
    benchmark_id: Optional[str] = None
    remediation_id: Optional[str] = None
    validation_completed: bool = False
    notes: str = ""


@dataclass
class OptimizationCase:
    """Canonical research representation of a historical optimization case."""
    case_id: str
    incident_type: IncidentType
    query: QueryInfo
    plan: PlanInfo
    recommendation: RecommendationAction
    hypopg_validation: HypoPGValidation
    measured_outcome: MeasuredOutcome
    measurement_quality: MeasurementQualityInfo
    provenance: CaseProvenance = CaseProvenance.UNVERIFIED
    is_verified: bool = False
    verification_state: str = "unverified"
    schema_info: Optional[SchemaInfo] = None
    workload: Optional[WorkloadContext] = None

    @property
    def template_hash(self) -> str:
        """Deterministic template group hash for leakage-safe splitting."""
        return self.query.template_hash

    @property
    def canonical_template(self) -> str:
        """Canonicalized SQL template string."""
        return self.query.template

    @property
    def embedding_text(self) -> str:
        """Text representation used for deterministic token hashing."""
        return f"incident_type: {self.incident_type.value} query: {self.query.text}"

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> OptimizationCase:
        """Parse an OptimizationCase from dictionary or sample_cases.json format."""
        case_id = str(d.get("case_id", "unknown"))

        # Incident type
        inc_raw = str(d.get("incident_type", "unknown"))
        try:
            incident_type = IncidentType(inc_raw)
        except ValueError:
            incident_type = IncidentType.UNKNOWN

        # Query info
        q_raw = d.get("query", "")
        if isinstance(q_raw, str):
            query = QueryInfo(text=q_raw)
        elif isinstance(q_raw, dict):
            query = QueryInfo(
                text=q_raw.get("text", ""),
                template=q_raw.get("template", ""),
                normalized_sql=q_raw.get("normalized_sql", ""),
            )
        else:
            query = QueryInfo(text="")

        # Plan info
        plan_raw = d.get("plan", {})
        plan = PlanInfo(
            raw_plan=plan_raw.get("raw_plan", {}),
            root_node_type=plan_raw.get("root_node", plan_raw.get("root_node_type", "")),
            nodes_analyzed=int(plan_raw.get("nodes_analyzed", 0)),
            estimated_cost=plan_raw.get("estimated_cost"),
            estimated_rows=plan_raw.get("estimated_rows"),
            actual_rows=plan_raw.get("actual_rows"),
            scan_type=plan_raw.get("scan_type", ""),
            index_used=bool(plan_raw.get("index_used", False)),
            findings=plan_raw.get("findings", []),
        )

        # Recommendation
        rec_raw = d.get("recommendation", {})
        recommendation = RecommendationAction(
            action_type=rec_raw.get("action", rec_raw.get("action_type", "unknown")),
            table=rec_raw.get("table"),
            columns=rec_raw.get("columns", []),
            index_method=rec_raw.get("index_method", "btree"),
            sql_preview=rec_raw.get("sql_preview", "") or "",
            requires_human_approval=bool(rec_raw.get("requires_human_approval", True)),
            confidence=rec_raw.get("confidence", "unknown"),
            risk=rec_raw.get("risk", "unknown"),
        )

        # HypoPG Validation
        hypo_raw = d.get("hypopg_validation", {})
        hypopg_validation = HypoPGValidation(
            hypopg_validated=bool(hypo_raw.get("validated", hypo_raw.get("hypopg_validated", False))),
            original_cost=hypo_raw.get("cost_before", hypo_raw.get("original_cost")),
            hypothetical_cost=hypo_raw.get("cost_after", hypo_raw.get("hypothetical_cost")),
            cost_improvement_percent=hypo_raw.get("improvement_pct", hypo_raw.get("cost_improvement_percent")),
            plan_change_summary=hypo_raw.get("plan_change_summary", ""),
            verdict=hypo_raw.get("verdict", "not_run"),
        )

        # Outcome
        out_raw = d.get("outcome", {})
        measured_outcome = MeasuredOutcome(
            before_runtime_ms=out_raw.get("runtime_before_ms", out_raw.get("before_runtime_ms")),
            after_runtime_ms=out_raw.get("runtime_after_ms", out_raw.get("after_runtime_ms")),
            runtime_improvement_percent=out_raw.get("runtime_improvement_pct", out_raw.get("runtime_improvement_percent")),
            planner_cost_improvement_percent=out_raw.get("planner_cost_improvement_pct"),
            plan_changed=bool(out_raw.get("plan_changed", False)),
            index_used_before=bool(out_raw.get("index_used_before", False)),
            index_used_after=bool(out_raw.get("index_used_after", False)),
            index_storage_bytes=out_raw.get("index_storage_bytes"),
            write_amplification=out_raw.get("write_amplification"),
            p95_latency_before_ms=out_raw.get("p95_latency_before_ms"),
            p95_latency_after_ms=out_raw.get("p95_latency_after_ms"),
            measurement_runs=int(out_raw.get("measurement_runs", 0)),
            benchmark_status="completed" if out_raw.get("benchmarked") else out_raw.get("benchmark_status", "not_benchmarked"),
        )

        # Quality
        qual_raw = d.get("measurement_quality")
        if isinstance(qual_raw, str):
            try:
                quality_enum = MeasurementQuality(qual_raw)
            except ValueError:
                quality_enum = MeasurementQuality.UNKNOWN
            measurement_quality = MeasurementQualityInfo(quality=quality_enum)
        elif isinstance(qual_raw, dict):
            measurement_quality = MeasurementQualityInfo(
                quality=MeasurementQuality(qual_raw.get("quality", "unknown")),
                runs_executed=int(qual_raw.get("runs_executed", 0)),
                notes=qual_raw.get("notes", ""),
            )
        else:
            measurement_quality = MeasurementQualityInfo(quality=MeasurementQuality.UNKNOWN)

        # Provenance
        prov_raw = str(d.get("provenance", "unverified"))
        try:
            provenance = CaseProvenance(prov_raw)
        except ValueError:
            provenance = CaseProvenance.UNVERIFIED

        is_verified = bool(d.get("is_verified", False))
        verification_state = str(d.get("verification_state", "unverified"))

        return cls(
            case_id=case_id,
            incident_type=incident_type,
            query=query,
            plan=plan,
            recommendation=recommendation,
            hypopg_validation=hypopg_validation,
            measured_outcome=measured_outcome,
            measurement_quality=measurement_quality,
            provenance=provenance,
            is_verified=is_verified,
            verification_state=verification_state,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert case to serializable dictionary format."""
        return {
            "case_id": self.case_id,
            "incident_type": self.incident_type.value,
            "query": self.query.text,
            "canonical_template": self.canonical_template,
            "template_hash": self.template_hash,
            "plan": {
                "root_node": self.plan.root_node_type,
                "estimated_cost": self.plan.estimated_cost,
                "scan_type": self.plan.scan_type,
                "index_used": self.plan.index_used,
            },
            "recommendation": {
                "action": self.recommendation.action_type,
                "table": self.recommendation.table,
                "columns": self.recommendation.columns,
                "sql_preview": self.recommendation.sql_preview,
            },
            "hypopg_validation": {
                "validated": self.hypopg_validation.hypopg_validated,
                "original_cost": self.hypopg_validation.original_cost,
                "hypothetical_cost": self.hypopg_validation.hypothetical_cost,
                "cost_improvement_percent": self.hypopg_validation.cost_improvement_percent,
            },
            "outcome": {
                "runtime_before_ms": self.measured_outcome.before_runtime_ms,
                "runtime_after_ms": self.measured_outcome.after_runtime_ms,
                "runtime_improvement_percent": self.measured_outcome.runtime_improvement_percent,
                "plan_changed": self.measured_outcome.plan_changed,
                "index_used_before": self.measured_outcome.index_used_before,
                "index_used_after": self.measured_outcome.index_used_after,
                "benchmark_status": self.measured_outcome.benchmark_status,
            },
            "measurement_quality": self.measurement_quality.quality.value,
            "provenance": self.provenance.value,
            "is_verified": self.is_verified,
            "verification_state": self.verification_state,
        }


def case_outcome(case: OptimizationCase) -> str:
    """Return the outcome label used by the legacy memory store."""
    if case.measured_outcome.benchmark_status == "not_benchmarked":
        return "not_benchmarked"
    if case.measured_outcome.success:
        return "success"
    if case.measured_outcome.regression:
        return "regression"
    return "no_improvement"