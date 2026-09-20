import React from 'react';
import { ShieldAlert, Check, X, KeyRound, AlertTriangle, FileCode } from 'lucide-react';
import { PatchProposalData } from '../services/api';

interface ApprovalModalProps {
  patch: PatchProposalData;
  isOpen: boolean;
  onApprove: () => void;
  onReject: () => void;
  onClose: () => void;
}

export const ApprovalModal: React.FC<ApprovalModalProps> = ({
  patch,
  isOpen,
  onApprove,
  onReject,
  onClose,
}) => {
  if (!isOpen) return null;

  return (
    <div style={{
      position: 'fixed',
      inset: 0,
      zIndex: 100,
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      background: 'rgba(0, 0, 0, 0.78)',
      backdropFilter: 'blur(20px)',
      WebkitBackdropFilter: 'blur(20px)',
      padding: '20px'
    }}>
      <div style={{
        width: '100%',
        maxWidth: '580px',
        borderRadius: '28px',
        background: 'rgba(16, 16, 20, 0.95)',
        border: '1px solid rgba(255, 255, 255, 0.16)',
        boxShadow: '0 25px 60px -15px rgba(0, 0, 0, 0.9), 0 0 50px -10px rgba(245, 158, 11, 0.25)',
        padding: '28px',
        display: 'flex',
        flexDirection: 'column',
        gap: '20px',
        animation: 'fadeIn 0.25s cubic-bezier(0.16, 1, 0.3, 1)'
      }}>
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
          <div style={{
            width: '46px',
            height: '46px',
            borderRadius: '16px',
            background: 'rgba(245, 158, 11, 0.14)',
            border: '1px solid rgba(245, 158, 11, 0.35)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            boxShadow: '0 0 20px rgba(245, 158, 11, 0.2)'
          }}>
            <ShieldAlert size={24} color="#f59e0b" />
          </div>
          <div>
            <h3 style={{ fontSize: '18px', fontWeight: 700, color: '#ffffff', letterSpacing: '-0.01em' }}>
              Human Authorization Gate (HITL)
            </h3>
            <p style={{ fontSize: '12px', color: '#a1a1aa', marginTop: '2px' }}>
              Disk modification is blocked pending explicit operator approval.
            </p>
          </div>
        </div>

        {/* Security Binding Details Box */}
        <div style={{
          padding: '16px',
          borderRadius: '16px',
          background: 'rgba(255, 255, 255, 0.03)',
          border: '1px solid rgba(255, 255, 255, 0.08)',
          display: 'flex',
          flexDirection: 'column',
          gap: '10px',
          fontSize: '12px'
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ color: '#71717a' }}>Action Target:</span>
            <span style={{ fontFamily: 'var(--font-mono)', color: '#38bdf8', fontWeight: 600 }}>
              {patch.targetFile}
            </span>
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ color: '#71717a' }}>Request ID:</span>
            <span style={{ fontFamily: 'var(--font-mono)', color: '#ffffff' }}>
              {patch.requestId}
            </span>
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ color: '#71717a' }}>Action Hash:</span>
            <span style={{ fontFamily: 'var(--font-mono)', color: '#e4e4e7', background: 'rgba(255, 255, 255, 0.06)', padding: '2px 6px', borderRadius: '4px' }}>
              {patch.actionHash.substring(0, 16)}...
            </span>
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ color: '#71717a' }}>Estimated Risk:</span>
            <span style={{
              color: patch.riskScore >= 5 ? '#f43f5e' : (patch.riskScore >= 3 ? '#f59e0b' : '#10b981'),
              fontWeight: 600
            }}>
              {patch.riskScore >= 5 ? 'HIGH RISK' : (patch.riskScore >= 3 ? 'MEDIUM RISK' : 'LOW RISK')} ({patch.riskScore}/10)
            </span>
          </div>
        </div>

        {/* Security Invariant Guarantee */}
        <div style={{
          display: 'flex',
          alignItems: 'flex-start',
          gap: '10px',
          padding: '12px 14px',
          borderRadius: '12px',
          background: 'rgba(56, 189, 248, 0.06)',
          border: '1px solid rgba(56, 189, 248, 0.2)',
          fontSize: '11px',
          color: '#bae6fd',
          lineHeight: 1.5
        }}>
          <KeyRound size={16} color="#38bdf8" style={{ flexShrink: 0, marginTop: '2px' }} />
          <span>
            <strong>Single-Use Cryptographic Token:</strong> Authorizing this proposal generates an immutable token bound specifically to this action hash. It cannot be replayed or repurposed.
          </span>
        </div>

        {/* Action Buttons */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: '12px', marginTop: '6px' }}>
          <button
            onClick={onReject}
            className="btn-danger"
          >
            <X size={15} />
            Reject & Block Patch
          </button>

          <button
            onClick={onApprove}
            className="btn-success"
          >
            <Check size={15} />
            Authorize & Apply Patch
          </button>
        </div>
      </div>
    </div>
  );
};
