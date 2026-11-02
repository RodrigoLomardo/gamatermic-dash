"""Resolucao de periodos em America/Sao_Paulo (UTC no banco)."""
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.core.errors import Unprocessable
from app.modules.query.spec import Period

SP = ZoneInfo("America/Sao_Paulo")


def _start(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, tzinfo=SP)


def _add_months(d: date, n: int) -> date:
    m = d.month - 1 + n
    return date(d.year + m // 12, m % 12 + 1, 1)


def now_sp() -> datetime:
    return datetime.now(SP)


def resolve(period: Period | None, now: datetime | None = None) -> tuple[datetime, datetime] | None:
    """[inicio, fim) em UTC; None = sem filtro de tempo."""
    if period is None:
        return None
    now = (now or now_sp()).astimezone(SP)
    today = now.date()
    if period.mode == "absolute":
        if not period.from_ or not period.to or period.to < period.from_:
            raise Unprocessable("Período absoluto inválido.", code="invalid_period")
        return _start(period.from_).astimezone(UTC), _start(period.to + timedelta(days=1)).astimezone(UTC)
    p = period.preset
    tomorrow = today + timedelta(days=1)
    if p == "all":
        return None
    if p == "today":
        a, b = today, tomorrow
    elif p == "yesterday":
        a, b = today - timedelta(days=1), today
    elif p == "this_week":
        a = today - timedelta(days=today.weekday())
        b = a + timedelta(days=7)
    elif p == "last_7_days":
        a, b = today - timedelta(days=6), tomorrow
    elif p == "last_30_days":
        a, b = today - timedelta(days=29), tomorrow
    elif p == "last_90_days":
        a, b = today - timedelta(days=89), tomorrow
    elif p == "this_month":
        a = today.replace(day=1)
        b = _add_months(a, 1)
    elif p == "last_month":
        b = today.replace(day=1)
        a = _add_months(b, -1)
    elif p == "this_quarter":
        a = date(today.year, 3 * ((today.month - 1) // 3) + 1, 1)
        b = _add_months(a, 3)
    elif p == "this_year":
        a, b = date(today.year, 1, 1), date(today.year + 1, 1, 1)
    elif p == "last_year":
        a, b = date(today.year - 1, 1, 1), date(today.year, 1, 1)
    elif p == "last_12_months":
        a = _add_months(today.replace(day=1), -11)
        b = _add_months(today.replace(day=1), 1)
    else:  # pragma: no cover
        raise Unprocessable("Período desconhecido.")
    return _start(a).astimezone(UTC), _start(b).astimezone(UTC)


def previous(period: Period | None, now: datetime | None = None) -> tuple[datetime, datetime] | None:
    """Janela anterior comparavel: calendario -> mesmo recorte decorrido (MTD vs MTD); rolante -> janela de igual tamanho."""
    rng = resolve(period, now)
    if rng is None or period is None:
        return None
    now = (now or now_sp()).astimezone(SP)
    a, b = rng
    a_l = a.astimezone(SP)
    if period.mode == "relative" and period.preset in ("this_month", "this_quarter", "this_year"):
        n = {"this_month": 1, "this_quarter": 3, "this_year": 12}[period.preset]
        pa = _add_months(a_l.date(), -n)
        pb_full = a_l.date()
        elapsed = now - a_l
        pb = min(_start(pa) + elapsed, _start(pb_full))
        return _start(pa).astimezone(UTC), pb.astimezone(UTC)
    if period.mode == "relative" and period.preset in ("last_month", "last_year", "last_12_months"):
        months = {"last_month": 1, "last_year": 12, "last_12_months": 12}[period.preset]
        return _start(_add_months(a_l.date(), -months)).astimezone(UTC), a
    length = b - a
    return a - length, a


def previous_year(period: Period | None, now: datetime | None = None) -> tuple[datetime, datetime] | None:
    """Mesmo recorte um ano antes (YoY). Periodo em curso (este mes/ano) segue o decorrido ate hoje: 'mesmo periodo de 2025'."""
    rng = resolve(period, now)
    if rng is None:
        return None
    a, b = (x.astimezone(SP) for x in rng)
    now = (now or now_sp()).astimezone(SP)
    pa = _add_months(a.date(), -12)
    if a <= now < b:  # periodo aberto: so o trecho decorrido (inclui o dia de hoje por inteiro)
        pb = _add_months(now.date(), -12) + timedelta(days=1)
    else:
        pb = _add_months(b.date(), -12)
    return _start(pa).astimezone(UTC), _start(pb).astimezone(UTC)
