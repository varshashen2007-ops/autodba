import React, { useState } from 'react';
import { BenchmarkResult } from '../types/api';
import { api } from '../services/api';
import { Gauge, Play, RotateCcw, AlertCircle, Info, Database } from 'lucide-react';
import { BenchmarkComparisonView } from '../components/BenchmarkComparisonView';

interface BenchmarksViewProps {
  initialQuery?: string;
}

export const BenchmarksView: React.FC<BenchmarksViewProps> = ({
  initialQuery = 'SELECT * FROM orders WHERE customer_id = 42;',
}) => {
  const [query, setQuery] = useState(initialQuery);
  const [runs, setRuns] = useState(10);
  const [warmupRuns, setWarmupRuns] = useState(2);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<BenchmarkResult | null>(null);

  const handleRunBenchmark = async () => {
    if (!query.trim()) return;

    try {
      setLoading(true);
      setError(null);
      const res = await api.runBenchmark(query.trim(), runs, warmupRuns);
      setResult(res);
    } catch (err: any) {
      setError(err.message || 'Benchmark execution failed');
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
              <Gauge size={18} style={{ color: 'var(--accent-blue)' }} />
              <span>Real PostgreSQL Runtime Benchmarking</span>
            </div>
            <div className="card-subtitle">
              Simulates baseline via session-local flags (enable_indexscan=off) to contrast Seq Scan against physical index performance
            </div>
          </div>
          <span className="badge badge-green">10 Runs + 2 Warmups</span>
        </div>

        <div style={{ marginBottom: '16px' }}>
          <label className="label">Benchmark Query</label>
          <div style={{ display: 'flex', gap: '10px' }}>
            <input
              type="text"
              className="input font-mono"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="SELECT * FROM orders WHERE customer_id = 42;"
            />
            <button
              className="btn btn-primary"
              onClick={handleRunBenchmark}
              disabled={loading || !query.trim()}
              style={{ flexShrink: 0, minWidth: '160px' }}
            >
              {loading ? (
                <>
                  <RotateCcw size={16} className="animate-spin" />
                  <span>Measuring...</span>
                </>
              ) : (
                <>
                  <Play size={16} />
                  <span>Run Benchmark</span>
                </>
              )}
            </button>
          </div>
        </div>

        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '16px',
            fontSize: '12.5px',
            color: 'var(--text-secondary)',
            backgroundColor: 'var(--bg-card-subtle)',
            padding: '10px 14px',
            borderRadius: '8px',
          }}
        >
          <Info size={16} style={{ color: '#60a5fa', flexShrink: 0 }} />
          <span>
            <strong>Experimental Rigor:</strong> Discards 2 initial warm-up runs to prime shared buffer caches.
            Executes 10 continuous iterations for robust mean, standard deviation, and median calculation.
          </span>
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

      {result && (
        <div className="card" style={{ borderLeft: '4px solid var(--accent-blue)' }}>
          <div className="card-header">
            <div>
              <div className="card-title">
                <Gauge size={18} style={{ color: '#10b981' }} />
                <span>Empirical Benchmark Outcome</span>
              </div>
              <div className="card-subtitle">
                benchmark_id: {result.benchmark_id} • status: {result.status.toUpperCase()}
              </div>
            </div>
            <span className="badge badge-green">Controlled Comparison</span>
          </div>

          <BenchmarkComparisonView benchmark={result} />
        </div>
      )}
    </div>
  );
};
