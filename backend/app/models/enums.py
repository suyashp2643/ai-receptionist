import enum


class TenantStatus(str, enum.Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"


class TenantMemberRole(str, enum.Enum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"


# Ordered so that ROLE_RANK[role] gives a comparable privilege level —
# used by the centralized permission dependency, never re-derived ad hoc.
ROLE_RANK: dict[TenantMemberRole, int] = {
    TenantMemberRole.MEMBER: 0,
    TenantMemberRole.ADMIN: 1,
    TenantMemberRole.OWNER: 2,
}


class TenantMemberStatus(str, enum.Enum):
    ACTIVE = "active"
    INVITED = "invited"
    SUSPENDED = "suspended"


class OnboardingStatus(str, enum.Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class ReceptionistStatus(str, enum.Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"


class ContentStatus(str, enum.Enum):
    """Shared active/inactive status for FAQ-adjacent and knowledge content."""

    ACTIVE = "active"
    INACTIVE = "inactive"


class KnowledgeSourceType(str, enum.Enum):
    MANUAL = "manual"
    # Not implemented in Phase 3 — reserved so the schema doesn't need to
    # change when crawling/upload ship later. The service layer rejects any
    # attempt to create a source with these types today.
    WEBSITE = "website"
    FILE_UPLOAD = "file_upload"


UNSUPPORTED_KNOWLEDGE_SOURCE_TYPES = frozenset({KnowledgeSourceType.WEBSITE, KnowledgeSourceType.FILE_UPLOAD})


class ConversationMode(str, enum.Enum):
    TEST = "test"
    # Public embeddable-widget conversations (Phase 5) — never chosen by
    # client input; the public widget route always passes this explicitly,
    # the dashboard test-console route always passes TEST.
    WIDGET = "widget"
    # Reserved for a later phase (e.g. true telephone/voice channels) —
    # nothing creates this value yet.
    FUTURE_LIVE = "future_live"


class ConversationChannel(str, enum.Enum):
    DASHBOARD_TEST = "dashboard_test"
    WIDGET = "widget"


class ConversationStatus(str, enum.Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    ABANDONED = "abandoned"
    FAILED = "failed"


class ConversationMessageRole(str, enum.Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


# --- Phase 5: public widget ---


class WidgetInstallationStatus(str, enum.Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    REVOKED = "revoked"


class AppointmentRequestStatus(str, enum.Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    DECLINED = "declined"
    CANCELLED = "cancelled"


class HandoffStatus(str, enum.Enum):
    OPEN = "open"
    CLAIMED = "claimed"
    RESOLVED = "resolved"
    CANCELLED = "cancelled"


class EnquiryStatus(str, enum.Enum):
    """`CLOSED` predates Phase 6's richer pipeline (added in Phase 5) and is
    kept, unmigrated, as a legacy terminal status equivalent to `ARCHIVED`
    for any row written before this phase — Postgres native enums cannot
    drop a value without rebuilding the type and rewriting every row, and
    there is nothing wrong with the data itself, so it is left in place
    rather than force-migrated. New status-transition validation (see
    app/services/enquiry_service.py) never assigns `CLOSED` to a row going
    forward; use `ARCHIVED` instead. See docs/database-schema.md."""

    NEW = "new"
    QUALIFIED = "qualified"
    CONTACTED = "contacted"
    APPOINTMENT_REQUESTED = "appointment_requested"
    IN_PROGRESS = "in_progress"
    WON = "won"
    LOST = "lost"
    ARCHIVED = "archived"
    CLOSED = "closed"


class PreferredContactMethod(str, enum.Enum):
    EMAIL = "email"
    PHONE = "phone"
    EITHER = "either"


# --- Phase 8: integrations ---


class IntegrationConnectorType(str, enum.Enum):
    """No provider-specific type may escape the adapter boundary (see
    app/integrations/connectors/) — this is the one place a connector
    "kind" is named, and every adapter registers under exactly one of
    these via the connector factory."""

    MOCK = "mock"
    WEBHOOK = "webhook"
    REVENUE_BRAIN = "revenue_brain"
    SALES_EMPLOYEE = "sales_employee"


class IntegrationConnectionStatus(str, enum.Enum):
    """Deliberately five distinct, mutually-exclusive states — never a
    boolean "connected" flag — so the dashboard/API can never claim a
    connector is working merely because it was configured. See
    docs/security.md's Phase 8 section for the exact promotion rules.

    CONFIGURED: created, has never passed a verify_connection() call.
    VERIFIED: verify_connection() has succeeded at least once and no
        subsequent delivery has failed enough times to become FAILING.
    PAUSED: an owner/admin explicitly paused delivery — no outbox events
        are claimed for this connection while paused.
    FAILING: was VERIFIED, but recent consecutive delivery attempts have
        failed (see failure_count) — deliveries still enqueue and still
        attempt delivery (this is a health signal, not a delivery gate).
    DISABLED: an owner/admin explicitly, deliberately turned this
        connection off — same delivery-skipping behavior as PAUSED, but
        communicates permanence rather than a temporary pause.
    """

    CONFIGURED = "configured"
    VERIFIED = "verified"
    PAUSED = "paused"
    FAILING = "failing"
    DISABLED = "disabled"


# Statuses in which the worker will still claim and attempt delivery.
INTEGRATION_DELIVERABLE_STATUSES = frozenset(
    {
        IntegrationConnectionStatus.CONFIGURED,
        IntegrationConnectionStatus.VERIFIED,
        IntegrationConnectionStatus.FAILING,
    }
)


class OutboxEventStatus(str, enum.Enum):
    """PENDING -> CLAIMED -> (DELIVERED | PENDING again on retryable
    failure | DEAD_LETTER on exhausted attempts). CLAIMED rows past their
    lease expiry are treated as PENDING again by the claim query itself
    (see app/services/outbox_worker_service.py) rather than a separate
    status transition, so a crashed worker never needs manual recovery."""

    PENDING = "pending"
    CLAIMED = "claimed"
    DELIVERED = "delivered"
    DEAD_LETTER = "dead_letter"


class DeliveryAttemptStatus(str, enum.Enum):
    """Recorded once per attempt, never mutated afterward — the outbox
    event's own status (above) is the mutable "current state"; this is
    permanent attempt history."""

    SUCCESS = "success"
    RETRYABLE_FAILURE = "retryable_failure"
    PERMANENT_FAILURE = "permanent_failure"


class InboundEventStatus(str, enum.Enum):
    PROCESSED = "processed"
    REJECTED = "rejected"
