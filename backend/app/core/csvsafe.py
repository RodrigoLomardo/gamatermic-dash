import csv
import io


def neutralize(value) -> str:
    """Neutraliza CSV/formula injection: celulas iniciadas por = + - @ TAB CR ganham apostrofo."""
    s = "" if value is None else str(value)
    if s and s[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + s
    return s


def to_csv(header: list[str], rows: list[list]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", lineterminator="\r\n")
    w.writerow(header)
    for r in rows:
        w.writerow([neutralize(c) for c in r])
    return "﻿" + buf.getvalue()
