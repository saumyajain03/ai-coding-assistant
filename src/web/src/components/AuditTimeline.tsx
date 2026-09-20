import React from 'react';
import { Activity, ShieldCheck, ShieldAlert, Terminal, FileCode, CheckCircle2 } from 'lucide-react';
import { AuditEventItem } from '../services/api';

interface AuditTimelineProps {
  events: AuditEventItem[];
}

export const AuditTimeline: React.FC<AuditTimelineProps> = ({ events }) => {
  return (
    <div style={{
      borderRadius: '24px',
      background: 'rgba(12, 12, 16, 0.75)',
      backdropFilter: 'blur(24px)',
      border: '1px solid rgba(255, 255, 255, 0.08)',
      padding: '24px',
      boxShadow: '0 8px 32px -8px rgba(0, 0, 0, 0.5)'
    }}>
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        marginBottom: '18px',
        paddingBottom: '12px',
        borderBottom: '1px solid rgba(255, 255, 255, 0.06)'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Activity size={18} color="#38bdf8" />
          <h3 style={{ fontSize: '14px', fontWeight: 700, color: '#ffffff', letterSpacing: '-0.01em' }}>
            Structured Security Audit Log ({events.length})
          </h3>
        </div>
        <div style={{ fontSize: '11px', color: '#71717a' }}>
          Immutable Append-Only JSONL Stream (SHA-256 Verified)
        </div>
      </div>

      {events.length === 0 ? (
        <div style={{ padding: '30px', textAlign: 'center', color: '#71717a', fontSize: '12px' }}>
          No audit events recorded yet. All agent actions, patch proposals, and approvals append here automatically.
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
          {events.map((ev, index) => {
            const isHighRisk = ev.riskLevel === 'HIGH' || ev.riskLevel === 'CRITICAL';
            const isApproval = ev.eventType.includes('APPROVAL');
            const isPatch = ev.eventType.includes('PATCH');
            const isExec = ev.eventType.includes('COMMAND');

            let badgeBg = 'rgba(255, 255, 255, 0.06)';
            let badgeColor = '#a1a1aa';
            let icon = <Activity size={14} color="#a1a1aa" />;

            if (isHighRisk) {
              badgeBg = 'rgba(244, 63, 94, 0.14)';
              badgeColor = '#fb7185';
              icon = <ShieldAlert size={14} color="#fb7185" />;
            } else if (isApproval) {
              badgeBg = 'rgba(245, 158, 11, 0.14)';
              badgeColor = '#fbbf24';
              icon = <ShieldCheck size={14} color="#fbbf24" />;
            } else if (isPatch) {
              badgeBg = 'rgba(56, 189, 248, 0.14)';
              badgeColor = '#38bdf8';
              icon = <FileCode size={14} color="#38bdf8" />;
            } else if (isExec) {
              badgeBg = 'rgba(16, 185, 129, 0.14)';
              badgeColor = '#34d399';
              icon = <Terminal size={14} color="#34d399" />;
            }

            return (
              <div
                key={index}
                style={{
                  display: 'flex',
                  alignItems: 'flex-start',
                  gap: '12px',
                  padding: '12px 16px',
                  borderRadius: '16px',
                  background: 'rgba(255, 255, 255, 0.02)',
                  border: '1px solid rgba(255, 255, 255, 0.05)',
                  fontSize: '12px'
                }}
              >
                <div style={{
                  padding: '6px',
                  borderRadius: '10px',
                  background: badgeBg,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  flexShrink: 0
                }}>
                  {icon}
                </div>

                <div style={{ flex: 1 }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '4px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <span style={{ fontWeight: 700, color: badgeColor, fontFamily: 'var(--font-mono)' }}>
                        {ev.eventType}
                      </span>
                      <span style={{ color: '#52525b', fontSize: '10px' }}>
                        by {ev.caller}
                      </span>
                    </div>

                    <span style={{
                      fontSize: '9px',
                      fontWeight: 600,
                      padding: '2px 7px',
                      borderRadius: '9999px',
                      background: isHighRisk ? 'rgba(244, 63, 94, 0.2)' : 'rgba(255, 255, 255, 0.08)',
                      color: isHighRisk ? '#fb7185' : '#a1a1aa'
                    }}>
                      {ev.riskLevel}
                    </span>
                  </div>

                  <div style={{ color: '#d4d4d8', fontSize: '11px', fontFamily: 'var(--font-mono)' }}>
                    {JSON.stringify(ev.details)}
                  </div>

                  {ev.actionHash && (
                    <div style={{ fontSize: '10px', color: '#71717a', marginTop: '4px' }}>
                      Hash: {ev.actionHash.substring(0, 16)}...
                    </div>
                  )}
                </div>

                <div style={{ fontSize: '10px', color: '#52525b', flexShrink: 0 }}>
                  {ev.isoTime.split('T')[1]?.replace('Z', '') || ''}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
