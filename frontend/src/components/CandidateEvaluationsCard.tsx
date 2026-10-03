import React, { useState } from 'react';
import { CandidateEvaluation, OptimizationRecommendation } from '../types/api';
import {
  Zap,
  Shield,
  CheckCircle2,
  AlertTriangle,
  Award,
  Layers,
  ArrowRight,
  TrendingDown,
  Info,
} from 'lucide-react';

interface CandidateEvaluationsCardProps {
  evaluations: CandidateEvaluation[];
  query: string;
  onRequestApproval: (rec: OptimizationRecommendation) => void;
}

export const CandidateEvaluationsCard: React.FC<CandidateEvaluationsCardProps> = ({
  evaluations = [],
  query,
  onRequestApproval,
}) => {
  const [selectedIdx, setSelectedIdx] = useState<number>(0);

  if (!evaluations || evaluations.length === 0) {
    return null;
  }

  const activeCandidate = evaluations[selectedIdx] || evaluations[0];
  const hypo = activeCandidate.hypopg_result;
  const safety = activeCandidate.safety_assessment;
  const comp = hypo?.comparison;

  return (
    <div className="card" style={{ borderLeft: '4px solid var(--accent-cyan)' }}>
      {/* Header */}
      <div className="card-header">
        <div>
          <div className="card-title">
            <Award size={18} style={{ color: 'var(--accent-cyan)' }} />
            <span>Outcome-Aware Candidate Evaluations ({evaluations.length} Evaluated)</span>
          </div>
          <div className="card-subtitle">
            Simulated via HypoPG counterfactual planner & audited against 7 deterministic safety gates
          </div>
        </div>
        <span className="badge badge-cyan">Multi-Candidate Ranking</span>
      </div>

      {/* Candidate Selector Tabs / Badges */}
      <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginBottom: '16px' }}>
        {evaluations.map((cand, idx) => {
          const isSelected = idx === selectedIdx;
          const isPrimary = cand.is_primary;
          const costImp = cand.hypopg_result?.comparison?.cost_improvement_percent;
          const isVal = cand.hypopg_result?.verdict === 'validated';

          return (
            <button
              key={idx}
              onClick={() => setSelectedIdx(idx)}
              style={{
                padding: '8px 14px',
                borderRadius: '8px',
                border: isSelected
                  ? '1px solid var(--accent-cyan)'
                  : '1px solid var(--border-medium)',
                backgroundColor: isSelected
                  ? 'rgba(6, 182, 212, 0.15)'
                  : 'var(--bg-card-subtle)',
                color: isSelected ? '#a5f3fc' : 'var(--text-secondary)',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                transition: 'all 0.15s ease',
              }}
            >
              {isPrimary && (
                <span
                  style={{
                    backgroundColor: '#06b6d4',
                    color: '#080a0f',
                    fontSize: '9.5px',
                    fontWeight: 700,
                    padding: '1px 5px',
                    borderRadius: '3px',
                    textTransform: 'uppercase',
                  }}
                >
                  Primary
                </span>
              )}
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: '12px', fontWeight: 600 }}>
                Candidate {idx + 1}: {cand.columns.length > 0 ? cand.columns.join(', ') : 'Analyze'}
              </span>
              {costImp !== undefined && isVal && (
                <span style={{ fontSize: '11px', color: '#34d399', fontWeight: 600 }}>
                  -{costImp.toFixed(0)}%
                </span>
              )}
            </button>
          );
        })}
      </div>

      {/* Selected Candidate Details Box */}
      <div
        style={{
          backgroundColor: 'var(--bg-card-subtle)',
          border: '1px solid var(--border-subtle)',
          borderRadius: '10px',
          padding: '18px',
          display: 'flex',
          flexDirection: 'column',
          gap: '14px',
        }}
      >
        {/* Candidate Title & Badges */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '10px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span
              style={{
                padding: '4px 8px',
                borderRadius: '6px',
                backgroundColor: activeCandidate.is_primary ? 'rgba(6, 182, 212, 0.2)' : 'rgba(148, 163, 184, 0.1)',
                color: activeCandidate.is_primary ? '#22d3ee' : 'var(--text-secondary)',
                fontSize: '11px',
                fontWeight: 700,
                textTransform: 'uppercase',
                display: 'flex',
                alignItems: 'center',
                gap: '4px',
              }}
            >
              {activeCandidate.is_primary ? (
                <>
                  <Award size={13} />
                  <span>Primary Selected Candidate</span>
                </>
              ) : (
                <span>Alternative Candidate</span>
              )}
            </span>
            <span style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
              Method: <strong>{activeCandidate.index_method || 'BTREE'}</strong>
            </span>
          </div>

          <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
            <span
              className={`badge ${
                hypo?.verdict === 'validated'
                  ? 'badge-green'
                  : hypo?.verdict === 'no_improvement'
                  ? 'badge-amber'
                  : 'badge-red'
              }`}
            >
              HypoPG: {hypo?.verdict?.toUpperCase() || 'UNKNOWN'}
            </span>

            <span
              className={`badge ${
                safety?.overall_status === 'passed'
                  ? 'badge-green'
                  : safety?.overall_status === 'warning'
                  ? 'badge-amber'
                  : 'badge-red'
              }`}
            >
              Safety: {safety?.overall_status?.toUpperCase() || 'EVALUATED'}
            </span>
          </div>
        </div>

        {/* SQL Preview Box */}
        <div>
          <div style={{ fontSize: '11.5px', color: 'var(--text-muted)', marginBottom: '4px', fontWeight: 600 }}>
            CANDIDATE DDL STATEMENT
          </div>
          <div className="sql-box">{activeCandidate.candidate_index}</div>
        </div>

        {/* Counterfactual Simulation Metrics */}
        {comp && (
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))',
              gap: '12px',
              padding: '12px 14px',
              backgroundColor: 'rgba(0, 0, 0, 0.3)',
              borderRadius: '8px',
            }}
          >
            <div>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Original Cost</div>
              <div style={{ fontSize: '14px', fontFamily: 'var(--font-mono)', color: '#f1f5f9' }}>
                {comp.original_cost.toFixed(2)}
              </div>
            </div>

            <div>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Hypothetical Cost</div>
              <div style={{ fontSize: '14px', fontFamily: 'var(--font-mono)', color: '#60a5fa' }}>
                {comp.hypothetical_cost.toFixed(2)}
              </div>
            </div>

            <div>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Cost Improvement</div>
              <div
                style={{
                  fontSize: '14px',
                  fontFamily: 'var(--font-mono)',
                  fontWeight: 700,
                  color: comp.cost_improvement_percent > 0 ? '#34d399' : '#f87171',
                }}
              >
                {comp.cost_improvement_percent > 0 ? '-' : '+'}
                {Math.abs(comp.cost_improvement_percent).toFixed(1)}%
              </div>
            </div>

            <div>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Plan Transformation</div>
              <div style={{ fontSize: '12px', color: '#93c5fd' }}>
                {comp.original_scan_type || 'Seq Scan'} &rarr; {comp.hypothetical_scan_type || 'Index Scan'}
              </div>
            </div>
          </div>
        )}

        {/* Safety Gate Summary */}
        {safety && (
          <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '4px' }}>
              <Shield size={14} style={{ color: safety.overall_status === 'passed' ? '#10b981' : '#f59e0b' }} />
              <strong>Safety Gate Assessment:</strong>
              <span>
                Risk Level: <strong>{safety.safety_level?.toUpperCase()}</strong> &bull;{' '}
                {safety.eligible_for_approval
                  ? 'Eligible for Human Authorization'
                  : 'Blocked by Safety Policy'}
              </span>
            </div>
            {safety.tradeoffs && safety.tradeoffs.length > 0 && (
              <div style={{ color: 'var(--text-muted)', fontSize: '11.5px', marginTop: '2px' }}>
                Tradeoff: {safety.tradeoffs[0]}
              </div>
            )}
          </div>
        )}

        {/* Action Button */}
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '4px' }}>
          <button
            className="btn btn-primary btn-sm"
            onClick={() => onRequestApproval(activeCandidate.recommendation)}
            disabled={!safety?.eligible_for_approval}
          >
            <Shield size={14} />
            <span>
              Request Approval for Candidate {selectedIdx + 1}
              {activeCandidate.is_primary ? ' (Recommended)' : ''}
            </span>
          </button>
        </div>
      </div>
    </div>
  );
};
