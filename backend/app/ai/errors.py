"""Domain errors for conversation orchestration — plain ValueError
subclasses carrying structured attributes where useful, matching the
house style established by onboarding_service.py and receptionist_service.py.
Routes catch these specific types and translate them to safe HTTP errors,
never leaking the raw message text of an unexpected exception."""


class ConversationError(ValueError):
    code = "conversation_error"


class ConversationNotFoundError(ConversationError):
    code = "conversation_not_found"


class ConversationNotActiveError(ConversationError):
    code = "conversation_not_active"


class ReceptionistWorkflowMissingError(ConversationError):
    code = "receptionist_workflow_missing"


class MessageTooLongError(ConversationError):
    code = "message_too_long"
