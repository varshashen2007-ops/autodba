import {
  ApprovalRequest,
  BenchmarkResult,
  ClosedLoopRequest,
  ClosedLoopResponse,
  DiagnoseRequest,
  DiagnoseResponse,
  ExplainResponse,
  HealthResponse,
  HypoPGValidationResult,
  MemoryListItem,
  MemorySearchRequest,
  MemorySearchResponse,
  OptimizationMemory,
  OptimizationRecommendation,
  RemediationResult,
  SlowQueryResponse,
} from '../types/api';

const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api/v1';

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let errorDetail = `HTTP ${response.status}: ${response.statusText}`;
    try {
      const errorJson = await response.json();
      if (errorJson.message) {
        errorDetail = errorJson.message;
      } else if (errorJson.detail) {
        errorDetail = typeof errorJson.detail === 'string' ? errorJson.detail : JSON.stringify(errorJson.detail);
      } else if (errorJson.error) {
        errorDetail = `${errorJson.error}: ${errorJson.message || ''}`;
      }
    } catch {
      // Body not JSON
      try {
        const text = await response.text();
        if (text) errorDetail = text;
      } catch {
        // ignore
      }
    }
    throw new Error(errorDetail);
  }
  return response.json();
}

export const api = {
  // System Health
  async getHealth(): Promise<HealthResponse> {
    const res = await fetch(`${API_BASE}/health`);
    return handleResponse<HealthResponse>(res);
  },

  // Slow Queries
  async getSlowQueries(limit = 10, minExecTimeMs = 0.0): Promise<SlowQueryResponse> {
    const params = new URLSearchParams({
      limit: limit.toString(),
      min_exec_time_ms: minExecTimeMs.toString(),
    });
    const res = await fetch(`${API_BASE}/slow-queries?${params}`);
    return handleResponse<SlowQueryResponse>(res);
  },

  // Explain Plan
  async explainQuery(query: string): Promise<ExplainResponse> {
    const res = await fetch(`${API_BASE}/explain`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query }),
    });
    return handleResponse<ExplainResponse>(res);
  },

  // Intelligence: Diagnose
  async diagnoseQuery(payload: DiagnoseRequest): Promise<DiagnoseResponse> {
    const res = await fetch(`${API_BASE}/intelligence/diagnose`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    return handleResponse<DiagnoseResponse>(res);
  },

  // Intelligence: Memories
  async getMemories(limit = 50, offset = 0): Promise<MemoryListItem[]> {
    const params = new URLSearchParams({
      limit: limit.toString(),
      offset: offset.toString(),
    });
    const res = await fetch(`${API_BASE}/intelligence/memories?${params}`);
    return handleResponse<MemoryListItem[]>(res);
  },

  async getMemory(memoryId: number): Promise<OptimizationMemory> {
    const res = await fetch(`${API_BASE}/intelligence/memories/${memoryId}`);
    return handleResponse<OptimizationMemory>(res);
  },

  async searchMemories(payload: MemorySearchRequest): Promise<MemorySearchResponse> {
    const res = await fetch(`${API_BASE}/intelligence/search`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    return handleResponse<MemorySearchResponse>(res);
  },

  // Intelligence: Closed-Loop Execution
  async executeClosedLoop(payload: ClosedLoopRequest): Promise<ClosedLoopResponse> {
    const res = await fetch(`${API_BASE}/intelligence/closed-loop`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    return handleResponse<ClosedLoopResponse>(res);
  },

  // Approvals
  async getApprovals(): Promise<ApprovalRequest[]> {
    const res = await fetch(`${API_BASE}/approvals`);
    return handleResponse<ApprovalRequest[]>(res);
  },

  async getApproval(approvalId: string): Promise<ApprovalRequest> {
    const res = await fetch(`${API_BASE}/approvals/${approvalId}`);
    return handleResponse<ApprovalRequest>(res);
  },

  async createApproval(recommendation: OptimizationRecommendation): Promise<ApprovalRequest> {
    const res = await fetch(`${API_BASE}/approvals`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ recommendation }),
    });
    return handleResponse<ApprovalRequest>(res);
  },

  async approveRequest(approvalId: string, approvedBy: string): Promise<ApprovalRequest> {
    const res = await fetch(`${API_BASE}/approvals/${approvalId}/approve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ approved_by: approvedBy }),
    });
    return handleResponse<ApprovalRequest>(res);
  },

  async rejectRequest(approvalId: string, rejectionReason: string): Promise<ApprovalRequest> {
    const res = await fetch(`${API_BASE}/approvals/${approvalId}/reject`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ rejection_reason: rejectionReason }),
    });
    return handleResponse<ApprovalRequest>(res);
  },

  // Remediation
  async applyRemediation(approvalId: string): Promise<RemediationResult> {
    const res = await fetch(`${API_BASE}/remediations/apply`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ approval_id: approvalId }),
    });
    return handleResponse<RemediationResult>(res);
  },

  // Benchmarks
  async runBenchmark(query: string, runs = 10, warmupRuns = 2): Promise<BenchmarkResult> {
    const res = await fetch(`${API_BASE}/benchmarks/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query, runs, warmup_runs: warmupRuns }),
    });
    return handleResponse<BenchmarkResult>(res);
  },

  // Recommendations: HypoPG Validate & Generate
  async validateCandidate(
    query: string,
    indexDefinition: string,
    table: string,
    minImprovementPercent?: number
  ): Promise<HypoPGValidationResult> {
    const res = await fetch(`${API_BASE}/recommendations/validate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        query,
        index_definition: indexDefinition,
        table,
        min_improvement_percent: minImprovementPercent,
      }),
    });
    return handleResponse<HypoPGValidationResult>(res);
  },

  async generateRecommendations(query: string): Promise<{ query: string; recommendations: OptimizationRecommendation[] }> {
    const res = await fetch(`${API_BASE}/recommendations/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query }),
    });
    return handleResponse<{ query: string; recommendations: OptimizationRecommendation[] }>(res);
  },
};
