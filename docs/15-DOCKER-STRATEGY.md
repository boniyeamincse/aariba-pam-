# Docker strategy

> Proposed packaging and deployment approach · 2026-11-22

| Environment | Approach |
| --- | --- |
| Local development | Compose for portal, API, database, and optional worker. Use synthetic fixtures and explicit lab-only credentials |
| Integration lab and CI | Start disposable dependencies and synthetic SSH targets. Separate ingress, application, and target networks. Destroy lab state after collecting sanitized evidence |
| Production pilot | Promote reviewed immutable images to the approved runtime. Validate gateway network boundaries, secret injection, independent evidence storage, and restore before enabling target access |

## Image and runtime controls

- Build multi-stage images with pinned bases, minimal runtime dependencies, and non-root users. Document any required runtime capability and restrict it to the affected service.
- Keep secrets out of image layers, build arguments, and versioned Compose files. Use service-scoped file mounts for lab secrets and the approved secret provider for production.
- Publish only approved ingress endpoints. Keep database, background jobs, and signing endpoints on restricted networks. Keep gateway target access restricted by zone.
- Add health, readiness, and graceful shutdown checks. Drain the gateway or end sessions according to the session policy before replacing it.
- Run migrations as a controlled deployment step. Test upgrade with existing records. Use a compatible prior image or the approved restore path if deployment fails.
- Preserve backups and protected evidence outside disposable containers. Exercise restore as part of pilot verification.

When runtime manifests are introduced, verify Compose configuration, startup, unpublished internal ports, synthetic end-to-end access, and shutdown. See [Docker Compose secrets](https://docs.docker.com/compose/how-tos/use-secrets/) and [architecture](09-SYSTEM-ARCHITECTURE.md).

## Deployment and rollback sequence

1. Confirm environment isolation, approved artifact identity, secret provider, backup freshness, gateway target allowlist, and time synchronization.
2. Apply and validate migrations under a deployment identity. Start the control plane and workers, verify authorization and evidence dependencies, then register gateways while target access remains closed.
3. Run synthetic checks for identity, scoped access, recording, evidence retrieval, and revocation. Open the approved asset cohort only after the pilot release decision.
4. On failure, stop new launches and drain or terminate existing sessions under the session policy. Roll back to a schema-compatible image or restore through the tested path. Reconcile grants and sessions before reopening.
