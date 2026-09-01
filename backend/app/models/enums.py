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
