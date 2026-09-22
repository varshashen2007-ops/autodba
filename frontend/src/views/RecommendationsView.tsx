import React, { useState } from 'react';
import { OptimizationRecommendation, HypoPGValidationResult } from '../types/api';
import { api } from '../services/api';
import { Lightbulb, Search, Zap, Shield, CheckCircle2, AlertCircle, ArrowRight } from 'lucide-react';
import { RecommendationCard } from '../components/RecommendationCard';

interface RecommendationsViewProps {
  onRequestApproval: (rec: OptimizationRecommendation) => void;
}

export const RecommendationsView: React.FC<RecommendationsViewProps> = ({ onRequestApproval }) => {
  const [query, setQuery] = useState('SELECT * FROM orders WHERE customer_id = 42;');
  const [recommendations, setRecommendations] = useState<OptimizationRecommendation[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleGenerate = async () => {
    if (!query.trim()) return;
    try {
      setLoading(true);
      setError(null);
      const res = await api.generateRecommendations(query.trim());
      setRecommendations(res.recommendations);
      if (res.recommendations.length === 0) {
        setError('No recommendations generated for this query. The plan may already be optimal or does not have high-cost filtered scans.');
      }
    } catch (err: any) {
      setError(err.message || 'Failed to generate recommendations');
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
              <Lightbulb size={18} style={{ color: 'var(--accent-blue)' }} />
              <span>Optimization Recommendation Engine</span>
            </div>
            <div className="card-subtitle">
              Generates deterministic candidate indexes based on PostgreSQL plan bottlenecks and predicate analysis
            </div>
          </div>
        </div>

        <div style={{ marginBottom: '14px' }}>
          <label className="label">Target Query to Analyze</label>
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
              onClick={handleGenerate}
              disabled={loading || !query.trim()}
              style={{ flexShrink: 0 }}
            >
              <Search size={16} />
              <span>{loading ? 'Analyzing...' : 'Generate Recommendations'}</span>
            </button>
          </div>
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
            }}
          >
            {error}
          </div>
        )}
      </div>

      {recommendations.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div style={{ fontSize: '14px', fontWeight: 600, color: 'var(--text-primary)' }}>
            Generated Recommendations ({recommendations.length})
          </div>

          {recommendations.map((rec, index) => (
            <RecommendationCard
              key={index}
              recommendation={rec}
              query={query}
              onRequestApproval={onRequestApproval}
            />
          ))}
        </div>
      )}
    </div>
  );
};
