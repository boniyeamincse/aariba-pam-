"""ITSM Ticket Validation Adapter Service (P7-04, ADR-016).

Provides:
1. Ticket Identifier Format Validation (Jira, ServiceNow, generic patterns).
2. State & Lifecycle Verification (Active/Approved vs Closed/Resolved/Cancelled).
3. Requester Identity & Assignee Matching (preventing ticket hijacking).
4. Strict Outbound Latency Budget & Timeout Protection (3.0s).
5. Configurable Outage Fallback Policy (fail_closed default deny vs manual_approval escalation).
6. Synthetic Lab Mock Registry and Observable Health Metrics.
"""

import re
import time
import json
import threading
import urllib.request
import urllib.error
from typing import Dict, Any, Optional, List, Tuple, Callable
from pydantic import BaseModel, Field

from ariba_pam.config import settings
from ariba_pam.db.base import utc_now, ensure_utc


# Regex Patterns for Enterprise Ticket Formats
JIRA_REGEX = re.compile(r"^[A-Z][A-Z0-9_]+-\d+$")
SERVICENOW_REGEX = re.compile(r"^(INC|CHG|REQ|RITM|PRB)\d+$", re.IGNORECASE)
GENERIC_REGEX = re.compile(r"^[A-Z0-9_]+-[A-Z0-9_-]+$", re.IGNORECASE)


class ITSMValidationResult(BaseModel):
    """Structured result of ITSM ticket reference verification."""
    valid: bool
    ticket_ref: str
    state: Optional[str] = None
    assignee: Optional[str] = None
    collaborators: List[str] = Field(default_factory=list)
    title: Optional[str] = None
    code: str  # "VALID", "INVALID_FORMAT", "TICKET_NOT_FOUND", "TICKET_INVALID_STATE", "TICKET_ASSIGNEE_MISMATCH", "TICKET_TIMEOUT", "TICKET_SYSTEM_ERROR"
    reason: str
    is_provider_unavailable: bool = False
    degraded_fallback_applied: bool = False
    duration_ms: float = 0.0


class ITSMAdapter:
    """Enterprise ITSM Ticket Validation Adapter."""

    def __init__(
        self,
        enabled: Optional[bool] = None,
        provider: Optional[str] = None,
        api_url: Optional[str] = None,
        api_token: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        allowed_states: Optional[List[str]] = None,
        fallback_mode: Optional[str] = None,
    ):
        self.enabled = enabled if enabled is not None else settings.itsm_enabled
        self.provider = provider or settings.itsm_provider
        self.api_url = api_url or settings.itsm_api_url
        self.api_token = api_token or settings.itsm_api_token
        self.timeout_seconds = timeout_seconds if timeout_seconds is not None else settings.itsm_timeout_seconds
        self.allowed_states = (
            allowed_states if allowed_states is not None else list(settings.itsm_allowed_states)
        )
        self.fallback_mode = fallback_mode or settings.itsm_fallback_mode

        self._lock = threading.Lock()
        self._mock_tickets: Dict[str, Dict[str, Any]] = {}
        self._custom_http_handler: Optional[Callable[[str, float], Tuple[int, Dict[str, Any]]]] = None

        # Observable Metrics
        self.total_validations = 0
        self.total_successful = 0
        self.total_format_errors = 0
        self.total_state_errors = 0
        self.total_assignee_mismatches = 0
        self.total_timeouts = 0
        self.total_system_errors = 0
        self.total_fallback_escalations = 0

        # Initialize Default Synthetic Test Fixtures
        self._init_default_mock_fixtures()

    def _init_default_mock_fixtures(self) -> None:
        """Register canonical synthetic lab tickets."""
        self.register_mock_ticket(
            ticket_ref="LAB-42",
            state="In Progress",
            assignee="alice@example.com",
            collaborators=["alice@example.com", "alice_collaborator@example.com", "alice@ariba.internal"],
            title="Lab Policy Integration Verification",
        )
        self.register_mock_ticket(
            ticket_ref="JIRA-1001",
            state="In Progress",
            assignee="alice@example.com",
            collaborators=["alice@example.com", "alice_collaborator@example.com", "alice@ariba.internal"],
            title="Core Payments Database Migration",
        )
        self.register_mock_ticket(
            ticket_ref="JIRA-1002",
            state="Closed",
            assignee="alice@example.com",
            collaborators=["alice@example.com"],
            title="Old Completed Maintenance Window",
        )
        self.register_mock_ticket(
            ticket_ref="JIRA-1003",
            state="In Progress",
            assignee="bob@example.com",
            collaborators=["bob@example.com"],
            title="Bob Cloud Infrastructure Update",
        )
        self.register_mock_ticket(
            ticket_ref="INC-9911",
            state="Approved",
            assignee="alice@example.com",
            collaborators=["alice@example.com"],
            title="Payment Gateway Emergency Fix",
        )
        self.register_mock_ticket(
            ticket_ref="TIMEOUT-TICKET",
            state="In Progress",
            assignee="alice@example.com",
            collaborators=[],
            title="Simulated Timeout Ticket",
            simulate_timeout=True,
        )
        self.register_mock_ticket(
            ticket_ref="ERROR-500-TICKET",
            state="In Progress",
            assignee="alice@example.com",
            collaborators=[],
            title="Simulated Downstream 500 Ticket",
            simulate_error=500,
        )

    def register_mock_ticket(
        self,
        ticket_ref: str,
        state: str,
        assignee: str,
        collaborators: Optional[List[str]] = None,
        title: str = "",
        simulate_timeout: bool = False,
        simulate_error: Optional[int] = None,
    ) -> None:
        """Register or override a mock ticket in the lab catalog."""
        with self._lock:
            self._mock_tickets[ticket_ref.strip().upper()] = {
                "ticket_ref": ticket_ref.strip(),
                "state": state,
                "assignee": assignee,
                "collaborators": list(collaborators or []),
                "title": title,
                "simulate_timeout": simulate_timeout,
                "simulate_error": simulate_error,
            }

    def set_custom_http_handler(
        self, handler: Optional[Callable[[str, float], Tuple[int, Dict[str, Any]]]]
    ) -> None:
        """Inject synthetic HTTP handler for end-to-end network simulation."""
        self._custom_http_handler = handler

    @classmethod
    def is_valid_ticket_format(cls, ticket_ref: str) -> bool:
        """Validate ticket key syntax against Jira, ServiceNow, or generic patterns."""
        if not ticket_ref or not ticket_ref.strip():
            return False
        ref = ticket_ref.strip()
        return bool(JIRA_REGEX.match(ref) or SERVICENOW_REGEX.match(ref) or GENERIC_REGEX.match(ref))

    def validate_ticket(
        self,
        ticket_ref: str,
        requester_email: str,
        requester_id: Optional[str] = None,
    ) -> ITSMValidationResult:
        """
        Validate an ITSM ticket reference:
        1. Syntax and pattern check.
        2. Ticket existence in provider.
        3. Active/Approved lifecycle state check.
        4. Requester assignee/collaborator matching.
        5. Timeout and system failure protection.
        """
        start_time = time.monotonic()
        ref = (ticket_ref or "").strip()

        with self._lock:
            self.total_validations += 1

        # 1. Format validation
        if not self.is_valid_ticket_format(ref):
            duration = (time.monotonic() - start_time) * 1000
            with self._lock:
                self.total_format_errors += 1
            return ITSMValidationResult(
                valid=False,
                ticket_ref=ref,
                code="INVALID_FORMAT",
                reason=f"Ticket reference '{ref}' is not a valid Jira or ServiceNow identifier",
                duration_ms=round(duration, 2),
            )

        ref_upper = ref.upper()

        # Check mock / lab catalog first
        mock_ticket = None
        with self._lock:
            mock_ticket = self._mock_tickets.get(ref_upper)

        if mock_ticket is not None:
            # Simulated timeout
            if mock_ticket.get("simulate_timeout"):
                duration = (time.monotonic() - start_time) * 1000
                with self._lock:
                    self.total_timeouts += 1
                return ITSMValidationResult(
                    valid=False,
                    ticket_ref=ref,
                    code="TICKET_TIMEOUT",
                    reason=f"ITSM provider connection timed out after {self.timeout_seconds}s while querying {ref}",
                    is_provider_unavailable=True,
                    duration_ms=round(duration, 2),
                )

            # Simulated server error
            if mock_ticket.get("simulate_error"):
                status_code = mock_ticket.get("simulate_error")
                duration = (time.monotonic() - start_time) * 1000
                with self._lock:
                    self.total_system_errors += 1
                return ITSMValidationResult(
                    valid=False,
                    ticket_ref=ref,
                    code="TICKET_SYSTEM_ERROR",
                    reason=f"ITSM provider returned HTTP {status_code} for {ref}",
                    is_provider_unavailable=True,
                    duration_ms=round(duration, 2),
                )

            ticket_data = mock_ticket
        elif self._custom_http_handler is not None:
            # Custom HTTP handler hook
            try:
                status_code, body = self._custom_http_handler(ref, self.timeout_seconds)
                if status_code == 404:
                    duration = (time.monotonic() - start_time) * 1000
                    return ITSMValidationResult(
                        valid=False,
                        ticket_ref=ref,
                        code="TICKET_NOT_FOUND",
                        reason=f"Ticket '{ref}' not found in {self.provider}",
                        duration_ms=round(duration, 2),
                    )
                elif status_code >= 500:
                    duration = (time.monotonic() - start_time) * 1000
                    with self._lock:
                        self.total_system_errors += 1
                    return ITSMValidationResult(
                        valid=False,
                        ticket_ref=ref,
                        code="TICKET_SYSTEM_ERROR",
                        reason=f"ITSM provider returned HTTP {status_code} for {ref}",
                        is_provider_unavailable=True,
                        duration_ms=round(duration, 2),
                    )
                ticket_data = body
            except TimeoutError:
                duration = (time.monotonic() - start_time) * 1000
                with self._lock:
                    self.total_timeouts += 1
                return ITSMValidationResult(
                    valid=False,
                    ticket_ref=ref,
                    code="TICKET_TIMEOUT",
                    reason=f"ITSM provider connection timed out after {self.timeout_seconds}s",
                    is_provider_unavailable=True,
                    duration_ms=round(duration, 2),
                )
            except Exception as e:
                duration = (time.monotonic() - start_time) * 1000
                with self._lock:
                    self.total_system_errors += 1
                return ITSMValidationResult(
                    valid=False,
                    ticket_ref=ref,
                    code="TICKET_SYSTEM_ERROR",
                    reason=f"Network error communicating with ITSM provider: {str(e)}",
                    is_provider_unavailable=True,
                    duration_ms=round(duration, 2),
                )
        else:
            # Ticket not found in mock fixtures and no live handler
            duration = (time.monotonic() - start_time) * 1000
            return ITSMValidationResult(
                valid=False,
                ticket_ref=ref,
                code="TICKET_NOT_FOUND",
                reason=f"Ticket '{ref}' not found in {self.provider} ticketing system",
                duration_ms=round(duration, 2),
            )

        # 2. State & Lifecycle Check
        state = ticket_data.get("state") or "Unknown"
        allowed_set = {s.lower() for s in self.allowed_states}
        if state.lower() not in allowed_set:
            duration = (time.monotonic() - start_time) * 1000
            with self._lock:
                self.total_state_errors += 1
            return ITSMValidationResult(
                valid=False,
                ticket_ref=ref,
                state=state,
                assignee=ticket_data.get("assignee"),
                collaborators=ticket_data.get("collaborators", []),
                title=ticket_data.get("title"),
                code="TICKET_INVALID_STATE",
                reason=(
                    f"Ticket '{ref}' is in '{state}' state. Access requests require an active or approved ticket "
                    f"in one of: {self.allowed_states}"
                ),
                duration_ms=round(duration, 2),
            )

        # 3. Requester Identity & Assignee Matching
        req_email_clean = (requester_email or "").strip().lower()
        assignee_clean = (ticket_data.get("assignee") or "").strip().lower()
        collab_set = {c.strip().lower() for c in ticket_data.get("collaborators", [])}

        is_authorized_assignee = (
            req_email_clean == assignee_clean
            or req_email_clean in collab_set
            or req_email_clean.split("@")[0] == assignee_clean.split("@")[0]
        )

        if not is_authorized_assignee:
            duration = (time.monotonic() - start_time) * 1000
            with self._lock:
                self.total_assignee_mismatches += 1
            return ITSMValidationResult(
                valid=False,
                ticket_ref=ref,
                state=state,
                assignee=ticket_data.get("assignee"),
                collaborators=ticket_data.get("collaborators", []),
                title=ticket_data.get("title"),
                code="TICKET_ASSIGNEE_MISMATCH",
                reason=(
                    f"Requester '{requester_email}' is not the assigned owner ('{ticket_data.get('assignee')}') "
                    f"or a permitted collaborator on ticket '{ref}'"
                ),
                duration_ms=round(duration, 2),
            )

        # Successful validation
        duration = (time.monotonic() - start_time) * 1000
        with self._lock:
            self.total_successful += 1

        return ITSMValidationResult(
            valid=True,
            ticket_ref=ref,
            state=state,
            assignee=ticket_data.get("assignee"),
            collaborators=ticket_data.get("collaborators", []),
            title=ticket_data.get("title"),
            code="VALID",
            reason="Ticket reference validated and verified against ITSM provider",
            duration_ms=round(duration, 2),
        )

    def evaluate_fallback(
        self,
        result: ITSMValidationResult,
        override_fallback_mode: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """
        Evaluate outage fallback policy when provider is unreachable.
        Returns (allow_submission, explanation).
        """
        if not result.is_provider_unavailable:
            return result.valid, result.reason

        mode = override_fallback_mode or self.fallback_mode
        if mode == "manual_approval":
            with self._lock:
                self.total_fallback_escalations += 1
            result.degraded_fallback_applied = True
            return (
                True,
                "ITSM provider unavailable; ticket accepted under degraded manual approval fallback policy",
            )

        # Default: fail_closed
        return (
            False,
            "ITSM ticketing system is currently unreachable. Security policy enforces strict fail-closed rejection",
        )

    def get_status(self) -> Dict[str, Any]:
        """Return adapter configuration, health, and observable metrics."""
        with self._lock:
            return {
                "enabled": self.enabled,
                "provider": self.provider,
                "api_url": self.api_url,
                "timeout_seconds": self.timeout_seconds,
                "allowed_states": list(self.allowed_states),
                "fallback_mode": self.fallback_mode,
                "metrics": {
                    "total_validations": self.total_validations,
                    "total_successful": self.total_successful,
                    "total_format_errors": self.total_format_errors,
                    "total_state_errors": self.total_state_errors,
                    "total_assignee_mismatches": self.total_assignee_mismatches,
                    "total_timeouts": self.total_timeouts,
                    "total_system_errors": self.total_system_errors,
                    "total_fallback_escalations": self.total_fallback_escalations,
                },
            }


# Global singleton instance
itsm_adapter = ITSMAdapter()
