import React, { useState } from 'react';
import { PlanNode } from '../types/api';
import { ChevronDown, ChevronRight, AlertTriangle, Layers, Zap } from 'lucide-react';

interface ExecutionPlanViewerProps {
  plan: PlanNode | Record<string, any>;
  bottleneckRelations?: string[];
}

export const ExecutionPlanViewer: React.FC<ExecutionPlanViewerProps> = ({
  plan,
  bottleneckRelations = [],
}) => {
  return (
    <div
      style={{
        backgroundColor: '#0a0d14',
        border: '1px solid var(--border-subtle)',
        borderRadius: '10px',
        padding: '16px',
        overflowX: 'auto',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: '12px',
          borderBottom: '1px solid var(--border-subtle)',
          paddingBottom: '8px',
        }}
      >
        <span
          style={{
            fontSize: '12px',
            textTransform: 'uppercase',
            letterSpacing: '0.05em',
            color: 'var(--text-muted)',
            fontWeight: 600,
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
          }}
        >
          <Layers size={14} /> Execution Plan Hierarchy
        </span>
        <span style={{ fontSize: '11.5px', color: 'var(--text-secondary)' }}>
          PostgreSQL Planner Tree
        </span>
      </div>

      <PlanNodeItem
        node={plan as PlanNode}
        depth={0}
        bottleneckRelations={bottleneckRelations}
      />
    </div>
  );
};

interface PlanNodeItemProps {
  node: PlanNode;
  depth: number;
  bottleneckRelations: string[];
}

const PlanNodeItem: React.FC<PlanNodeItemProps> = ({ node, depth, bottleneckRelations }) => {
  const [expanded, setExpanded] = useState(true);

  if (!node) return null;

  // Support both snake_case (PlanNode schema) and PostgreSQL raw Title Case
  const nodeType = node.node_type || (node as any)['Node Type'] || 'Unknown Node';
  const relation = node.relation_name || (node as any)['Relation Name'] || null;
  const totalCost = node.total_cost ?? (node as any)['Total Cost'] ?? null;
  const startupCost = node.startup_cost ?? (node as any)['Startup Cost'] ?? null;
  const planRows = node.plan_rows ?? (node as any)['Plan Rows'] ?? null;
  const actualRows = node.actual_rows ?? (node as any)['Actual Rows'] ?? null;
  const filter = node.filter || (node as any)['Filter'] || null;
  const indexCond = node.index_cond || (node as any)['Index Cond'] || null;
  const indexName = (node as any).index_name || (node as any)['Index Name'] || null;

  // Children can be in .children or raw .Plans
  const children: PlanNode[] = node.children || (node as any)['Plans'] || [];
  const hasChildren = children && children.length > 0;

  const isSeqScan = nodeType.toLowerCase().includes('seq scan');
  const isIndexScan = nodeType.toLowerCase().includes('index scan') || nodeType.toLowerCase().includes('bitmap');
  const isBottleneck =
    (isSeqScan && relation && bottleneckRelations.includes(relation)) ||
    (isSeqScan && totalCost && totalCost > 50);

  // Badge color based on node type
  let badgeClass = 'badge-neutral';
  if (isBottleneck) badgeClass = 'badge-red';
  else if (isIndexScan) badgeClass = 'badge-green';
  else if (isSeqScan) badgeClass = 'badge-amber';
  else if (nodeType.toLowerCase().includes('sort')) badgeClass = 'badge-purple';
  else if (nodeType.toLowerCase().includes('loop')) badgeClass = 'badge-blue';

  return (
    <div style={{ marginLeft: depth > 0 ? `${depth * 20}px` : '0px', marginTop: '6px' }}>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          padding: '8px 12px',
          borderRadius: '8px',
          backgroundColor: isBottleneck
            ? 'rgba(239, 68, 68, 0.08)'
            : 'var(--bg-card)',
          border: isBottleneck
            ? '1px solid rgba(239, 68, 68, 0.3)'
            : '1px solid var(--border-subtle)',
          transition: 'all 0.15s ease',
        }}
      >
        {hasChildren ? (
          <button
            onClick={() => setExpanded(!expanded)}
            style={{
              background: 'none',
              border: 'none',
              color: 'var(--text-muted)',
              cursor: 'pointer',
              display: 'flex',
              padding: 0,
            }}
          >
            {expanded ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
          </button>
        ) : (
          <div style={{ width: '15px' }} />
        )}

        <div className={`badge ${badgeClass}`}>
          {isBottleneck && <AlertTriangle size={11} />}
          {isIndexScan && <Zap size={11} />}
          <span>{nodeType}</span>
        </div>

        {relation && (
          <span style={{ fontSize: '13px', fontWeight: 600, color: '#f1f5f9' }}>
            on <span style={{ color: '#60a5fa' }}>{relation}</span>
          </span>
        )}

        {indexName && (
          <span
            style={{
              fontSize: '11.5px',
              fontFamily: 'var(--font-mono)',
              color: '#34d399',
              backgroundColor: 'rgba(16, 185, 129, 0.1)',
              padding: '2px 6px',
              borderRadius: '4px',
            }}
          >
            {indexName}
          </span>
        )}

        {totalCost !== null && (
          <div
            style={{
              marginLeft: 'auto',
              display: 'flex',
              alignItems: 'center',
              gap: '12px',
              fontFamily: 'var(--font-mono)',
              fontSize: '11.5px',
              color: 'var(--text-secondary)',
            }}
          >
            <span title="Estimated Total Cost">
              cost: <strong style={{ color: totalCost > 500 ? '#f87171' : 'inherit' }}>{totalCost.toFixed(2)}</strong>
            </span>
            {planRows !== null && (
              <span title="Estimated Output Rows">
                rows: <strong>{planRows.toLocaleString()}</strong>
              </span>
            )}
            {actualRows !== null && (
              <span title="Actual Returned Rows" style={{ color: '#34d399' }}>
                actual: <strong>{actualRows.toLocaleString()}</strong>
              </span>
            )}
          </div>
        )}
      </div>

      {(filter || indexCond) && (
        <div
          style={{
            marginLeft: hasChildren ? '24px' : '24px',
            marginTop: '4px',
            padding: '4px 10px',
            fontSize: '11.5px',
            fontFamily: 'var(--font-mono)',
            backgroundColor: 'rgba(15, 20, 29, 0.7)',
            borderRadius: '4px',
            borderLeft: '2px solid #3b82f6',
            color: 'var(--text-muted)',
          }}
        >
          {filter && <div>filter: <span style={{ color: '#93c5fd' }}>{filter}</span></div>}
          {indexCond && <div>index cond: <span style={{ color: '#86efac' }}>{indexCond}</span></div>}
        </div>
      )}

      {hasChildren && expanded && (
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          {children.map((child, index) => (
            <PlanNodeItem
              key={index}
              node={child}
              depth={depth + 1}
              bottleneckRelations={bottleneckRelations}
            />
          ))}
        </div>
      )}
    </div>
  );
};
