import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import TenantContext, get_db, get_tenant_context, require_tenant_role
from app.models.enums import TenantMemberRole
from app.models.knowledge import KnowledgeDocument, KnowledgeSource
from app.repositories.knowledge import (
    KnowledgeChunkRepository,
    KnowledgeDocumentRepository,
    KnowledgeSourceRepository,
)
from app.schemas.knowledge import (
    KnowledgeDocumentCreate,
    KnowledgeDocumentRead,
    KnowledgeDocumentUpdate,
    KnowledgeSearchRequest,
    KnowledgeSearchResponse,
    KnowledgeSearchResultItem,
    KnowledgeSourceCreate,
    KnowledgeSourceRead,
)
from app.services import knowledge_service

router = APIRouter()


def _get_source_or_404(source_id: uuid.UUID, ctx: TenantContext, db: Session) -> KnowledgeSource:
    source = KnowledgeSourceRepository(db, ctx.tenant_id).get(source_id)
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge source not found")
    return source


def _get_document_or_404(document_id: uuid.UUID, ctx: TenantContext, db: Session) -> KnowledgeDocument:
    document = KnowledgeDocumentRepository(db, ctx.tenant_id).get(document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge document not found")
    return document


@router.get("/tenants/{tenant_id}/knowledge/sources", response_model=list[KnowledgeSourceRead])
def list_sources(
    ctx: TenantContext = Depends(get_tenant_context), db: Session = Depends(get_db)
) -> list[KnowledgeSourceRead]:
    sources = KnowledgeSourceRepository(db, ctx.tenant_id).list()
    return [KnowledgeSourceRead.model_validate(s) for s in sources]


@router.post(
    "/tenants/{tenant_id}/knowledge/sources",
    response_model=KnowledgeSourceRead,
    status_code=status.HTTP_201_CREATED,
)
def create_source(
    payload: KnowledgeSourceCreate,
    ctx: TenantContext = Depends(require_tenant_role(TenantMemberRole.ADMIN)),
    db: Session = Depends(get_db),
) -> KnowledgeSourceRead:
    try:
        source = knowledge_service.create_source(db, tenant_id=ctx.tenant_id, type_=payload.type, title=payload.title)
    except knowledge_service.UnsupportedKnowledgeSourceTypeError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return KnowledgeSourceRead.model_validate(source)


@router.get("/tenants/{tenant_id}/knowledge/documents", response_model=list[KnowledgeDocumentRead])
def list_documents(
    ctx: TenantContext = Depends(get_tenant_context), db: Session = Depends(get_db)
) -> list[KnowledgeDocumentRead]:
    documents = KnowledgeDocumentRepository(db, ctx.tenant_id).list()
    return [KnowledgeDocumentRead.model_validate(d) for d in documents]


@router.post(
    "/tenants/{tenant_id}/knowledge/documents",
    response_model=KnowledgeDocumentRead,
    status_code=status.HTTP_201_CREATED,
)
def create_document(
    payload: KnowledgeDocumentCreate,
    ctx: TenantContext = Depends(require_tenant_role(TenantMemberRole.ADMIN)),
    db: Session = Depends(get_db),
) -> KnowledgeDocumentRead:
    source = _get_source_or_404(payload.source_id, ctx, db)
    document, _chunks = knowledge_service.create_document(
        db, tenant_id=ctx.tenant_id, source=source, title=payload.title, raw_text=payload.raw_text
    )
    return KnowledgeDocumentRead.model_validate(document)


@router.get("/tenants/{tenant_id}/knowledge/documents/{document_id}", response_model=KnowledgeDocumentRead)
def get_document(
    document_id: uuid.UUID,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> KnowledgeDocumentRead:
    document = _get_document_or_404(document_id, ctx, db)
    return KnowledgeDocumentRead.model_validate(document)


@router.patch("/tenants/{tenant_id}/knowledge/documents/{document_id}", response_model=KnowledgeDocumentRead)
def update_document(
    document_id: uuid.UUID,
    payload: KnowledgeDocumentUpdate,
    ctx: TenantContext = Depends(require_tenant_role(TenantMemberRole.ADMIN)),
    db: Session = Depends(get_db),
) -> KnowledgeDocumentRead:
    document = _get_document_or_404(document_id, ctx, db)
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(document, field, value)
    return KnowledgeDocumentRead.model_validate(document)


@router.delete("/tenants/{tenant_id}/knowledge/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: uuid.UUID,
    ctx: TenantContext = Depends(require_tenant_role(TenantMemberRole.ADMIN)),
    db: Session = Depends(get_db),
) -> None:
    document = _get_document_or_404(document_id, ctx, db)
    knowledge_service.delete_document(db, tenant_id=ctx.tenant_id, document=document)


@router.post("/tenants/{tenant_id}/knowledge/search", response_model=KnowledgeSearchResponse)
def search_knowledge(
    payload: KnowledgeSearchRequest,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> KnowledgeSearchResponse:
    chunk_repo = KnowledgeChunkRepository(db, ctx.tenant_id)
    document_repo = KnowledgeDocumentRepository(db, ctx.tenant_id)
    results = chunk_repo.search(payload.query)

    items = []
    for chunk, score in results:
        document = document_repo.get(chunk.document_id)
        if document is None:
            continue
        items.append(
            KnowledgeSearchResultItem(
                document_id=document.id,
                document_title=document.title,
                chunk_id=chunk.id,
                chunk_index=chunk.chunk_index,
                content=chunk.content,
                score=score,
            )
        )
    return KnowledgeSearchResponse(query=payload.query, results=items)
