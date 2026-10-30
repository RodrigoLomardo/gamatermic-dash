import uuid

from fastapi import APIRouter, Depends, File, Form, Header, Query, Request, Response, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authz.policy import Principal
from app.core.csvsafe import to_csv
from app.core.deps import get_session, require_permission
from app.core.rate_limit import hit
from app.modules.ingestion import schemas as sc
from app.modules.ingestion import service

router = APIRouter(tags=["ingestion"])
upload_perm = require_permission("ingestion:upload")
view_perm = require_permission("ingestion:view")


@router.post("/datasets/infer-schema", response_model=sc.InferOut)
async def infer(file: UploadFile = File(...), sheet: str | None = Form(None),
                _: Principal = Depends(require_permission("dataset:manage"))):
    return await service.infer_schema(file, sheet)


@router.post("/datasets/{did}/uploads", response_model=sc.RunOut, status_code=202)
async def upload(did: uuid.UUID, request: Request, response: Response, file: UploadFile = File(...),
                 force: bool = Query(False), sheet: str | None = Query(None),
                 idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
                 p: Principal = Depends(upload_perm), s: AsyncSession = Depends(get_session)):
    hit(f"upload:{p.id}", 10, 60)
    out = await service.accept_upload(s, request, p, did, file, idempotency_key, force, sheet)
    if out.duplicate:
        response.status_code = 200
    return out


@router.get("/ingestion/runs", response_model=list[sc.RunOut])
async def runs(dataset_id: uuid.UUID | None = None, status: str | None = None, limit: int = Query(50, le=200), offset: int = 0,
               p: Principal = Depends(view_perm), s: AsyncSession = Depends(get_session)):
    return await service.list_runs(s, p, dataset_id, status, limit, offset)


@router.get("/ingestion/runs/{rid}", response_model=sc.RunOut)
async def run(rid: uuid.UUID, p: Principal = Depends(view_perm), s: AsyncSession = Depends(get_session)):
    return await service.get_run(s, p, rid)


@router.get("/ingestion/runs/{rid}/errors", response_model=list[sc.RowErrorOut])
async def errors(rid: uuid.UUID, limit: int = Query(100, le=1000), offset: int = 0,
                 p: Principal = Depends(view_perm), s: AsyncSession = Depends(get_session)):
    return await service.run_errors(s, p, rid, limit, offset)


@router.get("/ingestion/runs/{rid}/errors.csv")
async def errors_csv(rid: uuid.UUID, p: Principal = Depends(view_perm), s: AsyncSession = Depends(get_session)):
    rows = await service.run_errors(s, p, rid, 5000, 0)
    body = to_csv(["linha", "coluna", "codigo", "mensagem", "trecho"],
                  [[r.row_number, r.column_name, r.error_code, r.message, r.raw_excerpt] for r in rows])
    return Response(body, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="erros-{rid}.csv"'})


@router.post("/ingestion/runs/{rid}/cancel", response_model=sc.RunOut)
async def cancel(rid: uuid.UUID, request: Request, p: Principal = Depends(upload_perm), s: AsyncSession = Depends(get_session)):
    return await service.cancel_run(s, request, p, rid)


@router.post("/ingestion/runs/{rid}/retry", response_model=sc.RunOut, status_code=202)
async def retry(rid: uuid.UUID, request: Request, p: Principal = Depends(upload_perm), s: AsyncSession = Depends(get_session)):
    return await service.retry_run(s, request, p, rid)

