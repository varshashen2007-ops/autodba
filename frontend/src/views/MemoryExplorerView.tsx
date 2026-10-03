import React, { useState } from 'react';
import { MemoryListItem, OptimizationMemory } from '../types/api';
import { api } from '../services/api';
import { History, Search, Database, Layers, Eye, X, CheckCircle2, TrendingUp, ShieldCheck } from 'lucide-react';

interface MemoryExplorerViewProps {
  memories: MemoryListItem[];
  onRefresh: () => void;
}

export const MemoryExplorerView: React.FC<MemoryExplorerViewProps> = ({ memories, onRefresh }) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedIncidentType, setSelectedIncidentType] = useState('all');
  const [selectedOutcome, setSelectedOutcome] = useState('all');
  const [selectedVerificationState, setSelectedVerificationState] = useState('all');
  const [activeMemory, setActiveMemory] = useState<OptimizationMemory | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);

  const filtered = memories.filter((m) => {
    const matchesSearch =
      !searchTerm ||
      m.query_text.toLowerCase().includes(searchTerm.toLowerCase()) ||
      m.incident_type.toLowerCase().includes(searchTerm.toLowerCase()) ||
      m.id.toString() === searchTerm.trim();

    const matchesType =
      selectedIncidentType === 'all' || m.incident_type.toLowerCase() === selectedIncidentType;

    const matchesOutcome =
      selectedOutcome === 'all' || m.outcome.toLowerCase() === selectedOutcome;

    const matchesVerification =
      selectedVerificationState === 'all' ||
      (selectedVerificationState === 'verified_measured' &&
        (m.verification_state === 'verified_measured' || m.is_verified)) ||
      (selectedVerificationState === 'synthetic' &&
        (m.verification_state === 'synthetic' || m.provenance === 'seeded')) ||
      (selectedVerificationState === 'unverified' &&
        (m.verification_state === 'unverified' || (!m.is_verified && m.provenance !== 'seeded')));

    return matchesSearch && matchesType && matchesOutcome && matchesVerification;
  });

  const handleViewDetail = async (id: number) => {
    try {
      setLoadingDetail(true);
      const mem = await api.getMemory(id);
      setActiveMemory(mem);
    } catch (err) {
      console.error(err);
    } finally {
      setLoadingDetail(false);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      <div className="card">
        <div className="card-header">
          <div>
            <div className="card-title">
              <History size={18} style={{ color: 'var(--accent-blue)' }} />
              <span>Optimization Memory Corpus Explorer</span>
            </div>
            <div className="card-subtitle">
              Persistent repository of historical optimization episodes stored in PostgreSQL
            </div>
          </div>
          <span className="badge badge-blue">{memories.length} Total Records</span>
        </div>

        {/* Filters */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
            gap: '14px',
            marginBottom: '16px',
          }}
        >
          <div>
            <label className="label">Filter by SQL / Text</label>
            <input
              type="text"
              className="input font-mono"
              placeholder="e.g. orders, customer_id..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
            />
          </div>

          <div>
            <label className="label">Incident Type</label>
            <select
              className="select"
              value={selectedIncidentType}
              onChange={(e) => setSelectedIncidentType(e.target.value)}
            >
              <option value="all">All Incident Types</option>
              <option value="missing_index">missing_index</option>
              <option value="filtered_seq_scan">filtered_seq_scan</option>
              <option value="expensive_sort">expensive_sort</option>
              <option value="expensive_nested_loop">expensive_nested_loop</option>
              <option value="large_row_estimate">large_row_estimate</option>
            </select>
          </div>

          <div>
            <label className="label">Outcome</label>
            <select
              className="select"
              value={selectedOutcome}
              onChange={(e) => setSelectedOutcome(e.target.value)}
            >
              <option value="all">All Outcomes</option>
              <option value="success">success</option>
              <option value="no_improvement">no_improvement</option>
              <option value="regression">regression</option>
            </select>
          </div>

          <div>
            <label className="label">Verification State</label>
            <select
              className="select"
              value={selectedVerificationState}
              onChange={(e) => setSelectedVerificationState(e.target.value)}
            >
              <option value="all">All States</option>
              <option value="verified_measured">Verified Measured Only</option>
              <option value="synthetic">Seeded / Synthetic Only</option>
              <option value="unverified">Unverified Only</option>
            </select>
          </div>
        </div>

        {/* Memories Table */}
        <div className="table-container">
          <table className="table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Incident Type</th>
                <th>Query Text</th>
                <th>Outcome</th>
                <th>Verification State</th>
                <th>Outcome Summary</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 ? (
                <tr>
                  <td colSpan={7} style={{ textAlign: 'center', color: 'var(--text-muted)' }}>
                    No memories found matching current filters
                  </td>
                </tr>
              ) : (
                filtered.map((m) => (
                  <tr key={m.id}>
                    <td style={{ fontFamily: 'var(--font-mono)', fontSize: '12px', color: '#60a5fa' }}>
                      #{m.id}
                    </td>
                    <td>
                      <span className="badge badge-purple" style={{ fontSize: '11px' }}>
                        {m.incident_type}
                      </span>
                    </td>
                    <td style={{ maxWidth: '300px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      <code style={{ fontSize: '11.5px', color: '#93c5fd' }}>{m.query_text}</code>
                    </td>
                    <td>
                      <span className={`badge ${m.outcome === 'success' ? 'badge-green' : 'badge-amber'}`}>
                        {m.outcome}
                      </span>
                    </td>
                    <td>
                      {m.verification_state === 'verified_measured' || m.is_verified ? (
                        <span className="badge badge-green" style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', fontSize: '10.5px' }}>
                          <ShieldCheck size={11} />
                          <span>VERIFIED MEASURED</span>
                        </span>
                      ) : m.verification_state === 'synthetic' || m.provenance === 'seeded' ? (
                        <span className="badge badge-purple" style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', fontSize: '10.5px' }}>
                          <Database size={11} />
                          <span>SEEDED</span>
                        </span>
                      ) : (
                        <span className="badge badge-neutral" style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', fontSize: '10.5px' }}>
                          <span>UNVERIFIED</span>
                        </span>
                      )}
                    </td>
                    <td style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                      {m.outcome_summary || 'Empirical benchmark verified'}
                    </td>
                    <td>
                      <button
                        className="btn btn-secondary btn-sm"
                        onClick={() => handleViewDetail(m.id)}
                      >
                        <Eye size={13} />
                        <span>Inspect</span>
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Memory Detail Modal */}
      {activeMemory && (
        <div className="modal-overlay" onClick={() => setActiveMemory(null)}>
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
                  <Database size={18} />
                </span>
                <div>
                  <div style={{ fontSize: '16px', fontWeight: 600, color: 'var(--text-primary)' }}>
                    Memory Record #{activeMemory.id}
                  </div>
                  <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                    type: {activeMemory.incident_type} • outcome: {activeMemory.outcome}
                  </div>
                </div>
              </div>

              <button
                onClick={() => setActiveMemory(null)}
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

            <div className="modal-body" style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))',
                  gap: '10px',
                  padding: '12px',
                  backgroundColor: 'rgba(0, 0, 0, 0.3)',
                  borderRadius: '8px',
                  fontSize: '12px',
                }}
              >
                <div>
                  <span style={{ color: 'var(--text-muted)' }}>Provenance:</span>{' '}
                  <strong style={{ color: '#60a5fa', textTransform: 'uppercase' }}>
                    {activeMemory.provenance || 'unverified'}
                  </strong>
                </div>
                <div>
                  <span style={{ color: 'var(--text-muted)' }}>Verification State:</span>{' '}
                  <strong
                    style={{
                      color:
                        activeMemory.verification_state === 'verified_measured' || activeMemory.is_verified
                          ? '#34d399'
                          : activeMemory.verification_state === 'synthetic'
                          ? '#a78bfa'
                          : '#fbbf24',
                      textTransform: 'uppercase',
                    }}
                  >
                    {activeMemory.verification_state || (activeMemory.is_verified ? 'verified_measured' : 'unverified')}
                  </strong>
                </div>
                <div>
                  <span style={{ color: 'var(--text-muted)' }}>Empirical Benchmark:</span>{' '}
                  <strong style={{ color: activeMemory.is_verified ? '#34d399' : 'var(--text-muted)' }}>
                    {activeMemory.is_verified ? 'VERIFIED' : 'UNVERIFIED'}
                  </strong>
                </div>
              </div>

              <div>
                <label className="label">Normalized SQL Query</label>
                <div className="sql-box">{activeMemory.query_text}</div>
              </div>

              {activeMemory.recommendation && (
                <div>
                  <label className="label">Stored Recommendation</label>
                  <div className="sql-box">{activeMemory.recommendation.sql_preview || JSON.stringify(activeMemory.recommendation, null, 2)}</div>
                </div>
              )}

              {activeMemory.benchmark && (
                <div>
                  <label className="label">Stored Benchmark Telemetry</label>
                  <div
                    style={{
                      padding: '12px',
                      borderRadius: '8px',
                      backgroundColor: 'rgba(16, 185, 129, 0.08)',
                      border: '1px solid var(--accent-green-border)',
                      fontSize: '12.5px',
                      fontFamily: 'var(--font-mono)',
                      color: '#34d399',
                    }}
                  >
                    <pre style={{ margin: 0 }}>{JSON.stringify(activeMemory.benchmark, null, 2)}</pre>
                  </div>
                </div>
              )}
            </div>

            <div className="modal-footer">
              <button className="btn btn-secondary" onClick={() => setActiveMemory(null)}>
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
