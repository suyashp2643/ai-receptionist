"""Import every model module here so Base.metadata sees all tables for Alembic."""

from app.models.activity_event import ActivityEvent
from app.models.appointment_request import AppointmentRequest
from app.models.business_location import BusinessLocation
from app.models.business_profile import BusinessProfile
from app.models.contact import Contact
from app.models.conversation import Conversation
from app.models.conversation_message import ConversationMessage
from app.models.conversation_summary import ConversationSummary
from app.models.enquiry import Enquiry
from app.models.faq import FAQ
from app.models.human_handoff import HumanHandoff
from app.models.industry_template import IndustryTemplate
from app.models.internal_note import InternalNote
from app.models.knowledge import KnowledgeChunk, KnowledgeDocument, KnowledgeSource
from app.models.public_lead import PublicLead
from app.models.receptionist import Receptionist
from app.models.receptionist_workflow import ReceptionistWorkflow
from app.models.refresh_token import RefreshToken
from app.models.service import Service
from app.models.tenant import Tenant
from app.models.tenant_member import TenantMember
from app.models.user import User
from app.models.widget_installation import WidgetInstallation
from app.models.widget_visitor_session import WidgetVisitorSession

__all__ = [
    "User",
    "Tenant",
    "TenantMember",
    "RefreshToken",
    "IndustryTemplate",
    "BusinessProfile",
    "Receptionist",
    "ReceptionistWorkflow",
    "BusinessLocation",
    "Service",
    "FAQ",
    "KnowledgeSource",
    "KnowledgeDocument",
    "KnowledgeChunk",
    "Conversation",
    "ConversationMessage",
    "ConversationSummary",
    "WidgetInstallation",
    "WidgetVisitorSession",
    "Contact",
    "Enquiry",
    "AppointmentRequest",
    "HumanHandoff",
    "InternalNote",
    "ActivityEvent",
    "PublicLead",
]
