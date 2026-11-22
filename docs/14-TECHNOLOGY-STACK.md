# Technology stack

> Candidate choices for the SSH pilot · 2026-11-22

| Layer | Candidate | Selection criteria |
| --- | --- | --- |
| Portal | Next.js with TypeScript and Tailwind CSS | Team support, accessible components, session handling, and maintainable builds |
| Control plane | Python with FastAPI | Validation, generated API contract, clear policy enforcement, and operability |
| SSH gateway | Go with a maintained SSH library | Host verification, constrained channel handling, timeouts, cancellation, and supported client and server combinations |
| Enterprise identity | One organization-approved IdP. OIDC is the proposed federation protocol | MFA assurance signal, account-disable propagation, issuer and subject stability, and integration tests |
| Transactional store | PostgreSQL | Transactions for approvals and launches, backup reliability, and migration support |
| Background jobs | Redis and a compatible worker when needed | Retry, backpressure, and idempotency. PostgreSQL remains authoritative for security decisions |
| Keys and recordings | Isolated SSH signer or approved vault, managed key custody, encrypted object storage | Scoped signing, rotation, audited access, protected retention, and independent recovery |
| Packaging and telemetry | Docker images, Compose for lab use, structured logs and metrics | Reproducible builds, isolation, and operational visibility |
| Security integrations | Wazuh and Ariba SOC adapters | Authenticated transport, documented event contract, retries, and monitored delivery |

Validate candidate licenses, supported versions, security maintenance, and compatibility before pinning dependencies. Prototype host key validation, lease expiry, required recording, and signer integration before selecting the gateway dependencies. Confirm the production deployment model in the decision log.

See [architecture decisions](../decisions/architecture-decisions.md) and [OpenID Connect Core](https://openid.net/specs/openid-connect-core-1_0.html).
