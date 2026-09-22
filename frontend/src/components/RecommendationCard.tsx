import React, { useState } from 'react';
import { OptimizationRecommendation, HypoPGValidationResult } from '../types/api';
import { Lightbulb, Shield, CheckCircle2, AlertTriangle, ArrowRight, Zap, Play } from 'lucide-react';
import { api } from '../services/api';

interface RecommendationCardProps {
  recommendation: OptimizationRecommendation;
  query: string;
  onRequestApproval?: (rec: OptimizationRecommendation) => void;
  onValidated?: (result: HypoPGValidationResult) => void;
}

export const RecommendationCard: React.FC<RecommendationCardProps> = ({
  recommendation,
  query,
  onRequestApproval,
  onValidated,
}) => {
  const [validating, setValidating] = useState(false);
  const [valResult, setValResult] = useState<HypoPGValidationResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleValidateHypoPG = async () => {
    try {
      setValidating(true);
      setError(null);
      const res = await api.validateCandidate(
        query,
        recommendation.sql_preview,
        recommendation.relation
      );
      setValResult(res);
      if (onValidated) onValidated(res);
    } catch (err: any) {
      setError(err.message || 'HypoPG validation failed');
    } finally {
      setValidating(false);
    }
  };

  const isLowRisk = recommendation.risk === 'low';
  const isHighConf = recommendation.confidence === 'high';

  return (
    <div
      style={{
        backgroundColor: 'var(--bg-card)',
        border: '1px solid var(--border-medium)',
        borderRadius: '12px',
        padding: '20px',
        position: 'relative',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: '12px' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
            <span
              style={{
                width: '28px',
                height: '28px',
                borderRadius: '8px',
                backgroundColor: 'rgba(59, 130, 246, 0.15)',
                color: '#60a5fa',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <Lightbulb size={16} />
            </span>
            <h3 style={{ fontSize: '16px', fontWeight: 600, color: 'var(--text-primary)' }}>
              {recommendation.title}
            </h3>
          </div>
          <p style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>{recommendation.summary}</p>
        </div>

        <div style={{ display: 'flex', gap: '6px' }}>
          <span className={`badge ${isHighConf ? 'badge-green' : 'badge-amber'}`}>
            confidence: {recommendation.confidence}
          </span>
          <span className={`badge ${isLowRisk ? 'badge-blue' : 'badge-red'}`}>
            risk: {recommendation.risk}
          </span>
          <span className="badge badge-purple">
            status: {recommendation.status}
          </span>
        </div>
      </div>

      <div style={{ margin: '14px 0' }}>
        <div style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-muted)', marginBottom: '6px' }}>
          RECOMMENDED REMEDIATION (SQL PREVIEW ONLY)
        </div>
        <div className="sql-box">{recommendation.sql_preview}</div>
      </div>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
          gap: '12px',
          padding: '12px',
          backgroundColor: 'rgba(0, 0, 0, 0.25)',
          borderRadius: '8px',
          marginBottom: '16px',
          fontSize: '12.5px',
        }}
      >
        <div>
          <span style={{ color: 'var(--text-muted)' }}>Target Relation:</span>{' '}
          <strong style={{ color: '#60a5fa', fontFamily: 'var(--font-mono)' }}>{recommendation.relation}</strong>
        </div>
        <div>
          <span style={{ color: 'var(--text-muted)' }}>Target Columns:</span>{' '}
          <strong style={{ color: '#a78bfa', fontFamily: 'var(--font-mono)' }}>
            {recommendation.columns?.join(', ') || 'N/A'}
          </strong>
        </div>
        <div>
          <span style={{ color: 'var(--text-muted)' }}>Optimization Type:</span>{' '}
          <strong style={{ color: 'var(--text-primary)' }}>{recommendation.optimization_type}</strong>
        </div>
      </div>

      {/* HypoPG Result if validated */}
      {valResult && (
        <div
          style={{
            padding: '14px',
            borderRadius: '8px',
            backgroundColor:
              valResult.verdict === 'validated'
                ? 'rgba(16, 185, 129, 0.08)'
                : 'rgba(239, 68, 68, 0.08)',
            border:
              valResult.verdict === 'validated'
                ? '1px solid var(--accent-green-border)'
                : '1px solid var(--accent-red-border)',
            marginBottom: '16px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '6px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontWeight: 600 }}>
              <Zap size={15} style={{ color: valResult.verdict === 'validated' ? '#10b981' : '#ef4444' }} />
              <span>HypoPG Counterfactual Verdict: {valResult.verdict.toUpperCase()}</span>
            </div>
            {valResult.comparison && (
              <span className="badge badge-green">
                -{valResult.comparison.cost_improvement_percent.toFixed(1)}% cost reduction
              </span>
            )}
          </div>
          {valResult.comparison && (
            <div style={{ fontSize: '12px', color: 'var(--text-secondary)', display: 'flex', gap: '16px' }}>
              <span>Original Cost: {valResult.comparison.original_cost.toFixed(2)}</span>
              <span>Hypothetical Cost: {valResult.comparison.hypothetical_cost.toFixed(2)}</span>
              <span>Plan Changed: {valResult.comparison.plan_changed ? 'Yes' : 'No'}</span>
            </div>
          )}
        </div>
      )}

      {error && (
        <div
          style={{
            padding: '10px 14px',
            borderRadius: '8px',
            backgroundColor: 'rgba(239, 68, 68, 0.1)',
            border: '1px solid var(--accent-red-border)',
            color: '#f87171',
            fontSize: '12.5px',
            marginBottom: '14px',
          }}
        >
          {error}
        </div>
      )}

      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: '10px' }}>
        <button
          className="btn btn-secondary btn-sm"
          onClick={handleValidateHypoPG}
          disabled={validating}
        >
          {validating ? 'Simulating in HypoPG...' : 'Run HypoPG Simulation'}
        </button>

        {onRequestApproval && (
          <button
            className="btn btn-primary btn-sm"
            onClick={() => onRequestApproval(recommendation)}
          >
            <Shield size={14} />
            <span>Request Human Approval</span>
          </button>
        )}
      </div>
    </div>
  );
};
