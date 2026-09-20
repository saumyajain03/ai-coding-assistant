import React from 'react';
import { CheckCircle2, Clock, AlertTriangle, XCircle, ArrowRight, ShieldCheck } from 'lucide-react';
import { AgentStageInfo } from '../services/api';

interface StageStepperProps {
  stages: AgentStageInfo[];
  currentStageId: string | null;
  onSelectStage?: (stageId: string) => void;
}

export const StageStepper: React.FC<StageStepperProps> = ({
  stages,
  currentStageId,
  onSelectStage,
}) => {
  return (
    <div style={{
      width: '100%',
      padding: '16px 20px',
      borderRadius: '24px',
      background: 'rgba(14, 14, 18, 0.65)',
      backdropFilter: 'blur(20px)',
      WebkitBackdropFilter: 'blur(20px)',
      border: '1px solid rgba(255, 255, 255, 0.08)',
      boxShadow: '0 8px 32px -8px rgba(0, 0, 0, 0.5)'
    }}>
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        marginBottom: '14px',
        paddingBottom: '10px',
        borderBottom: '1px solid rgba(255, 255, 255, 0.06)'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <ShieldCheck size={16} color="#38bdf8" />
          <span style={{ fontSize: '12px', fontWeight: 700, letterSpacing: '0.04em', textTransform: 'uppercase', color: '#e4e4e7' }}>
            7-Stage Verifiable Agent Orchestration
          </span>
        </div>
        <div style={{ fontSize: '11px', color: '#71717a' }}>
          Non-bypassable Sandbox & HITL Boundary
        </div>
      </div>

      {/* Stepper Flow Layout */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: '8px',
        overflowX: 'auto',
        paddingBottom: '4px'
      }}>
        {stages.map((stage, index) => {
          const isCurrent = currentStageId === stage.id;
          const isCompleted = stage.status === 'completed';
          const isWaiting = stage.status === 'waiting_approval';
          const isFailed = stage.status === 'failed';
          const isRunning = stage.status === 'running';

          let badgeColor = '#52525b';
          let bgColor = 'rgba(255, 255, 255, 0.02)';
          let borderColor = 'rgba(255, 255, 255, 0.06)';
          let icon = <Clock size={13} color="#71717a" />;

          if (isCompleted) {
            badgeColor = '#10b981';
            bgColor = 'rgba(16, 185, 129, 0.08)';
            borderColor = 'rgba(16, 185, 129, 0.25)';
            icon = <CheckCircle2 size={13} color="#10b981" />;
          } else if (isWaiting) {
            badgeColor = '#f59e0b';
            bgColor = 'rgba(245, 158, 11, 0.12)';
            borderColor = 'rgba(245, 158, 11, 0.4)';
            icon = <AlertTriangle size={13} color="#f59e0b" />;
          } else if (isRunning) {
            badgeColor = '#38bdf8';
            bgColor = 'rgba(56, 189, 248, 0.12)';
            borderColor = 'rgba(56, 189, 248, 0.4)';
            icon = <Clock size={13} color="#38bdf8" className="pulse-active" />;
          } else if (isFailed) {
            badgeColor = '#f43f5e';
            bgColor = 'rgba(244, 63, 94, 0.12)';
            borderColor = 'rgba(244, 63, 94, 0.35)';
            icon = <XCircle size={13} color="#f43f5e" />;
          }

          return (
            <React.Fragment key={stage.id}>
              <div
                onClick={() => onSelectStage && onSelectStage(stage.id)}
                style={{
                  flexShrink: 0,
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  padding: '8px 14px',
                  borderRadius: '16px',
                  background: bgColor,
                  border: `1px solid ${borderColor}`,
                  cursor: onSelectStage ? 'pointer' : 'default',
                  transition: 'all 0.2s cubic-bezier(0.16, 1, 0.3, 1)',
                  boxShadow: isCurrent ? `0 0 20px ${borderColor}` : 'none'
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  {icon}
                </div>
                <div>
                  <div style={{
                    fontSize: '11px',
                    fontWeight: isCurrent ? 700 : 600,
                    color: isCompleted ? '#ffffff' : (isRunning ? '#38bdf8' : (isWaiting ? '#fbbf24' : '#a1a1aa'))
                  }}>
                    {index + 1}. {stage.name}
                  </div>
                  <div style={{
                    fontSize: '9px',
                    color: isWaiting ? '#f59e0b' : '#71717a',
                    fontWeight: isWaiting ? 600 : 400
                  }}>
                    {stage.status.toUpperCase()}
                  </div>
                </div>
              </div>

              {index < stages.length - 1 && (
                <ArrowRight size={12} color="rgba(255, 255, 255, 0.2)" style={{ flexShrink: 0 }} />
              )}
            </React.Fragment>
          );
        })}
      </div>
    </div>
  );
};
