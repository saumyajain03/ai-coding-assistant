import React from 'react';
import { ChevronDown, User } from 'lucide-react';

interface NavbarProps {
  activeTab: string;
  setActiveTab: (tab: string) => void;
  onResetWorkspace?: () => void;
}

export const Navbar: React.FC<NavbarProps> = ({
  activeTab,
  setActiveTab,
  onResetWorkspace,
}) => {
  return (
    <nav style={{
      position: 'fixed',
      insetInline: 0,
      top: '18px',
      zIndex: 50,
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      padding: '0 24px',
      height: '44px',
      pointerEvents: 'none',
    }}>
      {/* SentinelForge Brand Mark (Left) */}
      <div style={{ pointerEvents: 'auto', display: 'flex', alignItems: 'center', gap: '10px' }}>
        <a
          href="/"
          aria-label="SentinelForge"
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '10px',
            textDecoration: 'none',
            color: '#ffffff',
            opacity: 0.95,
            transition: 'opacity 0.2s',
          }}
        >
          {/* Exact geometric eclipse/circle icon */}
          <svg width="30" height="30" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
            <ellipse cx="16" cy="16" rx="14" ry="14" stroke="white" strokeWidth="2.6" />
            <path d="M4 16H28" stroke="#000000" strokeWidth="3.2" strokeLinecap="round" />
            <circle cx="16" cy="16" r="5.5" fill="white" />
          </svg>
          <span style={{
            fontSize: '18px',
            fontWeight: 800,
            letterSpacing: '-0.03em',
            color: '#ffffff',
            fontFamily: 'var(--font-sans)',
          }}>
            SentinelForge
          </span>
        </a>
      </div>

      {/* Floating Centered Pill Navigation (Exact Superbuilt Nav Style) */}
      <div
        className="sb-nav-pill"
        style={{
          pointerEvents: 'auto',
          position: 'absolute',
          left: '50%',
          transform: 'translateX(-50%)',
          display: 'flex',
          alignItems: 'center',
          gap: '28px',
          padding: '8px 28px',
          fontSize: '15px',
          fontWeight: 600,
          color: '#ffffff',
          boxShadow: '0 10px 30px rgba(0, 0, 0, 0.45)'
        }}
      >
        <button
          onClick={() => setActiveTab('workspace')}
          style={{
            background: 'none',
            border: 'none',
            color: activeTab === 'workspace' ? '#ffffff' : 'rgba(255, 255, 255, 0.75)',
            fontSize: '14px',
            fontWeight: activeTab === 'workspace' ? 700 : 500,
            cursor: 'pointer',
            padding: 0,
            transition: 'opacity 0.2s',
          }}
        >
          Agent Workspace
        </button>

        <button
          onClick={() => setActiveTab('diff')}
          style={{
            background: 'none',
            border: 'none',
            color: activeTab === 'diff' ? '#ffffff' : 'rgba(255, 255, 255, 0.75)',
            fontSize: '14px',
            fontWeight: activeTab === 'diff' ? 700 : 500,
            cursor: 'pointer',
            padding: 0,
            transition: 'opacity 0.2s',
          }}
        >
          Patch Diff
        </button>

        <button
          onClick={() => setActiveTab('timeline')}
          style={{
            background: 'none',
            border: 'none',
            color: activeTab === 'timeline' ? '#ffffff' : 'rgba(255, 255, 255, 0.75)',
            fontSize: '14px',
            fontWeight: activeTab === 'timeline' ? 700 : 500,
            cursor: 'pointer',
            padding: 0,
            transition: 'opacity 0.2s',
          }}
        >
          Security Audit
        </button>

        <div style={{ display: 'flex', alignItems: 'center', gap: '4px', cursor: 'pointer', opacity: 0.85 }}>
          <span style={{ fontSize: '14px', fontWeight: 500 }}>More</span>
          <ChevronDown size={14} />
        </div>
      </div>

      {/* Right Buttons: Glass "Reset Workspace", White "Run Agent", Circle Account Button */}
      <div style={{ pointerEvents: 'auto', display: 'flex', alignItems: 'center', gap: '12px' }}>
        <button
          onClick={onResetWorkspace}
          className="sb-btn-glass"
          style={{ padding: '8px 18px', fontSize: '13px' }}
        >
          Reset Workspace
        </button>

        <button
          className="sb-btn-white"
          style={{ padding: '8px 22px', fontSize: '13px' }}
        >
          Launch Sandbox
        </button>

        <div style={{
          width: '38px',
          height: '38px',
          borderRadius: '50%',
          border: '1px solid rgba(255, 255, 255, 0.25)',
          background: 'rgba(255, 255, 255, 0.1)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          cursor: 'pointer',
          transition: 'border-color 0.2s',
        }}>
          <User size={18} color="#ffffff" />
        </div>
      </div>
    </nav>
  );
};
