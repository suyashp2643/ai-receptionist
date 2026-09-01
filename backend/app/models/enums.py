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
