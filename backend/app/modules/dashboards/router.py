import uuid

from fastapi import APIRouter, Depends, Header, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authz.policy import Principal
from app.core.deps import get_session, require_permission, require_user
from app.modules.dashboards import schemas as sc
from app.modules.dashboards import service
from app.modules.dashboards.widget_types import catalog

router = APIRouter(tags=["dashboards"])
view = require_permission("dashboard:view")
create_p = require_permission("dashboard:create")
edit = require_permission("dashboard:edit")
delete_p = require_permission("dashboard:delete")


def _v(if_match: str | None) -> int | None:
    if if_match is None:
        return None
    try:
        return int(if_match.strip('"'))
    except ValueError:
        return None


@router.get("/widget-types")
async def widget_types(_: Principal = Depends(require_user)):
    return catalog()


@router.post("/query/preview")
async def query_preview(body: sc.PreviewRequest, p: Principal = Depends(require_permission("dataset:query")), s: AsyncSession = Depends(get_session)):
    return await service.preview_query(s, p, body)


@router.get("/dashboards", response_model=list[sc.DashboardSummary])
async def list_(p: Principal = Depends(view), s: AsyncSession = Depends(get_session)):
    return await service.list_dashboards(s, p)


@router.post("/dashboards", response_model=sc.DashboardOut, status_code=201)
async def create(body: sc.DashboardIn, request: Request, p: Principal = Depends(create_p), s: AsyncSession = Depends(get_session)):
    return await service.create(s, request, p, body)


@router.get("/dashboards/{did}", response_model=sc.DashboardOut)
async def get(did: uuid.UUID, response: Response, p: Principal = Depends(view), s: AsyncSession = Depends(get_session)):
    out = await service.get(s, p, did)
    response.headers["ETag"] = f'"{out.version}"'
    return out


@router.patch("/dashboards/{did}", response_model=sc.DashboardOut)
async def patch(did: uuid.UUID, body: sc.DashboardPatch, request: Request, if_match: str | None = Header(None),
                p: Principal = Depends(edit), s: AsyncSession = Depends(get_session)):
    return await service.patch(s, request, p, did, body, _v(if_match))


@router.delete("/dashboards/{did}", status_code=204)
async def delete(did: uuid.UUID, request: Request, p: Principal = Depends(delete_p), s: AsyncSession = Depends(get_session)):
    await service.delete(s, request, p, did)
    return Response(status_code=204)


@router.post("/dashboards/{did}/duplicate", response_model=sc.DashboardOut, status_code=201)
async def duplicate(did: uuid.UUID, request: Request, p: Principal = Depends(create_p), s: AsyncSession = Depends(get_session)):
    return await service.duplicate(s, request, p, did)


@router.put("/dashboards/{did}/layout", response_model=sc.DashboardOut)
async def layout(did: uuid.UUID, body: sc.LayoutPut, request: Request, if_match: str | None = Header(None),
                 p: Principal = Depends(edit), s: AsyncSession = Depends(get_session)):
    return await service.put_layout(s, request, p, did, body.items, _v(if_match))


@router.post("/dashboards/{did}/widgets", response_model=sc.DashboardOut, status_code=201)
async def add_widget(did: uuid.UUID, body: sc.WidgetIn, request: Request, if_match: str | None = Header(None),
                     p: Principal = Depends(edit), s: AsyncSession = Depends(get_session)):
    return await service.add_widget(s, request, p, did, body, _v(if_match))


@router.patch("/dashboards/{did}/widgets/{wid}", response_model=sc.DashboardOut)
async def patch_widget(did: uuid.UUID, wid: uuid.UUID, body: sc.WidgetPatch, request: Request, if_match: str | None = Header(None),
                       p: Principal = Depends(edit), s: AsyncSession = Depends(get_session)):
    return await service.patch_widget(s, request, p, did, wid, body, _v(if_match))


@router.delete("/dashboards/{did}/widgets/{wid}", response_model=sc.DashboardOut)
async def delete_widget(did: uuid.UUID, wid: uuid.UUID, request: Request, if_match: str | None = Header(None),
                        p: Principal = Depends(edit), s: AsyncSession = Depends(get_session)):
    return await service.delete_widget(s, request, p, did, wid, _v(if_match))


@router.post("/dashboards/{did}/data")
async def data(did: uuid.UUID, body: sc.DataRequest, p: Principal = Depends(view), s: AsyncSession = Depends(get_session)):
    return await service.data(s, p, did, body)
