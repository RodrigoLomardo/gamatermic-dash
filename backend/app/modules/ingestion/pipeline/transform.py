"""Transform/Validate: coercao de tipos pt-BR por campo."""
import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

SP = ZoneInfo("America/Sao_Paulo")
TRUE = {"true", "1", "sim", "s", "verdadeiro", "yes", "y", "x"}
FALSE = {"false", "0", "nao", "não", "n", "falso", "no"}


class CoerceError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class FieldSpec:
    name: str
    data_type: str
    nullable: bool
    is_key: bool
    parse_options: dict
    sensitivity: str = "none"


def _norm(s: str) -> str:
    return unicodedata.normalize("NFC", s).strip()


def parse_decimal(v) -> Decimal:
    if isinstance(v, bool):
        raise CoerceError("invalid_decimal", "Valor numérico inválido.")
    if isinstance(v, (int, float, Decimal)):
        return Decimal(str(v))
    s = _norm(str(v)).replace("R$", "").replace(" ", "").replace(" ", "")
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    if s.startswith("-"):
        neg, s = True, s[1:]
    if not s or not re.fullmatch(r"[\d.,]+", s):
        raise CoerceError("invalid_decimal", f"Número inválido: '{str(v)[:40]}'.")
    if "," in s and "." in s:
        dec = "," if s.rfind(",") > s.rfind(".") else "."
        thou = "." if dec == "," else ","
        s = s.replace(thou, "").replace(dec, ".")
    elif "," in s:
        s = s.replace(",", ".") if s.count(",") == 1 else s.replace(",", "")
    elif "." in s and re.fullmatch(r"\d{1,3}(\.\d{3})+", s):
        s = s.replace(".", "")
    try:
        d = Decimal(s)
    except InvalidOperation as e:
        raise CoerceError("invalid_decimal", f"Número inválido: '{str(v)[:40]}'.") from e
    return -d if neg else d


def parse_date(v, fmt: str | None = None) -> date:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = _norm(str(v))
    formats = [fmt] if fmt else ["%d/%m/%Y", "%Y-%m-%d", "%d/%m/%y", "%d-%m-%Y", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"]
    for f in formats:
        try:
            return datetime.strptime(s, f).date()
        except ValueError:
            continue
    raise CoerceError("invalid_date", f"Data inválida: '{s[:30]}'.")


def parse_datetime(v, fmt: str | None = None) -> datetime:
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=SP).astimezone(UTC)
    if isinstance(v, date):
        return datetime(v.year, v.month, v.day, tzinfo=SP).astimezone(UTC)
    s = _norm(str(v))
    for f in ([fmt] if fmt else ["%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%d/%m/%Y", "%Y-%m-%d"]):
        try:
            return datetime.strptime(s, f).replace(tzinfo=SP).astimezone(UTC)
        except ValueError:
            continue
    raise CoerceError("invalid_datetime", f"Data/hora inválida: '{s[:30]}'.")


def coerce(v, f: FieldSpec):
    """Retorna valor JSON-serializavel (decimal->str, date->iso). Levanta CoerceError."""
    if isinstance(v, str):
        v = _norm(v)
    if v is None or v == "":
        if not f.nullable or f.is_key:
            raise CoerceError("required", "Valor obrigatório ausente.")
        return None
    if isinstance(v, str) and v.startswith("=") and f.data_type != "string":
        raise CoerceError("formula_not_computed", "Fórmula sem valor calculado no arquivo.")
    t = f.data_type
    if t == "string":
        if isinstance(v, float) and v.is_integer():
            v = int(v)
        if isinstance(v, (datetime, date)):
            v = v.isoformat()
        return str(v)[:2000]
    if t == "integer":
        d = parse_decimal(v)
        if d != d.to_integral_value():
            raise CoerceError("invalid_integer", f"Inteiro inválido: '{str(v)[:30]}'.")
        return int(d)
    if t == "decimal":
        d = parse_decimal(v)
        return format(d.normalize(), "f") if d != 0 else "0"
    if t == "date":
        return parse_date(v, f.parse_options.get("format")).isoformat()
    if t == "datetime":
        return parse_datetime(v, f.parse_options.get("format")).isoformat()
    if t == "boolean":
        if isinstance(v, bool):
            return v
        s = str(v).strip().lower()
        if s in TRUE:
            return True
        if s in FALSE:
            return False
        raise CoerceError("invalid_boolean", f"Booleano inválido: '{s[:20]}'.")
    raise CoerceError("unknown_type", f"Tipo desconhecido: {t}")


def occurred_at(value: str | None, data_type: str) -> datetime | None:
    if not value:
        return None
    if data_type == "date":
        d = date.fromisoformat(value)
        return datetime(d.year, d.month, d.day, tzinfo=SP).astimezone(UTC)
    return datetime.fromisoformat(value)
