"""Internal notes CRUD. Never reachable by the public widget and never fed
to the AI orchestrator — see InternalNote's docstring. Any active tenant
member may create a note or view notes on anything they can already view;
editing is author-only, deleting is author-or-admin/owner (see
notes_service.py)."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import TenantContext, get_db, get_tenant_context
from app.models.enums import TenantMemberRole
from app.repositories.internal_note import InternalNoteRepository
from app.schemas.notes import NoteCreateRequest, NoteRead, NoteUpdateRequest
from app.services import notes_service
from app.services.notes_service import (
    NoteBodyInvalidError,
    NoteNotFoundError,
    NotNoteAuthorError,
    UnknownNoteEntityError,
)

router = APIRouter()


@router.get("/tenants/{tenant_id}/notes", response_model=list[NoteRead])
def list_notes(
    entity_type: str,
    entity_id: uuid.UUID,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> list[NoteRead]:
    if entity_type not in {"conversation", "contact", "enquiry", "appointment_request", "human_handoff"}:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unknown entity_type.")
    notes = InternalNoteRepository(db, ctx.tenant_id).list_for_entity(entity_type, entity_id)
    return [NoteRead.model_validate(n) for n in notes]


@router.post("/tenants/{tenant_id}/notes", response_model=NoteRead, status_code=status.HTTP_201_CREATED)
def create_note(
    payload: NoteCreateRequest,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> NoteRead:
    try:
        note = notes_service.create_note(
            db,
            tenant_id=ctx.tenant_id,
            author_user_id=ctx.user_id,
            entity_type=payload.entity_type,
            entity_id=payload.entity_id,
            body=payload.body,
        )
    except UnknownNoteEntityError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except NoteBodyInvalidError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    db.commit()
    return NoteRead.model_validate(note)


@router.patch("/tenants/{tenant_id}/notes/{note_id}", response_model=NoteRead)
def update_note(
    note_id: uuid.UUID,
    payload: NoteUpdateRequest,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> NoteRead:
    try:
        note = notes_service.update_note(
            db, tenant_id=ctx.tenant_id, actor_user_id=ctx.user_id, note_id=note_id, body=payload.body
        )
    except NoteNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except NotNoteAuthorError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except NoteBodyInvalidError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    db.commit()
    return NoteRead.model_validate(note)


@router.delete("/tenants/{tenant_id}/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_note(
    note_id: uuid.UUID,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> None:
    try:
        notes_service.delete_note(
            db,
            tenant_id=ctx.tenant_id,
            actor_user_id=ctx.user_id,
            note_id=note_id,
            is_admin_or_owner=ctx.role in (TenantMemberRole.ADMIN, TenantMemberRole.OWNER),
        )
    except NoteNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except NotNoteAuthorError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    db.commit()
