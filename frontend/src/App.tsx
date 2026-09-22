import React, { useState, useEffect } from 'react';
import { NavTab, Sidebar } from './components/Sidebar';
import { Header } from './components/Header';
import { DashboardView } from './views/DashboardView';
import { InvestigateView } from './views/InvestigateView';
import { RecommendationsView } from './views/RecommendationsView';
import { ApprovalsView } from './views/ApprovalsView';
import { RemediationView } from './views/RemediationView';
import { BenchmarksView } from './views/BenchmarksView';
import { IntelligenceView } from './views/IntelligenceView';
import { MemoryExplorerView } from './views/MemoryExplorerView';
import { ClosedLoopView } from './views/ClosedLoopView';
import { HealthView } from './views/HealthView';
import { ApprovalModal } from './components/ApprovalModal';

import {
  ApprovalRequest,
  HealthResponse,
  MemoryListItem,
  OptimizationRecommendation,
  SlowQuery,
} from './types/api';
import { api } from './services/api';

export const App: React.FC = () => {
  const [currentTab, setCurrentTab] = useState<NavTab>('dashboard');
  const [investigateQuery, setInvestigateQuery] = useState<string>(
    'SELECT * FROM orders WHERE customer_id = 42;'
  );
  const [benchmarkQuery, setBenchmarkQuery] = useState<string>(
    'SELECT * FROM orders WHERE customer_id = 42;'
  );

  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [memories, setMemories] = useState<MemoryListItem[]>([]);
  const [slowQueries, setSlowQueries] = useState<SlowQuery[]>([]);
  const [approvals, setApprovals] = useState<ApprovalRequest[]>([]);

  // Approval modal state when creating from recommendation
  const [pendingApprovalModal, setPendingApprovalModal] = useState<ApprovalRequest | null>(null);
  const [creatingApproval, setCreatingApproval] = useState(false);
  const [globalError, setGlobalError] = useState<string | null>(null);

  const loadData = async () => {
    try {
      setGlobalError(null);
      const [h, m, sq, apprs] = await Promise.allSettled([
        api.getHealth(),
        api.getMemories(50),
        api.getSlowQueries(10),
        api.getApprovals(),
      ]);

      if (h.status === 'fulfilled') setHealth(h.value);
      if (m.status === 'fulfilled') setMemories(m.value);
      if (sq.status === 'fulfilled') setSlowQueries(sq.value.queries);
      if (apprs.status === 'fulfilled') setApprovals(apprs.value);
    } catch (err: any) {
      setGlobalError('Could not reach AutoDBA backend. Please verify that the FastAPI backend is running.');
    }
  };

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 20000);
    return () => clearInterval(interval);
  }, []);

  const handleNavigateWithQuery = (tab: NavTab, query?: string) => {
    if (query) {
      if (tab === 'investigate') setInvestigateQuery(query);
      if (tab === 'benchmarks') setBenchmarkQuery(query);
    }
    setCurrentTab(tab);
  };

  const handleRequestApproval = async (recommendation: OptimizationRecommendation) => {
    try {
      setCreatingApproval(true);
      const created = await api.createApproval(recommendation);
      setPendingApprovalModal(created);
      loadData();
    } catch (err: any) {
      alert(`Approval creation failed: ${err.message}`);
    } finally {
      setCreatingApproval(false);
    }
  };

  const pendingCount = approvals.filter((a) => a.status === 'pending').length;

  return (
    <div className="app-container">
      <Sidebar
        currentTab={currentTab}
        onSelectTab={setCurrentTab}
        health={health}
        pendingApprovalsCount={pendingCount}
      />

      <div className="main-content">
        <Header
          currentTab={currentTab}
          health={health}
          totalMemories={memories.length}
        />

        <div className="page-container">
          {globalError && (
            <div
              style={{
                marginBottom: '20px',
                padding: '12px 18px',
                borderRadius: '8px',
                backgroundColor: 'rgba(239, 68, 68, 0.12)',
                border: '1px solid var(--accent-red-border)',
                color: '#f87171',
                fontSize: '13px',
              }}
            >
              {globalError}
            </div>
          )}

          {currentTab === 'dashboard' && (
            <DashboardView
              health={health}
              memories={memories}
              slowQueries={slowQueries}
              pendingApprovalsCount={pendingCount}
              onNavigate={handleNavigateWithQuery}
            />
          )}

          {currentTab === 'investigate' && (
            <InvestigateView
              initialQuery={investigateQuery}
              onRequestApproval={handleRequestApproval}
              onNavigate={handleNavigateWithQuery}
            />
          )}

          {currentTab === 'recommendations' && (
            <RecommendationsView onRequestApproval={handleRequestApproval} />
          )}

          {currentTab === 'approvals' && (
            <ApprovalsView
              approvals={approvals}
              onRefresh={loadData}
              onSelectForRemediation={(appr) => {
                setCurrentTab('remediation');
              }}
            />
          )}

          {currentTab === 'remediation' && (
            <RemediationView
              approvals={approvals}
              onRefreshApprovals={loadData}
              onNavigateToBenchmark={(q) => {
                setBenchmarkQuery(q);
                setCurrentTab('benchmarks');
              }}
            />
          )}

          {currentTab === 'benchmarks' && (
            <BenchmarksView initialQuery={benchmarkQuery} />
          )}

          {currentTab === 'intelligence' && <IntelligenceView />}

          {currentTab === 'memory' && (
            <MemoryExplorerView memories={memories} onRefresh={loadData} />
          )}

          {currentTab === 'closed-loop' && (
            <ClosedLoopView approvals={approvals} onRefreshAll={loadData} />
          )}

          {currentTab === 'health' && (
            <HealthView health={health} slowQueries={slowQueries} onRefresh={loadData} />
          )}
        </div>
      </div>

      {pendingApprovalModal && (
        <ApprovalModal
          request={pendingApprovalModal}
          onClose={() => setPendingApprovalModal(null)}
          onActionComplete={(updated) => {
            loadData();
            setPendingApprovalModal(null);
          }}
        />
      )}
    </div>
  );
};
export default App;
