/**
 * SentinelForge Session & Telemetry Type Definitions
 */

export enum SessionState {
    IDLE = "IDLE",
    ACTIVE = "ACTIVE",
    SUSPENDED = "SUSPENDED",
    TERMINATED = "TERMINATED"
}

export interface UserSessionPayload {
    sessionId: string;
    userId: string;
    permissions: string[];
    createdAt: number;
    expiresAt: number;
}

export interface SessionValidatorConfig {
    maxDurationSeconds: number;
    clockSkewToleranceMs: number;
    requireMfaToken: boolean;
}

export class SessionRegistry<T extends UserSessionPayload> {
    private sessions: Map<string, T> = new Map();

    public registerSession(session: T): void {
        this.sessions.set(session.sessionId, session);
    }

    public getSession(sessionId: string): T | undefined {
        return this.sessions.get(sessionId);
    }

    public isSessionExpired(sessionId: string, currentTime: number): boolean {
        const sess = this.sessions.get(sessionId);
        if (!sess) return true;
        return currentTime > sess.expiresAt;
    }
}
