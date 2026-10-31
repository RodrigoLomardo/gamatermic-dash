from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authz.policy import Principal
from app.core.deps import get_session, require_permission
from app.core.rate_limit import hit
from app.modules.ai import schemas as sc
from app.modules.ai import service

router = APIRouter(prefix="/ai", tags=["ai"])
creator = require_permission("dashboard:create", "dataset:query")


@router.get("/status", response_model=sc.AiStatusOut)
async def status(_: Principal = Depends(creator), s: AsyncSession = Depends(get_session)):
    return await service.status(s)


@router.post("/dashboard-proposals", response_model=sc.ProposalsOut)
async def proposals(body: sc.ProposalsIn, request: Request, p: Principal = Depends(creator), s: AsyncSession = Depends(get_session)):
    hit(f"ai:{p.id}", 10, 60)
    return await service.generate(s, request, p, body)
