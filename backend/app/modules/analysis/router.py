import uuid

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authz.policy import Principal
from app.core.deps import get_session, require_permission
from app.core.rate_limit import hit
from app.modules.analysis import chat, service
from app.modules.analysis import schemas as sc

router = APIRouter(prefix="/dashboards/{did}/analysis", tags=["analysis"])
view = require_permission("dashboard:view")
export_p = require_permission("dashboard:view", "analysis:export")


@router.get("/fields", response_model=sc.AnalysisFieldsOut)
async def fields(did: uuid.UUID, p: Principal = Depends(view), s: AsyncSession = Depends(get_session)):
    return await service.fields(s, p, did)


@router.get("/values", response_model=sc.AnalysisValuesOut)
async def values(did: uuid.UUID, dataset_id: uuid.UUID, field: str = Query(pattern=r"^[a-z][a-z0-9_]{0,60}$"), q: str | None = Query(None, max_length=80),
                 limit: int = Query(50, ge=1, le=50), p: Principal = Depends(view), s: AsyncSession = Depends(get_session)):
    return await service.values(s, p, did, dataset_id, field, q, limit)


@router.get("/search", response_model=sc.AnalysisSearchOut)
async def search(did: uuid.UUID, q: str = Query(max_length=80), p: Principal = Depends(view), s: AsyncSession = Depends(get_session)):
    hit(f"analysis-search:{p.id}", 60, 60)
    return await service.search(s, p, did, q)


@router.post("/query")
async def query(did: uuid.UUID, body: sc.AnalysisQueryIn, p: Principal = Depends(view), s: AsyncSession = Depends(get_session)):
    return await service.query(s, p, did, body)


@router.post("/records", response_model=sc.AnalysisRecordsOut)
async def records(did: uuid.UUID, body: sc.AnalysisRecordsIn, p: Principal = Depends(view), s: AsyncSession = Depends(get_session)):
    return await service.records(s, p, did, body)


@router.post("/export")
async def export(did: uuid.UUID, body: sc.AnalysisExportIn, request: Request, p: Principal = Depends(export_p), s: AsyncSession = Depends(get_session)):
    hit(f"analysis-export:{p.id}", 10, 60)
    return await service.export_csv(s, request, p, did, body)


@router.get("/views", response_model=list[sc.AnalysisViewOut])
async def list_views(did: uuid.UUID, p: Principal = Depends(view), s: AsyncSession = Depends(get_session)):
    return await service.list_views(s, p, did)


@router.post("/views", response_model=sc.AnalysisViewOut, status_code=201)
async def create_view(did: uuid.UUID, body: sc.AnalysisViewIn, request: Request, p: Principal = Depends(view), s: AsyncSession = Depends(get_session)):
    return await service.create_view(s, request, p, did, body)


@router.delete("/views/{vid}", status_code=204)
async def delete_view(did: uuid.UUID, vid: uuid.UUID, request: Request, p: Principal = Depends(view), s: AsyncSession = Depends(get_session)):
    await service.delete_view(s, request, p, did, vid)
    return Response(status_code=204)


@router.get("/chat/status", response_model=sc.AnalysisChatStatus)
async def chat_status(did: uuid.UUID, p: Principal = Depends(view), s: AsyncSession = Depends(get_session)):
    await service._dashboard(s, p, did)
    return await chat.status(s)


@router.post("/chat", response_model=sc.AnalysisChatOut)
async def chat_ask(did: uuid.UUID, body: sc.AnalysisChatIn, request: Request, p: Principal = Depends(view), s: AsyncSession = Depends(get_session)):
    hit(f"analysis-chat:{p.id}", 12, 60)
    return await chat.ask(s, request, p, did, body)
