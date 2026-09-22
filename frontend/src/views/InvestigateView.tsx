import React, { useState, useEffect } from 'react';
import {
  DiagnoseResponse,
  OptimizationRecommendation,
  HypoPGValidationResult,
} from '../types/api';
import { api } from '../services/api';
import {
  Search,
  Sparkles,
  Zap,
  Play,
  RotateCcw,
  CheckCircle2,
  AlertCircle,
  BrainCircuit,
  Layers,
  Shield,
} from 'lucide-react';
import { ExecutionPlanViewer } from '../components/ExecutionPlanViewer';
import { BottleneckList } from '../components/BottleneckList';
import { RecommendationCard } from '../components/RecommendationCard';
import { AIExplanationPanel } from '../components/AIExplanationPanel';
import { RAGHistoricalCases } from '../components/RAGHistoricalCases';
import { NavTab } from '../components/Sidebar';

interface InvestigateViewProps {
  initialQuery?: string;
  onRequestApproval: (rec: OptimizationRecommendation) => void;
  onNavigate: (tab: NavTab) => void;
}

export const InvestigateView: React.FC<InvestigateViewProps> = ({
  initialQuery = 'SELECT * FROM orders WHERE customer_id = 42;',
  onRequestApproval,
  onNavigate,
}) => {
  const [query, setQuery] = useState(initialQuery);
  const [incidentType, setIncidentType] = useState('missing_index');
  const [includeRag, setIncludeRag] = useState(true);
  const [maxCases, setMaxCases] = useState(3);

  const [loading, setLoading] = useState(false);
  const [loadingStep, setLoadingStep] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<DiagnoseResponse | null>(null);

  useEffect(() => {
    if (initialQuery && initialQuery !== query) {
      setQuery(initialQuery);
    }
  }, [initialQuery]);

  const handleRunInvestigation = async (queryToRun = query) => {
    if (!queryToRun.trim()) {
      setError('Please provide a valid read-only SQL query to investigate.');
      return;
    }

    try {
      setLoading(true);
      setError(null);
      setResult(null);

      setLoadingStep('1/5 Validating SQL read-only safety with sql_validator...');
      await new Promise((r) => setTimeout(r, 200));

      setLoadingStep('2/5 Generating PostgreSQL EXPLAIN (FORMAT JSON) plan...');
      await new Promise((r) => setTimeout(r, 250));

      setLoadingStep('3/5 Running PlanAnalyzer & BottleneckDetector heuristics...');
      await new Promise((r) => setTimeout(r, 250));

      setLoadingStep('4/5 Retrieving similar historical memories via cosine similarity RAG...');
      await new Promise((r) => setTimeout(r, 250));

      setLoadingStep('5/5 Querying Groq · openai/gpt-oss-120b for evidence-grounded diagnosis...');

      const response = await api.diagnoseQuery({
        query: queryToRun.trim(),
        incident_type: incidentType || undefined,
        include_rag: includeRag,
        max_similar_cases: maxCases,
      });

      setResult(response);
    } catch (err: any) {
      setError(err.message || 'Failed to complete query investigation');
    } finally {
      setLoading(false);
      setLoadingStep('');
    }
  };

  const diagnosis = result?.diagnosis;
  const analysis = diagnosis?.analysis;
  const rootNode = analysis?.root_node;
  const rawPlan = analysis?.raw_plan;
  const findings = diagnosis?.findings || [];
  const recommendation = diagnosis?.recommendation as OptimizationRecommendation | null;
  const ragContext = diagnosis?.rag_context;
  const similarCases = ragContext?.similar_cases || [];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      {/* Query Input Section */}
      <div className="card">
        <div className="card-header">
          <div>
            <div className="card-title">
              <Search size={18} style={{ color: 'var(--accent-blue)' }} />
              <span>Query Performance Investigation Console</span>
            </div>
            <div className="card-subtitle">
              Enter any read-only PostgreSQL query to execute deterministic plan analysis + Groq RAG explanation
            </div>
          </div>

          <div style={{ display: 'flex', gap: '8px' }}>
            <button
              className="btn btn-secondary btn-sm"
              onClick={() => {
                const sample = 'SELECT * FROM orders WHERE customer_id = 42;';
                setQuery(sample);
                handleRunInvestigation(sample);
              }}
            >
              Load Canonical Experiment
            </button>
            <button
              className="btn btn-secondary btn-sm"
              onClick={() => {
                const sample = 'SELECT * FROM orders ORDER BY order_date DESC;';
                setQuery(sample);
                handleRunInvestigation(sample);
              }}
            >
              Load Sort Query
            </button>
          </div>
        </div>

        <div style={{ marginBottom: '14px' }}>
          <label className="label">PostgreSQL Query (SELECT only)</label>
          <textarea
            className="textarea"
            rows={3}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="SELECT * FROM orders WHERE customer_id = 42;"
            disabled={loading}
          />
        </div>

        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
            gap: '16px',
            alignItems: 'center',
            padding: '12px 16px',
            backgroundColor: 'var(--bg-card-subtle)',
            borderRadius: '8px',
            border: '1px solid var(--border-subtle)',
            marginBottom: '16px',
          }}
        >
          <div>
            <label className="label" style={{ marginBottom: '4px' }}>Incident Type Hint</label>
            <select
              className="select"
              value={incidentType}
              onChange={(e) => setIncidentType(e.target.value)}
              disabled={loading}
              style={{ padding: '6px 10px' }}
            >
              <option value="missing_index">missing_index</option>
              <option value="filtered_seq_scan">filtered_seq_scan</option>
              <option value="expensive_sort">expensive_sort</option>
              <option value="expensive_nested_loop">expensive_nested_loop</option>
              <option value="large_row_estimate">large_row_estimate</option>
              <option value="unknown">unknown (auto-infer)</option>
            </select>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <input
              type="checkbox"
              id="includeRag"
              checked={includeRag}
              onChange={(e) => setIncludeRag(e.target.checked)}
              disabled={loading}
              style={{ width: '16px', height: '16px', accentColor: 'var(--accent-purple)' }}
            />
            <label htmlFor="includeRag" style={{ fontSize: '13px', fontWeight: 500, color: 'var(--text-primary)', cursor: 'pointer' }}>
              Retrieve Historical RAG Memory
            </label>
          </div>

          {includeRag && (
            <div>
              <label className="label" style={{ marginBottom: '4px' }}>
                Max Historical Cases: <strong>{maxCases}</strong>
              </label>
              <input
                type="range"
                min="1"
                max="5"
                value={maxCases}
                onChange={(e) => setMaxCases(parseInt(e.target.value))}
                disabled={loading}
                style={{ width: '100%', accentColor: 'var(--accent-purple)' }}
              />
            </div>
          )}

          <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
            <button
              className="btn btn-purple"
              onClick={() => handleRunInvestigation()}
              disabled={loading || !query.trim()}
              style={{ minWidth: '170px' }}
            >
              {loading ? (
                <>
                  <RotateCcw size={16} className="animate-spin" />
                  <span>Investigating...</span>
                </>
              ) : (
                <>
                  <Sparkles size={16} />
                  <span>Run Full Investigation</span>
                </>
              )}
            </button>
          </div>
        </div>

        {/* Loading progress bar */}
        {loading && (
          <div
            style={{
              padding: '16px 20px',
              borderRadius: '8px',
              backgroundColor: 'rgba(139, 92, 246, 0.08)',
              border: '1px solid var(--accent-purple-border)',
              display: 'flex',
              alignItems: 'center',
              gap: '12px',
            }}
          >
            <div
              style={{
                width: '18px',
                height: '18px',
                border: '2px solid rgba(139, 92, 246, 0.3)',
                borderTopColor: '#a78bfa',
                borderRadius: '50%',
                animation: 'spin 1s linear infinite',
              }}
            />
            <div style={{ fontSize: '13.5px', color: '#c4b5fd', fontWeight: 500 }}>
              {loadingStep}
            </div>
          </div>
        )}

        {/* Error message */}
        {error && (
          <div
            style={{
              padding: '14px 18px',
              borderRadius: '8px',
              backgroundColor: 'rgba(239, 68, 68, 0.1)',
              border: '1px solid var(--accent-red-border)',
              color: '#f87171',
              fontSize: '13px',
              display: 'flex',
              alignItems: 'center',
              gap: '10px',
            }}
          >
            <AlertCircle size={18} style={{ flexShrink: 0 }} />
            <span>{error}</span>
          </div>
        )}
      </div>

      {/* Investigation Results Section */}
      {result && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
          {/* Top Summary Bar */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
              gap: '14px',
            }}
          >
            <div className="metric-card">
              <div className="metric-label">Incident Type</div>
              <div className="metric-value" style={{ fontSize: '18px', color: '#60a5fa' }}>
                {diagnosis?.incident_type}
              </div>
              <div className="metric-meta">Deterministic inference</div>
            </div>

            <div className="metric-card">
              <div className="metric-label">Bottlenecks Found</div>
              <div
                className="metric-value"
                style={{ fontSize: '18px', color: findings.length > 0 ? '#fbbf24' : '#10b981' }}
              >
                {findings.length}
              </div>
              <div className="metric-meta">Rule-based detection</div>
            </div>

            <div className="metric-card">
              <div className="metric-label">Root Estimated Cost</div>
              <div className="metric-value" style={{ fontSize: '18px', color: '#f1f5f9' }}>
                {rootNode?.total_cost?.toFixed(2) || (rawPlan && rawPlan[0]?.Plan?.['Total Cost']?.toFixed(2)) || 'N/A'}
              </div>
              <div className="metric-meta">Planner cost units</div>
            </div>

            <div className="metric-card">
              <div className="metric-label">Historical Cases</div>
              <div className="metric-value" style={{ fontSize: '18px', color: '#a78bfa' }}>
                {similarCases.length}
              </div>
              <div className="metric-meta">Cosine similarity RAG</div>
            </div>
          </div>

          {/* Section 1: Deterministic Plan Analysis */}
          <div className="card">
            <div className="card-header">
              <div>
                <div className="card-title">
                  <Layers size={18} style={{ color: 'var(--accent-blue)' }} />
                  <span>1. Deterministic Execution Plan Analysis (Authoritative)</span>
                </div>
                <div className="card-subtitle">
                  Parsed directly from PostgreSQL EXPLAIN engine via PlanAnalyzer
                </div>
              </div>
              <span className="badge badge-blue">Deterministic Engine</span>
            </div>

            {/* Plan Visualizer */}
            {(rootNode || rawPlan?.[0]?.Plan) && (
              <div style={{ marginBottom: '20px' }}>
                <ExecutionPlanViewer
                  plan={rootNode || rawPlan[0].Plan}
                  bottleneckRelations={findings.map((f) => f.relation).filter(Boolean) as string[]}
                />
              </div>
            )}

            {/* Bottleneck Findings */}
            <div>
              <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '10px' }}>
                DETECTED BOTTLENECKS ({findings.length})
              </div>
              <BottleneckList findings={findings} />
            </div>
          </div>

          {/* Section 2: Recommendation & HypoPG Simulation */}
          {recommendation && (
            <div className="card" style={{ borderLeft: '4px solid var(--accent-blue)' }}>
              <div className="card-header">
                <div>
                  <div className="card-title">
                    <Zap size={18} style={{ color: 'var(--accent-blue)' }} />
                    <span>2. Deterministic Recommendation & HypoPG Simulation</span>
                  </div>
                  <div className="card-subtitle">
                    Grounded recommendation requiring explicit human approval before any database write
                  </div>
                </div>
                <span className="badge badge-blue">Safe Advisory</span>
              </div>

              <RecommendationCard
                recommendation={recommendation}
                query={query}
                onRequestApproval={onRequestApproval}
              />
            </div>
          )}

          {/* Section 3: RAG Historical Cases */}
          {includeRag && (
            <div className="card" style={{ borderLeft: '4px solid var(--accent-purple)' }}>
              <div className="card-header">
                <div>
                  <div className="card-title">
                    <BrainCircuit size={18} style={{ color: 'var(--accent-purple)' }} />
                    <span>3. RAG Historical Memory Retrieval</span>
                  </div>
                  <div className="card-subtitle">
                    Prior optimization outcomes retrieved to ground AI reasoning in empirical database evidence
                  </div>
                </div>
                <span className="badge badge-purple">Cosine Similarity RAG</span>
              </div>

              <RAGHistoricalCases cases={similarCases} />
            </div>
          )}

          {/* Section 4: Groq AI Explanation */}
          <div style={{ borderLeft: '4px solid #8b5cf6' }}>
            <AIExplanationPanel
              explanation={result.llm_explanation}
              provider={result.llm_provider}
              hasRagContext={similarCases.length > 0}
            />
          </div>
        </div>
      )}
    </div>
  );
};
