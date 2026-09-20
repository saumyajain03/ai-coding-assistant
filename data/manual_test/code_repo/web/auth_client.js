/**
 * SentinelForge Web Authentication Client
 * Manages OAuth2 tokens, refresh flows, and HTTP request authorization.
 */

class AuthClient {
    constructor(baseURL, clientId) {
        this.baseURL = baseURL;
        this.clientId = clientId;
        this.accessToken = null;
        this.refreshToken = null;
    }

    async loginWithCredentials(username, password) {
        const response = await fetch(`${this.baseURL}/api/v1/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password, client_id: this.clientId })
        });
        if (!response.ok) {
            throw new Error(`Authentication failed with HTTP ${response.status}`);
        }
        const data = await response.json();
        this.accessToken = data.access_token;
        this.refreshToken = data.refresh_token;
        return data;
    }

    getAuthorizationHeader() {
        if (!this.accessToken) {
            throw new Error("No active access token available.");
        }
        return `Bearer ${this.accessToken}`;
    }

    clearSession() {
        this.accessToken = null;
        this.refreshToken = null;
    }
}

export function createAuthClient(config) {
    return new AuthClient(config.baseURL, config.clientId);
}
