"""Contrato de conectores. O nucleo (Extract->Transform->Validate->Load) e o mesmo; so muda o fetch()."""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar, Protocol

from pydantic import BaseModel

from app.modules.ingestion.pipeline.extract import Extracted


@dataclass
class FetchContext:
    parser_options: dict
    config: dict
    secret: str | None = None
    cursor: dict | None = None
    file_path: Path | None = None
    extra: dict = field(default_factory=dict)


class Connector(Protocol):
    kind: ClassVar[str]
    config_schema: ClassVar[type[BaseModel]]
    supports_push: ClassVar[bool]

    async def test_connection(self, ctx: FetchContext) -> None: ...

    def fetch(self, ctx: FetchContext) -> Extracted: ...


REGISTRY: dict[str, Any] = {}


def register(cls):
    REGISTRY[cls.kind] = cls
    return cls


def get_connector(kind: str):
    from app.modules.connectors import csv_upload  # noqa: F401  (registra)

    if kind not in REGISTRY:
        raise KeyError(kind)
    return REGISTRY[kind]()
