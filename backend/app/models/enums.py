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
    # Reserved for Phase 5+ (public/live widget conversations). The service
    # layer never creates anything but TEST in Phase 4 — there is no request
    # field that lets a client choose this value.
    FUTURE_LIVE = "future_live"


class ConversationChannel(str, enum.Enum):
    DASHBOARD_TEST = "dashboard_test"


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
