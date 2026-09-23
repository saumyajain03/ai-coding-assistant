import React, { useState } from 'react';
import { FileCode, Plus, Minus, Check, Copy, Files } from 'lucide-react';
import { PatchProposalData } from '../services/api';

interface DiffViewerProps {
  patch: PatchProposalData | null;
}

export const DiffViewer: React.FC<DiffViewerProps> = ({ patch }) => {
  const [copied, setCopied] = useState(false);
  const [selectedFileIdx, setSelectedFileIdx] = useState<number>(0);

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

  const hasMultiFiles = Boolean(patch.files && patch.files.length > 1);
  const currentFile = (hasMultiFiles && patch.files && patch.files[selectedFileIdx])
    ? patch.files[selectedFileIdx]
    : null;

  const activeTargetFile = currentFile ? currentFile.targetFile : patch.targetFile;
  const activeUnifiedDiff = currentFile ? currentFile.unifiedDiff : patch.unifiedDiff;
  const activeLinesAdded = currentFile ? currentFile.linesAdded : patch.linesAdded;
  const activeLinesRemoved = currentFile ? currentFile.linesRemoved : patch.linesRemoved;
  const activeSyntaxValid = currentFile ? currentFile.syntaxValid : patch.syntaxValid;
  const activeIsNew = currentFile ? currentFile.isNewFile : Boolean(patch.isNewFile);

  const handleCopy = () => {
    navigator.clipboard.writeText(activeUnifiedDiff);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const diffLines = activeUnifiedDiff.split('\n');

  return (
    <div style={{
      borderRadius: '20px',
      overflow: 'hidden',
      background: 'rgba(10, 10, 12, 0.8)',
      backdropFilter: 'blur(24px)',
      border: '1px solid rgba(255, 255, 255, 0.12)',
      boxShadow: '0 12px 40px -12px rgba(0, 0, 0, 0.7)'
    }}>
      {/* Multi-File Tab Selector (when multiple files are proposed) */}
      {hasMultiFiles && patch.files && (
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          padding: '10px 16px',
          background: 'rgba(0, 0, 0, 0.4)',
          borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
          overflowX: 'auto'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '11px', color: '#a1a1aa', marginRight: '6px' }}>
            <Files size={13} color="#38bdf8" />
            <span>Files ({patch.files.length}):</span>
          </div>
          {patch.files.map((f, idx) => {
            const isSelected = idx === selectedFileIdx;
            return (
              <button
                key={f.targetFile}
                onClick={() => setSelectedFileIdx(idx)}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '6px',
                  padding: '5px 12px',
                  borderRadius: '8px',
                  fontSize: '11px',
                  fontFamily: 'var(--font-mono)',
                  cursor: 'pointer',
                  border: isSelected ? '1px solid #38bdf8' : '1px solid rgba(255, 255, 255, 0.1)',
                  background: isSelected ? 'rgba(56, 189, 248, 0.15)' : 'rgba(255, 255, 255, 0.03)',
                  color: isSelected ? '#38bdf8' : '#d4d4d8',
                  fontWeight: isSelected ? 600 : 400,
                  transition: 'all 0.15s ease'
                }}
              >
                {f.isNewFile && (
                  <span style={{ fontSize: '9px', background: 'rgba(16, 185, 129, 0.2)', color: '#34d399', padding: '1px 4px', borderRadius: '4px' }}>
                    NEW
                  </span>
                )}
                <span>{f.targetFile}</span>
                <span style={{ fontSize: '10px', color: '#71717a' }}>
                  (+{f.linesAdded}/-{f.linesRemoved})
                </span>
              </button>
            );
          })}
        </div>
      )}

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
            {activeTargetFile}
          </span>
          {activeIsNew && (
            <span style={{
              fontSize: '10px',
              color: '#34d399',
              background: 'rgba(16, 185, 129, 0.15)',
              padding: '2px 6px',
              borderRadius: '6px',
              fontWeight: 600
            }}>
              CREATE NEW FILE
            </span>
          )}
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
              <Plus size={11} /> {activeLinesAdded}
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
              <Minus size={11} /> {activeLinesRemoved}
            </span>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <span style={{
            fontSize: '11px',
            color: activeSyntaxValid ? '#34d399' : '#f43f5e',
            background: activeSyntaxValid ? 'rgba(16, 185, 129, 0.1)' : 'rgba(244, 63, 94, 0.1)',
            padding: '3px 9px',
            borderRadius: '9999px',
            border: `1px solid ${activeSyntaxValid ? 'rgba(16, 185, 129, 0.3)' : 'rgba(244, 63, 94, 0.3)'}`
          }}>
            {activeSyntaxValid ? 'AST Syntax Valid' : 'Syntax Error'}
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
        {(!activeUnifiedDiff || activeUnifiedDiff === '(No changes detected)' || (activeLinesAdded === 0 && activeLinesRemoved === 0)) ? (
          <div style={{
            padding: '24px 20px',
            textAlign: 'center',
            color: '#a1a1aa',
            fontSize: '13px'
          }}>
            <div style={{ color: '#38bdf8', fontWeight: 600, marginBottom: '4px' }}>
              No Changes Detected (+0 / -0)
            </div>
            <div style={{ fontSize: '12px', color: '#71717a' }}>
              The target file <code>{activeTargetFile}</code> already contains the proposed fix or matches the requested implementation state.
            </div>
          </div>
        ) : (
          diffLines.map((line, idx) => {
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
        }))}
      </div>
    </div>
  );
};
