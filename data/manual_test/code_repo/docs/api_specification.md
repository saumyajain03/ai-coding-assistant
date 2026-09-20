# SentinelForge Microservice API Specification

## 1. Authentication & Token Management
The authentication service handles JWT minting and cryptographic verification.
Clients submit credentials to `/api/v1/auth/token` with an authorized `client_id`.
Tokens are signed with `HS256` and enforce a maximum TTL of 3600 seconds.

## 2. Ingress Traffic Routing and Rate Limiting
Incoming requests traverse an unprivileged gateway proxy before reaching internal handlers.
- Ingress Port: 8443 (mTLS termination)
- Max requests per second: 1200 req/sec
- Inactive connection timeout: 15000 milliseconds

## 3. Database Persistence Layer
Data persistence utilizes SQLite connection pools with write-ahead logging (WAL) enabled.
Foreign keys are strictly enforced across user sessions and audit transaction ledgers.
