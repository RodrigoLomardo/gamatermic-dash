from datetime import date, datetime
from decimal import Decimal

import pytest

from app.core.csvsafe import neutralize
from app.core.errors import Unprocessable
from app.core.security import validate_password_policy
from app.modules.ingestion.pipeline.transform import CoerceError, FieldSpec, coerce, parse_decimal


def spec(t, nullable=True, **po):
    return FieldSpec("f", t, nullable, False, po)


@pytest.mark.parametrize("raw,expected", [
    ("1.234,56", "1234.56"), ("1234,56", "1234.56"), ("1234.56", "1234.56"), ("R$ 1.234,56", "1234.56"),
    ("(1.234,56)", "-1234.56"), ("-10,5", "-10.5"), ("1.234", "1234"), ("1,234,567", "1234567"), (10, "10"), (12.5, "12.5"),
    ("0,00", "0"),
])
def test_decimal_ptbr(raw, expected):
    assert coerce(raw, spec("decimal")) == expected


@pytest.mark.parametrize("raw", ["abc", "1,2,3x", "--5", "12a", True])
def test_decimal_invalid(raw):
    with pytest.raises(CoerceError):
        coerce(raw, spec("decimal"))


def test_dates():
    assert coerce("03/01/2026", spec("date")) == "2026-01-03"
    assert coerce("2026-01-03", spec("date")) == "2026-01-03"
    assert coerce(datetime(2026, 1, 3, 10, 5), spec("date")) == "2026-01-03"
    assert coerce(date(2026, 1, 3), spec("date")) == "2026-01-03"
    for bad in ("31/02/2026", "ontem", "2026/13/01"):
        with pytest.raises(CoerceError):
            coerce(bad, spec("date"))
    # datetime local de SP vira UTC
    assert coerce("03/01/2026 10:00", spec("datetime")).startswith("2026-01-03T13:00")


def test_required_and_empty():
    with pytest.raises(CoerceError) as e:
        coerce("  ", spec("string", nullable=False))
    assert e.value.code == "required"
    assert coerce("", spec("string")) is None


def test_booleans_integers_strings():
    assert coerce("Sim", spec("boolean")) is True and coerce("não", spec("boolean")) is False and coerce(True, spec("boolean")) is True
    assert coerce(5.0, spec("integer")) == 5 and coerce("1.000", spec("integer")) == 1000
    with pytest.raises(CoerceError):
        coerce("1,5", spec("integer"))
    assert coerce(1234.0, spec("string")) == "1234"
    assert coerce("Café", spec("string")) == "Café"


def test_formula_without_value_is_error_for_numeric():
    with pytest.raises(CoerceError) as e:
        coerce("=INDEX(a,b)", spec("integer"))
    assert e.value.code == "formula_not_computed"


def test_neutralize():
    for s in ("=1+1", "+1", "-1", "@x", "\tx"):
        assert neutralize(s).startswith("'")
    assert neutralize("ok") == "ok" and neutralize(None) == ""


def test_password_policy():
    for bad in ("curta", "aaaaaaaaaaaa", "123456789012", "gamatermic2026"):
        with pytest.raises(Unprocessable):
            validate_password_policy(bad)
    validate_password_policy("uma frase longa sem regras de composição")


def test_parse_decimal_returns_decimal():
    assert parse_decimal("1.234,56") == Decimal("1234.56")
