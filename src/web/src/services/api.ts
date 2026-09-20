/**
 * SentinelForge Frontend Service Abstraction Layer
 * Exposes clean interfaces for Agent Execution, Approval Gate, RAG Retrieval,
 * Telemetry, and Sandbox Execution.
 *
 * Current State: High-fidelity simulation mode connected to full agent workflow
 * Future State: Simply switch USE_REAL_API = true when FastAPI backend is mounted.
 */

export const USE_REAL_API = false;
export const API_BASE_URL = 'http://localhost:8000/api/v1';

export interface AgentStageInfo {
  id: string;
  name: string;
  description: string;
  status: 'idle' | 'running' | 'completed' | 'waiting_approval' | 'failed';
  summary?: string;
  durationMs?: number;
  data?: any;
}

export interface CitationItem {
  id: string;
  filename: string;
  page?: number;
  startLine?: number;
  endLine?: number;
  snippet: string;
  similarityScore?: number;
  securityVerdict?: 'TRUSTED' | 'SANITIZED' | 'UNTRUSTED_WRAPPED';
}

export interface PatchProposalData {
  patchId: string;
  targetFile: string;
  rationale: string;
  unifiedDiff: string;
  oldContent: string;
  newContent: string;
  linesAdded: number;
  linesRemoved: number;
  syntaxValid: boolean;
  syntaxError?: string | null;
  riskScore: number; // 1 to 10
  riskNotes: string[];
  status: 'PENDING_APPROVAL' | 'APPROVED' | 'REJECTED' | 'APPLIED';
  requestId: string;
  actionHash: string;
  createdAt: number;
}

export interface SandboxTestResult {
  command: string;
  exitCode: number;
  passed: boolean;
  stdout: string;
  stderr: string;
  durationMs: number;
  timedOut: boolean;
  status: 'success' | 'failed' | 'timeout' | 'blocked';
}

export interface AuditEventItem {
  timestamp: number;
  isoTime: string;
  eventType: string;
  caller: string;
  details: Record<string, any>;
  riskLevel: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
  requestId?: string;
  actionHash?: string;
}

export interface AgentExecutionState {
  taskId: string;
  taskPrompt: string;
  targetFile: string;
  testCommand: string;
  status: 'idle' | 'running' | 'waiting_approval' | 'approved' | 'rejected' | 'completed' | 'failed';
  currentStageId: string | null;
  stages: AgentStageInfo[];
  analysisText: string;
  planText: string;
  citations: CitationItem[];
  patchProposal: PatchProposalData | null;
  testResult: SandboxTestResult | null;
  critiqueText: string;
  finalReportMarkdown: string;
  auditEvents: AuditEventItem[];
  executionStartTime?: number;
  executionEndTime?: number;
}

// Initial default state
export const INITIAL_STAGES: AgentStageInfo[] = [
  { id: 'analysis', name: 'Analysis', description: 'Analyze requirements, isolate risks & set scope', status: 'idle' },
  { id: 'plan', name: 'Plan', description: 'Discrete step-by-step resolution plan', status: 'idle' },
  { id: 'rag', name: 'RAG Retrieval', description: 'Query vector database & lexical citations', status: 'idle' },
  { id: 'patch', name: 'Patch Proposal', description: 'Unified diff synthesis & AST syntax validation', status: 'idle' },
  { id: 'approval', name: 'Human Approval', description: 'Operator authorization & single-use token binding', status: 'idle' },
  { id: 'apply', name: 'Apply Patch', description: 'Secure disk modification within workspace jail', status: 'idle' },
  { id: 'test', name: 'Sandbox Test', description: 'Dual-runtime test execution in resource sandbox', status: 'idle' },
  { id: 'critique', name: 'Critique', description: 'Truthful empirical assessment & risk evaluation', status: 'idle' },
  { id: 'report', name: 'Final Report', description: 'Comprehensive verifiable completion summary', status: 'idle' },
];

/**
 * Service Client
 */
export const AgentService = {
  /**
   * Dispatches an agent execution task.
   */
  async startAgentTask(
    prompt: string,
    targetFile: string = 'smoke_calc.py',
    testCommand: string = 'pytest test_smoke_calc.py'
  ): Promise<{ taskId: string }> {
    if (USE_REAL_API) {
      const res = await fetch(`${API_BASE_URL}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt, target_file: targetFile, test_command: testCommand }),
      });
      return await res.json();
    }

    // High fidelity simulation taskId
    return { taskId: `task_${Date.now().toString(36)}` };
  },

  /**
   * Responds to an approval gate request
   */
  async submitHumanApproval(
    requestId: string,
    actionHash: string,
    decision: 'approve' | 'reject',
    reason?: string
  ): Promise<{ approved: boolean; status: string }> {
    if (USE_REAL_API) {
      const res = await fetch(`${API_BASE_URL}/patches/action`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          request_id: requestId,
          action_hash: actionHash,
          action: decision,
          reason,
        }),
      });
      return await res.json();
    }

    return {
      approved: decision === 'approve',
      status: decision === 'approve' ? 'APPROVED' : 'REJECTED',
    };
  },

  /**
   * Retrieves current system telemetry & audit trail
   */
  async getSystemTelemetry(): Promise<any> {
    if (USE_REAL_API) {
      const res = await fetch(`${API_BASE_URL}/health`);
      return await res.json();
    }

    return {
      appName: 'SentinelForge',
      version: '0.1.0',
      activeProvider: 'Deterministic Local Mock (100% Private)',
      vectorIndexCount: 42,
      sandboxTimeLimit: 15,
      workspaceJail: '/data/workspace',
      status: 'healthy',
    };
  },
};
