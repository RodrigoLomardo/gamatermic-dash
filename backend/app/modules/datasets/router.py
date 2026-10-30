import uuid

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authz.policy import Principal
from app.core.deps import get_session, require_permission
from app.modules.datasets import schemas as sc
from app.modules.datasets import service

router = APIRouter(prefix="/datasets", tags=["datasets"])
view = require_permission("dataset:view")
manage = require_permission("dataset:manage")


@router.get("", response_model=list[sc.DatasetOut])
async def list_(p: Principal = Depends(view), s: AsyncSession = Depends(get_session)):
    return await service.list_datasets(s, p)


@router.post("", response_model=sc.DatasetOut, status_code=201)
async def create(body: sc.DatasetIn, request: Request, p: Principal = Depends(manage), s: AsyncSession = Depends(get_session)):
    return await service.create(s, request, p, body)


@router.get("/{did}", response_model=sc.DatasetOut)
async def get(did: uuid.UUID, p: Principal = Depends(view), s: AsyncSession = Depends(get_session)):
    return await service.get_out(s, p, did)


@router.patch("/{did}", response_model=sc.DatasetOut)
async def patch(did: uuid.UUID, body: sc.DatasetPatch, request: Request, p: Principal = Depends(manage), s: AsyncSession = Depends(get_session)):
    return await service.patch(s, request, p, did, body)


@router.put("/{did}/fields", response_model=sc.DatasetOut)
async def put_fields(did: uuid.UUID, body: list[sc.FieldIn], request: Request, p: Principal = Depends(manage), s: AsyncSession = Depends(get_session)):
    return await service.put_fields(s, request, p, did, body)


@router.delete("/{did}", status_code=204)
async def delete(did: uuid.UUID, request: Request, p: Principal = Depends(manage), s: AsyncSession = Depends(get_session)):
    await service.delete_dataset(s, request, p, did)
    return Response(status_code=204)


@router.get("/{did}/preview", response_model=sc.PreviewOut)
async def preview(did: uuid.UUID, limit: int = Query(50, le=200), p: Principal = Depends(view), s: AsyncSession = Depends(get_session)):
    return await service.preview(s, p, did, limit)
