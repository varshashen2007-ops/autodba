import React, { useState } from 'react';
import { SimilarCase, MemorySearchResponse } from '../types/api';
import { api } from '../services/api';
import { BrainCircuit, Search, Sparkles, AlertTriangle, Layers, Database, History } from 'lucide-react';
import { RAGHistoricalCases } from '../components/RAGHistoricalCases';

export const IntelligenceView: React.FC = () => {
  const [searchQuery, setSearchQuery] = useState('SELECT * FROM orders WHERE customer_id = 42;');
  const [incidentType, setIncidentType] = useState('missing_index');
  const [similarityThreshold, setSimilarityThreshold] = useState(0.0);
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<SimilarCase[]>([]);
  const [hasSearched, setHasSearched] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSearch = async () => {
    if (!searchQuery.trim()) return;

    try {
      setLoading(true);
      setError(null);
      const res: MemorySearchResponse = await api.searchMemories({
        query: searchQuery.trim(),
        incident_type: incidentType || undefined,
        limit: 5,
        similarity_threshold: similarityThreshold,
      });
      setResults(res.results);
      setHasSearched(true);
    } catch (err: any) {
      setError(err.message || 'Search failed');
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
              <BrainCircuit size={18} style={{ color: 'var(--accent-purple)' }} />
              <span>Historical RAG Intelligence & Semantic Case Matching</span>
            </div>
            <div className="card-subtitle">
              Retrieves empirically verified optimization outcomes to ground LLM reasoning in real database evidence
            </div>
          </div>
          <span className="badge badge-purple">Cosine Similarity RAG</span>
        </div>

        <div style={{ marginBottom: '16px' }}>
          <label className="label">Search Query or Incident Pattern</label>
          <div style={{ display: 'flex', gap: '10px' }}>
            <input
              type="text"
              className="input font-mono"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="e.g. SELECT * FROM orders WHERE customer_id = 42;"
            />
            <button
              className="btn btn-purple"
              onClick={handleSearch}
              disabled={loading || !searchQuery.trim()}
              style={{ flexShrink: 0, minWidth: '150px' }}
            >
              <Search size={16} />
              <span>{loading ? 'Searching...' : 'Find Matches'}</span>
            </button>
          </div>
        </div>

        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
            gap: '14px',
            padding: '12px 16px',
            backgroundColor: 'var(--bg-card-subtle)',
            borderRadius: '8px',
            border: '1px solid var(--border-subtle)',
          }}
        >
          <div>
            <label className="label" style={{ marginBottom: '4px' }}>Incident Type Bias</label>
            <select
              className="select"
              value={incidentType}
              onChange={(e) => setIncidentType(e.target.value)}
              style={{ padding: '6px 10px' }}
            >
              <option value="missing_index">missing_index</option>
              <option value="filtered_seq_scan">filtered_seq_scan</option>
              <option value="expensive_sort">expensive_sort</option>
              <option value="expensive_nested_loop">expensive_nested_loop</option>
              <option value="unknown">all incident types</option>
            </select>
          </div>

          <div>
            <label className="label" style={{ marginBottom: '4px' }}>
              Minimum Similarity: <strong>{Math.round(similarityThreshold * 100)}%</strong>
            </label>
            <input
              type="range"
              min="0"
              max="0.9"
              step="0.05"
              value={similarityThreshold}
              onChange={(e) => setSimilarityThreshold(parseFloat(e.target.value))}
              style={{ width: '100%', accentColor: 'var(--accent-purple)' }}
            />
          </div>
        </div>

        {error && (
          <div
            style={{
              marginTop: '14px',
              padding: '12px 16px',
              borderRadius: '8px',
              backgroundColor: 'rgba(239, 68, 68, 0.1)',
              border: '1px solid var(--accent-red-border)',
              color: '#f87171',
              fontSize: '13px',
            }}
          >
            {error}
          </div>
        )}
      </div>

      {/* Architecture Explanation Card */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
          gap: '16px',
        }}
      >
        <div className="card">
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
            <Layers size={16} style={{ color: 'var(--accent-blue)' }} />
            <h4 style={{ fontSize: '14px', fontWeight: 600 }}>Local Deterministic Embeddings</h4>
          </div>
          <p style={{ fontSize: '12.5px', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
            AutoDBA employs a deterministic hash-based embedding service that operates with zero external network dependencies.
            Embeddings capture normalized SQL tokens, incident classes, and table relations into continuous vector space.
          </p>
        </div>

        <div className="card">
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
            <Sparkles size={16} style={{ color: 'var(--accent-purple)' }} />
            <h4 style={{ fontSize: '14px', fontWeight: 600 }}>Grounded LLM Reasoning</h4>
          </div>
          <p style={{ fontSize: '12.5px', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
            Retrieved historical cases are injected directly into Groq Llama 3.3 context windows.
            The LLM synthesizes evidence from both the live PostgreSQL EXPLAIN plan and previous measured outcomes.
          </p>
        </div>

        <div className="card">
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
            <History size={16} style={{ color: 'var(--accent-green)' }} />
            <h4 style={{ fontSize: '14px', fontWeight: 600 }}>Closed-Loop Learning</h4>
          </div>
          <p style={{ fontSize: '12.5px', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
            Whenever a human-approved remediation is physically benchmarked, the empirical result is automatically vectorized
            and stored into PostgreSQL, making subsequent diagnoses progressively smarter.
          </p>
        </div>
      </div>

      {/* RAG Results */}
      {hasSearched && (
        <div className="card" style={{ borderLeft: '4px solid var(--accent-purple)' }}>
          <RAGHistoricalCases cases={results} retrievalThreshold={similarityThreshold} />
        </div>
      )}
    </div>
  );
};
