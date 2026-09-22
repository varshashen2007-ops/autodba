import React, { useState } from 'react';
import { ApprovalRequest } from '../types/api';
import { ShieldCheck, ShieldAlert, Check, X, Clock, User, AlertTriangle, CheckCircle2 } from 'lucide-react';
import { ApprovalModal } from '../components/ApprovalModal';

interface ApprovalsViewProps {
  approvals: ApprovalRequest[];
  onRefresh: () => void;
  onSelectForRemediation?: (approval: ApprovalRequest) => void;
}

export const ApprovalsView: React.FC<ApprovalsViewProps> = ({
  approvals,
  onRefresh,
  onSelectForRemediation,
}) => {
  const [selectedRequest, setSelectedRequest] = useState<ApprovalRequest | null>(null);
  const [filter, setFilter] = useState<'all' | 'pending' | 'approved' | 'rejected' | 'expired'>('all');

  const filtered = approvals.filter((a) => {
    if (filter === 'all') return true;
    return a.status.toLowerCase() === filter;
  });

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      <div className="card">
        <div className="card-header">
          <div>
            <div className="card-title">
              <ShieldCheck size={18} style={{ color: 'var(--accent-blue)' }} />
              <span>Human Approval & Safety Gate</span>
            </div>
            <div className="card-subtitle">
              Every database DDL modification requires explicit human approval backed by a 7-rule safety assessment
            </div>
          </div>

          <div style={{ display: 'flex', gap: '6px' }}>
            {(['all', 'pending', 'approved', 'rejected', 'expired'] as const).map((tab) => (
              <button
                key={tab}
                className={`btn btn-sm ${filter === tab ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => setFilter(tab)}
              >
                {tab.toUpperCase()}
              </button>
            ))}
          </div>
        </div>

        {filtered.length === 0 ? (
          <div style={{ padding: '32px', textAlign: 'center', color: 'var(--text-muted)' }}>
            <ShieldCheck size={36} style={{ color: 'var(--border-medium)', margin: '0 auto 10px' }} />
            <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>No approval requests in this category</div>
            <div style={{ fontSize: '12.5px', marginTop: '4px' }}>
              Run an investigation and click &ldquo;Request Human Approval&rdquo; on an eligible recommendation.
            </div>
          </div>
        ) : (
          <div className="table-container">
            <table className="table">
              <thead>
                <tr>
                  <th>Approval ID</th>
                  <th>Target Table / Index</th>
                  <th>Status</th>
                  <th>Risk / Confidence</th>
                  <th>Actor / Date</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((req) => {
                  const isPending = req.status === 'pending';
                  const isApproved = req.status === 'approved';
                  const isRejected = req.status === 'rejected';

                  let statusBadge = 'badge-neutral';
                  if (isPending) statusBadge = 'badge-amber';
                  if (isApproved) statusBadge = 'badge-green';
                  if (isRejected) statusBadge = 'badge-red';

                  return (
                    <tr key={req.approval_id}>
                      <td style={{ fontFamily: 'var(--font-mono)', fontSize: '12px' }}>
                        <span style={{ color: '#60a5fa' }}>{req.approval_id}</span>
                      </td>
                      <td>
                        <div style={{ fontWeight: 600, fontSize: '13px' }}>
                          {req.recommendation?.title || 'Index Recommendation'}
                        </div>
                        <div
                          style={{
                            fontSize: '11px',
                            fontFamily: 'var(--font-mono)',
                            color: 'var(--text-muted)',
                            maxWidth: '280px',
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                            whiteSpace: 'nowrap',
                          }}
                        >
                          {req.recommendation?.sql_preview}
                        </div>
                      </td>
                      <td>
                        <span className={`badge ${statusBadge}`}>{req.status.toUpperCase()}</span>
                      </td>
                      <td>
                        <div style={{ display: 'flex', gap: '4px' }}>
                          <span className="badge badge-neutral" style={{ fontSize: '10.5px' }}>
                            risk: {req.recommendation?.risk}
                          </span>
                          <span className="badge badge-neutral" style={{ fontSize: '10.5px' }}>
                            conf: {req.recommendation?.confidence}
                          </span>
                        </div>
                      </td>
                      <td style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                        {isApproved && (
                          <div style={{ display: 'flex', alignItems: 'center', gap: '4px', color: '#34d399' }}>
                            <User size={13} />
                            <span>{req.approved_by}</span>
                          </div>
                        )}
                        {isRejected && (
                          <div style={{ color: '#f87171' }}>
                            Rejected: {req.rejection_reason}
                          </div>
                        )}
                        <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                          {new Date(req.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                        </div>
                      </td>
                      <td>
                        <div style={{ display: 'flex', gap: '8px' }}>
                          <button
                            className="btn btn-secondary btn-sm"
                            onClick={() => setSelectedRequest(req)}
                          >
                            {isPending ? 'Review Safety...' : 'View Audit'}
                          </button>

                          {isApproved && onSelectForRemediation && (
                            <button
                              className="btn btn-primary btn-sm"
                              onClick={() => onSelectForRemediation(req)}
                            >
                              Remediate →
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {selectedRequest && (
        <ApprovalModal
          request={selectedRequest}
          onClose={() => setSelectedRequest(null)}
          onActionComplete={() => {
            onRefresh();
            setSelectedRequest(null);
          }}
        />
      )}
    </div>
  );
};
