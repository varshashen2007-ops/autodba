import React from 'react';
import {
  Activity,
  BrainCircuit,
  Database,
  Gauge,
  HeartPulse,
  History,
  LayoutDashboard,
  Lightbulb,
  RefreshCw,
  Search,
  ShieldCheck,
  Wrench,
} from 'lucide-react';
import { HealthResponse } from '../types/api';

export type NavTab =
  | 'dashboard'
  | 'investigate'
  | 'recommendations'
  | 'approvals'
  | 'remediation'
  | 'benchmarks'
  | 'intelligence'
  | 'memory'
  | 'closed-loop'
  | 'health';

interface SidebarProps {
  currentTab: NavTab;
  onSelectTab: (tab: NavTab) => void;
  health: HealthResponse | null;
  pendingApprovalsCount?: number;
}

export const Sidebar: React.FC<SidebarProps> = ({
  currentTab,
  onSelectTab,
  health,
  pendingApprovalsCount = 0,
}) => {
  const isConnected = health?.database === 'connected';

  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <div className="logo-badge">
          <div className="logo-icon">A</div>
          <div className="logo-text">
            <h1>AutoDBA</h1>
            <div className="logo-subtitle">Autonomous PostgreSQL DBA</div>
          </div>
        </div>
      </div>

      <nav className="sidebar-nav">
        <div className="nav-section-title">Overview</div>
        <div
          className={`nav-item ${currentTab === 'dashboard' ? 'active' : ''}`}
          onClick={() => onSelectTab('dashboard')}
        >
          <LayoutDashboard size={18} />
          <span>Dashboard</span>
        </div>

        <div className="nav-section-title">Investigation & AI</div>
        <div
          className={`nav-item ${currentTab === 'investigate' ? 'active' : ''}`}
          onClick={() => onSelectTab('investigate')}
        >
          <Search size={18} />
          <span>Investigate Query</span>
        </div>
        <div
          className={`nav-item ${currentTab === 'intelligence' ? 'active' : ''}`}
          onClick={() => onSelectTab('intelligence')}
        >
          <BrainCircuit size={18} />
          <span>Historical Intelligence</span>
        </div>
        <div
          className={`nav-item ${currentTab === 'memory' ? 'active' : ''}`}
          onClick={() => onSelectTab('memory')}
        >
          <History size={18} />
          <span>Memory Explorer</span>
        </div>

        <div className="nav-section-title">Autonomous Pipeline</div>
        <div
          className={`nav-item ${currentTab === 'recommendations' ? 'active' : ''}`}
          onClick={() => onSelectTab('recommendations')}
        >
          <Lightbulb size={18} />
          <span>Recommendations</span>
        </div>
        <div
          className={`nav-item ${currentTab === 'approvals' ? 'active' : ''}`}
          onClick={() => onSelectTab('approvals')}
        >
          <ShieldCheck size={18} />
          <span>Approvals Gate</span>
          {pendingApprovalsCount > 0 && (
            <span
              style={{
                marginLeft: 'auto',
                backgroundColor: 'rgba(245, 158, 11, 0.2)',
                color: '#fbbf24',
                padding: '1px 6px',
                borderRadius: '10px',
                fontSize: '11px',
                fontWeight: 700,
              }}
            >
              {pendingApprovalsCount}
            </span>
          )}
        </div>
        <div
          className={`nav-item ${currentTab === 'remediation' ? 'active' : ''}`}
          onClick={() => onSelectTab('remediation')}
        >
          <Wrench size={18} />
          <span>Physical Remediation</span>
        </div>
        <div
          className={`nav-item ${currentTab === 'benchmarks' ? 'active' : ''}`}
          onClick={() => onSelectTab('benchmarks')}
        >
          <Gauge size={18} />
          <span>Real Benchmarking</span>
        </div>
        <div
          className={`nav-item ${currentTab === 'closed-loop' ? 'active' : ''}`}
          onClick={() => onSelectTab('closed-loop')}
        >
          <RefreshCw size={18} />
          <span>Closed-Loop Engine</span>
        </div>

        <div className="nav-section-title">Database</div>
        <div
          className={`nav-item ${currentTab === 'health' ? 'active' : ''}`}
          onClick={() => onSelectTab('health')}
        >
          <HeartPulse size={18} />
          <span>PostgreSQL Health</span>
        </div>
      </nav>

      <div className="sidebar-footer">
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            fontSize: '12px',
          }}
        >
          <div
            style={{
              width: '8px',
              height: '8px',
              borderRadius: '50%',
              backgroundColor: isConnected ? '#10b981' : '#ef4444',
              boxShadow: isConnected
                ? '0 0 8px rgba(16, 185, 129, 0.6)'
                : '0 0 8px rgba(239, 68, 68, 0.6)',
            }}
          />
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>
              {isConnected ? 'PostgreSQL 17' : 'Disconnected'}
            </div>
            <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
              {isConnected ? 'hypopg + pg_stat' : 'Check backend service'}
            </div>
          </div>
          <Database size={15} style={{ color: 'var(--text-muted)' }} />
        </div>
      </div>
    </aside>
  );
};
