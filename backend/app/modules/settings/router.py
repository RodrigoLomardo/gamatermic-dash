from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authz.policy import Principal
from app.core.deps import get_session, require_permission
from app.core.rate_limit import hit
from app.modules.settings import schemas as sc
from app.modules.settings import service

router = APIRouter(prefix="/settings", tags=["settings"])
manage = require_permission("settings:manage")


@router.get("/ai", response_model=sc.AiSettingsOut)
async def get_ai(_: Principal = Depends(manage), s: AsyncSession = Depends(get_session)):
    return await service.get_ai(s)


@router.put("/ai", response_model=sc.AiSettingsOut)
async def put_ai(body: sc.AiSettingsIn, request: Request, p: Principal = Depends(manage), s: AsyncSession = Depends(get_session)):
    return await service.update_ai(s, request, p, body)


@router.post("/ai/test", response_model=sc.AiTestOut)
async def test_ai(request: Request, p: Principal = Depends(manage), s: AsyncSession = Depends(get_session)):
    hit(f"ai-test:{p.id}", 5, 60)
    return await service.test_ai(s, request, p)
