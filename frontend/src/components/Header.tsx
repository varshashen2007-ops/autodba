import React from 'react';
import { NavTab } from './Sidebar';
import { Database, Cpu, Sparkles, CheckCircle2 } from 'lucide-react';
import { HealthResponse } from '../types/api';

interface HeaderProps {
  currentTab: NavTab;
  health: HealthResponse | null;
  totalMemories?: number;
}

const tabTitles: Record<NavTab, { title: string; subtitle: string }> = {
  dashboard: {
    title: 'Autonomous DBA Overview',
    subtitle: 'Real-time performance monitoring & closed-loop intelligence telemetry',
  },
  investigate: {
    title: 'Query Performance Investigation',
    subtitle: 'Deterministic EXPLAIN plan analysis + HypoPG validation + Groq RAG reasoning',
  },
  recommendations: {
    title: 'Optimization Recommendations',
    subtitle: 'Formally generated index candidates with deterministic risk & confidence tiers',
  },
  approvals: {
    title: 'Human Safety & Approval Gate',
    subtitle: '7-rule safety assessment with mandatory explicit authorization before any write',
  },
  remediation: {
    title: 'Controlled Physical Remediation',
    subtitle: 'Idempotent, authorized index creation with post-DDL verification in PostgreSQL',
  },
  benchmarks: {
    title: 'Empirical Runtime Benchmarking',
    subtitle: '10-run EXPLAIN ANALYZE comparison isolating planner cost from real wall-clock latency',
  },
  intelligence: {
    title: 'Historical RAG Intelligence',
    subtitle: 'Semantic cosine-similarity matching over verified optimization memories',
  },
  memory: {
    title: 'Optimization Memory Explorer',
    subtitle: 'Searchable repository of historical performance incidents, remedies, and measured outcomes',
  },
  'closed-loop': {
    title: 'Closed-Loop Self-Improving Engine',
    subtitle: 'Full 10-step autonomous pipeline: Detect -> Diagnose -> Validate -> Remediate -> Benchmark -> Learn',
  },
  health: {
    title: 'Database & Extension Observability',
    subtitle: 'PostgreSQL 17 connection pool, pg_stat_statements metrics, and extension states',
  },
};

export const Header: React.FC<HeaderProps> = ({ currentTab, health, totalMemories = 0 }) => {
  const info = tabTitles[currentTab];

  return (
    <header className="top-header">
      <div className="header-title-section">
        <div>
          <div className="header-title">{info.title}</div>
          <div style={{ fontSize: '11.5px', color: 'var(--text-muted)' }}>{info.subtitle}</div>
        </div>
      </div>

      <div className="header-actions">
        <div className="badge badge-purple" title="LLM Advisory Reasoning Layer">
          <Sparkles size={12} />
          <span>Groq · openai/gpt-oss-120b</span>
        </div>

        <div className="badge badge-blue" title="Persistent Memory Corpus">
          <Database size={12} />
          <span>{totalMemories} Memories</span>
        </div>

        <div className={`badge ${health?.database === 'connected' ? 'badge-green' : 'badge-red'}`}>
          <CheckCircle2 size={12} />
          <span>{health?.database === 'connected' ? 'Postgres 17 Ready' : 'Database Offline'}</span>
        </div>
      </div>
    </header>
  );
};
