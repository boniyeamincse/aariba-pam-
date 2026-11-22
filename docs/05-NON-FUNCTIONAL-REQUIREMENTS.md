# Non-functional requirements

> Proposed pilot targets · 2026-11-22

The pilot sponsor and listed owners must approve or revise these targets in Phase 0. Measure against the selected asset count, session load, supported clients, and failure assumptions.

| ID | Measure or threshold | Verification | Owner |
| --- | --- | --- | --- |
| NFR-01 | Block new access and terminate associated sessions within 60 seconds of grant revocation or IdP disablement | Compare source and gateway timestamps across all affected sessions | IAM and PAM engineering |
| NFR-02 | Deny unverifiable new launches. End an active session no later than 60 seconds after its last successful authorization renewal during a partition, or at grant expiry if earlier | Partition gateway from authorization and revocation services | PAM engineering |
| NFR-03 | Pause forwarding immediately when mandatory recording fails. Terminate within 60 seconds of capture loss if capture remains unavailable | Fail recorder and storage separately. Correlate pause, termination, and alarm | Security operations and PAM engineering |
| NFR-04 | Restore service, key access, and audit retrieval within 4 hours RTO with at most 15 minutes RPO for recoverable state | Restore an isolated environment from backup and measure time and missing writes | Platform operations |
| NFR-05 | Define API latency, SSH establishment latency, and concurrent session budget in Phase 0 | Measure p95 latency and saturation at representative load | Platform and PAM engineering |
| NFR-06 | Deny direct routine SSH from user networks and restrict gateway access to its assigned targets | Probe allowed and denied paths with authorized lab assets | Infrastructure |
| NFR-07 | Routine PAM admins cannot overwrite or delete protected evidence. Audit events and recordings retain readable, verifiable content through the approved retention window | Verify role restrictions, integrity, authorized reads, and expiry policy | Security operations |
| NFR-08 | Establish a pilot compatibility matrix and operational alerts before rollout | Test the selected clients and hosts. Exercise gateway, recorder, audit, and signing alerts | Platform operations |

The recovery point objective describes restore capability. It does not authorize deletion of retained evidence or reopening stale grants. Restore procedures must revalidate identity and policy before restoring access.

## Measurement boundaries

- For revocation, measure from the authoritative change to both denial of new launches and the last linked target connection closing. Record IdP propagation, control-plane processing, and gateway closure separately.
- For a partition, measure from the last accepted successful renewal. Grant expiry remains an independent deadline. Record gateway clock drift during tests and use a monotonic timer for local elapsed limits.
- For recording, measure from last verified successful capture. Observe both directions of terminal forwarding. Keep evidence of any incomplete capture.
- For recovery, start timing when the service loss is declared. End timing only after reopening checks and evidence retrieval succeed. Determine loss by comparing the latest recoverable authoritative writes against the exercise reference point.

See [security requirements](13-SECURITY-REQUIREMENTS.md) and [test evidence requirements](16-TESTING-STRATEGY.md).
