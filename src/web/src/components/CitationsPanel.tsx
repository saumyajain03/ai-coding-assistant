import React from 'react';
import { BookOpen, ShieldCheck, ExternalLink, Hash } from 'lucide-react';
import { CitationItem } from '../services/api';

interface CitationsPanelProps {
  citations: CitationItem[];
}

export const CitationsPanel: React.FC<CitationsPanelProps> = ({ citations }) => {
  return (
    <div style={{
      borderRadius: '20px',
      background: 'rgba(12, 12, 16, 0.7)',
      backdropFilter: 'blur(20px)',
      border: '1px solid rgba(255, 255, 255, 0.08)',
      padding: '20px',
      display: 'flex',
      flexDirection: 'column',
      gap: '14px'
    }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <BookOpen size={16} color="#38bdf8" />
          <span style={{ fontSize: '13px', fontWeight: 700, color: '#f4f4f5' }}>
            Retrieved Citations & Knowledge ({citations.length})
          </span>
        </div>
        <span style={{
          fontSize: '10px',
          fontWeight: 600,
          padding: '2px 8px',
          borderRadius: '9999px',
          background: 'rgba(16, 185, 129, 0.1)',
          color: '#34d399',
          border: '1px solid rgba(16, 185, 129, 0.25)'
        }}>
          ChromaDB Semantic Vector Index
        </span>
      </div>

      {citations.length === 0 ? (
        <div style={{
          padding: '28px 16px',
          textAlign: 'center',
          color: '#71717a',
          fontSize: '12px',
          border: '1px dashed rgba(255, 255, 255, 0.06)',
          borderRadius: '14px'
        }}>
          No citations queried yet. Contextual documents and workspace code chunks will appear here during Stage 3.
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
          {citations.map((c) => (
            <div
              key={c.id}
              style={{
                padding: '12px 14px',
                borderRadius: '14px',
                background: 'rgba(255, 255, 255, 0.02)',
                border: '1px solid rgba(255, 255, 255, 0.06)',
                display: 'flex',
                flexDirection: 'column',
                gap: '6px'
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <Hash size={13} color="#38bdf8" />
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: '12px', fontWeight: 600, color: '#e4e4e7' }}>
                    {c.filename}
                  </span>
                  {c.startLine && (
                    <span style={{ fontSize: '11px', color: '#71717a' }}>
                      (Lines {c.startLine}-{c.endLine})
                    </span>
                  )}
                </div>

                <span style={{
                  fontSize: '9px',
                  fontWeight: 600,
                  padding: '1px 6px',
                  borderRadius: '4px',
                  background: 'rgba(56, 189, 248, 0.1)',
                  color: '#38bdf8'
                }}>
                  {c.securityVerdict || 'UNTRUSTED_WRAPPED'}
                </span>
              </div>

              <div style={{
                fontSize: '11px',
                fontFamily: 'var(--font-mono)',
                color: '#a1a1aa',
                background: 'rgba(0, 0, 0, 0.4)',
                padding: '8px 10px',
                borderRadius: '8px',
                lineHeight: 1.5
              }}>
                {c.snippet}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
