# Completed

| ID | Completed work | Evidence |
| --- | --- | --- |
| DOC-01 | Established the numbered Ariba PAM documentation baseline and Phase 0 backlog | [Documentation index](../README.md), [decision log](../decisions/architecture-decisions.md), and [changelog](../CHANGELOG.md) |
| DOC-02 | Completed the first implementation documentation pass, including module and integration contracts and planned test evidence | [Documentation index](../README.md), [API contract](../docs/11-API-SPECIFICATION.md), and [test strategy](../docs/16-TESTING-STRATEGY.md) |
| DOC-03 | Broke the roadmap into dependency-ordered development tasks with completion checks | [Development tasks](TODO.md) and [testing strategy](../docs/16-TESTING-STRATEGY.md) |

| P1-01 | Scaffold the control API and its test harness | [tests/test_health.py](../tests/test_health.py) (passing smoke & health verification) |
| P1-02 | Bring up the isolated PostgreSQL lab and migration runner | [alembic/versions/0001_initial_schema.py](../alembic/versions/0001_initial_schema.py), [tests/test_migrations.py](../tests/test_migrations.py) |
| P1-03 | Implement workforce sign-in, sessions, and GET /api/v1/me | [src/ariba_pam/services/auth.py](../src/ariba_pam/services/auth.py), [tests/test_auth.py](../tests/test_auth.py) |
| P1-04 | Implement resource-scoped permissions | [src/ariba_pam/core/scoping.py](../src/ariba_pam/core/scoping.py), [tests/test_scoping.py](../tests/test_scoping.py) |
| P1-05 | Implement transactional audit outbox and durable local delivery test | [src/ariba_pam/services/audit.py](../src/ariba_pam/services/audit.py), [tests/test_audit_outbox.py](../tests/test_audit_outbox.py) |
| P1-06 | Add scoped asset and target-account inventory reads | [src/ariba_pam/api/v1/assets.py](../src/ariba_pam/api/v1/assets.py), [tests/test_inventory.py](../tests/test_inventory.py) |
| P1-07 | Add independently reviewed inventory and role changes | [src/ariba_pam/api/v1/admin.py](../src/ariba_pam/api/v1/admin.py), [tests/test_admin_changes.py](../tests/test_admin_changes.py) |
| P1-08 | Build the lab portal sign-in and scoped asset catalog | [API checks](../tests/test_portal.py), [Chromium checks](../tests/test_portal_browser.py), [test record](../docs/16-TESTING-STRATEGY.md#lab-implementation-results) |
| P1-09 | Verify the core platform milestone | [tests/test_workflow.py](../tests/test_workflow.py) (full end-to-end access request, approval, grant issuance, launch, and gateway lifecycle) |
| P2-01 | Publish independently reviewed asset policies and enforce them during request, approval, and new session authorization | [Policy tests](../tests/test_policies.py), [API contract](../docs/11-API-SPECIFICATION.md#reviewed-asset-policy), [test record](../docs/16-TESTING-STRATEGY.md#lab-implementation-results) |

Phase 0 approvals, implementation, and pilot test results are tracked when evidence becomes available.
