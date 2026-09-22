import React from 'react';
import { BottleneckFinding } from '../types/api';
import { AlertCircle, AlertTriangle, Info, CheckCircle2 } from 'lucide-react';

interface BottleneckListProps {
  findings: BottleneckFinding[];
}

export const BottleneckList: React.FC<BottleneckListProps> = ({ findings }) => {
  if (!findings || findings.length === 0) {
    return (
      <div
        style={{
          padding: '24px',
          textAlign: 'center',
          backgroundColor: 'var(--bg-card-subtle)',
          borderRadius: '10px',
          border: '1px solid var(--border-subtle)',
        }}
      >
        <CheckCircle2 size={32} style={{ color: '#10b981', margin: '0 auto 8px' }} />
        <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>
          No Severe Bottlenecks Detected
        </div>
        <div style={{ fontSize: '12.5px', color: 'var(--text-muted)', marginTop: '4px' }}>
          PostgreSQL execution plan satisfies deterministic cost and index heuristic thresholds.
        </div>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
      {findings.map((f, i) => {
        const isHigh = f.severity === 'high';
        const isMedium = f.severity === 'medium';

        return (
          <div
            key={i}
            style={{
              padding: '16px',
              borderRadius: '10px',
              backgroundColor: isHigh
                ? 'rgba(239, 68, 68, 0.05)'
                : isMedium
                ? 'rgba(245, 158, 11, 0.05)'
                : 'var(--bg-card)',
              border: isHigh
                ? '1px solid var(--accent-red-border)'
                : isMedium
                ? '1px solid var(--accent-amber-border)'
                : '1px solid var(--border-subtle)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                {isHigh ? (
                  <AlertCircle size={16} style={{ color: '#ef4444' }} />
                ) : isMedium ? (
                  <AlertTriangle size={16} style={{ color: '#f59e0b' }} />
                ) : (
                  <Info size={16} style={{ color: '#3b82f6' }} />
                )}
                <span style={{ fontWeight: 600, color: 'var(--text-primary)', fontSize: '14px' }}>
                  {f.title}
                </span>
                {f.relation && (
                  <span
                    style={{
                      fontFamily: 'var(--font-mono)',
                      fontSize: '11px',
                      backgroundColor: 'rgba(59, 130, 246, 0.1)',
                      color: '#60a5fa',
                      padding: '2px 6px',
                      borderRadius: '4px',
                    }}
                  >
                    table: {f.relation}
                  </span>
                )}
              </div>

              <div style={{ display: 'flex', gap: '6px' }}>
                <span
                  className={`badge ${
                    isHigh ? 'badge-red' : isMedium ? 'badge-amber' : 'badge-neutral'
                  }`}
                >
                  severity: {f.severity}
                </span>
                <span className="badge badge-neutral">confidence: {f.confidence}</span>
              </div>
            </div>

            <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '8px', lineHeight: 1.5 }}>
              {f.description}
            </p>

            <div
              style={{
                fontSize: '12px',
                color: 'var(--text-muted)',
                backgroundColor: 'rgba(0, 0, 0, 0.25)',
                padding: '8px 12px',
                borderRadius: '6px',
                fontFamily: 'var(--font-mono)',
              }}
            >
              <strong>Impact:</strong> {f.estimated_impact}
            </div>
          </div>
        );
      })}
    </div>
  );
};
