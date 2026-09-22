import React, { useState } from 'react';
import { ApprovalRequest, RemediationResult } from '../types/api';
import { api } from '../services/api';
import { Wrench, CheckCircle2, AlertTriangle, ShieldCheck, Play, RotateCcw, Database } from 'lucide-react';

interface RemediationViewProps {
  approvals: ApprovalRequest[];
  onRefreshApprovals: () => void;
  onNavigateToBenchmark?: (query: string) => void;
}

export const RemediationView: React.FC<RemediationViewProps> = ({
  approvals,
  onRefreshApprovals,
  onNavigateToBenchmark,
}) => {
  const [selectedApprovalId, setSelectedApprovalId] = useState<string>(
    approvals.find((a) => a.status === 'approved')?.approval_id || ''
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [remediationResult, setRemediationResult] = useState<RemediationResult | null>(null);

  const approvedList = approvals.filter((a) => a.status === 'approved');

  const handleApply = async () => {
    if (!selectedApprovalId) {
      setError('Please select an approved request to remediate.');
      return;
    }

    try {
      setLoading(true);
      setError(null);
      const res = await api.applyRemediation(selectedApprovalId);
      setRemediationResult(res);
      onRefreshApprovals();
    } catch (err: any) {
      setError(err.message || 'Remediation failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      <div className="card">
        <div className="card-header">
          <div>
            <div className="card-title">
              <Wrench size={18} style={{ color: 'var(--accent-blue)' }} />
              <span>Controlled Physical Remediation</span>
            </div>
            <div className="card-subtitle">
              Applies approved DDL changes inside transactional blocks with post-DDL index verification in PostgreSQL
            </div>
          </div>
          <span className="badge badge-green">Idempotent Execution</span>
        </div>

        <div style={{ marginBottom: '16px' }}>
          <label className="label">Select Approved Authorization</label>
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
              No requests are currently in APPROVED status. Go to the Approvals Gate and grant authorization first.
            </div>
          ) : (
            <div style={{ display: 'flex', gap: '10px' }}>
              <select
                className="select"
                value={selectedApprovalId}
                onChange={(e) => setSelectedApprovalId(e.target.value)}
              >
                {approvedList.map((a) => (
                  <option key={a.approval_id} value={a.approval_id}>
                    {a.approval_id} — {a.recommendation?.title} (Approved by {a.approved_by})
                  </option>
                ))}
              </select>

              <button
                className="btn btn-primary"
                onClick={handleApply}
                disabled={loading || !selectedApprovalId}
                style={{ flexShrink: 0, minWidth: '160px' }}
              >
                {loading ? (
                  <>
                    <RotateCcw size={16} className="animate-spin" />
                    <span>Executing DDL...</span>
                  </>
                ) : (
                  <>
                    <Wrench size={16} />
                    <span>Apply Remediation</span>
                  </>
                )}
              </button>
            </div>
          )}
        </div>

        {error && (
          <div
            style={{
              padding: '12px 16px',
              borderRadius: '8px',
              backgroundColor: 'rgba(239, 68, 68, 0.1)',
              border: '1px solid var(--accent-red-border)',
              color: '#f87171',
              fontSize: '13px',
              marginBottom: '14px',
            }}
          >
            {error}
          </div>
        )}
      </div>

      {remediationResult && (
        <div className="card" style={{ borderLeft: '4px solid var(--accent-green)' }}>
          <div className="card-header">
            <div>
              <div className="card-title">
                <CheckCircle2 size={18} style={{ color: '#10b981' }} />
                <span>Remediation Outcome: {remediationResult.status.toUpperCase()}</span>
              </div>
              <div className="card-subtitle">
                remediation_id: {remediationResult.remediation_id} • Target table: {remediationResult.target_relation}
              </div>
            </div>
            <span className="badge badge-green">
              {remediationResult.verification_passed ? 'Verified in pg_indexes' : 'Verification Pending'}
            </span>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
            <div>
              <div style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-muted)', marginBottom: '4px' }}>
                EXECUTED DDL STATEMENT
              </div>
              <div className="sql-box">{remediationResult.sql_executed}</div>
            </div>

            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
                gap: '12px',
                padding: '12px',
                backgroundColor: 'rgba(0, 0, 0, 0.25)',
                borderRadius: '8px',
                fontSize: '12.5px',
              }}
            >
              <div>
                <span style={{ color: 'var(--text-muted)' }}>Resulting Index:</span>{' '}
                <strong style={{ color: '#34d399', fontFamily: 'var(--font-mono)' }}>
                  {remediationResult.index_name}
                </strong>
              </div>
              <div>
                <span style={{ color: 'var(--text-muted)' }}>Status:</span>{' '}
                <strong style={{ color: '#60a5fa' }}>{remediationResult.status}</strong>
              </div>
              <div>
                <span style={{ color: 'var(--text-muted)' }}>Verification Passed:</span>{' '}
                <strong style={{ color: '#34d399' }}>{remediationResult.verification_passed ? 'Yes' : 'No'}</strong>
              </div>
            </div>

            {onNavigateToBenchmark && (
              <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '6px' }}>
                <button
                  className="btn btn-success"
                  onClick={() => onNavigateToBenchmark('SELECT * FROM orders WHERE customer_id = 42;')}
                >
                  <span>Proceed to Real Benchmark Comparison →</span>
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
