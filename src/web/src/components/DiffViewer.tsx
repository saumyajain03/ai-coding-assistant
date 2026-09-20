import React, { useState } from 'react';
import { FileCode, Plus, Minus, Check, Copy } from 'lucide-react';
import { PatchProposalData } from '../services/api';

interface DiffViewerProps {
  patch: PatchProposalData | null;
}

export const DiffViewer: React.FC<DiffViewerProps> = ({ patch }) => {
  const [copied, setCopied] = useState(false);

  if (!patch) {
    return (
      <div style={{
        padding: '48px 24px',
        textAlign: 'center',
        background: 'rgba(255, 255, 255, 0.02)',
        borderRadius: '20px',
        border: '1px dashed rgba(255, 255, 255, 0.1)',
        color: '#71717a'
      }}>
        <FileCode size={36} color="#52525b" style={{ margin: '0 auto 12px' }} />
        <div style={{ fontSize: '14px', fontWeight: 500, color: '#a1a1aa' }}>No Patch Proposed Yet</div>
        <div style={{ fontSize: '12px', marginTop: '4px' }}>
          When the agent synthesizes a patch in Stage 4, unified diffs with line-by-line syntax validation appear here.
        </div>
      </div>
    );
  }

  const handleCopy = () => {
    navigator.clipboard.writeText(patch.unifiedDiff);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const diffLines = patch.unifiedDiff.split('\n');

  return (
    <div style={{
      borderRadius: '20px',
      overflow: 'hidden',
      background: 'rgba(10, 10, 12, 0.8)',
      backdropFilter: 'blur(24px)',
      border: '1px solid rgba(255, 255, 255, 0.12)',
      boxShadow: '0 12px 40px -12px rgba(0, 0, 0, 0.7)'
    }}>
      {/* Header bar */}
      <div style={{
        padding: '14px 20px',
        background: 'rgba(255, 255, 255, 0.04)',
        borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <FileCode size={18} color="#38bdf8" />
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: '13px', fontWeight: 600, color: '#f4f4f5' }}>
            {patch.targetFile}
          </span>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '2px',
              fontSize: '11px',
              color: '#34d399',
              background: 'rgba(16, 185, 129, 0.12)',
              padding: '2px 6px',
              borderRadius: '6px',
              fontFamily: 'var(--font-mono)'
            }}>
              <Plus size={11} /> {patch.linesAdded}
            </span>
            <span style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '2px',
              fontSize: '11px',
              color: '#fb7185',
              background: 'rgba(244, 63, 94, 0.12)',
              padding: '2px 6px',
              borderRadius: '6px',
              fontFamily: 'var(--font-mono)'
            }}>
              <Minus size={11} /> {patch.linesRemoved}
            </span>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <span style={{
            fontSize: '11px',
            color: patch.syntaxValid ? '#34d399' : '#f43f5e',
            background: patch.syntaxValid ? 'rgba(16, 185, 129, 0.1)' : 'rgba(244, 63, 94, 0.1)',
            padding: '3px 9px',
            borderRadius: '9999px',
            border: `1px solid ${patch.syntaxValid ? 'rgba(16, 185, 129, 0.3)' : 'rgba(244, 63, 94, 0.3)'}`
          }}>
            {patch.syntaxValid ? 'AST Syntax Valid' : 'Syntax Error'}
          </span>

          <button
            onClick={handleCopy}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '5px',
              padding: '5px 10px',
              borderRadius: '8px',
              background: 'rgba(255, 255, 255, 0.06)',
              border: '1px solid rgba(255, 255, 255, 0.12)',
              color: '#ffffff',
              fontSize: '11px',
              cursor: 'pointer'
            }}
          >
            {copied ? <Check size={12} color="#10b981" /> : <Copy size={12} />}
            {copied ? 'Copied' : 'Copy Diff'}
          </button>
        </div>
      </div>

      {/* Rationale Bar */}
      {patch.rationale && (
        <div style={{
          padding: '10px 20px',
          background: 'rgba(56, 189, 248, 0.05)',
          borderBottom: '1px solid rgba(56, 189, 248, 0.12)',
          fontSize: '12px',
          color: '#93c5fd'
        }}>
          <strong>Rationale:</strong> {patch.rationale}
        </div>
      )}

      {/* Code diff container */}
      <div style={{
        padding: '14px 0',
        fontFamily: 'var(--font-mono)',
        fontSize: '12px',
        lineHeight: 1.6,
        overflowX: 'auto',
        maxHeight: '440px'
      }}>
        {diffLines.map((line, idx) => {
          let bg = 'transparent';
          let textColor = '#d4d4d8';
          let sign = ' ';

          if (line.startsWith('+') && !line.startsWith('+++')) {
            bg = 'rgba(16, 185, 129, 0.14)';
            textColor = '#4ade80';
            sign = '+';
          } else if (line.startsWith('-') && !line.startsWith('---')) {
            bg = 'rgba(244, 63, 94, 0.14)';
            textColor = '#f87171';
            sign = '-';
          } else if (line.startsWith('@@')) {
            bg = 'rgba(168, 85, 247, 0.1)';
            textColor = '#c084fc';
          }

          return (
            <div
              key={idx}
              style={{
                display: 'flex',
                background: bg,
                padding: '1px 16px',
                borderLeft: line.startsWith('+') ? '3px solid #10b981' : (line.startsWith('-') ? '3px solid #f43f5e' : '3px solid transparent')
              }}
            >
              <span style={{
                width: '36px',
                color: '#52525b',
                userSelect: 'none',
                textAlign: 'right',
                paddingRight: '14px',
                flexShrink: 0
              }}>
                {idx + 1}
              </span>
              <pre style={{
                margin: 0,
                color: textColor,
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-all'
              }}>
                {line}
              </pre>
            </div>
          );
        })}
      </div>
    </div>
  );
};
