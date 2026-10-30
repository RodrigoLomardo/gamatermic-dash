import io
import zipfile

from sqlalchemy import select, text

from app.core.db import get_sessionmaker
from app.modules.datasets.models import DatasetRow
from tests.integration.helpers import (
    API,
    CSV_OK,
    make_dataset,
    run_worker,
    upload,
    upload_and_run,
    xlsx_bytes,
)


async def _rows(ds_id):
    async with get_sessionmaker()() as s:
        return (await s.scalars(select(DatasetRow).where(DatasetRow.dataset_id == ds_id, DatasetRow.deleted_at.is_(None)).order_by(DatasetRow.row_key))).all()


async def test_upload_returns_202_fast_and_worker_loads_ptbr(client, admin):
    ds = await make_dataset(client, admin)
    r = await upload(client, admin, ds["id"], CSV_OK.encode("utf-8"))
    assert r.status_code == 202 and r.json()["status"] == "queued"
    await run_worker()
    run = (await client.get(f"{API}/ingestion/runs/{r.json()['id']}", headers=admin)).json()
    assert run["status"] == "succeeded" and run["rows_inserted"] == 3
    rows = await _rows(ds["id"])
    assert rows[0].data["valor"] == "1234.56" and rows[0].data["data"] == "2026-01-03"
    d = (await client.get(f"{API}/datasets/{ds['id']}", headers=admin)).json()
    assert d["version"] == 1 and d["row_count"] == 3


async def test_latin1_csv_with_bom_and_comma_delimiter(client, admin):
    ds = await make_dataset(client, admin)
    content = "Pedido,Cliente,Data,Valor,Marca\n1,João Ação,2026-01-03,\"1.234,50\",Parker\n".encode("cp1252")
    run = await upload_and_run(client, admin, ds["id"], content)
    assert run["status"] == "succeeded"
    assert (await _rows(ds["id"]))[0].data["cliente"] == "João Ação"
    bom = ("﻿" + CSV_OK).encode("utf-8")
    ds2 = await make_dataset(client, admin, slug="outro")
    assert (await upload_and_run(client, admin, ds2["id"], bom))["status"] == "succeeded"


async def test_reupload_same_file_is_idempotent(client, admin):
    ds = await make_dataset(client, admin)
    first = await upload_and_run(client, admin, ds["id"], CSV_OK.encode())
    dup = await upload(client, admin, ds["id"], CSV_OK.encode())
    assert dup.status_code == 200 and dup.json()["duplicate"] and dup.json()["id"] == first["id"]
    # forcando o reprocessamento: nada duplica, tudo "inalterado"
    forced = await upload_and_run(client, admin, ds["id"], CSV_OK.encode(), force="true")
    assert forced["rows_unchanged"] == 3 and forced["rows_inserted"] == 0
    assert len(await _rows(ds["id"])) == 3


async def test_idempotency_key_header(client, admin):
    ds = await make_dataset(client, admin)
    a = await client.post(f"{API}/datasets/{ds['id']}/uploads", headers={**admin, "Idempotency-Key": "abc"}, files={"file": ("a.csv", CSV_OK.encode())})
    b = await client.post(f"{API}/datasets/{ds['id']}/uploads", headers={**admin, "Idempotency-Key": "abc"}, files={"file": ("b.csv", CSV_OK.replace("ACME", "X").encode())})
    assert a.json()["id"] == b.json()["id"]


async def test_update_changes_only_changed_rows(client, admin):
    ds = await make_dataset(client, admin)
    await upload_and_run(client, admin, ds["id"], CSV_OK.encode())
    changed = CSV_OK.replace("99,90", "100,00") + "4;Novo;06/01/2026;5,00;IMI\n"
    run = await upload_and_run(client, admin, ds["id"], changed.encode())
    assert (run["rows_inserted"], run["rows_updated"], run["rows_unchanged"]) == (1, 1, 2)


async def test_three_percent_errors_loads_valid_and_lists_each(client, admin):
    ds = await make_dataset(client, admin)
    lines = ["Pedido;Cliente;Data;Valor;Marca"] + [f"{i};C{i};03/01/2026;10,00;P" for i in range(1, 98)]
    lines += ["98;Z;31/02/2026;10,00;P", "99;Z;03/01/2026;abc;P", "100;;03/01/2026;1,00;P"]
    run = await upload_and_run(client, admin, ds["id"], "\n".join(lines).encode())
    assert run["status"] == "succeeded_with_errors" and run["rows_inserted"] == 97 and run["rows_rejected"] == 3
    errs = (await client.get(f"{API}/ingestion/runs/{run['id']}/errors", headers=admin)).json()
    assert {(e["row_number"], e["column_name"], e["error_code"]) for e in errs} == {
        (99, "Data", "invalid_date"), (100, "Valor", "invalid_decimal"), (101, "Cliente", "required")}


async def test_reject_threshold_fails_without_touching_data(client, admin):
    ds = await make_dataset(client, admin)
    await upload_and_run(client, admin, ds["id"], CSV_OK.encode())
    bad = "Pedido;Cliente;Data;Valor;Marca\n1;ACME;03/01/2026;777,00;P\n" + "\n".join(f"{i};;x;y;P" for i in range(10, 20))
    run = await upload_and_run(client, admin, ds["id"], bad.encode())
    assert run["status"] == "failed" and "acima do limite" in run["error_summary"]
    rows = await _rows(ds["id"])
    assert len(rows) == 3 and next(r for r in rows if r.row_key == "1").data["valor"] == "1234.56"  # nada mudou
    assert (await client.get(f"{API}/datasets/{ds['id']}", headers=admin)).json()["version"] == 1


async def test_missing_required_column_fails_whole_run(client, admin):
    ds = await make_dataset(client, admin)
    run = await upload_and_run(client, admin, ds["id"], b"Pedido;Cliente;Data;Marca\n1;A;03/01/2026;P\n")
    assert run["status"] == "failed" and "Valor" in run["error_summary"]


async def test_replace_snapshot_removes_missing_rows(client, admin):
    ds = await make_dataset(client, admin, slug="snap", mode="replace_snapshot")
    await upload_and_run(client, admin, ds["id"], CSV_OK.encode())
    run = await upload_and_run(client, admin, ds["id"], b"Pedido;Cliente;Data;Valor;Marca\n1;ACME;03/01/2026;1.234,56;Parker\n4;Z;07/01/2026;1,00;P\n")
    assert run["status"] == "succeeded"
    assert sorted(r.row_key for r in await _rows(ds["id"])) == ["1", "4"]


async def test_failure_mid_load_keeps_current_data(client, admin, monkeypatch):
    ds = await make_dataset(client, admin)
    await upload_and_run(client, admin, ds["id"], CSV_OK.encode())
    import app.modules.ingestion.runner as runner

    real = runner.merge_batch
    calls = {"n": 0}

    async def boom(*a, **k):
        calls["n"] += 1
        await real(*a, **k)
        raise RuntimeError("falha simulada no meio da carga")

    monkeypatch.setattr(runner, "merge_batch", boom)
    r = await upload(client, admin, ds["id"], CSV_OK.replace("ACME", "MUDOU").encode())
    from app.workers.runner import process_one

    await process_one()
    monkeypatch.setattr(runner, "merge_batch", real)
    rows = await _rows(ds["id"])
    assert next(x for x in rows if x.row_key == "1").data["cliente"] == "ACME"  # rollback total
    run = (await client.get(f"{API}/ingestion/runs/{r.json()['id']}", headers=admin)).json()
    assert run["status"] in ("queued", "failed")  # transitorio: volta para a fila com backoff


async def test_rejects_bad_files(client, admin):
    ds = await make_dataset(client, admin)
    assert (await upload(client, admin, ds["id"], b"MZ\x90\x00binary", "x.csv")).status_code == 422
    assert (await upload(client, admin, ds["id"], b"a;b\n1;2\n", "x.exe")).status_code == 422
    assert (await upload(client, admin, ds["id"], b"", "x.csv")).status_code == 422
    z = io.BytesIO()
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("[Content_Types].xml", "x")
        zf.writestr("xl/workbook.xml", "x")
        zf.writestr("xl/vbaProject.bin", "x")
    r = await upload(client, admin, ds["id"], z.getvalue(), "m.xlsx")
    assert r.status_code == 422 and r.json()["code"] == "macros_not_allowed"
    assert (await upload(client, admin, ds["id"], b"PK\x03\x04junk", "z.xlsx")).status_code == 422


async def test_oversize_rejected(client, admin, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "max_upload_bytes", 1000)
    ds = await make_dataset(client, admin)
    r = await upload(client, admin, ds["id"], b"a" * 5000)
    assert r.status_code == 413


async def test_xlsx_with_formula_cells_and_inflated_range(client, admin):
    ds = await make_dataset(client, admin, parser_options={"sheet": "Vendas"})
    import datetime as dt

    content = xlsx_bytes([[1, "ACME", dt.datetime(2026, 1, 3), 1234.56, "Parker"], [2, "Beta", dt.datetime(2026, 1, 4), 10, None]])
    run = await upload_and_run(client, admin, ds["id"], content, "p.xlsx")
    assert run["status"] == "succeeded" and run["rows_inserted"] == 2
    assert (await _rows(ds["id"]))[0].data["valor"] == "1234.56"


async def test_csv_injection_stored_as_text_and_neutralized_on_export(client, admin):
    ds = await make_dataset(client, admin, max_reject_pct=50)
    evil = CSV_OK.replace("ACME", "=cmd|' /C calc'!A0").replace("Beta Ltda", "@SUM(1+1)")
    run = await upload_and_run(client, admin, ds["id"], (evil + "5;Zed;03/01/2026;=1+1;P\n").encode())
    assert run["status"] == "succeeded_with_errors"
    assert (await _rows(ds["id"]))[0].data["cliente"].startswith("=cmd")  # armazenado como texto, nunca formula
    r = await client.get(f"{API}/ingestion/runs/{run['id']}/errors.csv", headers=admin)
    assert r.status_code == 200 and "'=1+1" in r.text and ";=1+1" not in r.text


async def test_cancel_and_retry(client, admin):
    ds = await make_dataset(client, admin)
    r = await upload(client, admin, ds["id"], CSV_OK.encode())
    c = await client.post(f"{API}/ingestion/runs/{r.json()['id']}/cancel", headers=admin)
    assert c.json()["status"] == "cancelled"
    retry = await client.post(f"{API}/ingestion/runs/{r.json()['id']}/retry", headers=admin)
    assert retry.status_code == 202
    await run_worker()
    assert (await client.get(f"{API}/ingestion/runs/{retry.json()['id']}", headers=admin)).json()["status"] == "succeeded"


async def test_infer_schema_from_xlsx_and_csv(client, admin):
    r = await client.post(f"{API}/datasets/infer-schema", headers=admin, files={"file": ("a.csv", CSV_OK.encode())})
    cols = {c["source_column"]: c for c in r.json()["columns"]}
    assert cols["Valor"]["data_type"] == "decimal" and cols["Data"]["data_type"] == "date" and cols["Pedido"]["data_type"] == "integer"
    assert cols["Valor"]["role"] == "measure" and cols["Data"]["role"] == "time"


async def test_viewer_cannot_upload(client, admin):
    from tests.conftest import create_user, login

    ds = await make_dataset(client, admin)
    await create_user("v@gama.com.br", ["Visualizador"])
    h = await login(client, "v@gama.com.br")
    assert (await client.post(f"{API}/datasets/{ds['id']}/uploads", headers=h, files={"file": ("a.csv", CSV_OK.encode())})).status_code == 403


async def test_job_row_count_matches_db(client, admin):
    ds = await make_dataset(client, admin)
    await upload_and_run(client, admin, ds["id"], CSV_OK.encode())
    async with get_sessionmaker()() as s:
        n = await s.scalar(text("select count(*) from jobs where status='done'"))
    assert n == 1
