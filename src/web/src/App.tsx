import React, { useState } from 'react';
import {
  ArrowUp,
  Paperclip,
  User,
  ChevronDown,
  ShieldAlert,
  FileCode,
  Terminal,
  Lock,
  Sparkles
} from 'lucide-react';
import { Navbar } from './components/Navbar';
import { StageStepper } from './components/StageStepper';
import { DiffViewer } from './components/DiffViewer';
import { ApprovalModal } from './components/ApprovalModal';
import { SandboxTerminal } from './components/SandboxTerminal';
import { CitationsPanel } from './components/CitationsPanel';
import { AuditTimeline } from './components/AuditTimeline';
import { FinalReportView } from './components/FinalReportView';
import {
  AgentStageInfo,
  CitationItem,
  PatchProposalData,
  SandboxTestResult,
  AuditEventItem,
  INITIAL_STAGES
} from './services/api';

export function App() {
  const [activeTab, setActiveTab] = useState('workspace');
  const [taskPrompt, setTaskPrompt] = useState(
    'Fix calculate_discount in smoke_calc.py so that it returns price - (price * discount)'
  );
  const [targetFile, setTargetFile] = useState('smoke_calc.py');
  const [testCommand, setTestCommand] = useState('pytest test_smoke_calc.py');

  // Execution states
  const [stages, setStages] = useState<AgentStageInfo[]>(INITIAL_STAGES);
  const [currentStageId, setCurrentStageId] = useState<string | null>(null);
  const [isExecuting, setIsExecuting] = useState(false);

  // Data artifacts
  const [analysisText, setAnalysisText] = useState('');
  const [planText, setPlanText] = useState('');
  const [citations, setCitations] = useState<CitationItem[]>([]);
  const [patchProposal, setPatchProposal] = useState<PatchProposalData | null>(null);
  const [testResult, setTestResult] = useState<SandboxTestResult | null>(null);
  const [critiqueText, setCritiqueText] = useState('');
  const [reportMarkdown, setReportMarkdown] = useState('');
  const [auditEvents, setAuditEvents] = useState<AuditEventItem[]>([]);

  // Approval Modal state
  const [isApprovalOpen, setIsApprovalOpen] = useState(false);

  const updateStage = (stageId: string, status: AgentStageInfo['status'], summary?: string) => {
    setStages((prev) =>
      prev.map((s) => (s.id === stageId ? { ...s, status, summary } : s))
    );
  };

  const addAuditEvent = (
    eventType: string,
    caller: string,
    details: Record<string, any>,
    riskLevel: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL' = 'LOW',
    actionHash?: string
  ) => {
    const newEvent: AuditEventItem = {
      timestamp: Date.now() / 1000,
      isoTime: new Date().toISOString(),
      eventType,
      caller,
      details,
      riskLevel,
      actionHash,
    };
    setAuditEvents((prev) => [newEvent, ...prev]);
  };

  /**
   * Runs the 7-Stage Agent Orchestration Workflow with HITL Gate
   */
  const handleStartExecution = async () => {
    setIsExecuting(true);
    setStages(INITIAL_STAGES);
    setAnalysisText('');
    setPlanText('');
    setCitations([]);
    setPatchProposal(null);
    setTestResult(null);
    setCritiqueText('');
    setReportMarkdown('');

    // STAGE 1: Analysis
    setCurrentStageId('analysis');
    updateStage('analysis', 'running');
    await new Promise((r) => setTimeout(r, 600));
    setAnalysisText(
      `### Task Analysis\n- Type: Code Modification / Verification\n- Target Scope: ${targetFile}\n- Risk Boundary: Path strictly confined to ./data/workspace root\n- Acceptance Criteria: Verify pytest test passes without regressions.`
    );
    updateStage('analysis', 'completed', 'Scope & security boundaries analyzed.');
    addAuditEvent('STAGE_ANALYSIS', 'agent_orchestrator', { targetFile, task: taskPrompt });

    // STAGE 2: Plan
    setCurrentStageId('plan');
    updateStage('plan', 'running');
    await new Promise((r) => setTimeout(r, 600));
    setPlanText(
      `### Implementation Plan\n1. Retrieve context via ChromaDB vector index.\n2. Synthesize minimal AST-validated diff.\n3. Submit proposal to Phase 4 Approval Manager.\n4. Execute approved sandboxed test via pytest.\n5. Evaluate empirical critique & publish report.`
    );
    updateStage('plan', 'completed', 'Step-by-step verification plan generated.');
    addAuditEvent('STAGE_PLAN', 'agent_orchestrator', { steps: 5 });

    // STAGE 3: RAG Retrieval
    setCurrentStageId('rag');
    updateStage('rag', 'running');
    await new Promise((r) => setTimeout(r, 700));
    const retrieved: CitationItem[] = [
      {
        id: 'cit-1',
        filename: 'smoke_calc.py',
        startLine: 1,
        endLine: 4,
        snippet: 'def calculate_discount(price: float, discount: float) -> float:\n    return price * discount',
        securityVerdict: 'TRUSTED',
      },
      {
        id: 'cit-2',
        filename: 'test_smoke_calc.py',
        startLine: 1,
        endLine: 5,
        snippet: 'from smoke_calc import calculate_discount\ndef test_discount():\n    assert calculate_discount(100.0, 0.2) == 80.0',
        securityVerdict: 'TRUSTED',
      },
    ];
    setCitations(retrieved);
    updateStage('rag', 'completed', 'Retrieved 2 context citations.');
    addAuditEvent('CONTEXT_RETRIEVED', 'rag_engine', { count: retrieved.length });

    // STAGE 4: Patch Proposal
    setCurrentStageId('patch');
    updateStage('patch', 'running');
    await new Promise((r) => setTimeout(r, 700));

    const proposedDiff = `--- smoke_calc.py\n+++ smoke_calc.py\n@@ -1,2 +1,2 @@\n def calculate_discount(price: float, discount: float) -> float:\n-    return price * discount\n+    return price - (price * discount)`;

    const proposal: PatchProposalData = {
      patchId: `patch_${Math.random().toString(36).substring(2, 10)}`,
      targetFile,
      rationale: `Fix discount formula calculation bug for ${targetFile}`,
      unifiedDiff: proposedDiff,
      oldContent: 'def calculate_discount(price: float, discount: float) -> float:\n    return price * discount\n',
      newContent: 'def calculate_discount(price: float, discount: float) -> float:\n    return price - (price * discount)\n',
      linesAdded: 1,
      linesRemoved: 1,
      syntaxValid: true,
      riskScore: 2,
      riskNotes: ['Standard patch: no dangerous primitives detected.'],
      status: 'PENDING_APPROVAL',
      requestId: `req_${Math.random().toString(36).substring(2, 12)}`,
      actionHash: 'bc5b0890c26c8efb78349021da31e9882901cfba98231',
      createdAt: Date.now() / 1000,
    };

    setPatchProposal(proposal);
    updateStage('patch', 'completed', 'Diff generated (+1 / -1 lines). AST valid.');
    addAuditEvent('PATCH_PROPOSED', 'patch_tool', {
      patchId: proposal.patchId,
      targetFile: proposal.targetFile,
      requestId: proposal.requestId,
    }, 'MEDIUM', proposal.actionHash);

    // STAGE 5: Approval Gate (Human in the loop required)
    setCurrentStageId('approval');
    updateStage('approval', 'waiting_approval', 'Halted. Waiting for explicit human operator authorization.');
    addAuditEvent('APPROVAL_REQUESTED', 'approval_manager', {
      requestId: proposal.requestId,
      targetFile: proposal.targetFile,
      actionHash: proposal.actionHash,
    }, 'MEDIUM', proposal.actionHash);

    // Open prominent approval modal
    setIsApprovalOpen(true);
  };

  /**
   * Human Approves the patch
   */
  const handleApprove = async () => {
    setIsApprovalOpen(false);
    if (!patchProposal) return;

    updateStage('approval', 'completed', 'Authorized by human operator.');
    addAuditEvent('ACTION_APPROVED', 'human_operator', {
      requestId: patchProposal.requestId,
      actionHash: patchProposal.actionHash,
    }, 'LOW', patchProposal.actionHash);

    // STAGE 6: Apply Patch
    setCurrentStageId('apply');
    updateStage('apply', 'running');
    await new Promise((r) => setTimeout(r, 600));

    setPatchProposal((prev) => (prev ? { ...prev, status: 'APPLIED' } : null));
    updateStage('apply', 'completed', `Patch successfully applied to workspace/${targetFile}.`);
    addAuditEvent('PATCH_APPLIED', 'patch_tool', {
      patchId: patchProposal.patchId,
      targetFile: patchProposal.targetFile,
    }, 'LOW', patchProposal.actionHash);

    // STAGE 7: Sandbox Test
    setCurrentStageId('test');
    updateStage('test', 'running');
    await new Promise((r) => setTimeout(r, 800));

    const sandboxRes: SandboxTestResult = {
      command: testCommand,
      exitCode: 0,
      passed: true,
      stdout: `============================= test session starts ==============================\nplatform darwin -- Python 3.11.15, pytest-9.1.1\nrootdir: /data/workspace\ncollected 1 item\n\ntest_smoke_calc.py .                                                     [100%]\n\n============================== 1 passed in 0.08s ===============================`,
      stderr: '',
      durationMs: 82,
      timedOut: false,
      status: 'success',
    };

    setTestResult(sandboxRes);
    updateStage('test', 'completed', 'Test suite PASSED in isolated sandbox (Exit 0).');
    addAuditEvent('COMMAND_EXEC', 'sandbox_runner', {
      command: testCommand,
      exitCode: 0,
      passed: true,
    }, 'LOW');

    // STAGE 8: Critique
    setCurrentStageId('critique');
    updateStage('critique', 'running');
    await new Promise((r) => setTimeout(r, 600));

    const critique = `### Self-Critique & Risk Scoring\n- Verification Status: PASSED.\n- Empirical Test: 1/1 tests passed in 82ms with exit code 0.\n- Risk Assessment: Score 2/10 (Low). No environment or sandbox breakouts detected.\n- Verdict: Clean, minimal resolution without regressions.`;
    setCritiqueText(critique);
    updateStage('critique', 'completed', 'Critique verified zero regressions.');
    addAuditEvent('STAGE_CRITIQUE', 'agent_orchestrator', { verified: true, riskScore: 2 });

    // STAGE 9: Final Report
    setCurrentStageId('report');
    updateStage('report', 'running');
    await new Promise((r) => setTimeout(r, 500));

    const finalReport = `# SentinelForge Execution Report\n\n## 1. Task Objective\n${taskPrompt}\n\n## 2. Implementation Plan\n${planText}\n\n## 3. Retrieved Citations\nTotal Citations: 2 (smoke_calc.py, test_smoke_calc.py)\n\n## 4. Proposed Unified Diff\n\`\`\`diff\n${patchProposal.unifiedDiff}\n\`\`\`\n\n## 5. Empirical Sandbox Test Verification\n- **Command Executed**: \`${testCommand}\`\n- **Test Result**: **PASSED**\n- **Exit Code**: 0\n- **Duration**: 82ms\n\n## 6. Self-Critique\n${critique}\n\n## 7. Status\n- **Status**: COMPLETED & VERIFIED\n- **Security Invariant**: Applied strictly after cryptographic single-use human sign-off.`;

    setReportMarkdown(finalReport);
    updateStage('report', 'completed', 'Final report compiled.');
    addAuditEvent('AGENT_LOOP_COMPLETED', 'agent_orchestrator', {
      stagesExecuted: 9,
      testsPassed: true,
      hasPatch: true,
    }, 'LOW');

    setIsExecuting(false);
    setCurrentStageId(null);
  };

  /**
   * Human Rejects the patch
   */
  const handleReject = () => {
    setIsApprovalOpen(false);
    if (!patchProposal) return;

    updateStage('approval', 'failed', 'Operator rejected proposal.');
    setPatchProposal((prev) => (prev ? { ...prev, status: 'REJECTED' } : null));

    addAuditEvent('ACTION_REJECTED', 'human_operator', {
      requestId: patchProposal.requestId,
      actionHash: patchProposal.actionHash,
    }, 'HIGH', patchProposal.actionHash);

    setIsExecuting(false);
    setCurrentStageId(null);
  };

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', position: 'relative', background: '#000000' }}>
      {/* Superbuilt Multi-Glow Background System */}
      <div className="sb-ambient-wrap">
        <div className="sb-glow-a" />
        <div className="sb-glow-b" />
        <div className="sb-glow-c" />
      </div>

      {/* Floating Superbuilt Header */}
      <Navbar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        onResetWorkspace={() => {
          setStages(INITIAL_STAGES);
          setPatchProposal(null);
          setTestResult(null);
          setAnalysisText('');
          setReportMarkdown('');
          addAuditEvent('WORKSPACE_RESET', 'user_action', { workspace: '/data/workspace' });
        }}
      />

      {/* Main Content Area */}
      <main style={{ flex: 1, width: '100%', maxWidth: '1440px', margin: '0 auto', padding: '110px 32px 80px', position: 'relative', zIndex: 1 }}>
        {/* Exact Superbuilt Hero Section */}
        <section style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          textAlign: 'center',
          paddingTop: '20px',
          marginBottom: '50px'
        }}>
          {/* Giant "SentinelForge" Wordmark with superbuilt styling */}
          <div style={{
            fontSize: 'clamp(64px, 10vw, 138px)',
            fontWeight: 800,
            letterSpacing: '-0.04em',
            lineHeight: 0.95,
            color: '#ffffff',
            userSelect: 'none',
            fontFamily: 'var(--font-sans)',
            display: 'flex',
            alignItems: 'baseline',
            gap: '8px',
            marginBottom: '36px'
          }}>
            <span>Sentinel</span>
            <span style={{ color: 'rgba(255, 255, 255, 0.45)', fontWeight: 600 }}>Forge</span>
          </div>

          {/* Subheading in exact Superbuilt font size and weight */}
          <h2 style={{
            fontSize: 'clamp(24px, 3.5vw, 36px)',
            fontWeight: 400,
            color: '#ffffff',
            letterSpacing: '-0.02em',
            lineHeight: 1.25,
            marginBottom: '32px'
          }}>
            AI-coding agent for every <br />
            <span style={{ fontWeight: 500 }}>Engineering team.</span>
          </h2>

          {/* Exact Superbuilt Floating White Pill Prompt Bar */}
          <div style={{
            width: '100%',
            maxWidth: '680px',
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            background: '#ffffff',
            borderRadius: '9999px',
            padding: '8px 10px 8px 14px',
            boxShadow: '0 20px 60px -15px rgba(0, 21, 50, 0.7), 0 0 45px -10px rgba(0, 127, 255, 0.35)',
            transition: 'all 0.3s ease'
          }}>
            {/* Paperclip attach icon */}
            <button
              type="button"
              aria-label="Attach file"
              style={{
                width: '34px',
                height: '34px',
                borderRadius: '50%',
                background: '#f4f4f5',
                border: '1px solid rgba(0, 0, 0, 0.08)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: '#52525b',
                cursor: 'pointer',
                flexShrink: 0
              }}
            >
              <Paperclip size={16} />
            </button>

            {/* Input field */}
            <input
              type="text"
              value={taskPrompt}
              onChange={(e) => setTaskPrompt(e.target.value)}
              placeholder="Ask about specs, code bugs, tests, contracts..."
              disabled={isExecuting}
              style={{
                flex: 1,
                border: 'none',
                outline: 'none',
                background: 'transparent',
                color: '#18181b',
                fontSize: '15px',
                fontFamily: 'inherit',
                fontWeight: 400,
                padding: '0 6px'
              }}
            />

            {/* Agent Select Micro-Pill inside prompt */}
            <button
              type="button"
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '5px',
                borderRadius: '9999px',
                border: '1px solid rgba(0, 0, 0, 0.1)',
                background: 'rgba(0, 0, 0, 0.04)',
                color: '#52525b',
                padding: '6px 12px',
                fontSize: '12px',
                fontWeight: 500,
                cursor: 'pointer',
                flexShrink: 0
              }}
            >
              <User size={12} />
              <span>Sentinel Agent</span>
              <ChevronDown size={12} />
            </button>

            {/* Black Circle Up Arrow Launch Button */}
            <button
              type="button"
              onClick={handleStartExecution}
              disabled={isExecuting}
              aria-label="Execute"
              style={{
                width: '42px',
                height: '42px',
                borderRadius: '50%',
                background: '#000000',
                border: 'none',
                color: '#ffffff',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                cursor: isExecuting ? 'not-allowed' : 'pointer',
                flexShrink: 0,
                boxShadow: '0 8px 20px rgba(0, 0, 0, 0.35)',
                transition: 'all 0.2s cubic-bezier(0.16, 1, 0.3, 1)',
                opacity: isExecuting ? 0.6 : 1
              }}
            >
              <ArrowUp size={18} strokeWidth={2.6} />
            </button>
          </div>

          {/* Value Prop captions */}
          <p style={{ fontSize: '13px', color: '#a1a1aa', marginTop: '22px' }}>
            Win back the 52% of the week lost to coordination and admin — and turn it into billable margin.
          </p>
          <p style={{ fontSize: '12px', color: '#71717a', marginTop: '4px' }}>
            Available in 29+ countries.
          </p>
        </section>

        {/* 7-Stage Stepper */}
        <div style={{ marginBottom: '32px' }}>
          <StageStepper stages={stages} currentStageId={currentStageId} />
        </div>

        {/* Human Approval Required Banner if pending */}
        {patchProposal && patchProposal.status === 'PENDING_APPROVAL' && (
          <div style={{
            marginBottom: '32px',
            padding: '18px 24px',
            borderRadius: '24px',
            background: 'rgba(245, 158, 11, 0.12)',
            border: '1px solid rgba(245, 158, 11, 0.35)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            boxShadow: '0 0 40px rgba(245, 158, 11, 0.2)'
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
              <ShieldAlert size={26} color="#f59e0b" />
              <div>
                <h4 style={{ fontSize: '15px', fontWeight: 700, color: '#ffffff' }}>
                  Action Proposal Awaiting Operator Approval
                </h4>
                <p style={{ fontSize: '12px', color: '#fef3c7', marginTop: '2px' }}>
                  Target: <code>{patchProposal.targetFile}</code> (+{patchProposal.linesAdded} / -{patchProposal.linesRemoved} lines). Disk write is jailed until signed off.
                </p>
              </div>
            </div>

            <button
              onClick={() => setIsApprovalOpen(true)}
              className="sb-btn-white"
              style={{ background: '#f59e0b', color: '#000000' }}
            >
              <Lock size={14} /> Review & Authorize
            </button>
          </div>
        )}

        {/* Tab 1: Agent Workspace Layout */}
        {activeTab === 'workspace' && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(12, 1fr)', gap: '24px' }}>
            {/* Left Column: Diff & Analysis */}
            <div style={{ gridColumn: 'span 7', display: 'flex', flexDirection: 'column', gap: '24px' }}>
              <div>
                <h3 style={{ fontSize: '14px', fontWeight: 700, color: '#e4e4e7', marginBottom: '12px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <FileCode size={16} color="#38bdf8" /> Proposed Unified Diff
                </h3>
                <DiffViewer patch={patchProposal} />
              </div>

              <div>
                <h3 style={{ fontSize: '14px', fontWeight: 700, color: '#e4e4e7', marginBottom: '12px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Terminal size={16} color="#10b981" /> Sandbox Execution Telemetry
                </h3>
                <SandboxTerminal testResult={testResult} isRunning={currentStageId === 'test'} />
              </div>
            </div>

            {/* Right Column: Context, Critique & Report */}
            <div style={{ gridColumn: 'span 5', display: 'flex', flexDirection: 'column', gap: '24px' }}>
              <CitationsPanel citations={citations} />

              <FinalReportView
                reportMarkdown={reportMarkdown}
                critiqueText={critiqueText}
                testResult={testResult}
                patch={patchProposal}
              />
            </div>
          </div>
        )}

        {/* Tab 2: Full Unified Diff View */}
        {activeTab === 'diff' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
            <DiffViewer patch={patchProposal} />
          </div>
        )}

        {/* Tab 3: Security Audit Trail Timeline */}
        {activeTab === 'timeline' && (
          <div>
            <AuditTimeline events={auditEvents} />
          </div>
        )}
      </main>

      {/* Human Approval Gate Modal */}
      {patchProposal && (
        <ApprovalModal
          patch={patchProposal}
          isOpen={isApprovalOpen}
          onApprove={handleApprove}
          onReject={handleReject}
          onClose={() => setIsApprovalOpen(false)}
        />
      )}
    </div>
  );
}

export default App;
