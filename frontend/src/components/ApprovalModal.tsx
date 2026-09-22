import React, { useState } from 'react';
import { ApprovalRequest, SafetyCheck } from '../types/api';
import { ShieldCheck, ShieldAlert, X, Check, AlertCircle, Clock, User, CheckCircle2 } from 'lucide-react';
import { api } from '../services/api';

interface ApprovalModalProps {
  request: ApprovalRequest;
  onClose: () => void;
  onActionComplete: (updated: ApprovalRequest) => void;
}

export const ApprovalModal: React.FC<ApprovalModalProps> = ({
  request,
  onClose,
  onActionComplete,
}) => {
  const [approverName, setApproverName] = useState('');
  const [rejectReason, setRejectReason] = useState('');
  const [isRejecting, setIsRejecting] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const assessment = request.safety_assessment;
  const checks: SafetyCheck[] = assessment?.checks || [];

  const handleApprove = async () => {
    if (!approverName.trim()) {
      setError('Please provide an approver name (anonymous approvals are forbidden).');
      return;
    }

    try {
      setLoading(true);
      setError(null);
      const res = await api.approveRequest(request.approval_id, approverName.trim());
      onActionComplete(res);
      onClose();
    } catch (err: any) {
      setError(err.message || 'Failed to approve request');
    } finally {
      setLoading(false);
    }
  };

  const handleReject = async () => {
    if (!rejectReason.trim()) {
      setError('Please provide a reason for rejecting the request.');
      return;
    }

    try {
      setLoading(true);
      setError(null);
      const res = await api.rejectRequest(request.approval_id, rejectReason.trim());
      onActionComplete(res);
      onClose();
    } catch (err: any) {
      setError(err.message || 'Failed to reject request');
    } finally {
      setLoading(false);
    }
  };

  const isPending = request.status === 'pending';

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <span
              style={{
                width: '32px',
                height: '32px',
                borderRadius: '8px',
                backgroundColor: 'rgba(59, 130, 246, 0.15)',
                color: '#60a5fa',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <ShieldCheck size={18} />
            </span>
            <div>
              <div style={{ fontSize: '16px', fontWeight: 600, color: 'var(--text-primary)' }}>
                Human Approval Review
              </div>
              <div style={{ fontSize: '12px', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                {request.approval_id} • status: {request.status.toUpperCase()}
              </div>
            </div>
          </div>

          <button
            onClick={onClose}
            style={{
              background: 'none',
              border: 'none',
              color: 'var(--text-muted)',
              cursor: 'pointer',
              display: 'flex',
            }}
          >
            <X size={20} />
          </button>
        </div>

        <div className="modal-body" style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {/* Target recommendation info */}
          <div
            style={{
              backgroundColor: 'rgba(0, 0, 0, 0.25)',
              border: '1px solid var(--border-subtle)',
              borderRadius: '8px',
              padding: '14px',
            }}
          >
            <div style={{ fontSize: '14px', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '4px' }}>
              {request.recommendation?.title || 'Index Recommendation'}
            </div>
            <div style={{ fontSize: '12.5px', color: 'var(--text-secondary)', marginBottom: '8px' }}>
              {request.recommendation?.summary}
            </div>
            <div className="sql-box">{request.recommendation?.sql_preview}</div>
          </div>

          {/* Safety Assessment Summary */}
          <div>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
              <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)' }}>
                Safety Gate Assessment (7 Automated Checks)
              </span>
              <span className={`badge ${assessment?.overall_status === 'passed' ? 'badge-green' : 'badge-amber'}`}>
                {assessment?.overall_status?.toUpperCase() || 'EVALUATED'}
              </span>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              {checks.map((chk, i) => (
                <div
                  key={i}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '8px 12px',
                    borderRadius: '6px',
                    backgroundColor: 'rgba(255, 255, 255, 0.02)',
                    border: '1px solid var(--border-subtle)',
                    fontSize: '12px',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    {chk.status === 'passed' ? (
                      <CheckCircle2 size={14} style={{ color: '#10b981' }} />
                    ) : (
                      <AlertCircle size={14} style={{ color: '#f59e0b' }} />
                    )}
                    <span style={{ color: 'var(--text-primary)', fontWeight: 500 }}>{chk.check_name}</span>
                  </div>
                  <span style={{ color: 'var(--text-muted)' }}>{chk.message}</span>
                </div>
              ))}
            </div>
          </div>

          {error && (
            <div
              style={{
                padding: '10px 14px',
                borderRadius: '8px',
                backgroundColor: 'rgba(239, 68, 68, 0.1)',
                border: '1px solid var(--accent-red-border)',
                color: '#f87171',
                fontSize: '12.5px',
              }}
            >
              {error}
            </div>
          )}

          {/* Action Inputs if Pending */}
          {isPending && (
            <div
              style={{
                marginTop: '8px',
                paddingTop: '16px',
                borderTop: '1px solid var(--border-subtle)',
                display: 'flex',
                flexDirection: 'column',
                gap: '12px',
              }}
            >
              {!isRejecting ? (
                <div>
                  <label className="label">Approver Full Name / Employee ID (Required)</label>
                  <input
                    type="text"
                    className="input"
                    placeholder="e.g., Alex Johnson (Staff DBA)"
                    value={approverName}
                    onChange={(e) => setApproverName(e.target.value)}
                  />
                  <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '4px' }}>
                    Explicit authorization will be permanently recorded in the audit snapshot.
                  </div>
                </div>
              ) : (
                <div>
                  <label className="label">Rejection Rationale (Required)</label>
                  <textarea
                    className="textarea"
                    rows={2}
                    placeholder="e.g., Write amplification concern on high-throughput orders table..."
                    value={rejectReason}
                    onChange={(e) => setRejectReason(e.target.value)}
                  />
                </div>
              )}
            </div>
          )}
        </div>

        <div className="modal-footer">
          {isPending ? (
            <>
              {!isRejecting ? (
                <>
                  <button
                    className="btn btn-secondary btn-sm"
                    onClick={() => setIsRejecting(true)}
                  >
                    Reject...
                  </button>
                  <button
                    className="btn btn-success"
                    onClick={handleApprove}
                    disabled={loading}
                  >
                    <Check size={16} />
                    <span>{loading ? 'Approving...' : 'Explicitly Approve'}</span>
                  </button>
                </>
              ) : (
                <>
                  <button
                    className="btn btn-secondary btn-sm"
                    onClick={() => setIsRejecting(false)}
                  >
                    Cancel
                  </button>
                  <button
                    className="btn btn-danger"
                    onClick={handleReject}
                    disabled={loading}
                  >
                    <span>{loading ? 'Rejecting...' : 'Confirm Rejection'}</span>
                  </button>
                </>
              )}
            </>
          ) : (
            <button className="btn btn-secondary" onClick={onClose}>
              Close
            </button>
          )}
        </div>
      </div>
    </div>
  );
};
