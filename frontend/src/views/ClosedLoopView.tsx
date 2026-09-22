import React, { useState } from 'react';
import { ApprovalRequest, ClosedLoopResponse } from '../types/api';
import { api } from '../services/api';
import {
  RefreshCw,
  CheckCircle2,
  AlertTriangle,
  Play,
  RotateCcw,
  ShieldCheck,
  Zap,
  Gauge,
  Database,
  ArrowDown,
  Sparkles,
  TrendingUp,
} from 'lucide-react';
import { BenchmarkComparisonView } from '../components/BenchmarkComparisonView';

interface ClosedLoopViewProps {
  approvals: ApprovalRequest[];
  onRefreshAll: () => void;
}

export const ClosedLoopView: React.FC<ClosedLoopViewProps> = ({ approvals, onRefreshAll }) => {
  const approvedList = approvals.filter((a) => a.status === 'approved');
  const [selectedApprovalId, setSelectedApprovalId] = useState<string>(
    approvedList[0]?.approval_id || ''
  );
  const [queryText, setQueryText] = useState('SELECT * FROM orders WHERE customer_id = 42;');
  const [loading, setLoading] = useState(false);
  const [currentStepIndex, setCurrentStepIndex] = useState<number>(-1);
  const [error, setError] = useState<string | null>(null);
  const [response, setResponse] = useState<ClosedLoopResponse | null>(null);

  const loopSteps = [
    { title: '1. Detect', desc: 'Continuous slow query monitoring via pg_stat_statements' },
    { title: '2. Diagnose', desc: 'Deterministic plan tree parsing & bottleneck detection' },
    { title: '3. Retrieve', desc: 'Local cosine-similarity lookup over prior optimization memories' },
    { title: '4. Recommend', desc: 'Rule-based index candidate generation with confidence & risk scoring' },
    { title: '5. Validate', desc: 'In-memory counterfactual HypoPG simulation & plan comparison' },
    { title: '6. Request Approval', desc: '7-rule safety assessment requiring explicit human sign-off' },
    { title: '7. Remediate', desc: 'Controlled, idempotent physical CREATE INDEX execution with post-DDL verification' },
    { title: '8. Benchmark', desc: '10-run EXPLAIN ANALYZE isolating wall-clock latency improvement' },
    { title: '9. Record Outcome', desc: 'Empirical classification: SUCCESS / NO_IMPROVEMENT / REGRESSION' },
    { title: '10. Learn', desc: 'Vectorization & storage into PostgreSQL memory corpus for future RAG' },
  ];

  const handleExecuteClosedLoop = async () => {
    if (!selectedApprovalId) {
      setError('Please select an already APPROVED authorization to execute the closed loop.');
      return;
    }

    try {
      setLoading(true);
      setError(null);
      setResponse(null);

      // Animate progress through post-approval stages
      setCurrentStepIndex(6); // Step 7: Remediate
      await new Promise((r) => setTimeout(r, 400));

      setCurrentStepIndex(7); // Step 8: Benchmark
      await new Promise((r) => setTimeout(r, 600));

      setCurrentStepIndex(8); // Step 9: Record Outcome

      const res = await api.executeClosedLoop({
        approval_id: selectedApprovalId,
        query_text: queryText.trim(),
        incident_type: 'missing_index',
      });

      setCurrentStepIndex(9); // Step 10: Learn
      setResponse(res);
      onRefreshAll();
    } catch (err: any) {
      setError(err.message || 'Closed-loop execution failed');
      setCurrentStepIndex(-1);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      {/* Visual Workflow Architecture */}
      <div className="card">
        <div className="card-header">
          <div>
            <div className="card-title">
              <RefreshCw size={18} style={{ color: 'var(--accent-purple)' }} />
              <span>Closed-Loop Self-Improving Architecture</span>
            </div>
            <div className="card-subtitle">
              How AutoDBA closes the feedback loop from detection to persistent learning
            </div>
          </div>
          <span className="badge badge-purple">10 Autonomous Stages</span>
        </div>

        {/* 10-Step Timeline */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '12px', margin: '14px 0' }}>
          {loopSteps.map((step, idx) => {
            const isActive = currentStepIndex === idx;
            const isDone = currentStepIndex > idx || (response && idx <= 9);

            return (
              <div
                key={idx}
                style={{
                  padding: '12px 14px',
                  borderRadius: '10px',
                  backgroundColor: isActive
                    ? 'rgba(139, 92, 246, 0.15)'
                    : isDone
                    ? 'rgba(16, 185, 129, 0.08)'
                    : 'var(--bg-card-subtle)',
                  border: isActive
                    ? '1px solid var(--accent-purple-border)'
                    : isDone
                    ? '1px solid var(--accent-green-border)'
                    : '1px solid var(--border-subtle)',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '4px',
                  transition: 'all 0.2s ease',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <span
                    style={{
                      fontSize: '11px',
                      fontWeight: 700,
                      color: isActive ? '#a78bfa' : isDone ? '#34d399' : 'var(--text-muted)',
                    }}
                  >
                    STAGE {idx + 1}
                  </span>
                  {isDone ? (
                    <CheckCircle2 size={13} style={{ color: '#10b981' }} />
                  ) : isActive ? (
                    <RotateCcw size={13} className="animate-spin" style={{ color: '#a78bfa' }} />
                  ) : null}
                </div>
                <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)' }}>
                  {step.title.split('. ')[1]}
                </div>
                <div style={{ fontSize: '11px', color: 'var(--text-secondary)', lineHeight: 1.4 }}>
                  {step.desc}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Execution Trigger Card */}
      <div className="card">
        <div className="card-header">
          <div>
            <div className="card-title">Execute Live Closed-Loop Feedback Cycle</div>
            <div className="card-subtitle">
              Executes physical remediation on an approved request, benchmarks before/after, records outcome, and persists memory
            </div>
          </div>
        </div>

        {approvedList.length === 0 ? (
          <div
            style={{
              padding: '16px',
              borderRadius: '8px',
              backgroundColor: 'rgba(245, 158, 11, 0.08)',
              border: '1px solid var(--accent-amber-border)',
              color: '#fbbf24',
              fontSize: '13px',
            }}
          >
            No approval requests are currently in APPROVED status. Go to the Approvals Gate and grant explicit authorization first.
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '14px' }}>
              <div>
                <label className="label">Select Approved Authorization</label>
                <select
                  className="select"
                  value={selectedApprovalId}
                  onChange={(e) => setSelectedApprovalId(e.target.value)}
                  disabled={loading}
                >
                  {approvedList.map((a) => (
                    <option key={a.approval_id} value={a.approval_id}>
                      {a.approval_id} — {a.recommendation?.title} (Approved by {a.approved_by})
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="label">Benchmark Target Query</label>
                <input
                  type="text"
                  className="input font-mono"
                  value={queryText}
                  onChange={(e) => setQueryText(e.target.value)}
                  disabled={loading}
                />
              </div>
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '6px' }}>
              <button
                className="btn btn-purple"
                onClick={handleExecuteClosedLoop}
                disabled={loading || !selectedApprovalId}
                style={{ minWidth: '220px' }}
              >
                {loading ? (
                  <>
                    <RotateCcw size={16} className="animate-spin" />
                    <span>Executing Pipeline Stages...</span>
                  </>
                ) : (
                  <>
                    <Play size={16} />
                    <span>Trigger Closed-Loop Pipeline</span>
                  </>
                )}
              </button>
            </div>
          </div>
        )}

        {error && (
          <div
            style={{
              marginTop: '14px',
              padding: '12px 16px',
              borderRadius: '8px',
              backgroundColor: 'rgba(239, 68, 68, 0.1)',
              border: '1px solid var(--accent-red-border)',
              color: '#f87171',
              fontSize: '13px',
            }}
          >
            {error}
          </div>
        )}
      </div>

      {/* Result Display */}
      {response && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          <div className="card" style={{ borderLeft: '4px solid var(--accent-green)' }}>
            <div className="card-header">
              <div>
                <div className="card-title" style={{ color: '#10b981' }}>
                  <CheckCircle2 size={18} />
                  <span>Closed-Loop Cycle Complete — Memory Persisted</span>
                </div>
                <div className="card-subtitle">
                  Outcome: {response.outcome.toUpperCase()} • New Memory ID #{response.memory.id} stored in PostgreSQL
                </div>
              </div>
              <span className="badge badge-green">Self-Improvement Verified</span>
            </div>

            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
                gap: '12px',
                padding: '14px',
                backgroundColor: 'rgba(0, 0, 0, 0.25)',
                borderRadius: '8px',
                fontSize: '12.5px',
              }}
            >
              <div>
                <span style={{ color: 'var(--text-muted)' }}>Remediation Status:</span>{' '}
                <strong style={{ color: '#34d399' }}>{response.remediation.status}</strong>
              </div>
              <div>
                <span style={{ color: 'var(--text-muted)' }}>Index Verified:</span>{' '}
                <strong style={{ color: '#60a5fa' }}>{response.remediation.index_name}</strong>
              </div>
              <div>
                <span style={{ color: 'var(--text-muted)' }}>Runtime Improvement:</span>{' '}
                <strong style={{ color: '#10b981' }}>
                  +{response.benchmark.runtime_improvement_percent?.toFixed(1)}%
                </strong>
              </div>
              <div>
                <span style={{ color: 'var(--text-muted)' }}>Vector Embedding:</span>{' '}
                <strong style={{ color: '#a78bfa' }}>Generated (128-dim)</strong>
              </div>
            </div>
          </div>

          <div className="card">
            <div className="card-header">
              <div className="card-title">Empirical Benchmark Results (Stage 8)</div>
            </div>
            <BenchmarkComparisonView benchmark={response.benchmark} />
          </div>
        </div>
      )}
    </div>
  );
};
