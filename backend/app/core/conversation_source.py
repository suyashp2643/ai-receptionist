"""Single source of truth for classifying a conversation as `test`,
`preview`, or `widget` — used identically by the dashboard's conversation
list/detail views and by every analytics aggregate, so the same
conversation is never counted under two different labels in two different
places.

Definitions:
- `test`: `Conversation.mode == TEST` — created only via the dashboard's
  private test console (app/api/v1/conversations.py). Never reachable by a
  real visitor.
- `preview`: `Conversation.mode == WIDGET` and its `WidgetVisitorSession.
  is_platform_preview` is `True` — the dashboard's own live local preview
  (frontend/public/widget-preview.html), set server-side from the
  request's Origin at session-creation time (see
  app/api/v1/widget_public.py::_is_platform_preview_request). Never a
  client-supplied field, so a real customer's widget embed cannot spoof it
  either way.
- `widget`: `Conversation.mode == WIDGET` and not flagged as a platform
  preview — genuine, real-visitor traffic. This is the only source
  included in "production" analytics by default (see
  app/services/analytics_service.py).

A TEST conversation has no WidgetVisitorSession row at all (the test
console never creates one), so `is_platform_preview` reads as `NULL` for
it after a LEFT JOIN — `source_case_expression` checks `mode` first for
exactly this reason.
"""

import enum
from typing import Any

from sqlalchemy import ColumnElement, case

from app.models.enums import ConversationMode


class ConversationSource(str, enum.Enum):
    TEST = "test"
    PREVIEW = "preview"
    WIDGET = "widget"


def source_case_expression(mode_col: Any, is_platform_preview_col: Any) -> ColumnElement[str]:
    """Builds the SQL CASE expression for use in a SELECT alongside a LEFT
    JOIN from Conversation to WidgetVisitorSession ON conversation_id.
    Typed `Any` for the inputs rather than `ColumnElement` because callers
    pass ORM `InstrumentedAttribute`s (e.g. `Conversation.mode`), which
    mypy does not consider a `ColumnElement` even though they behave as one
    in every SQLAlchemy expression context used here."""
    return case(
        (mode_col == ConversationMode.TEST, ConversationSource.TEST.value),
        (is_platform_preview_col.is_(True), ConversationSource.PREVIEW.value),
        else_=ConversationSource.WIDGET.value,
    )


def classify(mode: ConversationMode, is_platform_preview: bool | None) -> ConversationSource:
    """Python-side equivalent of `source_case_expression`, for classifying
    a single already-loaded Conversation (e.g. in a detail response)."""
    if mode == ConversationMode.TEST:
        return ConversationSource.TEST
    if is_platform_preview:
        return ConversationSource.PREVIEW
    return ConversationSource.WIDGET
