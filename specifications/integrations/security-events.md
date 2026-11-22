# Security event integrations

> Proposed outbound contract · 2026-11-22

The pilot needs an available SOC alert path and independent evidence. Dedicated Wazuh and Ariba SOC adapters follow the [roadmap](../../docs/17-DEVELOPMENT-ROADMAP.md). Each adapter authenticates to the approved receiver and forwards scoped, sanitized operational metadata.

| Event family | Examples | Delivery purpose |
| --- | --- | --- |
| Identity and authorization | MFA failure, denied access, grant revocation | Trace security decisions |
| Session and evidence | Session start or end, recording interruption, evidence integrity failure | Investigate activity and coverage gaps |
| Administration and custody | Policy publication, host trust changes, emergency activation, retention changes | Review sensitive actions and detect abuse |
| Operational health | Repeated delivery failures, buffer capacity warning, gateway renewal degradation | Alert owners before evidence delivery or access degrades |

Use a stable event ID, schema version, occurrence time, source, asset scope, severity, outcome, and relevant correlation IDs. Do not forward raw recordings, access secrets, justification text, or private credentials. Define recipient allowlists, event filtering, retention, and alert ownership during integration onboarding.

Deliver at least once with bounded retries and observable backlog. Use source event IDs for deduplication. Route repeated failures for operator review. An unavailable destination must not authorize a session or change the independent evidence record. For the pilot, exercise the available alert path with a mandatory recording failure and break-glass drill.

See [audit custody](../modules/audit-and-recovery.md), [security requirements](../../docs/13-SECURITY-REQUIREMENTS.md), and [test evidence](../../docs/16-TESTING-STRATEGY.md).
