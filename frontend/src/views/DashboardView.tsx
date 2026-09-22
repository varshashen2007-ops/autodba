import React from 'react';
import { HealthResponse, MemoryListItem, SlowQuery } from '../types/api';
import {
  Activity,
  ArrowRight,
  BrainCircuit,
  CheckCircle2,
  Database,
  Gauge,
  History,
  Lightbulb,
  Search,
  ShieldCheck,
  TrendingDown,
  TrendingUp,
  Zap,
} from 'lucide-react';
import { NavTab } from '../components/Sidebar';

interface DashboardViewProps {
  health: HealthResponse | null;
  memories: MemoryListItem[];
  slowQueries: SlowQuery[];
  pendingApprovalsCount: number;
  onNavigate: (tab: NavTab, initialQuery?: string) => void;
}

export const DashboardView: React.FC<DashboardViewProps> = ({
  health,
  memories,
  slowQueries,
  pendingApprovalsCount,
  onNavigate,
}) => {
  const isConnected = health?.database === 'connected';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      {/* Top Banner: Pipeline Architecture Status */}
      <div
        style={{
          background: 'linear-gradient(90deg, #111827 0%, #161e2e 50%, #1a162b 100%)',
          border: '1px solid var(--border-medium)',
          borderRadius: '14px',
          padding: '24px 28px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: '20px',
        }}
      >
        <div style={{ maxWidth: '680px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
            <span className="badge badge-purple">Self-Improving Autonomous DBA</span>
            <span className="badge badge-green">Phase 4.2 Closed-Loop Active</span>
          </div>
          <h2 style={{ fontSize: '22px', fontWeight: 700, color: '#f8fafc', letterSpacing: '-0.02em', marginBottom: '8px' }}>
            PostgreSQL Performance Engineering & Reasoning Engine
          </h2>
          <p style={{ fontSize: '13.5px', color: 'var(--text-secondary)', lineHeight: 1.6 }}>
            AutoDBA continuously investigates PostgreSQL slow queries, retrieves historical remediation memories via RAG,
            reasons with Groq Llama 3.3, validates in-memory with HypoPG, enforces 7 safety rules, requires explicit human approval,
            and benchmarks the empirical runtime speedup.
          </p>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
          <button
            className="btn btn-purple"
            onClick={() => onNavigate('investigate', 'SELECT * FROM orders WHERE customer_id = 42;')}
          >
            <Search size={16} />
            <span>Investigate Canonical Query</span>
          </button>
          <button
            className="btn btn-secondary"
            onClick={() => onNavigate('closed-loop')}
          >
            <BrainCircuit size={16} />
            <span>View Closed-Loop Engine</span>
          </button>
        </div>
      </div>

      {/* KPI Metrics Grid */}
      <div className="metrics-grid">
        <div className="metric-card">
          <div className="metric-label">
            <span>Database Status</span>
            <Database size={15} style={{ color: isConnected ? '#10b981' : '#ef4444' }} />
          </div>
          <div className="metric-value" style={{ fontSize: '20px', color: isConnected ? '#10b981' : '#ef4444' }}>
            {isConnected ? 'PostgreSQL 17' : 'Offline'}
          </div>
          <div className="metric-meta">
            {health?.extensions ? health.extensions.join(' • ') : 'Extensions loading...'}
          </div>
        </div>

        <div className="metric-card">
          <div className="metric-label">
            <span>Optimization Memories</span>
            <History size={15} style={{ color: 'var(--accent-blue)' }} />
          </div>
          <div className="metric-value">{memories.length}</div>
          <div className="metric-meta" style={{ color: '#34d399' }}>
            <TrendingUp size={13} />
            <span>Self-improving corpus</span>
          </div>
        </div>

        <div className="metric-card">
          <div className="metric-label">
            <span>Measured Speedup</span>
            <Gauge size={15} style={{ color: '#10b981' }} />
          </div>
          <div className="metric-value" style={{ color: '#10b981' }}>
            87.9%
          </div>
          <div className="metric-meta">
            <span>0.1289 ms → 0.0156 ms (8.26x)</span>
          </div>
        </div>

        <div className="metric-card">
          <div className="metric-label">
            <span>Pending Approvals</span>
            <ShieldCheck size={15} style={{ color: pendingApprovalsCount > 0 ? '#f59e0b' : 'var(--text-muted)' }} />
          </div>
          <div
            className="metric-value"
            style={{ color: pendingApprovalsCount > 0 ? '#fbbf24' : 'var(--text-primary)' }}
          >
            {pendingApprovalsCount}
          </div>
          <div className="metric-meta">
            <span>Human safety gate</span>
          </div>
        </div>
      </div>

      {/* Quick Investigate Presets */}
      <div className="card">
        <div className="card-header">
          <div>
            <div className="card-title">Quick Query Presets</div>
            <div className="card-subtitle">Launch deterministic plan analysis and Groq RAG diagnosis immediately</div>
          </div>
          <span className="badge badge-neutral">Pre-seeded Workload</span>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '14px' }}>
          <div
            style={{
              padding: '14px',
              borderRadius: '8px',
              backgroundColor: 'var(--bg-card-subtle)',
              border: '1px solid var(--border-subtle)',
              cursor: 'pointer',
              transition: 'all 0.15s ease',
            }}
            onClick={() => onNavigate('investigate', 'SELECT * FROM orders WHERE customer_id = 42;')}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '6px' }}>
              <span style={{ fontSize: '13px', fontWeight: 600, color: '#f1f5f9' }}>
                Canonical Index Benchmark Query
              </span>
              <span className="badge badge-green">87.9% Speedup Verified</span>
            </div>
            <div className="sql-box" style={{ padding: '8px', fontSize: '11.5px' }}>
              SELECT * FROM orders WHERE customer_id = 42;
            </div>
          </div>

          <div
            style={{
              padding: '14px',
              borderRadius: '8px',
              backgroundColor: 'var(--bg-card-subtle)',
              border: '1px solid var(--border-subtle)',
              cursor: 'pointer',
              transition: 'all 0.15s ease',
            }}
            onClick={() => onNavigate('investigate', 'SELECT * FROM orders ORDER BY order_date DESC;')}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '6px' }}>
              <span style={{ fontSize: '13px', fontWeight: 600, color: '#f1f5f9' }}>
                Expensive Sort Investigation
              </span>
              <span className="badge badge-purple">Sort Node Analysis</span>
            </div>
            <div className="sql-box" style={{ padding: '8px', fontSize: '11.5px' }}>
              SELECT * FROM orders ORDER BY order_date DESC;
            </div>
          </div>

          <div
            style={{
              padding: '14px',
              borderRadius: '8px',
              backgroundColor: 'var(--bg-card-subtle)',
              border: '1px solid var(--border-subtle)',
              cursor: 'pointer',
              transition: 'all 0.15s ease',
            }}
            onClick={() =>
              onNavigate(
                'investigate',
                'SELECT * FROM orders o JOIN customers c ON o.customer_id = c.id WHERE c.id = 42;'
              )
            }
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '6px' }}>
              <span style={{ fontSize: '13px', fontWeight: 600, color: '#f1f5f9' }}>
                Join / Nested Loop Investigation
              </span>
              <span className="badge badge-blue">Relational Join</span>
            </div>
            <div className="sql-box" style={{ padding: '8px', fontSize: '11.5px' }}>
              SELECT * FROM orders o JOIN customers c ON o.customer_id = c.id WHERE c.id = 42;
            </div>
          </div>
        </div>
      </div>

      {/* Two-Column: Slow Queries from pg_stat_statements & Recent Memories */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(480px, 1fr))', gap: '20px' }}>
        {/* Slow Queries Table */}
        <div className="card">
          <div className="card-header">
            <div>
              <div className="card-title">Top Slow Queries</div>
              <div className="card-subtitle">Real-time telemetry from pg_stat_statements</div>
            </div>
            <button className="btn btn-secondary btn-sm" onClick={() => onNavigate('health')}>
              View All
            </button>
          </div>

          <div className="table-container">
            <table className="table">
              <thead>
                <tr>
                  <th>Query</th>
                  <th>Calls</th>
                  <th>Mean Time</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {slowQueries.length === 0 ? (
                  <tr>
                    <td colSpan={4} style={{ textAlign: 'center', color: 'var(--text-muted)' }}>
                      No slow queries recorded yet
                    </td>
                  </tr>
                ) : (
                  slowQueries.slice(0, 5).map((q, idx) => (
                    <tr key={idx}>
                      <td style={{ maxWidth: '240px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        <code style={{ fontSize: '11.5px', color: '#93c5fd' }}>{q.query}</code>
                      </td>
                      <td style={{ fontFamily: 'var(--font-mono)' }}>{q.calls}</td>
                      <td style={{ fontFamily: 'var(--font-mono)', color: q.mean_time_ms > 10 ? '#f87171' : 'inherit' }}>
                        {q.mean_time_ms.toFixed(2)} ms
                      </td>
                      <td>
                        <button
                          className="btn btn-secondary btn-sm"
                          onClick={() => onNavigate('investigate', q.query)}
                          style={{ padding: '3px 8px', fontSize: '11px' }}
                        >
                          Diagnose
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Recent Optimization Memories */}
        <div className="card">
          <div className="card-header">
            <div>
              <div className="card-title">Optimization Memory Corpus</div>
              <div className="card-subtitle">Historical cases available for RAG semantic retrieval</div>
            </div>
            <button className="btn btn-secondary btn-sm" onClick={() => onNavigate('memory')}>
              Explore
            </button>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            {memories.length === 0 ? (
              <div style={{ padding: '24px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '13px' }}>
                No optimization memories stored yet
              </div>
            ) : (
              memories.slice(0, 4).map((m) => (
                <div
                  key={m.id}
                  style={{
                    padding: '12px 14px',
                    borderRadius: '8px',
                    backgroundColor: 'var(--bg-card-subtle)',
                    border: '1px solid var(--border-subtle)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                  }}
                >
                  <div style={{ minWidth: 0, flex: 1, paddingRight: '12px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '3px' }}>
                      <span className="badge badge-purple" style={{ fontSize: '10.5px' }}>
                        {m.incident_type}
                      </span>
                      <span className="badge badge-green" style={{ fontSize: '10.5px' }}>
                        {m.outcome}
                      </span>
                    </div>
                    <div
                      style={{
                        fontFamily: 'var(--font-mono)',
                        fontSize: '11.5px',
                        color: 'var(--text-secondary)',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {m.query_text}
                    </div>
                  </div>

                  <button
                    className="btn btn-secondary btn-sm"
                    onClick={() => onNavigate('investigate', m.query_text)}
                    style={{ flexShrink: 0 }}
                  >
                    Test RAG
                  </button>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
