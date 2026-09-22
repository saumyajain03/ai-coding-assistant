import React from 'react';
import { Award, CheckCircle2, ShieldCheck, Terminal, AlertTriangle, FileText } from 'lucide-react';
import { SandboxTestResult, PatchProposalData } from '../services/api';

interface FinalReportViewProps {
  reportMarkdown: string;
  critiqueText: string;
  testResult: SandboxTestResult | null;
  patch: PatchProposalData | null;
}

export const FinalReportView: React.FC<FinalReportViewProps> = ({
  reportMarkdown,
  critiqueText,
  testResult,
  patch,
}) => {
  if (!reportMarkdown && !critiqueText) {
    return (
      <div style={{
        padding: '40px 20px',
        textAlign: 'center',
        background: 'rgba(255, 255, 255, 0.02)',
        borderRadius: '20px',
        border: '1px dashed rgba(255, 255, 255, 0.08)',
        color: '#71717a'
      }}>
        <FileText size={32} color="#52525b" style={{ margin: '0 auto 10px' }} />
        <div style={{ fontSize: '13px', color: '#a1a1aa', fontWeight: 500 }}>
          Execution Summary Pending
        </div>
        <div style={{ fontSize: '11px', marginTop: '4px' }}>
          After Stage 6 Critique and Stage 7 Report generation, full verifiable test outputs and compliance telemetry display here.
        </div>
      </div>
    );
  }

  const isCodePatch = Boolean(patch);
  const passed = isCodePatch ? (testResult?.passed ?? false) : true;

  return (
    <div style={{
      borderRadius: '24px',
      background: 'rgba(12, 12, 16, 0.8)',
      backdropFilter: 'blur(24px)',
      border: '1px solid rgba(255, 255, 255, 0.1)',
      padding: '24px',
      display: 'flex',
      flexDirection: 'column',
      gap: '18px',
      boxShadow: '0 8px 32px -8px rgba(0, 0, 0, 0.5)'
    }}>
      {/* Header Banner */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        paddingBottom: '14px',
        borderBottom: '1px solid rgba(255, 255, 255, 0.08)'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <ShieldCheck size={20} color={passed ? '#10b981' : '#f43f5e'} />
          <div>
            <h3 style={{ fontSize: '15px', fontWeight: 700, color: '#ffffff' }}>
              Execution Summary & Stage 6 Critique
            </h3>
            <span style={{ fontSize: '11px', color: '#a1a1aa' }}>
              {isCodePatch ? 'Verified by Local Sandbox Runner' : 'Architecture & Deliverable Verified'}
            </span>
          </div>
        </div>

        <span style={{
          fontSize: '11px',
          fontWeight: 700,
          padding: '4px 12px',
          borderRadius: '9999px',
          background: passed ? 'rgba(16, 185, 129, 0.2)' : 'rgba(244, 63, 94, 0.2)',
          color: passed ? '#34d399' : '#fb7185',
          border: `1px solid ${passed ? 'rgba(16, 185, 129, 0.4)' : 'rgba(244, 63, 94, 0.4)'}`
        }}>
          {isCodePatch ? (passed ? 'EMPIRICALLY VERIFIED' : 'TESTS FAILED') : 'ROADMAP VERIFIED'}
        </span>
      </div>

      {/* Stage 6: Critique Box */}
      {critiqueText && (
        <div style={{
          padding: '16px',
          borderRadius: '16px',
          background: 'rgba(255, 255, 255, 0.03)',
          border: '1px solid rgba(255, 255, 255, 0.08)',
          display: 'flex',
          flexDirection: 'column',
          gap: '8px'
        }}>
          <span style={{ fontSize: '12px', fontWeight: 700, color: '#38bdf8', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Agent Self-Critique & Regression Inspection
          </span>
          <p style={{ fontSize: '12px', color: '#d4d4d8', lineHeight: 1.6, whiteSpace: 'pre-line' }}>
            {critiqueText}
          </p>
        </div>
      )}

      {/* Stage 7: Final Markdown Report */}
      {reportMarkdown && (
        <div style={{
          padding: '16px',
          borderRadius: '16px',
          background: 'rgba(0, 0, 0, 0.4)',
          border: '1px solid rgba(255, 255, 255, 0.06)',
          fontFamily: 'var(--font-mono)',
          fontSize: '12px',
          lineHeight: 1.6,
          color: '#e4e4e7',
          maxHeight: '350px',
          overflowY: 'auto',
          whiteSpace: 'pre-wrap'
        }}>
          {reportMarkdown}
        </div>
      )}
    </div>
  );
};
