// TypeScript interfaces mirroring AutoDBA Pydantic schemas

export interface HealthResponse {
  status: string;
  database: string;
  version: string | null;
  extensions: string[];
}

export interface SlowQuery {
  query: string;
  calls: number;
  total_time_ms: number;
  mean_time_ms: number;
  rows: number;
  shared_blks_hit: number;
  shared_blks_read: number;
}

export interface SlowQueryResponse {
  queries: SlowQuery[];
  count: number;
}

export interface PlanNode {
  node_type: string;
  relation_name?: string | null;
  alias?: string | null;
  startup_cost?: number | null;
  total_cost?: number | null;
  plan_rows?: number | null;
  actual_rows?: number | null;
  actual_startup_time?: number | null;
  actual_total_time?: number | null;
  filter?: string | null;
  index_cond?: string | null;
  join_type?: string | null;
  children?: PlanNode[];
  extra?: Record<string, any>;
  [key: string]: any;
}

export interface BottleneckFinding {
  finding_type: string;
  severity: 'low' | 'medium' | 'high';
  confidence: 'low' | 'medium' | 'high';
  title: string;
  description: string;
  relation?: string | null;
  evidence: Record<string, any>;
  estimated_impact: string;
  recommendation?: string | null;
}

export interface PlanSummary {
  total_nodes: number;
  total_estimated_cost: number;
  max_estimated_rows: number;
  scan_nodes: number;
  join_nodes: number;
  sort_nodes: number;
  has_seq_scans: boolean;
  has_index_scans: boolean;
  findings_count: number;
}

export interface OptimizationRecommendation {
  optimization_type: string;
  title: string;
  summary: string;
  description: string;
  relation: string;
  columns: string[];
  recommended_action: string;
  sql_preview: string;
  status: 'validated' | 'unvalidated' | 'rejected' | 'requires_review';
  confidence: 'low' | 'medium' | 'high';
  risk: 'low' | 'medium' | 'high';
  evidence: string[];
  requires_human_approval: boolean;
  hypopg_result?: any;
}

export interface PlanComparison {
  original_cost: number;
  hypothetical_cost: number;
  cost_difference: number;
  cost_improvement_percent: number;
  original_root_node_type: string;
  hypothetical_root_node_type: string;
  original_scan_type?: string | null;
  hypothetical_scan_type?: string | null;
  plan_changed: boolean;
  plan_change_summary?: string | null;
}

export interface HypoPGValidationResult {
  verdict: 'validated' | 'no_improvement' | 'regression' | 'invalid_candidate' | 'error';
  candidate_index: string;
  hypothetical_index_name?: string | null;
  hypothetical_index_oid?: number | null;
  original_query: string;
  comparison?: PlanComparison | null;
  original_plan?: PlanNode | null;
  hypothetical_plan?: PlanNode | null;
  evidence: Record<string, any>;
  warnings: string[];
  error_message?: string | null;
}

export interface SafetyCheck {
  check_name: string;
  status: 'passed' | 'failed' | 'warning' | 'not_evaluated';
  severity: 'low' | 'medium' | 'high' | 'critical';
  message: string;
  evidence: Record<string, any>;
}

export interface SafetyAssessment {
  recommendation: OptimizationRecommendation;
  safety_level: 'low' | 'medium' | 'high' | 'critical';
  checks: SafetyCheck[];
  overall_status: 'passed' | 'warning' | 'failed';
  eligible_for_approval: boolean;
  requires_human_approval: boolean;
  blocking_reasons: string[];
  warnings: string[];
  tradeoffs: string[];
}

export interface ApprovalRequest {
  approval_id: string;
  recommendation: OptimizationRecommendation;
  safety_assessment: SafetyAssessment;
  status: 'pending' | 'approved' | 'rejected' | 'expired';
  created_at: string;
  expires_at: string;
  approved_at?: string | null;
  rejected_at?: string | null;
  approved_by?: string | null;
  rejection_reason?: string | null;
}

export interface RemediationResult {
  remediation_id: string;
  approval_id: string;
  recommendation: OptimizationRecommendation;
  status: 'pending' | 'running' | 'applied' | 'already_applied' | 'failed' | 'blocked' | 'rolled_back';
  target_relation: string;
  target_columns: string[];
  sql_executed?: string | null;
  index_name?: string | null;
  started_at: string;
  completed_at: string;
  pre_remediation_indexes: Record<string, any>[];
  post_remediation_indexes: Record<string, any>[];
  error?: string | null;
  warnings: string[];
  verification_passed: boolean;
}

export interface ExecutionMeasurement {
  runs: number;
  warmup_runs: number;
  execution_times_ms: number[];
  planning_times_ms: number[];
  mean_execution_time_ms: number;
  median_execution_time_ms: number;
  min_execution_time_ms: number;
  max_execution_time_ms: number;
  stddev_execution_time_ms: number;
  coefficient_of_variation?: number | null;
  rows_returned: number;
  planner_cost?: number | null;
  scan_type?: string | null;
  index_used?: string | null;
  shared_hit_blocks?: number | null;
  shared_read_blocks?: number | null;
  plan_tree?: Record<string, any> | null;
}

export interface BenchmarkResult {
  benchmark_id: string;
  remediation_id?: string | null;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'blocked';
  query: string;
  before: ExecutionMeasurement;
  after: ExecutionMeasurement;
  planner_cost_improvement_percent?: number | null;
  runtime_improvement_percent?: number | null;
  plan_changed: boolean;
  index_usage_changed: boolean;
  started_at: string;
  completed_at: string;
  warnings: string[];
  error?: string | null;
}

export interface SimilarCase {
  memory_id: number;
  similarity: number;
  incident_type: string;
  query_text: string;
  diagnosis: Record<string, any>;
  recommendation: Record<string, any>;
  validation?: Record<string, any> | null;
  benchmark?: Record<string, any> | null;
  outcome: 'success' | 'no_improvement' | 'regression' | 'failed' | 'unknown';
  outcome_summary?: string | null;
  created_at?: string | null;
}

export interface RAGContext {
  query_fingerprint?: string | null;
  incident_type?: string | null;
  similar_cases: SimilarCase[];
  retrieval_count: number;
  retrieval_threshold: number;
}

export interface DiagnosisResult {
  query: string;
  incident_type: string;
  analysis: Record<string, any>;
  findings: BottleneckFinding[];
  recommendation?: OptimizationRecommendation | null;
  rag_context?: RAGContext | null;
}

export interface DiagnoseRequest {
  query: string;
  incident_type?: string | null;
  include_rag?: boolean;
  max_similar_cases?: number;
}

export interface DiagnoseResponse {
  diagnosis: DiagnosisResult;
  llm_explanation?: string | null;
  llm_provider?: string | null;
}

export interface MemoryListItem {
  id: number;
  incident_type: string;
  query_fingerprint?: string | null;
  query_text: string;
  outcome: 'success' | 'no_improvement' | 'regression' | 'failed' | 'unknown';
  outcome_summary?: string | null;
  created_at?: string | null;
}

export interface OptimizationMemory {
  id: number;
  incident_type: string;
  query_fingerprint?: string | null;
  query_text: string;
  diagnosis: Record<string, any>;
  recommendation: Record<string, any>;
  validation?: Record<string, any> | null;
  benchmark?: Record<string, any> | null;
  outcome: 'success' | 'no_improvement' | 'regression' | 'failed' | 'unknown';
  outcome_summary?: string | null;
  embedding?: number[] | null;
  created_at?: string | null;
}

export interface MemorySearchRequest {
  query: string;
  incident_type?: string | null;
  limit?: number;
  similarity_threshold?: number;
}

export interface MemorySearchResponse {
  query: string;
  results: SimilarCase[];
  total: number;
}

export interface ClosedLoopRequest {
  approval_id: string;
  query_text: string;
  incident_type?: string;
  diagnosis?: Record<string, any>;
  recommendation?: OptimizationRecommendation | null;
}

export interface ClosedLoopResponse {
  approval: ApprovalRequest;
  remediation: RemediationResult;
  benchmark: BenchmarkResult;
  outcome: 'success' | 'no_improvement' | 'regression' | 'failed' | 'unknown';
  memory: OptimizationMemory;
}
