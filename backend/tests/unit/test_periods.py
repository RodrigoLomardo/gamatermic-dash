from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from app.modules.query.periods import previous, resolve
from app.modules.query.spec import Period

SP = ZoneInfo("America/Sao_Paulo")


def p(preset="this_month", **kw):
    return Period(mode="relative", preset=preset, **kw)


def local(rng):
    return tuple(x.astimezone(SP).replace(tzinfo=None).isoformat() for x in rng)


def test_this_month_boundaries_use_sao_paulo_not_utc():
    # 01/11 00:30 em SP = 01/11 03:30 UTC; ja e novembro em SP
    now = datetime(2026, 11, 1, 0, 30, tzinfo=SP)
    assert local(resolve(p(), now)) == ("2026-11-01T00:00:00", "2026-12-01T00:00:00")
    # 31/10 23:30 em SP = 01/11 02:30 UTC; ainda e outubro em SP
    now = datetime(2026, 10, 31, 23, 30, tzinfo=SP)
    assert local(resolve(p(), now)) == ("2026-10-01T00:00:00", "2026-11-01T00:00:00")
    assert now.astimezone(UTC).month == 11


def test_year_end_and_leap():
    now = datetime(2026, 12, 31, 23, 59, tzinfo=SP)
    assert local(resolve(p(), now))[1] == "2027-01-01T00:00:00"
    now = datetime(2028, 2, 29, 12, 0, tzinfo=SP)
    assert local(resolve(p(), now)) == ("2028-02-01T00:00:00", "2028-03-01T00:00:00")


def test_last_12_months_and_quarter():
    now = datetime(2026, 10, 30, 9, 0, tzinfo=SP)
    assert local(resolve(p("last_12_months"), now)) == ("2025-11-01T00:00:00", "2026-11-01T00:00:00")
    assert local(resolve(p("this_quarter"), now)) == ("2026-10-01T00:00:00", "2027-01-01T00:00:00")


def test_absolute_inclusive_end():
    per = Period(mode="absolute", **{"from": "2026-01-01", "to": "2026-01-31"})
    assert local(resolve(per)) == ("2026-01-01T00:00:00", "2026-02-01T00:00:00")


def test_all_is_no_filter():
    assert resolve(p("all")) is None and resolve(None) is None


def test_previous_is_same_elapsed_window_mtd():
    now = datetime(2026, 10, 15, 12, 0, tzinfo=SP)
    a, b = previous(p(), now)
    assert local((a, b)) == ("2026-09-01T00:00:00", "2026-09-15T12:00:00")
    now = datetime(2026, 3, 31, 12, 0, tzinfo=SP)  # fev tem menos dias: limitado ao fim do mes anterior
    assert local(previous(p(), now))[1] == "2026-03-01T00:00:00"


def test_previous_rolling():
    now = datetime(2026, 10, 30, 12, 0, tzinfo=SP)
    a, b = previous(p("last_7_days"), now)
    assert (b - a).days == 7 and local((a, b))[1] == "2026-10-24T00:00:00"
