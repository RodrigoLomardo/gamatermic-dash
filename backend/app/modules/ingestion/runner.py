"""Executor de cargas (roda no worker). Idempotente; carga atomica numa unica transacao."""
import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import timedelta
from itertools import islice
from pathlib import Path

from sqlalchemy import select, update

from app.core.config import get_settings
from app.core.db import get_sessionmaker, utcnow
from app.core.errors import DomainError
from app.core.events import notify
from app.core.logging import get_logger
from app.modules.audit import service as audit
from app.modules.connectors.base import FetchContext, get_connector
from app.modules.datasets.models import (
    Dataset,
    DatasetField,
    DataSource,
    IngestionRowError,
    IngestionRun,
    SourceBinding,
    UploadedFile,
)
from app.modules.ingestion.pipeline.load import BATCH, Counters, PreparedRow, finalize_snapshot, merge_batch
from app.modules.ingestion.pipeline.transform import CoerceError, FieldSpec, coerce, occurred_at

log = get_logger("ingestion")
MAX_STORED_ERRORS = 5000


class RunFailed(Exception):
    def __init__(self, summary: str):
        super().__init__(summary)
        self.summary = summary


@dataclass
class _Err:
    row: int
    col: str | None
    code: str
    msg: str
    raw: str | None = None


@dataclass
class _Plan:
    specs: dict[str, FieldSpec]
    col_index: dict[str, int]  # field -> indice da coluna
    col_name: dict[str, str]  # field -> nome da coluna de origem
    key_fields: list[str]
    time_field: str | None
    time_type: str | None
    warnings: list[str] = field(default_factory=list)


def _build_plan(header: list[str], fields: list[DatasetField], mapping: dict[str, str], ds: Dataset) -> _Plan:
    norm = {h.strip().casefold(): i for i, h in enumerate(header) if h}
    by_name = {f.name: f for f in fields}
    specs: dict[str, FieldSpec] = {}
    idx: dict[str, int] = {}
    cname: dict[str, str] = {}
    missing_required: list[str] = []
    missing_optional: list[str] = []
    mapped_fields = set()
    for src, fname in mapping.items():
        f = by_name.get(fname)
        if f is None:
            continue
        mapped_fields.add(fname)
        specs[fname] = FieldSpec(f.name, f.data_type, f.nullable, f.is_key, f.parse_options or {}, f.sensitivity)
        cname[fname] = src
        i = norm.get(src.strip().casefold())
        if i is None:
            (missing_required if (not f.nullable or f.is_key) else missing_optional).append(src)
        else:
            idx[fname] = i
    if missing_required:
        raise RunFailed(f"Colunas obrigatórias ausentes no arquivo: {', '.join(missing_required)}.")
    warnings = []
    if missing_optional:
        warnings.append(f"Colunas opcionais ausentes (ficam vazias): {', '.join(missing_optional)}.")
    used = {h.strip().casefold() for h in cname.values()}
    extra = [h for h in header if h and h.strip().casefold() not in used]
    if extra:
        warnings.append(f"Colunas ignoradas: {', '.join(extra[:10])}{'…' if len(extra) > 10 else ''}.")
    tf = ds.time_field if ds.time_field in specs else None
    return _Plan(specs, idx, cname, list(ds.key_fields or []), tf, specs[tf].data_type if tf else None, warnings)


def _prepare(chunk: list[tuple[int, list]], plan: _Plan, run_id: uuid.UUID) -> tuple[list[PreparedRow], list[_Err]]:
    out, errs = [], []
    for rownum, values in chunk:
        data, bad = {}, False
        for fname, spec in plan.specs.items():
            i = plan.col_index.get(fname)
            raw = values[i] if i is not None and i < len(values) else None
            try:
                data[fname] = coerce(raw, spec)
            except CoerceError as e:
                bad = True
                excerpt = None if spec.sensitivity == "pii" else (str(raw)[:80] if raw is not None else None)
                errs.append(_Err(rownum, plan.col_name.get(fname), e.code, e.message, excerpt))
        if bad:
            continue
        key = "|".join(str(data[k]) for k in plan.key_fields) if plan.key_fields else f"{run_id}:{rownum}"
        out.append(PreparedRow(key, data, occurred_at(data.get(plan.time_field), plan.time_type) if plan.time_field and plan.time_type else None))
    return out, errs


async def execute_run(run_id: uuid.UUID) -> None:
    sm = get_sessionmaker()
    async with sm() as s:
        run = await s.get(IngestionRun, run_id)
        if run is None or run.status in ("succeeded", "succeeded_with_errors", "cancelled"):
            return
        run.status, run.started_at, run.attempt = "running", utcnow(), run.attempt + 1
        ds = await s.get(Dataset, run.dataset_id)
        binding = await s.scalar(select(SourceBinding).where(SourceBinding.dataset_id == run.dataset_id))
        src = await s.get(DataSource, binding.data_source_id) if binding else None
        file = await s.get(UploadedFile, run.file_id) if run.file_id else None
        fields = list((await s.scalars(select(DatasetField).where(DatasetField.dataset_id == run.dataset_id))).all())
        run.dataset_version_before = ds.version if ds else None
        await s.commit()
    if ds is None or binding is None or src is None:
        await _fail(run_id, "Dataset sem fonte/binding configurados.")
        return

    errors: list[_Err] = []
    counters = Counters()
    rows_read = 0
    summary_warnings: list[str] = []
    try:
        opts = dict(binding.parser_options or {})
        if run.cursor_state and run.cursor_state.get("sheet"):
            opts["sheet"] = run.cursor_state["sheet"]
        path = Path(get_settings().upload_dir) / file.stored_path if file else None
        connector = get_connector(src.kind)
        ex = await asyncio.to_thread(connector.fetch, FetchContext(parser_options=opts, config=src.config or {}, file_path=path))
        plan = _build_plan(ex.header, fields, binding.field_mapping or {}, ds)
        summary_warnings = plan.warnings
        async with sm() as ls:  # transacao de carga: tudo ou nada
            while True:
                chunk = await asyncio.to_thread(lambda: list(islice(ex.rows, BATCH)))
                if not chunk:
                    break
                rows_read += len(chunk)
                prepared, errs = await asyncio.to_thread(_prepare, chunk, plan, run_id)
                errors.extend(errs)
                if ds.strict_mode and errs:
                    raise RunFailed("Modo estrito: há linhas inválidas; nenhuma linha foi carregada.")
                await merge_batch(ls, ds.id, run_id, ds.load_mode, prepared, counters)
                async with sm() as cs:
                    r2 = await cs.get(IngestionRun, run_id)
                    if r2 and r2.cancel_requested:
                        raise RunFailed("Carga cancelada pelo usuário.")
            rejected_rows = len({e.row for e in errors})
            if rows_read == 0:
                raise RunFailed("O arquivo não contém linhas de dados.")
            pct = rejected_rows * 100 / rows_read
            if pct > ds.max_reject_pct:
                raise RunFailed(
                    f"{rejected_rows} de {rows_read} linhas rejeitadas ({pct:.1f}%), acima do limite de {ds.max_reject_pct}%. "
                    "Nenhum dado foi alterado."
                )
            removed = await finalize_snapshot(ls, ds.id, run_id) if ds.load_mode == "replace_snapshot" else 0
            from app.modules.datasets.service import refresh_row_count

            dsr = await ls.get(Dataset, ds.id, with_for_update=True)
            assert dsr is not None
            dsr.version += 1
            dsr.last_loaded_at = utcnow()
            dsr.row_count = await refresh_row_count(ls, ds.id)
            runr = await ls.get(IngestionRun, run_id)
            assert runr is not None
            runr.status = "succeeded_with_errors" if rejected_rows else "succeeded"
            runr.finished_at = utcnow()
            runr.rows_read, runr.rows_rejected = rows_read, rejected_rows
            runr.rows_inserted, runr.rows_updated, runr.rows_unchanged = counters.inserted, counters.updated, counters.unchanged
            runr.dataset_version_after = dsr.version
            notes = list(summary_warnings)
            if removed:
                notes.append(f"{removed} linhas removidas (replace_snapshot).")
            runr.error_summary = " ".join(notes) or None
            for e in errors[:MAX_STORED_ERRORS]:
                ls.add(IngestionRowError(run_id=run_id, row_number=e.row, column_name=e.col, error_code=e.code,
                                         message=e.msg, raw_excerpt=e.raw))
            await audit.record(ls, "ingestion.run.finished", actor_type="system", resource_type="ingestion_run",
                               resource_id=run_id, request_id=runr.request_id,
                               metadata={"status": runr.status, "dataset": ds.slug, "read": rows_read, "rejected": rejected_rows})
            await notify(ls, {"type": "dataset_updated", "dataset_id": str(ds.id), "version": dsr.version,
                              "last_loaded_at": dsr.last_loaded_at.isoformat()})
            await ls.commit()
    except RunFailed as e:
        await _fail(run_id, e.summary, errors, rows_read)
    except DomainError as e:
        await _fail(run_id, e.detail, errors, rows_read)
    except Exception as e:  # noqa: BLE001 - erro transitorio/inesperado: marca e deixa a fila tentar de novo
        log.exception("run_failed_unexpected", run_id=str(run_id))
        await _fail(run_id, f"Erro inesperado: {type(e).__name__}", errors, rows_read, final=False)
        raise


async def _fail(run_id: uuid.UUID, summary: str, errors: list[_Err] | None = None, rows_read: int = 0, final: bool = True) -> None:
    async with get_sessionmaker()() as s:
        run = await s.get(IngestionRun, run_id)
        if run is None:
            return
        cancelled = "cancelada" in summary
        run.status = "cancelled" if cancelled else ("failed" if final else "queued")
        run.error_summary = summary
        run.rows_read, run.rows_rejected = rows_read, len({e.row for e in (errors or [])})
        if final:
            run.finished_at = utcnow()
        for e in (errors or [])[:MAX_STORED_ERRORS]:
            s.add(IngestionRowError(run_id=run_id, row_number=e.row, column_name=e.col, error_code=e.code, message=e.msg, raw_excerpt=e.raw))
        if final:
            await audit.record(s, "ingestion.run.finished", actor_type="system", resource_type="ingestion_run", resource_id=run_id,
                               outcome="failure", request_id=run.request_id, metadata={"status": run.status, "summary": summary})
        await s.commit()


async def mark_stuck_runs(minutes: int = 45) -> int:
    async with get_sessionmaker()() as s:
        r = await s.execute(
            update(IngestionRun).where(IngestionRun.status == "running",
                                       IngestionRun.started_at < utcnow() - timedelta(minutes=minutes))
            .values(status="failed", finished_at=utcnow(), error_summary="Carga travada: excedeu o tempo limite.")
        )
        await s.commit()
        return getattr(r, "rowcount", 0) or 0

