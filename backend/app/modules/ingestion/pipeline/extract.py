"""Extract: CSV (encoding/delimitador detectados) e XLSX (somente leitura, anti zip-bomb)."""
import csv
import io
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from openpyxl import load_workbook

from app.core.errors import Unprocessable

MAX_XLSX_UNCOMPRESSED = 200 * 1024 * 1024
MAX_EMPTY_STREAK = 200  # xlsx com ranges "inchados" (ex.: 1M linhas vazias)


@dataclass
class Extracted:
    header: list[str]
    rows: Iterator[tuple[int, list]]  # (numero da linha no arquivo, valores)
    encoding: str | None = None


def sniff_kind(path: Path) -> str:
    """Tipo pelo conteudo (magic bytes), nao pela extensao."""
    with path.open("rb") as f:
        head = f.read(8)
    if head.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(path) as z:
                names = z.namelist()
        except zipfile.BadZipFile as e:
            raise Unprocessable("Arquivo corrompido.", code="invalid_file") from e
        if "xl/workbook.xml" in names:
            if any(n.endswith("vbaProject.bin") for n in names):
                raise Unprocessable("Planilhas com macros não são aceitas.", code="macros_not_allowed")
            return "xlsx"
        raise Unprocessable("Arquivo ZIP não é uma planilha válida.", code="invalid_file")
    if head.startswith(b"\xd0\xcf\x11\xe0") or head.startswith(b"MZ") or head.startswith(b"%PDF") or head.startswith(b"\x7fELF"):
        raise Unprocessable("Tipo de arquivo não suportado.", code="invalid_file")
    sample = path.read_bytes()[:4096]
    if b"\x00" in sample:
        raise Unprocessable("Arquivo binário não suportado.", code="invalid_file")
    return "csv"


def _decode_all(path: Path) -> tuple[str, str]:
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw.decode("utf-8-sig"), "utf-8-sig"
    try:
        return raw.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        pass
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16"), "utf-16"
    # Excel BR salva "CSV" em Windows-1252; detectores genericos erram em amostras curtas (viram CJK)
    try:
        return raw.decode("cp1252"), "cp1252"
    except UnicodeDecodeError:
        return raw.decode("latin-1"), "latin-1"


def _sniff_delimiter(text: str, forced: str | None) -> str:
    if forced:
        return forced
    first = "\n".join(text.splitlines()[:5])
    counts = {d: first.count(d) for d in (";", ",", "\t", "|")}
    best = max(counts, key=lambda d: counts[d])
    return best if counts[best] > 0 else ";"


def extract_csv(path: Path, opts: dict) -> Extracted:
    text, enc = _decode_all(path)
    if opts.get("encoding"):
        text = path.read_bytes().decode(opts["encoding"], errors="replace")
        enc = opts["encoding"]
    delim = _sniff_delimiter(text, opts.get("delimiter"))
    reader = csv.reader(text.splitlines(), delimiter=delim)
    header_row = int(opts.get("header_row", 1))
    header: list[str] = []
    rows_iter = enumerate(reader, start=1)
    for n, r in rows_iter:
        if n == header_row:
            header = [c.strip() for c in r]
            break
    if not header:
        raise Unprocessable("Cabeçalho não encontrado.", code="no_header")

    def gen() -> Iterator[tuple[int, list]]:
        for n, r in rows_iter:
            if not any(c.strip() for c in r):
                continue
            yield n, r

    return Extracted(header, gen(), enc)


def _open_wb(path: Path):
    # openpyxl valida a extensao; o arquivo armazenado e .bin (nome aleatorio), entao abrimos por stream
    return load_workbook(io.BufferedReader(path.open("rb")), read_only=True, data_only=True)  # type: ignore[arg-type]


def extract_xlsx(path: Path, opts: dict) -> Extracted:
    with zipfile.ZipFile(path) as z:
        total = sum(i.file_size for i in z.infolist())
    if total > MAX_XLSX_UNCOMPRESSED:
        raise Unprocessable("Planilha descomprimida grande demais.", code="zip_bomb")
    wb = _open_wb(path)
    sheet = opts.get("sheet")
    if sheet:
        if sheet not in wb.sheetnames:
            wb.close()
            raise Unprocessable(f"Aba '{sheet}' não encontrada. Abas: {', '.join(wb.sheetnames)}", code="sheet_not_found")
        ws = wb[sheet]
    else:
        ws = wb[wb.sheetnames[0]]
    header_row = int(opts.get("header_row", 1))
    it = ws.iter_rows(values_only=True)
    header: list[str] = []
    n = 0
    for n, r in enumerate(it, start=1):
        if n == header_row:
            header = [str(c).strip() if c is not None else "" for c in r]
            break
    if not header:
        wb.close()
        raise Unprocessable("Cabeçalho não encontrado.", code="no_header")

    def gen() -> Iterator[tuple[int, list]]:
        empty = 0
        k = n
        try:
            for r in it:
                k += 1
                if all(c is None or (isinstance(c, str) and not c.strip()) for c in r):
                    empty += 1
                    if empty >= MAX_EMPTY_STREAK:
                        return
                    continue
                empty = 0
                yield k, list(r)
        finally:
            wb.close()

    return Extracted(header, gen())


def extract(path: Path, kind: str, opts: dict) -> Extracted:
    return extract_xlsx(path, opts) if kind == "xlsx" else extract_csv(path, opts)


def list_sheets(path: Path) -> list[str]:
    wb = _open_wb(path)
    try:
        return list(wb.sheetnames)
    finally:
        wb.close()
