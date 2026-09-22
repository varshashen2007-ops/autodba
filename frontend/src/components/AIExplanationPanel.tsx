import React, { useState } from 'react';
import { Sparkles, ShieldAlert, Copy, Check, Info } from 'lucide-react';

interface AIExplanationPanelProps {
  explanation?: string | null;
  provider?: string | null;
  model?: string;
  hasRagContext?: boolean;
}

export const AIExplanationPanel: React.FC<AIExplanationPanelProps> = ({
  explanation,
  provider = 'groq',
  model = 'llama-3.3-70b-versatile',
  hasRagContext = false,
}) => {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    if (!explanation) return;
    navigator.clipboard.writeText(explanation);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (!explanation) {
    return (
      <div className="card" style={{ borderLeft: '4px solid var(--accent-purple)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--text-muted)' }}>
          <Sparkles size={18} style={{ color: 'var(--accent-purple)' }} />
          <span style={{ fontSize: '14px', fontWeight: 500 }}>
            AI Explanation not generated for this analysis. (Run Investigate to generate)
          </span>
        </div>
      </div>
    );
  }

  // Render markdown-like sections cleanly
  const renderFormattedExplanation = (text: string) => {
    const paragraphs = text.split('\n\n');
    return paragraphs.map((p, idx) => {
      if (p.startsWith('**') && p.includes('**')) {
        return (
          <div key={idx} style={{ marginBottom: '14px' }}>
            <h4
              style={{
                fontSize: '14px',
                fontWeight: 700,
                color: '#e2e8f0',
                marginBottom: '6px',
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
              }}
            >
              {p.split('\n')[0].replace(/\*\*/g, '')}
            </h4>
            <div style={{ fontSize: '13.5px', color: 'var(--text-secondary)', lineHeight: 1.6 }}>
              {p.split('\n').slice(1).join('\n')}
            </div>
          </div>
        );
      }
      return (
        <p key={idx} style={{ marginBottom: '12px', fontSize: '13.5px', color: 'var(--text-secondary)', lineHeight: 1.6 }}>
          {p}
        </p>
      );
    });
  };

  return (
    <div
      className="card"
      style={{
        border: '1px solid var(--accent-purple-border)',
        background: 'linear-gradient(180deg, rgba(139, 92, 246, 0.04) 0%, var(--bg-card) 100%)',
      }}
    >
      <div className="card-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <span
            style={{
              width: '32px',
              height: '32px',
              borderRadius: '8px',
              background: 'linear-gradient(135deg, #7c3aed 0%, #3b82f6 100%)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: 'white',
              boxShadow: '0 0 12px rgba(124, 58, 237, 0.4)',
            }}
          >
            <Sparkles size={17} />
          </span>
          <div>
            <div className="card-title">AI Performance Diagnosis & Explanation</div>
            <div className="card-subtitle">
              Grounded in PostgreSQL plan evidence {hasRagContext ? '+ historical RAG memory' : ''}
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span className="badge badge-purple">provider: {provider || 'groq'}</span>
          <span className="badge badge-neutral">{model}</span>
          <button
            onClick={handleCopy}
            className="btn btn-secondary btn-sm"
            title="Copy explanation"
            style={{ padding: '4px 8px' }}
          >
            {copied ? <Check size={13} style={{ color: '#10b981' }} /> : <Copy size={13} />}
          </button>
        </div>
      </div>

      <div
        style={{
          padding: '16px',
          borderRadius: '8px',
          backgroundColor: 'rgba(10, 13, 20, 0.8)',
          border: '1px solid var(--border-subtle)',
          marginBottom: '14px',
        }}
      >
        <div className="ai-prose">{renderFormattedExplanation(explanation)}</div>
      </div>

      <div
        style={{
          display: 'flex',
          alignItems: 'flex-start',
          gap: '8px',
          padding: '10px 14px',
          borderRadius: '8px',
          backgroundColor: 'rgba(59, 130, 246, 0.06)',
          border: '1px solid var(--accent-blue-border)',
          fontSize: '11.5px',
          color: 'var(--text-secondary)',
        }}
      >
        <Info size={15} style={{ color: '#60a5fa', flexShrink: 0, marginTop: '1px' }} />
        <div>
          <strong style={{ color: '#93c5fd' }}>Architectural Safety Separation:</strong> The LLM functions
          strictly as an advisory reasoning layer. It does not execute SQL, create indexes, or bypass
          the deterministic Phase 1–3 safety gates. All database actions require explicit human approval.
        </div>
      </div>
    </div>
  );
};
