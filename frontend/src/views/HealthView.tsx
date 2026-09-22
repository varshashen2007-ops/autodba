import React, { useState } from 'react';
import { HealthResponse, SlowQuery } from '../types/api';
import { api } from '../services/api';
import { HeartPulse, Database, Activity, CheckCircle2, RefreshCw, Cpu, Layers } from 'lucide-react';

interface HealthViewProps {
  health: HealthResponse | null;
  slowQueries: SlowQuery[];
  onRefresh: () => void;
}

export const HealthView: React.FC<HealthViewProps> = ({ health, slowQueries, onRefresh }) => {
  const [minTime, setMinTime] = useState(0.0);
  const [limit, setLimit] = useState(20);
  const [loading, setLoading] = useState(false);
  const [queries, setQueries] = useState<SlowQuery[]>(slowQueries);

  const isConnected = health?.database === 'connected';

  const handleFilter = async () => {
    try {
      setLoading(true);
      const res = await api.getSlowQueries(limit, minTime);
      setQueries(res.queries);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      {/* DB Connection & Extension Status */}
      <div className="card">
        <div className="card-header">
          <div>
            <div className="card-title">
              <Database size={18} style={{ color: isConnected ? '#10b981' : '#ef4444' }} />
              <span>PostgreSQL Observability & Extension Status</span>
            </div>
            <div className="card-subtitle">
              Hardware, server engine version, and active PostgreSQL extension catalog
            </div>
          </div>
          <button className="btn btn-secondary btn-sm" onClick={onRefresh}>
            <RefreshCw size={13} />
            <span>Refresh Telemetry</span>
          </button>
        </div>

        <div className="metrics-grid">
          <div className="metric-card">
            <div className="metric-label">Connectivity</div>
            <div className="metric-value" style={{ fontSize: '20px', color: isConnected ? '#10b981' : '#ef4444' }}>
              {isConnected ? 'ONLINE' : 'OFFLINE'}
            </div>
            <div className="metric-meta">SQLAlchemy sync pool</div>
          </div>

          <div className="metric-card">
            <div className="metric-label">Engine Version</div>
            <div className="metric-value" style={{ fontSize: '15px' }}>
              {health?.version ? health.version.split(' ')[0] + ' ' + health.version.split(' ')[1] : 'PostgreSQL 17'}
            </div>
            <div className="metric-meta">Linux x86_64 container</div>
          </div>

          <div className="metric-card">
            <div className="metric-label">Installed Extensions</div>
            <div className="metric-value" style={{ fontSize: '18px', color: '#60a5fa' }}>
              {health?.extensions?.length || 0} Active
            </div>
            <div className="metric-meta">
              {health?.extensions ? health.extensions.join(', ') : 'None'}
            </div>
          </div>
        </div>
      </div>

      {/* pg_stat_statements Detailed Table */}
      <div className="card">
        <div className="card-header">
          <div>
            <div className="card-title">
              <Activity size={18} style={{ color: 'var(--accent-blue)' }} />
              <span>pg_stat_statements Telemetry Table</span>
            </div>
            <div className="card-subtitle">
              Normalized query execution statistics collected directly from the database engine
            </div>
          </div>
        </div>

        <div
          style={{
            display: 'flex',
            gap: '14px',
            alignItems: 'center',
            marginBottom: '16px',
            flexWrap: 'wrap',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <label className="label" style={{ margin: 0 }}>Min Execution Time (ms):</label>
            <input
              type="number"
              className="input"
              style={{ width: '90px', padding: '6px 10px' }}
              value={minTime}
              onChange={(e) => setMinTime(parseFloat(e.target.value) || 0)}
              step="0.5"
            />
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <label className="label" style={{ margin: 0 }}>Max Queries:</label>
            <input
              type="number"
              className="input"
              style={{ width: '80px', padding: '6px 10px' }}
              value={limit}
              onChange={(e) => setLimit(parseInt(e.target.value) || 10)}
            />
          </div>

          <button className="btn btn-secondary btn-sm" onClick={handleFilter} disabled={loading}>
            <span>Filter</span>
          </button>
        </div>

        <div className="table-container">
          <table className="table">
            <thead>
              <tr>
                <th>Normalized SQL</th>
                <th>Calls</th>
                <th>Total Time</th>
                <th>Mean Latency</th>
                <th>Rows Returned</th>
                <th>Cache Hits / Reads</th>
              </tr>
            </thead>
            <tbody>
              {queries.length === 0 ? (
                <tr>
                  <td colSpan={6} style={{ textAlign: 'center', color: 'var(--text-muted)' }}>
                    No queries found meeting criteria
                  </td>
                </tr>
              ) : (
                queries.map((q, i) => (
                  <tr key={i}>
                    <td style={{ maxWidth: '300px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      <code style={{ fontSize: '11.5px', color: '#93c5fd' }}>{q.query}</code>
                    </td>
                    <td style={{ fontFamily: 'var(--font-mono)' }}>{q.calls.toLocaleString()}</td>
                    <td style={{ fontFamily: 'var(--font-mono)' }}>{q.total_time_ms.toFixed(2)} ms</td>
                    <td
                      style={{
                        fontFamily: 'var(--font-mono)',
                        color: q.mean_time_ms > 10 ? '#f87171' : '#34d399',
                        fontWeight: 600,
                      }}
                    >
                      {q.mean_time_ms.toFixed(3)} ms
                    </td>
                    <td style={{ fontFamily: 'var(--font-mono)' }}>{q.rows.toLocaleString()}</td>
                    <td style={{ fontFamily: 'var(--font-mono)', fontSize: '11.5px', color: 'var(--text-muted)' }}>
                      {q.shared_blks_hit} / {q.shared_blks_read}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
