import React from 'react';
import { Terminal, CheckCircle2, XCircle, Clock, AlertOctagon } from 'lucide-react';
import { SandboxTestResult } from '../services/api';

interface SandboxTerminalProps {
  testResult: SandboxTestResult | null;
  isRunning?: boolean;
}

export const SandboxTerminal: React.FC<SandboxTerminalProps> = ({
  testResult,
  isRunning = false,
}) => {
  if (!testResult && !isRunning) {
    return (
      <div style={{
        padding: '36px 20px',
        textAlign: 'center',
        background: 'rgba(255, 255, 255, 0.02)',
        borderRadius: '20px',
        border: '1px dashed rgba(255, 255, 255, 0.08)',
        color: '#71717a'
      }}>
        <Terminal size={32} color="#52525b" style={{ margin: '0 auto 10px' }} />
        <div style={{ fontSize: '13px', color: '#a1a1aa', fontWeight: 500 }}>
          Sandbox Execution Terminal Idle
        </div>
        <div style={{ fontSize: '11px', marginTop: '4px' }}>
          When Stage 5 runs tests via <code>run_sandbox_command</code>, live stdout, stderr, and resource containment telemetry stream here.
        </div>
      </div>
    );
  }

  const passed = testResult?.passed ?? false;
  const exitCode = testResult?.exitCode ?? -1;

  return (
    <div style={{
      borderRadius: '20px',
      overflow: 'hidden',
      background: '#09090b',
      border: '1px solid rgba(255, 255, 255, 0.1)',
      boxShadow: '0 12px 35px -10px rgba(0, 0, 0, 0.8)'
    }}>
      {/* Terminal Titlebar */}
      <div style={{
        padding: '12px 18px',
        background: 'rgba(255, 255, 255, 0.03)',
        borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <div style={{ display: 'flex', gap: '6px' }}>
            <span style={{ width: '10px', height: '10px', borderRadius: '50%', background: '#ef4444', display: 'inline-block' }} />
            <span style={{ width: '10px', height: '10px', borderRadius: '50%', background: '#f59e0b', display: 'inline-block' }} />
            <span style={{ width: '10px', height: '10px', borderRadius: '50%', background: '#10b981', display: 'inline-block' }} />
          </div>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: '12px', color: '#a1a1aa' }}>
            sandbox@sentinelforge:~/workspace$ {testResult?.command || 'running...'}
          </span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          {testResult && (
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              padding: '3px 10px',
              borderRadius: '9999px',
              fontSize: '11px',
              fontWeight: 600,
              background: passed ? 'rgba(16, 185, 129, 0.15)' : 'rgba(244, 63, 94, 0.15)',
              color: passed ? '#34d399' : '#fb7185',
              border: `1px solid ${passed ? 'rgba(16, 185, 129, 0.3)' : 'rgba(244, 63, 94, 0.3)'}`
            }}>
              {passed ? <CheckCircle2 size={12} /> : <XCircle size={12} />}
              {passed ? 'TESTS PASSED (Exit 0)' : `FAILED (Exit ${exitCode})`}
            </div>
          )}

          {testResult?.durationMs && (
            <span style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '11px', color: '#71717a' }}>
              <Clock size={11} /> {testResult.durationMs}ms
            </span>
          )}
        </div>
      </div>

      {/* Terminal Output Body */}
      <div style={{
        padding: '16px 20px',
        fontFamily: 'var(--font-mono)',
        fontSize: '12px',
        lineHeight: 1.55,
        color: '#e4e4e7',
        maxHeight: '260px',
        overflowY: 'auto',
        whiteSpace: 'pre-wrap',
        wordBreak: 'break-word'
      }}>
        {isRunning && (
          <div style={{ color: '#38bdf8' }} className="pulse-active">
            Executing pytest in isolated Phase 3 sandbox jail...
          </div>
        )}

        {testResult?.stdout && (
          <div style={{ color: '#d4d4d8' }}>
            {testResult.stdout}
          </div>
        )}

        {testResult?.stderr && (
          <div style={{ color: '#fb7185', marginTop: '8px' }}>
            {testResult.stderr}
          </div>
        )}
      </div>
    </div>
  );
};
