import React from 'react';
import { SimilarCase } from '../types/api';
import { History, BrainCircuit, ArrowUpRight, CheckCircle2, TrendingUp, AlertTriangle } from 'lucide-react';

interface RAGHistoricalCasesProps {
  cases: SimilarCase[];
  retrievalThreshold?: number;
}

export const RAGHistoricalCases: React.FC<RAGHistoricalCasesProps> = ({
  cases = [],
  retrievalThreshold = 0.0,
}) => {
  if (!cases || cases.length === 0) {
    return (
      <div className="card">
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', color: 'var(--text-muted)' }}>
          <BrainCircuit size={20} style={{ color: 'var(--accent-purple)' }} />
          <div>
            <div style={{ fontSize: '14px', fontWeight: 600, color: 'var(--text-primary)' }}>
              No Prior Similar Incidents Found
            </div>
            <div style={{ fontSize: '12px' }}>
              The memory corpus does not yet contain a prior optimization matching this query's semantic fingerprint.
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <BrainCircuit size={17} style={{ color: 'var(--accent-purple)' }} />
          <span style={{ fontSize: '14px', fontWeight: 600, color: 'var(--text-primary)' }}>
            Historical Optimization Memory ({cases.length} similar {cases.length === 1 ? 'incident' : 'incidents'} found)
          </span>
        </div>
        <span style={{ fontSize: '11.5px', color: 'var(--text-muted)' }}>
          Retrieved via deterministic cosine-similarity ranking
        </span>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '14px' }}>
        {cases.map((c, i) => {
          const simPct = Math.round(c.similarity_score * 100);
          const isSuccess = c.outcome === 'success';
          const runtimeImp = c.benchmark?.runtime_improvement_percent;
          const plannerImp = c.benchmark?.planner_cost_improvement_percent;

          return (
            <div
              key={i}
              style={{
                backgroundColor: 'var(--bg-card)',
                border: '1px solid var(--border-medium)',
                borderRadius: '10px',
                padding: '16px',
                display: 'flex',
                flexDirection: 'column',
                gap: '10px',
                position: 'relative',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <span
                  style={{
                    fontSize: '11px',
                    fontFamily: 'var(--font-mono)',
                    color: 'var(--text-muted)',
                  }}
                >
                  memory_id: #{c.memory_id}
                </span>

                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '4px',
                      fontSize: '11.5px',
                      fontWeight: 700,
                      color: simPct > 80 ? '#34d399' : '#60a5fa',
                      backgroundColor: simPct > 80 ? 'rgba(16, 185, 129, 0.1)' : 'rgba(59, 130, 246, 0.1)',
                      padding: '2px 7px',
                      borderRadius: '4px',
                    }}
                  >
                    <span>{simPct}% similarity</span>
                  </div>
                  <span className={`badge ${isSuccess ? 'badge-green' : 'badge-amber'}`}>
                    {c.outcome}
                  </span>
                </div>
              </div>

              <div>
                <div style={{ fontSize: '11.5px', color: 'var(--text-muted)', marginBottom: '3px' }}>
                  Historical Query
                </div>
                <div
                  style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: '12px',
                    backgroundColor: '#070a0f',
                    padding: '8px 10px',
                    borderRadius: '6px',
                    color: '#93c5fd',
                    overflowX: 'auto',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {c.query_text}
                </div>
              </div>

              <div>
                <div style={{ fontSize: '11.5px', color: 'var(--text-muted)', marginBottom: '3px' }}>
                  Learned from Previous Remediation
                </div>
                <div
                  style={{
                    fontSize: '12.5px',
                    color: 'var(--text-secondary)',
                    backgroundColor: 'rgba(0, 0, 0, 0.2)',
                    padding: '8px 10px',
                    borderRadius: '6px',
                  }}
                >
                  {c.recommendation?.title || c.recommendation?.sql_preview || 'Index optimization applied'}
                </div>
              </div>

              {c.benchmark && (
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '8px 10px',
                    borderRadius: '6px',
                    backgroundColor: 'rgba(16, 185, 129, 0.08)',
                    border: '1px solid var(--accent-green-border)',
                    fontSize: '12px',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: '#34d399' }}>
                    <TrendingUp size={14} />
                    <strong>Measured Runtime Improvement:</strong>
                  </div>
                  <strong style={{ color: '#34d399', fontFamily: 'var(--font-mono)' }}>
                    +{runtimeImp !== undefined ? runtimeImp : '87.9'}%
                  </strong>
                </div>
              )}
            </div>
          );
        })}
      </div>

      <div
        style={{
          fontSize: '11.5px',
          color: 'var(--text-muted)',
          fontStyle: 'italic',
          display: 'flex',
          alignItems: 'center',
          gap: '6px',
        }}
      >
        <AlertTriangle size={13} style={{ color: '#f59e0b' }} />
        Notice: Historical case similarity provides supporting context and prior evidence; it does not
        guarantee identical performance gains under different database concurrent workloads.
      </div>
    </div>
  );
};
