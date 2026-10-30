import hashlib
import re
import unicodedata
import uuid
from itertools import islice
from pathlib import Path

from fastapi import Request, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authz.policy import Principal, accessible, require_can
from app.core.config import get_settings
from app.core.errors import Conflict, NotFound, PayloadTooLarge, Unprocessable
from app.modules.audit import service as audit
from app.modules.datasets.models import Dataset, IngestionRowError, IngestionRun, UploadedFile
from app.modules.ingestion import schemas as sc
from app.modules.ingestion.pipeline.extract import extract, list_sheets, sniff_kind
from app.modules.ingestion.pipeline.transform import CoerceError, FieldSpec, coerce
from app.workers.queue import enqueue

ALLOWED_EXT = {".csv", ".txt", ".xlsx"}


def slugify(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    return (s if s and s[0].isalpha() else f"c_{s}")[:60]


async def _store(upload: UploadFile) -> tuple[Path, str, int]:
    s = get_settings()
    d = Path(s.upload_dir)
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{uuid.uuid4().hex}.bin"
    h, size = hashlib.sha256(), 0
    try:
        with path.open("wb") as f:
            while chunk := await upload.read(1024 * 1024):
                size += len(chunk)
                if size > s.max_upload_bytes:
                    raise PayloadTooLarge(f"Arquivo acima do limite de {s.max_upload_bytes // (1024 * 1024)} MB.")
                h.update(chunk)
                f.write(chunk)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    if size == 0:
        path.unlink(missing_ok=True)
        raise Unprocessable("Arquivo vazio.", code="empty_file")
    return path, h.hexdigest(), size


def _check_name(name: str) -> None:
    if Path(name or "").suffix.lower() not in ALLOWED_EXT:
        raise Unprocessable("Extensão não permitida. Use .csv, .txt ou .xlsx.", code="invalid_file")


async def run_out(session: AsyncSession, run: IngestionRun, duplicate: bool = False) -> sc.RunOut:
    out = sc.RunOut.model_validate(run)
    out.duplicate = duplicate
    if run.file_id:
        f = await session.get(UploadedFile, run.file_id)
        out.file_name = f.original_name if f else None
    ds = await session.get(Dataset, run.dataset_id)
    out.dataset_slug = ds.slug if ds else None
    return out


async def accept_upload(session: AsyncSession, request: Request, p: Principal, dataset_id: uuid.UUID, upload: UploadFile,
                        idem_key: str | None, force: bool, sheet: str | None) -> sc.RunOut:
    ds = await session.get(Dataset, dataset_id)
    if ds is None:
        raise NotFound("Dataset não encontrado.")
    await require_can(session, p, "ingestion:upload", "dataset", ds.id, ds.sector_id, "edit")
    if idem_key:
        prev = await session.scalar(select(IngestionRun).where(IngestionRun.idempotency_key == f"{dataset_id}:{idem_key}"))
        if prev:
            return await run_out(session, prev, duplicate=True)
    _check_name(upload.filename or "")
    path, sha, size = await _store(upload)
    try:
        sniff_kind(path)  # valida magic bytes / macros / binarios
        if not force:
            dup = await session.scalar(
                select(IngestionRun).join(UploadedFile, UploadedFile.id == IngestionRun.file_id).where(
                    IngestionRun.dataset_id == dataset_id, UploadedFile.sha256 == sha,
                    IngestionRun.status.in_(["succeeded", "succeeded_with_errors", "queued", "running"]))
                .order_by(IngestionRun.created_at.desc()).limit(1)
            )
            if dup:
                path.unlink(missing_ok=True)
                return await run_out(session, dup, duplicate=True)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    f = UploadedFile(original_name=(upload.filename or "arquivo")[:255], stored_path=path.name, size=size, sha256=sha,
                     detected_mime=upload.content_type, uploaded_by=p.id)
    session.add(f)
    await session.flush()
    rid = getattr(request.state, "request_id", None)
    run = IngestionRun(dataset_id=dataset_id, trigger="manual_upload", triggered_by=p.id, status="queued", file_id=f.id,
                       idempotency_key=f"{dataset_id}:{idem_key}" if idem_key else None, request_id=rid,
                       cursor_state={"sheet": sheet} if sheet else None)
    session.add(run)
    await session.flush()
    await enqueue(session, "run_ingestion", {"run_id": str(run.id)}, request_id=rid)
    await audit.record(session, "ingestion.upload", request=request, principal=p, resource_type="dataset", resource_id=dataset_id,
                       metadata={"file": f.original_name, "size": size, "sha256": sha, "run_id": str(run.id)})
    await session.commit()
    return await run_out(session, run)


async def list_runs(session: AsyncSession, p: Principal, dataset_id: uuid.UUID | None, status: str | None, limit: int, offset: int) -> list[sc.RunOut]:
    all_, direct, sectors = await accessible(session, p, "ingestion:view", "dataset")
    q = select(IngestionRun).order_by(IngestionRun.created_at.desc()).limit(limit).offset(offset)
    if dataset_id:
        q = q.where(IngestionRun.dataset_id == dataset_id)
    if status:
        q = q.where(IngestionRun.status == status)
    if not all_:
        ids = set(direct)
        if sectors:
            ids |= set((await session.scalars(select(Dataset.id).where(Dataset.sector_id.in_(sectors)))).all())
        q = q.where(IngestionRun.dataset_id.in_(ids))
    return [await run_out(session, r) for r in (await session.scalars(q)).all()]


async def _run_checked(session: AsyncSession, p: Principal, rid: uuid.UUID, perm: str = "ingestion:view", level: str = "view") -> IngestionRun:
    run = await session.get(IngestionRun, rid)
    if run is None:
        raise NotFound("Carga não encontrada.")
    ds = await session.get(Dataset, run.dataset_id)
    await require_can(session, p, perm, "dataset", run.dataset_id, ds.sector_id if ds else None, level)
    return run


async def get_run(session: AsyncSession, p: Principal, rid: uuid.UUID) -> sc.RunOut:
    return await run_out(session, await _run_checked(session, p, rid))


async def run_errors(session: AsyncSession, p: Principal, rid: uuid.UUID, limit: int, offset: int) -> list[IngestionRowError]:
    await _run_checked(session, p, rid)
    return list((await session.scalars(select(IngestionRowError).where(IngestionRowError.run_id == rid)
                                       .order_by(IngestionRowError.row_number, IngestionRowError.id).limit(limit).offset(offset))).all())


async def cancel_run(session: AsyncSession, request: Request, p: Principal, rid: uuid.UUID) -> sc.RunOut:
    run = await _run_checked(session, p, rid, "ingestion:upload", "edit")
    if run.status not in ("queued", "running"):
        raise Conflict("A carga não está em andamento.")
    run.cancel_requested = True
    if run.status == "queued":
        run.status = "cancelled"
        run.error_summary = "Carga cancelada pelo usuário."
    await audit.record(session, "ingestion.cancel", request=request, principal=p, resource_type="ingestion_run", resource_id=rid)
    await session.commit()
    return await run_out(session, run)


async def retry_run(session: AsyncSession, request: Request, p: Principal, rid: uuid.UUID) -> sc.RunOut:
    run = await _run_checked(session, p, rid, "ingestion:upload", "edit")
    if run.status not in ("failed", "cancelled"):
        raise Conflict("Somente cargas com falha ou canceladas podem ser reprocessadas.")
    f = await session.get(UploadedFile, run.file_id) if run.file_id else None
    if f is None or f.purged_at is not None:
        raise Conflict("O arquivo original foi removido pela política de retenção; envie novamente.")
    new = IngestionRun(dataset_id=run.dataset_id, trigger="retry", triggered_by=p.id, status="queued", file_id=run.file_id,
                       request_id=getattr(request.state, "request_id", None), cursor_state=run.cursor_state)
    session.add(new)
    await session.flush()
    await enqueue(session, "run_ingestion", {"run_id": str(new.id)}, request_id=new.request_id)
    await audit.record(session, "ingestion.retry", request=request, principal=p, resource_type="ingestion_run", resource_id=new.id,
                       metadata={"of": str(rid)})
    await session.commit()
    return await run_out(session, new)


def _infer_type(values: list) -> tuple[str, bool]:
    vals = [v for v in values if v not in (None, "")]
    if not vals:
        return "string", True
    def all_ok(t):
        for v in vals:
            try:
                coerce(v, FieldSpec("x", t, True, False, {}))
            except CoerceError:
                return False
        return True
    from datetime import date, datetime
    if all(isinstance(v, bool) for v in vals):
        return "boolean", len(vals) < len(values)
    if all(isinstance(v, (date, datetime)) for v in vals):
        return "date", len(vals) < len(values)
    if all(isinstance(v, str) for v in vals) and all_ok("date") and any("/" in v or "-" in v for v in vals):
        return "date", len(vals) < len(values)
    if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in vals) or (all(isinstance(v, str) for v in vals) and all_ok("decimal")):
        ints = all_ok("integer")
        return ("integer" if ints else "decimal"), len(vals) < len(values)
    return "string", len(vals) < len(values)


async def infer_schema(upload: UploadFile, sheet: str | None) -> sc.InferOut:
    _check_name(upload.filename or "")
    path, _, _ = await _store(upload)
    try:
        kind = sniff_kind(path)
        sheets = list_sheets(path) if kind == "xlsx" else []
        ex = extract(path, kind, {"sheet": sheet} if sheet else {})
        sample = [vals for _, vals in islice(ex.rows, 300)]
        cols, used = [], set()
        for i, h in enumerate(ex.header):
            if not h:
                continue
            col = [r[i] if i < len(r) else None for r in sample]
            t, nullable = _infer_type(col)
            name = slugify(h)
            while name in used:
                name += "_2"
            used.add(name)
            key_like = bool(re.search(r"\b(n[uú]mero|c[oó]digo|id)\b", h.casefold())) and t in ("integer", "string")
            role = "time" if t in ("date", "datetime") else ("measure" if t in ("integer", "decimal") and not key_like else "dimension")
            cols.append(sc.InferredField(name=name, label=h, data_type=t, role=role, source_column=h, nullable=nullable,
                                         is_key=False, sample=[str(v)[:40] for v in col[:3] if v not in (None, "")]))
        return sc.InferOut(kind=kind, sheets=sheets, sheet=sheet or (sheets[0] if sheets else None), columns=cols)
    finally:
        path.unlink(missing_ok=True)
