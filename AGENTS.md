# Ariba PAM repository instructions

## Working with the baseline

- Use Ariba PAM as the product name. Follow the [README index](README.md) and preserve stable requirement, test, and decision IDs.
- Treat the numbered documents as the design baseline. Use [the decision log](decisions/architecture-decisions.md) to record changes with rationale, status, and evidence.
- Update related requirements, design, tests, and tasks together when behavior changes. Keep proposals, verified results, and approved decisions clearly labeled.
- Use the task lists as a single workflow. Move each item to its current list and link the evidence when it is complete.

## Implementing privileged access

- Enforce resource-scoped authorization server-side. Preserve default deny, separation of duties, and traceability from request to session.
- Test rejected paths, retries, concurrency, and dependency failures when touching approvals, grants, session launch, revocation, or evidence handling.
- Use synthetic identities, targets, credentials, and recordings in the lab. Keep secrets and production evidence out of source control.
- Use maintained protocol and cryptography libraries. Follow the [security requirements](docs/13-SECURITY-REQUIREMENTS.md) and [testing strategy](docs/16-TESTING-STRATEGY.md) for implementation changes.
