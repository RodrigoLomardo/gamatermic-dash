import io

from openpyxl import Workbook

from app.workers.runner import process_one

API = "/api/v1"

FIELDS = [
    {"name": "pedido", "label": "Pedido", "data_type": "integer", "is_key": True, "source_column": "Pedido"},
    {"name": "cliente", "label": "Cliente", "data_type": "string", "nullable": False, "source_column": "Cliente"},
    {"name": "data", "label": "Data", "data_type": "date", "role": "time", "nullable": False, "source_column": "Data"},
    {"name": "valor", "label": "Valor", "data_type": "decimal", "role": "measure", "nullable": False, "source_column": "Valor"},
    {"name": "marca", "label": "Marca", "data_type": "string", "source_column": "Marca"},
]


async def make_dataset(client, admin, slug="pedidos", mode="upsert", **extra):
    body = {"slug": slug, "name": "Pedidos", "load_mode": mode, "time_field": "data", "fields": FIELDS,
            "parser_options": {}, **extra}
    r = await client.post(f"{API}/datasets", headers=admin, json=body)
    assert r.status_code == 201, r.text
    return r.json()


async def upload(client, admin, dataset_id, content: bytes, name="p.csv", **params):
    r = await client.post(f"{API}/datasets/{dataset_id}/uploads", headers=admin, params=params,
                          files={"file": (name, content, "text/csv")})
    return r


async def run_worker():
    n = 0
    while await process_one():
        n += 1
    return n


async def upload_and_run(client, admin, dataset_id, content, name="p.csv", **params):
    r = await upload(client, admin, dataset_id, content, name, **params)
    assert r.status_code in (200, 202), r.text
    await run_worker()
    return (await client.get(f"{API}/ingestion/runs/{r.json()['id']}", headers=admin)).json()


def xlsx_bytes(rows: list[list], header=("Pedido", "Cliente", "Data", "Valor", "Marca"), sheet="Vendas") -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = sheet
    ws.append(list(header))
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


CSV_OK = ("Pedido;Cliente;Data;Valor;Marca\n"
          "1;ACME;03/01/2026;1.234,56;Parker\n"
          "2;Beta Ltda;04/01/2026;99,90;Danfoss\n"
          "3;Café São João;05/01/2026;10,00;IMI\n")
